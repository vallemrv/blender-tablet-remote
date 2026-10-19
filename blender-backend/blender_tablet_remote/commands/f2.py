"""Native F2 face completion, aimed through the tablet camera instead of the PC mouse."""
import importlib
from types import SimpleNamespace
import bpy
import bmesh
from ..bpy_utils import active_object, edit_bmesh, find_view3d, view3d_override
from ..camera import camera
from ..errors import BadPayload, CommandError


def complete(payload):
    from .sessions import cancel_all
    cancel_all()
    obj = active_object(); bm = edit_bmesh(obj)
    selected = [v for v in bm.verts if v.select and not v.hide]
    edges = [e for e in bm.edges if e.select and not e.hide]
    if not (len(selected)==1 or len(selected)==2 and len(edges)==1):
        raise CommandError('F2 necesita un vértice o una arista del borde', code='incompatible_selection')
    if any(e.hide or any(v.hide for v in e.verts) for v in selected for e in v.link_edges if len(e.link_faces)<2):
        raise CommandError('Muestra las aristas vecinas antes de completar esta cara', code='incompatible_selection')
    try:
        u,v = float(payload['u']),float(payload['v'])
    except (KeyError,TypeError,ValueError) as exc:
        raise BadPayload('F2 necesita el punto de la pulsación larga') from exc
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
            if len(selected)==1:addon.quad_from_vertex(bm,selected[0],context,event)
            else:addon.quad_from_edge(bm,edges[0],context,event)
        bm = bmesh.from_edit_mesh(obj.data)
        if len(bm.faces) <= face_count:
            raise CommandError('No hay una cara que F2 pueda completar desde esta selección',code='topology_incompatible')
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
    from ..bpy_utils import undo_push
    from .. import state
    undo_push('Remote F2 completar cara')
    return state.snapshot(include_view=False)
