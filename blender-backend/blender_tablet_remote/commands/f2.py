"""Native F2 face completion, aimed through the tablet camera instead of the PC mouse."""
import importlib
from types import SimpleNamespace
import bpy
import bmesh
from ..bpy_utils import active_object, edit_bmesh, find_view3d, view3d_override
from ..camera import camera
from ..errors import BadPayload, CommandError


def _create_face(payload):
    obj = active_object(); bm = edit_bmesh(obj)
    selected = [v for v in bm.verts if v.select and not v.hide]
    edges = [e for e in bm.edges if e.select and not e.hide]
    if not (len(selected)>=3 or len(selected)==1 or len(selected)==2 and len(edges)==1):
        raise CommandError('Selecciona un vértice, una arista del borde o varios vértices para formar la cara', code='incompatible_selection')
    if any(e.hide or any(v.hide for v in e.verts) for v in selected for e in v.link_edges if len(e.link_faces)<2):
        raise CommandError('Muestra las aristas vecinas antes de completar esta cara', code='incompatible_selection')
    try:
        u,v = float(payload['u']),float(payload['v'])
    except (KeyError,TypeError,ValueError) as exc:
        raise BadPayload('F2 necesita el punto del visor') from exc
    if not 0<=u<=1 or not 0<=v<=1:raise BadPayload('Punto fuera del visor')
    found = find_view3d()
    if found is None:raise CommandError('Se necesita una vista 3D',code='no_viewport')
    try:
        rna = bpy.ops.mesh.f2.get_rna_type()
        cls = bpy.types.Operator.bl_rna_get_subclass_py(rna.identifier)
        addon = importlib.import_module(cls.__module__)
    except (AttributeError,KeyError,RuntimeError,ImportError) as exc:
        raise CommandError('El add-on F2 no está habilitado',code='dependency_unavailable') from exc
    camera.sync_from_region(found[3])
    region = found[2]
    remote_view = SimpleNamespace(perspective_matrix=camera.perspective_matrix(found[3]).copy())
    context = SimpleNamespace(active_object=obj, object=obj, mode='EDIT_MESH', region=region,
        space_data=SimpleNamespace(region_3d=remote_view), preferences=bpy.context.preferences,
        selected_objects=list(bpy.context.selected_objects))
    event = SimpleNamespace(mouse_region_x=u*region.width, mouse_region_y=(1-v)*region.height)
    backup = bpy.data.meshes.new('.remote_f2_backup'); bm.to_mesh(backup)
    face_count = len(bm.faces)
    try:
        with view3d_override():
            # Call the add-on's geometry helpers: its invoke path would open a PC translate modal.
            if len(selected)>=3:
                bpy.ops.mesh.edge_face_add('EXEC_DEFAULT', False)
            elif len(selected)==1:addon.quad_from_vertex(bm,selected[0],context,event)
            else:addon.quad_from_edge(bm,edges[0],context,event)
        bm = bmesh.from_edit_mesh(obj.data)
        if len(bm.faces) <= face_count:
            raise CommandError('No hay una cara que F2 pueda completar desde esta selección',code='topology_incompatible')
        if any(face.calc_area() <= 1e-16 * max((edge.calc_length()**2 for edge in face.edges),default=1.0)
               for face in list(bm.faces)[face_count:]):
            raise CommandError('Los puntos no forman una cara con superficie',code='topology_incompatible')
        bmesh.update_edit_mesh(obj.data,loop_triangles=True,destructive=True)
    except Exception as exc:
        if obj.mode != 'EDIT':
            with view3d_override():bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(obj.data);bm.clear();bm.from_mesh(backup)
        bmesh.update_edit_mesh(obj.data,loop_triangles=True,destructive=True)
        if isinstance(exc,CommandError):raise
        raise CommandError('F2 no puede completar esa cara desde esta vista',code='topology_incompatible') from exc
    finally:
        bpy.data.meshes.remove(backup)
    return True


