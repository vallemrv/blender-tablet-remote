"""gizmo.* — manipulador sobre la selección: mover, rotar y escalar con un gesto.

Se dibuja dentro de GPUOffScreen con la cámara de la tablet. `gizmo.drag` sigue el
patrón de Tweak: BEGIN sondea las asas aquí, donde la proyección es exacta, y si
toca una abre la sesión modal de siempre con ese modo y eje; UPDATE la alimenta
siguiendo al dedo y END la confirma con un único undo (sin cambios, no hay undo).
Sin asa bajo el dedo, el mismo gesto orbita la cámara.

Las coordenadas de pantalla se miden en fracciones de la altura del vídeo
(x = u·aspecto, y = v, origen arriba-izquierda): así las asas tienen el mismo
tamaño en cualquier resolución y orientación.
"""

from __future__ import annotations

import math

import bpy
import bmesh
from mathutils import Vector

from ..bpy_utils import find_view3d, get_float
from ..camera import camera
from ..errors import BadPayload, CommandError
from ..palette import AXIS_COLORS
from . import command

AXES = (("X", Vector((1.0, 0.0, 0.0))), ("Y", Vector((0.0, 1.0, 0.0))), ("Z", Vector((0.0, 0.0, 1.0))))
COLORS = {**AXIS_COLORS, None: (0.95, 0.95, 0.95, 1.0)}
# Longitudes en fracciones de la altura del vídeo.
ARROW = 0.10
ARROW_START = 0.30 * ARROW
SCALE_BOX = 1.32 * ARROW
BOX_HALF = 0.012
RING = 1.8 * ARROW
UNIFORM = 2.25 * ARROW
CENTER = 0.022
# Tolerancias táctiles por tipo de asa: un dedo cubre unos 7 mm.
TOUCH = 0.035
RING_TOUCH = 0.022
RING_SEGMENTS = 64
# Un eje que apunta casi hacia la cámara se ve como un punto: sin asas propias.
MIN_AXIS_FRACTION = 0.2
# Un anillo visto de canto es una línea por el centro: tapa al resto y girar sobre
# él no está definido, así que se oculta hasta que la vista lo abra.
MIN_RING_OPENING = 0.3
SNAP_TYPES = {"NONE", "INCREMENT"}

_enabled = False
_revision = 0
_center_cache: tuple | None = None
_drag: dict | None = None


@bpy.app.handlers.persistent
def _bump_revision(*_args) -> None:
    global _revision
    _revision += 1


def _ensure_handler() -> None:
    for handlers in (bpy.app.handlers.depsgraph_update_post, bpy.app.handlers.undo_post,
                     bpy.app.handlers.redo_post, bpy.app.handlers.load_post):
        if _bump_revision not in handlers:
            handlers.append(_bump_revision)


def _selection_center() -> Vector | None:
    """Mismo pivote que abre la sesión modal: media de vértices u orígenes."""
    global _center_cache
    obj = bpy.context.view_layer.objects.active
    if obj is not None and obj.mode == "EDIT":
        if obj.type != "MESH" or not obj.data.total_vert_sel:
            return None
        _ensure_handler()
        key = (obj.name, obj.data.total_vert_sel, _revision, tuple(obj.matrix_world.translation))
        if _center_cache is not None and _center_cache[0] == key:
            return _center_cache[1].copy()
        bm = bmesh.from_edit_mesh(obj.data)
        total, count = Vector(), 0
        for vert in bm.verts:
            if vert.select and not vert.hide:
                total += vert.co
                count += 1
        if not count:
            return None
        center = obj.matrix_world @ (total / count)
        _center_cache = (key, center)
        return center.copy()
    if obj is not None and obj.mode != "OBJECT":
        return None
    selected = [o for o in bpy.context.view_layer.objects if o.select_get()]
    if not selected:
        return None
    return sum((o.matrix_world.translation for o in selected), Vector()) / len(selected)


def visible() -> bool:
    """Solo sin otra intención en curso: el manipulador abre su propia sesión."""
    if not _enabled:
        return False
    from ..cad.runtime import runtime
    from ..materials.runtime import runtime as materials
    from .modal import session
    from .tools import tool_session
    if runtime.workspace or materials.active or session.active:
        return False
    status = tool_session.status()
    return not (status.get("active") or status.get("armed"))


def _screen(point, rv3d, aspect) -> Vector | None:
    projected = camera.project(point, rv3d)
    return None if projected is None else Vector((projected[0] * aspect, projected[1]))


