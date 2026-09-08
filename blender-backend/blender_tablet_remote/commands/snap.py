"""snap.* — cursor 3D y origen de objeto.

El cursor 3D es la referencia con la que Blender coloca cosas, y el menú Shift+S es
de lo más usado del programa. Aquí está su equivalente: mover el cursor a lo que hay
seleccionado, mover lo seleccionado al cursor, y recolocar el origen del objeto.
"""

from __future__ import annotations

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

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

# Distancias en fracciones del ancho de imagen, con corrección de aspecto.
# La corona de salida solo retiene el MISMO id; nunca adquiere otro punto.
STICKY_RELEASE_FACTOR = 1.55
STICKY_RELEASE_PADDING = 0.012
STICKY_SWITCH_MARGIN = 0.014
REFERENCE_THRESHOLDS = {"VERTEX": 0.055, "FACE_CENTER": 0.050, "EDGE_CENTER": 0.045}


def choose_sticky_candidate(candidates: list[dict], previous: dict | None,
                            acquire_threshold: float,
                            release_threshold: float | None = None) -> dict | None:
    """Una competición común, también entre categorías con radios distintos."""
    previous_id = previous.get("id") if isinstance(previous, dict) else None
    incumbent = next((c for c in candidates if c.get("id") == previous_id), None)
    eligible = [c for c in candidates
                if c["distance"] <= c.get("acquire_threshold", acquire_threshold)]
    best = min(eligible, key=lambda c: c["distance"], default=None)
    if incumbent is not None:
        acquire = incumbent.get("acquire_threshold", acquire_threshold)
        release = (release_threshold if release_threshold is not None else
                   acquire * STICKY_RELEASE_FACTOR + STICKY_RELEASE_PADDING)
        if incumbent["distance"] <= release:
            if (best is not None and best.get("id") != previous_id
                    and best["distance"] + STICKY_SWITCH_MARGIN < incumbent["distance"]):
                return best
            return incumbent
    return best


def query_reference_candidate(payload: dict, previous: dict | None = None) -> dict:
    return _query_geometric(payload, REFERENCE_THRESHOLDS, previous)


def query_edit_surface_candidate(obj, u, v, enabled=True, mode="AUTO", previous=None):
    """Ancla sobre la superficie editable viva, incluidas las caras de cortes previos."""
    found = find_view3d()
    if found is None:
        raise CommandError("No 3D viewport available", code="no_viewport")
    region, rv3d = found[2], found[3]
    viewport = found[1].spaces.active if found[1] is not None else None
    camera.sync_from_region(rv3d)
    aspect = max(1, region.width) / max(1, region.height)
    bm = bmesh.from_edit_mesh(obj.data)
    for seq in (bm.verts, bm.edges, bm.faces):
        seq.index_update()
        seq.ensure_lookup_table()
    # Scene.ray_cast usa la malla evaluada, que puede ir por detrás del BMesh.
    faces = [face for face in bm.faces if not face.hide]
    tree = BVHTree.FromPolygons([v.co for v in bm.verts],
                               [[v.index for v in face.verts] for face in faces])
    inverse = obj.matrix_world.inverted()
    depsgraph = bpy.context.evaluated_depsgraph_get()

    def surface(screen):
        origin, direction = camera.ray(*screen, rv3d)
        point, _, index, _ = tree.ray_cast(inverse @ origin,
                                         (inverse.to_3x3() @ direction).normalized())
        return point, index

    def visible(position, screen):
        if not _visible(position, screen, depsgraph, rv3d, {obj.name}, viewport):
            return False
        point, _ = surface(screen)
        if point is None:
            return True  # silueta o arista sin cara
        origin, direction = camera.ray(*screen, rv3d)
        target_distance = (position - origin).dot(direction)
        hit_distance = (obj.matrix_world @ point - origin).dot(direction)
        return target_distance <= hit_distance + max(1e-6, abs(target_distance) * 1e-5)

    thresholds = ({"VERTEX": .035, "EDGE_CENTER": .028, "EDGE": .042} if mode == "AUTO"
                  else {mode: {"VERTEX": .080, "EDGE_CENTER": .070, "EDGE": .042}[mode]})
    ranked = []
    if enabled:
        for kind, acquire in thresholds.items():
            for distance, element, position in _screen_candidates(obj, kind, rv3d, Vector((u, v)), aspect, set()):
                identity = f"{obj.name}:{kind}:{element}"
                limit = (acquire * STICKY_RELEASE_FACTOR + STICKY_RELEASE_PADDING
                         if previous and previous.get("id") == identity else acquire)
                if distance > limit:
                    continue
                screen = camera.project(position, rv3d)
                if screen is None or not visible(position, screen):
                    continue
                ranked.append(dict(hit=True, snap_type=kind, id=identity, object=obj.name,
                                   element=element, position=list(position), screen=list(screen),
                                   local_position=list(inverse @ position), distance=distance,
                                   acquire_threshold=acquire))
        # AUTO deja adquirir puntos discretos cerca de una arista; una arista a
        # distancia cero no puede tapar sus extremos ni su centro.
        points = [c for c in ranked if c["snap_type"] != "EDGE"]
        chosen = choose_sticky_candidate(points, previous, max(thresholds.values()))
        if chosen is None:
            chosen = choose_sticky_candidate(ranked, previous, max(thresholds.values()))
        if chosen is not None:
            return {k: value for k, value in chosen.items() if k != "acquire_threshold"}
    local, index = surface((u, v))
    if local is None or not visible(obj.matrix_world @ local, (u, v)):
        return dict(hit=False, snap_type="NONE", screen=[u, v])
    return dict(hit=True, snap_type="FACE", id=f"{obj.name}:FACE:{faces[index].index}",
                object=obj.name, element=faces[index].index, position=list(obj.matrix_world @ local),
                local_position=list(local), screen=[u, v], distance=0.0)


