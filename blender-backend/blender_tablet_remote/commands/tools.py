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

SUPPORTED = {"EXTRUDE", "BEVEL", "INSET", "SUBDIVIDE", "LOOP_CUT", "BRIDGE_EDGE_LOOPS", "KNIFE"}

KNIFE_SNAP_THRESHOLD = 0.045


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
        self.result = None
        self.points = []  # anclas del Knife, en coordenadas locales
        self.closed = False

    def begin(self, tool, owner, params):
        obj = active_object()
        if obj.mode != "EDIT" or obj.type != "MESH":
            raise CommandError("Parametric tools require mesh Edit Mode", code="wrong_mode")
        if self.active:
            self.restore()
            self.close()
        bm = bmesh.from_edit_mesh(obj.data)
        if tool == "LOOP_CUT" and "edge" not in params:
            seed = next((edge for edge in bm.edges if edge.select and not edge.hide), None)
            if seed is None:
                raise CommandError("Select an edge or provide 'edge'", code="empty_selection")
            params = dict(params, edge=seed.index)
        backup = bpy.data.meshes.new(".remote_tool_backup")
        bm.to_mesh(backup)
        self.active, self.session_id, self.owner_id = True, str(uuid.uuid4()), owner
        self.tool, self.params, self.obj, self.backup = tool, dict(params), obj, backup
        self.points = []
        self.closed = False
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
        if self.obj.name not in bpy.data.objects or self.obj.mode != "EDIT":
            self.close()
            raise CommandError("Tool session invalidated", code="session_invalidated")

    def restore(self):
        if self.obj is None or self.backup is None or self.obj.mode != "EDIT":
            return
        bm = bmesh.from_edit_mesh(self.obj.data)
        bm.clear()
        bm.from_mesh(self.backup)
        bmesh.update_edit_mesh(self.obj.data, loop_triangles=True, destructive=True)

    def preview(self):
        self.restore()
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
        payload["_no_undo"] = True
        handlers = {"EXTRUDE": mesh_commands.extrude, "BEVEL": mesh_commands.bevel,
                    "INSET": mesh_commands.inset, "SUBDIVIDE": mesh_commands.subdivide,
                    "LOOP_CUT": mesh_commands.loop_cut,
                    "BRIDGE_EDGE_LOOPS": mesh_commands.bridge_edge_loops}
        self.result = handlers[self.tool](payload)

    def close(self):
        backup = self.backup
        self.reset()
        if backup is not None and backup.name in bpy.data.meshes:
            bpy.data.meshes.remove(backup)

    def status(self):
        if not self.active:
            return {"active": False, "phase": "IDLE"}
        state = {"active": True, "phase": "ACTIVE", "session_id": self.session_id,
                 "owner": self.owner_id, "tool": self.tool, "parameters": self.params,
                 "preview": self.result}
        if self.tool == "KNIFE":
            state["points"] = [list(p) for p in self.points]
            state["closed"] = self.closed
        return state

    def owner_disconnected(self, owner):
        if self.active and self.owner_id == owner:
            self.restore()
            self.close()


tool_session = ToolSession()


@command("tool.begin", mutating=True)
def begin(payload):
    tool = str(payload.get("tool", "")).upper()
    if tool not in SUPPORTED:
        raise BadPayload("'tool' must be EXTRUDE, BEVEL, INSET, SUBDIVIDE, LOOP_CUT, BRIDGE_EDGE_LOOPS or KNIFE")
    params = payload.get("parameters", {})
    if not isinstance(params, dict):
        raise BadPayload("'parameters' must be an object")
    params = dict(params)
    if "edge" in payload and "edge" not in params:
        params["edge"] = payload["edge"]
    tool_session.begin(tool, payload.get("_client_id"), params)
    return tool_session.status()


@command("tool.parameter", mutating=True)
def parameter(payload):
    tool_session.require(payload.get("_client_id"))
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
    tool_session.preview()
    return tool_session.status()


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
    snap = _knife_snap(tool_session.obj, rv3d, u, v, local)
    tool_session.points.append(list(local))
    tool_session.preview()
    return dict(tool_session.status(), hit=True, snap=snap, point=list(local))


def _knife_snap(obj, rv3d, u, v, local):
    """Clase de snap más cercana en pantalla: VERTEX, EDGE o NONE."""
    if not tool_session.params.get("snap", True):
        return "NONE"
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
        if d <= KNIFE_SNAP_THRESHOLD:
            best = (d, "VERTEX", vert.co.copy()) if best is None or d < best[0] else best
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
        if d <= KNIFE_SNAP_THRESHOLD:
            best = (d, "EDGE", None) if best is None or d < best[0] else best
    if best is None:
        return "NONE"
    return best[1]


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
    """Re-ubica el corte de una sesión LOOP_CUT tocando la malla.

    Los índices de `edge` son de la malla ORIGINAL (la copia que restaura cada
    preview), no del preview en pantalla: sondear contra el preview daría índices
    que ya no existen al reconstruir. Así que restore → sondeo → parámetros →
    preview, todo en un paso atómico.
    """
    tool_session.require(payload.get("_client_id"))
    if tool_session.tool != "LOOP_CUT":
        raise CommandError("loop_pick requires a LOOP_CUT session", code="wrong_tool")
    from ..bpy_utils import find_view3d

    if find_view3d() is None:
        raise CommandError("No 3D viewport available", code="no_viewport")
    tool_session.restore()
    probe = mesh_commands.loop_probe(dict(payload))
    if not probe.get("hit"):
        # Sin arista bajo el dedo la sesión queda como estaba.
        tool_session.preview()
        return dict(tool_session.status(), pick=probe)
    tool_session.params.update({"edge": probe["edge"], "factor": probe["factor"]})
    tool_session.preview()
    return dict(tool_session.status(), pick=probe)


@command("tool.nudge", mutating=True)
def nudge(payload):
    tool_session.require(payload.get("_client_id"))
    if tool_session.tool == "KNIFE":
        raise CommandError("Knife is not nudged; place points with knife_point", code="wrong_tool")
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
    result = tool_session.status()
    undo_push(f"Remote {tool_session.tool.lower()}")
    tool_session.close()
    result["active"], result["phase"] = False, "CONFIRMED"
    return result


@command("tool.cancel", mutating=True)
def cancel(payload):
    tool_session.require(payload.get("_client_id"))
    result = tool_session.status()
    tool_session.restore()
    tool_session.close()
    result["active"], result["phase"] = False, "CANCELLED"
    return result


@command("tool.status")
def status(payload):
    return tool_session.status()
