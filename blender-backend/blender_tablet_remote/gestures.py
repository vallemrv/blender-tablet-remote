"""Gestos continuos con coalescing.

Un arrastre en la tablet genera cientos de eventos por segundo. Aplicar uno a uno
sería inviable (y llenaría la pila de undo). En su lugar:

  gesture.begin  -> abre la sesión, marca punto de undo si el gesto modifica datos
  gesture.update -> SOLO acumula (dx/dy se suman, factor se multiplica)
  gesture.end    -> aplica lo que quede y cierra con un único paso de undo

El acumulado se aplica una vez por tick del timer del hilo principal, así que la
frecuencia real de trabajo dentro de Blender es la del timer, no la del dedo.
"""

from __future__ import annotations

import bpy

from mathutils import Vector

from . import log
from .bpy_utils import require_rv3d, undo_push
from .camera import camera
from .commands import transform as transform_cmds
from .commands import view as view_cmds
from .errors import BadPayload


def _sync_camera():
    """Asegura que la cámara de la tablet está inicializada antes de usarla."""
    camera.sync_from_region(require_rv3d())


def _has_transform_target() -> bool:
    """¿Hay algo realmente seleccionado que transformar?

    En Edit Mode manda la selección de malla, que ya comprueban los comandos.
    """
    active = bpy.context.view_layer.objects.active
    if active is not None and active.mode == "EDIT":
        return True
    return any(o.select_get() for o in bpy.context.view_layer.objects)

def _modal_active() -> bool:
    """¿Hay una transformación modal abierta? Import diferido: modal usa gestures."""
    from .commands.modal import session

    return session.active


VIEW_GESTURES = {"orbit", "pan", "zoom", "roll"}
TRANSFORM_GESTURES = {"move", "rotate", "scale"}
ALL_GESTURES = VIEW_GESTURES | TRANSFORM_GESTURES

class _Accumulator:
    __slots__ = ("dx", "dy", "factor", "dirty")

    def __init__(self):
        self.dx = 0.0
        self.dy = 0.0
        self.factor = 1.0
        self.dirty = False

    def add(self, dx: float, dy: float, factor: float) -> None:
        self.dx += dx
        self.dy += dy
        self.factor *= factor
        self.dirty = True

    def take(self) -> tuple[float, float, float]:
        values = (self.dx, self.dy, self.factor)
        self.dx = 0.0
        self.dy = 0.0
        self.factor = 1.0
        self.dirty = False
        return values

