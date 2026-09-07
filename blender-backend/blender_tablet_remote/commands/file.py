"""file.* — nuevo, abrir y guardar.

Cargar un .blend es la operación más agresiva del add-on: invalida toda referencia
a datos que Python tuviera guardada. Se puede hacer aquí porque el timer del puente
está registrado con `persistent=True` (sobrevive a la carga) y la captura de vídeo
resuelve el viewport en cada frame en vez de cachearlo. Lo que sí hay que rehacer es
el estado propio del add-on: de eso se encarga `bridge.reset_session()`.
"""

from __future__ import annotations

import json
import os
import string

import bpy

from ..errors import BadPayload, CommandError
from . import command

_SETTINGS_NAME = "blender-tablet-remote.json"


def _settings_path() -> str:
    return os.path.join(bpy.utils.user_resource("CONFIG"), _SETTINGS_NAME)


def _load_default_folder() -> str:
    try:
        with open(_settings_path(), encoding="utf-8") as handle:
            value = json.load(handle).get("default_folder", "")
        if isinstance(value, str) and os.path.isdir(value):
            return os.path.realpath(os.path.abspath(os.path.expanduser(value)))
    except (OSError, ValueError, TypeError):
        pass
    current = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else ""
    return os.path.realpath(current or os.path.expanduser("~"))


def _store_default_folder(path: str) -> None:
    target = _settings_path()
    temp = target + ".tmp"
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump({"default_folder": path}, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp, target)
    except PermissionError as exc:
        raise CommandError(f"Cannot persist default folder: {exc}", code="access_denied")
    except OSError as exc:
        raise CommandError(f"Cannot persist default folder: {exc}", code="io_error")


def _aliases() -> dict[str, str]:
    return {
        "@default": _load_default_folder(),
        "@home": os.path.realpath(os.path.expanduser("~")),
        "@root": os.path.abspath(os.sep),
    }


def _resolve_path(raw, *, required: bool = True) -> str:
    if raw is None and not required:
        raw = "@default"
    if not isinstance(raw, str) or not raw.strip():
        raise BadPayload("'path' is required")
    value = os.path.expanduser(raw.strip())
    folded = value.replace("\\", "/")
    for alias, base in _aliases().items():
        if folded.lower() == alias or folded.lower().startswith(alias + "/"):
            suffix = folded[len(alias):].lstrip("/")
            value = os.path.join(base, *suffix.split("/")) if suffix else base
            break
    if not os.path.isabs(value):
        value = os.path.join(_load_default_folder(), value)
    return os.path.realpath(os.path.abspath(value))


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
    path = _resolve_path(payload.get("path"))
    if os.path.isdir(path):
        raise BadPayload(f"'{path}' is a directory")
    return path


def _save_as_path(payload: dict) -> str:
    """Resuelve el payload moderno folder+name o el path legado completo."""
    uses_parts = "folder" in payload or "name" in payload
    if not uses_parts:
        return _blend_path(payload)
    if "path" in payload:
        raise BadPayload("Use either 'path' or 'folder' + 'name', not both")

    raw_name = payload.get("name")
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise BadPayload("'name' is required")
    name = raw_name.strip()
    # Se comprueban ambos separadores incluso si Blender corre en POSIX: la ruta es
    # un token del host remoto y un cliente no debe poder colar traversal Windows.
    if (name in (".", "..") or "/" in name or "\\" in name or "\x00" in name
            or os.path.basename(name) != name or os.path.splitdrive(name)[0]):
        raise BadPayload("'name' must be a filename without path separators")

    folder = _resolve_path(payload.get("folder"))
    if not os.path.exists(folder):
        raise CommandError(f"Folder not found: {folder}", code="not_found")
    if not os.path.isdir(folder):
        raise CommandError(f"Not a directory: {folder}", code="not_directory")
    return os.path.join(folder, name)


def _locations() -> list[dict]:
    candidates = [
        ("DEFAULT", "Predeterminada", _load_default_folder()),
        ("HOME", "Carpeta personal", os.path.expanduser("~")),
        ("ROOT", "Sistema", os.path.abspath(os.sep)),
    ]
    if os.name == "nt":
        candidates.extend((f"VOLUME_{letter}", f"Unidad {letter}:", f"{letter}:\\")
                          for letter in string.ascii_uppercase if os.path.isdir(f"{letter}:\\"))
    else:
        user = os.environ.get("USER", "")
        for base in (os.path.join("/media", user), os.path.join("/run/media", user), "/mnt"):
            try:
                with os.scandir(base) as scan:
                    for item in scan:
                        if item.is_dir(follow_symlinks=True):
                            candidates.append(("VOLUME", item.name, item.path))
            except OSError:
                pass
    result, seen = [], set()
    for identifier, label, path in candidates:
        canonical = os.path.realpath(os.path.abspath(path))
        key = os.path.normcase(canonical)
        # Los tres aliases base conservan siempre su identidad aunque DEFAULT y
        # HOME apunten al mismo sitio; solo se deduplican volúmenes descubiertos.
        if (identifier == "VOLUME" and key in seen) or not os.path.isdir(canonical):
            continue
        seen.add(key)
        stable_id = identifier if identifier != "VOLUME" else "VOLUME_" + str(len(result))
        result.append({"id": stable_id, "label": label, "path": canonical})
    return result


