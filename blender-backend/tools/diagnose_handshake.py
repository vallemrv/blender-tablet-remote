"""Captura una sola petición WebSocket para diagnosticar clientes Android."""

import base64
import hashlib
import json
import socket
from pathlib import Path


HOST = "0.0.0.0"
PORT = 8766
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
RESULT = Path("/tmp/blender_remote_handshake.json")


with socket.socket() as server:
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(1)
    connection, address = server.accept()
    with connection:
        data = b""
        while b"\r\n\r\n" not in data and len(data) < 16384:
            chunk = connection.recv(4096)
            if not chunk:
                break
            data += chunk

        request = data.decode("latin-1", "replace")
        keys = []
        for line in request.split("\r\n")[1:]:
            if ":" not in line:
                continue
            name, value = line.split(":", 1)
            if name.strip().lower() == "sec-websocket-key":
                keys.append(value.strip())

        accept = None
        if keys:
            digest = hashlib.sha1((keys[0] + GUID).encode()).digest()
            accept = base64.b64encode(digest).decode()
            response = (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
            )
            connection.sendall(response.encode())

        RESULT.write_text(
            json.dumps(
                {
                    "client": [address[0], address[1]],
                    "request": request,
                    "keys": keys,
                    "accept": accept,
                },
                indent=2,
            )
        )
