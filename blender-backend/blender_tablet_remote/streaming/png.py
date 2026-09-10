"""Encode GPU RGBA rows as a PNG; independent of ffmpeg and streaming viewers."""
import struct
import zlib


def encode_png(rgba, width, height):
    if len(rgba) != width*height*4:
        raise ValueError('Invalid RGBA frame size')
    def chunk(kind, data):
        return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
    stride=width*4
    rows=b''.join(b'\0'+rgba[y*stride:(y+1)*stride] for y in range(height-1,-1,-1))
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',width,height,8,6,0,0,0))+
            chunk(b'IDAT',zlib.compress(rows,4))+chunk(b'IEND',b''))
