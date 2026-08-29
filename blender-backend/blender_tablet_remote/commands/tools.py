"""Herramientas paramétricas de Edit Mode con preview reversible."""

from __future__ import annotations

import uuid

import bmesh
import bpy
from mathutils import Vector

from ..bpy_utils import active_object, find_view3d, undo_push
from ..camera import camera
from ..errors import BadPayload, CommandError
from . import command
from . import knife as knife_commands
from . import mesh as mesh_commands

SUPPORTED = {"EXTRUDE", "BEVEL", "INSET", "SUBDIVIDE", "LOOP_CUT", "BRIDGE_EDGE_LOOPS", "KNIFE", "BISECT"}

# Herramientas cuya sesión puede quedar ARMED (elegidas pero sin backup ni preview
# todavía) porque su primer dato lo da un toque/arrastre en el viewport, no la
# selección ya hecha. El resto empieza ACTIVE de inmediato, como siempre.
VIEWPORT_ARMED = {"LOOP_CUT", "BISECT"}

SNAP_THRESHOLD = 0.045


class ToolSession:
    def __init__(self):
        self.reset()

    def reset(self):
        self.active = False
        self.session_id = None
        self.owner_id = None
        self.tool = None
        self.params = {}
        self.obj = None
        self.backup = None
        self.original_backup = None
        self.loop_history = []  # [(base anterior, parámetros del corte anterior)]
        self.result = None
        self.points = []  # anclas del Knife, en coordenadas locales
        self.knife_start = None
        self.closed = False
        self.line = None  # {"start": [u, v], "end": [u, v]} de la sesión Bisect
        self.snap_candidate = None
        # Armado: familia/variante elegida, aún sin backup ni preview (B1/B3/B4).
        self.armed_tool = None
        self.armed_owner = None
        self.armed_params = {}

    def arm(self, tool, owner, params):
        """Marca la herramienta como elegida, a la espera de un toque en el viewport."""
        self.armed_tool, self.armed_owner, self.armed_params = tool, owner, dict(params)

    def disarm(self):
        self.armed_tool, self.armed_owner, self.armed_params = None, None, {}

    def begin(self, tool, owner, params):
        obj = active_object()
        if obj.mode != "EDIT" or obj.type != "MESH":
            raise CommandError("Parametric tools require mesh Edit Mode", code="wrong_mode")
        if self.active:
            self.restore()
            self.close()
        self.disarm()
        self.obj = obj
        bm = bmesh.from_edit_mesh(obj.data)
        if tool == "LOOP_CUT" and "edge" not in params:
            seed = next((edge for edge in bm.edges if edge.select and not edge.hide), None)
            if seed is None:
                # Sin arista de partida, la familia queda armada: el primer
                # `tool.loop_pick` sobre el viewport es quien la activa de verdad.
                self.arm(tool, owner, params)
                return
            params = dict(params, edge=seed.index)
        if tool == "BISECT":
            # Bisect siempre arma: su geometría solo existe tras un arrastre de
            # línea completo (`tool.drag_line`), nunca al elegir la herramienta.
            self.arm(tool, owner, params)
            return
        self._activate(tool, owner, params)

    def _activate(self, tool, owner, params):
        """Crea backup + primera preview. Llamado desde `begin` o al resolver un armado."""
        obj = self.obj
        bm = bmesh.from_edit_mesh(obj.data)
        backup = bpy.data.meshes.new(".remote_tool_backup")
        bm.to_mesh(backup)
        self.active, self.session_id, self.owner_id = True, str(uuid.uuid4()), owner
        self.tool, self.params, self.obj, self.backup = tool, dict(params), obj, backup
        if tool == "LOOP_CUT":
            self.original_backup = backup
        self.points = []
        self.knife_start = None
        self.closed = False
        self.line = None
        try:
            self.preview()
        except Exception:
            self.close()
            raise

    def require(self, owner):
        if not self.active:
            raise CommandError("No tool in progress", code="no_session")
        if owner is not None and self.owner_id is not None and owner != self.owner_id:
            raise CommandError("Tool session belongs to another client", code="session_owned")
        try:
            valid = self.obj.name in bpy.data.objects and self.obj.mode == "EDIT"
        except ReferenceError:
            valid = False
        if not valid:
            self.close()
            raise CommandError("Tool session invalidated", code="session_invalidated")

    def require_armed_owner(self, owner):
        """Como `require`, pero para una herramienta solo armada (sin backup aún)."""
        if not self.armed_tool:
            raise CommandError("No tool in progress", code="no_session")
        if owner is not None and self.armed_owner is not None and owner != self.armed_owner:
            raise CommandError("Tool session belongs to another client", code="session_owned")

    def _restore_mesh(self, source):
        if self.obj is None or source is None or self.obj.mode != "EDIT":
            return
        bm = bmesh.from_edit_mesh(self.obj.data)
        bm.clear()
        bm.from_mesh(source)
        bmesh.update_edit_mesh(self.obj.data, loop_triangles=True, destructive=True)

    def restore(self):
        """Restaura el estado anterior a toda la sesión, también con loops acumulados."""
        self._restore_mesh(self.original_backup or self.backup)

    def restore_preview_base(self):
        """Restaura solo la base del corte activo antes de reconstruir su preview."""
        self._restore_mesh(self.backup)

    def restore_safely(self):
        try:
            self.restore()
            return True
        except (ReferenceError, RuntimeError):
            return False

    def preview(self):
        self.restore_preview_base()
        if self.tool == "KNIFE":
            bm = bmesh.from_edit_mesh(self.obj.data)
            try:
                self.result = knife_commands.cut_polyline(bm, self.points, self.closed)
            except CommandError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise CommandError(f"Knife cut failed: {exc}", code="topology_incompatible") from exc
            bmesh.update_edit_mesh(self.obj.data, loop_triangles=True, destructive=True)
            return
        payload = dict(self.params)
        if str(payload.get("snap_type", "NONE")).upper() in {"VERTEX", "EDGE", "EDGE_CENTER", "FACE", "FACE_CENTER", "CURSOR"}:
            payload["snap_type"] = "NONE"  # aún no hay candidato o ya se resuelve abajo
        if self.tool == "EXTRUDE" and self.snap_candidate is not None:
            if str(payload.get("variant", "REGION")).upper() != "REGION":
                raise CommandError("Geometric snap requires Extrude REGION", code="incompatible_parameter")
            bm = bmesh.from_edit_mesh(self.obj.data)
            selected = [v.co.copy() for v in bm.verts if v.select and not v.hide]
            if not selected:
                raise CommandError("No vertices selected", code="empty_selection")
            source_local = Vector((0.0, 0.0, 0.0))
            for coordinate in selected:
                source_local += coordinate
            source_local /= len(selected)
            source_world = self.obj.matrix_world @ source_local
            target_world = Vector(self.snap_candidate["position"])
            delta_world = target_world - source_world
            payload["direction"] = list((self.obj.matrix_world.inverted().to_3x3() @ delta_world).normalized()) if delta_world.length else [0, 0, 1]
            payload["offset"] = delta_world.length
            payload["snap_type"] = "NONE"  # el destino ya quedó resuelto exactamente
        payload["_no_undo"] = True
        handlers = {"EXTRUDE": mesh_commands.extrude, "BEVEL": mesh_commands.bevel,
                    "INSET": mesh_commands.inset, "SUBDIVIDE": mesh_commands.subdivide,
                    "LOOP_CUT": mesh_commands.loop_cut,
                    "BRIDGE_EDGE_LOOPS": mesh_commands.bridge_edge_loops,
                    "BISECT": mesh_commands.bisect}
        self.result = handlers[self.tool](payload)

    def close(self):
        backups = {mesh for mesh in [self.backup, self.original_backup] if mesh is not None}
        backups.update(base for base, _params in self.loop_history)
        self.reset()
        for backup in backups:
            if backup.name in bpy.data.meshes:
                bpy.data.meshes.remove(backup)

    def status(self):
        if self.active:
            try:
                self.require(None)
            except CommandError as exc:
                if exc.code in {"session_invalidated", "no_session"}:
                    return {"active": False, "armed": False, "phase": "INVALIDATED"}
                raise
            except (ReferenceError, RuntimeError):
                self.close()
                return {"active": False, "armed": False, "phase": "INVALIDATED"}
            state = {"active": True, "armed": True, "phase": "ACTIVE", "session_id": self.session_id,
                     "owner": self.owner_id, "tool": self.tool, "parameters": self.params,
                     "preview": self.result}
            state["snap_type"] = str(self.params.get("snap_type", "NONE")).upper()
            state["snap_step"] = float(self.params.get("snap_step", 0.1))
            state["snap_candidate"] = self.snap_candidate
            if self.tool == "KNIFE":
                state["points"] = [list(p) for p in self.points]
                state["closed"] = self.closed
                found = find_view3d()
                if found is not None:
                    rv3d = found[3]
                    camera.sync_from_region(rv3d)
                    matrix = self.obj.matrix_world
                    state["projected_points"] = [
                        list(screen) for point in self.points
                        if (screen := camera.project(matrix @ Vector(point), rv3d)) is not None
                    ]
            if self.tool == "BISECT":
                state["line"] = self.line
            if self.tool == "LOOP_CUT":
                state["loop_count"] = len(self.loop_history) + 1
            return state
        if self.armed_tool:
            return {"active": False, "armed": True, "phase": "ARMED", "tool": self.armed_tool,
                    "owner": self.armed_owner, "parameters": self.armed_params}
        return {"active": False, "armed": False, "phase": "IDLE"}

    def owner_disconnected(self, owner):
        if self.active and self.owner_id == owner:
            self.restore()
            self.close()
        elif self.armed_tool and self.armed_owner == owner:
            self.disarm()


