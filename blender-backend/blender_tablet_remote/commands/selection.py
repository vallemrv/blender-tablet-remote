"""selection.* — modo de selección de malla y picking desde coordenadas de pantalla."""

from __future__ import annotations

import bpy
import bmesh
import heapq
import itertools
from mathutils import Vector
from mathutils.bvhtree import BVHTree

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
# Face Loop/Ring necesita una dirección además de la cara. La toma de la arista más
# próxima al último toque sobre esa cara, equivalente a la posición del cursor en el
# Alt+click de Blender. Se invalida por objeto para no reutilizar intención vieja.
_last_face_edge: tuple[str, int] | None = None


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


def _apply_group_op(elements, mode: str) -> None:
    """TOGGLE sobre un grupo alterna el grupo entero, no elemento a elemento.

    Es el Shift+Alt+click de Blender: un loop ya seleccionado se apaga entero y uno
    nuevo se enciende entero. Alternando uno a uno, un loop seleccionado a medias
    quedaría en damero.
    """
    elements = list(elements)
    if mode == "TOGGLE":
        mode = "REMOVE" if elements and all(elem.select for elem in elements) else "ADD"
    for elem in elements:
        _apply_op(elem, mode)


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
        bm.select_history.clear()
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

    mode = _selection_op(payload)
    active = bpy.context.view_layer.objects.active
    depsgraph = bpy.context.evaluated_depsgraph_get()

    # En Edit Mode los índices de ``scene.ray_cast`` pertenecen a la geometría
    # evaluada. Con Subdivision no corresponden al BMesh editable. Raycast sobre la
    # jaula original para que cara/vértice/arista tocados sean los que se seleccionan.
    if (active is not None and active.mode == "EDIT" and active.type == "MESH"
            and any(modifier.show_viewport for modifier in active.modifiers)):
        edit_hit = _edit_cage_raycast(active, origin, direction)
        if edit_hit is None:
            hit, location, face_index, obj = False, None, -1, active
        else:
            location, face_index = edit_hit
            hit, obj = True, active
    else:
        hit, location, _normal, face_index, obj, _matrix = bpy.context.scene.ray_cast(
            depsgraph, origin, direction
        )

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

    # En wireframe+xray, picar sobre lo ya seleccionado con ADD/TOGGLE pasa al
    # objeto que está detrás (el Alt+click de Blender): se ve el armazón entero
    # y poder elegir solo el frente sería frustrante.
    from .view import is_xray_wireframe

    if is_xray_wireframe() and mode in ("SET", "ADD", "TOGGLE") and obj.select_get():
        origin, location, obj = _cycle_behind(depsgraph, origin, direction, location, obj)

    if mode == "SET":
        for o in bpy.context.view_layer.objects:
            o.select_set(False)
    obj.select_set(False if mode == "REMOVE" else (not obj.select_get() if mode == "TOGGLE" else True))
    bpy.context.view_layer.objects.active = obj
    return _with_state({"hit": True, "object": obj.name, "location": list(location)})


def _edit_cage_raycast(obj, world_origin: Vector, world_direction: Vector):
    bm = edit_bmesh(obj)
    inverse = obj.matrix_world.inverted_safe()
    local_origin = inverse @ world_origin
    local_direction = (inverse.to_3x3() @ world_direction).normalized()
    location, _normal, face_index, _distance = BVHTree.FromBMesh(bm).ray_cast(
        local_origin, local_direction)
    if location is None or face_index is None:
        return None
    return obj.matrix_world @ location, int(face_index)


_tweak_owner = None
_tweak_missed = False
# El BEGIN configura el gesto entero; los UPDATE llegan sin repetir los ajustes.
_tweak_snap_type = "NONE"
_tweak_session_id = None


def _reset_tweak():
    global _tweak_owner, _tweak_missed, _tweak_snap_type, _tweak_session_id
    _tweak_owner = None
    _tweak_missed = False
    _tweak_snap_type = "NONE"
    _tweak_session_id = None

TWEAK_SNAP_TYPES = {"NONE", "INCREMENT", "VERTEX", "EDGE", "EDGE_CENTER", "FACE", "FACE_CENTER"}
GEOMETRIC_SNAP_TYPES = {"VERTEX", "EDGE", "EDGE_CENTER", "FACE", "FACE_CENTER"}
# Fracción del riel con SLIDE, unidades de escena con FREE.
DEFAULT_TWEAK_SLIDE_STEP = 0.1


