"""Coordinación perezosa de las dos sesiones globales.

Los imports viven dentro de cada función para no crear el ciclo
``modal -> tools -> mesh -> ...`` durante el registro de comandos.
"""


def cancel_transform(*, restore=True):
    from .modal import session
    if not session.active:
        return
    if restore:
        session.restore_safely()
    session.reset()
    session.phase = "CANCELLED"


def cancel_tool(*, restore=True):
    from .tools import tool_session
    if tool_session.active:
        if restore:
            tool_session.restore_safely()
        tool_session.close()
    elif tool_session.armed_tool:
        tool_session.disarm()


def cancel_all(*, restore=True):
    cancel_transform(restore=restore)
    cancel_tool(restore=restore)
