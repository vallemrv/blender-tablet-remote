"""Inspector Object: esquema contextual y cambios atómicos, sin sesión transform."""
import hashlib
import json
import math
import uuid

import bpy

from . import command
from ..bpy_utils import undo_push
from ..errors import BadPayload, CommandError

_EPOCH = uuid.uuid4().hex


def _identity(obj):
    return f'{_EPOCH}:{bpy.context.scene.session_uid}:{obj.session_uid}'


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

    image = obj.type == 'EMPTY' and obj.empty_display_type == 'IMAGE'
    if obj.type in {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META', 'LATTICE'}:
        for i, axis in enumerate('XYZ'):
            field(f'dimension_{axis.lower()}', axis, 'Tamaño', obj.dimensions[i] * scale,
                  unit='length', min=0.)
            # Un eje sin extensión no puede recuperar volumen cambiando dimensions.
            fields[-1]['read_only'] |= obj.lock_scale[i] or abs(obj.dimensions[i]) < 1e-12
    elif obj.type == 'EMPTY':
        limits = obj.bl_rna.properties['empty_display_size']
        field('display_size', 'Tamaño de imagen' if image else 'Tamaño', 'Tamaño',
              obj.empty_display_size * scale, unit='length', min=limits.hard_min * scale,
              max=limits.hard_max * scale)
        for i, axis in enumerate('XYZ'):
            field(f'scale_{axis.lower()}', f'Escala {axis}', 'Tamaño', obj.scale[i], unit='factor')
            fields[-1]['read_only'] |= obj.lock_scale[i]

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
            native = value / (bpy.context.scene.unit_settings.scale_length or 1.) if spec['unit'] == 'length' else value
            if not math.isfinite(native) or abs(native) > 3.402823e38:
                raise BadPayload(f'{key} excede el rango de Blender')
        if value != current['values'][key]:
            validated[key] = value

    # Validación completa antes de tocar RNA. Copias de valores para revertir errores.
    scale = bpy.context.scene.unit_settings.scale_length or 1.
    baseline = dict(location=obj.location.copy(), scale=obj.scale.copy(),
                    hidden=obj.hide_get(), render=obj.hide_render, front=obj.show_in_front)
    image = obj.type == 'EMPTY' and obj.empty_display_type == 'IMAGE'
    if obj.type == 'EMPTY': baseline['size'] = obj.empty_display_size
    image_attrs = {'orthographic': 'show_empty_image_orthographic', 'perspective': 'show_empty_image_perspective',
                   'axis_only': 'show_empty_image_only_axis_aligned', 'depth': 'empty_image_depth', 'side': 'empty_image_side'}
    if image:
        baseline['image'] = {attr: getattr(obj, attr) for attr in image_attrs.values()}
        baseline['alpha'] = obj.use_empty_image_alpha
        baseline['color'] = tuple(obj.color)
    try:
        dimensions = obj.dimensions.copy()
        for key, value in validated.items():
            if key.startswith('location_'): obj.location['xyz'.index(key[-1])] = value / scale
            elif key.startswith('dimension_'): dimensions['xyz'.index(key[-1])] = value / scale
            elif key.startswith('scale_'): obj.scale['xyz'.index(key[-1])] = value
            elif key == 'display_size': obj.empty_display_size = value / scale
            elif key == 'visible': obj.hide_set(not value)
            elif key == 'render': obj.hide_render = not value
            elif key == 'in_front': obj.show_in_front = value
            elif key == 'opacity': obj.use_empty_image_alpha = True; obj.color[3] = value
            elif key in image_attrs: setattr(obj, image_attrs[key], value)
        if any(k.startswith('dimension_') for k in validated):
            obj.dimensions = dimensions
        bpy.context.view_layer.update()
    except Exception:
        obj.location, obj.scale = baseline['location'], baseline['scale']
        obj.hide_set(baseline['hidden'])
        obj.hide_render, obj.show_in_front = baseline['render'], baseline['front']
        if 'size' in baseline: obj.empty_display_size = baseline['size']
        if image:
            for attr, value in baseline['image'].items(): setattr(obj, attr, value)
            obj.use_empty_image_alpha, obj.color = baseline['alpha'], baseline['color']
        bpy.context.view_layer.update()
        raise
    if validated: undo_push('Remote object properties')
    from .. import state
    return state.snapshot()
