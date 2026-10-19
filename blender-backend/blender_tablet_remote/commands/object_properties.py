"""Inspector Object: esquema contextual y cambios atómicos, sin sesión transform."""
import hashlib
import json
import math
import uuid

import bpy
from mathutils import Quaternion, Vector

from . import command
from ..bpy_utils import undo_push
from ..errors import BadPayload, CommandError

_EPOCH = uuid.uuid4().hex


def _identity(obj):
    return f'{_EPOCH}:{bpy.context.scene.session_uid}:{obj.session_uid}'


def _rotation(obj):
    if obj.rotation_mode == 'QUATERNION':
        return obj.rotation_quaternion.to_euler('XYZ')
    if obj.rotation_mode == 'AXIS_ANGLE':
        angle, *axis = obj.rotation_axis_angle
        return Quaternion(Vector(axis), angle).to_euler('XYZ')
    return obj.rotation_euler.copy()


def describe(obj):
    if obj is None or obj.mode != 'OBJECT':
        return None
    from ..cad.runtime import FEATURE_KEY, runtime
    from ..materials.runtime import runtime as materials
    from .modal import session
    from .tools import tool_session
    if session.active or tool_session.active or tool_session.armed_tool:
        return None
    if runtime.workspace or materials.active or obj.get(FEATURE_KEY):
        return None
    scale = bpy.context.scene.unit_settings.scale_length or 1.
    values, fields = {}, []
    editable = obj.library is None or obj.override_library is not None

    def field(key, label, group, value, kind='number', unit='', **extra):
        values[key] = value
        fields.append(dict(id=key, label=label, group=group, type=kind, unit=unit,
                           read_only=not editable, **extra))

    for i, axis in enumerate('XYZ'):
        field(f'location_{axis.lower()}', axis, 'Posición', obj.location[i] * scale, unit='length')
        fields[-1]['read_only'] |= obj.lock_location[i]

    rotation = _rotation(obj)
    non_euler_locked = obj.rotation_mode in {'QUATERNION', 'AXIS_ANGLE'} and (
        any(obj.lock_rotation) or (obj.lock_rotations_4d and obj.lock_rotation_w))
    for i, axis in enumerate('XYZ'):
        field(f'rotation_{axis.lower()}', axis, 'Rotación', math.degrees(rotation[i]), unit='angle')
        fields[-1]['read_only'] |= obj.lock_rotation[i] or non_euler_locked

    image = obj.type == 'EMPTY' and obj.empty_display_type == 'IMAGE'
    if obj.type in {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META', 'LATTICE'}:
        for i, axis in enumerate('XYZ'):
            field(f'dimension_{axis.lower()}', axis, 'Tamaño', obj.dimensions[i] * scale,
                  unit='length', min=0.)
            # Escala cero conserva la geometría: Blender puede recuperar dimensions.
            # Solo un eje plano en la geometría local carece de extensión recuperable.
            local_span = max(c[i] for c in obj.bound_box) - min(c[i] for c in obj.bound_box)
            fields[-1]['read_only'] |= obj.lock_scale[i] or local_span <= 0.
    elif obj.type == 'EMPTY':
        limits = obj.bl_rna.properties['empty_display_size']
        field('display_size', 'Tamaño', 'Tamaño',
              obj.empty_display_size * scale, unit='length', min=limits.hard_min * scale,
              max=limits.hard_max * scale)
        if not image:
            for i, axis in enumerate('XYZ'):
                field(f'scale_{axis.lower()}', f'Escala {axis}', 'Tamaño', obj.scale[i], unit='factor')
                fields[-1]['read_only'] |= obj.lock_scale[i]

    from .circle_properties import describe as describe_circle
    circle = describe_circle(obj)
    if circle:
        field('circle_vertices', 'Resolución', 'Círculo', circle['count'], unit='count', min=3, max=4096)
    if obj.type == 'CURVE':
        limits = obj.data.bl_rna.properties['resolution_u']
        field('curve_resolution', 'Resolución', 'Curva', obj.data.resolution_u, unit='count',
              min=limits.hard_min, max=limits.hard_max)
    field('visible', 'Visible en la vista', 'Visibilidad', not obj.hide_get(), 'bool')
    if obj.type != 'EMPTY':
        field('render', 'Visible en render', 'Visibilidad', not obj.hide_render, 'bool')
    field('in_front', 'Mostrar delante', 'Visibilidad', obj.show_in_front, 'bool')
    if image:
        field('opacity', 'Opacidad', 'Imagen', obj.color[3] if obj.use_empty_image_alpha else 1.,
              unit='percent', min=0., max=1.)
        field('orthographic', 'En ortográfica', 'Imagen', obj.show_empty_image_orthographic, 'bool')
        field('perspective', 'En perspectiva', 'Imagen', obj.show_empty_image_perspective, 'bool')
        field('axis_only', 'Solo vista alineada', 'Imagen', obj.show_empty_image_only_axis_aligned, 'bool')
        field('depth', 'Profundidad', 'Imagen', obj.empty_image_depth, 'enum',
              choices={'DEFAULT': 'Normal', 'FRONT': 'Delante', 'BACK': 'Detrás'})
        field('side', 'Lados visibles', 'Imagen', obj.empty_image_side, 'enum',
              choices={'DOUBLE_SIDED': 'Ambos', 'FRONT': 'Frontal', 'BACK': 'Trasero'})
    revision = hashlib.sha256(json.dumps([values, fields], sort_keys=True).encode()).hexdigest()[:20]
    return dict(id=_identity(obj), name=obj.name, revision=revision, values=values, fields=fields,
                note='Posición local respecto al padre.' if obj.parent else 'Posición en los ejes de la escena.')


def _require_idle():
    from .modal import session
    from .tools import tool_session
    from ..cad.runtime import runtime
    from ..materials.runtime import runtime as materials
    if session.active or tool_session.active or tool_session.armed_tool or runtime.session or materials.active:
        raise CommandError('Confirma o cancela la herramienta antes de editar las propiedades', code='session_active')


@command('object.properties', mutating=True)
def apply(payload):
    _require_idle()
    obj = bpy.context.view_layer.objects.active
    current = describe(obj)
    if not current or current['id'] != payload.get('object_id'):
        raise CommandError('El objeto activo ha cambiado; revisa sus propiedades', code='object_changed')
    if current['revision'] != payload.get('revision'):
        raise CommandError('El objeto cambió mientras escribías. Cancela el borrador y vuelve a editar.', code='properties_changed')
    changes = payload.get('values')
    if not isinstance(changes, dict) or not changes:
        raise BadPayload('Indica las propiedades que quieres cambiar')
    schema = {f['id']: f for f in current['fields']}
    validated = {}
    for key, value in changes.items():
        spec = schema.get(key)
        if not spec or spec['read_only']:
            raise BadPayload(f'Propiedad no editable: {key}')
        if spec['type'] == 'bool':
            if type(value) is not bool:
                raise BadPayload(f'{key} requiere verdadero o falso')
        elif spec['type'] == 'enum':
            if not isinstance(value, str) or value not in spec['choices']:
                raise BadPayload(f'Opción no válida para {key}')
        else:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise BadPayload(f'{key} requiere un número finito')
            if value < spec.get('min', -math.inf) or value > spec.get('max', math.inf):
                raise BadPayload(f'{key} está fuera del rango permitido')
            if spec['unit'] == 'count' and int(value) != value:
                raise BadPayload('La resolución requiere un número entero de vértices')
            native = value / (bpy.context.scene.unit_settings.scale_length or 1.) if spec['unit'] == 'length' else value
            if not math.isfinite(native) or abs(native) > 3.402823e38:
                raise BadPayload(f'{key} excede el rango de Blender')
        if value != current['values'][key]:
            validated[key] = value

    # Validación completa antes de tocar RNA. Copias de valores para revertir errores.
    scale = bpy.context.scene.unit_settings.scale_length or 1.
    baseline = dict(location=obj.location.copy(), scale=obj.scale.copy(),
                    euler=obj.rotation_euler.copy(), quaternion=obj.rotation_quaternion.copy(),
                    axis_angle=tuple(obj.rotation_axis_angle),
                    hidden=obj.hide_get(), render=obj.hide_render, front=obj.show_in_front)
    image = obj.type == 'EMPTY' and obj.empty_display_type == 'IMAGE'
    if obj.type == 'EMPTY': baseline['size'] = obj.empty_display_size
    image_attrs = {'orthographic': 'show_empty_image_orthographic', 'perspective': 'show_empty_image_perspective',
                   'axis_only': 'show_empty_image_only_axis_aligned', 'depth': 'empty_image_depth', 'side': 'empty_image_side'}
    if image:
        baseline['image'] = {attr: getattr(obj, attr) for attr in image_attrs.values()}
        baseline['alpha'] = obj.use_empty_image_alpha
        baseline['color'] = tuple(obj.color)
    replacement_data = None
    original_data = obj.data if any(k in validated for k in ('circle_vertices', 'curve_resolution')) else None
    data_collection = bpy.data.curves if obj.type == 'CURVE' else bpy.data.meshes
    try:
        if original_data is not None:
            if 'circle_vertices' in validated:
                from .circle_properties import describe as describe_circle, resized_mesh
                replacement_data = resized_mesh(obj, describe_circle(obj), int(validated['circle_vertices']))
            else:
                replacement_data = obj.data.copy()
                replacement_data.resolution_u = int(validated['curve_resolution'])
            obj.data = replacement_data
        dimensions = obj.dimensions.copy()
        rotation = _rotation(obj)
        for key, value in validated.items():
            if key.startswith('location_'): obj.location['xyz'.index(key[-1])] = value / scale
            elif key.startswith('rotation_'): rotation['xyz'.index(key[-1])] = math.radians(value)
            elif key.startswith('dimension_'): dimensions['xyz'.index(key[-1])] = value / scale
            elif key.startswith('scale_'): obj.scale['xyz'.index(key[-1])] = value
            elif key == 'display_size': obj.empty_display_size = value / scale
            elif key == 'visible': obj.hide_set(not value)
            elif key == 'render': obj.hide_render = not value
            elif key == 'in_front': obj.show_in_front = value
            elif key == 'opacity': obj.use_empty_image_alpha = True; obj.color[3] = value
            elif key in image_attrs: setattr(obj, image_attrs[key], value)
        if any(k.startswith('rotation_') for k in validated):
            if obj.rotation_mode == 'QUATERNION': obj.rotation_quaternion = rotation.to_quaternion()
            elif obj.rotation_mode == 'AXIS_ANGLE':
                axis, angle = rotation.to_quaternion().to_axis_angle()
                obj.rotation_axis_angle = (angle, *axis)
            else: obj.rotation_euler = rotation
        if any(k.startswith('dimension_') for k in validated):
            obj.dimensions = dimensions
        bpy.context.view_layer.update()
    except Exception:
        if replacement_data is not None:
            obj.data = original_data
            data_collection.remove(replacement_data)
        obj.location, obj.scale = baseline['location'], baseline['scale']
        obj.rotation_euler, obj.rotation_quaternion = baseline['euler'], baseline['quaternion']
        obj.rotation_axis_angle = baseline['axis_angle']
        obj.hide_set(baseline['hidden'])
        obj.hide_render, obj.show_in_front = baseline['render'], baseline['front']
        if 'size' in baseline: obj.empty_display_size = baseline['size']
        if image:
            for attr, value in baseline['image'].items(): setattr(obj, attr, value)
            obj.use_empty_image_alpha, obj.color = baseline['alpha'], baseline['color']
        bpy.context.view_layer.update()
        raise
    if original_data is not None and original_data.users == 0:
        data_collection.remove(original_data)
    if validated: undo_push('Remote object properties')
    from .. import state
    return state.snapshot()