_pending = None


def _restore(pending):
    obj, backup = pending['object'], pending['backup']
    try:
        if obj.name not in bpy.data.objects: return
        if obj.mode == 'EDIT':
            bm = bmesh.from_edit_mesh(obj.data); bm.clear(); bm.from_mesh(backup)
            bmesh.update_edit_mesh(obj.data,loop_triangles=True,destructive=True)
        else:
            bm = bmesh.new()
            try: bm.from_mesh(backup); bm.to_mesh(obj.data); obj.data.update()
            finally: bm.free()
    except ReferenceError:
        pass


def cancel():
    global _pending
    pending, _pending = _pending, None
    if pending is None: return
    try: _restore(pending)
    finally:
        if pending['backup'].name in bpy.data.meshes: bpy.data.meshes.remove(pending['backup'])


def gesture(payload, tool):
    global _pending
    from .. import state
    from ..bpy_utils import undo_push
    tool.require_armed_owner(payload.get('_client_id'))
    identifier = payload.get('gesture_id')
    if not isinstance(identifier,str) or not identifier: raise BadPayload('F2 necesita un ID de gesto')
    phase = str(payload.get('phase','')).upper()
    if phase not in {'BEGIN','UPDATE','END','CANCEL'}: raise BadPayload('Fase F2 desconocida')
    try:
        valid = tool.obj == bpy.context.object and tool.obj.mode == 'EDIT' and tool.obj.type == 'MESH'
    except ReferenceError: valid = False
    if not valid:
        tool.disarm()
        raise CommandError('La malla de F2 ha cambiado',code='session_invalidated')
    if phase == 'BEGIN':
        cancel()
        backup = bpy.data.meshes.new('.remote_f2_touch')
        bmesh.from_edit_mesh(tool.obj.data).to_mesh(backup)
        _pending = dict(id=identifier,object=tool.obj,backup=backup,face=False,error=None)
    elif _pending is None or _pending['id'] != identifier:
        return dict(tool.status(),state=state.snapshot(include_view=False))
    if phase == 'CANCEL':
        cancel()
    elif phase == 'END':
        pending, _pending = _pending, None
        try:
            if pending['error'] is not None:
                _restore(pending)
                raise pending['error']
            if pending['face']: undo_push('Remote F2 completar cara')
        finally: bpy.data.meshes.remove(pending['backup'])
    else:
        pending = _pending
        _restore(pending)
        pending['face'], pending['error'] = False, None
        try:
            from .snap import query_edit_surface_candidate
            obj = tool.obj
            edge_mode = bpy.context.scene.tool_settings.mesh_select_mode[1]
            hit = query_edit_surface_candidate(obj, float(payload['u']), float(payload['v']), True, 'EDGE' if edge_mode else 'AUTO')
            if hit.get('hit') and hit.get('snap_type') in {'VERTEX','EDGE','EDGE_CENTER'}:
                bm = bmesh.from_edit_mesh(obj.data)
                if hit['snap_type'] == 'VERTEX':
                    bm.verts.ensure_lookup_table(); target = bm.verts[int(hit['element'])]
                else:
                    indices = {int(i) for i in str(hit['element']).split('-')}
                    target = next(e for e in bm.edges if {v.index for v in e.verts} == indices)
                target.select_set(not target.select)
                bm.select_history.clear()
                if target.select: bm.select_history.add(target)
                bm.select_flush_mode()
                bmesh.update_edit_mesh(obj.data,loop_triangles=False,destructive=False)
            else:
                _create_face(payload)
                pending['face'] = True
        except CommandError as exc:
            _restore(pending)
            pending['error'] = exc
        except Exception as exc:
            _restore(pending)
            pending['error'] = CommandError('No se pudo preparar la cara F2',code='topology_incompatible')
    result = dict(tool.status(),state=state.snapshot(include_view=False))
    if _pending and _pending.get('error'): result['instruction'] = str(_pending['error'])
    return result
