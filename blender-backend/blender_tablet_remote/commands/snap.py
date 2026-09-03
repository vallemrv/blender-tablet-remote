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
    # ``scene.ray_cast`` golpea la geometría evaluada. Con Subdivision Surface el
    # índice de cara puede no existir en ``obj.data`` (la malla original), pero para
    # FACE el propio hit ya es la respuesta exacta que necesitamos. Además se devuelve
    # el original seleccionable: Android compara este nombre con selected_objects.
    if snap_type == "FACE":
        if not hit or obj is None or obj.type != "MESH":
            return {"hit": False, "snap_type": snap_type}
        original = getattr(obj, "original", obj)
        return {"hit": True, "snap_type": snap_type, "id": f"{original.name}:FACE:{face_index}",
                "object": original.name, "element": face_index, "position": list(location),
                "screen": [u, v], "distance": 0.0}

    target = _snap_target_object(hit, obj, include, exclude)
    if target is None:
        return {"hit": False, "snap_type": snap_type}
    object_name = target.name
    excluded = payload.get("exclude_elements", {})
    excluded_vertices = {
        int(index) for index in excluded.get(object_name, {}).get("vertices", [])
    } if isinstance(excluded, dict) else set()

    touch = Vector((u, v))
    candidates = _screen_candidates(
        target, snap_type, rv3d, touch, direction, excluded_vertices)
    if not candidates:
        return {"hit": False, "snap_type": snap_type}
    distance, element, position = min(candidates, key=lambda item: item[0])
    if distance > threshold:
        return {"hit": False, "snap_type": snap_type, "distance": distance}
    return {"hit": True, "snap_type": snap_type, "id": f"{object_name}:{snap_type}:{element}",
            "object": object_name, "element": element, "position": list(position),
            "screen": list(camera.project(position, rv3d) or (u, v)), "distance": distance}


def _snap_target_object(hit: bool, obj, include: set[str], exclude: set[str]):
    """Objeto sobre el que buscar candidatos.

    El rayo manda cuando golpea algo. Si no golpea se cae al objeto en edición: el
    dedo cae a menudo junto a la silueta, o sobre el hueco que deja la geometría que
    se está moviendo, y ahí sigue habiendo destinos válidos a la vista.
    """
    if hit and obj is not None and obj.type == "MESH":
        return getattr(obj, "original", obj)
    active = bpy.context.view_layer.objects.active
    if (active is not None and active.type == "MESH" and active.mode == "EDIT"
            and (not include or active.name in include) and active.name not in exclude):
        return active
    return None


def _screen_candidates(obj, snap_type: str, rv3d, touch: Vector, view_direction: Vector,
                       excluded_vertices: set[int]) -> list[tuple[float, object, Vector]]:
    """Candidatos del objeto puntuados por distancia EN PANTALLA al toque.

    Blender busca el snap en un radio de pantalla; limitarse a la cara que cruza el
    rayo hacía inalcanzables casi todos los destinos: el centro de arista que se ve
    pegado al dedo rara vez pertenece a esa cara, y al mover un loop las caras que lo
    rodean están todas excluidas. Se descarta lo que da la espalda a la cámara para
    no engancharse a la parte de atrás de la malla.
    """
    matrix = obj.matrix_world
    normals = matrix.to_3x3().inverted_safe().transposed()
    in_edit = obj.mode == "EDIT"

    def collect(frontfacing) -> list[tuple[float, object, Vector]]:
        sources = (_edit_sources(obj, snap_type, excluded_vertices, frontfacing) if in_edit
                   else _mesh_sources(obj, snap_type, excluded_vertices, frontfacing))
        scored: list[tuple[float, object, Vector]] = []
        for element, points in sources:
            if len(points) == 1:
                position = matrix @ points[0]
                projected = camera.project(position, rv3d)
                if projected is not None:
                    scored.append(((Vector(projected) - touch).length, element, position))
                continue
            # EDGE engancha al punto del segmento más próximo al dedo, no a un extremo.
            a, b = matrix @ points[0], matrix @ points[1]
            pa, pb = camera.project(a, rv3d), camera.project(b, rv3d)
            if pa is None or pb is None:
                continue
            segment = Vector(pb) - Vector(pa)
            t = 0.0 if segment.length_squared <= 1e-12 else max(
                0.0, min(1.0, (touch - Vector(pa)).dot(segment) / segment.length_squared))
            scored.append(((touch - (Vector(pa) + segment * t)).length, element, a.lerp(b, t)))
        return scored

    scored = collect(lambda normal: (normals @ normal).dot(view_direction) < 0.0)
    # Una malla abierta mirada por su reverso (el plano visto desde abajo) no tiene
    # ni una cara de cara a la cámara, y se ve entera. Si el filtro no deja nada,
    # es que no había nada que ocultar: se repite sin él.
    return scored or collect(lambda _normal: True)


