"""Servidor WebSocket (RFC 6455) en stdlib puro.

El Python empaquetado con Blender no trae `websockets` ni `aiohttp`, y no queremos
obligar a instalar paquetes dentro de la instalación de Blender del usuario. Este
módulo implementa el subconjunto del protocolo que necesitamos: handshake HTTP,
frames de texto, ping/pong, close y fragmentación básica.

Nada de este módulo toca `bpy`: corre íntegramente en threads secundarios y se
comunica con el hilo principal de Blender a través de colas (ver bridge.py).
"""

from __future__ import annotations

import base64
import hashlib
import json
import queue
import socket
import struct
import threading
import time
from typing import Callable

from . import log

# RFC 6455 §1.3. El último grupo es C5AB0DC85B11: cuidado al teclearlo, una C
# perdida al principio hace que el servidor devuelva un Sec-WebSocket-Accept
# coherente consigo mismo pero inválido, y todo cliente que valide (OkHttp) lo
# rechaza. tests/run_tests.py comprueba el vector de ejemplo del RFC.
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

OP_CONT = 0x0
OP_TEXT = 0x1
OP_BIN = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA

MAX_PAYLOAD = 8 * 1024 * 1024  # 8 MB, más que de sobra para JSON de control
PING_INTERVAL = 20.0