def _tweak_settings(payload: dict) -> tuple[str, str, float | None, bool]:
    """Lee y concilia motion/snap del BEGIN."""
    motion = str(payload.get("motion", "FREE")).upper()
    if motion not in {"FREE", "SLIDE"}:
        raise BadPayload("'motion' must be FREE or SLIDE")
    snap_type = str(payload.get("snap_type", "NONE")).upper()
    if snap_type not in TWEAK_SNAP_TYPES:
        raise BadPayload("Unknown 'snap_type'")
    # Deslizar por una arista ya decide el destino: un candidato geométrico lo sacaría
    # del riel. Se degrada en vez de fallar para que la UI conserve ambos ajustes
    # independientes y el gesto siga funcionando.
    if motion == "SLIDE" and snap_type in GEOMETRIC_SNAP_TYPES:
        snap_type = "NONE"
    if "snap_step" in payload:
        step = get_float(payload, "snap_step", DEFAULT_TWEAK_SLIDE_STEP)
        if step <= 0.0:
            raise BadPayload("'snap_step' must be positive")
    else:
        step = DEFAULT_TWEAK_SLIDE_STEP if motion == "SLIDE" else None
    return motion, snap_type, step, bool(payload.get("clamp", True))


@command("selection.tweak", mutating=True)
def tweak(payload: dict) -> dict:
    """Selecciona bajo el apoyo y mueve directamente hasta soltar el gesto."""
    from . import modal, tools
    global _tweak_owner, _tweak_missed, _tweak_snap_type, _tweak_session_id

    phase = str(payload.get("phase", "")).upper()
    if phase not in {"BEGIN", "UPDATE", "END", "CANCEL"}:
        raise BadPayload("'phase' must be BEGIN, UPDATE, END or CANCEL")
    owner = payload.get("_client_id")

    if phase == "BEGIN":
        obj = active_object()
        if obj.mode != "EDIT":
            raise CommandError("Tweak requires Edit Mode", code="wrong_mode")
        selection_mode = tuple(bpy.context.scene.tool_settings.mesh_select_mode)
        # Una cara se traslada libremente; SLIDE solo tiene rieles de vértices/aristas.
        settings = dict(payload, motion="FREE") if selection_mode[2] else payload
        motion, snap_type, step, clamp = _tweak_settings(settings)
        if tools.tool_session.active:
            tools.tool_session.require(owner)
        if modal.session.active:
            modal.session.require(owner)
            modal.session.restore_safely()
            modal.session.reset()
        from .sessions import cancel_tool
        cancel_tool(restore=True)
        _reset_tweak()
        bm = edit_bmesh(obj)
        selected = {kind: {e.index for e in seq if e.select}
                    for kind, seq in (("vert", bm.verts), ("edge", bm.edges), ("face", bm.faces))}
        # Un único picking. Tocar algo seleccionado arrastra el grupo; tocar otro
        # elemento lo selecciona en exclusiva. Un miss conserva la selección.
        picked = pick(dict(payload, mode="ADD"))
        if picked.get("hit"):
            kind, index = picked["element"], picked["index"]
            if index not in selected[kind]:
                bm.select_history.clear()
                for seq in (bm.verts, bm.edges, bm.faces):
                    for elem in seq:
                        elem.select = False
                seq = {"vert": bm.verts, "edge": bm.edges, "face": bm.faces}[kind]
                seq.ensure_lookup_table()
                seq[index].select = True
                bm.select_history.add(seq[index])
                bm.select_flush_mode()
                flush_bmesh(obj, bm, destructive=False)
            picked = _with_state({key: picked[key] for key in
                                  ("hit", "object", "element", "index", "distance") if key in picked})
        _tweak_owner = owner
        _tweak_missed = not picked.get("hit")
        _tweak_snap_type = snap_type
        if not picked.get("hit"):
            return picked
        try:
            modal.session.begin("MOVE", [], snap_type != "NONE", step, owner_id=owner,
                                orientation="GLOBAL", value_mode="RELATIVE", snap_type=snap_type,
                                motion=motion, slide_clamp=clamp)
        except Exception:
            modal.session.restore_safely()
            modal.session.reset()
            _reset_tweak()
            raise
        _tweak_session_id = modal.session.session_id
        return dict(picked, tweak=True, session_id=modal.session.session_id,
                    motion=motion, snap_type=snap_type)

    # Un END/CANCEL retrasado tras cambiar de herramienta nunca toca la sesión nueva.
    if ((_tweak_missed and (modal.session.active or tools.tool_session.active)) or
            (not _tweak_missed and (not modal.session.active or
                                   modal.session.session_id != _tweak_session_id))):
        _reset_tweak()
        return {"tweak": True, "moved": False}
    if owner != _tweak_owner:
        raise CommandError("Tweak gesture belongs to another client", code="session_owned")

    if _tweak_missed:
        if phase == "UPDATE":
            # Tweak es también la herramienta de navegación de un dedo: si BEGIN no
            # encontró geometría, el mismo flujo de deltas orbita sin esperar una
            # respuesta asíncrona que obligaría a cambiar de gesto a mitad del drag.
            from .view import orbit_delta
            dx = get_float(payload, "dx", 0.0)
            dy = get_float(payload, "dy", 0.0)
            orbit_delta(dx, dy)
            return {"hit": False, "tweak": True, "orbit": True, "moved": bool(dx or dy)}
        if phase in {"END", "CANCEL"}:
            _reset_tweak()
        return {"hit": False, "tweak": True, "orbit": True, "moved": False}

    modal.session.require(owner)
    if modal.session.mode != "MOVE" or modal.session.edit_object is None:
        raise CommandError("Tweak session is not an Edit MOVE", code="wrong_tool")
    if phase == "UPDATE":
        modal.session.nudge(get_float(payload, "dx", 0.0), get_float(payload, "dy", 0.0))
        modal.session.apply()
        if _tweak_snap_type in GEOMETRIC_SNAP_TYPES and "u" in payload and "v" in payload:
            # El elemento arrastrado es la fuente de la sesión, así que resolver
            # fuente→candidato lo deja exactamente encima del destino. Sin impacto se
            # conserva el nudge ya aplicado y el gesto sigue al dedo.
            status = modal.set_snap_candidate(
                dict(payload, snap_type=_tweak_snap_type, lock=False))
            return dict(status, tweak=True)
        return dict(modal.session.status(), tweak=True)
    # Con SLIDE el delta acumulado no es el desplazamiento: hasta que el arrastre fija
    # un riel el vértice no se ha movido, y confirmar ahí crearía un undo vacío.
    if modal.session.slide_candidates is not None:
        moved = modal.session.slide_rails is not None
    else:
        moved = modal.session.values.length > 1e-12
    finished_session_id = _tweak_session_id
    if phase == "CANCEL" or not moved:
        result = modal.cancel(payload)
    else:
        result = modal.confirm(payload)
    _reset_tweak()
    return dict(result, tweak=True, tweak_finished=finished_session_id,
                moved=moved and phase == "END")


