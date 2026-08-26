"""Mantiene despierta la pantalla del PC mientras haya alguien conectado.

Con el monitor en DPMS off, el redibujo de la ventana de Blender se bloquea, y con él
todo su bucle de eventos: los `bpy.app.timers` dejan de correr, así que `_pump()` no
drena comandos ni captura vídeo. Medido sobre la instalación real alternando
`xset dpms force on/off`, con un cubo de 8 vértices en escena:

    pantalla apagada ....  1,2 fps de vídeo,  783 ms por comando
    pantalla encendida ... 19,3 fps de vídeo,   21 ms por comando

Solo se nota al mutar la escena, que es lo que obliga a Blender a redibujar; orbitar y
hacer zoom mueven la cámara virtual de `camera.py`, que Blender ni ve. De ahí el
síntoma clásico: "navegar va perfecto pero seleccionar tarda cuatro segundos".

Y como la tablet es precisamente la interfaz que se usa lejos del PC, el caso normal
era el malo: el monitor se apagaba solo a los pocos minutos.

Esto es X11 con `xset`. En Wayland o sin `xset` no hace nada y lo dice una vez: es una
comodidad, y no funcionar aquí jamás puede impedir que el servidor arranque.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time

from . import log

TIMEOUT = 2.0
# Desactivar el DPMS de X no basta: en este equipo sus timeouts ya están a 0 y quien
# apaga la pantalla es el gestor de energía del escritorio, que va por su cuenta. Un
# latido barato la vuelve a encender si alguien la apagó por detrás.
HEARTBEAT = 30.0

_active = False
_available: bool | None = None
_saved: dict | None = None
_last_beat = 0.0

_SAVER = re.compile(r"timeout:\s*(\d+)\s+cycle:\s*(\d+)")
_DPMS = re.compile(r"Standby:\s*(\d+)\s+Suspend:\s*(\d+)\s+Off:\s*(\d+)")
_ENABLED = re.compile(r"DPMS is (Enabled|Disabled)")


def _xset(*args: str) -> str | None:
    """Ejecuta xset. Devuelve stdout, o None si no se pudo."""
    try:
        done = subprocess.run(["xset", *args], capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError) as exc:
        log.debug("xset %s falló: %s", " ".join(args), exc)
        return None
    return done.stdout


def available() -> bool:
    global _available
    if _available is None:
        _available = bool(os.environ.get("DISPLAY")) and shutil.which("xset") is not None
        if not _available:
            log.info("sin DISPLAY/xset: la pantalla del PC no se gestiona; si se apaga sola, "
                     "el viewport de la tablet se volverá lento (ver AGENTS.md)")
    return _available


def _read_settings() -> dict | None:
    out = _xset("-q")
    if not out:
        return None
    saver, dpms, enabled = _SAVER.search(out), _DPMS.search(out), _ENABLED.search(out)
    if saver is None or dpms is None or enabled is None:
        log.debug("no se pudo interpretar 'xset -q'")
        return None
    return {
        "timeout": saver.group(1),
        "cycle": saver.group(2),
        "standby": dpms.group(1),
        "suspend": dpms.group(2),
        "off": dpms.group(3),
        "enabled": enabled.group(1) == "Enabled",
    }


def keep_awake(wanted: bool) -> None:
    """Activa o suelta la inhibición. Idempotente: solo actúa en las transiciones.

    La llama el pump en cada tick, así que no puede permitirse lanzar un proceso si
    no hay nada que cambiar.
    """
    global _active
    if not available():
        return
    if wanted == _active:
        if wanted:
            _heartbeat()
        return
    if wanted:
        _inhibit()
    else:
        _restore()


def _heartbeat() -> None:
    """Cada HEARTBEAT segundos, reenciende la pantalla si alguien la apagó por detrás."""
    global _last_beat
    now = time.monotonic()
    if now - _last_beat < HEARTBEAT:
        return
    _last_beat = now
    out = _xset("-q")
    if out and "Monitor is Off" in out:
        _xset("dpms", "force", "on")
        _xset("-dpms")  # 'force' reactiva el DPMS: hay que volver a apagarlo
        log.info("pantalla del PC reencendida: estaba apagada con la tablet conectada")


def _inhibit() -> None:
    global _active, _saved, _last_beat
    _saved = _read_settings()
    if _saved is None:
        return
    _xset("s", "off")
    # Si ya estaba apagada al conectar, encenderla: si no, seguiría bloqueando. Va
    # ANTES de `-dpms` a propósito: `xset dpms force` reactiva el DPMS, así que
    # deshabilitarlo después es lo único que deja el estado que queremos.
    _xset("dpms", "force", "on")
    _xset("-dpms")
    _active = True
    _last_beat = time.monotonic()
    log.info("pantalla del PC mantenida despierta mientras haya clientes")


def _restore() -> None:
    """Devuelve el ahorro de energía tal como estaba antes de inhibirlo."""
    global _active, _saved
    _active = False
    saved, _saved = _saved, None
    if saved is None:
        return
    _xset("s", saved["timeout"], saved["cycle"])
    _xset("dpms", saved["standby"], saved["suspend"], saved["off"])
    _xset("+dpms" if saved["enabled"] else "-dpms")
    log.info("ahorro de energía de pantalla restaurado")
