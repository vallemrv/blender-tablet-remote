"""snap.* — cursor 3D y origen de objeto.

El cursor 3D es la referencia con la que Blender coloca cosas, y el menú Shift+S es
de lo más usado del programa. Aquí está su equivalente: mover el cursor a lo que hay
seleccionado, mover lo seleccionado al cursor, y recolocar el origen del objeto.
"""

from __future__ import annotations

import bmesh
import bpy
from mathutils import Vector

from .. import state
from ..bpy_utils import (
    find_view3d,
    get_float,
    get_float3,
    resolve_objects,
    selected_objects,
    undo_push,
    view3d_override,
)
from ..camera import camera
from ..errors import BadPayload, CommandError
from . import command

GEOMETRIC_TYPES = {"VERTEX", "EDGE", "EDGE_CENTER", "FACE", "FACE_CENTER"}


def query_reference_candidate(payload: dict) -> dict:
    """Referencia táctil automática: destinos exactos por prioridad."""
    thresholds = (("VERTEX", 0.080), ("EDGE_CENTER", 0.070), ("FACE_CENTER", 0.065))
    for snap_type, threshold in thresholds:
        candidate = query_candidate(dict(payload, snap_type=snap_type, threshold=threshold))
        if candidate.get("hit"):
            return candidate
    return {"hit": False, "snap_type": "NONE"}


def query_candidate(payload: dict) -> dict:
    """Devuelve el candidato visible más cercano bajo coordenadas normalizadas."""
    snap_type = str(payload.get("snap_type", payload.get("type", "VERTEX"))).upper()
    if snap_type == "CURSOR":
        return {"hit": True, "snap_type": "CURSOR", "id": "CURSOR",
                "position": list(_cursor().location),
                "screen": [float(payload.get("u", 0.5)), float(payload.get("v", 0.5))],
                "distance": 0.0}
    if snap_type not in GEOMETRIC_TYPES:
        raise BadPayload("Unsupported geometric 'snap_type'")
    found = find_view3d()
    if found is None:
        raise CommandError("No 3D viewport available", code="no_viewport")
    rv3d = found[3]
    camera.sync_from_region(rv3d)
    u, v = get_float(payload, "u", 0.5), get_float(payload, "v", 0.5)
    # Radios táctiles por categoría. Vértice es deliberadamente más pegajoso: con
    # stylus el jitter alrededor de una esquina era suficiente para soltarlo.
    default_threshold = {
        "VERTEX": 0.080,
        "EDGE_CENTER": 0.070,
        "FACE_CENTER": 0.065,
        "EDGE": 0.042,
    }.get(snap_type, 0.060)
    threshold = get_float(payload, "threshold", default_threshold)
    if not 0.0 < threshold <= 0.25:
        raise BadPayload("'threshold' must be in (0, 0.25]")
    origin, direction = camera.ray(u, v, rv3d)
    include = {str(name) for name in payload.get("include_objects", [])}
    exclude = {str(name) for name in payload.get("exclude_objects", [])}
    depsgraph = bpy.context.evaluated_depsgraph_get()
    # El objeto móvil puede quedar delante del destino. Avanzar el rayo después de
    # cada objeto excluido permite seguir viendo el cubo de detrás sin ocultar RNA.
    hit = False
    location = None
    face_index = -1
    obj = None
    ray_origin = origin
    for _attempt in range(16):
        hit, location, _normal, face_index, obj, _matrix = bpy.context.scene.ray_cast(
            depsgraph, ray_origin, direction)
        if not hit or obj is None:
            break
        original = getattr(obj, "original", obj)
        if (not include or original.name in include) and original.name not in exclude:
            break
        ray_origin = location + direction * 1e-5
        hit = False
    if not hit or obj is None or obj.type != "MESH":
        return {"hit": False, "snap_type": snap_type}
    # ``scene.ray_cast`` golpea la geometría evaluada. Con Subdivision Surface el
    # índice de cara puede no existir en ``obj.data`` (la malla original), pero para
    # FACE el propio hit ya es la respuesta exacta que necesitamos. Además se devuelve
    # el original seleccionable: Android compara este nombre con selected_objects.
    original = getattr(obj, "original", obj)
    object_name = original.name
    if snap_type == "FACE":
        return {"hit": True, "snap_type": snap_type, "id": f"{object_name}:FACE:{face_index}",
                "object": object_name, "element": face_index, "position": list(location),
                "screen": [u, v], "distance": 0.0}
    mesh = obj.data
    if not 0 <= face_index < len(mesh.polygons):
        return {"hit": False, "snap_type": snap_type}
    polygon = mesh.polygons[face_index]
    touch = Vector((u, v))

    if snap_type == "FACE_CENTER":
        position = obj.matrix_world @ polygon.center
        projected = camera.project(position, rv3d)
        if projected is None:
            return {"hit": False, "snap_type": snap_type}
        distance = (Vector(projected) - touch).length
        if distance > threshold:
            return {"hit": False, "snap_type": snap_type, "distance": distance}
        return {"hit": True, "snap_type": snap_type,
                "id": f"{obj.name}:FACE_CENTER:{face_index}", "object": obj.name,
                "element": face_index, "position": list(position),
                "screen": list(projected), "distance": distance}

    candidates = []
    if snap_type == "VERTEX":
        for index in polygon.vertices:
            position = obj.matrix_world @ mesh.vertices[index].co
            projected = camera.project(position, rv3d)
            if projected is not None:
                candidates.append(((Vector(projected) - touch).length, index, position))
    elif snap_type == "EDGE":
        for edge_key in polygon.edge_keys:
            a = obj.matrix_world @ mesh.vertices[edge_key[0]].co
            b = obj.matrix_world @ mesh.vertices[edge_key[1]].co
            pa, pb = camera.project(a, rv3d), camera.project(b, rv3d)
            if pa is None or pb is None:
                continue
            segment = Vector(pb) - Vector(pa)
            t = 0.0 if segment.length_squared <= 1e-12 else max(
                0.0, min(1.0, (touch - Vector(pa)).dot(segment) / segment.length_squared))
            candidates.append(((touch - (Vector(pa) + segment * t)).length,
                               f"{edge_key[0]}-{edge_key[1]}", a.lerp(b, t)))
    else:  # EDGE_CENTER
        for edge_key in polygon.edge_keys:
            a = obj.matrix_world @ mesh.vertices[edge_key[0]].co
            b = obj.matrix_world @ mesh.vertices[edge_key[1]].co
            position = a.lerp(b, 0.5)
            projected = camera.project(position, rv3d)
            if projected is not None:
                candidates.append(((Vector(projected) - touch).length,
                                   f"{edge_key[0]}-{edge_key[1]}", position))
    if not candidates:
        return {"hit": False, "snap_type": snap_type}
    distance, element, position = min(candidates, key=lambda item: item[0])
    if distance > threshold:
        return {"hit": False, "snap_type": snap_type, "distance": distance}
    return {"hit": True, "snap_type": snap_type, "id": f"{obj.name}:{snap_type}:{element}",
            "object": obj.name, "element": element, "position": list(position),
            "screen": list(camera.project(position, rv3d) or (u, v)), "distance": distance}