@command("selection.shortest_path", mutating=True)
def shortest_path(payload: dict) -> dict:
    """Ctrl+toque de Blender: camino topológico entre el activo y lo tocado.

    El destino se resuelve con el mismo raycast, oclusión y umbral que
    ``selection.pick``. El cálculo se hace sobre BMesh porque la cámara de la tablet
    no coincide con las coordenadas de ventana que exige ``bpy.ops.mesh.shortest_path_pick``.
    """
    obj = active_object()
    if obj.mode != "EDIT":
        raise CommandError("Shortest path requires Edit Mode", code="wrong_mode")
    bm = edit_bmesh(obj)
    seq = _active_elements(bm)
    source = bm.select_history.active
    if source not in seq or not source.select or source.hide:
        selected = [elem for elem in seq if elem.select and not elem.hide]
        source = selected[0] if len(selected) == 1 else None

    # ADD conserva el origen mientras reutilizamos exactamente el picking táctil.
    picked = pick(dict(payload, mode="ADD"))
    if not picked.get("hit"):
        return picked
    target = bm.select_history.active
    if target not in seq:
        raise CommandError("Touched element does not match selection mode", code="wrong_selection")
    if source is None:
        # Igual que Blender, el primer toque solo establece el origen del próximo
        # camino. Ya quedó seleccionado y activo por ``pick``.
        return _with_state({"hit": True, "object": obj.name, "element": picked.get("element"),
                            "index": target.index, "path": [target.index], "path_length": 1})

    path = _shortest_element_path(source, target)
    if not path:
        raise CommandError("No connected path to touched element", code="no_selection_path")
    if not bool(payload.get("extend", False)):
        for collection in (bm.verts, bm.edges, bm.faces):
            for elem in collection:
                elem.select = False
        bm.select_history.clear()
    for elem in path:
        elem.select = True
    bm.select_history.add(target)
    bm.select_flush_mode()
    flush_bmesh(obj, bm, destructive=False)
    return _with_state({"hit": True, "object": obj.name, "element": picked.get("element"),
                        "index": target.index, "path": [elem.index for elem in path],
                        "path_length": len(path)})


