"""mode.* — cambio de modo de Blender."""

from __future__ import annotations

import bpy

from ..bpy_utils import active_object, view3d_override
from ..errors import BadPayload, CommandError
from . import command

VALID_MODES = {
    "OBJECT",
    "EDIT",
    "SCULPT",
    "VERTEX_PAINT",
    "WEIGHT_PAINT",
    "TEXTURE_PAINT",
}


def _set_mode(target: str) -> dict:
    obj = active_object()
    if obj.mode == target:
        return {"mode": target}
    if target == "EDIT" and obj.type not in {"MESH", "CURVE", "SURFACE", "META", "FONT", "ARMATURE", "LATTICE"}:
        raise CommandError(f"Object type '{obj.type}' has no Edit Mode", code="wrong_mode")
    try:
        with view3d_override():
            bpy.ops.object.mode_set(mode=target)
    except RuntimeError as exc:
        raise CommandError(f"Cannot switch to {target}: {exc}", code="wrong_mode")
    return {"mode": obj.mode}


@command("mode.object", mutating=False)
def mode_object(payload: dict) -> dict:
    return _set_mode("OBJECT")


@command("mode.edit", mutating=False)
def mode_edit(payload: dict) -> dict:
    return _set_mode("EDIT")


@command("mode.sculpt", mutating=False)
def mode_sculpt(payload: dict) -> dict:
    return _set_mode("SCULPT")


@command("mode.set", mutating=False)
def mode_set(payload: dict) -> dict:
    target = str(payload.get("mode", "")).upper()
    if target not in VALID_MODES:
        raise BadPayload(f"'mode' must be one of {', '.join(sorted(VALID_MODES))}")
    return _set_mode(target)


@command("mode.toggle", mutating=False)
def mode_toggle(payload: dict) -> dict:
    obj = active_object()
    return _set_mode("OBJECT" if obj.mode == "EDIT" else "EDIT")
