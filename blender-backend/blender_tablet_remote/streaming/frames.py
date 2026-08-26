"""Buffer de frames compartido entre el hilo principal y los threads HTTP.

Hay dos formas de leer, y la diferencia importa:

`wait_newer()` conserva solo el último frame. Es lo correcto para MJPEG: cada JPEG es
independiente, así que un cliente lento debe saltar fotogramas en vez de acumular
retraso, que es la prioridad nº1 del plan (§109).

`subscribe()` da una cola propia por cliente. H.264 la necesita porque sus frames NO
son independientes: perder un solo access unit obliga a descartar hasta el siguiente
keyframe, lo que hace perder más, y se realimenta. Medido con el buffer de un hueco:
Blender capturaba 19 frames/s, el encoder producía 19 AU/s y al cliente llegaban 7,6
—el 61 % se quedaba por el camino— con saltos de secuencia continuos. La causa es que
entre dos vueltas del thread HTTP el encoder publica varios AUs y el buffer solo
guarda el último; basta que el GIL retrase al thread para empezar a perder.

Cuando una cola se llena (cliente realmente atascado) se vacía entera y se marca el
hueco: ahí sí toca esperar al siguiente keyframe, que es justo lo que hay que hacer.
"""

from __future__ import annotations

import collections
import threading

# ~2,5 s de vídeo a 24 fps. Suficiente para absorber un tirón del planificador sin
# convertirse en latencia acumulada: si un cliente se queda tan atrás, mejor cortar
# por lo sano y reengancharlo en el siguiente keyframe.
QUEUE_CAPACITY = 60


class FrameQueue:
    """Cola de un consumidor. La llena `FrameBuffer.publish` desde el encoder."""

    def __init__(self, capacity: int = QUEUE_CAPACITY) -> None:
        self._items: collections.deque = collections.deque()
        self._cond = threading.Condition()
        self._capacity = capacity
        self._gap = False
        self._closed = False

    def push(self, item: tuple[bytes, int, float]) -> None:
        with self._cond:
            if len(self._items) >= self._capacity:
                self._items.clear()
                self._gap = True
            self._items.append(item)
            self._cond.notify()

    def pop(self, timeout: float = 2.0) -> tuple[tuple[bytes, int, float] | None, bool]:
        """(frame, hubo_hueco). frame es None si expiró el plazo o se cerró."""
        with self._cond:
            if not self._items and not self._closed:
                self._cond.wait(timeout)
            if not self._items:
                return None, False
            gap, self._gap = self._gap, False
            return self._items.popleft(), gap

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()


class FrameBuffer:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._data: bytes = b""
        self._seq = 0
        self._stamp = 0.0
        self._subscribers: list[FrameQueue] = []

    # ------------------------------------------------------------- publicación

    def publish(self, data: bytes, stamp: float) -> None:
        with self._cond:
            self._data = data
            self._seq += 1
            self._stamp = stamp
            item = (data, self._seq, stamp)
            subscribers = list(self._subscribers)
            self._cond.notify_all()
        # Fuera del lock: `push` toma el suyo y no queremos anidarlos.
        for queue in subscribers:
            queue.push(item)

    # ------------------------------------------------- lectura latest-wins (MJPEG)

    def latest(self) -> tuple[bytes, int, float]:
        with self._lock:
            return self._data, self._seq, self._stamp

    def wait_newer(self, seq: int, timeout: float = 2.0) -> tuple[bytes, int, float]:
        """Bloquea hasta que haya un frame más nuevo que `seq`.

        Devuelve seq==0 si expira el plazo, para que el emisor decida si sigue vivo
        (mandando un keep-alive) o corta.
        """
        with self._cond:
            if self._seq <= seq:
                self._cond.wait(timeout)
            if self._seq <= seq:
                return b"", 0, 0.0
            return self._data, self._seq, self._stamp

    # ----------------------------------------------------- suscripción (H.264)

    def subscribe(self, capacity: int = QUEUE_CAPACITY) -> FrameQueue:
        queue = FrameQueue(capacity)
        with self._cond:
            self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: FrameQueue) -> None:
        with self._cond:
            if queue in self._subscribers:
                self._subscribers.remove(queue)
        queue.close()

    @property
    def subscribers(self) -> int:
        with self._lock:
            return len(self._subscribers)

    def wake_all(self) -> None:
        """Desbloquea a los que esperan (al parar el servidor)."""
        with self._cond:
            subscribers = list(self._subscribers)
            self._cond.notify_all()
        for queue in subscribers:
            queue.close()
