"""Streaming del viewport (Fase 2 del plan).

Dos piezas que no se conocen entre sí más que por un buffer de un frame:

    _pump() [hilo principal]        threads HTTP
        │                                │
    capture.tick()  ── JPEG ──▶  FrameBuffer  ──▶  mjpeg.StreamServer
    (bpy + gpu aquí)                              (aquí NO se toca bpy)

El plan (§89) admite MJPEG para el prototipo y pide sustituirlo luego por WebRTC.
El límite de MJPEG es el ancho de banda: cada frame va completo, sin predicción
entre fotogramas. Dentro de WireGuard en LAN da de sobra para validar la app.
"""

from __future__ import annotations

from .capture import ViewportCapture
from .encoder import H264Encoder, JpegEncoder, VideoEncoder, h264_available
from .frames import FrameBuffer
from .mjpeg import StreamServer

__all__ = ["ViewportCapture", "JpegEncoder", "H264Encoder", "VideoEncoder", "h264_available", "FrameBuffer", "StreamServer"]
