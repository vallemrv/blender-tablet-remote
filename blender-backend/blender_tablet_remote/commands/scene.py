"""Comandos de escena y estado."""

from __future__ import annotations

from copy import deepcopy

import bpy

from .. import state
from ..errors import CommandError
from ..protocol import ENUMS, FEATURES, LOOPTOOLS_CIRCLE_ACTION, PROTOCOL_VERSION, UNITS
from . import command, names


@command("scene.get_state")
def get_state(payload: dict) -> dict:
    result = state.snapshot(include_view=payload.get("include_view", True))
    if payload.get("include_objects"):
        result["objects"] = state.scene_objects()
    return result


@command("scene.capture")
def capture(payload: dict) -> dict:
    import base64
    from .. import bridge
    from ..errors import CommandError
    if bridge._capture is None:
        raise CommandError('La captura requiere el servidor de vídeo', code='no_viewport')
    result = bridge._capture._grab_offscreen(clean=True)
    if not result:
        raise CommandError('No hay una vista 3D disponible', code='no_viewport')
    data, width, height = result
    return {'mime':'image/png','width':width,'height':height,'png_base64':base64.b64encode(data).decode('ascii')}


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

    features = deepcopy(FEATURES)
    try:
        bpy.ops.mesh.looptools_circle.get_rna_type()
        circle_available = True
    except (AttributeError, KeyError, RuntimeError):
        circle_available = False
    if circle_available:
        catalog = features["edit_catalog"]["groups"]
        for mode in ("VERTEX", "EDGE"):
            action = deepcopy(LOOPTOOLS_CIRCLE_ACTION)
            action["requirements"]["selection_modes"] = [mode]
            catalog[mode].insert(1, action)

    return {
        "addon_version": ".".join(str(n) for n in VERSION),
        "protocol_version": PROTOCOL_VERSION,
        "features": features,
        "enums": ENUMS,
        "units": dict(UNITS, scale_length=bpy.context.scene.unit_settings.scale_length,
                      unit_system=bpy.context.scene.unit_settings.system),
        "blender": bpy.app.version_string,
        "commands": names(),
        "gestures": ["orbit", "pan", "zoom", "roll", "move", "rotate", "scale"],
        "background": bpy.app.background,
    }
