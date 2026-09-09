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
import time

from .. import log
from .frames import FrameBuffer
from .h264 import flv_access_units

FFMPEG = "ffmpeg"
BOUNDARY_PREFIX = b"--"
# Cola de 1: si el codificador se retrasa preferimos tirar el frame viejo antes que
# acumular retraso. La prioridad del plan es la latencia, no no perder fotogramas.
QUEUE_SIZE = 1


def available() -> bool:
    return shutil.which(FFMPEG) is not None


_h264_available: bool | None = None


def h264_available() -> bool:
    """Comprueba una vez que este ffmpeg fue compilado con libx264."""
    global _h264_available
    if _h264_available is not None:
        return _h264_available
    if not available():
        _h264_available = False
        return False
    try:
        probe = subprocess.run([FFMPEG, "-hide_banner", "-encoders"], capture_output=True,
                               timeout=3.0, check=False)
        _h264_available = b"libx264 " in probe.stdout
    except (OSError, subprocess.TimeoutExpired):
        _h264_available = False
    return _h264_available


def _quality_to_qv(quality: int) -> int:
    """quality 20..95 (más alto mejor) -> -q:v 31..2 de ffmpeg (más bajo mejor)."""
    quality = max(20, min(int(quality), 95))
    return int(round(31 - (quality - 20) * (31 - 2) / (95 - 20)))


class JpegEncoder:
    """Convierte RGBA cruda en JPEG usando un ffmpeg persistente."""

    def __init__(self, frames: FrameBuffer):
        self.frames = frames
        self._proc: subprocess.Popen | None = None
        self._queue: queue.Queue[tuple[bytes, float] | None] = queue.Queue(maxsize=QUEUE_SIZE)
        self._capture_stamps: queue.Queue[float] = queue.Queue()
        self._writer: threading.Thread | None = None
        self._reader: threading.Thread | None = None
        self._size = (0, 0)
        self._quality = 0
        self._lock = threading.Lock()
        self._dropped = 0
        self._encoded = 0
        self._last_encode_ms = 0.0
        self._max_encode_ms = 0.0

    # -------------------------------------------------------------------- API

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def stats(self) -> dict:
        return {
            "encoded": self._encoded,
            "dropped": self._dropped,
            "last_encode_ms": round(self._last_encode_ms, 1),
            "max_encode_ms": round(self._max_encode_ms, 1),
        }

    def ensure(self, width: int, height: int, fps: float, quality: int) -> bool:
        """Arranca ffmpeg, o lo reinicia si cambió el formato. False si no se puede."""
        with self._lock:
            if self.running and self._size == (width, height) and self._quality == quality:
                return True
            self._stop_locked()
            return self._start_locked(width, height, fps, quality)

    def submit(self, raw: bytes, captured_at: float | None = None) -> None:
        """Llamado desde el hilo principal de Blender: no debe bloquear jamás."""
        item = (raw, time.time() if captured_at is None else captured_at)
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            # Latest frame wins. Antes se descartaba `raw`, conservando justamente
            # el frame viejo que provocaba que el viewport fuese por detrás del dedo.
            self._dropped += 1
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(item)
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
        self._drain_capture_stamps()

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
        self._drain_capture_stamps()

    def _drain_queue(self) -> None:
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def _drain_capture_stamps(self) -> None:
        while True:
            try:
                self._capture_stamps.get_nowait()
            except queue.Empty:
                break

    def _write_loop(self, proc: subprocess.Popen) -> None:
        stdin = proc.stdin
        assert stdin is not None
        try:
            while True:
                item = self._queue.get()
                if item is None or proc.poll() is not None:
                    break
                raw, captured_at = item
                # Registrar antes de escribir: ffmpeg puede producir y el reader
                # despertar en cuanto el último byte entra en el pipe.
                self._capture_stamps.put(captured_at)
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
                try:
                    captured_at = self._capture_stamps.get_nowait()
                except queue.Empty:
                    captured_at = time.time()
                encode_ms = max(0.0, (time.time() - captured_at) * 1000.0)
                self._last_encode_ms = encode_ms
                self._max_encode_ms = max(self._max_encode_ms, encode_ms)
                self._encoded += 1
                # X-Timestamp representa ahora el instante de captura, no el de
                # publicación. Así el cliente mide también la cola/coste ffmpeg.
                self.frames.publish(data, captured_at)
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


