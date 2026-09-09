"""Native sculpt strokes, replayed as one reversible Blender undo step.

Only the main-thread pump calls this module. The temporary object transform adapts
Blender's native brush view to the independent remote camera; rv3d is never written.
"""
from __future__ import annotations

import math
import bpy
from bpy.app.handlers import persistent
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

from ..bpy_utils import active_object, find_view3d, view3d_override, undo_push
from ..camera import camera
from ..errors import BadPayload, CommandError
from . import command

_BRUSHES = {
    'DRAW': ('Dibujar', 'Draw'), 'CLAY': ('Arcilla', 'Clay'),
    'INFLATE': ('Inflar', 'Inflate/Deflate'), 'CREASE': ('Pliegue', 'Crease Sharp'),
    'FLATTEN': ('Aplanar', 'Flatten/Contrast'), 'GRAB': ('Agarrar', 'Grab'),
    'SMOOTH': ('Suavizar', 'Smooth'), 'MASK': ('Máscara', 'Mask'),
    'PINCH': ('Pellizcar', 'Pinch/Magnify'),
}
_settings = dict(brush='DRAW', radius=.04, strength=.5,
                 pressure_strength=True, pressure_size=False)
_stroke = None
_replaying = False
_cancelled_redo = None
_saved_preview = False


def _number(value, name, low, high):
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise BadPayload(f'{name} debe ser un número')
    if not math.isfinite(result) or not low <= result <= high:
        raise BadPayload(f'{name} debe estar entre {low} y {high}')
    return result


def _mesh():
    from ..cad.runtime import FEATURE_KEY
    obj = active_object()
    if obj.type != 'MESH' or obj.mode != 'SCULPT':
        raise CommandError('Selecciona una malla y entra en Sculpt', code='wrong_mode')
    if obj.get(FEATURE_KEY):
        raise CommandError('Convierte la pieza CAD a malla antes de esculpir', code='cad_mesh_protected')
    if any(m.type == 'MULTIRES' for m in obj.modifiers) and obj.data.users - int(obj.data.use_fake_user) > 1:
        raise CommandError('Multires requiere una malla propia: duplica Normal, no Enlazada, antes de esculpir', code='shared_mesh')
    if obj.data.library or obj.library:
        raise CommandError('La malla enlazada no se puede esculpir', code='read_only')
    return obj


def status():
    obj = bpy.context.view_layer.objects.active
    mesh = obj if obj and obj.type == 'MESH' else None
    sd = bpy.context.scene.tool_settings.sculpt
    modifier = next((m for m in mesh.modifiers if m.type == 'MULTIRES'), None) if mesh else None
    result = dict(_settings, available=not bpy.app.background and bpy.app.version >= (4, 4, 0),
                  active=bool(mesh and mesh.mode == 'SCULPT'),
                  symmetry={axis: bool(getattr(mesh, 'use_mesh_mirror_' + axis, axis == 'x'))
                            for axis in 'xyz'},
                  dyntopo={'enabled': bool(mesh and mesh.use_dynamic_topology_sculpting),
                           'detail': float(sd.detail_size) if sd else 12.0},
                  multires={'name': modifier.name if modifier else '',
                            'level': modifier.sculpt_levels if modifier else 0,
                            'total_levels': modifier.total_levels if modifier else 0},
                  brushes=[{'id': key, 'label': label, 'icon': key}
                           for key, (label, _) in _BRUSHES.items()])
    return result


def _result(**kwargs):
    return dict(kwargs, sculpt=status())