def query_face_frame(payload: dict) -> dict | None:
    """Cara visible evaluada, con ancla local y contorno para herramientas de colocación."""
    hit = query_candidate(dict(payload, snap_type="FACE"))
    if not hit.get("hit"):
        return None
    obj = bpy.data.objects.get(hit["object"])
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.data
    index = hit["element"]
    if not 0 <= index < len(mesh.polygons):
        return None
    face = mesh.polygons[index]
    return dict(hit, center=list(face.center), normal=list(face.normal),
                vertices=[list(mesh.vertices[i].co) for i in face.vertices])


def query_candidate(payload: dict, previous: dict | None = None,
                    release_threshold: float | None = None) -> dict:
    """Devuelve el candidato visible más cercano bajo coordenadas normalizadas."""
    snap_type = str(payload.get("snap_type", payload.get("type", "VERTEX"))).upper()
    if snap_type == "CURSOR":
        found = find_view3d()
        if found is None:
            raise CommandError("No 3D viewport available", code="no_viewport")
        camera.sync_from_region(found[3])
        return {"hit": True, "snap_type": "CURSOR", "id": "CURSOR",
                "position": list(_cursor().location),
                "screen": camera.project(_cursor().location, found[3]) or [], "distance": 0.0}
    if snap_type not in GEOMETRIC_TYPES:
        raise BadPayload("Unsupported geometric 'snap_type'")
    default = {"VERTEX": 0.080, "EDGE_CENTER": 0.070, "FACE_CENTER": 0.065,
               "EDGE": 0.042}.get(snap_type, 0.060)
    threshold = get_float(payload, "threshold", default)
    if not 0.0 < threshold <= 0.25:
        raise BadPayload("'threshold' must be in (0, 0.25]")
    return _query_geometric(payload, {snap_type: threshold}, previous, release_threshold)


def _ray_hit(depsgraph, origin, direction, exclude, distance=1e30, viewport=None):
    """Respeta oclusores; solo atraviesa objetos excluidos explícitamente (Propio)."""
    remaining = distance
    for _ in range(64):
        hit, location, _normal, face, obj, _matrix = bpy.context.scene.ray_cast(
            depsgraph, origin, direction, distance=remaining)
        if not hit:
            return None
        original = getattr(obj, "original", obj)
        if original.name not in exclude and original.visible_get(viewport=viewport):
            return location, face, original
        advance = (location - origin).length + 1e-5
        remaining -= advance
        if remaining <= 0:
            return None
        origin = location + direction * 1e-5
    # Demasiadas superficies: no asumir que el destino está libre.
    raise CommandError("Too many occluding surfaces", code="snap_occlusion_limit")


