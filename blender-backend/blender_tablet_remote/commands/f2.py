"""F2 táctil: cuadriláteros continuos, colocados con el gesto que los crea."""
import itertools
import math
import bpy
import bmesh
from mathutils import Vector
from ..bpy_utils import find_view3d
from ..camera import camera
from ..errors import BadPayload, CommandError

_pending = None


def _restore_mesh(obj, backup):
    try:
        if obj.name not in bpy.data.objects: return
        if obj.mode == 'EDIT':
            bm = bmesh.from_edit_mesh(obj.data); bm.clear(); bm.from_mesh(backup)
            bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=True)
        else:
            bm = bmesh.new()
            try: bm.from_mesh(backup); bm.to_mesh(obj.data); obj.data.update()
            finally: bm.free()
    except ReferenceError:
        pass


def _restore(pending):
    _restore_mesh(pending['object'], pending['backup'])


def _dispose(pending):
    for key in ('backup', 'template', 'valid_preview'):
        mesh = pending.get(key)
        if mesh is not None and mesh.name in bpy.data.meshes: bpy.data.meshes.remove(mesh)


def cancel():
    global _pending
    pending, _pending = _pending, None
    if pending is None: return
    try: _restore(pending)
    finally: _dispose(pending)


def _view(payload):
    try: u, v = float(payload['u']), float(payload['v'])
    except (KeyError, TypeError, ValueError) as exc: raise BadPayload('F2 necesita el punto del visor') from exc
    if not (math.isfinite(u) and math.isfinite(v) and 0 <= u <= 1 and 0 <= v <= 1):
        raise BadPayload('Punto fuera del visor')
    found = find_view3d()
    if found is None: raise CommandError('Se necesita una vista 3D', code='no_viewport')
    camera.sync_from_region(found[3])
    return u, v, found[3]


def _on_plane(payload, point, normal):
    u, v, rv = _view(payload)
    origin, direction = camera.ray(u, v, rv)
    denominator = direction.dot(normal)
    if abs(denominator) < 1e-7:
        raise CommandError('Mira el plano de la cara de frente para colocar el vértice', code='topology_incompatible')
    return origin + direction * ((point - origin).dot(normal) / denominator)


def _score(point, payload):
    u, v, rv = _view(payload)
    screen = camera.project(point, rv)
    return (Vector(screen) - Vector((u,v))).length_squared if screen else float('inf')


def _normal(points):
    candidates = [(b-a).cross(c-a) for a,b,c in itertools.combinations(points,3)]
    normal = max(candidates, key=lambda n:n.length_squared)
    scale = max((a-b).length_squared for a,b in itertools.combinations(points,2))
    if normal.length_squared <= max(scale*scale*1e-12, 1e-30):
        raise CommandError('Los puntos están alineados y no forman un cuadrilátero', code='topology_incompatible')
    return normal.normalized()


def _ordered_four(vertices, world):
    points = [world @ v.co for v in vertices]
    normal = _normal(points); center = sum(points, Vector()) / 4
    x = normal.orthogonal().normalized(); y = normal.cross(x)
    return [item[1] for item in sorted((math.atan2((p-center).dot(y), (p-center).dot(x)),v)
                                       for p,v in zip(points,vertices))]


def _face(bm, vertices):
    # Compartir una arista exige un sentido opuesto al de su cara vecina.
    for i, first in enumerate(vertices):
        second = vertices[(i+1)%4]
        edge = bm.edges.get((first,second))
        if edge and edge.link_faces:
            loop = next(loop for loop in edge.link_faces[0].loops if loop.edge == edge)
            if loop.vert == first: vertices = list(reversed(vertices))
            break
    return bm.faces.new(vertices)


def _edge_quad(bm, obj, edge_vertices, payload, existing_face=None):
    a,b = edge_vertices
    world=obj.matrix_world; inverse=world.inverted()
    p,q=world@a.co,world@b.co
    normal=(camera.rotation @ Vector((0,0,1))).normalized()
    center=(p+q)*.5
    outward=normal.cross(q-p)
    if outward.length < 1e-10: raise CommandError('Mira la arista desde otra vista',code='topology_incompatible')
    outward.normalize();outward *= (q-p).length
    if existing_face is not None:
        face_center=world@existing_face.calc_center_median()
        if outward.dot(center-face_center)<0:outward.negate()
    c=bm.verts.new(inverse@(q+outward));d=bm.verts.new(inverse@(p+outward))
    face=_face(bm,[a,b,c,d])
    # Con cuatro vértices sobre una cara, nace fuera de ella y el arrastre la recoloca.
    anchor=_on_plane(payload,center,normal) if existing_face is not None else center+outward
    return face,[d,c],center,normal,anchor