def _activate(brush_id):
    name = _BRUSHES[brush_id][1]
    with view3d_override():
        result = bpy.ops.brush.asset_activate(
            asset_library_type='ESSENTIALS',
            relative_asset_identifier=f'brushes/essentials_brushes-mesh_sculpt.blend/Brush/{name}')
    if 'FINISHED' not in result:
        raise CommandError(f'No se pudo cargar el pincel {name}', code='brush_unavailable')
    brush = bpy.context.scene.tool_settings.sculpt.brush
    # Essential assets are shared with the desktop: change only the parameters
    # exposed by the tablet, preserving the actual native brush behavior.
    brush.strength = _settings['strength']
    brush.use_pressure_strength = _settings['pressure_strength']
    brush.use_pressure_size = _settings['pressure_size']
    brush.use_locked_size = 'SCENE'
    brush.falloff_shape = 'SPHERE'
    sd = bpy.context.scene.tool_settings.sculpt
    unified = getattr(sd, 'unified_paint_settings', None)
    if unified is None:
        unified = bpy.context.scene.tool_settings.unified_paint_settings
    unified.use_unified_size = False
    unified.use_unified_strength = False
    return brush


def enter():
    _mesh()
    if bpy.app.background or bpy.app.version < (4, 4, 0):
        raise CommandError('Escultura requiere Blender 4.4 o posterior con ventana 3D', code='no_viewport')
    _activate(_settings['brush'])
    # The native sculpt undo encoder requires a memfile baseline after changing
    # modes from a timer; without it the first native undo can crash Blender.
    undo_push('Entrar en Escultura')


@command('sculpt.settings')
def settings(payload):
    _mesh()
    if _stroke:
        raise CommandError('Termina el trazo antes de cambiar sus ajustes', code='session_active')
    values = dict(_settings)
    if 'brush' in payload:
        brush = str(payload['brush']).upper()
        if brush not in _BRUSHES:
            raise BadPayload('Pincel desconocido')
        values['brush'] = brush
    for key, low, high in [('radius', .002, .3), ('strength', 0, 1)]:
        if key in payload:
            values[key] = _number(payload[key], key, low, high)
    for key in ('pressure_strength', 'pressure_size'):
        if key in payload:
            if not isinstance(payload[key], bool):
                raise BadPayload(f'{key} debe ser booleano')
            values[key] = payload[key]
    symmetry = payload.get('symmetry', {})
    if not isinstance(symmetry, dict) or any(k not in {'x', 'y', 'z'} or not isinstance(v, bool) for k, v in symmetry.items()):
        raise BadPayload('Simetría requiere x/y/z booleanos')
    _settings.update(values)
    obj = _mesh()
    for axis, enabled in symmetry.items():
        setattr(obj, 'use_mesh_mirror_' + axis, enabled)
    _activate(_settings['brush'])
    return _result()


def _copy_multires_mesh():
    # Native Multires undo crossing a memfile can retain flushed MDisps. Keep
    # its complete native mesh in a private temporary .blend: RNA copies alone
    # are invalidated by Blender's undo decode and lose those displacement grids.
    import os
    import tempfile
    obj = _mesh()
    fd, path = tempfile.mkstemp(prefix='tablet-sculpt-', suffix='.blend')
    os.close(fd)
    try:
        with view3d_override():
            bpy.ops.object.mode_set(mode='OBJECT')
            try:
                mesh = obj.data.copy()
                try:
                    indices = [face.material_index for face in mesh.polygons]
                    mesh.materials.clear()
                    for face, index in zip(mesh.polygons, indices):
                        face.material_index = index
                    bpy.data.libraries.write(path, {mesh}, compress=False)
                finally:
                    bpy.data.meshes.remove(mesh)
            finally:
                bpy.ops.object.mode_set(mode='SCULPT')
        return path
    except Exception:
        os.unlink(path)
        raise


def _replace_multires_mesh(path):
    obj = _mesh()
    with view3d_override():
        bpy.ops.object.mode_set(mode='OBJECT')
        try:
            with bpy.data.libraries.load(path, link=False) as (source, target):
                target.meshes = list(source.meshes)
            previous = obj.data
            name = previous.name
            materials = list(previous.materials)
            obj.data = target.meshes[0]
            for material in materials:
                obj.data.materials.append(material)
            if previous.users == 0:
                bpy.data.meshes.remove(previous)
                obj.data.name = name
        finally:
            bpy.ops.object.mode_set(mode='SCULPT')
    bpy.context.view_layer.update()