tool_session = ToolSession()


@command("tool.begin", mutating=True)
def begin(payload):
    tool = str(payload.get("tool", "")).upper()
    if tool not in SUPPORTED:
        raise BadPayload(f"'tool' must be one of {', '.join(sorted(SUPPORTED))}")
    params = payload.get("parameters", {})
    if not isinstance(params, dict):
        raise BadPayload("'parameters' must be an object")
    params = dict(params)
    if "edge" in payload and "edge" not in params:
        params["edge"] = payload["edge"]
    from .sessions import cancel_transform
    cancel_transform(restore=True)
    tool_session.begin(tool, payload.get("_client_id"), params)
    return tool_session.status()


@command("tool.parameter", mutating=True)
def parameter(payload):
    owner = payload.get("_client_id")
    if not tool_session.active and tool_session.armed_tool:
        tool_session.require_armed_owner(owner)
        params = payload.get("parameters", payload.get("parameter"))
        if not isinstance(params, dict):
            raise BadPayload("'parameters' must be an object")
        tool_session.armed_params.update(params)
        return tool_session.status()
    tool_session.require(owner)
    if tool_session.tool == "KNIFE":
        # Solo el snap es un parámetro real de Knife; el resto son puntos.
        params = payload.get("parameters", payload.get("parameter"))
        if not isinstance(params, dict):
            raise BadPayload("'parameters' must be an object")
        for key, value in params.items():
            if key != "snap":
                raise BadPayload(f"Knife parameter '{key}' not supported")
            tool_session.params["snap"] = bool(value)
        return tool_session.status()
    params = payload.get("parameters", payload.get("parameter"))
    if not isinstance(params, dict):
        raise BadPayload("'parameters' must be an object")
    tool_session.params.update(params)
    if str(tool_session.params.get("snap_type", "NONE")).upper() not in {"VERTEX", "EDGE", "EDGE_CENTER", "FACE", "FACE_CENTER", "CURSOR"}:
        tool_session.snap_candidate = None
    tool_session.preview()
    return tool_session.status()