def _build(pending, payload):
    obj=pending['object'];bm=bmesh.from_edit_mesh(obj.data);world=obj.matrix_world
    vertices=[v for v in bm.verts if v.select and not v.hide]
    if not 1<=len(vertices)<=4:
        raise CommandError('F2 usa de uno a cuatro vértices o una arista',code='incompatible_selection')
    moving=[]
    if len(vertices)==4:
        existing=next((f for f in bm.faces if set(f.verts)==set(vertices)),None)
        if existing is None:
            face=_face(bm,_ordered_four(vertices,world));point=world@vertices[0].co
            normal=world.to_3x3().inverted().transposed()@face.normal
            anchor=point
        else:
            edges=[e for e in existing.edges if not e.hide and len(e.link_faces)<2]
            if not edges: raise CommandError('Esta cara no tiene una arista de borde para continuar',code='topology_incompatible')
            u,v,rv=_view(payload)
            from .selection import _point_segment_distance
            def score(edge):
                screen=[camera.project(world@vert.co,rv) for vert in edge.verts]
                if None in screen:return float('inf')
                return _point_segment_distance(Vector((u,v)),Vector(screen[0]),Vector(screen[1]))
            edge=min(edges,key=score)
            face,moving,point,normal,anchor=_edge_quad(bm,obj,list(edge.verts),payload,existing)
    elif len(vertices)==2:
        face,moving,point,normal,anchor=_edge_quad(bm,obj,vertices,payload)
    else:
        if len(vertices)==1:
            corner=vertices[0]
            neighbors=[e.other_vert(corner) for e in corner.link_edges
                       if not e.hide and len(e.link_faces)<2 and not e.other_vert(corner).hide]
            choices=[]
            for a,c in itertools.combinations(neighbors,2):
                if any(corner in f.verts and a in f.verts and c in f.verts for f in bm.faces):continue
                points=[world@v.co for v in (a,corner,c)]
                try:normal=_normal(points)
                except CommandError:continue
                predicted=points[0]+points[2]-points[1]
                choices.append((_score(predicted,payload),a,corner,c,normal,predicted))
        else:
            choices=[]
            for corner in vertices:
                a,c=[v for v in vertices if v!=corner]
                connected=bm.edges.get((a,corner)) is not None and bm.edges.get((corner,c)) is not None
                points=[world@v.co for v in (a,corner,c)]
                normal=_normal(points);predicted=points[0]+points[2]-points[1]
                choices.append((_score(predicted,payload) + (0 if connected else 100),a,corner,c,normal,predicted))
        if not choices:raise CommandError('Elige una esquina con dos aristas de borde, o selecciona una arista',code='topology_incompatible')
        _,a,b,c,normal,predicted=min(choices,key=lambda item:item[0])
        new=bm.verts.new(world.inverted()@predicted)
        face=_face(bm,[a,b,c,new]);moving=[new];point=world@b.co;anchor=predicted
    for seq in (bm.verts,bm.edges,bm.faces):
        for elem in seq:elem.select=False
    bm.select_history.clear()
    if moving:
        if bpy.context.scene.tool_settings.mesh_select_mode[1] and len(moving)==2:
            front=bm.edges.get(tuple(moving));front.select_set(True);bm.select_history.add(front)
        else:
            for vert in moving:vert.select_set(True);bm.select_history.add(vert)
    else:
        for vert in vertices:vert.select_set(True)
    bm.select_flush_mode();bm.verts.index_update();bm.faces.index_update();bm.normal_update()
    template=bpy.data.meshes.new('.remote_f2_template');bm.to_mesh(template)
    pending.update(template=template,moving=[v.index for v in moving],face_index=face.index,
                   plane_point=point,plane_normal=normal,anchor=anchor,placing=True)


