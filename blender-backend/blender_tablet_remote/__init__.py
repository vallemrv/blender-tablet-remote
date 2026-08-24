"""Blender Tablet Remote — servidor WebSocket para controlar Blender desde una tablet.

Instalable como extensión (Blender 4.2+) o como add-on clásico.
"""

from __future__ import annotations

import os

VERSION = (0, 1, 0)
from .protocol import PROTOCOL_VERSION

bl_info = {
    "name": "Blender Tablet Remote",
    "author": "blender_remoto",
    "version": VERSION,
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Remote",
    "description": "Servidor WebSocket para controlar Blender desde un cliente táctil Android",
    "category": "System",
}

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8765
DEFAULT_STREAM_PORT = 8766
TOKEN_ENV_VAR = "BLENDER_REMOTE_TOKEN"

import bpy  # noqa: E402
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty  # noqa: E402

from . import bridge, log  # noqa: E402


def _resolve_token(prefs) -> str:
    """El token del entorno gana: permite no guardarlo en las preferencias."""
    return os.environ.get(TOKEN_ENV_VAR, "") or (prefs.token if prefs else "")


def _stream_config(prefs) -> dict:
    if prefs is None:
        return {"enabled": True, "port": DEFAULT_STREAM_PORT}
    return {
        "enabled": prefs.stream_enabled,
        "port": prefs.stream_port,
        "fps": prefs.stream_fps,
        "max_width": prefs.stream_max_width,
        "quality": prefs.stream_quality,
        "capture_mode": prefs.stream_capture_mode,
    }


def get_prefs():
    try:
        return bpy.context.preferences.addons[__package__].preferences
    except (KeyError, AttributeError):
        return None


class BTRPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    host: StringProperty(
        name="Host",
        description=(
            "Interfaz de escucha. 0.0.0.0 escucha en todas; "
            "pon la IP de WireGuard (p.ej. 10.0.0.8) para restringirlo a la VPN"
        ),
        default=DEFAULT_HOST,
    )
    port: IntProperty(name="Puerto", default=DEFAULT_PORT, min=1024, max=65535)
    token: StringProperty(
        name="Token",
        description=f"Token de acceso. Si está vacío se usa la variable de entorno {TOKEN_ENV_VAR}",
        default="",
        subtype="PASSWORD",
    )
    autostart: BoolProperty(
        name="Arrancar con Blender",
        description="Levantar el servidor automáticamente al iniciar Blender",
        default=False,
    )
    verbose: BoolProperty(
        name="Log detallado",
        description="Registra también gestos y eventos (mucho ruido en consola)",
        default=False,
    )

    stream_enabled: BoolProperty(
        name="Enviar vídeo del viewport",
        description="Captura el viewport 3D y lo sirve como MJPEG",
        default=True,
    )
    stream_port: IntProperty(
        name="Puerto de vídeo",
        description="Puerto HTTP del stream, distinto del de control",
        default=DEFAULT_STREAM_PORT,
        min=1024,
        max=65535,
    )
    stream_fps: IntProperty(
        name="FPS",
        description="Fotogramas por segundo objetivo. Cada frame cuesta tiempo del hilo principal de Blender",
        default=24,
        min=1,
        max=60,
    )
    stream_max_width: IntProperty(
        name="Ancho máximo",
        description="El viewport se escala a este ancho conservando la proporción",
        default=1280,
        min=320,
        max=2560,
    )
    stream_quality: IntProperty(
        name="Calidad JPEG",
        description="Menos calidad = menos ancho de banda y menos latencia",
        default=70,
        min=20,
        max=95,
    )
    stream_capture_mode: EnumProperty(
        name="Fuente de captura",
        description="POST_PIXEL intenta incluir overlays y gizmos; Offscreen es el modo compatible",
        items=(
            ("POST_PIXEL", "Viewport real (experimental)", "Lee el framebuffer compuesto de la región"),
            ("OFFSCREEN", "Offscreen compatible", "Captura estable sin gizmos de interfaz"),
        ),
        default="OFFSCREEN",
    )

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, "host")
        col.prop(self, "port")
        col.prop(self, "token")
        if os.environ.get(TOKEN_ENV_VAR):
            col.label(text=f"Usando {TOKEN_ENV_VAR} del entorno", icon="CHECKMARK")
        elif not self.token:
            col.label(text="Sin token: cualquiera en la red puede controlar Blender", icon="ERROR")
        col.prop(self, "autostart")
        col.prop(self, "verbose")

        box = layout.box()
        box.label(text="Vídeo del viewport", icon="CAMERA_DATA")
        box.prop(self, "stream_enabled")
        sub = box.column()
        sub.enabled = self.stream_enabled
        sub.prop(self, "stream_port")
        sub.prop(self, "stream_fps")
        sub.prop(self, "stream_max_width")
        sub.prop(self, "stream_quality")
        sub.prop(self, "stream_capture_mode")
        if self.stream_port == self.port:
            box.label(text="El puerto de vídeo debe ser distinto al de control", icon="ERROR")


