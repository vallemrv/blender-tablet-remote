"""Reinstala el ZIP local conservando preferencias y activa el arranque automático."""

from __future__ import annotations

import sys
from pathlib import Path

import bpy

PACKAGE_ID = "blender_tablet_remote"
MODULE = f"bl_ext.user_default.{PACKAGE_ID}"
ZIP = Path(__file__).resolve().parent.parent / "dist" / f"{PACKAGE_ID}-0.1.0.zip"


def main() -> None:
    old = bpy.context.preferences.addons.get(MODULE)
    prefs = old.preferences if old else None
    keys = (
        "host", "port", "token", "verbose", "stream_enabled", "stream_port",
        "stream_fps", "stream_max_width", "stream_quality", "stream_capture_mode",
    )
    preserved = {key: getattr(prefs, key) for key in keys if prefs and hasattr(prefs, key)}

    repos = bpy.context.preferences.extensions.repos
    repo_index = next((i for i, repo in enumerate(repos) if repo.module == "user_default"), None)
    if repo_index is None:
        raise RuntimeError("No existe el repositorio de extensiones User Default")
    if not ZIP.is_file():
        raise FileNotFoundError(ZIP)

    if old or (Path(repos[repo_index].directory) / PACKAGE_ID).exists():
        result = bpy.ops.extensions.package_uninstall(repo_index=repo_index, pkg_id=PACKAGE_ID)
        if "FINISHED" not in result:
            raise RuntimeError(f"No se pudo desinstalar {PACKAGE_ID}: {result}")

    result = bpy.ops.extensions.package_install_files(
        filepath=str(ZIP), repo="user_default", enable_on_install=True, overwrite=True,
    )
    if "FINISHED" not in result:
        raise RuntimeError(f"No se pudo instalar {ZIP}: {result}")

    installed = bpy.context.preferences.addons.get(MODULE)
    if installed is None:
        raise RuntimeError(f"La extensión no quedó habilitada: {MODULE}")
    prefs = installed.preferences
    for key, value in preserved.items():
        setattr(prefs, key, value)
    prefs.autostart = True
    bpy.ops.wm.save_userpref()
    print(f"REINSTALLED module={MODULE} autostart={prefs.autostart} host={prefs.host} port={prefs.port}")


try:
    main()
except Exception as exc:
    print(f"REINSTALL_FAILED: {exc}", file=sys.stderr)
    raise
