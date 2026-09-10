"""Registro de comandos.

Cada comando es una función `f(payload: dict) -> dict | None` que se ejecuta SIEMPRE
en el hilo principal de Blender. Devolver un dict lo añade a la respuesta como
"result". Para fallar de forma controlada, lanzar CommandError.
"""

from __future__ import annotations

from typing import Callable

REGISTRY: dict[str, Callable[[dict], dict | None]] = {}

# Comandos que modifican datos: el bridge hace undo_push tras ejecutarlos.
MUTATING: set[str] = set()


def command(name: str, mutating: bool = False):
    def decorator(func):
        REGISTRY[name] = func
        if mutating:
            MUTATING.add(name)
        return func

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
