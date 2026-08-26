"""Logging del add-on. Prefijo [REMOTE] y control de verbosidad."""

from __future__ import annotations

PREFIX = "[REMOTE]"

# 0 = silencio, 1 = normal (conexiones, comandos), 2 = verbose (gestos, frames)
_level = 1


def set_level(level: int) -> None:
    global _level
    _level = int(level)


def get_level() -> int:
    return _level


def info(msg: str, *args) -> None:
    if _level >= 1:
        print(PREFIX, msg % args if args else msg, flush=True)


def debug(msg: str, *args) -> None:
    """Para eventos de alta frecuencia (gestos, frames). Silenciado salvo verbose.

    Sin flush: a decenas de mensajes por segundo, forzar la syscall por línea
    costaba más que el propio log; stdout termina volcándose solo.
    """
    if _level >= 2:
        print(PREFIX, msg % args if args else msg)


def warn(msg: str, *args) -> None:
    if _level >= 1:
        print(PREFIX, "WARN:", msg % args if args else msg, flush=True)


def error(msg: str, *args) -> None:
    print(PREFIX, "ERROR:", msg % args if args else msg, flush=True)
