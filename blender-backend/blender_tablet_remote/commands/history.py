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

_last_action: tuple[str, dict] | None = None
_last_tool: tuple[str, dict] | None = None


def remember(name: str, payload: dict) -> None:
    """Conserva solo intenciones discretas que pueden ejecutarse otra vez."""
    global _last_action, _last_tool
    allowed = (
        name.startswith("mesh.") and name not in {"mesh.info", "mesh.loop_probe"}
        or name in {"object.add", "object.duplicate", "object.delete", "object.shade",
                    "transform.move", "transform.rotate", "transform.scale", "transform.apply"}
        or name in {"modifier.add", "modifier.remove", "modifier.set", "modifier.apply"}
    )
    if not allowed:
        return
    _last_action = (name, {key: value for key, value in payload.items() if key != "_client_id"})
    _last_tool = None


def remember_tool(name: str, parameters: dict) -> None:
    global _last_action, _last_tool
    if name in {"KNIFE", "BISECT", "ALIGN"}:
        return
    _last_tool = (name, dict(parameters))
    _last_action = None


def _run(op, label: str) -> dict:
    if bpy.app.background:
        raise CommandError("Undo/redo is not available in background mode", code="no_undo_stack")
    from .sessions import cancel_all
    cancel_all(restore=True)
    try:
        with view3d_override():
            op()
    except RuntimeError as exc:
        raise CommandError(f"{label} failed: {exc}", code="undo_failed")
    return {"action": label}


@command("history.undo")
def undo(payload: dict) -> dict:
    result = _run(bpy.ops.ed.undo, "undo")
    from .sculpt import history_traversed
    history_traversed(True)
    return result


@command("history.redo")
def redo(payload: dict) -> dict:
    from .sculpt import redo_allowed
    if not redo_allowed():
        raise CommandError("El trazo cancelado no se puede rehacer", code="nothing_to_redo")
    result = _run(bpy.ops.ed.redo, "redo")
    from .sculpt import history_traversed
    history_traversed(False)
    return result


@command("history.push")
def push(payload: dict) -> dict:
    """Marca manualmente un punto de undo (útil al cerrar un gesto compuesto)."""
    label = str(payload.get("message", "Remote step"))
    undo_push(label)
    return {"pushed": label}


@command("history.repeat_last", mutating=True)
def repeat_last(payload: dict) -> dict:
    """Shift+R remoto: repite la última intención de modelado confirmada."""
    owner = payload.get("_client_id")
    if _last_tool is not None:
        from . import tools
        name, parameters = _last_tool
        tools.begin({"tool": name, "parameters": dict(parameters), "_client_id": owner})
        result = tools.confirm({"_client_id": owner})
        return {"repeated": name, "result": result}
    if _last_action is not None:
        from . import get
        name, saved = _last_action
        func = get(name)
        if func is None:
            raise CommandError("Last action is no longer available", code="not_found")
        result = func(dict(saved, _client_id=owner))
        return {"repeated": name, "result": result}
    raise CommandError("There is no repeatable action yet", code="nothing_to_repeat")