@command("tool.snap_candidate", mutating=True)
def snap_candidate(payload):
    """Sondea y opcionalmente bloquea un candidato geométrico para Extrude REGION."""
    tool_session.require(payload.get("_client_id"))
    if tool_session.tool != "EXTRUDE" or str(tool_session.params.get("variant", "REGION")).upper() != "REGION":
        raise CommandError("Geometric snap requires Extrude REGION", code="wrong_tool")
    snap_type = str(payload.get("snap_type", tool_session.params.get("snap_type", "VERTEX"))).upper()
    if snap_type not in {"VERTEX", "EDGE", "EDGE_CENTER", "FACE", "FACE_CENTER", "CURSOR"}:
        raise BadPayload("Unsupported geometric 'snap_type'")
    from .snap import query_candidate
    tool_session.restore()
    query = dict(payload, snap_type=snap_type)
    candidate = query_candidate(query)
    if not candidate.get("hit"):
        tool_session.snap_candidate = None
        tool_session.preview()
        return tool_session.status()
    tool_session.params["snap_type"] = snap_type
    if bool(payload.get("lock", True)):
        tool_session.snap_candidate = candidate
    tool_session.preview()
    return tool_session.status()


@command("tool.drag_line", mutating=True)
def drag_line(payload):
    """Arrastre de línea completo de Bisect: inicio/fin normalizados al soltar.

    Primer arrastre con la herramienta solo armada: crea el backup y activa la
    sesión con el plano resuelto. Arrastres siguientes con la sesión ya activa:
    reconstruyen desde el backup con el plano nuevo, sin acumular cortes.
    """
    owner = payload.get("_client_id")
    tool = tool_session.tool if tool_session.active else tool_session.armed_tool
    if tool != "BISECT":
        raise CommandError("drag_line requires a BISECT tool", code="wrong_tool")
    if tool_session.active:
        tool_session.require(owner)
        params_source = tool_session.params
    else:
        tool_session.require_armed_owner(owner)
        params_source = tool_session.armed_params

    found = find_view3d()
    if found is None:
        raise CommandError("No 3D viewport available", code="no_viewport")
    rv3d = found[3]
    camera.sync_from_region(rv3d)

    start = payload.get("start")
    end = payload.get("end")
    if not isinstance(start, (list, tuple)) or len(start) != 2 or not isinstance(end, (list, tuple)) or len(end) != 2:
        raise BadPayload("'start' and 'end' must be [u, v]")
    start_uv = (float(start[0]), float(start[1]))
    end_uv = (float(end[0]), float(end[1]))
    obj = tool_session.obj or active_object()
    snap_enabled = bool(params_source.get("snap", True))
    plane_co, plane_no = _bisect_plane(obj, rv3d, start_uv, end_uv, snap_enabled)
    line = {"start": list(start_uv), "end": list(end_uv)}

    if tool_session.active:
        tool_session.params.update({"plane_co": list(plane_co), "plane_no": list(plane_no)})
        tool_session.line = line
        tool_session.preview()
        return dict(tool_session.status(), line=line)

    params = dict(tool_session.armed_params, plane_co=list(plane_co), plane_no=list(plane_no))
    owner_id, armed_params = tool_session.armed_owner, tool_session.armed_params
    tool_session.disarm()
    try:
        tool_session._activate("BISECT", owner_id, params)
    except CommandError:
        # Un arrastre que no cruza geometría vuelve a dejar la tool armada, no en
        # IDLE: el usuario solo necesita intentar otra línea, no reelegir Cut.
        tool_session.arm("BISECT", owner_id, armed_params)
        raise
    tool_session.line = line
    return dict(tool_session.status(), line=line)