def _visible(position, screen, depsgraph, rv3d, exclude, viewport=None):
    origin, direction = camera.ray(screen[0], screen[1], rv3d)
    distance = (position - origin).dot(direction)
    if distance <= 0:
        return False
    tolerance = max(1e-6, distance * 1e-5)
    return _ray_hit(depsgraph, origin, direction, exclude,
                    max(0.0, distance - tolerance), viewport) is None


def _query_geometric(payload, thresholds, previous=None, release_threshold=None):
    found = find_view3d()
    if found is None:
        raise CommandError("No 3D viewport available", code="no_viewport")
    region, rv3d = found[2], found[3]
    viewport = found[1].spaces.active if found[1] is not None else None
    camera.sync_from_region(rv3d)
    aspect = max(1, region.width) / max(1, region.height)
    u, v = get_float(payload, "u", 0.5), get_float(payload, "v", 0.5)
    touch = Vector((u, v))
    include = {str(name) for name in payload.get("include_objects", [])}
    exclude = {str(name) for name in payload.get("exclude_objects", [])}
    depsgraph = bpy.context.evaluated_depsgraph_get()
    missing = {"hit": False, "snap_type": next(iter(thresholds)) if len(thresholds) == 1 else "NONE"}
    if "FACE" in thresholds:
        origin, direction = camera.ray(u, v, rv3d)
        result = _ray_hit(depsgraph, origin, direction, exclude, viewport=viewport)
        if result is None:
            return missing
        position, face, obj = result
        if obj.type != "MESH" or (include and obj.name not in include):
            return missing
        return {"hit": True, "snap_type": "FACE", "id": f"{obj.name}:FACE:{face}",
                "object": obj.name, "element": face, "position": list(position),
                "screen": [u, v], "distance": 0.0}

    previous_id = previous.get("id") if isinstance(previous, dict) else None
    radius = max(thresholds.values()) * STICKY_RELEASE_FACTOR + STICKY_RELEASE_PADDING
    if release_threshold is not None:
        radius = max(radius, release_threshold)
    excluded = payload.get("exclude_elements", {})
    ranked = []
    # El radio de pantalla incluye siluetas y mallas sin caras, aunque el rayo
    # central no toque ningún objeto. Las cajas evitan recorrer mallas lejanas.
    for obj in bpy.context.view_layer.objects:
        if (obj.type != "MESH" or obj.name in exclude or not obj.visible_get(viewport=viewport)
                or (include and obj.name not in include)):
            continue
        if obj.mode != "EDIT":
            bounds = [camera.project(obj.matrix_world @ Vector(corner), rv3d)
                      for corner in obj.bound_box]
            if all(b is not None for b in bounds):
                if (u < min(b[0] for b in bounds) - radius or u > max(b[0] for b in bounds) + radius
                        or v < min(b[1] for b in bounds) - radius * aspect
                        or v > max(b[1] for b in bounds) + radius * aspect):
                    continue
        vertices = {int(i) for i in excluded.get(obj.name, {}).get("vertices", [])} if isinstance(excluded, dict) else set()
        for kind, acquire in thresholds.items():
            for distance, element, position in _screen_candidates(obj, kind, rv3d, touch, aspect, vertices):
                candidate_id = f"{obj.name}:{kind}:{element}"
                release = (release_threshold if release_threshold is not None else
                           acquire * STICKY_RELEASE_FACTOR + STICKY_RELEASE_PADDING)
                limit = release if candidate_id == previous_id else acquire
                if distance > limit:
                    continue
                screen = camera.project(position, rv3d)
                if screen is None or not (0 <= screen[0] <= 1 and 0 <= screen[1] <= 1):
                    continue
                ranked.append({"hit": True, "snap_type": kind, "id": candidate_id,
                               "object": obj.name, "element": element, "position": list(position),
                               "screen": screen, "distance": distance, "acquire_threshold": acquire})
    # Visibilidad antes de competir: basta comprobar el incumbente y el candidato
    # nuevo visible más cercano. No se lanza un rayo por cada vértice de la escena.
    visible = []
    incumbent = next((c for c in ranked if c["id"] == previous_id), None)
    if incumbent and _visible(Vector(incumbent["position"]), incumbent["screen"], depsgraph, rv3d, exclude, viewport):
        visible.append(incumbent)
    for c in sorted(ranked, key=lambda c: c["distance"]):
        if c["id"] == previous_id:
            continue
        if _visible(Vector(c["position"]), c["screen"], depsgraph, rv3d, exclude, viewport):
            visible.append(c)
            break
    chosen = choose_sticky_candidate(visible, previous, max(thresholds.values()), release_threshold)
    if chosen is None:
        return missing
    return {k: value for k, value in chosen.items() if k != "acquire_threshold"}


