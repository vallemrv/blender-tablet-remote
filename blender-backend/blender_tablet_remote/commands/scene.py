"""Comandos de escena y estado."""

from __future__ import annotations

import bpy

from .. import state
from ..errors import CommandError
from ..protocol import ENUMS, FEATURES, PROTOCOL_VERSION, UNITS
from . import command, names


@command("scene.get_state")
def get_state(payload: dict) -> dict:
    result = state.snapshot(include_view=payload.get("include_view", True))
    if payload.get("include_objects"):
        result["objects"] = state.scene_objects()
    return result


@command("scene.list_objects")
def list_objects(payload: dict) -> dict:
    return {"objects": state.scene_objects()}


@command("scene.get_context")
def get_context(payload: dict) -> dict:
    return state.context_snapshot()


@command("scene.get_object")
def get_object(payload: dict) -> dict:
    name = payload.get("name")
    obj = bpy.data.objects.get(name) if name else bpy.context.view_layer.objects.active
    if obj is None:
        raise CommandError(f"Object not found: {name}", code="not_found")
    return state.object_info(obj)


@command("server.ping")
def ping(payload: dict) -> dict:
    return {"pong": True, "echo": payload.get("echo")}


@command("server.capabilities")
def capabilities(payload: dict) -> dict:
    from .. import VERSION

    return {
        "addon_version": ".".join(str(n) for n in VERSION),
        "protocol_version": PROTOCOL_VERSION,
        "features": FEATURES,
        "enums": ENUMS,
        "units": dict(UNITS, scale_length=bpy.context.scene.unit_settings.scale_length,
                      unit_system=bpy.context.scene.unit_settings.system),
        "blender": bpy.app.version_string,
        "commands": names(),
        "gestures": ["orbit", "pan", "zoom", "move", "rotate", "scale"],
        "background": bpy.app.background,
    }
