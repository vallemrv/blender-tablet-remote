"""selection.* — modo de selección de malla y picking desde coordenadas de pantalla."""

from __future__ import annotations

import bpy
from mathutils import Vector

from .. import state
from ..bpy_utils import active_object, edit_bmesh, find_view3d, flush_bmesh, get_float
from ..camera import camera
from ..errors import BadPayload, CommandError
from . import command

MODE_FLAGS = {
    "VERTEX": (True, False, False),
    "EDGE": (False, True, False),
    "FACE": (False, False, True),
}

SELECTION_OPS = {"SET", "ADD", "REMOVE", "TOGGLE"}
DEFAULT_TOUCH_THRESHOLD = 0.035


def _with_state(result: dict) -> dict:
    """La selección vuelve en el mismo viaje; Android no necesita pedir otro snapshot."""
    return dict(state.snapshot(include_view=False), **result)


def _selection_op(payload: dict) -> str:
    mode = str(payload.get("mode", "SET")).upper()
    if mode not in SELECTION_OPS:
        raise BadPayload("'mode' must be SET, ADD, REMOVE or TOGGLE")
    return mode


def _apply_op(elem, mode: str) -> None:
    elem.select = False if mode == "REMOVE" else (not elem.select if mode == "TOGGLE" else True)


def _touch_threshold(payload: dict) -> float:
    value = get_float(payload, "threshold", DEFAULT_TOUCH_THRESHOLD)
    if not 0.0 < value <= 0.25:
        raise BadPayload("'threshold' must be in (0, 0.25]")
    return value


def _set_select_mode(name: str) -> dict:
    flags = MODE_FLAGS[name]
    bpy.context.scene.tool_settings.mesh_select_mode = flags
    return {"selection_mode": name}


@command("selection.vertex")
def sel_vertex(payload: dict) -> dict:
    return _set_select_mode("VERTEX")


@command("selection.edge")
def sel_edge(payload: dict) -> dict:
    return _set_select_mode("EDGE")


@command("selection.face")
def sel_face(payload: dict) -> dict:
    return _set_select_mode("FACE")


@command("selection.set_mode")
def sel_set_mode(payload: dict) -> dict:
    name = str(payload.get("selection_mode", payload.get("mode", ""))).upper()
    if name not in MODE_FLAGS:
        raise BadPayload("'selection_mode' must be VERTEX, EDGE or FACE")
    return _set_select_mode(name)


@command("selection.all", mutating=True)
def sel_all(payload: dict) -> dict:
    """En Edit Mode selecciona/deselecciona todos los elementos de la malla."""
    obj = active_object()
    value = bool(payload.get("value", True))
    bm = edit_bmesh(obj)
    for seq in (bm.verts, bm.edges, bm.faces):
        for elem in seq:
            elem.select = value
    bm.select_flush(value)
    flush_bmesh(obj, bm, destructive=False)
    return {"selected_verts": sum(1 for v in bm.verts if v.select)}


@command("selection.info")
def sel_info(payload: dict) -> dict:
    obj = active_object()
    if obj.mode != "EDIT":
        raise CommandError("Not in Edit Mode", code="wrong_mode")
    bm = edit_bmesh(obj)
    return {
        "verts": [v.index for v in bm.verts if v.select],
        "edges": [e.index for e in bm.edges if e.select],
        "faces": [f.index for f in bm.faces if f.select],
    }


