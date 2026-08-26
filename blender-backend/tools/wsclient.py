"""Cliente WebSocket mínimo en stdlib. Lo usan el CLI y los tests.

No pretende ser completo: habla lo justo con nuestro servidor (texto JSON, ping/pong,
close) y evita añadir dependencias para poder ejecutarse con el Python de Blender.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import struct
import time

OP_TEXT = 0x1
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA

# Duplicado a propósito respecto a wsserver.GUID: este cliente tiene que funcionar
# fuera de Blender (CLI, CI) y el paquete del add-on importa bpy al cargarse.
# run_tests.py comprueba que ambas copias coinciden con el vector del RFC 6455.
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class WSError(RuntimeError):
    pass


class WSClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 8765, token: str = "", timeout: float = 5.0):
        self.host = host
        self.port = port
        self.token = token
        self.timeout = timeout
        self.sock: socket.socket | None = None
        self.rfile = None
        self._msg_id = 0

    # ------------------------------------------------------------ conexión

    def connect(self) -> dict:
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self.sock.settimeout(self.timeout)
        self.rfile = self.sock.makefile("rb")

        key = base64.b64encode(os.urandom(16)).decode()
        path = "/"
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(request.encode())

        raw = b""
        while b"\r\n\r\n" not in raw:
            chunk = self.rfile.read(1)
            if not chunk:
                raise WSError("Connection closed during handshake")
            raw += chunk
        if b"101" not in raw.split(b"\r\n")[0]:
            raise WSError(f"Handshake failed: {raw.split(chr(13).encode())[0]!r}")

        # Validamos Sec-WebSocket-Accept igual que OkHttp. Si este cliente se lo
        # salta, un servidor que calcule mal el accept parece sano aquí y falla
        # únicamente en Android, que es justo el sitio donde peor se diagnostica.
        import hashlib

        expected = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        got = None
        for line in raw.split(b"\r\n\r\n")[0].decode("latin-1").split("\r\n")[1:]:
            if line.lower().startswith("sec-websocket-accept:"):
                got = line.split(":", 1)[1].strip()
        if got != expected:
            raise WSError(f"Sec-WebSocket-Accept inválido: esperaba {expected!r}, llegó {got!r}")

        hello = self.recv()
        if self.token and hello.get("auth_required") and not hello.get("authenticated"):
            reply = self.request({"type": "auth", "token": self.token})
            if not reply.get("ok"):
                raise WSError(f"Auth failed: {reply.get('error')}")
        return hello

    def close(self) -> None:
        if self.sock is None:
            return
        try:
            self._send_frame(OP_CLOSE, struct.pack("!H", 1000))
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass
        self.sock = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.close()

    # ------------------------------------------------------------- mensajes

    def send(self, msg: dict) -> None:
        if self.token:
            msg.setdefault("token", self.token)
        self._send_frame(OP_TEXT, json.dumps(msg).encode())

    def recv(self, timeout: float | None = None) -> dict:
        if timeout is not None:
            self.sock.settimeout(timeout)
        try:
            while True:
                opcode, payload = self._recv_frame()
                if opcode == OP_TEXT:
                    return json.loads(payload.decode())
                if opcode == OP_PING:
                    self._send_frame(OP_PONG, payload)
                elif opcode == OP_CLOSE:
                    raise WSError("Server closed the connection")
        finally:
            if timeout is not None and self.sock is not None:
                self.sock.settimeout(self.timeout)

    def request(self, msg: dict, timeout: float | None = None) -> dict:
        """Envía y espera la respuesta con el mismo id, ignorando eventos por medio."""
        self._msg_id += 1
        msg.setdefault("id", str(self._msg_id))
        self.send(msg)
        deadline = time.monotonic() + (timeout or self.timeout)
        while time.monotonic() < deadline:
            reply = self.recv(timeout=max(0.05, deadline - time.monotonic()))
            if reply.get("type") == "response" and reply.get("id") == msg["id"]:
                return reply
        raise WSError(f"Timeout waiting for response to {msg.get('command', msg.get('type'))}")

    def command(self, name: str, payload: dict | None = None, timeout: float | None = None) -> dict:
        return self.request({"type": "command", "command": name, "payload": payload or {}}, timeout)

    def gesture(self, gesture: str, phase: str, **kwargs) -> None:
        self.send({"type": "gesture", "gesture": gesture, "phase": phase, **kwargs})

    def drain_events(self, seconds: float = 0.2) -> list[dict]:
        """Recoge los eventos que hayan llegado durante `seconds`."""
        events = []
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                msg = self.recv(timeout=max(0.01, deadline - time.monotonic()))
            except (socket.timeout, TimeoutError):
                # Un reader de socket queda envenenado tras cualquier timeout
                # (Python 3.14: "cannot read from timed out object"): se rehace
                # antes de seguir, que el socket en sí sigue sano.
                self._rebuild_reader()
                break
            if msg.get("type") == "event":
                events.append(msg)
        return events

    def _rebuild_reader(self) -> None:
        if self.sock is None:
            return
        if self.rfile is not None:
            try:
                self.rfile.close()
            except OSError:
                pass
        self.rfile = self.sock.makefile("rb")

    # --------------------------------------------------------------- frames

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        if self.sock is None:
            raise WSError("Not connected")
        header = bytearray([0x80 | opcode])
        mask = os.urandom(4)
        n = len(payload)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += struct.pack("!H", n)
        else:
            header.append(0x80 | 127)
            header += struct.pack("!Q", n)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def _recv_frame(self) -> tuple[int, bytes]:
        header = self._read_exact(2)
        opcode = header[0] & 0x0F
        masked = bool(header[1] & 0x80)
        length = header[1] & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._read_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._read_exact(8))[0]
        mask = self._read_exact(4) if masked else None
        payload = self._read_exact(length) if length else b""
        if mask:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        return opcode, payload

    def _read_exact(self, n: int) -> bytes:
        data = self.rfile.read(n)
        if not data or len(data) < n:
            raise WSError("Connection closed while reading frame")
        return data