def _discard_mesh(path):
    if path is not None:
        import os
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


def _undo_preview():
    global _replaying
    if not _stroke or not _stroke['preview']:
        return
    _replaying = True
    try:
        with view3d_override():
            bpy.ops.ed.undo()
        bpy.context.view_layer.update()
        _stroke['preview'] = False
        if _stroke.get('multires_baseline') is not None:
            _replace_multires_mesh(_stroke['multires_baseline'])
        obj = _mesh()
        for axis, enabled in _stroke['symmetry'].items():
            setattr(obj, 'use_mesh_mirror_' + axis, enabled)
        bpy.context.scene.tool_settings.sculpt.detail_size = _stroke['detail']
    finally:
        _replaying = False


def cancel(*, restore=True):
    global _stroke, _cancelled_redo
    if not _stroke or _replaying:
        return
    try:
        if restore:
            had_preview = _stroke['preview']
            _undo_preview()
            if had_preview:
                _cancelled_redo = 0
    finally:
        _discard_mesh(_stroke.get('multires_baseline'))
        _stroke = None


def owner_disconnected(owner):
    if _stroke and _stroke['owner'] == owner:
        cancel()


def redo_allowed():
    return _cancelled_redo is None or _cancelled_redo > 0


def history_traversed(undo):
    global _cancelled_redo
    if _cancelled_redo is not None:
        _cancelled_redo += 1 if undo else -1


def history_changed():
    global _cancelled_redo
    _cancelled_redo = None


def _sample(point):
    if not isinstance(point, dict):
        raise BadPayload('Cada punto debe ser un objeto')
    return {'u': _number(point.get('u'), 'u', 0, 1),
            'v': _number(point.get('v'), 'v', 0, 1),
            'pressure': _number(point.get('pressure', 1), 'pressure', 0, 1),
            'time': _number(point.get('time', 0), 'time', 0, 1e15)}


def _location(obj, point, rv3d):
    origin, direction = camera.ray(point['u'], point['v'], rv3d)
    inv = obj.matrix_world.inverted_safe()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    from .. import bridge
    usable, world = bridge._capture.sculpt_surface(point['u'], point['v'], obj, rv3d)
    if usable:
        if world is None:
            return None
        # The depth contains the whole scene. Reject any other visible mesh
        # between the camera and that pixel before admitting a sculpt sample.
        hit, location, normal, index, target, matrix = bpy.context.scene.ray_cast(depsgraph, origin, direction)
        if hit and target.original != obj and (location-origin).length < (world-origin).length + 1e-4:
            return None
        return inv @ world
    visible, location, normal, index, target, matrix = bpy.context.scene.ray_cast(depsgraph, origin, direction)
    if visible and target.original != obj:
        return None
    evaluated = obj.evaluated_get(depsgraph)
    hit, local, normal, index = evaluated.ray_cast(inv @ origin, (inv.to_3x3() @ direction).normalized())
    if not hit:
        return None
    return local.copy()


def _map_samples(points):
    obj = _mesh()
    found = find_view3d()
    if not found:
        raise CommandError('Falta la vista 3D', code='no_viewport')
    rv3d = found[3]
    camera.sync_from_region(rv3d)
    result = []
    for point in points:
        if point['pressure'] <= 0:
            continue
        if _stroke['brush'] == 'GRAB' and _stroke['points']:
            anchor = obj.matrix_world @ Vector(_stroke['points'][0]['location'])
            origin, direction = camera.ray(point['u'], point['v'], rv3d)
            normal = camera.rotation @ Vector((0, 0, 1))
            denom = direction.dot(normal)
            if abs(denom) < 1e-8:
                continue
            world = origin + direction * ((anchor - origin).dot(normal) / denom)
            local = obj.matrix_world.inverted_safe() @ world
        else:
            local = _location(obj, point, rv3d)
        if local is not None:
            result.append(dict(point, location=list(local)))
    return result


