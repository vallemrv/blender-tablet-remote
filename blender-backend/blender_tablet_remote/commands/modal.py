"""Transformación modal: se confirma a mano, no al soltar el dedo.

Blender trabaja así (G, mover, clic para confirmar) y en una tablet lo es todavía
más: levantar el dedo para recolocar la mano no debe dar por terminado el
movimiento, y hay que poder cambiar de eje, de incremento o teclear el valor exacto
con la transformación aún viva.

Los comandos se llaman `transform.*` como el resto de la familia, pero viven aparte
porque esto es una máquina de estados, no operaciones sueltas.

**Cada cambio recalcula desde las matrices originales** en vez de acumular sobre lo
ya aplicado. Es la decisión que sostiene todo lo demás: el snap y la entrada numérica
salen exactos (no arrastran el error de las doscientas aplicaciones anteriores),
cancelar es restaurar, y cambiar de eje a mitad de gesto no deja residuo del eje
anterior.
"""

from __future__ import annotations

import math
import uuid

import bpy
import bmesh
from mathutils import Matrix, Vector

from .. import state
from ..bpy_utils import require_rv3d, selected_objects, undo_push
from ..camera import camera
from ..errors import BadPayload, CommandError
from . import command

MODES = ("MOVE", "ROTATE", "SCALE")
AXIS_INDEX = {"X": 0, "Y": 1, "Z": 2}

# Incremento por defecto de cada modo: 1 cm, 5 grados, 0.1 de factor.
DEFAULT_STEP = {"MOVE": 0.01, "ROTATE": math.radians(5.0), "SCALE": 0.1}

# Cuánto gira un arrastre de pantalla completa, y cuánto escala.
ROTATE_SENSITIVITY = math.pi
SCALE_SENSITIVITY = 2.0

MIN_SCALE = 1e-4


