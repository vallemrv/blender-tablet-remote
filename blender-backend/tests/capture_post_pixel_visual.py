"""Smoke test visual de POST_PIXEL con el gizmo de traslación nativo."""

from __future__ import annotations

import sys
import threading
import time
import urllib.request
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from blender_tablet_remote import bridge  # noqa: E402

PORT = 8891
STREAM_PORT = 8892
OUTPUT = Path("/tmp/blender_remote_post_pixel_gizmo.jpg")


def fetch() -> None:
    try:
        deadline = time.monotonic() + 10.0
        data = b""
        while time.monotonic() < deadline:
            try:
                data = urllib.request.urlopen(
                    f"http://127.0.0.1:{STREAM_PORT}/frame.jpg", timeout=2
                ).read()
                if len(data) > 1000:
                    break
            except OSError:
                time.sleep(0.2)
        if len(data) <= 1000:
            raise RuntimeError("POST_PIXEL did not produce a JPEG")
        OUTPUT.write_bytes(data)
        print(f"POST_PIXEL_VISUAL_OK {len(data)} {OUTPUT}", flush=True)
        bpy.app.timers.register(finish, first_interval=0.1)
    except Exception as exc:  # noqa: BLE001
        print(f"POST_PIXEL_VISUAL_FAIL {exc}", flush=True)
        bpy.app.timers.register(lambda: sys.exit(1), first_interval=0.1)


def finish():
    info = bridge.stream_info()
    print(f"POST_PIXEL_STATS {info}", flush=True)
    bridge.stop()
    raise SystemExit(0)


def start():
    obj = bpy.context.view_layer.objects.active
    if obj is not None:
        obj.select_set(True)

    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != "VIEW_3D":
                continue
            space = area.spaces.active
            space.show_gizmo = True
            space.show_gizmo_context = True
            space.show_gizmo_object_translate = True
            area.tag_redraw()
            break

    bridge.start(
        "127.0.0.1",
        PORT,
        "",
        stream={
            "enabled": True,
            "port": STREAM_PORT,
            "fps": 12,
            "max_width": 1280,
            "quality": 80,
            "capture_mode": "POST_PIXEL",
        },
    )
    threading.Thread(target=fetch, name="post-pixel-fetch", daemon=True).start()
    return None


bpy.app.timers.register(start, first_interval=1.0)