@command("tool.knife_point", mutating=True)
def knife_point(payload):
    """Sondea (u,v), resuelve un ancla y la añade a la polilínea."""
    tool_session.require(payload.get("_client_id"))
    if tool_session.tool != "KNIFE":
        raise CommandError("knife_point requires a KNIFE session", code="wrong_tool")
    found = find_view3d()
    if found is None:
        raise CommandError("No 3D viewport available", code="no_viewport")
    rv3d = found[3]
    camera.sync_from_region(rv3d)

    u = float(payload.get("u", 0.5))
    v = float(payload.get("v", 0.5))
    origin, direction = camera.ray(u, v, rv3d)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    hit, location, _normal, _face_index, hit_obj, _matrix = bpy.context.scene.ray_cast(
        depsgraph, origin, direction
    )
    if not hit or hit_obj != tool_session.obj:
        return dict(tool_session.status(), hit=False)

    # El ancla es el punto local; el raycast se hace sobre el backup (restaurado), así
    # que las coordenadas y la cara son estables para todas las reproducciones.
    world = Vector(location)
    local = tool_session.obj.matrix_world.inverted() @ world
    snap_class = "NONE"
    if tool_session.params.get("snap", True):
        snap_class, snap_local = _geometry_snap(tool_session.obj, rv3d, u, v)
        if snap_local is not None:
            local = snap_local
    tool_session.points.append(list(local))
    tool_session.preview()
    return dict(tool_session.status(), hit=True, snap=snap_class, point=list(local))


