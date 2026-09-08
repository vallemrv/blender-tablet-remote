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

# Mover cuenta escalones, no distancias: cruzar la pantalla entera avanza estos pasos,
# sea cual sea el zoom. Rotar y Escalar ya se comportaban así (su sensibilidad es fija);
# Mover era el único que seguía al dedo 1:1 como el paneo, y por eso la misma pizca de
# dedo valía micras o metros según lo cerca que estuviera la cámara. Con 100, un paso
# cae cada 1 % de pantalla: fino para el lápiz y todavía cómodo para el dedo.
# Con snap, cruzar la pantalla recorre cuarenta incrementos. Un paso cada 2,5 % de
# pantalla deja una zona táctil perceptible antes del siguiente salto; con 100 el
# redondeo era correcto matemáticamente pero se sentía casi igual al movimiento libre.
MOVE_SNAP_STEPS_PER_SCREEN = 40.0

MIN_SCALE = 1e-4
PROPORTIONAL_FALLOFFS = {"SMOOTH", "SPHERE", "ROOT", "SHARP", "LINEAR", "CONSTANT", "INVERSE_SQUARE"}

MOTIONS = ("FREE", "SLIDE")
# Fracción de la longitud media de los rieles que hay que arrastrar antes de fijar
# cuál es. Es relativo a la malla a propósito: un umbral en metros elegiría rieles al
# azar en una pieza de milímetros y no llegaría a fijarlos nunca en una de kilómetros.
SLIDE_RAIL_FRACTION = 0.02
# Sin clamp el riel extrapola, pero acotado: si no, un arrastre largo manda el vértice
# al infinito y la malla desaparece del viewport.
SLIDE_FREE_RANGE = (-1.0, 2.0)


def _move_base_to_visible(point: Vector, orientation_basis: Matrix,
                          values: Vector) -> Vector:
    """Proyecta un punto persistente del baseline al preview MOVE visible."""
    return point + orientation_basis @ values