def _place(pending,payload):
    obj=pending['object'];_restore_mesh(obj,pending['template']);bm=bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table();bm.faces.ensure_lookup_table()
    if pending['moving']:
        target=_on_plane(payload,pending['plane_point'],pending['plane_normal'])
        delta=obj.matrix_world.inverted().to_3x3()@(target-pending['anchor'])
        for index in pending['moving']:bm.verts[index].co+=delta
    face=bm.faces[pending['face_index']]
    points=[obj.matrix_world@v.co for v in face.verts]
    lengths=[(points[(i+1)%4]-points[i]).length_squared for i in range(4)]
    first=(points[1]-points[0]).cross(points[2]-points[0])
    second=(points[2]-points[0]).cross(points[3]-points[0])
    if min(lengths)<=max(lengths)*1e-12 or (first+second).length_squared <= max(lengths)**2*1e-12 or first.dot(second)<-max(lengths)**2*1e-12:
        raise CommandError('Coloca los vértices sin cruzar ni aplastar la cara',code='topology_incompatible')
    bm.normal_update();bmesh.update_edit_mesh(obj.data,loop_triangles=True,destructive=True)
    if pending.get('valid_preview') is None:pending['valid_preview']=bpy.data.meshes.new('.remote_f2_valid')
    bm.to_mesh(pending['valid_preview']);pending['face']=True;pending['error']=None


def _begin(pending,payload):
    from .snap import query_edit_surface_candidate
    obj=pending['object'];u,v,_=_view(payload)
    edge_mode=bpy.context.scene.tool_settings.mesh_select_mode[1]
    hit=query_edit_surface_candidate(obj,u,v,True,'EDGE' if edge_mode else 'AUTO')
    if hit.get('hit') and hit.get('snap_type') in {'VERTEX','EDGE','EDGE_CENTER'}:
        bm=bmesh.from_edit_mesh(obj.data)
        if hit['snap_type']=='VERTEX':
            bm.verts.ensure_lookup_table();target=bm.verts[int(hit['element'])]
            target.select_set(not target.select)
        else:
            ids={int(i) for i in str(hit['element']).split('-')}
            target=next(e for e in bm.edges if {vert.index for vert in e.verts}==ids)
            only_edge={vert.index for vert in bm.verts if vert.select}==ids
            for seq in (bm.verts,bm.edges,bm.faces):
                for elem in seq:elem.select=False
            target.select_set(not only_edge)
        bm.select_history.clear()
        if target.select:bm.select_history.add(target)
        bm.select_flush_mode();bmesh.update_edit_mesh(obj.data,loop_triangles=False,destructive=False)
        if sum(vert.select and not vert.hide for vert in bm.verts)!=4:return
    _build(pending,payload)
    _place(pending,payload)


def gesture(payload,tool):
    global _pending
    from .. import state
    from ..bpy_utils import undo_push
    tool.require_armed_owner(payload.get('_client_id'))
    identifier=payload.get('gesture_id')
    if not isinstance(identifier,str) or not identifier:raise BadPayload('F2 necesita un ID de gesto')
    phase=str(payload.get('phase','')).upper()
    if phase not in {'BEGIN','UPDATE','END','CANCEL'}:raise BadPayload('Fase F2 desconocida')
    try:valid=tool.obj==bpy.context.object and tool.obj.mode=='EDIT' and tool.obj.type=='MESH'
    except ReferenceError:valid=False
    if not valid:
        tool.disarm();raise CommandError('La malla de F2 ha cambiado',code='session_invalidated')
    if phase=='BEGIN':
        cancel();backup=bpy.data.meshes.new('.remote_f2_touch');bmesh.from_edit_mesh(tool.obj.data).to_mesh(backup)
        _pending=dict(id=identifier,object=tool.obj,backup=backup,face=False,error=None,placing=False)
    elif _pending is None or _pending['id']!=identifier:
        return dict(tool.status(),state=state.snapshot(include_view=False))
    if phase=='CANCEL':cancel()
    elif phase=='END':
        pending,_pending=_pending,None
        try:
            if pending['error'] is not None and not pending['face']:
                _restore(pending);raise pending['error']
            if pending['face']:undo_push('Remote F2 cuadrilátero')
        finally:_dispose(pending)
    elif phase=='BEGIN' or _pending['placing']:
        pending=_pending
        try:
            if phase=='BEGIN':_begin(pending,payload)
            else:_place(pending,payload)
        except Exception as exc:
            _restore_mesh(pending['object'],pending.get('valid_preview') or pending['backup'])
            pending['error']=exc if isinstance(exc,CommandError) else CommandError('No se pudo preparar el cuadrilátero',code='topology_incompatible')
    result=dict(tool.status(),state=state.snapshot(include_view=False))
    if _pending and _pending.get('error'):result['instruction']=str(_pending['error'])
    return result