@command("tool.knife_drag", mutating=True)
def knife_drag(payload):
    """Sondea o confirma un tramo de Knife mediante pulsar, arrastrar y soltar."""
    tool_session.require(payload.get("_client_id"))
    if tool_session.tool != "KNIFE":
        raise CommandError("knife_drag requires a KNIFE session", code="wrong_tool")
    phase = str(payload.get("phase", "UPDATE")).upper()
    if phase not in {"BEGIN", "UPDATE", "END", "CANCEL"}:
        raise BadPayload("'phase' must be BEGIN, UPDATE, END or CANCEL")
    if phase == "CANCEL":
        tool_session.knife_start = None
        tool_session.snap_candidate = None
        return tool_session.status()

    candidate = _knife_candidate(tool_session.obj, float(payload.get("u", 0.5)),
                                  float(payload.get("v", 0.5)),
                                  bool(tool_session.params.get("snap", True)))
    tool_session.snap_candidate = candidate if candidate.get("hit") else None
    if phase == "BEGIN":
        # Solo es una referencia transitoria para diagnóstico/cancel. El primer
        # ancla se toma siempre del END, para que también pueda arrastrarse.
        tool_session.knife_start = candidate if candidate.get("hit") else None
    elif phase == "END" and candidate.get("hit"):
        endpoint = list(candidate["local_position"])
        if not tool_session.points or (Vector(endpoint) - Vector(tool_session.points[-1])).length_squared > 1e-12:
            tool_session.points.append(endpoint)
            tool_session.closed = False
            tool_session.preview()
        tool_session.knife_start = None
    return dict(tool_session.status(), hit=bool(candidate.get("hit")), candidate=candidate)


def _knife_candidate(obj, u, v, snap_enabled):
    """Punto visible de cara con snap deliberado solo a sus vértices/aristas."""
    found = find_view3d()
    if found is None:
        raise CommandError("No 3D viewport available", code="no_viewport")
    rv3d = found[3]
    camera.sync_from_region(rv3d)
    origin, direction = camera.ray(u, v, rv3d)
    hit, location, _normal, _face_index, hit_obj, _matrix = bpy.context.scene.ray_cast(
        bpy.context.evaluated_depsgraph_get(), origin, direction)
    if not hit or hit_obj != obj:
        return {"hit": False, "snap_type": "NONE", "screen": [u, v]}
    world = Vector(location)
    local = obj.matrix_world.inverted() @ world
    bm = bmesh.from_edit_mesh(obj.data)
    face = min((f for f in bm.faces if not f.hide),
               key=lambda f: knife_commands._point_face_distance(f, local), default=None)
    snap_type, snapped = "FACE", local
    touch = Vector((u, v))
    if snap_enabled and face is not None:
        ranked = []
        for vert in face.verts:
            screen = camera.project(obj.matrix_world @ vert.co, rv3d)
            if screen is not None:
                distance = (Vector(screen) - touch).length
                if distance <= 0.025:
                    ranked.append((distance, 0, "VERTEX", vert.co.copy(), screen, vert.index))
        for edge in face.edges:
            pa = camera.project(obj.matrix_world @ edge.verts[0].co, rv3d)
            pb = camera.project(obj.matrix_world @ edge.verts[1].co, rv3d)
            if pa is None or pb is None:
                continue
            a2, b2 = Vector(pa), Vector(pb)
            span = b2 - a2
            center_screen = (a2 + b2) * 0.5
            center_distance = (center_screen - touch).length
            if center_distance <= 0.02:
                ranked.append((center_distance, 1, "EDGE_CENTER",
                               (edge.verts[0].co + edge.verts[1].co) * 0.5,
                               center_screen, edge.index))
            t = max(0.0, min(1.0, (touch - a2).dot(span) / span.length_squared)) if span.length_squared > 1e-12 else 0.5
            screen = a2 + span * t
            distance = (screen - touch).length
            if distance <= 0.015:
                ranked.append((distance, 2, "EDGE", edge.verts[0].co.lerp(edge.verts[1].co, t), screen, edge.index))
        if ranked:
            # El punto más cercano de una arista coincide con su centro cuando el
            # toque entra perpendicular, y entonces las dos distancias solo se
            # separan por el ruido del flotante. En ese empate práctico debe ganar
            # el snap más específico (vértice, luego centro), no el que se lleve el
            # epsilon; si algo está de verdad más cerca, sigue ganando por distancia.
            closest = min(item[0] for item in ranked)
            _distance, _priority, snap_type, snapped, _screen, element = min(
                (item for item in ranked if item[0] <= closest + 1e-3),
                key=lambda item: (item[1], item[0]))
        else:
            element = face.index if face is not None else -1
    else:
        element = face.index if face is not None else -1
    snapped_world = obj.matrix_world @ snapped
    screen = camera.project(snapped_world, rv3d) or (u, v)
    return {"hit": True, "snap_type": snap_type, "id": f"{obj.name}:{snap_type}:{element}",
            "object": obj.name, "element": element, "position": list(snapped_world),
            "local_position": list(snapped), "screen": list(screen),
            "distance": float((Vector(screen) - touch).length)}


