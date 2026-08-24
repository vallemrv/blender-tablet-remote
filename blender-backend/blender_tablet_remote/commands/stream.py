"""stream.* — control del vídeo del viewport desde el cliente.

Permite que la tablet baje calidad o fps si la red va justa (§38) sin que el usuario
tenga que tocar las preferencias del add-on en el PC.
"""

from __future__ import annotations

from ..errors import BadPayload
from . import command


def _bridge():
    # Import diferido: bridge importa commands, así que hacerlo arriba sería circular.
    from .. import bridge

    return bridge


@command("stream.info")
def info(payload: dict) -> dict:
    return _bridge().stream_info()


@command("stream.configure")
def configure(payload: dict) -> dict:
    """Ajusta el stream en caliente. Los campos ausentes se quedan como estaban."""
    enabled = payload.get("enabled")
    if enabled is not None and not isinstance(enabled, bool):
        raise BadPayload("'enabled' must be a boolean")

    def as_int(key: str) -> int | None:
        value = payload.get(key)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            raise BadPayload(f"'{key}' must be an integer")

    return _bridge().configure_stream(
        enabled=enabled,
        fps=as_int("fps"),
        max_width=as_int("max_width"),
        quality=as_int("quality"),
    )
