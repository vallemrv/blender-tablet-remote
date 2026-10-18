"""Lista de objetos y acciones por identidad; el movimiento usa la sesión nativa."""
import bpy

from . import command
from .object_properties import _identity, _require_idle
from .. import state
from ..bpy_utils import undo_push
from ..errors import BadPayload, CommandError


def describe():
    layer = bpy.context.view_layer
    result = []
    for obj in bpy.context.scene.objects:
        in_layer = obj.name in layer.objects
        hidden = bool(obj.hide_viewport or (in_layer and obj.hide_get()))
        visible = bool(in_layer and obj.visible_get())
        result.append(dict(id=_identity(obj), name=obj.name, type=obj.type,
                           selected=bool(in_layer and obj.select_get()),
                           active=layer.objects.active == obj, hidden=hidden, visible=visible,
                           locked=obj.hide_select, in_view_layer=in_layer,
                           parent=obj.parent.name if obj.parent else None,
                           collections=[c.name for c in obj.users_collection],
                           collection_ids=[_identity(c) for c in obj.users_collection],
                           editable=obj.library is None or obj.override_library is not None))
    return sorted(result, key=lambda row: row['name'].casefold())


def _target(payload):
    _require_object_context()
    identity = payload.get('object_id')
    obj = next((o for o in bpy.context.scene.objects if _identity(o) == identity), None)
    if obj is None:
        raise CommandError('El objeto ya no existe en esta escena; actualiza el Outliner', code='object_changed')
    return obj


def _require_object_context():
    _require_idle()
    from ..cad.runtime import runtime
    if runtime.workspace or bpy.context.mode != 'OBJECT':
        raise CommandError('Estas acciones requieren Object sin una herramienta activa', code='wrong_mode')


def _scene_collections():
    """Cada datablock una vez; conserva padres múltiples sin guardar RNA en caché."""
    found = {}

    def visit(collection, parent=None, path=''):
        key = _identity(collection)
        if key in found:
            if parent is not None: found[key][1]['parents'].append(parent)
            return
        root = collection == bpy.context.scene.collection
        label = 'Escena' if root else collection.name
        full_path = f'{path} / {label}' if path else label
        row = dict(id=key, name=label, path=full_path, root=root,
                   parents=[] if parent is None else [parent], count=len(collection.objects),
                   editable=collection.library is None)
        found[key] = (collection, row)
        for child in sorted(collection.children, key=lambda c: c.name.casefold()):
            visit(child, key, full_path)

    visit(bpy.context.scene.collection)
    return found


def describe_collections():
    return [row for _, row in _scene_collections().values()]


def _select(obj):
    if obj.hide_select:
        raise CommandError('Desbloquea primero este objeto', code='object_locked')
    if obj.name not in bpy.context.view_layer.objects or not obj.visible_get():
        raise CommandError('Muestra primero este objeto y su colección', code='object_hidden')
    for candidate in bpy.context.view_layer.objects:
        candidate.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def _result():
    return dict(state=state.snapshot(), objects=describe(), collections=describe_collections())


@command('outliner.list')
def listing(payload):
    return dict(objects=describe(), collections=describe_collections())


