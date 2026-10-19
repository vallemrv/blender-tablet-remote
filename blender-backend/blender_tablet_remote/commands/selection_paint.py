"""Pincel de selección: cada elemento se invierte una vez por trazo reversible."""
import math
import bpy
import bmesh
from mathutils import Vector
from . import command
from .. import state
from ..camera import camera
from ..bpy_utils import find_view3d, get_float, undo_push
from ..errors import BadPayload, CommandError

_session = None


def _valid(s):
    try:
        if bpy.context.scene.session_uid != s['scene']:return False
        if s['mode']=='OBJECT':return bpy.context.mode=='OBJECT'
        obj=s['object']
        if obj.name not in bpy.data.objects or obj.mode!='EDIT' or obj.data!=s['data']:return False
        if s['mode']=='CURVE':
            from .curve_edit import topology
            return topology(obj)==s['topology']
        bm=bmesh.from_edit_mesh(obj.data)
        return (len(bm.verts),len(bm.edges),len(bm.faces))==s['topology'] and tuple(bpy.context.scene.tool_settings.mesh_select_mode)==s['select_mode']
    except ReferenceError:return False


def _restore(s):
    if not _valid(s):return
    if s['mode']=='OBJECT':
        for obj,value in s['baseline']:
            try:obj.select_set(value)
            except (ReferenceError,RuntimeError):pass
        try:bpy.context.view_layer.objects.active=s['active']
        except (ReferenceError,RuntimeError):pass
    elif s['mode']=='CURVE':
        from .curve_edit import set_selection
        set_selection(s['object'],s['baseline'])
    else:
        bm=bmesh.from_edit_mesh(s['data'])
        for seq,flags in zip((bm.verts,bm.edges,bm.faces),s['baseline']):
            for elem,value in zip(seq,flags):elem.select=value
        bm.select_flush_mode();bmesh.update_edit_mesh(s['data'],loop_triangles=False,destructive=False)


def cancel(*, restore=True):
    global _session
    s,_session=_session,None
    if s and restore:_restore(s)


def owner_disconnected(owner):
    if _session and _session['owner']==owner:cancel()


def _begin(payload):
    from ..cad.runtime import runtime as cad
    from ..materials.runtime import runtime as materials
    if cad.workspace or materials.active or bpy.context.mode not in {'OBJECT','EDIT_MESH','EDIT_CURVE'}:
        raise CommandError('Pintar selección requiere Object o Edit de malla/curva',code='wrong_mode')
    from .sessions import cancel_all
    cancel_all()
    obj=bpy.context.view_layer.objects.active
    s=dict(owner=payload.get('_client_id'),id=payload['stroke_id'],scene=bpy.context.scene.session_uid,
           object=obj,active=obj,touched=set(),mode='OBJECT')
    if obj and obj.mode=='EDIT':
        s['data']=obj.data
        if obj.type=='CURVE':
            from .curve_edit import selected,topology
            s.update(mode='CURVE',baseline=selected(obj),topology=topology(obj))
        elif obj.type=='MESH':
            bm=bmesh.from_edit_mesh(obj.data)
            for seq in (bm.verts,bm.edges,bm.faces):seq.ensure_lookup_table();seq.index_update()
            flags=tuple(bpy.context.scene.tool_settings.mesh_select_mode)
            s.update(mode='MESH',select_mode=flags,kind=flags.index(True),
                     topology=(len(bm.verts),len(bm.edges),len(bm.faces)),
                     baseline=[[e.select for e in seq] for seq in (bm.verts,bm.edges,bm.faces)])
        else:raise CommandError('Pintar selección requiere objetos, mallas o curvas',code='wrong_type')
    elif bpy.context.mode!='OBJECT':raise CommandError('Pintar selección requiere Object o Edit',code='wrong_mode')
    else:s['baseline']=[(o,o.select_get()) for o in bpy.context.view_layer.objects]
    return s


