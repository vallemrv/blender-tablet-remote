"""Captura del viewport 3D. Solo esto corre en el hilo principal de Blender.

`gpu` y `bpy` únicamente son seguros desde el hilo principal, así que `tick()` lo
llama el timer `_pump()` del bridge. Aquí se hace lo mínimo —dibujar el viewport en
un offscreen y leer los píxeles, unos 12 ms— y los bytes crudos se entregan al
codificador, que trabaja aparte. El motivo está documentado en encoder.py: comprimir
dentro de Blender lo dejaba a 1 Hz.

La única fuente es ``GPUOffScreen``: dibuja con la cámara independiente de la tablet.
No captura el framebuffer de la ventana del PC ni su interfaz nativa.
"""

from __future__ import annotations

import time
from contextlib import contextmanager

import bpy
import gpu
from mathutils import Vector

from .. import log
from ..camera import camera
from .encoder import VideoEncoder
from .frames import FrameBuffer
from .markers import draw_transform_markers

# Tras varios fallos seguidos dejamos de intentarlo: si no hay GPU o no hay VIEW_3D,
# reintentar 30 veces por segundo solo llena la consola de trazas idénticas.
MAX_CONSECUTIVE_ERRORS = 10


def _find_view3d_space():
    """(area, region, space, rv3d) del primer VIEW_3D con región dibujable."""
    wm = bpy.context.window_manager
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type != "VIEW_3D":
                continue
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            space = area.spaces.active
            if region is None or space is None or region.width <= 1 or region.height <= 1:
                continue
            return area, region, space, space.region_3d
    return None


@contextmanager
def _sculpt_grid(space):
    """Hide only the grid in tablet Sculpt frames; preserve the viewport settings."""
    obj = bpy.context.view_layer.objects.active
    overlay = space.overlay
    previous = {key: getattr(overlay, key) for key in
                ('show_floor', 'show_ortho_grid', 'show_axis_x', 'show_axis_y', 'show_axis_z')
                } if obj and obj.mode == 'SCULPT' else {}
    try:
        for key in previous:
            setattr(overlay, key, False)
        yield
    finally:
        for key, value in previous.items():
            setattr(overlay, key, value)


@contextmanager
def _multires_surface():
    """Materialize native Multires grids for GPUOffScreen's image-render path.

    Workbench excludes sculpt PBVH batches during offscreen image rendering.
    In Sculpt, the evaluated Mesh otherwise contains only the coarse cage, with
    the actual surface stored in native CCG grids. This evaluation flag exposes
    that same displaced surface as a Mesh, at sculpt_levels, for this draw only.
    """
    obj = bpy.context.view_layer.objects.active
    modifiers = [m for m in obj.modifiers
                 if m.type == 'MULTIRES' and m.show_viewport and m.sculpt_levels > 0
                 and not m.use_sculpt_base_mesh] if obj and obj.mode == 'SCULPT' else []
    try:
        for modifier in modifiers:
            modifier.use_sculpt_base_mesh = True
        if modifiers:
            bpy.context.evaluated_depsgraph_get()
        yield
    finally:
        for modifier in modifiers:
            modifier.use_sculpt_base_mesh = False
        if modifiers:
            # Native brushes must receive their live grids again, including when
            # drawing failed. No Mesh.update(), mode switch, or undo is involved.
            bpy.context.view_layer.update()