@command("selection.elements", mutating=True)
def sel_elements(payload: dict) -> dict:
    """Selecciona elementos por índice: {"verts": [...], "edges": [...], "faces": [...], "mode": "SET"}"""
    obj = active_object()
    bm = edit_bmesh(obj)
    mode = _selection_op(payload)
    if mode == "SET":
        for seq in (bm.verts, bm.edges, bm.faces):
            for elem in seq:
                elem.select = False

    value = mode != "REMOVE"
    for key, seq in (("verts", bm.verts), ("edges", bm.edges), ("faces", bm.faces)):
        indices = payload.get(key) or []
        if not isinstance(indices, list):
            raise BadPayload(f"'{key}' must be a list of indices")
        seq.ensure_lookup_table()
        for index in indices:
            try:
                elem = seq[int(index)]
                elem.select = (not elem.select) if mode == "TOGGLE" else value
            except (IndexError, ValueError, TypeError):
                raise CommandError(f"Invalid {key} index: {index}", code="not_found")

    bm.select_flush(value)
    flush_bmesh(obj, bm, destructive=False)
    return sel_info({})


@command("selection.pick", mutating=True)
def pick(payload: dict) -> dict:
    """Tap en la tablet -> raycast en el viewport.

    payload: {"u": 0..1, "v": 0..1, "mode": "SET"|"ADD"|"TOGGLE"}
    u/v son coordenadas normalizadas con origen ARRIBA-IZQUIERDA (convención Android).
    """
    found = find_view3d()
    if found is None:
        raise CommandError("No 3D viewport available", code="no_viewport")
    _window, _area, _region, rv3d = found

    # El rayo sale de la cámara de la TABLET, no de la del PC: es la que se está
    # viendo en el vídeo. Usa las mismas matrices con las que se dibujó el frame,
    # así lo que se toca es exactamente lo que se ve.
    camera.sync_from_region(rv3d)
    u = get_float(payload, "u", 0.5)
    v = get_float(payload, "v", 0.5)
    origin, direction = camera.ray(u, v, rv3d)

    depsgraph = bpy.context.evaluated_depsgraph_get()
    hit, location, _normal, face_index, obj, _matrix = bpy.context.scene.ray_cast(
        depsgraph, origin, direction
    )

    mode = _selection_op(payload)
    active = bpy.context.view_layer.objects.active

    if not hit:
        if mode == "SET":
            if active is not None and active.mode == "EDIT":
                sel_elements({"mode": "SET"})
                return _with_state({"hit": False})
            for o in bpy.context.view_layer.objects:
                o.select_set(False)
        return _with_state({"hit": False})

    if active is not None and active.mode == "EDIT":
        return _with_state(_pick_element(active, location, face_index, mode, payload))

    if mode == "SET":
        for o in bpy.context.view_layer.objects:
            o.select_set(False)
    obj.select_set(False if mode == "REMOVE" else (not obj.select_get() if mode == "TOGGLE" else True))
    bpy.context.view_layer.objects.active = obj
    return _with_state({"hit": True, "object": obj.name, "location": list(location)})


def _pick_element(obj, world_location, face_index: int, mode: str, payload: dict | None = None) -> dict:
    """Selecciona solo geometría visible de la cara impactada y dentro del umbral."""
    payload = payload or {}
    bm = edit_bmesh(obj)
    found = find_view3d()
    rv3d = found[3] if found else None
    camera.sync_from_region(rv3d)
    touch = Vector((get_float(payload, "u", 0.5), get_float(payload, "v", 0.5)))
    threshold = _touch_threshold(payload)
    sel_mode = bpy.context.scene.tool_settings.mesh_select_mode

    bm.faces.ensure_lookup_table()
    visible_face = bm.faces[face_index] if 0 <= face_index < len(bm.faces) else None
    if visible_face is None or visible_face.hide:
        return {"hit": False, "reason": "hidden_or_missing_face"}

    if mode == "SET":
        for seq in (bm.verts, bm.edges, bm.faces):
            for elem in seq:
                elem.select = False

    if sel_mode[0]:
        bm.verts.ensure_lookup_table()
        candidates = [v for v in visible_face.verts if not v.hide]
        scored = [((Vector(camera.project(obj.matrix_world @ v.co, rv3d)) - touch).length, v)
                  for v in candidates if camera.project(obj.matrix_world @ v.co, rv3d) is not None]
        kind = "vert"
    elif sel_mode[1]:
        bm.edges.ensure_lookup_table()
        candidates = [e for e in visible_face.edges if not e.hide]
        scored = []
        for edge in candidates:
            points = [camera.project(obj.matrix_world @ vert.co, rv3d) for vert in edge.verts]
            if None not in points:
                scored.append((_point_segment_distance(touch, Vector(points[0]), Vector(points[1])), edge))
        kind = "edge"
    else:
        scored = [(0.0, visible_face)]
        kind = "face"

    if not scored:
        return {"hit": False, "reason": "no_visible_candidate"}
    distance, target = min(scored, key=lambda item: item[0])
    if kind != "face" and distance > threshold:
        return {"hit": False, "reason": "outside_threshold", "distance": distance}

    _apply_op(target, mode)
    bm.select_flush(target.select)
    flush_bmesh(obj, bm, destructive=False)
    return {"hit": True, "object": obj.name, "element": kind, "index": target.index,
            "distance": distance}


