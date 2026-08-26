"""Herramientas paramétricas de Edit Mode con preview reversible."""

from __future__ import annotations

import uuid

import bmesh
import bpy

from ..bpy_utils import active_object, undo_push
from ..errors import BadPayload, CommandError
from . import command
from . import mesh as mesh_commands

SUPPORTED = {"EXTRUDE", "BEVEL", "INSET", "SUBDIVIDE", "LOOP_CUT"}


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
        payload = dict(self.params)
        payload["_no_undo"] = True
        handlers = {"EXTRUDE": mesh_commands.extrude, "BEVEL": mesh_commands.bevel,
                    "INSET": mesh_commands.inset, "SUBDIVIDE": mesh_commands.subdivide,
                    "LOOP_CUT": mesh_commands.loop_cut}
        self.result = handlers[self.tool](payload)

    def close(self):
        backup = self.backup
        self.reset()
        if backup is not None and backup.name in bpy.data.meshes:
            bpy.data.meshes.remove(backup)

    def status(self):
        if not self.active:
            return {"active": False, "phase": "IDLE"}
        return {"active": True, "phase": "ACTIVE", "session_id": self.session_id,
                "owner": self.owner_id, "tool": self.tool, "parameters": self.params,
                "preview": self.result}

    def owner_disconnected(self, owner):
        if self.active and self.owner_id == owner:
            self.restore()
            self.close()


tool_session = ToolSession()


@command("tool.begin", mutating=True)
def begin(payload):
    tool = str(payload.get("tool", "")).upper()
    if tool not in SUPPORTED:
        raise BadPayload("'tool' must be EXTRUDE, BEVEL, INSET, SUBDIVIDE or LOOP_CUT")
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
    params = payload.get("parameters", payload.get("parameter"))
    if not isinstance(params, dict):
        raise BadPayload("'parameters' must be an object")
    tool_session.params.update(params)
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
    try:
        delta = float(payload.get("delta", payload.get("dy", 0.0)))
    except (TypeError, ValueError):
        raise BadPayload("'delta' must be a number")
    primary = {"EXTRUDE": "offset", "BEVEL": "offset", "INSET": "thickness",
               "SUBDIVIDE": "cuts", "LOOP_CUT": "factor"}[tool_session.tool]
    current = tool_session.params.get(primary, 0 if primary != "cuts" else 1)
    nxt = max(1, round(current + delta)) if primary == "cuts" else current + delta
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
