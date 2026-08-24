"""Arranca el servidor sin instalar el add-on. Útil para desarrollo.

Con interfaz (lo normal, así ves el viewport moverse):

    blender --python blender-backend/tools/run_server.py -- --host 0.0.0.0 --port 8765

Headless (para tests de integración, sin ventana):

    blender --background --python blender-backend/tools/run_server.py -- --port 8765

En `--background` Blender no corre su bucle de eventos y los `bpy.app.timers` nunca se
disparan, así que aquí bombeamos el bridge a mano hasta Ctrl+C.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ADDON_PARENT = str(Path(__file__).resolve().parent.parent)
if ADDON_PARENT not in sys.path:
    sys.path.insert(0, ADDON_PARENT)

from blender_tablet_remote import bridge  # noqa: E402


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--token", default=os.environ.get("BLENDER_REMOTE_TOKEN", ""))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    bridge.start(args.host, args.port, args.token, verbose=args.verbose)
    print(f"[REMOTE] dev server ready on ws://{args.host}:{args.port}", flush=True)

    import bpy

    if bpy.app.background:
        print("[REMOTE] background mode: pumping manually, Ctrl+C to stop", flush=True)
        try:
            while True:
                bridge._pump()
                time.sleep(0.004)
        except KeyboardInterrupt:
            pass
        finally:
            bridge.stop()


main()
