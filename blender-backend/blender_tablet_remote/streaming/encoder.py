"""Codificación JPEG fuera del hilo principal, con ffmpeg.

Por qué no se codifica con `bpy.data.images`, que sería lo obvio: escribir píxeles
en un datablock de imagen y guardarlo hunde el bucle de eventos de Blender de ~48 Hz
a 1 Hz. Medido, aislando etapas:

    sin captura ................................. 48,4 Hz
    draw_view3d + read_color (12,5 ms) .......... 44,8 Hz   <- la GPU no es el problema
    + Image.pixels.foreach_set + Image.save ......  1,0 Hz   <- lo es tocar el datablock

Con Blender a 1 Hz no solo el vídeo va a tirones: los comandos de la tablet también
tardarían un segundo en aplicarse. Así que el hilo principal solo hace la captura GPU
y entrega los píxeles crudos; comprimir es trabajo de otro proceso.

ffmpeg añade además el muxer `mpjpeg`, que ya emite el multipart con Content-length
que necesita el cliente, y deja la puerta abierta a H.264/NVENC (§88) sin rehacer esto.
"""

from __future__ import annotations

import queue
import shutil
import subprocess
import threading

from .. import log
from .frames import FrameBuffer

FFMPEG = "ffmpeg"
BOUNDARY_PREFIX = b"--"
# Cola de 1: si el codificador se retrasa preferimos tirar el frame viejo antes que
# acumular retraso. La prioridad del plan es la latencia, no no perder fotogramas.
QUEUE_SIZE = 1


def available() -> bool:
    return shutil.which(FFMPEG) is not None


def _quality_to_qv(quality: int) -> int:
    """quality 20..95 (más alto mejor) -> -q:v 31..2 de ffmpeg (más bajo mejor)."""
    quality = max(20, min(int(quality), 95))
    return int(round(31 - (quality - 20) * (31 - 2) / (95 - 20)))


class JpegEncoder:
    """Convierte RGBA cruda en JPEG usando un ffmpeg persistente."""

    def __init__(self, frames: FrameBuffer):
        self.frames = frames
        self._proc: subprocess.Popen | None = None
        self._queue: queue.Queue[bytes | None] = queue.Queue(maxsize=QUEUE_SIZE)
        self._writer: threading.Thread | None = None
        self._reader: threading.Thread | None = None
        self._size = (0, 0)
        self._quality = 0
        self._lock = threading.Lock()
        self._dropped = 0
        self._encoded = 0

    # -------------------------------------------------------------------- API

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def stats(self) -> dict:
        return {"encoded": self._encoded, "dropped": self._dropped}

    def ensure(self, width: int, height: int, fps: float, quality: int) -> bool:
        """Arranca ffmpeg, o lo reinicia si cambió el formato. False si no se puede."""
        with self._lock:
            if self.running and self._size == (width, height) and self._quality == quality:
                return True
            self._stop_locked()
            return self._start_locked(width, height, fps, quality)

    def submit(self, raw: bytes) -> None:
        """Llamado desde el hilo principal de Blender: no debe bloquear jamás."""
        try:
            self._queue.put_nowait(raw)
        except queue.Full:
            # Latest frame wins. Antes se descartaba `raw`, conservando justamente
            # el frame viejo que provocaba que el viewport fuese por detrás del dedo.
            self._dropped += 1
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(raw)
            except queue.Full:
                # El writer ganó la carrera y volvió a ocuparla: jamás bloquear el
                # hilo principal por un fotograma.
                pass

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    # --------------------------------------------------------------- interno

    def _start_locked(self, width: int, height: int, fps: float, quality: int) -> bool:
        if not available():
            log.error("ffmpeg no encontrado: el vídeo del viewport no puede codificarse")
            return False
        cmd = [
            FFMPEG, "-hide_banner", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "rgba",
            "-s", f"{width}x{height}", "-r", f"{max(1, int(fps))}",
            "-i", "pipe:0",
            # read_color entrega las filas de abajo arriba; voltear en ffmpeg es
            # gratis comparado con hacerlo en Python.
            "-vf", "vflip",
            "-fflags", "nobuffer", "-flush_packets", "1",
            "-q:v", str(_quality_to_qv(quality)),
            "-f", "mpjpeg", "pipe:1",
        ]
        try:
            proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            log.error("no se pudo arrancar ffmpeg: %s", exc)
            return False

        self._proc = proc
        self._size = (width, height)
        self._quality = quality
        self._drain_queue()

        self._writer = threading.Thread(target=self._write_loop, args=(proc,), name="btr-enc-w", daemon=True)
        self._reader = threading.Thread(target=self._read_loop, args=(proc,), name="btr-enc-r", daemon=True)
        self._writer.start()
        self._reader.start()
        log.info("encoder ffmpeg %dx%d q=%d", width, height, quality)
        return True

    def _stop_locked(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            self._queue.put_nowait(None)  # despierta al writer para que cierre stdin
        except queue.Full:
            self._drain_queue()
            try:
                self._queue.put_nowait(None)
            except queue.Full:
                pass
        try:
            proc.terminate()
            proc.wait(timeout=2.0)
        except (OSError, subprocess.TimeoutExpired):
            proc.kill()
        for thread in (self._writer, self._reader):
            if thread is not None:
                thread.join(timeout=2.0)
        self._writer = self._reader = None
        self._size = (0, 0)
        self._drain_queue()

    def _drain_queue(self) -> None:
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def _write_loop(self, proc: subprocess.Popen) -> None:
        stdin = proc.stdin
        assert stdin is not None
        try:
            while True:
                raw = self._queue.get()
                if raw is None or proc.poll() is not None:
                    break
                stdin.write(raw)
                stdin.flush()
        except (BrokenPipeError, OSError, ValueError):
            pass
        finally:
            try:
                stdin.close()
            except OSError:
                pass

    def _read_loop(self, proc: subprocess.Popen) -> None:
        """Parsea el multipart que emite el muxer mpjpeg y publica cada JPEG."""
        import time

        stdout = proc.stdout
        assert stdout is not None
        try:
            while True:
                length = self._read_part_length(stdout)
                if length is None:
                    break
                data = stdout.read(length)
                if not data or len(data) < length:
                    break
                self._encoded += 1
                self.frames.publish(data, time.time())
        except (OSError, ValueError):
            pass

    @staticmethod
    def _read_part_length(stdout) -> int | None:
        length: int | None = None
        while True:
            line = stdout.readline()
            if not line:
                return None
            stripped = line.strip()
            if not stripped:
                # Línea en blanco: fin de cabeceras, empieza el JPEG.
                if length is not None:
                    return length
                continue
            if stripped.startswith(BOUNDARY_PREFIX):
                length = None
                continue
            name, _, value = stripped.partition(b":")
            if name.strip().lower() == b"content-length":
                try:
                    length = int(value.strip())
                except ValueError:
                    return None