class BTR_OT_start(bpy.types.Operator):
    bl_idname = "btr.start_server"
    bl_label = "Arrancar servidor remoto"
    bl_description = "Levanta el servidor WebSocket"

    @classmethod
    def poll(cls, context):
        return not bridge.is_running()

    def execute(self, context):
        prefs = get_prefs()
        host = prefs.host if prefs else DEFAULT_HOST
        port = prefs.port if prefs else DEFAULT_PORT
        try:
            bridge.start(
                host,
                port,
                _resolve_token(prefs),
                verbose=bool(prefs and prefs.verbose),
                stream=_stream_config(prefs),
            )
        except OSError as exc:
            self.report({"ERROR"}, f"No se pudo abrir {host}:{port} — {exc}")
            return {"CANCELLED"}
        except RuntimeError as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
        _start_keepalive()
        self.report({"INFO"}, f"Escuchando en ws://{host}:{port}")
        return {"FINISHED"}


class BTR_OT_stop(bpy.types.Operator):
    bl_idname = "btr.stop_server"
    bl_label = "Parar servidor remoto"

    @classmethod
    def poll(cls, context):
        return bridge.is_running()

    def execute(self, context):
        bridge.stop()
        self.report({"INFO"}, "Servidor detenido")
        return {"FINISHED"}


class BTR_OT_keepalive(bpy.types.Operator):
    """Mantiene el bucle de eventos de Blender despierto mientras el servidor corre.

    `bpy.app.timers` solo avanza al ritmo al que Blender procesa su bucle, y ese
    ritmo se desploma a ~1 Hz cuando la ventana no se está dibujando (tapada, en
    otro escritorio, o según el compositor). Medido: 1 Hz en esas condiciones
    frente a ~55 Hz normales, lo que dejaría el vídeo y los comandos inservibles
    justo en el caso de uso real: mirar la tablet y no el monitor del PC.

    Un `event_timer_add` inyecta eventos reales en la cola, que Blender sí procesa
    con independencia del dibujado (medido: 60,0 Hz estables). Este operador no
    hace trabajo: solo late para que el pump del bridge corra a su ritmo.
    """

    bl_idname = "btr.keepalive"
    bl_label = "Blender Tablet Remote: mantener activo"
    bl_options = {"INTERNAL"}

    _timer = None

    def modal(self, context, event):
        if not bridge.is_running():
            return self.cancel(context)
        # PASS_THROUGH: no robamos ningún evento al usuario, que sigue usando
        # Blender con normalidad mientras la tablet está conectada.
        return {"PASS_THROUGH"}

    def execute(self, context):
        wm = context.window_manager
        window = context.window
        if window is None:
            return {"CANCELLED"}
        self._timer = wm.event_timer_add(1.0 / 60.0, window=window)
        wm.modal_handler_add(self)
        log.info("keepalive running")
        return {"RUNNING_MODAL"}

    def cancel(self, context):
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        log.info("keepalive stopped")


def _start_keepalive() -> None:
    """Sin interfaz (tests, --background) no hay bucle de eventos que mantener."""
    if bpy.app.background:
        return
    try:
        bpy.ops.btr.keepalive("INVOKE_DEFAULT")
    except RuntimeError as exc:
        log.warn("keepalive unavailable, video may stutter when Blender is idle: %s", exc)


class BTR_PT_panel(bpy.types.Panel):
    bl_label = "Tablet Remote"
    bl_idname = "BTR_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Remote"

    def draw(self, context):
        layout = self.layout
        status = bridge.status()

        if status["running"]:
            box = layout.box()
            box.label(text=f"ws://{status['host']}:{status['port']}", icon="URL")
            box.label(text=f"Clientes: {status['clients']}", icon="COMMUNITY")
            for peer in status["peers"]:
                box.label(text=peer, icon="DOT")
            if not status["auth"]:
                box.label(text="Sin token", icon="ERROR")

            stream = status.get("stream", {})
            sbox = layout.box()
            if stream.get("running"):
                sbox.label(text=f"Vídeo :{stream['port']}", icon="CAMERA_DATA")
                res = stream.get("resolution") or [0, 0]
                sbox.label(text=f"{res[0]}x{res[1]}  ·  {stream.get('fps_actual', 0)} fps")
                sbox.label(text=f"{stream.get('last_bytes', 0) // 1024} KB/frame  ·  {stream.get('clients', 0)} viendo")
                if stream.get("errors"):
                    sbox.label(text=f"errores de captura: {stream['errors']}", icon="ERROR")
            else:
                sbox.label(text="Vídeo desactivado", icon="CAMERA_DATA")

            layout.operator(BTR_OT_stop.bl_idname, icon="PAUSE")
            row = layout.row()
            row.label(text=f"cmds: {status['commands_run']}  err: {status['errors']}")
        else:
            layout.label(text="Servidor detenido", icon="RADIOBUT_OFF")
            layout.operator(BTR_OT_start.bl_idname, icon="PLAY")


CLASSES = (BTRPreferences, BTR_OT_start, BTR_OT_stop, BTR_OT_keepalive, BTR_PT_panel)


def _autostart():
    prefs = get_prefs()
    if prefs and prefs.autostart and not bridge.is_running():
        try:
            bridge.start(
                prefs.host,
                prefs.port,
                _resolve_token(prefs),
                verbose=prefs.verbose,
                stream=_stream_config(prefs),
            )
        except OSError as exc:
            log.error("autostart failed: %s", exc)
            return None
        _start_keepalive()
    return None


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.app.timers.register(_autostart, first_interval=1.0)


def unregister():
    bridge.stop()
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