@command('outliner.collection', mutating=True)
def collection_action(payload):
    _require_object_context()
    action = payload.get('action')
    if action not in {'CREATE', 'MOVE_OBJECTS'}:
        raise BadPayload('Acción de colección desconocida')
    collections = _scene_collections()
    key = payload.get('parent_id' if action == 'CREATE' else 'collection_id')
    if action == 'CREATE' and key is None: key = _identity(bpy.context.scene.collection)
    destination = collections.get(key)
    if destination is None:
        raise CommandError('La colección ya no pertenece a esta escena', code='collection_changed')
    if not destination[1]['editable']:
        raise CommandError('La colección enlazada es de solo lectura', code='read_only')
    container = destination[0]
    name = payload.get('name', 'Colección')
    if action == 'CREATE' and (not isinstance(name, str) or not name.strip() or len(name.strip().encode('utf-8')) > 63):
        raise BadPayload('Escribe un nombre de colección entre 1 y 63 bytes')
    ids = payload.get('object_ids', [])
    if not isinstance(ids, list) or any(not isinstance(i, str) for i in ids):
        raise BadPayload('object_ids debe contener identificadores de objetos')
    if action == 'MOVE_OBJECTS' and not ids:
        raise BadPayload('Elige los objetos que quieres mover')
    by_id = {_identity(o): o for o in bpy.context.scene.objects}
    targets = []
    for identity in dict.fromkeys(ids):
        obj = by_id.get(identity)
        if obj is None:
            raise CommandError('Uno de los objetos ya no pertenece a la escena', code='object_changed')
        sources = [c for c in obj.users_collection if _identity(c) in collections]
        if any(c.library is not None for c in sources):
            raise CommandError('Una colección de origen es de solo lectura', code='read_only')
        targets.append((obj, sources))
    created = None
    changes = []
    active = bpy.context.view_layer.objects.active
    selected = [o for o in bpy.context.view_layer.objects if o.select_get()]
    try:
        if action == 'CREATE':
            created = bpy.data.collections.new(name.strip())
            container.children.link(created)
            destination_collection = created
        else:
            destination_collection = container
        for obj, sources in targets:
            if sources == [destination_collection]: continue
            # Registra antes de modificar: también restaura un error de enlace.
            was_linked = obj.name in destination_collection.objects
            changes.append((obj, sources, was_linked))
            if not was_linked: destination_collection.objects.link(obj)
            for source in sources:
                if source != destination_collection: source.objects.unlink(obj)
        bpy.context.view_layer.update()
        for obj in selected:
            if obj.name in bpy.context.view_layer.objects and not obj.hide_select and obj.visible_get(): obj.select_set(True)
        if active is not None and active.name in bpy.context.view_layer.objects and active.visible_get():
            bpy.context.view_layer.objects.active = active
    except Exception:
        for obj, sources, was_linked in reversed(changes):
            for source in sources:
                if obj.name not in source.objects: source.objects.link(obj)
            if not was_linked and obj.name in destination_collection.objects: destination_collection.objects.unlink(obj)
        if created is not None: bpy.data.collections.remove(created)
        bpy.context.view_layer.update()
        for obj in bpy.context.view_layer.objects: obj.select_set(obj in selected)
        if active is not None and active.name in bpy.context.view_layer.objects:
            bpy.context.view_layer.objects.active = active
        raise
    if created is not None or changes: undo_push('Remote create collection' if created else 'Remote move to collection')
    result = _result()
    if created is not None: result['created_collection'] = dict(id=_identity(created), name=created.name)
    return result


@command('outliner.action', mutating=True)
def action(payload):
    obj = _target(payload)
    kind = payload.get('action')
    if kind == 'SELECT':
        _select(obj)
        return _result()
    if obj.library is not None and obj.override_library is None:
        raise CommandError('El objeto enlazado es de solo lectura', code='read_only')
    changed = False
    if kind == 'RENAME':
        name = payload.get('name')
        if not isinstance(name, str) or not name.strip() or len(name.strip().encode('utf-8')) > 63:
            raise BadPayload('El nombre debe contener entre 1 y 63 bytes')
        changed = obj.name != name.strip()
        if changed: obj.name = name.strip()
    elif kind == 'VISIBLE':
        visible = payload.get('value')
        if type(visible) is not bool: raise BadPayload('Visible requiere verdadero o falso')
        if obj.name not in bpy.context.view_layer.objects:
            raise CommandError('La colección está excluida de esta capa de vista', code='collection_hidden')
        changed = obj.hide_get() == visible or (visible and obj.hide_viewport)
        if visible:
            obj.hide_viewport = False
        obj.hide_set(not visible)
        if not visible:
            from .view import forget_local_hidden
            forget_local_hidden([obj.name])
    elif kind == 'LOCK':
        locked = payload.get('value')
        if type(locked) is not bool: raise BadPayload('Bloqueado requiere verdadero o falso')
        changed = obj.hide_select != locked
        obj.hide_select = locked
        if locked and obj.name in bpy.context.view_layer.objects:
            obj.select_set(False)
    else:
        raise BadPayload('Acción de Outliner desconocida')
    layer = bpy.context.view_layer
    if layer.objects.active == obj and (obj.hide_select or not obj.visible_get()):
        layer.objects.active = next((o for o in layer.objects if o.select_get() and not o.hide_select and o.visible_get()), None)
    if changed: undo_push('Remote outliner ' + kind.lower())
    return _result()


@command('outliner.move', mutating=True)
def move(payload):
    obj = _target(payload)
    from . import modal
    layer = bpy.context.view_layer
    previous_active = layer.objects.active
    selected = [o for o in layer.objects if o.select_get()]
    try:
        _select(obj)
        config = payload.get('transform')
        if not isinstance(config, dict): raise BadPayload('Faltan los ajustes de Mover')
        # Una sola petición fija el objeto y abre el Mover habitual; no hay una
        # ventana entre seleccionar y empezar que pueda mover otro objeto.
        transform = modal.begin(dict(config, mode='MOVE', _client_id=payload.get('_client_id')))
    except Exception:
        if modal.session.active:
            modal.session.restore_safely()
            modal.session.reset()
        for o in layer.objects: o.select_set(o in selected)
        layer.objects.active = previous_active
        raise
    return dict(_result(), transform=transform)
