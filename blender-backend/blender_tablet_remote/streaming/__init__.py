"""Streaming del viewport.

Dos piezas que no se conocen entre sí más que por un buffer de un frame:

    _pump() [hilo principal]        threads HTTP
        │                                │
    capture.tick()  ── JPEG ──▶  FrameBuffer  ──▶  mjpeg.StreamServer
    (bpy + gpu aquí)                              (aquí NO se toca bpy)

MJPEG permanece como fallback de H.264. Su límite es el ancho de banda: cada frame va
completo, sin predicción entre fotogramas.
"""

from __future__ import annotations

from .capture import ViewportCapture
from .encoder import H264Encoder, JpegEncoder, VideoEncoder, h264_available
from .frames import FrameBuffer
from .mjpeg import StreamServer

__all__ = ["ViewportCapture", "JpegEncoder", "H264Encoder", "VideoEncoder", "h264_available", "FrameBuffer", "StreamServer"]