def layout(rv3d, aspect: float, center: Vector | None = None) -> dict | None:
    """Asas proyectadas alrededor de `center` (por defecto, la selección)."""
    center = _selection_center() if center is None else center
    if center is None:
        return None
    origin = _screen(center, rv3d, aspect)
    if origin is None:
        return None
    probe = max(camera.distance, 1e-6) * 1e-3
    axes = []
    for name, vector in AXES:
        tip = _screen(center + vector * probe, rv3d, aspect)
        if tip is None:
            continue
        offset = tip - origin
        axes.append({"name": name, "index": "XYZ".index(name), "vector": vector,
                     "direction": offset.normalized() if offset.length > 1e-12 else Vector((0.0, 0.0)),
                     "scale": offset.length / probe})
    if not axes:
        return None
    reference = max(axis["scale"] for axis in axes)
    if reference <= 1e-12:
        return None
    radius = RING / reference
    eye = camera.view_matrix().inverted().translation
    sight = (center - eye).normalized() if (center - eye).length > 1e-12 else Vector((0.0, 0.0, -1.0))
    hidden_axis = {"TOP": "Z", "BOTTOM": "Z", "FRONT": "Y", "BACK": "Y",
                   "LEFT": "X", "RIGHT": "X"}.get(camera.axis_view)
    if hidden_axis is None and camera.perspective == 'ORTHO':
        view_normal = camera.rotation @ Vector((0, 0, 1))
        hidden_axis = next((name for name, vector in AXES if abs(vector.dot(view_normal)) > .99999), None)
    for axis in axes:
        axis["visible"] = axis["name"] != hidden_axis and axis["scale"] >= MIN_AXIS_FRACTION * reference
        axis["ring"] = []
        if axis["name"] == hidden_axis or abs(axis["vector"].dot(sight)) < MIN_RING_OPENING:
            continue
        first = axis["vector"].orthogonal().normalized()
        second = axis["vector"].cross(first).normalized()
        ring = []
        for step in range(RING_SEGMENTS):
            angle = step * math.tau / RING_SEGMENTS
            point = _screen(center + (first * math.cos(angle) + second * math.sin(angle)) * radius,
                            rv3d, aspect)
            if point is None:
                ring = []
                break
            ring.append(point)
        axis["ring"] = ring
    return {"center": center, "origin": origin, "axes": axes}


def _segment_distance(point: Vector, start: Vector, end: Vector) -> float:
    segment = end - start
    if segment.length_squared <= 1e-18:
        return (point - start).length
    t = max(0.0, min(1.0, (point - start).dot(segment) / segment.length_squared))
    return (point - (start + segment * t)).length


def hit(gizmo: dict, point: Vector) -> tuple[str, dict | None] | None:
    """Centro > flechas y cajas > anillos; dentro de cada nivel, el más cercano."""
    origin = gizmo["origin"]
    if (point - origin).length <= CENTER + 0.012:
        return "MOVE", None
    near = []
    for axis in gizmo["axes"]:
        if not axis["visible"]:
            continue
        direction = axis["direction"]
        arrow = _segment_distance(point, origin + direction * ARROW_START, origin + direction * ARROW)
        if arrow <= TOUCH:
            near.append((arrow, "MOVE", axis))
        box = (point - (origin + direction * SCALE_BOX)).length
        if box <= TOUCH:
            near.append((box, "SCALE", axis))
    if near:
        _distance, mode, axis = min(near, key=lambda item: item[0])
        return mode, axis
    rings = []
    for axis in gizmo["axes"]:
        ring = axis["ring"]
        if ring:
            distance = min(_segment_distance(point, ring[i], ring[(i + 1) % len(ring)])
                           for i in range(len(ring)))
            if distance <= RING_TOUCH:
                rings.append((distance, "ROTATE", axis))
    uniform = abs((point - origin).length - UNIFORM)
    if uniform <= RING_TOUCH:
        rings.append((uniform, "SCALE", None))
    if rings:
        _distance, mode, axis = min(rings, key=lambda item: item[0])
        return mode, axis
    return None


def _region():
    found = find_view3d()
    if found is None:
        raise CommandError("No 3D viewport available", code="no_viewport")
    _window, _area, region, rv3d = found
    camera.sync_from_region(rv3d)
    return rv3d, max(region.width, 1) / max(region.height, 1)


def _touch(payload: dict, aspect: float) -> Vector:
    return Vector((get_float(payload, "u", 0.5) * aspect, get_float(payload, "v", 0.5)))


@command("gizmo.set")
def set_enabled(payload: dict) -> dict:
    """Android decide si el arrastre de un dedo pertenece al manipulador."""
    global _enabled
    _enabled = bool(payload.get("enabled", False))
    return {"enabled": _enabled}


def _steps(payload: dict) -> dict:
    steps = payload.get("steps") or {}
    if not isinstance(steps, dict):
        raise BadPayload("'steps' must be an object")
    return steps


