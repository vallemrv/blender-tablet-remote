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
from mathutils.kdtree import KDTree

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
PROPORTIONAL_FALLOFFS = {"SMOOTH", "SPHERE", "ROOT", "SHARP", "LINEAR", "CONSTANT", "INVERSE_SQUARE"}


def edit_settings_state() -> dict:
    settings = bpy.context.scene.tool_settings
    return {
        "proportional": bool(settings.use_proportional_edit),
        "proportional_connected": bool(settings.use_proportional_connected),
        "falloff": str(settings.proportional_edit_falloff),
        "radius": float(settings.proportional_size),
        "auto_merge": bool(settings.use_mesh_automerge),
        "merge_threshold": float(settings.double_threshold),
    }


def _falloff_weight(falloff: str, distance: float, radius: float) -> float:
    if distance <= 0.0:
        return 1.0
    if radius <= 0.0 or distance >= radius:
        return 0.0
    x = 1.0 - distance / radius
    if falloff == "CONSTANT":
        return 1.0
    if falloff == "LINEAR":
        return x
    if falloff == "SHARP":
        return x * x
    if falloff == "ROOT":
        return math.sqrt(x)
    if falloff == "SPHERE":
        return math.sqrt(max(0.0, 2.0 * x - x * x))
    if falloff == "INVERSE_SQUARE":
        return x * (2.0 - x)
    return x * x * (3.0 - 2.0 * x)  # SMOOTH


def _mirror_clip_planes(obj, edit_coords: dict[int, Vector]):
    """Congela los espacios de los Mirror visibles que tienen Clipping activo."""
    clips = []
    for modifier in obj.modifiers:
        if modifier.type != "MIRROR" or not modifier.show_viewport or not modifier.use_clip:
            continue
        axes = tuple(index for index, enabled in enumerate(modifier.use_axis) if enabled)
        if not axes:
            continue
        if modifier.mirror_object is None:
            to_mirror = Matrix.Identity(4)
        else:
            to_mirror = modifier.mirror_object.matrix_world.inverted_safe() @ obj.matrix_world
        from_mirror = to_mirror.inverted_safe()
        originals = {index: to_mirror @ co for index, co in edit_coords.items()}
        clips.append((to_mirror, from_mirror, axes, float(modifier.merge_threshold), originals))
    return clips