def _edit_sources(obj, snap_type: str, excluded: set[int], frontfacing):
    """Elementos del BMesh vivo: en Edit Mode `obj.data` va por detrás del gesto."""
    bm = bmesh.from_edit_mesh(obj.data)
    if snap_type == "FACE_CENTER":
        for face in bm.faces:
            if face.hide or any(vert.index in excluded for vert in face.verts):
                continue
            if frontfacing(face.normal):
                yield face.index, (face.calc_center_median(),)
        return
    if snap_type == "VERTEX":
        for vert in bm.verts:
            if vert.hide or vert.index in excluded:
                continue
            if not vert.link_faces or any(frontfacing(f.normal) for f in vert.link_faces):
                yield vert.index, (vert.co.copy(),)
        return
    for edge in bm.edges:
        if edge.hide or any(vert.index in excluded for vert in edge.verts):
            continue
        if edge.link_faces and not any(frontfacing(f.normal) for f in edge.link_faces):
            continue
        a, b = edge.verts[0].co, edge.verts[1].co
        element = "-".join(str(index) for index in sorted(v.index for v in edge.verts))
        yield element, ((a.lerp(b, 0.5),) if snap_type == "EDGE_CENTER" else (a.copy(), b.copy()))


def _mesh_sources(obj, snap_type: str, excluded: set[int], frontfacing):
    mesh = obj.data
    if snap_type == "FACE_CENTER":
        for polygon in mesh.polygons:
            if polygon.hide or any(index in excluded for index in polygon.vertices):
                continue
            if frontfacing(polygon.normal):
                yield polygon.index, (polygon.center.copy(),)
        return
    # Un vértice/arista es visible si toca alguna cara orientada a la cámara. Sin
    # caras (mallas de solo aristas) no hay nada que ocluya y entran todos.
    vertices, edges = _frontfacing_keys(mesh, frontfacing)
    if snap_type == "VERTEX":
        for vert in mesh.vertices:
            if vert.hide or vert.index in excluded:
                continue
            if vertices is None or vert.index in vertices:
                yield vert.index, (vert.co.copy(),)
        return
    for edge in mesh.edges:
        key = tuple(sorted(edge.vertices))
        if edge.hide or any(index in excluded for index in key):
            continue
        if edges is not None and key not in edges:
            continue
        a, b = mesh.vertices[key[0]].co, mesh.vertices[key[1]].co
        element = f"{key[0]}-{key[1]}"
        yield element, ((a.lerp(b, 0.5),) if snap_type == "EDGE_CENTER" else (a.copy(), b.copy()))


def _frontfacing_keys(mesh, frontfacing):
    """(vértices, aristas) que tocan alguna cara orientada a la cámara. None si no hay caras."""
    if not mesh.polygons:
        return None, None
    vertices: set[int] = set()
    edges: set[tuple[int, int]] = set()
    for polygon in mesh.polygons:
        if polygon.hide or not frontfacing(polygon.normal):
            continue
        vertices.update(polygon.vertices)
        edges.update(polygon.edge_keys)
    return vertices, edges


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
