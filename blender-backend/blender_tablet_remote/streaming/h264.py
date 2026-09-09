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


def _read_exact(stream, size):
    data = bytearray()
    while len(data) < size:
        chunk = stream.read(size - len(data))
        if not chunk:
            if not data:
                return None
            raise EOFError('Truncated encoder packet')
        data.extend(chunk)
    return bytes(data)


def _required(stream, size):
    data = _read_exact(stream, size)
    if data is None:
        raise EOFError('Truncated encoder packet')
    return data


def _avc_config(data):
    if len(data) < 7 or data[0] != 1:
        raise ValueError('Invalid AVC configuration')
    length_size = (data[4] & 3) + 1
    if length_size not in (1, 2, 4):
        raise ValueError('Invalid AVC NAL length size')
    position, headers = 6, []
    counts = [data[5] & 31]
    for group in range(2):
        if group:
            if position >= len(data):
                raise ValueError('Missing AVC picture parameter sets')
            counts.append(data[position]); position += 1
        for _ in range(counts[group]):
            if position + 2 > len(data):
                raise ValueError('Truncated AVC configuration')
            size = int.from_bytes(data[position:position + 2], 'big'); position += 2
            if not size or position + size > len(data):
                raise ValueError('Invalid AVC parameter set length')
            headers.append(b'\x00\x00\x00\x01' + data[position:position + size])
            position += size
    if not all(counts):
        raise ValueError('Missing AVC parameter sets')
    return length_size, b''.join(headers)


def flv_access_units(stream):
    """Read complete ffmpeg packets without waiting for the following frame.

    FLV is private pipe framing, never sent to Android. Its tag size marks the
    end of each AVC packet; the HTTP channel continues to carry Annex B AUs.
    Metadata/configuration tags consume no capture timestamp.
    """
    header = _read_exact(stream, 9)
    if header is None:
        return
    if header[:4] != b'FLV\x01':
        raise ValueError('Invalid FLV header')
    offset = int.from_bytes(header[5:9], 'big')
    if not 9 <= offset <= 4096:
        raise ValueError('Invalid FLV data offset')
    _required(stream, offset - 9 + 4)
    length_size, config = None, b''
    while True:
        tag = _read_exact(stream, 11)
        if tag is None:
            return
        size = int.from_bytes(tag[1:4], 'big')
        payload = _required(stream, size)
        previous_size = int.from_bytes(_required(stream, 4), 'big')
        if previous_size != size + 11:
            raise ValueError('Invalid FLV tag size')
        if tag[0] != 9:
            continue
        if len(payload) < 5 or payload[0] & 15 != 7:
            raise ValueError('Expected AVC video in encoder output')
        packet_type = payload[1]
        if packet_type == 0:
            length_size, config = _avc_config(payload[5:])
        elif packet_type == 1:
            if length_size is None:
                raise ValueError('AVC frame before configuration')
            position, nals = 5, []
            while position < len(payload):
                if position + length_size > len(payload):
                    raise ValueError('Truncated AVC NAL length')
                size = int.from_bytes(payload[position:position + length_size], 'big')
                position += length_size
                if not size or position + size > len(payload):
                    raise ValueError('Invalid AVC NAL length')
                nals.append(b'\x00\x00\x00\x01' + payload[position:position + size])
                position += size
            if not nals:
                raise ValueError('Empty AVC frame')
            unit = b''.join(nals)
            # Reconnecting clients must receive SPS/PPS with every keyframe.
            if payload[0] >> 4 == 1 and flags_for(unit) & FLAG_CONFIG == 0:
                insert_at = 1 if nals[0][4] & 31 == 9 else 0
                nals.insert(insert_at, config)
                unit = b''.join(nals)
            yield unit
        elif packet_type != 2:  # AVC end of sequence has no picture.
            raise ValueError('Unknown AVC packet type')
