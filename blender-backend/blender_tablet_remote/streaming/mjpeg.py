"""Servidor HTTP que sirve el viewport como MJPEG.

Corre íntegramente en threads secundarios: aquí NO se toca `bpy` ni `gpu`, solo se
lee el último frame del FrameBuffer.

Rutas:
    /                una página mínima para comprobar el stream desde el navegador
    /stream.mjpg     multipart/x-mixed-replace, el que consume Android
    /frame.jpg       un único fotograma (útil para depurar con curl)
    /stats.json      métricas de captura
"""

from __future__ import annotations

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .. import log
from .frames import FrameBuffer

BOUNDARY = "btrframe"
# Si en 2 s no hay frame nuevo (Blender parado, nadie mueve nada) reenviamos el
# último para que el cliente no confunda "escena quieta" con "conexión muerta".
IDLE_RESEND = 2.0
# Cuánto sigue considerándose "hay interés" tras pedir un fotograma suelto.
FRAME_INTEREST = 3.0
# Arrancar ffmpeg desde cero y capturar el primer fotograma no es instantáneo.
FIRST_FRAME_WAIT = 5.0


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # El log por defecto escribe en stderr por cada petición; usamos el nuestro.
    def log_message(self, fmt, *args):  # noqa: A003
        log.debug("mjpeg %s - %s", self.address_string(), fmt % args)

    @property
    def _server(self) -> "StreamServer":
        return self.server.stream_server  # type: ignore[attr-defined]

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if not self._server.authorize(query.get("token", [""])[0]):
            self._send_bytes(401, b"Unauthorized", "text/plain")
            return

        route = parsed.path.rstrip("/") or "/"
        if route == "/stream.mjpg":
            self._serve_stream()
        elif route == "/frame.jpg":
            self._serve_single()
        elif route == "/stats.json":
            body = json.dumps(self._server.stats_provider()).encode()
            self._send_bytes(200, body, "application/json")
        elif route == "/":
            self._send_bytes(200, _TEST_PAGE, "text/html; charset=utf-8")
        else:
            self._send_bytes(404, b"Not found", "text/plain")

    # ------------------------------------------------------------------ rutas

    def _send_bytes(self, code: int, body: bytes, content_type: str) -> None:
        try:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except OSError:
            pass

    def _serve_single(self) -> None:
        # Marcamos interés ANTES de esperar: sin espectadores la captura está parada,
        # así que primero hay que pedirle a Blender que vuelva a capturar.
        self._server.touch()
        data, seq, _ = self._server.frames.latest()
        # Generoso a propósito: si la captura estaba parada hay que esperar a que
        # Blender vuelva a capturar Y a que arranque ffmpeg.
        fresh, fresh_seq, _ = self._server.frames.wait_newer(seq, timeout=FIRST_FRAME_WAIT)
        if fresh_seq:
            data, seq = fresh, fresh_seq
        if not seq:
            self._send_bytes(503, b"No frame yet", "text/plain")
            return
        self._send_bytes(200, data, "image/jpeg")

    def _serve_stream(self) -> None:
        try:
            self.send_response(200)
            self.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={BOUNDARY}")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
        except OSError:
            return

        log.info("mjpeg client connected: %s", self.address_string())
        self._server.clients_delta(+1)
        seq = 0
        try:
            while not self._server.stopping:
                data, new_seq, stamp = self._server.frames.wait_newer(seq, timeout=IDLE_RESEND)
                if not new_seq:
                    # Sin frame nuevo: reenviamos el último como keep-alive.
                    data, new_seq, stamp = self._server.frames.latest()
                    if not new_seq:
                        continue
                seq = new_seq
                # El timestamp viaja en una cabecera propia para que el cliente
                # pueda medir latencia extremo a extremo (§40) sin canal aparte.
                head = (
                    f"--{BOUNDARY}\r\n"
                    f"Content-Type: image/jpeg\r\n"
                    f"Content-Length: {len(data)}\r\n"
                    f"X-Timestamp: {stamp:.3f}\r\n"
                    f"X-Frame: {seq}\r\n\r\n"
                ).encode()
                self.wfile.write(head)
                self.wfile.write(data)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
        except (OSError, ValueError):
            pass  # el cliente cerró; es lo normal al salir de la app
        finally:
            self._server.clients_delta(-1)
            log.info("mjpeg client gone: %s", self.address_string())


class _ThreadingServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        # Una desconexión brusca del cliente no es un error digno de traza.
        log.debug("mjpeg connection error from %s", client_address)


class StreamServer:
    def __init__(self, frames: FrameBuffer, stats_provider):
        self.frames = frames
        self.stats_provider = stats_provider
        self.host = ""
        self.port = 0
        self.stopping = False
        self._token = ""
        self._httpd: _ThreadingServer | None = None
        self._thread: threading.Thread | None = None
        self._clients = 0
        self._clients_lock = threading.Lock()
        self._last_request = 0.0

    # --------------------------------------------------------------------- API

    def start(self, host: str, port: int, token: str = "") -> None:
        if self._httpd is not None:
            raise RuntimeError("Stream server already running")
        self._token = token or ""
        self.stopping = False
        httpd = _ThreadingServer((host, port), _Handler)
        httpd.stream_server = self  # type: ignore[attr-defined]
        httpd.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._httpd = httpd
        self.host, self.port = host, port
        self._thread = threading.Thread(target=httpd.serve_forever, name="btr-mjpeg", daemon=True)
        self._thread.start()
        log.info("Viewport stream on http://%s:%d/stream.mjpg", host, port)

    def stop(self) -> None:
        self.stopping = True
        self.frames.wake_all()
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        with self._clients_lock:
            self._clients = 0
        log.info("Viewport stream stopped")

    def is_running(self) -> bool:
        return self._httpd is not None

    def authorize(self, token: str) -> bool:
        return not self._token or token == self._token

    def clients_delta(self, delta: int) -> None:
        with self._clients_lock:
            self._clients = max(0, self._clients + delta)

    @property
    def clients(self) -> int:
        with self._clients_lock:
            return self._clients

    def touch(self) -> None:
        """Alguien pidió un fotograma suelto: cuenta como interés durante un rato."""
        self._last_request = time.monotonic()

    def wanted(self) -> bool:
        """¿Merece la pena capturar? Con nadie mirando, Blender no gasta GPU."""
        return self.clients > 0 or (time.monotonic() - self._last_request) < FRAME_INTEREST


_TEST_PAGE = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>Blender Tablet Remote</title>
<style>
 body{margin:0;background:#121212;color:#ddd;font:14px system-ui,sans-serif;
      display:flex;flex-direction:column;height:100vh}
 header{padding:8px 14px;background:#1e1e1e;display:flex;gap:18px;align-items:center}
 b{color:#e87d3e}
 img{flex:1;min-height:0;object-fit:contain;background:#000}
</style></head><body>
<header><b>Blender Tablet Remote</b><span id="s">conectando...</span></header>
<img id="v" src="stream.mjpg" alt="viewport">
<script>
 const img=document.getElementById('v'), s=document.getElementById('s');
 img.onload=()=>{s.textContent='streaming';};
 img.onerror=()=>{s.textContent='sin stream (revisa el token o que la captura este activa)';};
 setInterval(async()=>{try{const r=await fetch('stats.json'+location.search);
   const j=await r.json();
   s.textContent=`${j.resolution?.join('x')||'-'} · ${j.fps_actual} fps · `+
                 `${(j.last_bytes/1024).toFixed(0)} KB/frame · ${j.last_cost_ms} ms captura`;
 }catch(e){}},1000);
</script></body></html>
""".encode("utf-8")
