"""Puente entre el servidor WebSocket (threads) y Blender (hilo principal).

Regla de oro: `bpy` SOLO se toca desde el timer `_pump()`, que Blender ejecuta en su
hilo principal. Los threads del servidor únicamente meten mensajes en una cola.
"""

from __future__ import annotations

import queue
import time
import traceback

import bpy

from . import commands, log, screen, state
from .camera import camera as _camera
from .errors import AuthError, CommandError, UnknownCommand
from .gestures import GestureManager
from .streaming import FrameBuffer, StreamServer, ViewportCapture, h264_available
from .wsserver import WSClient, WSServer

# Cola de entrada: (cliente, mensaje). Escriben los threads, lee el hilo principal.
_inbox: "queue.Queue[tuple[WSClient, dict]]" = queue.Queue(maxsize=4096)

_server: WSServer | None = None
_watcher = state.StateWatcher()
_gestures = GestureManager()
_frames = FrameBuffer()
_h264_frames = FrameBuffer()
_capture = ViewportCapture(_frames, _h264_frames, has_viewers=lambda: _stream.wanted(),
                           wanted_formats=lambda: _stream.formats_wanted())
_stream = StreamServer(_frames, lambda: _capture.stats(), _h264_frames)
_token: str = ""
_timer_registered = False
_last_event_poll = 0.0
_last_modal_status: dict | None = None
_stats = {"commands": 0, "gestures": 0, "errors": 0, "started_at": 0.0}

DEFAULT_STREAM_PORT = 8766
EVENT_POLL_INTERVAL = 0.1  # 10 Hz para detectar cambios de estado
TICK_ACTIVE = 1.0 / 60.0
TICK_IDLE = 0.25
MAX_MESSAGES_PER_TICK = 256

# Estos comandos representan una acción discreta cuya confirmación visual no debe
# esperar al siguiente intervalo del stream. Las actualizaciones continuas quedan
# fuera deliberadamente: forzar una captura por cada transform.nudge/value anularía
# el límite de FPS y monopolizaría el hilo principal con renders.
IMMEDIATE_FRAME_COMMANDS = {
    "selection.pick",
    "selection.elements",
    "selection.all",
    "selection.box",
    "selection.circle",
    "selection.loop",
    "selection.ring",
    "selection.invert",
    "selection.hide",
    "selection.reveal",
    "object.select",
    "transform.begin",
    "transform.confirm",
    "transform.cancel",
    # Colocar el corte con el toque es una acción discreta: su preview no debe
    # esperar al siguiente hueco de fps.
    "tool.begin",
    "tool.loop_pick",
}


# --------------------------------------------------------------------- ciclo


def start(
    host: str,
    port: int,
    token: str = "",
    verbose: bool = False,
    stream: dict | None = None,
) -> None:
    global _server, _token

    if _server is not None:
        raise RuntimeError("Server already running")

    commands.load_all()
    log.set_level(2 if verbose else 1)

    _token = token or ""
    if not _token:
        log.warn("no token configured: any client on the network can control Blender")

    _watcher.reset()
    _gestures.reset()
    # Cada sesión arranca mirando donde mira el PC; a partir de ahí van por libre.
    _camera.reset()
    _stats.update({"commands": 0, "gestures": 0, "errors": 0, "started_at": time.time()})

    server = WSServer(
        host,
        port,
        on_message=_enqueue,
        on_connect=_on_connect,
        on_disconnect=_on_disconnect,
    )
    server.start()
    _server = server
    _start_stream(host, stream or {})
    _register_timer()
    log.info("Commands available: %d", len(commands.REGISTRY))


def _start_stream(host: str, cfg: dict) -> None:
    """El stream es opcional: si su puerto está ocupado, el control sigue vivo."""
    _capture.configure(
        enabled=bool(cfg.get("enabled", True)),
        fps=cfg.get("fps", 24),
        max_width=cfg.get("max_width", 1280),
        quality=cfg.get("quality", 70),
        mode=cfg.get("capture_mode", "OFFSCREEN"),
    )
    if not _capture.enabled:
        return
    try:
        _stream.start(host, int(cfg.get("port", DEFAULT_STREAM_PORT)), _token)
    except OSError as exc:
        _capture.enabled = False
        log.error("viewport stream disabled, cannot bind port %s: %s", cfg.get("port"), exc)