def _preview():
    global _cancelled_redo
    _undo_preview()
    obj = _mesh()
    points = _stroke['points']
    if not points:
        return
    window, area, region, rv3d = find_view3d()
    brush = _activate(_stroke['brush'])
    original = obj.matrix_world.copy()
    adapter = rv3d.view_matrix.inverted_safe() @ camera.view_matrix()
    first_world = original @ Vector(points[0]['location'])
    depth = abs((camera.view_matrix() @ first_world).z)
    projection = camera.projection_matrix(rv3d)
    span = 2 * (depth if camera.perspective == 'PERSP' else 1) / max(abs(projection[1][1]), 1e-9)
    # Blender 5 reports diameter; older supported versions report radius.
    world_factor = 2 if 'Diameter' in brush.bl_rna.properties['unprojected_size'].description else 1
    pixel_factor = 2 if 'Diameter' in brush.bl_rna.properties['size'].description else 1
    brush.unprojected_size = world_factor * span * _settings['radius'] / max(max(abs(v) for v in obj.scale), 1e-9)
    brush.size = max(1, min(5000, int(pixel_factor * _settings['radius'] * region.height)))
    records = []
    try:
        if adapter @ original != original:
            obj.matrix_world = adapter @ original
            bpy.context.view_layer.update()
        for i, point in enumerate(points):
            world = obj.matrix_world @ Vector(point['location'])
            mouse = location_3d_to_region_2d(region, rv3d, world)
            if mouse is None:
                continue
            records.append(dict(name='Tablet', location=point['location'], mouse=list(mouse),
                                mouse_event=list(mouse), pressure=point['pressure'],
                                size=brush.size, time=point['time'], is_start=i == 0,
                                x_tilt=0.0, y_tilt=0.0))
        if records:
            with bpy.context.temp_override(window=window, area=area, region=region):
                result = bpy.ops.sculpt.brush_stroke('EXEC_DEFAULT', True, stroke=records,
                                                   override_location=False,
                                                   mode='INVERT' if _stroke['invert'] else 'NORMAL')
            if 'FINISHED' not in result:
                raise CommandError('Blender no pudo aplicar el trazo', code='stroke_failed')
            _stroke['preview'] = True
            _cancelled_redo = None
    finally:
        if obj.matrix_world != original:
            obj.matrix_world = original
            bpy.context.view_layer.update()