def _paint(s,payload):
    from .selection import _point_segment_distance,_object_hit,_edit_cage_raycast
    from .snap import _visible,_screen_candidates
    found=find_view3d()
    if not found:raise CommandError('No 3D viewport available',code='no_viewport')
    _,area,region,rv3d=found;camera.sync_from_region(rv3d)
    radius=get_float(payload,'radius',.05)
    if not .001<=radius<=.5:raise BadPayload('Radio de selección fuera de rango')
    aspect=max(1,region.width)/max(1,region.height)
    a=Vector((get_float(payload,'u0',.5),get_float(payload,'v0',.5)/aspect))
    b=Vector((get_float(payload,'u1',.5),get_float(payload,'v1',.5)/aspect))
    count=min(128,max(1,math.ceil((b-a).length/(radius*.5))))
    stamps=[a.lerp(b,i/count) for i in range(count+1)]
    viewport=area.spaces.active if area else None
    graph=bpy.context.evaluated_depsgraph_get()
    def visible(position):
        screen=camera.project(position,rv3d)
        if screen is None:return False
        clip=camera.perspective_matrix(rv3d)@Vector((*position,1.))
        return -clip.w<=clip.z<=clip.w and (s.get('object') and s['object'].show_in_front or _visible(position,screen,graph,rv3d,set(),viewport))
    if s['mode']=='OBJECT':
        baseline={o.session_uid:value for o,value in s['baseline'] if o.name in bpy.data.objects}
        for stamp in stamps:
            for dx,dy in ((0,0),(.7,0),(-.7,0),(0,.7),(0,-.7)):
                u,v=stamp.x+dx*radius,(stamp.y+dy*radius)*aspect
                if not (0<=u<=1 and 0<=v<=1):continue
                origin,direction=camera.ray(u,v,rv3d)
                hit=_object_hit(u,v,origin,direction,rv3d,region,area,graph,radius)
                if hit and not hit[0].hide_select and hit[0].session_uid in baseline:
                    s['touched'].add(hit[0].session_uid)
        for obj,value in s['baseline']:
            if obj.session_uid in s['touched']:obj.select_set(not value)
        active=bpy.context.view_layer.objects.active
        if active is None or not active.select_get():
            bpy.context.view_layer.objects.active=next((o for o in bpy.context.view_layer.objects if o.select_get()),None)
        return
    obj=s['object']
    if s['mode']=='CURVE':
        from .curve_edit import controls,set_selection
        for key,co,_ in controls(obj):
            position=obj.matrix_world@co;screen=camera.project(position,rv3d)
            if screen and _point_segment_distance(Vector((screen[0],screen[1]/aspect)),a,b)<=radius:
                if obj.show_in_front or _visible(position,screen,graph,rv3d,{obj.name},viewport):s['touched'].add(key)
        set_selection(obj,s['baseline']^s['touched']);return
    bm=bmesh.from_edit_mesh(obj.data);seq=(bm.verts,bm.edges,bm.faces)[s['kind']]
    seq.ensure_lookup_table()
    if s['kind']==1:
        edges={'-'.join(str(i) for i in sorted(v.index for v in edge.verts)):edge for edge in bm.edges}
        for stamp in stamps:
            for distance,key,position in _screen_candidates(obj,'EDGE',rv3d,Vector((stamp.x,stamp.y*aspect)),aspect,set()):
                if distance<=radius and visible(position):s['touched'].add(edges[key].index)
    else:
        for elem in seq:
            if elem.hide:continue
            co=elem.co if s['kind']==0 else elem.calc_center_median()
            position=obj.matrix_world@co;screen=camera.project(position,rv3d)
            if screen and _point_segment_distance(Vector((screen[0],screen[1]/aspect)),a,b)<=radius and visible(position):
                s['touched'].add(elem.index)
        if s['kind']==2:
            for stamp in stamps:
                origin,direction=camera.ray(stamp.x,stamp.y*aspect,rv3d)
                hit=_edit_cage_raycast(obj,origin,direction)
                if hit and not bm.faces[hit[1]].hide and visible(hit[0]):s['touched'].add(hit[1])
    _restore(s)
    for index in s['touched']:seq[index].select=not s['baseline'][s['kind']][index]
    bm.select_flush_mode();bmesh.update_edit_mesh(obj.data,loop_triangles=False,destructive=False)


@command('selection.paint',mutating=True)
def paint(payload):
    global _session
    phase=str(payload.get('phase','')).upper()
    if phase not in {'BEGIN','UPDATE','END','CANCEL'}:raise BadPayload('Fase de selección no válida')
    identifier=payload.get('stroke_id')
    if not isinstance(identifier,str) or not identifier:raise BadPayload('El trazo necesita una identidad')
    if phase=='BEGIN':
        if _session and _session['owner']!=payload.get('_client_id'):
            raise CommandError('El trazo pertenece a otra conexión',code='session_owned')
        _session=_begin(payload)
    s=_session
    if s is None or s['id']!=identifier or s['owner']!=payload.get('_client_id'):
        return dict(state.snapshot(include_view=False),paint_active=False)
    if phase=='CANCEL' or not _valid(s):cancel()
    elif phase=='END':
        _session=None
        if s['touched']:undo_push('Remote paint selection')
    else:
        try:_paint(s,payload)
        except Exception:cancel();raise
    return dict(state.snapshot(include_view=False),paint_active=_session is not None)