def _move_visible_to_base(point: Vector, orientation_basis: Matrix,
                          values: Vector) -> Vector:
    """Convierte un punto sondeado en el preview al baseline de la sesión."""
    return point - orientation_basis @ values


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
        self.snap_to_selection = False
        self.snap_candidate = None
        self.snap_locked = False
        self.reference_candidate = None
        self.reference_candidate_role = None
        self.reference_candidate_locked = False
        self.reference_locked = False
        self.reference_position = None
        self.center_position = None
        self.center_mode = "SELECTION"
        self.source_position = None
        self.reference_role = None
        self.step = DEFAULT_STEP["MOVE"]
        self.scale_step_unit = "FACTOR"
        self.scale_exact = False
        # Sentido según el modo: metros, radianes o factor.
        self.values = Vector((0.0, 0.0, 0.0))
        self.rotation_axis = Vector((0.0, 0.0, 1.0))
        self.orientation_basis = Matrix.Identity(3)
        self.originals: list[tuple[object, Matrix]] = []
        self.pivot = Vector((0.0, 0.0, 0.0))
        self.base_dimensions = Vector((0.0, 0.0, 0.0))
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
        # Deslizamiento por aristas (el GG de Blender). `slide_candidates` son las
        # aristas que puede recorrer cada vértice; `slide_rails` es la elegida, que se
        # fija en el primer arrastre significativo y ya no cambia durante el gesto.
        self.motion = "FREE"
        self.slide_clamp = True
        self.slide_candidates = None
        self.slide_rails = None
        self.slide_factor = None
        self.slide_epsilon = 0.0
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
              proportional=None, proportional_radius=None, proportional_falloff=None,
              motion="FREE", slide_clamp=True, scale_step_unit="FACTOR") -> None:
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
        self.motion = motion
        self.slide_clamp = bool(slide_clamp)
        self.step = DEFAULT_STEP[mode] if step is None else step
        self.scale_step_unit = scale_step_unit
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
            if mode == "MOVE" and self.motion == "SLIDE":
                self._collect_slide_candidates(selected, selected_indices)
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
        self.base_dimensions = self._measure_base_dimensions()

    # ------------------------------------------------------- deslizar por aristas

    def _collect_slide_candidates(self, selected, selected_indices) -> None:
        """Aristas por las que puede correr cada vértice seleccionado (locales).

        Se prefieren las que salen de la selección: en una arista seleccionada, sus dos
        vértices deslizan por las aristas transversales (el edge slide de Blender) en
        vez de colapsar uno sobre otro por la arista que comparten. Un vértice que solo
        toca aristas seleccionadas conserva todas como candidatas para no quedarse
        inmóvil.
        """
        candidates = {}
        lengths = []
        for vert in selected:
            outgoing, every = [], []
            for edge in vert.link_edges:
                other = edge.other_vert(vert)
                if other is None or other.hide:
                    continue
                rail = other.co - vert.co
                if rail.length < 1e-9:
                    continue
                every.append(rail)
                if other.index not in selected_indices:
                    outgoing.append(rail)
            rails = outgoing or every
            if rails:
                candidates[vert.index] = rails
                lengths.extend((self.edit_world.to_3x3() @ rail).length for rail in rails)
        self.slide_candidates = candidates
        average = sum(lengths) / len(lengths) if lengths else 0.0
        self.slide_epsilon = average * SLIDE_RAIL_FRACTION

    def _view_direction(self) -> Vector | None:
        """Eje de visión, o None sin ventana (tests headless)."""
        try:
            camera.sync_from_region(require_rv3d())
        except CommandError:
            return None
        return (camera.rotation @ Vector((0.0, 0.0, 1.0))).normalized()

    def _projected_rail(self, rail: Vector, view: Vector | None) -> Vector:
        """El riel tal y como se ve: sin su componente hacia la cámara.

        Comparar en el mundo elegiría siempre la arista más larga aunque en pantalla
        apenas se mueva, que es justo la que el dedo no está señalando.
        """
        world_rail = self.edit_world.to_3x3() @ rail
        if view is None:
            return world_rail
        return world_rail - view * world_rail.dot(view)

    def _resolve_slide_rails(self, delta_world: Vector) -> None:
        """Fija el riel de cada vértice con la primera dirección real del arrastre.

        El signo cuenta: entre dos aristas colineales opuestas gana la que apunta hacia
        el dedo. Puntuar por alineación absoluta elegía a veces la contraria, y con
        clamp el factor se recortaba a cero y el vértice no se movía nunca.
        """
        view = self._view_direction()
        direction = delta_world.normalized()
        rails = {}
        for index, candidates in self.slide_candidates.items():
            best, best_score = None, None
            for rail in candidates:
                projected = self._projected_rail(rail, view)
                if projected.length < 1e-9:
                    continue
                score = projected.dot(direction) / projected.length
                if best_score is None or score > best_score:
                    best, best_score = rail, score
            if best is not None:
                rails[index] = best
        self.slide_rails = rails

    def _slide_offsets(self, delta_world: Vector) -> dict[int, Vector]:
        """Desplazamiento local de cada vértice sobre su riel, siguiendo al dedo."""
        view = self._view_direction()
        offsets, factors = {}, []
        low, high = (0.0, 1.0) if self.slide_clamp else SLIDE_FREE_RANGE
        for index, rail in self.slide_rails.items():
            projected = self._projected_rail(rail, view)
            denominator = projected.length_squared
            if denominator < 1e-12:
                continue
            factor = projected.dot(delta_world) / denominator
            # Con SLIDE el incremento es fracción del riel, no metros: cuadrarlo aquí
            # deja el vértice en la mitad o el cuarto exactos de la arista.
            if self.snap and self.snap_type == "INCREMENT" and self.step > 0:
                factor = round(factor / self.step) * self.step
            factor = min(high, max(low, factor))
            offsets[index] = rail * factor
            factors.append(factor)
        self.slide_factor = sum(factors) / len(factors) if factors else None
        return offsets

    def _measure_base_dimensions(self) -> Vector:
        """Caja de la selección en la orientación congelada de la sesión."""
        points = []
        if self.edit_object is not None:
            for index in self.selection_signature:
                co = self.edit_coords.get(index)
                if co is not None:
                    points.append(self.edit_world @ co)
        else:
            for obj, matrix in self.originals:
                points.extend(matrix @ Vector(corner) for corner in obj.bound_box)
        if not points:
            return Vector((0.0, 0.0, 0.0))
        inverse = self.orientation_basis.inverted()
        oriented = [inverse @ (point - self.pivot) for point in points]
        return Vector(
            max(point[index] for point in oriented) - min(point[index] for point in oriented)
            for index in range(3)
        )

    def center_base(self) -> Vector:
        return self.center_position.copy() if self.center_position is not None else self.pivot.copy()

    def source_base(self) -> Vector:
        if self.mode == "MOVE":
            point = self.source_position if self.source_position is not None else self.reference_position
            return (point if point is not None else self.pivot).copy()
        return self.source_position.copy() if self.source_position is not None else self.pivot.copy()

    def _transform_point(self, point: Vector, values: Vector) -> Vector:
        if self.mode == "MOVE":
            return _move_base_to_visible(point, self.orientation_basis, values)
        center = self.center_base()
        if self.mode == "ROTATE":
            return center + Matrix.Rotation(
                self._rotation_angle(values), 3, self.rotation_axis) @ (point - center)
        linear = self.orientation_basis @ Matrix.Diagonal(values) @ self.orientation_basis.inverted()
        return center + linear @ (point - center)

    def _untransform_point(self, point: Vector, values: Vector) -> Vector:
        if self.mode == "MOVE":
            return _move_visible_to_base(point, self.orientation_basis, values)
        center = self.center_base()
        if self.mode == "ROTATE":
            return center + Matrix.Rotation(
                -self._rotation_angle(values), 3, self.rotation_axis) @ (point - center)
        linear = self.orientation_basis @ Matrix.Diagonal(values) @ self.orientation_basis.inverted()
        if abs(linear.determinant()) < 1e-12:
            raise CommandError("Scale reference is degenerate", code="degenerate_reference")
        return center + linear.inverted() @ (point - center)

    def solve_target(self, target: Vector) -> None:
        """Resuelve source→target sin acumular sobre el preview actual."""
        center = self.center_base()
        source = self.source_base()
        if self.mode == "MOVE":
            self.values = self.orientation_basis.inverted() @ (target - source)
            return
        source_vector = source - center
        target_vector = target - center
        if self.mode == "ROTATE":
            axis = self.rotation_axis.normalized()
            source_plane = source_vector - axis * source_vector.dot(axis)
            target_plane = target_vector - axis * target_vector.dot(axis)
            if source_plane.length < 1e-8 or target_plane.length < 1e-8:
                raise CommandError("Rotation reference is degenerate", code="degenerate_reference")
            source_plane.normalize()
            target_plane.normalize()
            angle = math.atan2(axis.dot(source_plane.cross(target_plane)),
                               source_plane.dot(target_plane))
            self.values = Vector((0.0, 0.0, 0.0))
            self.values[self._rotation_value_index()] = angle
            return
        basis_inv = self.orientation_basis.inverted()
        source_oriented = basis_inv @ source_vector
        target_oriented = basis_inv @ target_vector
        active = [AXIS_INDEX[name] for name in self.axes] if self.axes else [0, 1, 2]
        if len(active) == 1:
            index = active[0]
            denominator = abs(source_oriented[index])
            numerator = abs(target_oriented[index])
        else:
            denominator = Vector(source_oriented[i] if i in active else 0.0 for i in range(3)).length
            numerator = Vector(target_oriented[i] if i in active else 0.0 for i in range(3)).length
        if denominator < 1e-8:
            raise CommandError("Scale reference is degenerate", code="degenerate_reference")
        factor = max(MIN_SCALE, numerator / denominator)
        self.values = Vector(factor if i in active else 1.0 for i in range(3))

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
            self.values += self.orientation_basis.inverted() @ self._move_delta(dx, dy)
        elif self.mode == "ROTATE":
            self.values[self._rotation_value_index()] -= dx * ROTATE_SENSITIVITY
        else:
            self.scale_exact = False
            factor = 1.0 + dx * SCALE_SENSITIVITY
            self.values = Vector(max(MIN_SCALE, v * factor) for v in self.values)

    def _move_delta(self, dx: float, dy: float) -> Vector:
        """Arrastre de Mover, medido en pasos en vez de en distancia de pantalla.

        La cámara sigue decidiendo la DIRECCIÓN (el dedo empuja hacia donde se ve),
        pero la MAGNITUD sale del incremento: arrastrar 1/MOVE_STEPS_PER_SCREEN de
        pantalla avanza exactamente un paso, con la cámara cerca o lejos. Así el gesto
        es un contador de pasos y el resultado deja de depender del zoom.

        Sin snap el objeto sigue al dedo de forma continua. Solo Incremento convierte
        el gesto en pasos; deslizando por aristas el incremento ya es una fracción del
        riel y se resuelve en `_slide_offsets`.
        """
        world = self._screen_to_world(dx, dy)
        if (not self.snap or self.snap_type != "INCREMENT" or not self.step
                or self.step <= 0.0 or self.slide_candidates is not None):
            return world
        length = world.length
        if length <= 1e-12:
            return world
        steps = math.hypot(dx, dy) * MOVE_SNAP_STEPS_PER_SCREEN
        return world * (steps * self.step / length)

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
        self.values = Vector((float(values[0]), float(values[1]), float(values[2])))
        if self.mode == "SCALE":
            self.scale_exact = True

    def _rotation_value_index(self) -> int:
        """Componente canónica del giro escalar compatible con el contrato v2."""
        return AXIS_INDEX[self.axes[0]] if self.axes else 2

    def _rotation_angle(self, values: Vector) -> float:
        return float(values[self._rotation_value_index()])

    # --------------------------------------------------------------- aplicar

    def _effective(self) -> Vector:
        """Delta ya filtrado por ejes y cuadrado al incremento."""
        values = self.values.copy()

        if self.mode == "MOVE":
            # Con SLIDE el incremento cuadra la fracción del riel (en _slide_offsets),
            # no el delta en metros: cuadrar aquí además desalinearía las dos rejillas.
            if (self.snap and self.step > 0 and self.snap_type == "INCREMENT"
                    and self.slide_candidates is None):
                # Se cuantizan las coordenadas que edita el usuario. Con REL esto
                # hace que 0, ±paso... nazcan exactamente en la referencia.
                values = Vector(round(v / self.step) * self.step for v in values)
            if self.axes:
                for name, index in AXIS_INDEX.items():
                    if name not in self.axes:
                        values[index] = 0.0
        elif self.mode == "SCALE":
            indices = [AXIS_INDEX[name] for name in self.axes] if self.axes else list(range(3))
            if (not self.scale_exact and self.snap
                    and self.snap_type in {"INCREMENT", "GRID"} and self.step > 0):
                step = self.step
                if self.scale_step_unit == "LENGTH":
                    # Un factor común conserva proporciones. Con restricción usa
                    # ese eje; libre/plano mide el incremento en la dimensión mayor.
                    baseline = max(self.base_dimensions[index] for index in indices)
                    step = self.step / baseline if baseline > 1e-12 else 0.0
                if step > 0.0:
                    for index in indices:
                        values[index] = max(MIN_SCALE, 1.0 + round((values[index] - 1.0) / step) * step)
            if self.axes:
                for name, index in AXIS_INDEX.items():
                    if name not in self.axes:
                        values[index] = 1.0
        else:
            if self.snap and self.snap_type in {"INCREMENT", "GRID"} and self.step > 0:
                index = self._rotation_value_index()
                values[index] = round(values[index] / self.step) * self.step

        return values

    def apply(self) -> None:
        """Reconstruye desde las matrices originales. Idempotente a propósito."""
        values = self._effective()
        if self.edit_object is not None:
            self._apply_edit(values)
            return
        for obj, original in self.originals:
            if self.mode == "MOVE":
                obj.matrix_world = Matrix.Translation(self.orientation_basis @ values) @ original
            elif self.mode == "ROTATE":
                angle = self._rotation_angle(values)
                rotation = Matrix.Rotation(angle, 4, self.rotation_axis)
                obj.matrix_world = (
                    Matrix.Translation(self.center_base())
                    @ rotation
                    @ Matrix.Translation(-self.center_base())
                    @ original
                )
            else:
                oriented_scale = self.orientation_basis @ Matrix.Diagonal(values) @ self.orientation_basis.inverted()
                scale = oriented_scale.to_4x4()
                obj.matrix_world = (
                    Matrix.Translation(self.center_base())
                    @ scale
                    @ Matrix.Translation(-self.center_base())
                    @ original
                )

    def _apply_edit(self, values: Vector) -> None:
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

        if self.mode == "MOVE" and self.slide_candidates is not None:
            delta_world = self.orientation_basis @ values
            if self.slide_rails is None and delta_world.length >= self.slide_epsilon > 0.0:
                self._resolve_slide_rails(delta_world)
            offsets = self._slide_offsets(delta_world) if self.slide_rails is not None else {}
            for index, original_local in self.edit_coords.items():
                offset = offsets.get(index)
                verts[index].co = original_local if offset is None else original_local + offset
        elif self.mode == "MOVE":
            # co' = W⁻¹·(W·co + delta_mundo) = co + W⁻¹·delta_mundo
            delta_local = world_inv @ (self.orientation_basis @ values)
            for index, original_local in self.edit_coords.items():
                verts[index].co = original_local + delta_local * self.edit_weights.get(index, 1.0)
        else:
            if self.mode == "ROTATE":
                angle = self._rotation_angle(values)
                linear = Matrix.Rotation(angle, 3, self.rotation_axis)
            else:
                linear = self.orientation_basis @ Matrix.Diagonal(values) @ self.orientation_basis.inverted()
            pivot_local = world_inv @ self.center_base()
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
        values = self._effective()
        proportional_circle = None
        if self.proportional and self.edit_object is not None:
            try:
                rv3d = require_rv3d()
                camera.sync_from_region(rv3d)
                center = self._transform_point(self.center_base(), values)
                right = camera.rotation @ Vector((1.0, 0.0, 0.0))
                center_screen = camera.project(center, rv3d)
                edge_screen = camera.project(center + right * self.proportional_radius, rv3d)
                if center_screen is not None and edge_screen is not None:
                    proportional_circle = {
                        "center": list(center_screen),
                        "radius": math.hypot(edge_screen[0] - center_screen[0],
                                             edge_screen[1] - center_screen[1]),
                    }
            except (CommandError, ReferenceError, RuntimeError):
                pass
        snap_candidate = self.snap_candidate
        if snap_candidate is not None:
            snap_candidate = dict(snap_candidate)
            try:
                rv3d = require_rv3d()
                camera.sync_from_region(rv3d)
                projected = camera.project(Vector(snap_candidate["position"]), rv3d)
                snap_candidate["screen"] = list(projected) if projected is not None else []
            except (CommandError, KeyError, ReferenceError, RuntimeError, TypeError):
                snap_candidate["screen"] = []
        reference_candidate = self.reference_candidate
        source_position = (self.source_position if self.source_position is not None
                           else self.reference_position)
        reference_position = (source_position if self.reference_role == "SOURCE"
                              else self.center_position)
        if self.reference_locked and reference_position is not None:
            current_reference = (self._transform_point(reference_position, values)
                                 if self.reference_role == "SOURCE"
                                 else reference_position.copy())
            reference_position = current_reference
            if reference_candidate is not None and self.reference_candidate_locked:
                candidate_position = (source_position if self.reference_candidate_role == "SOURCE"
                                      else self.center_position)
                current_candidate = (self._transform_point(candidate_position, values)
                                     if self.reference_candidate_role == "SOURCE"
                                     else candidate_position.copy())
                reference_candidate = dict(reference_candidate, position=list(current_candidate))
                try:
                    rv3d = require_rv3d()
                    camera.sync_from_region(rv3d)
                    projected = camera.project(current_candidate, rv3d)
                    reference_candidate["screen"] = list(projected) if projected is not None else []
                except (CommandError, ReferenceError, RuntimeError, TypeError):
                    reference_candidate["screen"] = []
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
            "snap_to_selection": self.snap_to_selection,
            "snap_candidate": snap_candidate,
            "snap_locked": self.snap_locked,
            "reference_candidate": reference_candidate,
            "reference_locked": (self.reference_candidate_locked
                                 if reference_candidate is not None else self.reference_locked),
            "reference_position": list(reference_position) if reference_position is not None else None,
            "reference_distance": (source_position - self.center_base()).length
                if source_position is not None else None,
            "reference_role": self.reference_candidate_role or self.reference_role,
            "center_locked": self.center_position is not None,
            "center_mode": self.center_mode,
            "source_locked": source_position is not None,
            "center": list(self.center_base()),
            "source": list(self._transform_point(source_position, values))
                if source_position is not None else None,
            "target": list(snap_candidate["position"])
                if snap_candidate is not None else None,
            "motion": self.motion,
            "slide_clamp": self.slide_clamp,
            "slide_factor": self.slide_factor,
            "step": self.step,
            "scale_step_unit": self.scale_step_unit,
            "base_dimensions": list(self.base_dimensions),
            "dimensions": list(Vector(
                abs(self.base_dimensions[index] * values[index])
                if self.mode == "SCALE" else self.base_dimensions[index]
                for index in range(3)
            )),
            "proportional": self.proportional,
            "proportional_radius": self.proportional_radius,
            "proportional_falloff": self.proportional_falloff,
            "proportional_circle": proportional_circle,
            "objects": [o.name for o, _m in self.originals] or ([self.edit_object.name] if self.edit_object else []),
            # Lo que la barra enseña mientras se arrastra. La rotación va en grados
            # porque es lo que se lee, no radianes.
            "values": list(values),
            # `mathutils.Vector` almacena float32; redondear la presentación evita
            # ruido como 45.000001° sin crear otra fuente interna de verdad.
            "angle": round(math.degrees(self._rotation_angle(values)), 6)
                if self.mode == "ROTATE" else 0.0,
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