@command('sculpt.stroke')
def stroke(payload):
    global _stroke
    phase = str(payload.get('phase', '')).lower()
    identity = payload.get('stroke_id')
    owner = payload.get('_client_id')
    if not isinstance(identity, str) or not identity or len(identity) > 128:
        raise BadPayload('stroke_id requerido')
    if phase not in {'begin', 'update', 'end', 'cancel'}:
        raise BadPayload('Fase de trazo desconocida')
    if phase != 'begin':
        if not _stroke or _stroke['id'] != identity or _stroke['owner'] != owner:
            return _result(active=False, stroke_id=identity, stale=True)
        if phase == 'cancel':
            cancel()
            return _result(active=False, stroke_id=identity)
        if phase == 'end':
            applied = _stroke['preview']
            if applied and _stroke.get('multires_baseline') is not None:
                final_mesh = None
                try:
                    final_mesh = _copy_multires_mesh()
                    _undo_preview()
                    _replace_multires_mesh(final_mesh)
                    undo_push('Trazo de Escultura')
                except Exception:
                    cancel()
                    raise
                finally:
                    _discard_mesh(final_mesh)
            _discard_mesh(_stroke.get('multires_baseline'))
            _stroke = None
            return _result(active=False, stroke_id=identity, changed=applied)
    raw = payload.get('points', [])
    if not isinstance(raw, list) or len(raw) > 128:
        raise BadPayload('Se admiten hasta 128 puntos por mensaje')
    points = [_sample(point) for point in raw]
    _mesh()
    if bpy.app.background:
        raise CommandError('El pincel necesita Blender con ventana', code='no_viewport')
    if phase == 'begin':
        if _stroke and _stroke['id'] == identity and _stroke['owner'] == owner:
            return _result(active=True, stroke_id=identity, stale=True)
        if _stroke and _stroke['owner'] != owner:
            raise CommandError('Otra tablet tiene un trazo activo', code='session_owned')
        from .sessions import cancel_all
        cancel_all()
        _stroke = dict(id=identity, owner=owner, points=[], preview=False,
                       brush='SMOOTH' if payload.get('smooth') else _settings['brush'],
                       invert=bool(payload.get('invert')), multires_baseline=None,
                       symmetry=status()['symmetry'], detail=status()['dyntopo']['detail'])
        obj = _mesh()
        if obj.use_dynamic_topology_sculpting or any(m.type == 'MULTIRES' for m in obj.modifiers):
            try:
                _stroke['multires_baseline'] = _copy_multires_mesh()
            except Exception:
                _stroke = None
                raise
        else:
            from array import array
            coords = array('f', [0]) * (len(obj.data.vertices) * 3)
            obj.data.vertices.foreach_get('co', coords)
            mask = obj.data.attributes.get('.sculpt_mask')
            masks = array('f', [0]) * len(obj.data.vertices)
            if mask:
                mask.data.foreach_get('value', masks)
            _stroke['save_coords'] = coords
            _stroke['save_masks'] = masks
    if len(_stroke['points']) + len(points) > 4096:
        result = stroke(dict(phase='end', stroke_id=identity, _client_id=owner))
        return dict(result, limit_reached=True, message='Trazo confirmado: levanta el lápiz para continuar')
    mapped = _map_samples(points)
    if mapped:
        _stroke['points'].extend(mapped)
        try:
            _preview()
        except Exception:
            cancel()
            raise
    return _result(active=True, stroke_id=identity, hit=bool(mapped))


@command('sculpt.dyntopo')
def dyntopo(payload):
    cancel()
    obj = _mesh()
    enabled = payload.get('enabled', obj.use_dynamic_topology_sculpting)
    if not isinstance(enabled, bool):
        raise BadPayload('enabled debe ser booleano')
    detail = _number(payload.get('detail', bpy.context.scene.tool_settings.sculpt.detail_size), 'detail', 1, 40)
    if enabled and any(m.type == 'MULTIRES' for m in obj.modifiers):
        raise CommandError('Dyntopo y Multires son alternativas: retira Multires para activar Dyntopo', code='incompatible_modifier')
    if enabled and obj.data.shape_keys:
        raise CommandError('Dyntopo no admite claves de forma', code='incompatible_mesh')
    changed = enabled != obj.use_dynamic_topology_sculpting
    with view3d_override():
        if changed:
            bpy.ops.sculpt.dynamic_topology_toggle('EXEC_DEFAULT', True)
        sd = bpy.context.scene.tool_settings.sculpt
        sd.detail_size = detail
        sd.detail_type_method = 'RELATIVE'
        sd.detail_refine_method = 'SUBDIVIDE_COLLAPSE'
    if changed:
        history_changed()
    return _result()