def _shortest_element_path(source, target):
    """Dijkstra geométrico para vértices, aristas o caras de un mismo BMesh."""
    if source is target:
        return [source]
    distances = {source: 0.0}
    previous = {}
    serial = itertools.count()
    queue = [(0.0, next(serial), source)]
    while queue:
        distance, _order, current = heapq.heappop(queue)
        if distance != distances.get(current):
            continue
        if current is target:
            break
        for neighbor, weight in _path_neighbors(current):
            if neighbor.hide:
                continue
            candidate = distance + max(weight, 1e-12)
            if candidate < distances.get(neighbor, float("inf")):
                distances[neighbor] = candidate
                previous[neighbor] = current
                heapq.heappush(queue, (candidate, next(serial), neighbor))
    if target not in distances:
        return []
    result = [target]
    while result[-1] is not source:
        result.append(previous[result[-1]])
    result.reverse()
    return result


def _path_neighbors(elem):
    if isinstance(elem, bmesh.types.BMVert):
        return [(edge.other_vert(elem), edge.calc_length()) for edge in elem.link_edges]
    if isinstance(elem, bmesh.types.BMEdge):
        center = (elem.verts[0].co + elem.verts[1].co) * 0.5
        neighbors = {other for vert in elem.verts for other in vert.link_edges if other is not elem}
        return [(other, ((other.verts[0].co + other.verts[1].co) * 0.5 - center).length)
                for other in neighbors]
    center = elem.calc_center_median()
    neighbors = {other for edge in elem.edges for other in edge.link_faces if other is not elem}
    return [(other, (other.calc_center_median() - center).length) for other in neighbors]


def _cycle_behind(depsgraph, origin, direction, location, obj):
    """Siguiente impacto del rayo más allá del objeto ya seleccionado.

    `ray_cast` no acepta una distancia mínima, así que se avanza el origen justo
    pasado el impacto anterior y se repite. Tope de 16: en una pila de objetos
    superpuestos más profunda que eso, tocar el fondo a ciegas no es selección.
    """
    from mathutils import Vector

    for _ in range(16):
        travelled = (location - origin).length
        epsilon = max(1e-5, travelled * 1e-4)
        origin = origin + direction * (travelled + epsilon)
        hit, location, _normal, _face_index, candidate, _matrix = bpy.context.scene.ray_cast(
            depsgraph, origin, direction
        )
        if not hit or candidate is None:
            break
        if not candidate.select_get():
            return origin, Vector(location), candidate
    return origin, Vector(location), obj


def _pick_element(obj, world_location, face_index: int, mode: str, payload: dict | None = None) -> dict:
    """Selecciona geometría visible de la cara impactada y dentro del umbral.

    Con wireframe+xray los vértices/aristas de detrás son tan picables como los
    del frente: los candidatos salen de la malla entera, no solo de la cara del
    raycast (que siempre es la frontal). Sin xray se mantiene la oclusión real.
    """
    payload = payload or {}
    bm = edit_bmesh(obj)
    found = find_view3d()
    rv3d = found[3] if found else None
    camera.sync_from_region(rv3d)
    touch = Vector((get_float(payload, "u", 0.5), get_float(payload, "v", 0.5)))
    threshold = _touch_threshold(payload)
    sel_mode = bpy.context.scene.tool_settings.mesh_select_mode

    from .view import is_xray_wireframe

    if is_xray_wireframe() and (sel_mode[0] or sel_mode[1]):
        through = _pick_through(obj, bm, rv3d, touch, threshold, mode, sel_mode)
        if through is not None:
            return through
        return {"hit": False, "reason": "outside_threshold"}

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
        edge_scores = []
        for edge in visible_face.edges:
            points = [camera.project(obj.matrix_world @ vert.co, rv3d) for vert in edge.verts]
            if None not in points:
                edge_scores.append((_point_segment_distance(
                    touch, Vector(points[0]), Vector(points[1])), edge))
        if edge_scores:
            global _last_face_edge
            _last_face_edge = (obj.name, min(edge_scores, key=lambda item: item[0])[1].index)

    if not scored:
        return {"hit": False, "reason": "no_visible_candidate"}
    distance, target = min(scored, key=lambda item: item[0])
    if kind != "face" and distance > threshold:
        return {"hit": False, "reason": "outside_threshold", "distance": distance}

    _apply_op(target, mode)
    if target.select:
        bm.select_history.add(target)
    else:
        bm.select_history.discard(target)
    # `select_flush(True)` propaga hacia arriba DESDE los vértices: enciende toda
    # arista cuyos dos vértices ya estuvieran marcados. Como Blender marca los
    # vértices de las aristas seleccionadas al escribir la malla, picar una segunda
    # arista arrastraba a sus vecinas. `select_flush_mode` respeta el modo activo
    # (deriva los vértices desde lo picado, no al revés), igual que loop/ring/box.
    bm.select_flush_mode()
    flush_bmesh(obj, bm, destructive=False)
    return {"hit": True, "object": obj.name, "element": kind, "index": target.index,
            "distance": distance}