# `merge_threshold` decide cuándo Mirror fusiona dos lados al evaluar el modificador;
# no convierte todo vértice cercano en parte de la costura durante una transformación.
# Solo una coordenada que ya está numéricamente sobre el plano debe quedar inmóvil.
MIRROR_SEAM_EPSILON = 1e-7


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
        # Recuento O(1) de la selección (Mesh.total_*_sel) para el camino rápido de
        # require(): sin él, cada nudge recorría bm.verts entero y en una malla de
        # 90 k vértices a 60 Hz eso eran millones de iteraciones por segundo.
        self._edit_sel_counts = None
        # matrix_world y su inversa congeladas al comenzar: en Edit Mode no pueden
        # cambiar sin salir del modo, y require() ya invalida en ese caso.
        self.edit_world = None
        self.edit_world_inv = None
        # Pivote en coordenadas locales de la malla (ya calculado en begin).
        self.pivot_local = None
        self.proportional = False
        self.proportional_radius = 1.0
        self.proportional_falloff = "SMOOTH"
        self.edit_weights: dict[int, float] = {}
        # Planos de Mirror con Clipping. Cada entrada conserva la transformación
        # local-malla -> espacio del espejo y el lado original de cada vértice.
        self.mirror_clips: list[tuple[Matrix, Matrix, tuple[int, ...], float, dict[int, Vector]]] = []

    # ------------------------------------------------------------------ ciclo

    def begin(self, mode: str, axes: list[str], snap: bool, step: float | None,
              owner_id=None, orientation="GLOBAL", value_mode="RELATIVE", snap_type="NONE",
              proportional=None, proportional_radius=None, proportional_falloff=None) -> None:
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
        tool_settings = bpy.context.scene.tool_settings
        self.proportional = bool(tool_settings.use_proportional_edit if proportional is None else proportional)
        self.proportional_radius = float(tool_settings.proportional_size if proportional_radius is None else proportional_radius)
        self.proportional_falloff = str(
            tool_settings.proportional_edit_falloff if proportional_falloff is None else proportional_falloff
        ).upper()
        if edit:
            bm = bmesh.from_edit_mesh(active.data)
            bm.verts.ensure_lookup_table()
            selected = [v for v in bm.verts if v.select and not v.hide]
            if not selected:
                self.reset()
                raise CommandError("Nothing selected", code="empty_selection")
            self.edit_object = active
            selected_indices = frozenset(v.index for v in selected)
            if self.proportional:
                tree = KDTree(len(selected))
                for tree_index, vert in enumerate(selected):
                    tree.insert(active.matrix_world @ vert.co, tree_index)
                tree.balance()
                for vert in bm.verts:
                    if vert.hide:
                        continue
                    if vert.index in selected_indices:
                        weight = 1.0
                    else:
                        _co, _index, distance = tree.find(active.matrix_world @ vert.co)
                        weight = _falloff_weight(
                            self.proportional_falloff, distance, self.proportional_radius)
                    if weight > 0.0:
                        self.edit_coords[vert.index] = vert.co.copy()
                        self.edit_weights[vert.index] = weight
            else:
                self.edit_coords = {v.index: v.co.copy() for v in selected}
                self.edit_weights = {v.index: 1.0 for v in selected}
            self.edit_topology = (len(bm.verts), len(bm.edges), len(bm.faces))
            self.selection_signature = selected_indices
            self._edit_sel_counts = (active.data.total_vert_sel, active.data.total_edge_sel,
                                     active.data.total_face_sel)
            self.edit_world = active.matrix_world.copy()
            self.edit_world_inv = self.edit_world.inverted()
            self.mirror_clips = _mirror_clip_planes(active, self.edit_coords)
            local_center = sum((vert.co for vert in selected), Vector()) / len(selected)
            self.pivot = active.matrix_world @ local_center
            self.pivot_local = local_center
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
            try:
                valid = obj.name in bpy.data.objects and obj.mode == "EDIT"
            except ReferenceError:
                valid = False
            if not valid:
                self.invalidate("mode_or_object_changed")
            bm = bmesh.from_edit_mesh(obj.data)
            topology = (len(bm.verts), len(bm.edges), len(bm.faces))
            sel_counts = (obj.data.total_vert_sel, obj.data.total_edge_sel, obj.data.total_face_sel)
            # Camino rápido O(1): si topología y conteos no se mueven, la selección
            # es la misma que la última vez validada. Solo si algo cambia se paga el
            # recorrido exacto para comparar la firma índice a índice.
            if topology == self.edit_topology and sel_counts == self._edit_sel_counts:
                return
            signature = frozenset(v.index for v in bm.verts if v.select and not v.hide)
            if topology != self.edit_topology or signature != self.selection_signature:
                self.invalidate("selection_or_topology_changed")
            self._edit_sel_counts = sel_counts
            return
        # Un objeto borrado a mitad de transformación deja una referencia muerta.
        valid_originals = []
        for obj, matrix in self.originals:
            try:
                if obj.name in bpy.data.objects:
                    valid_originals.append((obj, matrix))
            except ReferenceError:
                continue
        self.originals = valid_originals
        if not self.originals:
            self.reset()
            raise CommandError("The objects being transformed are gone", code="no_session")
        if tuple(sorted(o.name for o in bpy.context.selected_objects)) != self.selection_signature:
            self.invalidate("selection_changed")

    def invalidate(self, reason: str) -> None:
        self.restore_safely()
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
        """Arrastre en pantalla (fracción de pantalla) -> incremento del modo.

        Rotate y Scale comparten el eje horizontal (B6): dedo a la derecha gira en
        sentido horario visto en pantalla y agranda; a la izquierda, antihorario y
        encoge. Antes ambos usaban +dx crudo (Scale ni eso: usaba dy) y en tablet
        real quedaban al revés / sin responder al arrastre horizontal.
        """
        if self.mode == "MOVE":
            self.values += self.orientation_basis.inverted() @ self._screen_to_world(dx, dy)
        elif self.mode == "ROTATE":
            self.angle -= dx * ROTATE_SENSITIVITY
        else:
            factor = 1.0 + dx * SCALE_SENSITIVITY
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
            if self.snap and self.step > 0:
                if self.snap_type == "GRID":
                    # Rejilla mundial absoluta: se redondea la posición destino
                    # (pivote original + offset mundial) a múltiplos de step.
                    # Así un objeto que nace fuera de rejilla aterriza en ella,
                    # que es lo que espera todo el que pide "rejilla".
                    offset = self.orientation_basis @ values
                    pivot = self.pivot
                    active_indices = ({AXIS_INDEX[name] for name in self.axes}
                                      if self.axes else set(range(3)))
                    snapped = offset.copy()
                    for index in active_indices:
                        snapped[index] = (
                            round((pivot[index] + offset[index]) / self.step) * self.step
                            - pivot[index]
                        )
                    values = self.orientation_basis.inverted() @ snapped
                elif self.snap_type == "INCREMENT":
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
        """Aplica el delta sobre las coords originales, en local y sin matrices por vértice.

        Antes esto invertía `matrix_world` y multiplicaba matrices 4×4 por cada
        vértice en cada nudge. Ahora todo lo que no depende del vértice se calcula
        una vez: MOVE se reduce a una suma por vértice, ROTATE/SCALE a una única
        matriz 3×3 local (W⁻¹ · R · W) aplicada alrededor del pivote.
        """
        obj = self.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        world = self.edit_world
        world_inv = self.edit_world_inv
        verts = bm.verts

        if self.mode == "MOVE":
            # co' = W⁻¹·(W·co + delta_mundo) = co + W⁻¹·delta_mundo
            delta_local = world_inv @ (self.orientation_basis @ values)
            for index, original_local in self.edit_coords.items():
                verts[index].co = original_local + delta_local * self.edit_weights.get(index, 1.0)
        else:
            if self.mode == "ROTATE":
                linear = Matrix.Rotation(angle, 3, self.rotation_axis)
            else:
                linear = self.orientation_basis @ Matrix.Diagonal(values) @ self.orientation_basis.inverted()
            pivot_local = self.pivot_local
            local_matrix = world_inv.to_3x3() @ linear @ world.to_3x3()
            for index, original_local in self.edit_coords.items():
                transformed = pivot_local + local_matrix @ (original_local - pivot_local)
                verts[index].co = original_local.lerp(transformed, self.edit_weights.get(index, 1.0))
        self._apply_mirror_clipping(verts)
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)

    def _apply_mirror_clipping(self, verts) -> None:
        """Emula el límite que los operadores nativos aplican con Mirror Clipping."""
        for to_mirror, from_mirror, axes, _merge_threshold, originals in self.mirror_clips:
            for index, original_mirror in originals.items():
                candidate = to_mirror @ verts[index].co
                for axis in axes:
                    original = original_mirror[axis]
                    value = candidate[axis]
                    if abs(original) <= MIRROR_SEAM_EPSILON:
                        candidate[axis] = 0.0
                    elif original > 0.0 and value < 0.0:
                        candidate[axis] = 0.0
                    elif original < 0.0 and value > 0.0:
                        candidate[axis] = 0.0
                verts[index].co = from_mirror @ candidate
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

    def restore_safely(self) -> bool:
        """Restaura si los RNA siguen vivos; una referencia eliminada no debe escapar."""
        try:
            self.restore()
            return True
        except (ReferenceError, RuntimeError):
            return False

    def invalidate_silently(self) -> None:
        self.restore_safely()
        self.reset()
        self.phase = "INVALIDATED"

    # ---------------------------------------------------------------- estado

    def status(self) -> dict:
        if not self.active:
            return {"active": False}
        try:
            self.require()
        except CommandError as exc:
            if exc.code in {"session_invalidated", "no_session"}:
                return {"active": False, "phase": "INVALIDATED"}
            raise
        except (ReferenceError, RuntimeError):
            self.invalidate_silently()
            return {"active": False, "phase": "INVALIDATED"}
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
            "proportional": self.proportional,
            "proportional_radius": self.proportional_radius,
            "proportional_falloff": self.proportional_falloff,
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
    if snap_type not in {"NONE", "INCREMENT", "GRID", "VERTEX", "EDGE", "EDGE_CENTER", "FACE", "FACE_CENTER", "CURSOR"}:
        raise BadPayload("Unknown 'snap_type'")
    if mode != "MOVE" and snap_type in {"VERTEX", "EDGE", "EDGE_CENTER", "FACE", "FACE_CENTER", "CURSOR"}:
        raise BadPayload("Geometric snap is only valid for MOVE")
    proportional_falloff = str(payload.get(
        "proportional_falloff", bpy.context.scene.tool_settings.proportional_edit_falloff)).upper()
    if proportional_falloff not in PROPORTIONAL_FALLOFFS:
        raise BadPayload("Unknown proportional falloff")
    try:
        proportional_radius = float(payload.get(
            "proportional_radius", bpy.context.scene.tool_settings.proportional_size))
    except (TypeError, ValueError):
        raise BadPayload("'proportional_radius' must be a number")
    if proportional_radius <= 0.0:
        raise BadPayload("'proportional_radius' must be greater than zero")

    # Una sesión abierta se descarta: empezar a mover con algo a medias sería
    # acumular dos transformaciones sin que el usuario lo pidiera.
    from .sessions import cancel_tool
    cancel_tool(restore=True)
    if session.active:
        session.restore_safely()

    step = _parse_step(payload)
    if step is None and payload.get("mode") == "ROTATE" and "step_degrees" in payload:
        step = math.radians(float(payload["step_degrees"]))

    session.begin(mode, _parse_axes(payload), bool(payload.get("snap", False)), step,
                  payload.get("_client_id"), orientation, value_mode, snap_type,
                  payload.get("proportional"), proportional_radius,
                  proportional_falloff)
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
        if snap_type not in {"NONE", "INCREMENT", "GRID", "VERTEX", "EDGE", "EDGE_CENTER", "FACE", "FACE_CENTER", "CURSOR"}:
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
    if session.edit_object is not None and session.mode == "MOVE" and bpy.context.scene.tool_settings.use_mesh_automerge:
        bm = bmesh.from_edit_mesh(session.edit_object.data)
        bm.verts.ensure_lookup_table()
        moved = [bm.verts[index] for index in session.selection_signature if index < len(bm.verts)]
        stationary = [vert for vert in bm.verts if vert.index not in session.selection_signature and not vert.hide]
        if moved:
            found = bmesh.ops.find_doubles(
                bm, verts=moved + stationary, keep_verts=stationary,
                dist=float(bpy.context.scene.tool_settings.double_threshold),
            )
            if found.get("targetmap"):
                bmesh.ops.weld_verts(bm, targetmap=found["targetmap"])
                bmesh.update_edit_mesh(session.edit_object.data, loop_triangles=True, destructive=True)
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