@command("gizmo.drag", mutating=True)
def drag(payload: dict) -> dict:
    """BEGIN elige asa (o orbita), UPDATE sigue al dedo y END confirma un undo."""
    from . import modal
    from .view import orbit_delta
    global _drag

    phase = str(payload.get("phase", "")).upper()
    if phase not in {"BEGIN", "UPDATE", "END", "CANCEL"}:
        raise BadPayload("'phase' must be BEGIN, UPDATE, END or CANCEL")
    owner = payload.get("_client_id")

    if phase == "BEGIN":
        _drag = {"owner": owner, "missed": True}
        if not visible():
            return {"gizmo": True, "hit": False, "orbit": True}
        rv3d, aspect = _region()
        gizmo = layout(rv3d, aspect)
        point = _touch(payload, aspect)
        picked = hit(gizmo, point) if gizmo is not None else None
        if picked is None:
            return {"gizmo": True, "hit": False, "orbit": True}
        mode, axis = picked
        snap_type = str(payload.get("snap_type", "NONE")).upper()
        if snap_type not in SNAP_TYPES:
            snap_type = "NONE"
        step = _steps(payload).get(mode)
        step = float(step) if isinstance(step, (int, float)) and step > 0 else None
        scale_unit = str(payload.get("scale_step_unit", "FACTOR")).upper()
        modal.session.begin(mode, [axis["name"]] if axis else [], snap_type != "NONE", step,
                            owner_id=owner, orientation="GLOBAL", value_mode="RELATIVE",
                            snap_type=snap_type,
                            scale_step_unit=scale_unit if scale_unit in {"FACTOR", "LENGTH"} else "FACTOR")
        session_origin = _screen(modal.session.center_base(), rv3d, aspect) or gizmo["origin"]
        _drag = {"owner": owner, "missed": False, "mode": mode, "axis": axis,
                 "origin": session_origin, "grab": point, "last": point,
                 "session_id": modal.session.session_id}
        return dict(modal.session.status(), gizmo=True, hit=True,
                    handle={"mode": mode, "axis": axis["name"] if axis else None})

    if _drag is None:
        return {"gizmo": True, "moved": False}
    if owner != _drag["owner"]:
        raise CommandError("Gizmo gesture belongs to another client", code="session_owned")
    if _drag["missed"]:
        if phase == "UPDATE":
            dx, dy = get_float(payload, "dx", 0.0), get_float(payload, "dy", 0.0)
            orbit_delta(dx, dy)
            return {"gizmo": True, "hit": False, "orbit": True, "moved": bool(dx or dy)}
        _drag = None
        return {"gizmo": True, "hit": False, "orbit": True, "moved": False}
    # Un END retrasado tras abrir otra sesión nunca toca la sesión nueva.
    if not modal.session.active or modal.session.session_id != _drag["session_id"]:
        _drag = None
        return {"gizmo": True, "moved": False}
    modal.session.require(owner)

    if phase == "UPDATE":
        _, aspect = _region()
        point = _touch(payload, aspect)
        _follow(modal.session, _drag, point, payload)
        _drag["last"] = point
        modal.session.apply()
        return dict(modal.session.status(), gizmo=True)

    finished = _drag["session_id"]
    effective = modal.session._effective()
    if _drag["mode"] == "MOVE":
        moved = effective.length > 1e-12
    elif _drag["mode"] == "ROTATE":
        moved = abs(modal.session._rotation_angle(effective)) > 1e-9
    else:
        moved = any(abs(value - 1.0) > 1e-9 for value in effective)
    _drag = None
    if phase == "CANCEL" or not moved:
        result = modal.cancel(payload)
    else:
        result = modal.confirm(payload)
    return dict(result, gizmo=True, gizmo_finished=finished, moved=moved and phase == "END")


def _follow(session, drag_state: dict, point: Vector, payload: dict) -> None:
    """Convierte la posición del dedo en el valor del modo, sin sensibilidades."""
    from .modal import MIN_SCALE
    axis, origin = drag_state["axis"], drag_state["origin"]
    if drag_state["mode"] == "MOVE":
        if axis is None:
            session.nudge(get_float(payload, "dx", 0.0), get_float(payload, "dy", 0.0))
            return
        delta = point - drag_state["last"]
        session.values[axis["index"]] += delta.dot(axis["direction"]) / axis["scale"]
        return
    if drag_state["mode"] == "ROTATE":
        before, after = drag_state["last"] - origin, point - origin
        if before.length < 1e-6 or after.length < 1e-6:
            return
        # Pantalla con y hacia abajo: el producto cruzado con y hacia arriba da el
        # giro antihorario visible, positivo si el eje apunta hacia la cámara.
        cross = before.y * after.x - before.x * after.y
        angle = math.atan2(cross, before.dot(after))
        eye = camera.view_matrix().inverted().translation
        facing = 1.0 if axis["vector"].dot(eye - session.center_base()) >= 0.0 else -1.0
        session.values[axis["index"]] += angle * facing
        return
    grab = drag_state["grab"] - origin
    current = point - origin
    session.scale_exact = False
    if axis is None:
        factor = current.length / grab.length if grab.length > 1e-6 else 1.0
        session.values = Vector((max(MIN_SCALE, factor),) * 3)
        return
    reference = grab.dot(axis["direction"])
    factor = current.dot(axis["direction"]) / reference if abs(reference) > 1e-6 else 1.0
    values = Vector((1.0, 1.0, 1.0))
    values[axis["index"]] = max(MIN_SCALE, factor)
    session.values = values


def drag_guide() -> dict | None:
    """Asa activa durante el arrastre, para dibujar su guía en el vídeo."""
    return None if _drag is None or _drag.get("missed") else _drag


def owner_disconnected(owner_id) -> None:
    global _drag, _enabled
    if _drag is not None and _drag.get("owner") == owner_id:
        _drag = None
    _enabled = False