def _pick_through(obj, bm, rv3d, touch: Vector, threshold: float, mode: str, sel_mode) -> dict | None:
    """Pick en wireframe+xray: el candidato más próximo al punto tocado.

    Se ve (y se quiere tocar) el armazón entero, no solo la cara frontal del rayo:
    vértices y aristas se puntúan por distancia en pantalla al toque. Los
    modificadores cambian la operación, nunca el elemento elegido.
    """
    matrix = obj.matrix_world
    scored: list[tuple[float, object]] = []
    if sel_mode[0]:
        kind = "vert"
        for vert in bm.verts:
            if vert.hide:
                continue
            projected = camera.project(matrix @ vert.co, rv3d)
            if projected is None:
                continue
            distance = (Vector(projected) - touch).length
            if distance <= threshold:
                scored.append((distance, vert))
    else:
        kind = "edge"
        for edge in bm.edges:
            if edge.hide:
                continue
            points = [camera.project(matrix @ vert.co, rv3d) for vert in edge.verts]
            if None in points:
                continue
            distance = _point_segment_distance(touch, Vector(points[0]), Vector(points[1]))
            if distance <= threshold:
                scored.append((distance, edge))

    if not scored:
        return None

    # Un segundo toque sobre el elemento ya seleccionado avanza al candidato que
    # queda detrás. Hay que decidirlo antes de limpiar SET o se pierde esa memoria.
    nearest = min(scored, key=lambda item: item[0])
    selectable = [item for item in scored if not item[1].select]
    chosen = min(selectable, key=lambda item: item[0]) if nearest[1].select and selectable else nearest

    if mode == "SET":
        bm.select_history.clear()
        for collection in (bm.verts, bm.edges, bm.faces):
            for elem in collection:
                elem.select = False

    distance, target = chosen

    _apply_op(target, mode)
    if target.select:
        bm.select_history.add(target)
    else:
        bm.select_history.discard(target)
    bm.select_flush_mode()
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
    # En Object Mode no hace falta objeto activo (puede no haberlo tras un
    # delete); en Edit sí, y edit_bmesh lo exige.
    active = bpy.context.view_layer.objects.active
    if active is not None and active.mode == "EDIT":
        return _edit_shape_select(active, payload, contains)
    return _object_shape_select(payload, contains)


def _edit_shape_select(obj, payload: dict, contains) -> dict:
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


