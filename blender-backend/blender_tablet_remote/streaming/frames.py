"""Buffer de un solo frame compartido entre el hilo principal y los threads HTTP.

Guardamos únicamente el último frame: si un cliente va lento preferimos que salte
fotogramas antes que acumular latencia, que es la prioridad nº1 del plan (§109).
"""

from __future__ import annotations

import threading


class FrameBuffer:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._data: bytes = b""
        self._seq = 0
        self._stamp = 0.0

    def publish(self, data: bytes, stamp: float) -> None:
        with self._cond:
            self._data = data
            self._seq += 1
            self._stamp = stamp
            self._cond.notify_all()

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

    def wake_all(self) -> None:
        """Desbloquea a los que esperan (al parar el servidor)."""
        with self._cond:
            self._cond.notify_all()