def _parse_scale_step_unit(payload: dict, default="FACTOR") -> str:
    unit = str(payload.get("scale_step_unit", default)).upper()
    if unit not in {"FACTOR", "LENGTH"}:
        raise BadPayload("'scale_step_unit' must be FACTOR or LENGTH")
    return unit


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
    if snap_type not in {"NONE", "INCREMENT", "VERTEX", "EDGE", "EDGE_CENTER", "FACE", "FACE_CENTER"}:
        raise BadPayload("Unknown 'snap_type'")
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

    scale_step_unit = _parse_scale_step_unit(payload)

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
                  proportional_falloff, scale_step_unit=scale_step_unit)
    session.apply()
    return session.status()


@command("transform.axes", mutating=True)
def set_axes(payload: dict) -> dict:
    """Cambia la restricción de ejes con la transformación viva."""
    session.require(payload.get("_client_id"))
    angle = session._rotation_angle(session.values) if session.mode == "ROTATE" else None
    session.axes = _parse_axes(payload)
    if session.mode == "ROTATE":
        session.values = Vector((0.0, 0.0, 0.0))
        session.values[session._rotation_value_index()] = angle
        session.rotation_axis = session._resolve_rotation_axis()
    session.apply()
    return session.status()


@command("transform.orientation", mutating=True)
def set_orientation(payload: dict) -> dict:
    """Cambia la base sin reiniciar session_id ni perder referencias fijadas."""
    session.require(payload.get("_client_id"))
    orientation = str(payload.get("orientation", "")).upper()
    allowed = {"GLOBAL", "LOCAL", "VIEW"} | ({"NORMAL"} if session.edit_object else set())
    if orientation not in allowed:
        raise BadPayload("Unknown 'orientation'")
    session.orientation = orientation
    session.orientation_basis = session._resolve_orientation_basis()
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
        if snap_type not in {"NONE", "INCREMENT", "VERTEX", "EDGE", "EDGE_CENTER", "FACE", "FACE_CENTER"}:
            raise BadPayload("Unknown 'snap_type'")
        session.snap_type = snap_type
    if "snap_to_selection" in payload:
        snap_to_selection = bool(payload["snap_to_selection"])
        if snap_to_selection != session.snap_to_selection:
            session.snap_candidate = None
            session.snap_locked = False
        session.snap_to_selection = snap_to_selection
    step = _parse_step(payload, session.step)
    session.scale_step_unit = _parse_scale_step_unit(payload, session.scale_step_unit)
    session.step = step
    session.apply()
    return session.status()