class _Session:
    """La transformación en curso. Una sola, global: la tablet es un único usuario."""

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self.active = False
        self.mode = "MOVE"
        self.axes: list[str] = []
        self.snap = False
        self.snap_type = "NONE"
        self.snap_candidate = None
        self.snap_locked = False
        self.step = DEFAULT_STEP["MOVE"]
        # Sentido según el modo: metros, radianes o factor.
        self.values = Vector((0.0, 0.0, 0.0))
        self.angle = 0.0
        self.rotation_axis = Vector((0.0, 0.0, 1.0))
        self.orientation_basis = Matrix.Identity(3)
        self.originals: list[tuple[object, Matrix]] = []
        self.pivot = Vector((0.0, 0.0, 0.0))
        self.session_id = None
        self.owner_id = None
        self.phase = "IDLE"
        self.orientation = "GLOBAL"
        self.value_mode = "RELATIVE"
        self.edit_object = None
        self.edit_coords: dict[int, Vector] = {}
        self.edit_topology = None
        self.selection_signature = None

    # ------------------------------------------------------------------ ciclo

    def begin(self, mode: str, axes: list[str], snap: bool, step: float | None,
              owner_id=None, orientation="GLOBAL", value_mode="RELATIVE", snap_type="NONE") -> None:
        active = bpy.context.view_layer.objects.active
        edit = active is not None and active.mode == "EDIT" and active.type == "MESH"
        objs = selected_objects()
        if not objs and not edit:
            raise CommandError("Nothing selected", code="empty_selection")

        self.reset()
        self.active = True
        self.phase = "ACTIVE"
        self.session_id = str(uuid.uuid4())
        self.owner_id = owner_id
        self.orientation = orientation
        self.value_mode = value_mode
        self.mode = mode
        self.axes = axes
        self.snap = snap
        self.snap_type = snap_type
        self.step = DEFAULT_STEP[mode] if step is None else step
        if edit:
            bm = bmesh.from_edit_mesh(active.data)
            bm.verts.ensure_lookup_table()
            selected = [v for v in bm.verts if v.select and not v.hide]
            if not selected:
                self.reset()
                raise CommandError("Nothing selected", code="empty_selection")
            self.edit_object = active
            self.edit_coords = {v.index: v.co.copy() for v in selected}
            self.edit_topology = (len(bm.verts), len(bm.edges), len(bm.faces))
            self.selection_signature = tuple(sorted(self.edit_coords))
            local_center = sum(self.edit_coords.values(), Vector()) / len(self.edit_coords)
            self.pivot = active.matrix_world @ local_center
        else:
            self.originals = [(obj, obj.matrix_world.copy()) for obj in objs]
            self.selection_signature = tuple(sorted(o.name for o in objs))

        total = Vector((0.0, 0.0, 0.0))
        if self.originals:
            for _obj, matrix in self.originals:
                total += matrix.translation
            self.pivot = total / len(self.originals)

        if mode == "SCALE":
            self.values = Vector((1.0, 1.0, 1.0))
        self.orientation_basis = self._resolve_orientation_basis()
        self.rotation_axis = self._resolve_rotation_axis()

    def _resolve_orientation_basis(self) -> Matrix:
        if self.orientation == "GLOBAL":
            return Matrix.Identity(3)
        if self.orientation == "VIEW":
            try:
                camera.sync_from_region(require_rv3d())
                return camera.rotation.to_matrix()
            except CommandError:
                return Matrix.Identity(3)
        obj = self.edit_object or bpy.context.view_layer.objects.active
        if self.orientation == "LOCAL" and obj is not None:
            return obj.matrix_world.to_3x3().normalized()
        if self.orientation == "NORMAL" and self.edit_object is not None:
            bm = bmesh.from_edit_mesh(self.edit_object.data)
            normals = [v.normal for v in bm.verts if v.select and not v.hide]
            if normals:
                normal = (self.edit_object.matrix_world.to_3x3() @
                          (sum(normals, Vector()) / len(normals))).normalized()
                helper = Vector((0.0, 1.0, 0.0)) if abs(normal.z) > 0.9 else Vector((0.0, 0.0, 1.0))
                x_axis = helper.cross(normal).normalized()
                y_axis = normal.cross(x_axis).normalized()
                return Matrix((x_axis, y_axis, normal)).transposed()
        return Matrix.Identity(3)

    def _resolve_rotation_axis(self) -> Vector:
        """Con eje elegido, ése; sin eje, el de visión, como la R de Blender."""
        if self.axes:
            vector = Vector((0.0, 0.0, 0.0))
            vector[AXIS_INDEX[self.axes[0]]] = 1.0
            return (self.orientation_basis @ vector).normalized()
        try:
            camera.sync_from_region(require_rv3d())
            return (camera.rotation @ Vector((0.0, 0.0, 1.0))).normalized()
        except CommandError:
            return Vector((0.0, 0.0, 1.0))  # sin ventana (tests headless)

    def require(self, owner_id=None) -> None:
        if not self.active:
            raise CommandError("No transform in progress", code="no_session")
        if owner_id is not None and self.owner_id is not None and owner_id != self.owner_id:
            raise CommandError("Transform session belongs to another client", code="session_owned")
        if self.edit_object is not None:
            obj = self.edit_object
            if obj.name not in bpy.data.objects or obj.mode != "EDIT":
                self.invalidate("mode_or_object_changed")
            bm = bmesh.from_edit_mesh(obj.data)
            signature = tuple(sorted(v.index for v in bm.verts if v.select and not v.hide))
            if (len(bm.verts), len(bm.edges), len(bm.faces)) != self.edit_topology or signature != self.selection_signature:
                self.invalidate("selection_or_topology_changed")
            return
        # Un objeto borrado a mitad de transformación deja una referencia muerta.
        self.originals = [(o, m) for o, m in self.originals if o.name in bpy.data.objects]
        if not self.originals:
            self.reset()
            raise CommandError("The objects being transformed are gone", code="no_session")
        if tuple(sorted(o.name for o in bpy.context.selected_objects)) != self.selection_signature:
            self.invalidate("selection_changed")

    def invalidate(self, reason: str) -> None:
        self.restore()
        session_id = self.session_id
        self.reset()
        self.phase = "INVALIDATED"
        raise CommandError(f"Transform invalidated: {reason}", code="session_invalidated")

    def owner_disconnected(self, owner_id) -> None:
        if self.active and self.owner_id == owner_id:
            self.restore()
            self.reset()
            self.phase = "CANCELLED"

    # -------------------------------------------------------------- acumular

    def nudge(self, dx: float, dy: float) -> None:
        """Arrastre en pantalla (fracción de pantalla) -> incremento del modo."""
        if self.mode == "MOVE":
            self.values += self.orientation_basis.inverted() @ self._screen_to_world(dx, dy)
        elif self.mode == "ROTATE":
            self.angle += dx * ROTATE_SENSITIVITY
        else:
            # Arrastrar hacia arriba agranda: en pantalla dy es negativo hacia arriba.
            factor = 1.0 - dy * SCALE_SENSITIVITY
            self.values = Vector(max(MIN_SCALE, v * factor) for v in self.values)

    def _screen_to_world(self, dx: float, dy: float) -> Vector:
        """Mismo cálculo que el paneo: el objeto sigue al dedo (ver camera.py)."""
        rv3d = require_rv3d()
        camera.sync_from_region(rv3d)
        right = camera.rotation @ Vector((1.0, 0.0, 0.0))
        up = camera.rotation @ Vector((0.0, 1.0, 0.0))
        span_x, span_y = camera.screen_span(camera.projection_matrix(rv3d))
        return right * (dx * span_x) - up * (dy * span_y)

    def set_values(self, values) -> None:
        """Entrada numérica: fija el delta en vez de sumarlo."""
        if self.mode == "ROTATE":
            self.angle = float(values[0])
        else:
            self.values = Vector((float(values[0]), float(values[1]), float(values[2])))

    # --------------------------------------------------------------- aplicar

    def _effective(self) -> tuple[Vector, float]:
        """Delta ya filtrado por ejes y cuadrado al incremento."""
        values = self.values.copy()
        angle = self.angle

        if self.mode == "MOVE":
            if self.axes:
                for name, index in AXIS_INDEX.items():
                    if name not in self.axes:
                        values[index] = 0.0
            if self.snap and self.snap_type in {"INCREMENT", "GRID"} and self.step > 0:
                values = Vector(round(v / self.step) * self.step for v in values)
        elif self.mode == "SCALE":
            if self.axes:
                for name, index in AXIS_INDEX.items():
                    if name not in self.axes:
                        values[index] = 1.0
            if self.snap and self.snap_type in {"INCREMENT", "GRID"} and self.step > 0:
                values = Vector(max(MIN_SCALE, round(v / self.step) * self.step) for v in values)
        else:
            if self.snap and self.snap_type in {"INCREMENT", "GRID"} and self.step > 0:
                angle = round(angle / self.step) * self.step

        return values, angle

    def apply(self) -> None:
        """Reconstruye desde las matrices originales. Idempotente a propósito."""
        values, angle = self._effective()

        if self.edit_object is not None:
            self._apply_edit(values, angle)
            return
        for obj, original in self.originals:
            if self.mode == "MOVE":
                obj.matrix_world = Matrix.Translation(self.orientation_basis @ values) @ original
            elif self.mode == "ROTATE":
                rotation = Matrix.Rotation(angle, 4, self.rotation_axis)
                obj.matrix_world = (
                    Matrix.Translation(self.pivot)
                    @ rotation
                    @ Matrix.Translation(-self.pivot)
                    @ original
                )
            else:
                oriented_scale = self.orientation_basis @ Matrix.Diagonal(values) @ self.orientation_basis.inverted()
                scale = oriented_scale.to_4x4()
                obj.matrix_world = (
                    Matrix.Translation(self.pivot)
                    @ scale
                    @ Matrix.Translation(-self.pivot)
                    @ original
                )

    def _apply_edit(self, values: Vector, angle: float) -> None:
        obj = self.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        inv = obj.matrix_world.inverted()
        rotation = Matrix.Rotation(angle, 4, self.rotation_axis)
        scale = Matrix.Diagonal(values).to_4x4()
        for index, original_local in self.edit_coords.items():
            world = obj.matrix_world @ original_local
            if self.mode == "MOVE":
                result = world + self.orientation_basis @ values
            elif self.mode == "ROTATE":
                result = self.pivot + rotation.to_3x3() @ (world - self.pivot)
            else:
                oriented_scale = self.orientation_basis @ scale.to_3x3() @ self.orientation_basis.inverted()
                result = self.pivot + oriented_scale @ (world - self.pivot)
            bm.verts[index].co = inv @ result
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
    def restore(self) -> None:
        if self.edit_object is not None and self.edit_object.name in bpy.data.objects and self.edit_object.mode == "EDIT":
            bm = bmesh.from_edit_mesh(self.edit_object.data)
            bm.verts.ensure_lookup_table()
            for index, co in self.edit_coords.items():
                if index < len(bm.verts):
                    bm.verts[index].co = co
            bmesh.update_edit_mesh(self.edit_object.data, loop_triangles=False, destructive=False)
            return
        for obj, original in self.originals:
            obj.matrix_world = original

    # ---------------------------------------------------------------- estado

    def status(self) -> dict:
        if not self.active:
            return {"active": False}
        values, angle = self._effective()
        return {
            "active": True,
            "session_id": self.session_id,
            "owner": self.owner_id,
            "phase": self.phase,
            "mode": self.mode,
            "tool": self.mode,
            "orientation": self.orientation,
            "value_mode": self.value_mode,
            "axes": list(self.axes),
            "snap": self.snap,
            "snap_type": self.snap_type,
            "snap_candidate": self.snap_candidate,
            "snap_locked": self.snap_locked,
            "step": self.step,
            "objects": [o.name for o, _m in self.originals] or ([self.edit_object.name] if self.edit_object else []),
            # Lo que la barra enseña mientras se arrastra. La rotación va en grados
            # porque es lo que se lee, no radianes.
            "values": list(values),
            "angle": math.degrees(angle),
        }