def _geometry_snap(obj, rv3d, u, v):
    """Candidato de snap más cercano en pantalla: (clase, punto local) o (NONE, None).

    Compartido por Knife y Bisect: ambos son cortes de geometría, no
    transformaciones, así que el snap real es "el punto cae exactamente en el
    vértice/arista", no un cuadrado a incremento.
    """
    matrix = obj.matrix_world
    touch = Vector((u, v))
    bm = bmesh.from_edit_mesh(obj.data)
    best = None
    for vert in bm.verts:
        if vert.hide:
            continue
        projected = camera.project(matrix @ vert.co, rv3d)
        if projected is None:
            continue
        d = (Vector(projected) - touch).length
        if d <= SNAP_THRESHOLD and (best is None or d < best[0]):
            best = (d, "VERTEX", vert.co.copy())
    for edge in bm.edges:
        if edge.hide:
            continue
        pa = camera.project(matrix @ edge.verts[0].co, rv3d)
        pb = camera.project(matrix @ edge.verts[1].co, rv3d)
        if pa is None or pb is None:
            continue
        a2, b2 = Vector(pa), Vector(pb)
        span = b2 - a2
        t = 0.5
        if span.length_squared > 1e-12:
            t = max(0.0, min(1.0, (touch - a2).dot(span) / span.length_squared))
        midpoint = a2 + span * t
        d = (midpoint - touch).length
        if d <= SNAP_THRESHOLD and (best is None or d < best[0]):
            best = (d, "EDGE", edge.verts[0].co.lerp(edge.verts[1].co, t))
    if best is None:
        return "NONE", None
    return best[1], best[2]


def _bisect_endpoint(obj, rv3d, u, v, snap_enabled):
    """Punto de mundo bajo (u, v) para un extremo de Bisect, con snap opcional."""
    origin, direction = camera.ray(u, v, rv3d)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    hit, location, _normal, _face_index, hit_obj, _matrix = bpy.context.scene.ray_cast(
        depsgraph, origin, direction
    )
    if hit and hit_obj == obj:
        point = Vector(location)
    else:
        # Sin impacto sobre la malla: se ancla en el plano paralelo a la pantalla que
        # pasa por el origen del objeto, para que la línea siga siendo previsible en
        # vez de depender de qué otra cosa haya detrás en la escena.
        forward = camera.rotation @ Vector((0.0, 0.0, -1.0))
        pivot = obj.matrix_world.translation
        denom = direction.dot(forward)
        point = origin + direction * ((pivot - origin).dot(forward) / denom) if abs(denom) > 1e-9 else pivot.copy()
    if snap_enabled:
        _snap_class, snap_local = _geometry_snap(obj, rv3d, u, v)
        if snap_local is not None:
            point = obj.matrix_world @ snap_local
    return point