def stop() -> None:
    global _server
    _unregister_timer()
    # Antes que nada: el pump ya no va a correr, y es quien suelta la inhibición.
    # Dejarla puesta significaría dejar la pantalla del usuario sin ahorro de energía.
    screen.keep_awake(False)
    if _stream.is_running():
        _stream.stop()
    # shutdown() libera recursos GPU y solo es seguro en el hilo principal, que es
    # donde corren los operadores que llaman a stop().
    _capture.shutdown()
    if _server is not None:
        _server.stop()
        _server = None
    _gestures.reset()
    while not _inbox.empty():
        try:
            _inbox.get_nowait()
        except queue.Empty:
            break


def is_running() -> bool:
    return _server is not None


def reset_session() -> None:
    """
    Tras cargar otro .blend nada de lo cacheado sigue valiendo: la cámara apunta a
    una escena que ya no existe, los gestos a objetos borrados y el watcher compara
    contra un estado de otro archivo.
    """
    global _last_modal_status
    from .commands.modal import session

    # La sesión modal guarda matrices de objetos del archivo anterior: restaurarlas
    # sobre la escena nueva sería escribir en punteros muertos.
    session.reset()
    from .commands.tools import tool_session
    # No restaurar sobre el archivo recién cargado; solo liberar el backup viejo.
    tool_session.close()
    _last_modal_status = None
    _watcher.reset()
    _gestures.reset()
    _camera.reset()
    from .commands.view import reset_local_view
    reset_local_view()


def status() -> dict:
    if _server is None:
        return {"running": False}
    clients = _server.clients()
    return {
        "running": True,
        "host": _server.host,
        "port": _server.port,
        "clients": len(clients),
        "peers": [c.peer for c in clients],
        "auth": bool(_token),
        "uptime": time.time() - _stats["started_at"],
        "commands_run": _stats["commands"],
        "gestures_run": _stats["gestures"],
        "errors": _stats["errors"],
        "stream": stream_info(),
    }


def configure_stream(
    enabled: bool | None = None,
    fps: float | None = None,
    max_width: int | None = None,
    quality: int | None = None,
) -> dict:
    """Reajusta el vídeo en caliente. Lo que llegue como None se queda igual."""
    _capture.configure(
        enabled=_capture.enabled if enabled is None else enabled,
        fps=_capture.fps if fps is None else fps,
        max_width=_capture.max_width if max_width is None else max_width,
        quality=_capture.quality if quality is None else quality,
        mode=_capture.mode,
    )
    return stream_info()


def stream_info() -> dict:
    """Lo que Android necesita para abrir el vídeo. Se manda en el 'hello'."""
    h264 = h264_available()
    info = {
        "running": _stream.is_running(),
        "port": _stream.port,
        "path": "/stream.h264" if h264 else "/stream.mjpg",
        "format": "h264" if h264 else "mjpeg",
        "clients": _stream.clients,
    }
    if h264:
        info.update({"framing": "btr-h264-v1", "codec": "avc1.42C01F",
                     "alternatives": [{"format": "mjpeg", "path": "/stream.mjpg"}]})
    info.update(_capture.stats())
    return info


# ------------------------------------------------------------ threads -> cola


def _enqueue(client: WSClient, msg: dict) -> None:
    """Llamado desde el thread lector. Prohibido tocar bpy aquí."""
    try:
        _inbox.put_nowait((client, msg))
    except queue.Full:
        _stats["errors"] += 1
        log.warn("inbox full, dropping message from %s", client.peer)