@command("transform.snap_candidate", mutating=True)
def set_snap_candidate(payload: dict) -> dict:
    """Busca y bloquea el candidato geométrico que se previsualiza bajo el dedo."""
    session.require(payload.get("_client_id"))
    if session.mode in {"ROTATE", "SCALE"} and session.source_position is None:
        raise CommandError("Pick a source before the target", code="missing_source")
    from .snap import query_candidate
    query_payload = dict(payload)
    query_payload["snap_type"] = payload.get("snap_type", session.snap_type)
    if not session.snap_to_selection:
        if session.originals:
            query_payload["exclude_objects"] = [o.name for o, _matrix in session.originals]
        elif session.edit_object is not None:
            query_payload["exclude_elements"] = {
                session.edit_object.name: {"vertices": list(session.edit_coords)}
            }
    candidate = query_candidate(query_payload, session.snap_candidate)
    if not candidate.get("hit"):
        session.snap_candidate = None
        session.snap_locked = False
        return dict(session.status(), candidate=candidate)
    session.solve_target(Vector(candidate["position"]))
    session.snap_type = candidate["snap_type"]
    session.snap = True
    session.snap_candidate = candidate
    session.snap_locked = bool(payload.get("lock", True))
    session.apply()
    return session.status()


@command("transform.reference_candidate", mutating=True)
def set_reference_candidate(payload: dict) -> dict:
    """Sondea center/source sobre la selección sin alterar el preview al apoyar."""
    session.require(payload.get("_client_id"))
    default_role = "SOURCE" if session.mode == "MOVE" else "CENTER"
    role = str(payload.get("role", default_role)).upper()
    if role not in {"CENTER", "SOURCE"}:
        raise BadPayload("'role' must be CENTER or SOURCE")
    if session.mode == "MOVE" and role == "CENTER":
        raise CommandError("MOVE uses a source reference", code="wrong_reference_role")
    preset = str(payload.get("preset", "")).upper()
    if preset:
        if role != "CENTER" or session.mode not in {"ROTATE", "SCALE"}:
            raise CommandError("Center presets require ROTATE or SCALE", code="wrong_reference_role")
        if preset == "SELECTION":
            session.center_position = None
        elif preset == "OBJECT_ORIGIN":
            active = bpy.context.view_layer.objects.active
            if active is None:
                raise CommandError("No active object", code="empty_selection")
            session.center_position = active.matrix_world.translation.copy()
        elif preset == "CURSOR":
            session.center_position = bpy.context.scene.cursor.location.copy()
        else:
            raise BadPayload("'preset' must be SELECTION, OBJECT_ORIGIN or CURSOR")
        session.center_mode = preset
        session.reference_candidate = None
        session.reference_candidate_role = None
        session.reference_candidate_locked = False
        session.reference_locked = session.center_position is not None or session.source_position is not None
        session.reference_role = "CENTER" if session.center_position is not None else (
            "SOURCE" if session.source_position is not None else None)
        session.apply()
        return session.status()
    if payload.get("clear"):
        session.reference_candidate = None
        session.reference_candidate_role = None
        session.reference_candidate_locked = False
        session.reference_locked = False
        if role == "CENTER":
            session.center_position = None
            session.center_mode = "SELECTION"
            session.reference_role = "SOURCE" if session.source_position is not None else None
        else:
            session.source_position = None
            session.reference_position = None
            session.reference_role = "CENTER" if session.center_position is not None else None
        session.reference_locked = session.reference_role is not None
        session.apply()
        return session.status()
    lock = bool(payload.get("lock", False))
    def lock_candidate(candidate):
        # El raycast observa la geometría ya transformada. La sesión, en cambio,
        # reconstruye siempre desde las matrices originales: guardar directamente
        # esta posición sumaría otra vez cualquier movimiento previo. Conservamos la
        # posición base para que status() le aplique el delta exactamente una vez.
        values = session._effective()
        current_position = Vector(candidate["position"])
        if role == "CENTER":
            # El centro deja de ser un punto móvil en cuanto se convierte en pivote:
            # la rotación siguiente ocurre *alrededor* de él. Desrotarlo hacia el
            # baseline, como se hace con una fuente ligada a la selección, desplazaba
            # el marcador rojo respecto del último verde tras una primera rotación no
            # confirmada. El candidato visible es aquí la referencia canónica.
            session.center_position = current_position
            session.center_mode = "PICKED"
        else:
            base_position = session._untransform_point(current_position, values)
            session.source_position = base_position
            if session.mode == "MOVE":
                session.reference_position = base_position
        session.reference_locked = True
        session.reference_role = role
        session.reference_candidate_locked = True

    # END congela exactamente el marcador verde que el usuario estaba viendo. Un
    # segundo raycast con el jitter de ACTION_UP puede elegir otra categoría exacta.
    if (lock and session.reference_candidate is not None
            and session.reference_candidate_role == role):
        lock_candidate(session.reference_candidate)
        return session.status()
    from .snap import query_reference_candidate
    query_payload = dict(payload)
    if session.originals:
        query_payload["include_objects"] = [o.name for o, _matrix in session.originals]
    elif session.edit_object is not None:
        query_payload["include_objects"] = [session.edit_object.name]
    previous = (session.reference_candidate
                if session.reference_candidate_role == role else None)
    candidate = query_reference_candidate(query_payload, previous)
    session.reference_candidate = candidate if candidate.get("hit") else None
    session.reference_candidate_role = role if candidate.get("hit") else None
    session.reference_candidate_locked = bool(candidate.get("hit") and lock)
    if candidate.get("hit") and lock:
        lock_candidate(candidate)
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
    if "flatten_axis" in payload:
        axis = str(payload["flatten_axis"]).upper()
        if session.mode != "SCALE" or axis not in AXIS_INDEX:
            raise BadPayload("flatten_axis requires SCALE and X, Y or Z")
        values = session._effective()
        values[AXIS_INDEX[axis]] = 0.0
        # Una única operación: conserva lo visible en los otros ejes y elimina
        # cualquier restricción que pudiera ignorar el eje solicitado.
        session.axes = []
        session.set_values(values)
        session.apply()
        return session.status()
    if session.mode == "ROTATE":
        try:
            if "values" in payload:
                raw = payload["values"]
                if not isinstance(raw, (list, tuple)) or len(raw) != 3:
                    raise BadPayload("'values' must be [x, y, z]")
                values = Vector(float(value) for value in raw)
            elif "angle" in payload:
                values = session.values.copy()
                values[session._rotation_value_index()] = math.radians(float(payload["angle"]))
            else:
                raise BadPayload("'values' or 'angle' is required when rotating")
            session.set_values(values)
        except (TypeError, ValueError):
            raise BadPayload("rotation values must contain numbers")
    else:
        if session.mode == "SCALE" and "dimensions" in payload:
            dimensions = payload.get("dimensions")
            if not isinstance(dimensions, (list, tuple)) or len(dimensions) != 3:
                raise BadPayload("'dimensions' must be [x, y, z]")
            try:
                factors = []
                for index, dimension in enumerate(dimensions):
                    target = float(dimension)
                    baseline = session.base_dimensions[index]
                    if not math.isfinite(target) or target < 0.0:
                        raise BadPayload("dimensions must be finite and non-negative")
                    if target == 0.0:
                        factors.append(0.0)
                        continue
                    if baseline <= 1e-12:
                        raise CommandError("Scale dimension is degenerate", code="degenerate_reference")
                    factors.append(target / baseline)
                session.set_values(factors)
            except (TypeError, ValueError):
                raise BadPayload("dimensions must contain numbers")
            session.apply()
            return session.status()
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