def _locations_result() -> dict:
    return {"default_folder": _load_default_folder(), "locations": _locations()}


def _breadcrumbs(path: str) -> list[dict]:
    """Componentes navegables sin obligar al cliente a interpretar paths del host."""
    result = []
    current = path
    while True:
        parent = os.path.dirname(current)
        name = os.path.basename(current) or current
        result.append({"name": name, "path": current})
        if parent == current:
            break
        current = parent
    result.reverse()
    return result


@command("file.info")
def info(payload: dict) -> dict:
    return _info()


@command("file.new", mutating=True)
def new(payload: dict) -> dict:
    """`empty=True` da una escena vacía; por defecto se usa el archivo de inicio."""
    from .sessions import cancel_cad
    cancel_cad()
    try:
        from ..cad.runtime import runtime
        runtime.leave()
        bpy.ops.wm.read_homefile(use_empty=bool(payload.get("empty", False)))
    except RuntimeError as exc:
        raise CommandError(f"Cannot start a new file: {exc}")
    _reset_session()
    return _info()


@command("file.open", mutating=True)
def open_file(payload: dict) -> dict:
    from .sessions import cancel_cad
    cancel_cad()
    path = _blend_path(payload)
    if not os.path.isfile(path):
        raise CommandError(f"File not found: {path}", code="not_found")
    if not path.lower().endswith(".blend"):
        raise CommandError(f"Not a Blender file: {path}", code="not_blend")
    try:
        from ..cad.runtime import runtime
        runtime.leave()
        bpy.ops.wm.open_mainfile(filepath=path)
    except RuntimeError as exc:
        raise CommandError(f"Cannot open '{path}': {exc}")
    _reset_session()
    return _info()


@command("file.save", mutating=True)
def save(payload: dict) -> dict:
    from .sessions import cancel_cad
    cancel_cad()
    if not bpy.data.filepath:
        # No inventamos una ruta: que el cliente pida nombre y llame a file.save_as.
        raise CommandError("This file has never been saved", code="no_path")
    try:
        from ..cad.runtime import runtime
        with runtime.saving():
            bpy.ops.wm.save_mainfile()
    except RuntimeError as exc:
        raise CommandError(f"Cannot save: {exc}")
    return _info()


@command("file.save_as", mutating=True)
def save_as(payload: dict) -> dict:
    from .sessions import cancel_cad
    cancel_cad()
    path = _save_as_path(payload)
    if not path.lower().endswith(".blend"):
        path += ".blend"
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        raise CommandError(f"Folder not found: {folder}", code="not_found")
    try:
        from ..cad.runtime import runtime
        with runtime.saving():
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


@command("file.locations")
def locations(payload: dict) -> dict:
    return _locations_result()


@command("file.browse")
def browse(payload: dict) -> dict:
    path = _resolve_path(payload.get("path"), required=False)
    if not os.path.exists(path):
        raise CommandError(f"Path not found: {path}", code="not_found")
    if not os.path.isdir(path):
        raise CommandError(f"Not a directory: {path}", code="not_directory")
    entries = []
    try:
        with os.scandir(path) as scan:
            for item in scan:
                try:
                    if item.is_dir(follow_symlinks=True):
                        kind = "DIRECTORY"
                    elif item.is_file(follow_symlinks=True) and item.name.lower().endswith(".blend"):
                        kind = "BLEND"
                    else:
                        continue
                except OSError:
                    continue
                entries.append({"name": item.name, "path": os.path.realpath(item.path), "type": kind})
    except PermissionError as exc:
        raise CommandError(f"Cannot read directory '{path}': {exc}", code="access_denied")
    except OSError as exc:
        raise CommandError(f"Cannot read directory '{path}': {exc}", code="io_error")
    entries.sort(key=lambda item: (item["type"] != "DIRECTORY", item["name"].casefold()))
    parent = os.path.dirname(path)
    return {"path": path, "parent": parent if parent != path else None,
            "breadcrumbs": _breadcrumbs(path),
            "default_folder": _load_default_folder(), "entries": entries}


@command("file.default_folder")
def default_folder(payload: dict) -> dict:
    path = _resolve_path(payload.get("path"))
    if not os.path.exists(path):
        raise CommandError(f"Path not found: {path}", code="not_found")
    if not os.path.isdir(path):
        raise CommandError(f"Not a directory: {path}", code="not_directory")
    if not os.access(path, os.R_OK | os.X_OK):
        raise CommandError(f"Cannot access directory: {path}", code="access_denied")
    _store_default_folder(path)
    return _locations_result()