class H264Encoder(JpegEncoder):
    """libx264 baseline/zerolatency; publica access units Annex B completos."""

    def _start_locked(self, width: int, height: int, fps: float, quality: int) -> bool:
        if not h264_available():
            log.warn("ffmpeg sin libx264: se usará MJPEG")
            return False
        fps_i = max(1, int(fps))
        # Un GOP de ~200 ms comprime mucho mejor que intra-only y limita lo que una
        # reconexión/salto debe esperar para recuperar una referencia limpia.
        gop = max(4, min(6, int(round(fps_i / 5))))
        # CRF bajo = mejor calidad. El rango de UI histórico 20..95 se conserva.
        crf = max(18, min(36, int(round(36 - (quality - 20) * 18 / 75))))
        cmd = [
            FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "rawvideo",
            "-pix_fmt", "rgba", "-s", f"{width}x{height}", "-r", str(fps_i),
            "-i", "pipe:0", "-vf", "vflip", "-an", "-c:v", "libx264",
            "-preset", "ultrafast", "-tune", "zerolatency", "-profile:v", "baseline",
            "-pix_fmt", "yuv420p", "-bf", "0", "-g", str(gop),
            "-keyint_min", str(gop), "-sc_threshold", "0", "-crf", str(crf),
            "-x264-params", "aud=1:repeat-headers=1:bframes=0:rc-lookahead=0:sync-lookahead=0",
            # Packet lengths let the reader publish this frame immediately.
            # Raw Annex B needs the next AUD to delimit the previous frame.
            "-fflags", "nobuffer", "-flush_packets", "1",
            "-flvflags", "no_duration_filesize+no_sequence_end", "-f", "flv", "pipe:1",
        ]
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL)
        except OSError as exc:
            log.error("no se pudo arrancar libx264: %s", exc)
            return False
        self._proc, self._size, self._quality = proc, (width, height), quality
        self._drain_queue(); self._drain_capture_stamps()
        self._writer = threading.Thread(target=self._write_loop, args=(proc,), name="btr-h264-w", daemon=True)
        self._reader = threading.Thread(target=self._read_loop, args=(proc,), name="btr-h264-r", daemon=True)
        self._writer.start(); self._reader.start()
        log.info("encoder libx264 low-latency %dx%d crf=%d", width, height, crf)
        return True

    def _read_loop(self, proc: subprocess.Popen) -> None:
        stdout = proc.stdout
        assert stdout is not None
        try:
            for unit in flv_access_units(stdout):
                self._publish_au(unit)
        except (OSError, ValueError, EOFError):
            pass

    def _publish_au(self, data: bytes) -> None:
        try:
            captured_at = self._capture_stamps.get_nowait()
        except queue.Empty:
            captured_at = time.time()
        encode_ms = max(0.0, (time.time() - captured_at) * 1000.0)
        self._last_encode_ms = encode_ms
        self._max_encode_ms = max(self._max_encode_ms, encode_ms)
        self._encoded += 1
        self.frames.publish(data, captured_at)


class VideoEncoder:
    """Alimenta H.264 preferido y JPEG fallback desde una sola captura GPU."""

    def __init__(self, jpeg_frames: FrameBuffer, h264_frames: FrameBuffer):
        self.jpeg = JpegEncoder(jpeg_frames)
        self.h264 = H264Encoder(h264_frames)
        self._wanted: set[str] = set()

    @property
    def stats(self) -> dict:
        return {"active": sorted(self._wanted), "h264": self.h264.stats, "mjpeg": self.jpeg.stats}

    def ensure(self, width: int, height: int, fps: float, quality: int,
               formats: set[str] | None = None) -> bool:
        wanted = {"h264", "mjpeg"} if formats is None else formats
        h264_ok = self.h264.ensure(width, height, fps, quality) if "h264" in wanted else False
        jpeg_ok = self.jpeg.ensure(width, height, fps, quality) if "mjpeg" in wanted else False
        # No terminamos procesos desde el hilo principal al cambiar de cliente:
        # terminate/join puede bloquear Blender. Un encoder inactivo queda dormido
        # sin recibir raw frames y se reutiliza o se cierra al parar el stream.
        self._wanted = ({"h264"} if h264_ok else set()) | ({"mjpeg"} if jpeg_ok else set())
        return h264_ok or jpeg_ok

    def submit(self, raw: bytes, captured_at: float | None = None) -> None:
        stamp = time.time() if captured_at is None else captured_at
        if "h264" in self._wanted and self.h264.running:
            self.h264.submit(raw, stamp)
        if "mjpeg" in self._wanted and self.jpeg.running:
            self.jpeg.submit(raw, stamp)

    def stop(self) -> None:
        self._wanted.clear()
        self.h264.stop(); self.jpeg.stop()