@command("edit.settings")
def get_edit_settings(payload: dict) -> dict:
    return edit_settings_state()


@command("edit.settings_set", mutating=True)
def set_edit_settings(payload: dict) -> dict:
    settings = bpy.context.scene.tool_settings
    if "proportional" in payload:
        settings.use_proportional_edit = bool(payload["proportional"])
    if "falloff" in payload:
        falloff = str(payload["falloff"]).upper()
        if falloff not in PROPORTIONAL_FALLOFFS:
            raise BadPayload("Unknown proportional falloff")
        settings.proportional_edit_falloff = falloff
    if "radius" in payload:
        try:
            radius = float(payload["radius"])
        except (TypeError, ValueError):
            raise BadPayload("'radius' must be a number")
        if radius <= 0.0:
            raise BadPayload("'radius' must be greater than zero")
        settings.proportional_size = radius
    if "auto_merge" in payload:
        settings.use_mesh_automerge = bool(payload["auto_merge"])
    if "merge_threshold" in payload:
        try:
            threshold = float(payload["merge_threshold"])
        except (TypeError, ValueError):
            raise BadPayload("'merge_threshold' must be a number")
        if threshold <= 0.0:
            raise BadPayload("'merge_threshold' must be greater than zero")
        settings.double_threshold = threshold
    return dict(state.snapshot(include_view=False), edit_settings=edit_settings_state())