def _bisect_plane(obj, rv3d, start_uv, end_uv, snap_enabled):
    """Plano local (punto, normal) cuya traza en pantalla es la línea arrastrada.

    El plano contiene la dirección del arrastre y la de visión (profundidad), así
    que se ve como una línea recta que cruza toda la pantalla, tal y como la
    dibujó el dedo; su normal es perpendicular a ambas.
    """
    su, sv = start_uv
    eu, ev = end_uv
    if (su - eu) ** 2 + (sv - ev) ** 2 < 1e-8:
        raise BadPayload("'start' and 'end' must be different points")
    start_point = _bisect_endpoint(obj, rv3d, su, sv, snap_enabled)
    end_point = _bisect_endpoint(obj, rv3d, eu, ev, snap_enabled)
    forward = camera.rotation @ Vector((0.0, 0.0, -1.0))
    line_dir = end_point - start_point
    if line_dir.length < 1e-9:
        # Snap llevó ambos extremos al mismo punto (p.ej. mismo vértice): la
        # dirección de mundo es degenerada, así que se usa la de pantalla.
        right = camera.rotation @ Vector((1.0, 0.0, 0.0))
        up = camera.rotation @ Vector((0.0, 1.0, 0.0))
        span_x, span_y = camera.screen_span(camera.projection_matrix(rv3d))
        line_dir = right * ((eu - su) * span_x) - up * ((ev - sv) * span_y)
    if line_dir.length < 1e-9:
        raise BadPayload("'start' and 'end' must be different points")
    line_dir.normalize()
    normal = line_dir.cross(forward)
    if normal.length < 1e-9:
        raise CommandError("Cannot bisect exactly along the view direction", code="topology_incompatible")
    normal.normalize()
    mid_point = (start_point + end_point) * 0.5
    world_inv = obj.matrix_world.inverted()
    local_point = world_inv @ mid_point
    local_normal = (world_inv.to_3x3() @ normal).normalized()
    return local_point, local_normal


@command("tool.knife_pop", mutating=True)
def knife_pop(payload):
    tool_session.require(payload.get("_client_id"))
    if tool_session.tool != "KNIFE":
        raise CommandError("knife_pop requires a KNIFE session", code="wrong_tool")
    if tool_session.points:
        tool_session.points.pop()
    tool_session.closed = False
    tool_session.preview()
    return tool_session.status()


@command("tool.knife_close", mutating=True)
def knife_close(payload):
    tool_session.require(payload.get("_client_id"))
    if tool_session.tool != "KNIFE":
        raise CommandError("knife_close requires a KNIFE session", code="wrong_tool")
    tool_session.closed = not tool_session.closed
    tool_session.preview()
    return tool_session.status()


@command("tool.loop_pick", mutating=True)
def loop_pick(payload):
    """Coloca o re-ubica el corte de Loop Cut tocando la malla.

    Con la familia solo armada (B3), este es el primer toque: resuelve la arista
    bajo el dedo y recién ahí crea el backup y activa la sesión. Con sesión ya
    activa, re-ubica igual que antes.

    Los índices de `edge` son de la malla ORIGINAL (la copia que restaura cada
    preview), no del preview en pantalla: sondear contra el preview daría índices
    que ya no existen al reconstruir. Así que restore → sondeo → parámetros →
    preview, todo en un paso atómico.
    """
    owner = payload.get("_client_id")
    if tool_session.active:
        tool_session.require(owner)
        if tool_session.tool != "LOOP_CUT":
            raise CommandError("loop_pick requires a LOOP_CUT session", code="wrong_tool")
    elif tool_session.armed_tool == "LOOP_CUT":
        tool_session.require_armed_owner(owner)
    else:
        raise CommandError("No tool in progress", code="no_session")

    if find_view3d() is None:
        raise CommandError("No 3D viewport available", code="no_viewport")

    if tool_session.active and bool(payload.get("add", False)):
        # El preview actual pasa a ser la base inmutable del siguiente corte. Se
        # sondea antes de copiar porque el usuario está tocando precisamente esa
        # topología ya cortada; sus índices coinciden con la copia recién creada.
        probe = mesh_commands.loop_probe(dict(payload))
        if not probe.get("hit"):
            return dict(tool_session.status(), pick=probe)
        bm = bmesh.from_edit_mesh(tool_session.obj.data)
        new_base = bpy.data.meshes.new(".remote_loop_base")
        bm.to_mesh(new_base)
        tool_session.loop_history.append((tool_session.backup, dict(tool_session.params)))
        tool_session.backup = new_base
        tool_session.params.update({"edge": probe["edge"], "factor": probe["factor"]})
        tool_session.preview()
        return dict(tool_session.status(), pick=probe)

    if tool_session.active:
        tool_session.restore_preview_base()
        probe = mesh_commands.loop_probe(dict(payload))
        if not probe.get("hit"):
            # Sin arista bajo el dedo la sesión queda como estaba.
            tool_session.preview()
            return dict(tool_session.status(), pick=probe)
        tool_session.params.update({"edge": probe["edge"], "factor": probe["factor"]})
        tool_session.preview()
        return dict(tool_session.status(), pick=probe)

    # Armada: nada que restaurar todavía. Un toque sin impacto la deja armada.
    probe = mesh_commands.loop_probe(dict(payload))
    if not probe.get("hit"):
        return dict(tool_session.status(), pick=probe)
    params = dict(tool_session.armed_params, edge=probe["edge"], factor=probe["factor"])
    owner_id = tool_session.armed_owner
    tool_session.disarm()
    tool_session._activate("LOOP_CUT", owner_id, params)
    return dict(tool_session.status(), pick=probe)


