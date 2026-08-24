"""history.* — undo / redo.

bpy.ops.ed.undo() necesita contexto de ventana; desde un timer lo envolvemos en un
override del VIEW_3D. En background (`blender -b`) Blender no mantiene pila de undo,
así que devolvemos un error explícito en vez de fingir que funcionó.
"""

from __future__ import annotations

import bpy

from ..bpy_utils import undo_push, view3d_override
from ..errors import CommandError
from . import command


def _run(op, label: str) -> dict:
    if bpy.app.background:
        raise CommandError("Undo/redo is not available in background mode", code="no_undo_stack")
    try:
        with view3d_override():
            op()
    except RuntimeError as exc:
        raise CommandError(f"{label} failed: {exc}", code="undo_failed")
    return {"action": label}


@command("history.undo")
def undo(payload: dict) -> dict:
    return _run(bpy.ops.ed.undo, "undo")


@command("history.redo")
def redo(payload: dict) -> dict:
    return _run(bpy.ops.ed.redo, "redo")


@command("history.push")
def push(payload: dict) -> dict:
    """Marca manualmente un punto de undo (útil al cerrar un gesto compuesto)."""
    label = str(payload.get("message", "Remote step"))
    undo_push(label)
    return {"pushed": label}