def _point_segment_distance(point: Vector, start: Vector, end: Vector) -> float:
    segment = end - start
    length_squared = segment.length_squared
    if length_squared <= 1e-12:
        return (point - start).length
    t = max(0.0, min(1.0, (point - start).dot(segment) / length_squared))
    return (point - (start + segment * t)).length


def _active_elements(bm):
    flags = tuple(bpy.context.scene.tool_settings.mesh_select_mode)
    return bm.verts if flags == MODE_FLAGS["VERTEX"] else (bm.edges if flags == MODE_FLAGS["EDGE"] else bm.faces)


def _projected_center(obj, elem, rv3d):
    if hasattr(elem, "co"):
        local = elem.co
    elif hasattr(elem, "verts"):
        local = sum((v.co for v in elem.verts), Vector()) / len(elem.verts)
    else:
        return None
    return camera.project(obj.matrix_world @ local, rv3d)


def _shape_select(payload: dict, contains) -> dict:
    obj = active_object()
    bm = edit_bmesh(obj)
    found = find_view3d()
    if found is None:
        raise CommandError("No 3D viewport available", code="no_viewport")
    rv3d = found[3]
    camera.sync_from_region(rv3d)
    mode = _selection_op(payload)
    seq = _active_elements(bm)
    if mode == "SET":
        for collection in (bm.verts, bm.edges, bm.faces):
            for elem in collection:
                elem.select = False
    affected = 0
    for elem in seq:
        if elem.hide:
            continue
        projected = _projected_center(obj, elem, rv3d)
        if projected is not None and contains(projected[0], projected[1]):
            _apply_op(elem, mode)
            affected += 1
    bm.select_flush_mode()
    flush_bmesh(obj, bm, destructive=False)
    return dict(sel_info({}), affected=affected)


@command("selection.box", mutating=True)
def box_select(payload: dict) -> dict:
    u0, v0 = get_float(payload, "u0", 0.0), get_float(payload, "v0", 0.0)
    u1, v1 = get_float(payload, "u1", 1.0), get_float(payload, "v1", 1.0)
    left, right, top, bottom = min(u0, u1), max(u0, u1), min(v0, v1), max(v0, v1)
    return _shape_select(payload, lambda u, v: left <= u <= right and top <= v <= bottom)


@command("selection.circle", mutating=True)
def circle_select(payload: dict) -> dict:
    u, v = get_float(payload, "u", 0.5), get_float(payload, "v", 0.5)
    radius = get_float(payload, "radius", 0.1)
    if not 0.0 < radius <= 1.0:
        raise BadPayload("'radius' must be in (0, 1]")
    radius_squared = radius * radius
    return _shape_select(payload, lambda x, y: (x - u) ** 2 + (y - v) ** 2 <= radius_squared)


