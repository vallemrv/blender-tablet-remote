"""Framing HTTP de access units H.264 para MediaCodec.

No toca Blender: el encoder publica AUs completos en un buffer latest-frame-wins y
los threads HTTP solo empaquetan el último. El header estable está en protocol.md §11.
"""

from __future__ import annotations

import struct

MAGIC = b"BTRH"
VERSION = 1
HEADER_SIZE = 32
FLAG_CONFIG = 1
FLAG_KEYFRAME = 2
CONTENT_TYPE = "application/x-btr-h264"


def nal_types(annex_b: bytes) -> set[int]:
    """Devuelve tipos NAL de un access unit Annex B (start codes 3/4 bytes)."""
    result: set[int] = set()
    start = annex_b.find(b"\x00\x00\x01")
    while start >= 0:
        pos = start + 3
        if pos >= len(annex_b):
            break
        result.add(annex_b[pos] & 0x1F)
        start = annex_b.find(b"\x00\x00\x01", pos + 1)
    return result


def flags_for(annex_b: bytes) -> int:
    types = nal_types(annex_b)
    return (FLAG_CONFIG if 7 in types and 8 in types else 0) | (FLAG_KEYFRAME if 5 in types else 0)


def pack_header(seq: int, stamp: float, payload_len: int, width: int, height: int,
                flags: int) -> bytes:
    return struct.pack(">4sBBHIQIII", MAGIC, VERSION, flags, HEADER_SIZE,
                       seq & 0xFFFFFFFF, max(0, int(stamp * 1_000_000)),
                       payload_len, width, height)


def split_access_units(buffer: bytes, final: bool = False) -> tuple[list[bytes], bytes]:
    """Separa por AUD. ffmpeg se configura con ``aud=1``.

    Conserva el último AU incompleto salvo al cerrar el proceso.
    """
    starts: list[int] = []
    # bytes.find scans in native code. A Python iteration per compressed byte
    # held the GIL for tens of milliseconds on detailed/subdivided viewports.
    marker = b"\x00\x00\x01\x09"
    pos = buffer.find(marker)
    while pos >= 0:
        starts.append(pos - 1 if pos and buffer[pos - 1] == 0 else pos)
        pos = buffer.find(marker, pos + len(marker))
    if not starts:
        return [], buffer
    units = [buffer[starts[n]:starts[n + 1]] for n in range(len(starts) - 1)]
    if final:
        units.append(buffer[starts[-1]:])
        return units, b""
    return units, buffer[starts[-1]:]
