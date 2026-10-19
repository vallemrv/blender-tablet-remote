"""Coordinación perezosa de las sesiones globales de transformación, tool y CAD.

Los imports viven dentro de cada función para no crear el ciclo
``modal -> tools -> mesh -> ...`` durante el registro de comandos.
"""


def cancel_transform(*, restore=True):
    cancel_cad(restore=restore)
    from .sculpt import cancel as cancel_sculpt
    cancel_sculpt(restore=restore)
    from .modal import session
    if not session.active:
        return
    if restore:
        session.restore_safely()
    session.reset()
    session.phase = "CANCELLED"


def cancel_tool(*, restore=True):
    cancel_cad(restore=restore)
    from .sculpt import cancel as cancel_sculpt
    cancel_sculpt(restore=restore)
    from .tools import tool_session
    if tool_session.active:
        if restore:
            tool_session.restore_safely()
        tool_session.close()
    elif tool_session.armed_tool:
        tool_session.disarm()


def cancel_all(*, restore=True):
    from ..materials.runtime import runtime as materials
    materials.cancel()
    cancel_transform(restore=restore)
    cancel_tool(restore=restore)
    cancel_cad(restore=restore)
    from .sculpt import cancel as cancel_sculpt
    cancel_sculpt(restore=restore)


def cancel_cad(*, restore=True):
    from .selection_paint import cancel
    cancel(restore=restore)
    from ..cad.runtime import runtime
    runtime.cancel(restore=restore)


def finish_for_switch(owner=None):
    """Confirma el resultado estable al cambiar intención; los gestos incompletos se retiran."""
    from . import modal, tools
    session = modal.session
    if session.active:
        session.require(owner)
        if session.motion == 'SLIDE' or session.mode in {'MOVE', 'ROTATE', 'SCALE'}:
            if session.curve_edit is not None:
                changed = session.curve_edit.changed()
            elif session.edit_object is not None:
                import bmesh
                bm = bmesh.from_edit_mesh(session.edit_object.data)
                bm.verts.ensure_lookup_table()
                baseline = session.individual_edit_coords if session.individual_edit_coords is not None else session.edit_coords
                changed = any((bm.verts[index].co-co).length_squared > 1e-20 for index,co in baseline.items())
            else:
                changed = any(any(abs(obj.matrix_world[r][c]-matrix[r][c]) > 1e-10
                                  for r in range(4) for c in range(4)) for obj,matrix in session.originals)
            if changed:
                modal.confirm({'_client_id': owner})
            else:
                session.reset()
    tool = tools.tool_session
    if tool.active:
        tool.require(owner)
        ready = not ((tool.tool == 'KNIFE' and len(tool.points) < 2 and not tool.knife_strokes)
                     or (tool.tool == 'BISECT' and tool.line is None)
                     or (tool.alignment is not None and not tool.alignment.status(tool.params)['can_confirm']))
        if ready:
            tools.confirm({'_client_id': owner})
        else:
            tools.cancel({'_client_id': owner})
    elif tool.armed_tool:
        tool.require_armed_owner(owner)
        tool.disarm()


from . import command

@command('interaction.finish', mutating=True)
def finish(payload):
    finish_for_switch(payload.get('_client_id'))
    from .. import state
    return state.snapshot(include_view=False)