def _screen_candidates(obj, snap_type, rv3d, touch, aspect, excluded_vertices):
    """Distancia circular en pantalla y puntos de arista correctos en perspectiva."""
    matrix = obj.matrix_world
    sources = (_edit_sources(obj, snap_type, excluded_vertices) if obj.mode == "EDIT"
               else _mesh_sources(obj, snap_type, excluded_vertices))
    def metric(point):
        return Vector((point[0], point[1] / aspect))
    scaled_touch = metric(touch)
    for element, points in sources:
        if len(points) == 1:
            position = matrix @ points[0]
            projected = camera.project(position, rv3d)
            if projected is not None:
                yield (metric(projected) - scaled_touch).length, element, position
            continue
        a, b = matrix @ points[0], matrix @ points[1]
        pa, pb = camera.project(a, rv3d), camera.project(b, rv3d)
        if pa is None or pb is None:
            continue
        start, segment = metric(pa), metric(pb) - metric(pa)
        t = 0.0 if segment.length_squared <= 1e-12 else max(
            0.0, min(1.0, (scaled_touch - start).dot(segment) / segment.length_squared))
        projection = camera.perspective_matrix(rv3d)
        wa = (projection @ a.to_4d()).w
        wb = (projection @ b.to_4d()).w
        world_t = t * wa / max((1.0 - t) * wb + t * wa, 1e-12)
        yield (scaled_touch - (start + segment * t)).length, element, a.lerp(b, world_t)


def _edit_sources(obj, snap_type: str, excluded: set[int]):
    """Elementos del BMesh vivo: en Edit Mode `obj.data` va por detrás del gesto."""
    bm = bmesh.from_edit_mesh(obj.data)
    if snap_type == "FACE_CENTER":
        for face in bm.faces:
            if face.hide or any(vert.index in excluded for vert in face.verts):
                continue
            yield face.index, (face.calc_center_median(),)
        return
    if snap_type == "VERTEX":
        for vert in bm.verts:
            if vert.hide or vert.index in excluded:
                continue
            yield vert.index, (vert.co.copy(),)
        return
    for edge in bm.edges:
        if edge.hide or any(vert.index in excluded for vert in edge.verts):
            continue
        a, b = edge.verts[0].co, edge.verts[1].co
        element = "-".join(str(index) for index in sorted(v.index for v in edge.verts))
        yield element, ((a.lerp(b, 0.5),) if snap_type == "EDGE_CENTER" else (a.copy(), b.copy()))


def _mesh_sources(obj, snap_type: str, excluded: set[int]):
    mesh = obj.data
    if snap_type == "FACE_CENTER":
        for polygon in mesh.polygons:
            if polygon.hide or any(index in excluded for index in polygon.vertices):
                continue
            yield polygon.index, (polygon.center.copy(),)
        return
    if snap_type == "VERTEX":
        for vert in mesh.vertices:
            if vert.hide or vert.index in excluded:
                continue
            yield vert.index, (vert.co.copy(),)
        return
    for edge in mesh.edges:
        key = tuple(sorted(edge.vertices))
        if edge.hide or any(index in excluded for index in key):
            continue
        a, b = mesh.vertices[key[0]].co, mesh.vertices[key[1]].co
        element = f"{key[0]}-{key[1]}"
        yield element, ((a.lerp(b, 0.5),) if snap_type == "EDGE_CENTER" else (a.copy(), b.copy()))


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