class WSClient:
    """Una conexión. Un thread lee, otro escribe; el resto del add-on solo usa send_json()."""

    _next_id = 1
    _id_lock = threading.Lock()

    def __init__(self, sock: socket.socket, addr, server: "WSServer"):
        with WSClient._id_lock:
            self.id = WSClient._next_id
            WSClient._next_id += 1
        self.sock = sock
        self.addr = addr
        self.server = server
        self.authenticated = False
        self.handshake_token: str | None = None
        self.peer = f"{addr[0]}:{addr[1]}"

        self._outbox: queue.Queue[bytes | None] = queue.Queue(maxsize=512)
        self._closed = threading.Event()   # socket ya cerrado
        self._closing = threading.Event()  # cierre pedido, aún vaciando la cola
        self._torn = threading.Event()
        self._reader = threading.Thread(target=self._read_loop, name=f"ws-read-{self.id}", daemon=True)
        self._writer = threading.Thread(target=self._write_loop, name=f"ws-write-{self.id}", daemon=True)

    # ------------------------------------------------------------------ API

    def start(self) -> None:
        self._reader.start()
        self._writer.start()

    def send_json(self, obj: dict) -> None:
        self.send_text(json.dumps(obj, separators=(",", ":")))

    def send_text(self, text: str) -> None:
        if self._closing.is_set():
            return
        try:
            self._outbox.put_nowait(_encode_frame(OP_TEXT, text.encode("utf-8")))
        except queue.Full:
            # Cliente atascado: no dejamos crecer la cola indefinidamente.
            log.warn("client %s outbox full, dropping connection", self.peer)
            self.abort()

    def close(self, code: int = 1000, reason: str = "") -> None:
        """Cierre ordenado: el frame CLOSE va por la cola, detrás de lo pendiente.

        Importante para casos como "token inválido": el cliente debe recibir la
        respuesta de error ANTES de que le cerremos la conexión.
        """
        if self._closing.is_set():
            return
        self._closing.set()
        payload = struct.pack("!H", code) + reason.encode("utf-8")
        try:
            self._outbox.put_nowait(_encode_frame(OP_CLOSE, payload))
            self._outbox.put_nowait(None)
        except queue.Full:
            self.abort()

    def abort(self) -> None:
        """Cierre inmediato, sin vaciar la cola (errores de protocolo o parada)."""
        self._closing.set()
        self._closed.set()
        try:
            self._outbox.put_nowait(None)
        except queue.Full:
            pass
        self._shutdown_socket()

    def _shutdown_socket(self) -> None:
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass

    @property
    def closed(self) -> bool:
        return self._closing.is_set()

    # -------------------------------------------------------------- threads

    def _write_loop(self) -> None:
        last_ping = time.monotonic()
        while not self._closed.is_set():
            try:
                data = self._outbox.get(timeout=1.0)
            except queue.Empty:
                now = time.monotonic()
                if now - last_ping >= PING_INTERVAL:
                    last_ping = now
                    data = _encode_frame(OP_PING, b"")
                else:
                    continue
            if data is None:
                break
            try:
                self.sock.sendall(data)
            except OSError:
                break
        self._closed.set()
        self._shutdown_socket()
        self._teardown()

    def _read_loop(self) -> None:
        try:
            rfile = self.sock.makefile("rb")
        except OSError:
            self._teardown()
            return
        try:
            if not self._handshake(rfile):
                return
            log.info("Client connected %s (id=%d)", self.peer, self.id)
            self.server.on_connect(self)
            self._frame_loop(rfile)
        except (OSError, ValueError) as exc:
            log.debug("client %s read ended: %s", self.peer, exc)
        finally:
            self._teardown()

    def _handshake(self, rfile) -> bool:
        raw = bytearray()
        while b"\r\n\r\n" not in raw:
            chunk = rfile.read1(1024) if hasattr(rfile, "read1") else rfile.read(1)
            if not chunk:
                return False
            raw += chunk
            if len(raw) > 16384:
                return False

        head, _, rest = raw.partition(b"\r\n\r\n")
        if rest:
            # Cliente que envía el primer frame pegado al handshake: lo devolvemos al buffer.
            self._pending = bytes(rest)
        lines = head.decode("latin-1").split("\r\n")
        request = lines[0]
        headers = {}
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                # Conservamos la primera aparición. Algunos proxies/VPN de Android
                # pueden duplicar cabeceras durante el upgrade; para
                # Sec-WebSocket-Key la primera es la clave original con la que el
                # cliente validará Sec-WebSocket-Accept. Sobrescribirla con una
                # copia posterior hace que OkHttp rechace el handshake.
                headers.setdefault(k.strip().lower(), v.strip())

        parts = request.split(" ")
        path = parts[1] if len(parts) > 1 else "/"
        if "?" in path:
            self.handshake_token = _token_from_query(path.split("?", 1)[1])

        key = headers.get("sec-websocket-key")
        upgrade = headers.get("upgrade", "").lower()
        if not key or upgrade != "websocket":
            self._http_error(400, "Expected WebSocket upgrade")
            return False

        accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        response = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
        )
        self.sock.sendall(response.encode())
        return True

    def _http_error(self, code: int, msg: str) -> None:
        body = msg.encode()
        try:
            self.sock.sendall(
                f"HTTP/1.1 {code} {msg}\r\nContent-Length: {len(body)}\r\n"
                f"Content-Type: text/plain\r\nConnection: close\r\n\r\n".encode()
                + body
            )
        except OSError:
            pass

    def _frame_loop(self, rfile) -> None:
        pending = getattr(self, "_pending", b"")
        buf = _PrefixReader(rfile, pending)

        frag_op = None
        frag_data = bytearray()

        while not self._closed.is_set():
            header = buf.read_exact(2)
            if header is None:
                return
            b0, b1 = header[0], header[1]
            fin = bool(b0 & 0x80)
            opcode = b0 & 0x0F
            masked = bool(b1 & 0x80)
            length = b1 & 0x7F

            if length == 126:
                ext = buf.read_exact(2)
                if ext is None:
                    return
                length = struct.unpack("!H", ext)[0]
            elif length == 127:
                ext = buf.read_exact(8)
                if ext is None:
                    return
                length = struct.unpack("!Q", ext)[0]

            if length > MAX_PAYLOAD:
                self.close(1009, "Message too big")
                return

            mask_key = None
            if masked:
                mask_key = buf.read_exact(4)
                if mask_key is None:
                    return

            payload = buf.read_exact(length) if length else b""
            if payload is None:
                return
            if mask_key:
                payload = _unmask(payload, mask_key)

            if opcode == OP_CLOSE:
                self.close()
                return
            if opcode == OP_PING:
                try:
                    self._outbox.put_nowait(_encode_frame(OP_PONG, payload))
                except queue.Full:
                    pass
                continue
            if opcode == OP_PONG:
                continue

            if opcode == OP_CONT:
                if frag_op is None:
                    self.close(1002, "Unexpected continuation")
                    return
                frag_data += payload
                if fin:
                    self._deliver(frag_op, bytes(frag_data))
                    frag_op, frag_data = None, bytearray()
                continue

            if not fin:
                frag_op = opcode
                frag_data = bytearray(payload)
                continue

            self._deliver(opcode, payload)

    def _deliver(self, opcode: int, payload: bytes) -> None:
        if opcode != OP_TEXT:
            return  # binario reservado para vídeo en fases futuras
        try:
            msg = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.send_json({"type": "response", "ok": False, "error": f"Invalid JSON: {exc}"})
            return
        if not isinstance(msg, dict):
            self.send_json({"type": "response", "ok": False, "error": "Message must be a JSON object"})
            return
        self.server.on_message(self, msg)

    def _teardown(self) -> None:
        """Idempotente: lo llaman tanto el lector como el escritor al terminar."""
        if self._torn.is_set():
            return
        self._torn.set()
        self._closing.set()
        self._closed.set()
        try:
            self._outbox.put_nowait(None)
        except queue.Full:
            pass
        self._shutdown_socket()
        self.server.on_disconnect(self)