@command('sculpt.multires')
def multires(payload):
    cancel()
    obj = _mesh()
    if obj.use_dynamic_topology_sculpting:
        raise CommandError('Desactiva Dyntopo antes de usar Multires', code='incompatible_modifier')
    action = str(payload.get('action', 'add')).lower()
    if action not in {'add', 'subdivide', 'level'}:
        raise BadPayload('Acción Multires desconocida')
    modifier = next((m for m in obj.modifiers if m.type == 'MULTIRES'), None)
    if action == 'level' and modifier is None:
        raise CommandError('Añade Multires primero', code='not_found')
    if action == 'level':
        level = int(_number(payload.get('level'), 'level', 0, modifier.total_levels))
    if modifier and action == 'add':
        return _result()
    with view3d_override():
        bpy.ops.object.mode_set(mode='OBJECT')
        try:
            if modifier is None:
                modifier = obj.modifiers.new('Multires', 'MULTIRES')
            if action in {'add', 'subdivide'}:
                if modifier.total_levels >= 6:
                    raise CommandError('Máximo de 6 niveles Multires desde la tablet', code='resolution_limit')
                bpy.ops.object.multires_subdivide(modifier=modifier.name, mode='CATMULL_CLARK')
                level = modifier.total_levels
            modifier.sculpt_levels = level
            modifier.levels = level
        finally:
            bpy.ops.object.mode_set(mode='SCULPT')
    undo_push('Multires tablet')
    history_changed()
    return _result()


@command('sculpt.mask')
def mask(payload):
    cancel()
    _mesh()
    action = str(payload.get('action', '')).lower()
    if action not in {'clear', 'invert'}:
        raise BadPayload('Acción de máscara desconocida')
    with view3d_override():
        bpy.ops.paint.mask_flood_fill('EXEC_DEFAULT', True, mode='INVERT' if action == 'invert' else 'VALUE', value=0)
    history_changed()
    return _result()


def finish_saved_preview():
    global _saved_preview
    if _saved_preview:
        _saved_preview = False
        cancel()
    return None


@persistent
def _save_pre(*_):
    global _saved_preview
    if not _stroke or not _stroke['preview']:
        return
    # Undo from save_pre crashes native Blender: serialize the baseline here,
    # then close its native undo step after the save operator has returned.
    if _stroke.get('multires_baseline'):
        _replace_multires_mesh(_stroke['multires_baseline'])
    else:
        obj = _mesh()
        with view3d_override():
            bpy.ops.object.mode_set(mode='OBJECT')
            obj.data.vertices.foreach_set('co', _stroke['save_coords'])
            mask = obj.data.attributes.get('.sculpt_mask')
            if mask:
                mask.data.foreach_set('value', _stroke['save_masks'])
            obj.data.update()
            bpy.ops.object.mode_set(mode='SCULPT')
    _saved_preview = True
    if not bpy.app.timers.is_registered(finish_saved_preview):
        bpy.app.timers.register(finish_saved_preview, first_interval=0)


@persistent
def _discard_before_load(*_):
    cancel(restore=False)


@persistent
def _reset(*_):
    global _stroke, _cancelled_redo, _saved_preview
    _saved_preview = False
    from .. import bridge
    bridge._capture._sculpt_depth = None
    if _stroke:
        _discard_mesh(_stroke.get('multires_baseline'))
    _stroke = None
    _cancelled_redo = None


@persistent
def _external_history(*_):
    global _stroke
    if not _replaying and _stroke:
        _discard_mesh(_stroke.get('multires_baseline'))
        _stroke = None


def register_handlers():
    for name, callback in [('save_pre', _save_pre), ('load_pre', _discard_before_load),
                           ('load_post', _reset), ('undo_post', _external_history), ('redo_post', _external_history)]:
        handlers = getattr(bpy.app.handlers, name)
        if callback not in handlers:
            handlers.append(callback)


def unregister_handlers():
    cancel()
    if bpy.app.timers.is_registered(finish_saved_preview):
        bpy.app.timers.unregister(finish_saved_preview)
    for name, callback in [('save_pre', _save_pre), ('load_pre', _discard_before_load),
                           ('load_post', _reset), ('undo_post', _external_history), ('redo_post', _external_history)]:
        handlers = getattr(bpy.app.handlers, name)
        if callback in handlers:
            handlers.remove(callback)