session = _Session()


# ----------------------------------------------------------------- comandos


def _parse_axes(payload: dict) -> list[str]:
    raw = payload.get("axes", [])
    if "constraint" in payload and "axes" not in payload:
        constraint = str(payload["constraint"]).upper()
        raw = [] if constraint in ("FREE", "VIEW", "NORMAL") else list(constraint)
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)):
        raise BadPayload("'axes' must be a list of X, Y, Z")
    axes = []
    for item in raw:
        name = str(item).upper()
        if name not in AXIS_INDEX:
            raise BadPayload(f"Unknown axis '{name}'. Options: X, Y, Z")
        if name not in axes:
            axes.append(name)
    return axes


def _parse_step(payload: dict, default=None):
    if "step" not in payload:
        return default
    try:
        step = float(payload["step"])
    except (TypeError, ValueError):
        raise BadPayload("'step' must be a number")
    if step <= 0:
        raise BadPayload("'step' must be greater than zero")
    return step


@command("transform.begin", mutating=True)
def begin(payload: dict) -> dict:
    """Abre una transformación modal sobre selección Object o Edit."""
    mode = str(payload.get("mode", "MOVE")).upper()
    if mode not in MODES:
        raise BadPayload(f"'mode' must be one of {', '.join(MODES)}")

    active = bpy.context.view_layer.objects.active
    if active is not None and active.mode not in ("OBJECT", "EDIT"):
        raise CommandError("Modal transform requires Object or Edit Mode", code="wrong_mode")

    orientation = str(payload.get("orientation", "GLOBAL")).upper()
    valid_orientations = {"GLOBAL", "LOCAL", "NORMAL", "VIEW"}
    if orientation not in valid_orientations:
        raise BadPayload("'orientation' must be GLOBAL, LOCAL, NORMAL or VIEW")
    if orientation == "NORMAL" and (active is None or active.mode != "EDIT"):
        raise BadPayload("NORMAL orientation is only valid in Edit Mode")
    value_mode = str(payload.get("value_mode", "RELATIVE")).upper()
    if value_mode not in ("RELATIVE", "ABSOLUTE"):
        raise BadPayload("'value_mode' must be RELATIVE or ABSOLUTE")
    snap_type = str(payload.get("snap_type", "INCREMENT" if payload.get("snap") else "NONE")).upper()
    if snap_type not in {"NONE", "INCREMENT", "GRID", "VERTEX", "EDGE", "FACE", "CURSOR"}:
        raise BadPayload("Unknown 'snap_type'")
    if mode != "MOVE" and snap_type in {"VERTEX", "EDGE", "FACE", "CURSOR"}:
        raise BadPayload("Geometric snap is only valid for MOVE")

    # Una sesión abierta se descarta: empezar a mover con algo a medias sería
    # acumular dos transformaciones sin que el usuario lo pidiera.
    if session.active:
        session.restore()

    step = _parse_step(payload)
    if step is None and payload.get("mode") == "ROTATE" and "step_degrees" in payload:
        step = math.radians(float(payload["step_degrees"]))

    session.begin(mode, _parse_axes(payload), bool(payload.get("snap", False)), step,
                  payload.get("_client_id"), orientation, value_mode, snap_type)
    session.apply()
    return session.status()