class _PrefixReader:
    """Lector con bytes pre-leídos por delante del socket."""

    def __init__(self, rfile, prefix: bytes = b""):
        self._rfile = rfile
        self._prefix = prefix

    def read_exact(self, n: int) -> bytes | None:
        out = b""
        if self._prefix:
            take = self._prefix[:n]
            self._prefix = self._prefix[len(take):]
            out = take
            n -= len(take)
        if n == 0:
            return out
        data = self._rfile.read(n)
        if not data or len(data) < n:
            return None
        return out + data


class WSServer:
    """Escucha en (host, port) y crea un WSClient por conexión."""

    def __init__(
        self,
        host: str,
        port: int,
        on_message: Callable[[WSClient, dict], None],
        on_connect: Callable[[WSClient], None] | None = None,
        on_disconnect: Callable[[WSClient], None] | None = None,
        max_clients: int = 8,
    ):
        self.host = host
        self.port = port
        self._on_message = on_message
        self._on_connect = on_connect
        self._on_disconnect = on_disconnect
        self.max_clients = max_clients

        self._clients: list[WSClient] = []
        self._lock = threading.Lock()
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # ------------------------------------------------------------------ API

    def start(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        sock.listen(8)
        sock.settimeout(0.5)
        self._sock = sock
        self._stop.clear()
        self._thread = threading.Thread(target=self._accept_loop, name="ws-accept", daemon=True)
        self._thread.start()
        log.info("Server listening on ws://%s:%d", self.host, self.port)

    def stop(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        for client in self.clients():
            client.close(1001, "Server shutting down")
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        log.info("Server stopped")

    def clients(self) -> list[WSClient]:
        with self._lock:
            return list(self._clients)

    def has_client(self, client: WSClient) -> bool:
        with self._lock:
            return client in self._clients

    def broadcast(self, obj: dict, only_authenticated: bool = True) -> None:
        for client in self.clients():
            if only_authenticated and not client.authenticated:
                continue
            client.send_json(obj)

    # ------------------------------------------------------------- callbacks

    def on_message(self, client: WSClient, msg: dict) -> None:
        self._on_message(client, msg)

    def on_connect(self, client: WSClient) -> None:
        with self._lock:
            self._clients.append(client)
        if self._on_connect:
            self._on_connect(client)

    def on_disconnect(self, client: WSClient) -> None:
        with self._lock:
            if client in self._clients:
                self._clients.remove(client)
            else:
                return
        log.info("Client disconnected %s (id=%d)", client.peer, client.id)
        if self._on_disconnect:
            self._on_disconnect(client)

    # ---------------------------------------------------------------- accept

    def _accept_loop(self) -> None:
        while not self._stop.is_set():
            sock = self._sock
            if sock is None:
                break
            try:
                conn, addr = sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            if len(self.clients()) >= self.max_clients:
                log.warn("max clients reached, rejecting %s", addr)
                try:
                    conn.close()
                except OSError:
                    pass
                continue
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            WSClient(conn, addr, self).start()


# --------------------------------------------------------------- utilidades


def _encode_frame(opcode: int, payload: bytes) -> bytes:
    header = bytearray()
    header.append(0x80 | opcode)
    n = len(payload)
    if n < 126:
        header.append(n)
    elif n < 65536:
        header.append(126)
        header += struct.pack("!H", n)
    else:
        header.append(127)
        header += struct.pack("!Q", n)
    return bytes(header) + payload


def _unmask(payload: bytes, key: bytes) -> bytes:
    n = len(payload)
    if n == 0:
        return b""
    if n < 512:
        mask = key * (n // 4 + 1)
        return bytes(a ^ b for a, b in zip(payload, mask))
    # XOR por bloques de 8 bytes: el bucle byte a byte de Python era O(n) interpretado
    # y con payloads grandes (selecciones con miles de índices) ahogaba al lector.
    out = bytearray(payload)
    view = memoryview(out)
    mask64 = int.from_bytes(key * 2, "big")
    full = n & ~7
    for off in range(0, full, 8):
        chunk = int.from_bytes(payload[off:off + 8], "big") ^ mask64
        view[off:off + 8] = chunk.to_bytes(8, "big")
    for i in range(full, n):
        out[i] ^= key[i & 3]
    return bytes(out)


def _token_from_query(query: str) -> str | None:
    for pair in query.split("&"):
        if pair.startswith("token="):
            from urllib.parse import unquote

            return unquote(pair[6:])
    return None