@command("snap.query")
def query(payload: dict) -> dict:
    return query_candidate(payload)


def _cursor():
    return bpy.context.scene.cursor


def _grid_step(payload: dict) -> float:
    step = payload.get("step", 1.0)
    try:
        step = float(step)
    except (TypeError, ValueError):
        raise BadPayload("'step' must be a number")
    if step <= 0:
        raise BadPayload("'step' must be greater than zero")
    return step


def _snapped(vector: Vector, step: float) -> Vector:
    return Vector(round(value / step) * step for value in vector)


def _edit_mesh_median(obj):
    """Mediana de los vértices seleccionados, en coordenadas de mundo. None si no hay."""
    bm = bmesh.from_edit_mesh(obj.data)
    selected = [v.co for v in bm.verts if v.select]
    if not selected:
        return None
    local = Vector()
    for co in selected:
        local += co
    return obj.matrix_world @ (local / len(selected))


def _selection_median() -> Vector:
    """
    En Edit Mode manda la selección de vértices; en Object Mode, los orígenes.

    Es lo que hace Blender y lo que el usuario espera: con la malla abierta, "lo
    seleccionado" son los vértices, no el objeto entero.
    """
    active = bpy.context.view_layer.objects.active
    if active is not None and active.mode == "EDIT" and active.type == "MESH":
        median = _edit_mesh_median(active)
        if median is None:
            raise CommandError("No vertices selected", code="empty_selection")
        return median

    objs = selected_objects()
    if not objs:
        raise CommandError("Nothing selected", code="empty_selection")
    total = Vector()
    for obj in objs:
        total += obj.matrix_world.translation
    return total / len(objs)


def _cursor_result() -> dict:
    return {"cursor": list(_cursor().location)}