class ViewportCapture:
    def __init__(self, frames: FrameBuffer, h264_frames: FrameBuffer | None = None,
                 has_viewers=None, wanted_formats=None):
        self.frames = frames
        self.h264_frames = h264_frames or FrameBuffer()
        self.encoder = VideoEncoder(frames, self.h264_frames)
        # Sin nadie mirando no tiene sentido gastar GPU ni ffmpeg en cada tick.
        self.has_viewers = has_viewers or (lambda: True)
        self.wanted_formats = wanted_formats or (lambda: {"h264", "mjpeg"})
        self.enabled = False
        self.fps = 24.0
        self.max_width = 1280
        self.quality = 70
        self._sculpt_depth = None
        self._offscreen = None
        self._offscreen_size = (0, 0)

        self._last_capture = 0.0
        self._errors = 0
        self._frames_done = 0
        self._last_cost_ms = 0.0
        self._measured_fps = 0.0
        self._fps_window_start = 0.0
        self._fps_window_count = 0
        # Un comando discreto (tap, confirmar, cambiar modo) pide un frame inmediato
        # para que el viewport lo refleje ya, sin esperar al siguiente hueco de fps.
        self._force_capture = False

    # ------------------------------------------------------------------ ajuste

    def configure(
        self,
        *,
        enabled: bool,
        fps: float,
        max_width: int,
        quality: int,
    ) -> None:
        self.enabled = bool(enabled)
        self.fps = max(1.0, min(float(fps), 60.0))
        self.max_width = max(320, min(int(max_width), 2560))
        self.quality = max(20, min(int(quality), 95))
        self._errors = 0

    def stats(self) -> dict:
        return {
            "enabled": self.enabled,
            "fps_target": self.fps,
            "fps_actual": round(self._measured_fps, 1),
            "max_width": self.max_width,
            "quality": self.quality,
            "frames": self._frames_done,
            "last_bytes": len(self.frames.latest()[0]),
            "last_cost_ms": round(self._last_cost_ms, 1),
            "resolution": list(self._offscreen_size),
            "errors": self._errors,
            "encoder": self.encoder.stats,
        }

    # ------------------------------------------------------------------- ciclo

    def request_frame(self) -> None:
        """Pide capturar en el siguiente tick, saltándose el límite de fps una vez.

        Los gestos y comandos continuos (arrastrar) no lo usan: a 60 Hz saturarían
        el hilo principal de render. Solo se invoca tras comandos discretos.
        """
        self._force_capture = True

    def next_delay(self, maximum: float) -> float:
        """Wake at the next video deadline instead of sleeping past it after render."""
        if not self.enabled or self._errors >= MAX_CONSECUTIVE_ERRORS or not self.has_viewers():
            return maximum
        if self._force_capture:
            return min(maximum, .001)
        remaining = self._last_capture + 1.0 / self.fps - time.monotonic()
        return min(maximum, max(.001, remaining))

    def tick(self) -> None:
        """Captura un frame si toca. Nunca lanza: el pump no puede morir."""
        if not self.enabled or self._errors >= MAX_CONSECUTIVE_ERRORS:
            self._force_capture = False
            return
        if not self.has_viewers():
            self._measured_fps = 0.0
            self._fps_window_start = 0.0
            self._fps_window_count = 0
            self._force_capture = False
            return

        now = time.monotonic()
        if now - self._last_capture < 1.0 / self.fps and not self._force_capture:
            return
        self._force_capture = False
        self._last_capture = now

        try:
            captured = self._grab_offscreen()
        except Exception as exc:  # noqa: BLE001
            self._errors += 1
            log.error("viewport capture failed (%d/%d): %s", self._errors, MAX_CONSECUTIVE_ERRORS, exc)
            if self._errors >= MAX_CONSECUTIVE_ERRORS:
                log.error("viewport capture disabled after repeated failures")
            return

        if not captured:
            return

        self._errors = 0
        self._frames_done += 1
        self._last_cost_ms = (time.monotonic() - now) * 1000.0
        self._tally_fps(now)

    def _tally_fps(self, now: float) -> None:
        if self._fps_window_start == 0.0:
            self._fps_window_start = now
        self._fps_window_count += 1
        elapsed = now - self._fps_window_start
        if elapsed >= 1.0:
            self._measured_fps = self._fps_window_count / elapsed
            self._fps_window_start = now
            self._fps_window_count = 0

    # ---------------------------------------------------------------- captura

    def _grab_offscreen(self) -> bool:
        found = _find_view3d_space()
        if found is None:
            return False
        area, region, space, rv3d = found

        scale = min(1.0, self.max_width / float(region.width))
        width = max(2, int(region.width * scale) & ~1)   # pares: los encoders lo agradecen
        height = max(2, int(region.height * scale) & ~1)

        if not self.encoder.ensure(width, height, self.fps, self.quality, self.wanted_formats()):
            self.enabled = False
            return False

        offscreen = self._ensure_offscreen(width, height)

        # draw_view3d dibuja el depsgraph EVALUADO, y no lo evalúa él: se limita a
        # usar el que haya. Los cambios que hacemos desde el timer (select_set,
        # matrix_world, bmesh) marcan el depsgraph como sucio pero no lo actualizan,
        # así que sin esta llamada el offscreen seguía pintando la escena anterior
        # hasta que algo ajeno forzaba la evaluación: la navegación se veía perfecta
        # (solo cambia la matriz de vista) mientras seleccionar o escalar tardaba
        # segundos en aparecer. Si nada está sucio, esto no cuesta nada.
        bpy.context.evaluated_depsgraph_get()

        # La vista es la de la tablet, no la de la ventana: ver camera.py. De la
        # región solo se hereda la proyección.
        camera.sync_from_region(rv3d)

        from ..cad.runtime import runtime as cad_runtime
        with _multires_surface(), _sculpt_grid(space), offscreen.bind(), cad_runtime.preview_shading(space):
            fb = gpu.state.active_framebuffer_get()
            fb.clear(color=(0.0, 0.0, 0.0, 1.0), depth=1.0)
            offscreen.draw_view3d(
                bpy.context.scene,
                bpy.context.view_layer,
                space,
                region,
                camera.view_matrix(),
                camera.projection_matrix(rv3d),
                do_color_management=True,
            )
            obj = bpy.context.view_layer.objects.active
            if obj and obj.mode == "SCULPT":
                matrix = camera.perspective_matrix(rv3d).copy()
                self._sculpt_depth = (fb.read_depth(0, 0, width, height), matrix,
                                      matrix.inverted_safe(), obj.name, obj.matrix_world.copy(),
                                      width, height)
            else:
                self._sculpt_depth = None
            draw_transform_markers(rv3d, width, height)
            buffer = fb.read_color(0, 0, width, height, 4, 0, "UBYTE")

        # `buffer` es un gpu.types.Buffer; bytes() lo copia y deja que el resto del
        # trabajo ocurra fuera del hilo principal.
        self.encoder.submit(bytes(buffer))
        return True

    def sculpt_surface(self, u, v, obj, rv3d):
        """Visible sculpt surface of the last video frame, never desktop depth.

        The boolean distinguishes a valid background sample from unavailable or
        stale depth. Native multires/Dyntopo cannot be raycast through Mesh RNA.
        """
        cached = self._sculpt_depth
        if cached is None:
            return False, None
        depth, matrix, inverse, name, object_matrix, width, height = cached
        if (name != obj.name or object_matrix != obj.matrix_world or
                matrix != camera.perspective_matrix(rv3d) or
                (width, height) != self._offscreen_size):
            return False, None
        x = min(width - 1, max(0, int(u * width)))
        y = min(height - 1, max(0, int((1 - v) * height)))
        z = float(depth[y][x])
        if z >= 1 or z < 0:
            return True, None
        world = inverse @ Vector(((x + .5) / width * 2 - 1,
                                    (y + .5) / height * 2 - 1, z * 2 - 1, 1))
        return True, Vector(world[:3]) / world.w if abs(world.w) > 1e-9 else None

    def _ensure_offscreen(self, width: int, height: int):
        if self._offscreen is not None and self._offscreen_size == (width, height):
            return self._offscreen
        if self._offscreen is not None:
            self._offscreen.free()
        self._offscreen = gpu.types.GPUOffScreen(width, height)
        self._offscreen_size = (width, height)
        log.info("viewport capture at %dx%d", width, height)
        return self._offscreen

    # -------------------------------------------------------------- limpieza

    def shutdown(self) -> None:
        """Libera recursos GPU. Debe llamarse desde el hilo principal."""
        self.enabled = False
        self._sculpt_depth = None
        self.encoder.stop()
        if self._offscreen is not None:
            try:
                self._offscreen.free()
            except Exception:  # noqa: BLE001
                pass
            self._offscreen = None
            self._offscreen_size = (0, 0)
