"""file.* — nuevo, abrir y guardar.

Cargar un .blend es la operación más agresiva del add-on: invalida toda referencia
a datos que Python tuviera guardada. Se puede hacer aquí porque el timer del puente
está registrado con `persistent=True` (sobrevive a la carga) y la captura de vídeo
resuelve el viewport en cada frame en vez de cachearlo. Lo que sí hay que rehacer es
el estado propio del add-on: de eso se encarga `bridge.reset_session()`.
"""

from __future__ import annotations

import os

import bpy

from ..errors import BadPayload, CommandError
from . import command


def _reset_session() -> None:
    """Import diferido: `bridge` importa `commands`, y al revés sería circular."""
    from .. import bridge

    bridge.reset_session()


def _info() -> dict:
    path = bpy.data.filepath
    return {
        "path": path,
        "name": os.path.basename(path) or "Sin título",
        # Distinguir "nunca guardado" de "con cambios" importa: el primero obliga a
        # pedir nombre, el segundo solo a confirmar.
        "saved": bool(path),
        "dirty": bool(bpy.data.is_dirty),
    }


def _blend_path(payload: dict) -> str:
    raw = str(payload.get("path", "")).strip()
    if not raw:
        raise BadPayload("'path' is required")
    path = bpy.path.abspath(raw)
    if os.path.isdir(path):
        raise BadPayload(f"'{path}' is a directory")
    return path


@command("file.info")
def info(payload: dict) -> dict:
    return _info()


@command("file.new", mutating=True)
def new(payload: dict) -> dict:
    """`empty=True` da una escena vacía; por defecto se usa el archivo de inicio."""
    try:
        bpy.ops.wm.read_homefile(use_empty=bool(payload.get("empty", False)))
    except RuntimeError as exc:
        raise CommandError(f"Cannot start a new file: {exc}")
    _reset_session()
    return _info()


@command("file.open", mutating=True)
def open_file(payload: dict) -> dict:
    path = _blend_path(payload)
    if not os.path.isfile(path):
        raise CommandError(f"File not found: {path}", code="not_found")
    try:
        bpy.ops.wm.open_mainfile(filepath=path)
    except RuntimeError as exc:
        raise CommandError(f"Cannot open '{path}': {exc}")
    _reset_session()
    return _info()


@command("file.save", mutating=True)
def save(payload: dict) -> dict:
    if not bpy.data.filepath:
        # No inventamos una ruta: que el cliente pida nombre y llame a file.save_as.
        raise CommandError("This file has never been saved", code="no_path")
    try:
        bpy.ops.wm.save_mainfile()
    except RuntimeError as exc:
        raise CommandError(f"Cannot save: {exc}")
    return _info()


@command("file.save_as", mutating=True)
def save_as(payload: dict) -> dict:
    path = _blend_path(payload)
    if not path.lower().endswith(".blend"):
        path += ".blend"
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        raise CommandError(f"Folder not found: {folder}", code="not_found")
    try:
        bpy.ops.wm.save_as_mainfile(filepath=path)
    except RuntimeError as exc:
        raise CommandError(f"Cannot save to '{path}': {exc}")
    return _info()


@command("file.recent")
def recent(payload: dict) -> dict:
    """
    Los recientes que ya muestra Blender, leídos de su propio `recent-files.txt`.

    Es la lista que el usuario reconoce, y evita tener que navegar el disco del PC
    desde una tablet, que es incómodo y mucho más protocolo.
    """
    limit = payload.get("limit", 12)
    try:
        limit = max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        raise BadPayload("'limit' must be an integer")

    config = bpy.utils.user_resource("CONFIG")
    listing = os.path.join(config, "recent-files.txt")
    if not os.path.isfile(listing):
        return {"files": []}

    files = []
    try:
        with open(listing, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                path = line.strip()
                if not path:
                    continue
                files.append(
                    {
                        "path": path,
                        "name": os.path.basename(path),
                        "folder": os.path.dirname(path),
                        # Un reciente puede haberse movido o borrado. Se manda igual,
                        # marcado, para que la app lo muestre en gris en vez de mentir.
                        "exists": os.path.isfile(path),
                    }
                )
                if len(files) >= limit:
                    break
    except OSError as exc:
        raise CommandError(f"Cannot read recent files: {exc}")

    return {"files": files}