# ------------------------------------------------------------------- cursor


@command("snap.info")
def info(payload: dict) -> dict:
    cursor = _cursor()
    return {"cursor": list(cursor.location), "rotation": list(cursor.rotation_euler)}


@command("snap.cursor_set", mutating=True)
def cursor_set(payload: dict) -> dict:
    """Coloca el cursor en coordenadas absolutas."""
    _cursor().location = get_float3(payload, default=0.0)
    undo_push("Remote set cursor")
    return _cursor_result()


@command("snap.cursor_to_world", mutating=True)
def cursor_to_world(payload: dict) -> dict:
    _cursor().location = (0.0, 0.0, 0.0)
    undo_push("Remote cursor to world origin")
    return _cursor_result()


@command("snap.cursor_to_selected", mutating=True)
def cursor_to_selected(payload: dict) -> dict:
    _cursor().location = _selection_median()
    undo_push("Remote cursor to selected")
    return _cursor_result()


@command("snap.cursor_to_active", mutating=True)
def cursor_to_active(payload: dict) -> dict:
    obj = bpy.context.view_layer.objects.active
    if obj is None:
        raise CommandError("No active object")
    _cursor().location = obj.matrix_world.translation
    undo_push("Remote cursor to active")
    return _cursor_result()


@command("snap.cursor_to_grid", mutating=True)
def cursor_to_grid(payload: dict) -> dict:
    step = _grid_step(payload)
    _cursor().location = _snapped(Vector(_cursor().location), step)
    undo_push("Remote cursor to grid")
    return _cursor_result()


# ---------------------------------------------------------------- selección


@command("snap.selected_to_cursor", mutating=True)
def selected_to_cursor(payload: dict) -> dict:
    """
    `keep_offset=True` conserva la forma del grupo y lo mueve entero, como el
    "Selection to Cursor (Keep Offset)" de Blender.
    """
    _require_object_mode()
    objs = resolve_objects(payload)
    target = Vector(_cursor().location)

    if payload.get("keep_offset"):
        center = Vector()
        for obj in objs:
            center += obj.matrix_world.translation
        center /= len(objs)
        delta = target - center
        for obj in objs:
            obj.matrix_world.translation = obj.matrix_world.translation + delta
    else:
        for obj in objs:
            obj.matrix_world.translation = target

    undo_push("Remote selection to cursor")
    return state.snapshot(include_view=False)


@command("snap.selected_to_grid", mutating=True)
def selected_to_grid(payload: dict) -> dict:
    _require_object_mode()
    step = _grid_step(payload)
    for obj in resolve_objects(payload):
        obj.matrix_world.translation = _snapped(obj.matrix_world.translation, step)
    undo_push("Remote selection to grid")
    return state.snapshot(include_view=False)


# ------------------------------------------------------------------- origen


def _require_object_mode() -> None:
    active = bpy.context.view_layer.objects.active
    if active is not None and active.mode != "OBJECT":
        raise CommandError("Only available in Object Mode", code="wrong_mode")


def _origin_set(kind: str, center: str = "MEDIAN") -> dict:
    """
    Aquí sí se usa el operador: recolocar el origen implica transformar los datos de
    malla y compensar la matriz del objeto, con casos raros (datos compartidos entre
    objetos, hijos) que `origin_set` ya resuelve bien.
    """
    _require_object_mode()
    if not selected_objects():
        raise CommandError("Nothing selected", code="empty_selection")
    try:
        with view3d_override():
            bpy.ops.object.origin_set(type=kind, center=center)
    except RuntimeError as exc:
        raise CommandError(f"Cannot set origin: {exc}")
    undo_push(f"Remote {kind.lower()}")
    return state.snapshot(include_view=False)


@command("snap.origin_to_cursor", mutating=True)
def origin_to_cursor(payload: dict) -> dict:
    return _origin_set("ORIGIN_CURSOR")


@command("snap.origin_to_geometry", mutating=True)
def origin_to_geometry(payload: dict) -> dict:
    """`center`: MEDIAN (por defecto) o BOUNDS."""
    center = str(payload.get("center", "MEDIAN")).upper()
    if center not in {"MEDIAN", "BOUNDS"}:
        raise BadPayload("'center' must be MEDIAN or BOUNDS")
    return _origin_set("ORIGIN_GEOMETRY", center)


@command("snap.origin_to_center_of_mass", mutating=True)
def origin_to_center_of_mass(payload: dict) -> dict:
    return _origin_set("ORIGIN_CENTER_OF_MASS")