@command("transform.axes", mutating=True)
def set_axes(payload: dict) -> dict:
    """Cambia la restricción de ejes con la transformación viva."""
    session.require(payload.get("_client_id"))
    session.axes = _parse_axes(payload)
    if session.mode == "ROTATE":
        session.rotation_axis = session._resolve_rotation_axis()
    session.apply()
    return session.status()


@command("transform.snap", mutating=True)
def set_snap(payload: dict) -> dict:
    """Activa el cuadrado a incrementos y/o cambia el tamaño del incremento."""
    session.require(payload.get("_client_id"))
    if "snap" in payload:
        session.snap = bool(payload["snap"])
    if "snap_type" in payload:
        snap_type = str(payload["snap_type"]).upper()
        if snap_type not in {"NONE", "INCREMENT", "GRID", "VERTEX", "EDGE", "FACE", "CURSOR"}:
            raise BadPayload("Unknown 'snap_type'")
        session.snap_type = snap_type
    step = _parse_step(payload, session.step)
    session.step = step
    session.apply()
    return session.status()


@command("transform.snap_candidate", mutating=True)
def set_snap_candidate(payload: dict) -> dict:
    """Busca y bloquea el candidato geométrico que se previsualiza bajo el dedo."""
    session.require(payload.get("_client_id"))
    if session.mode != "MOVE":
        raise CommandError("Geometric snap requires MOVE", code="wrong_tool")
    from .snap import query_candidate
    query_payload = dict(payload)
    query_payload["snap_type"] = payload.get("snap_type", session.snap_type)
    candidate = query_candidate(query_payload)
    if not candidate.get("hit"):
        session.snap_candidate = None
        session.snap_locked = False
        return dict(session.status(), candidate=candidate)
    session.snap_type = candidate["snap_type"]
    session.snap = True
    session.snap_candidate = candidate
    session.snap_locked = bool(payload.get("lock", True))
    session.values = session.orientation_basis.inverted() @ (Vector(candidate["position"]) - session.pivot)
    session.apply()
    return session.status()