def _object_shape_select(payload: dict, contains) -> dict:
    """Caja/círculo en Object Mode: cae el objeto cuyo centro proyectado queda dentro.

    El centro es `matrix_world.translation`: barato y suficiente para "englobar
    eso de ahí"; reproyectar el bound_box entero no cambia qué se selecciona en
    la práctica y sí multiplica el coste por objeto.
    """
    found = find_view3d()
    if found is None:
        raise CommandError("No 3D viewport available", code="no_viewport")
    rv3d = found[3]
    camera.sync_from_region(rv3d)
    mode = _selection_op(payload)
    view_layer = bpy.context.view_layer
    if mode == "SET":
        for o in view_layer.objects:
            o.select_set(False)
    affected = 0
    for o in view_layer.objects:
        if o.hide_get():
            continue
        projected = camera.project(o.matrix_world.translation, rv3d)
        if projected is not None and contains(projected[0], projected[1]):
            o.select_set(False if mode == "REMOVE" else (not o.select_get() if mode == "TOGGLE" else True))
            affected += 1
    return dict(
        state.snapshot(include_view=False),
        affected=affected,
        selected_objects=[o.name for o in view_layer.objects if o.select_get()],
    )


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
    active = bm.select_history.active
    if isinstance(active, bmesh.types.BMEdge) and active.select and not active.hide:
        return active
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
        visible = [edge for edge in vertex.link_edges if not edge.hide]
        candidates = [edge for edge in visible if edge != incoming and edge not in result]

        # Un edge loop es una relación topológica, no una línea geométricamente
        # recta. En un vértice regular de una superficie de quads continúa por la
        # única arista que no comparte cara con la entrante. Esto permite que el
        # loop doble por las esquinas (por ejemplo, el anillo creado al hacer un
        # Loop Cut en un cubo). En polos o topología no-quad la continuación es
        # ambigua y debe detenerse.
        if len(visible) == 2 and len(candidates) == 1:
            continuation = candidates[0]
        elif len(visible) == 4 and all(len(face.edges) == 4 for face in vertex.link_faces):
            incoming_faces = set(incoming.link_faces)
            opposite = [edge for edge in candidates if incoming_faces.isdisjoint(edge.link_faces)]
            if len(opposite) != 1:
                continue
            continuation = opposite[0]
        else:
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
    _apply_group_op(targets, mode)
    bm.select_flush_mode()
    flush_bmesh(obj, bm, destructive=False)
    return dict(sel_info({}), affected=len(targets))


def _face_strip(seed_face, seed_edge):
    """Fila de quads que atraviesa la cara por `seed_edge` y su opuesta."""
    if len(seed_face.edges) != 4 or seed_edge not in seed_face.edges:
        return {seed_face}
    result = {seed_face}
    opposite = next(edge for edge in seed_face.edges
                    if not set(edge.verts).intersection(seed_edge.verts))
    pending = [(seed_face, seed_edge), (seed_face, opposite)]
    while pending:
        face, exit_edge = pending.pop()
        neighbor = next((candidate for candidate in exit_edge.link_faces
                         if candidate is not face and not candidate.hide), None)
        if neighbor is None or neighbor in result or len(neighbor.edges) != 4:
            continue
        result.add(neighbor)
        next_edge = next((edge for edge in neighbor.edges
                          if not set(edge.verts).intersection(exit_edge.verts)), None)
        if next_edge is not None and not next_edge.hide:
            pending.append((neighbor, next_edge))
    return result


def _face_topology_select(payload: dict, perpendicular: bool) -> dict:
    obj = active_object()
    bm = edit_bmesh(obj)
    active = bm.select_history.active
    seed_face = active if isinstance(active, bmesh.types.BMFace) and active.select else next(
        (face for face in bm.faces if face.select and not face.hide), None)
    if seed_face is None:
        raise CommandError("Select a face first", code="empty_selection")
    edge_index = (_last_face_edge[1] if _last_face_edge and _last_face_edge[0] == obj.name else None)
    seed_edge = next((edge for edge in seed_face.edges if edge.index == edge_index), seed_face.edges[0])
    if perpendicular:
        position = list(seed_face.edges).index(seed_edge)
        seed_edge = seed_face.edges[(position + 1) % len(seed_face.edges)]
    targets = _face_strip(seed_face, seed_edge)
    mode = _selection_op(payload)
    if mode == "SET":
        for collection in (bm.verts, bm.edges, bm.faces):
            for elem in collection:
                elem.select = False
    _apply_group_op(targets, mode)
    bm.select_flush_mode()
    flush_bmesh(obj, bm, destructive=False)
    return dict(sel_info({}), affected=len(targets))


@command("selection.loop", mutating=True)
def loop_select(payload: dict) -> dict:
    if bpy.context.scene.tool_settings.mesh_select_mode[2]:
        return _face_topology_select(payload, perpendicular=False)
    return _topology_select(payload, _edge_loop)


@command("selection.ring", mutating=True)
def ring_select(payload: dict) -> dict:
    if bpy.context.scene.tool_settings.mesh_select_mode[2]:
        return _face_topology_select(payload, perpendicular=True)
    return _topology_select(payload, _edge_ring)