def _seed_edge(bm, payload: dict):
    bm.edges.ensure_lookup_table()
    if "edge" in payload:
        try:
            edge = bm.edges[int(payload["edge"])]
        except (ValueError, TypeError, IndexError):
            raise CommandError("Invalid edge index", code="not_found")
        if edge.hide:
            raise CommandError("Edge is hidden", code="not_found")
        return edge
    return next((edge for edge in bm.edges if edge.select and not edge.hide), None)


def _edge_ring(seed):
    result, pending = {seed}, [seed]
    while pending:
        edge = pending.pop()
        for face in edge.link_faces:
            if face.hide or len(face.edges) != 4:
                continue
            opposite = next((candidate for candidate in face.edges
                             if not set(candidate.verts).intersection(edge.verts)), None)
            if opposite is not None and not opposite.hide and opposite not in result:
                result.add(opposite)
                pending.append(opposite)
    return result


def _edge_loop(seed):
    result, pending = {seed}, [(seed, vert) for vert in seed.verts]
    while pending:
        incoming, vertex = pending.pop()
        direction = (incoming.other_vert(vertex).co - vertex.co).normalized()
        candidates = [edge for edge in vertex.link_edges if edge != incoming and not edge.hide and edge not in result]
        if not candidates:
            continue
        continuation = max(candidates, key=lambda edge: direction.dot((vertex.co - edge.other_vert(vertex).co).normalized()))
        if direction.dot((vertex.co - continuation.other_vert(vertex).co).normalized()) < 0.5:
            continue
        result.add(continuation)
        pending.append((continuation, continuation.other_vert(vertex)))
    return result


def _topology_select(payload: dict, resolver) -> dict:
    obj = active_object()
    bm = edit_bmesh(obj)
    seed = _seed_edge(bm, payload)
    if seed is None:
        raise CommandError("Select an edge or provide 'edge'", code="empty_selection")
    mode = _selection_op(payload)
    if mode == "SET":
        for edge in bm.edges:
            edge.select = False
    targets = resolver(seed)
    for edge in targets:
        _apply_op(edge, mode)
    bm.select_flush_mode()
    flush_bmesh(obj, bm, destructive=False)
    return dict(sel_info({}), affected=len(targets))


@command("selection.loop", mutating=True)
def loop_select(payload: dict) -> dict:
    return _topology_select(payload, _edge_loop)


@command("selection.ring", mutating=True)
def ring_select(payload: dict) -> dict:
    return _topology_select(payload, _edge_ring)


@command("selection.invert", mutating=True)
def invert(payload: dict) -> dict:
    obj = active_object()
    bm = edit_bmesh(obj)
    active_seq = bm.verts if MODE_FLAGS["VERTEX"] == tuple(bpy.context.scene.tool_settings.mesh_select_mode) else (
        bm.edges if MODE_FLAGS["EDGE"] == tuple(bpy.context.scene.tool_settings.mesh_select_mode) else bm.faces)
    for elem in active_seq:
        if not elem.hide:
            elem.select = not elem.select
    bm.select_flush_mode()
    flush_bmesh(obj, bm, destructive=False)
    return sel_info({})


@command("selection.hide", mutating=True)
def hide(payload: dict) -> dict:
    obj = active_object()
    bm = edit_bmesh(obj)
    unselected = bool(payload.get("unselected", False))
    for seq in (bm.verts, bm.edges, bm.faces):
        for elem in seq:
            if elem.select != unselected:
                elem.hide_set(True)
    flush_bmesh(obj, bm, destructive=False)
    return sel_info({})


@command("selection.reveal", mutating=True)
def reveal(payload: dict) -> dict:
    obj = active_object()
    bm = edit_bmesh(obj)
    select = bool(payload.get("select", True))
    for seq in (bm.verts, bm.edges, bm.faces):
        for elem in seq:
            if elem.hide:
                elem.hide_set(False)
                elem.select = select
    bm.select_flush_mode()
    flush_bmesh(obj, bm, destructive=False)
    return sel_info({})
