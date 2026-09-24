"""Registro de comandos.

Cada comando es una función `f(payload: dict) -> dict | None` que se ejecuta SIEMPRE
en el hilo principal de Blender. Devolver un dict lo añade a la respuesta como
"result". Para fallar de forma controlada, lanzar CommandError.
Los generadores CAD suspenden su respuesta al ceder un cálculo: el bridge los
reanuda desde el pump. Las llamadas Python directas consumen el mismo generador.
"""

from __future__ import annotations

from typing import Callable
import inspect
from functools import wraps

REGISTRY: dict[str, Callable[[dict], object]] = {}

# Comandos que modifican datos: el bridge hace undo_push tras ejecutarlos.
MUTATING: set[str] = set()


def command(name: str, mutating: bool = False):
    def decorator(func):
        if inspect.isgeneratorfunction(func):
            from ..cad.jobs import PendingCommand, blocking
            @wraps(func)
            def synchronous(payload):
                return blocking(func(payload))
            REGISTRY[name] = lambda payload: PendingCommand(func(payload))
        else:
            synchronous = func
            REGISTRY[name] = func
        if mutating:
            MUTATING.add(name)
        return synchronous

    return decorator


def load_all() -> None:
    """Importa los módulos de comandos (rellena REGISTRY por efecto secundario)."""
    from . import (  # noqa: F401
        cad,
        reconnect,
        file,
        history,
        mesh,
        material,
        modal,
        mode,
        modifiers,
        objects,
        scene,
        sculpt,
        selection,
        snap,
        stream,
        transform,
        tools,
        units,
        view,
    )


def get(name: str):
    return REGISTRY.get(name)


def names() -> list[str]:
    return sorted(REGISTRY)