@command("transform.nudge", mutating=True)
def nudge(payload: dict) -> dict:
    """Incremento por arrastre. Normalmente llega por el canal de gestos."""
    session.require(payload.get("_client_id"))
    try:
        dx = float(payload.get("dx", 0.0))
        dy = float(payload.get("dy", 0.0))
    except (TypeError, ValueError):
        raise BadPayload("'dx' and 'dy' must be numbers")
    session.nudge(dx, dy)
    session.apply()
    return session.status()


@command("transform.value", mutating=True)
def set_value(payload: dict) -> dict:
    """Valor exacto: [x, y, z] para mover/escalar, o `angle` en grados para rotar."""
    session.require(payload.get("_client_id"))
    if session.mode == "ROTATE":
        if "angle" not in payload:
            raise BadPayload("'angle' is required when rotating")
        try:
            session.angle = math.radians(float(payload["angle"]))
        except (TypeError, ValueError):
            raise BadPayload("'angle' must be a number")
    else:
        values = payload.get("values")
        if not isinstance(values, (list, tuple)) or len(values) != 3:
            raise BadPayload("'values' must be [x, y, z]")
        try:
            numeric = Vector(float(value) for value in values)
            if session.value_mode == "ABSOLUTE" and session.mode == "MOVE":
                numeric = session.orientation_basis.inverted() @ (numeric - session.pivot)
            session.set_values(numeric)
        except (TypeError, ValueError):
            raise BadPayload("'values' must contain numbers")
    session.apply()
    return session.status()


@command("transform.confirm", mutating=True)
def confirm(payload: dict) -> dict:
    """Cierra la transformación y la deja como un único paso de undo."""
    session.require(payload.get("_client_id"))
    session.apply()
    undo_push(f"Remote {session.mode.lower()}")
    session.reset()
    return dict(state.snapshot(include_view=False), active=False)


@command("transform.cancel", mutating=True)
def cancel(payload: dict) -> dict:
    """Devuelve todo a como estaba antes de `transform.begin`."""
    session.require(payload.get("_client_id"))
    session.restore()
    session.reset()
    return dict(state.snapshot(include_view=False), active=False)


@command("transform.status")
def status(payload: dict) -> dict:
    return session.status()