def _on_connect(client: WSClient) -> None:
    if not _token:
        client.authenticated = True
    elif client.handshake_token and client.handshake_token == _token:
        client.authenticated = True
        log.info("Client %s authenticated via handshake", client.peer)

    client.send_json(
        {
            "type": "hello",
            "server": "Blender Tablet Remote",
            "blender": bpy.app.version_string,
            "auth_required": bool(_token),
            "authenticated": client.authenticated,
            # El cliente descubre el vídeo aquí en vez de configurarlo a mano (§63).
            "stream": stream_info(),
        }
    )
    if client.authenticated:
        _enqueue(client, {"type": "_send_state"})


def _on_disconnect(client: WSClient) -> None:
    _enqueue(client, {"type": "_client_gone", "client_id": client.id})


# ---------------------------------------------------- hilo principal (timer)


def _register_timer() -> None:
    global _timer_registered
    if not _timer_registered:
        bpy.app.timers.register(_pump, first_interval=0.05, persistent=True)
        _timer_registered = True


def _unregister_timer() -> None:
    global _timer_registered
    if _timer_registered:
        try:
            bpy.app.timers.unregister(_pump)
        except ValueError:
            pass
        _timer_registered = False


def _pump() -> float | None:
    """Timer de Blender: drena la cola, aplica gestos y difunde eventos."""
    global _last_event_poll

    if _server is None:
        return None  # desregistra el timer

    processed = 0
    ran_command = False
    while processed < MAX_MESSAGES_PER_TICK:
        try:
            client, msg = _inbox.get_nowait()
        except queue.Empty:
            break
        processed += 1
        if (str(msg.get("type", "")).lower() == "command"
                and msg.get("command") in IMMEDIATE_FRAME_COMMANDS):
            ran_command = True
        try:
            _handle(client, msg)
        except Exception:  # noqa: BLE001 - el pump nunca debe morir
            _stats["errors"] += 1
            log.error("unhandled error while processing message:\n%s", traceback.format_exc())

    try:
        _gestures.flush()
    except Exception:  # noqa: BLE001
        _stats["errors"] += 1
        log.error("gesture flush failed:\n%s", traceback.format_exc())

    # Tras aplicar gestos y comandos, para que el frame refleje ya el cambio. Un
    # comando discreto de selección/sesión fuerza un frame inmediato; los arrastres
    # continuos siguen el ritmo de fps para no saturar el hilo principal.
    if ran_command:
        _capture.request_frame()
    _capture.tick()

    now = time.monotonic()
    if now - _last_event_poll >= EVENT_POLL_INTERVAL:
        _last_event_poll = now
        _broadcast_events()

    # Un cliente de vídeo sin sesión WebSocket (el navegador de pruebas) también
    # cuenta: si no, el ritmo cae a TICK_IDLE y el stream baja a 4 fps.
    busy = _server.clients() or _stream.clients
    # Con la pantalla del PC apagada, Blender se bloquea al redibujar y este timer deja
    # de correr: el mismo `busy` decide si hay que impedir que se apague (ver screen.py).
    # En background no hay ventana que se bloquee, así que no hay por qué tocar la
    # pantalla de nadie: importa sobre todo para no manosearla durante los tests.
    screen.keep_awake(bool(busy) and not bpy.app.background)
    return TICK_ACTIVE if busy else TICK_IDLE


def _broadcast_events() -> None:
    if _server is None:
        return
    try:
        events = _watcher.poll()
    except Exception:  # noqa: BLE001
        log.error("state poll failed:\n%s", traceback.format_exc())
        return
    for event in events:
        log.debug("event %s", event["event"])
        _server.broadcast(event)
    _broadcast_modal()


def _broadcast_modal() -> None:
    """Cuánto se lleva movido/girado/escalado, para el marcador de la barra.

    Va por el canal de eventos y no como respuesta al gesto: responder a cada
    arrastre saturaría el canal de vuelta, que es justo lo que evita que los gestos
    lleven id. A 10 Hz el número se lee perfectamente.
    """
    global _last_modal_status
    from .commands.modal import session

    status = session.status()
    if status == _last_modal_status:
        return
    _last_modal_status = status
    _server.broadcast({"type": "event", "event": "transform.session", "payload": status})


# ------------------------------------------------------------------ dispatch