@command("selection.linked", mutating=True)
def linked(payload: dict) -> dict:
    """Selecciona las islas conectadas a lo ya seleccionado (la `L` / `Ctrl+L`).

    La `L` de Blender siembra con lo que hay bajo el ratón; aquí siembra la propia
    selección, que en la tablet es lo mismo: se toca la pieza (queda seleccionada) y
    el anillo la extiende a todo lo que cuelga de ella. Sin selección no hay isla que
    elegir, así que se responde `empty_selection` en vez de adivinar.

    El recorrido es por aristas y se para en lo oculto: una parte escondida no debe
    reaparecer en la selección por estar pegada a lo que se tocó.
    """
    obj = active_object()
    bm = edit_bmesh(obj)
    stack = [v for v in bm.verts if v.select and not v.hide]
    if not stack:
        raise CommandError("Select something first", code="empty_selection")

    island = set(stack)
    while stack:
        vert = stack.pop()
        for edge in vert.link_edges:
            if edge.hide:
                continue
            other = edge.other_vert(vert)
            if other.hide or other in island:
                continue
            island.add(other)
            stack.append(other)

    for vert in island:
        vert.select = True
    # Marcar solo los vértices deja el submodo activo sin nada seleccionado (en Caras
    # no hay cara marcada), y `select_flush_mode` lo desharía. Se sube a mano.
    for edge in bm.edges:
        if not edge.hide and all(v in island for v in edge.verts):
            edge.select = True
    for face in bm.faces:
        if not face.hide and all(v in island for v in face.verts):
            face.select = True
    bm.select_flush_mode()
    flush_bmesh(obj, bm, destructive=False)
    return dict(sel_info({}), affected=len(island))


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


@command("selection.more", mutating=True)
def more(payload: dict) -> dict:
    """Ctrl+Numpad+ : extiende la selección a lo adyacente según el submodo."""
    return _grow_shrink(grow=True)


@command("selection.less", mutating=True)
def less(payload: dict) -> dict:
    """Ctrl+Numpad- : retira lo que toca algo no seleccionado."""
    return _grow_shrink(grow=False)


def _grow_shrink(grow: bool) -> dict:
    obj = active_object()
    if obj is None or obj.mode != "EDIT":
        raise CommandError("Not in Edit Mode", code="wrong_mode")
    bm = edit_bmesh(obj)
    flags = tuple(bpy.context.scene.tool_settings.mesh_select_mode)

    # Las adyacencias se miran SIEMPRE entre elementos del mismo nivel, y contra
    # una instantánea de la selección de partida: marcar durante el propio bucle
    # encadena vecinos recién seleccionados y un solo `more` se come la malla.
    if flags == MODE_FLAGS["VERTEX"]:
        selected = {v.index for v in bm.verts if v.select and not v.hide}
        if grow:
            for vert in bm.verts:
                if vert.hide or vert.select:
                    continue
                if any(edge.other_vert(vert).index in selected
                       for edge in vert.link_edges if not edge.hide):
                    vert.select = True
        else:
            for vert in bm.verts:
                if vert.hide or not vert.select:
                    continue
                if any(not edge.hide and edge.other_vert(vert).index not in selected
                       for edge in vert.link_edges):
                    vert.select = False
    elif flags == MODE_FLAGS["EDGE"]:
        selected = {e.index for e in bm.edges if e.select and not e.hide}
        if grow:
            for edge in bm.edges:
                if edge.hide or edge.select:
                    continue
                if any(neighbor.index in selected
                       for vert in edge.verts for neighbor in vert.link_edges):
                    edge.select = True
        else:
            for edge in bm.edges:
                if edge.hide or not edge.select:
                    continue
                if any(neighbor.index not in selected
                       for vert in edge.verts for neighbor in vert.link_edges if not neighbor.hide):
                    edge.select = False
    else:
        selected = {f.index for f in bm.faces if f.select and not f.hide}
        if grow:
            for face in bm.faces:
                if face.hide or face.select:
                    continue
                if any(neighbor.index in selected
                       for edge in face.edges for neighbor in edge.link_faces):
                    face.select = True
        else:
            for face in bm.faces:
                if face.hide or not face.select:
                    continue
                if any(neighbor.index not in selected
                       for edge in face.edges for neighbor in edge.link_faces):
                    face.select = False

    bm.select_flush_mode()
    flush_bmesh(obj, bm, destructive=False)
    return sel_info({})