@command("tool.loop_pop", mutating=True)
def loop_pop(payload):
    """Descarta el corte activo y vuelve al anterior para poder editarlo."""
    tool_session.require(payload.get("_client_id"))
    if tool_session.tool != "LOOP_CUT":
        raise CommandError("loop_pop requires a LOOP_CUT session", code="wrong_tool")
    if not tool_session.loop_history:
        raise CommandError("There is no previous loop cut", code="empty_history")
    current_base = tool_session.backup
    previous_base, previous_params = tool_session.loop_history.pop()
    tool_session.backup = previous_base
    tool_session.params = previous_params
    tool_session.preview()
    if current_base is not tool_session.original_backup and current_base.name in bpy.data.meshes:
        bpy.data.meshes.remove(current_base)
    return tool_session.status()


@command("tool.nudge", mutating=True)
def nudge(payload):
    tool_session.require(payload.get("_client_id"))
    if tool_session.tool == "KNIFE":
        raise CommandError("Knife is not nudged; place points with knife_point", code="wrong_tool")
    if tool_session.tool == "BISECT":
        raise CommandError("Bisect is not nudged; redraw the line with tool.drag_line", code="wrong_tool")
    try:
        delta = float(payload.get("delta", payload.get("dy", 0.0)))
    except (TypeError, ValueError):
        raise BadPayload("'delta' must be a number")
    primary = {"EXTRUDE": "offset", "BEVEL": "offset", "INSET": "thickness",
               "SUBDIVIDE": "cuts", "LOOP_CUT": "factor",
               "BRIDGE_EDGE_LOOPS": "twist_offset"}[tool_session.tool]
    current = tool_session.params.get(primary, 0 if primary != "cuts" else 1)
    nxt = max(1, round(current + delta)) if primary == "cuts" else current + delta
    if primary == "twist_offset":
        nxt = round(nxt)
    if primary == "factor":
        # Sin clamp el corte puede salirse del borde (extrapolación), así que el
        # arrastre llega más lejos; con clamp se queda en el borde.
        limit = 1.999 if not tool_session.params.get("clamp", True) else 0.999
        nxt = max(-limit, min(limit, nxt))
    tool_session.params[primary] = nxt
    tool_session.preview()
    return tool_session.status()


@command("tool.confirm", mutating=True)
def confirm(payload):
    tool_session.require(payload.get("_client_id"))
    if tool_session.tool == "KNIFE" and len(tool_session.points) < 2:
        raise CommandError("Knife needs at least two points", code="empty_selection")
    if tool_session.tool == "BISECT" and tool_session.line is None:
        raise CommandError("Bisect needs a drawn line", code="empty_selection")
    result = tool_session.status()
    undo_push(f"Remote {tool_session.tool.lower()}")
    tool_session.close()
    result["active"], result["armed"], result["phase"] = False, False, "CONFIRMED"
    return result


@command("tool.cancel", mutating=True)
def cancel(payload):
    owner = payload.get("_client_id")
    if tool_session.active:
        tool_session.require(owner)
        result = tool_session.status()
        tool_session.restore()
        tool_session.close()
        result["active"], result["armed"], result["phase"] = False, False, "CANCELLED"
        return result
    if tool_session.armed_tool:
        tool_session.require_armed_owner(owner)
        tool_session.disarm()
        return {"active": False, "armed": False, "phase": "CANCELLED"}
    raise CommandError("No tool in progress", code="no_session")


@command("tool.status")
def status(payload):
    return tool_session.status()