def _handle(client: WSClient, msg: dict) -> None:
    kind = str(msg.get("type", "command")).lower()

    if kind == "_client_gone":
        _gestures.drop_client(msg["client_id"])
        from .commands.modal import session
        session.owner_disconnected(msg["client_id"])
        from .commands.tools import tool_session
        tool_session.owner_disconnected(msg["client_id"])
        return
    if kind == "_send_state":
        client.send_json({"type": "event", "event": "scene.changed", "payload": state.snapshot()})
        return
    if kind == "auth":
        _handle_auth(client, msg)
        return
    if kind == "ping":
        client.send_json({"type": "pong", "id": msg.get("id")})
        return

    if not _authorized(client, msg):
        _respond(client, msg, False, error="Authentication required", code="auth_required")
        return

    if kind == "gesture":
        try:
            _gestures.handle(client.id, msg)
            _stats["gestures"] += 1
        except CommandError as exc:
            _respond(client, msg, False, error=exc.message, code=exc.code)
        return

    if kind == "command":
        _handle_command(client, msg)
        return

    _respond(client, msg, False, error=f"Unknown message type '{kind}'", code="bad_type")


def _handle_auth(client: WSClient, msg: dict) -> None:
    if not _token:
        client.authenticated = True
        _respond(client, msg, True, result={"authenticated": True, "auth_required": False})
        return
    if str(msg.get("token", "")) == _token:
        client.authenticated = True
        log.info("Client %s authenticated", client.peer)
        _respond(client, msg, True, result={"authenticated": True})
        client.send_json({"type": "event", "event": "scene.changed", "payload": state.snapshot()})
    else:
        log.warn("Client %s failed authentication", client.peer)
        _respond(client, msg, False, error="Invalid token", code="auth_failed")
        client.close(1008, "Invalid token")


def _authorized(client: WSClient, msg: dict) -> bool:
    if client.authenticated:
        return True
    if not _token:
        client.authenticated = True
        return True
    # Token por mensaje: cómodo para clientes sin estado (CLI, curl).
    if str(msg.get("token", "")) == _token:
        client.authenticated = True
        return True
    return False


def _handle_command(client: WSClient, msg: dict) -> None:
    name = msg.get("command")
    if not name:
        _respond(client, msg, False, error="Missing 'command'", code="bad_payload")
        return

    func = commands.get(name)
    if func is None:
        exc = UnknownCommand(name)
        _respond(client, msg, False, error=exc.message, code=exc.code)
        return

    payload = msg.get("payload") or {}
    if not isinstance(payload, dict):
        _respond(client, msg, False, error="'payload' must be an object", code="bad_payload")
        return
    # Metadato interno no serializado por el cliente. Permite que las máquinas
    # modales impidan que una segunda conexión altere una sesión ajena.
    payload = dict(payload)
    payload["_client_id"] = client.id

    log.info("command %s", name)
    try:
        result = func(payload)
    except CommandError as exc:
        _stats["errors"] += 1
        log.warn("command %s failed: %s", name, exc.message)
        _respond(client, msg, False, error=exc.message, code=exc.code)
        return
    except Exception as exc:  # noqa: BLE001
        _stats["errors"] += 1
        log.error("command %s crashed:\n%s", name, traceback.format_exc())
        _respond(client, msg, False, error=f"{type(exc).__name__}: {exc}", code="internal_error")
        return

    _stats["commands"] += 1
    _respond(client, msg, True, result=result)
    log.info("command complete %s", name)


def _respond(client: WSClient, msg: dict, ok: bool, result=None, error: str = "", code: str = "") -> None:
    response = {"type": "response", "id": msg.get("id"), "ok": ok}
    if ok:
        if result is not None:
            response["result"] = result
    else:
        response["error"] = error
        if code:
            response["code"] = code
    client.send_json(response)


def broadcast_event(name: str, payload: dict) -> None:
    """Para que otras partes del add-on emitan eventos (p.ej. operadores de la UI)."""
    if _server is not None:
        _server.broadcast({"type": "event", "event": name, "payload": payload})


__all__ = ["start", "stop", "is_running", "status", "broadcast_event", "AuthError"]
