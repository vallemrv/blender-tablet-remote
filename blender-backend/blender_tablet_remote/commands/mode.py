"""mode.* — cambio de modo de Blender."""

from __future__ import annotations

import bpy

from ..bpy_utils import active_object, view3d_override
from ..errors import BadPayload, CommandError
from . import command

VALID_MODES = {
    "OBJECT",
    "EDIT",
    "CAD",
    "SCULPT",
}


def _set_mode(target: str, owner=None) -> dict:
    from ..cad.runtime import runtime, FEATURE_KEY
    from .sessions import cancel_all, cancel_cad
    from .sculpt import cancel as cancel_sculpt
    cancel_sculpt()
    cancel_cad()
    if target == "CAD":
        doc = runtime.doc()
        entering = not runtime.workspace
        cancel_all()
        obj = bpy.context.view_layer.objects.active
        if obj and obj.mode != "OBJECT":
            with view3d_override():
                bpy.ops.object.mode_set(mode="OBJECT")
        runtime.workspace = True
        runtime.workspace_owner = owner
        runtime.isolate()
        if entering and doc['sketches']:
            sketch = next((s for s in doc['sketches'] if s['id'] == runtime.active_sketch_id),
                          doc['sketches'][0])
            runtime.focus(sketch)
        return {"mode": "CAD", "cad": runtime.status()}
    obj = bpy.context.view_layer.objects.active
    if target in {"EDIT", "SCULPT"} and obj and obj.get(FEATURE_KEY):
        raise CommandError("Esta pieza es paramétrica: edita su sketch o conviértela a malla", code="cad_mesh_protected")
    runtime.leave()
    if target == "OBJECT" and obj is None:
        return {"mode": "OBJECT"}
    obj = active_object()
    if obj.mode == target:
        return {"mode": target}
    if target == "EDIT" and obj.type not in {"MESH", "CURVE", "SURFACE", "META", "FONT", "ARMATURE", "LATTICE"}:
        raise CommandError(f"Object type '{obj.type}' has no Edit Mode", code="wrong_mode")
    if target == "SCULPT":
        if obj.type != "MESH":
            raise CommandError("Escultura requiere una malla", code="wrong_mode")
        if bpy.app.background or bpy.app.version < (4, 4, 0):
            raise CommandError("Escultura requiere Blender 4.4+ con ventana", code="no_viewport")
        cancel_all()
    try:
        with view3d_override():
            bpy.ops.object.mode_set(mode=target)
    except RuntimeError as exc:
        raise CommandError(f"Cannot switch to {target}: {exc}", code="wrong_mode")
    if target == "SCULPT":
        from .sculpt import enter, status
        enter()
        return {"mode": obj.mode, "sculpt": status()}
    return {"mode": obj.mode}


@command("mode.object", mutating=False)
def mode_object(payload: dict) -> dict:
    return _set_mode("OBJECT")


@command("mode.edit", mutating=False)
def mode_edit(payload: dict) -> dict:
    return _set_mode("EDIT")


@command("mode.set", mutating=False)
def mode_set(payload: dict) -> dict:
    target = str(payload.get("mode", "")).upper()
    if target not in VALID_MODES:
        raise BadPayload(f"'mode' must be one of {', '.join(sorted(VALID_MODES))}")
    return _set_mode(target, payload.get("_client_id"))


@command("mode.toggle", mutating=False)
def mode_toggle(payload: dict) -> dict:
    obj = active_object()
    return _set_mode("OBJECT" if obj.mode == "EDIT" else "EDIT")