class GestureManager:
    """Una sesión de gesto por cliente y tipo. Todo corre en el hilo principal."""

    def __init__(self):
        self._acc: dict[tuple[int, str], _Accumulator] = {}
        self._open: set[tuple[int, str]] = set()
        self._options: dict[tuple[int, str], dict] = {}

    def reset(self) -> None:
        self._acc.clear()
        self._open.clear()
        self._options.clear()

    def drop_client(self, client_id: int) -> None:
        for key in [k for k in self._open if k[0] == client_id]:
            self._close(key)

    # ---------------------------------------------------------------- entrada

    def handle(self, client_id: int, msg: dict) -> None:
        gesture = str(msg.get("gesture", "")).lower()
        phase = str(msg.get("phase", "update")).lower()
        if gesture not in ALL_GESTURES:
            raise BadPayload(f"Unknown gesture '{gesture}'. Options: {', '.join(sorted(ALL_GESTURES))}")
        if phase not in {"begin", "update", "end", "cancel"}:
            raise BadPayload("'phase' must be begin, update, end or cancel")

        key = (client_id, gesture)

        if phase == "begin":
            self._acc[key] = _Accumulator()
            self._open.add(key)
            self._options[key] = {
                "space": msg.get("space", "GLOBAL"),
                "pivot": msg.get("pivot"),
                "axis": msg.get("axis"),
            }
            log.debug("gesture %s begin", gesture)
            return

        if phase == "cancel":
            self._close(key)
            return

        acc = self._acc.get(key)
        if acc is None:
            # update sin begin: lo tratamos como sesión implícita, la tablet puede
            # perder el begin si se reconecta a mitad de arrastre.
            acc = self._acc[key] = _Accumulator()
            self._open.add(key)
            self._options.setdefault(key, {})

        acc.add(
            _num(msg.get("dx", 0.0)),
            _num(msg.get("dy", 0.0)),
            _num(msg.get("factor", 1.0), default=1.0),
        )

        if phase == "end":
            self.flush()
            self._close(key)
            # Con una transformación modal viva, soltar el dedo NO la cierra: se
            # confirma a mano desde la barra. Cerrar aquí impediría recolocar la
            # mano a mitad de un desplazamiento largo.
            if gesture in TRANSFORM_GESTURES and not _modal_active():
                undo_push(f"Remote {gesture}")
            log.debug("gesture %s end", gesture)

    # ----------------------------------------------------------------- salida

    def flush(self) -> None:
        """Aplica todo lo acumulado. Se llama una vez por tick."""
        for (_client_id, gesture), acc in self._acc.items():
            if not acc.dirty:
                continue
            # El coalescing ya evita reproducir una cola de previews antiguas: se
            # aplica una sola vez el desplazamiento total recibido desde el tick
            # anterior. Recortarlo y descartar el exceso hacía que, precisamente
            # cuando la red agrupaba mensajes, el objeto recorriera mucha menos
            # distancia que el dedo y la transformación pareciera extremadamente
            # lenta.
            dx, dy, factor = acc.take()
            key = (_client_id, gesture)
            try:
                self._apply(gesture, dx, dy, factor, self._options.get(key, {}))
            except Exception as exc:  # un gesto roto no debe tumbar el pump
                log.error("gesture %s failed: %s", gesture, exc)

    def _apply(self, gesture: str, dx: float, dy: float, factor: float, options: dict) -> None:
        if gesture == "orbit":
            view_cmds.orbit_delta(dx, dy)
        elif gesture == "pan":
            view_cmds.pan_delta(dx, dy)
        elif gesture == "zoom":
            view_cmds.zoom_factor(factor)
        elif gesture == "roll":
            # El ángulo de rueda viaja acumulado en `dx` (radianes).
            view_cmds.roll_delta(dx)
        elif gesture in TRANSFORM_GESTURES and _modal_active():
            # La sesión manda: ella sabe de ejes, incrementos y valor acumulado, y
            # el modo lo eligió la barra, no el gesto que llegue.
            from .commands.modal import session

            session.nudge(dx, dy)
            session.apply()
        elif gesture in TRANSFORM_GESTURES and not _has_transform_target():
            # Sin selección no se transforma NADA. `resolve_objects` cae al objeto
            # activo cuando no hay selección, y el cubo por defecto de Blender es
            # activo sin estar seleccionado: bastaba arrastrar para moverlo sin
            # querer, creyendo que estabas navegando.
            log.debug("gesture %s ignored: nothing selected", gesture)
        elif gesture == "move":
            self._move(dx, dy, options)
        elif gesture == "rotate":
            self._rotate(dx, options)
        elif gesture == "scale":
            transform_cmds.scale({"factor": factor, "_no_undo": True, **_clean(options)})

    def _move(self, dx: float, dy: float, options: dict) -> None:
        """Arrastre en pantalla -> desplazamiento en el plano de la vista.

        La vista de referencia es la de la tablet (camera.py), que es la que el
        usuario está viendo; la del PC puede estar mirando a otro sitio.
        """
        rv3d = require_rv3d()
        camera.sync_from_region(rv3d)
        right = camera.rotation @ Vector((1.0, 0.0, 0.0))
        up = camera.rotation @ Vector((0.0, 1.0, 0.0))
        # Mismo cálculo que el paneo de cámara: el objeto sigue al dedo.
        span_x, span_y = camera.screen_span(camera.projection_matrix(rv3d))
        delta = right * (dx * span_x) - up * (dy * span_y)

        axis = options.get("axis")
        if axis in {"X", "Y", "Z"}:
            index = {"X": 0, "Y": 1, "Z": 2}[axis]
            magnitude = delta[index]
            delta = Vector((0.0, 0.0, 0.0))
            delta[index] = magnitude

        transform_cmds.move({"vector": list(delta), "space": "GLOBAL", "_no_undo": True})

    def _rotate(self, dx: float, options: dict) -> None:
        """Giro alrededor del eje de visión (o de un eje fijo si se pidió)."""
        axis = options.get("axis")
        if axis in {"X", "Y", "Z"}:
            vector = {"X": [1, 0, 0], "Y": [0, 1, 0], "Z": [0, 0, 1]}[axis]
        else:
            _sync_camera()
            vector = list(camera.rotation @ Vector((0.0, 0.0, 1.0)))
        transform_cmds.rotate(
            {
                "axis": vector,
                "angle": dx * view_cmds.ORBIT_SENSITIVITY,
                "radians": True,
                "_no_undo": True,
                **_clean(options),
            }
        )

    def _close(self, key) -> None:
        self._acc.pop(key, None)
        self._options.pop(key, None)
        self._open.discard(key)


def _num(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clean(options: dict) -> dict:
    """Solo pasamos a los comandos las opciones que entienden y que están puestas."""
    out = {}
    if options.get("pivot"):
        out["pivot"] = options["pivot"]
    return out
