"""Pure Python framing checks: python blender-backend/tests/test_h264_stream.py."""
import importlib.util
import random
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location('wire',Path(__file__).resolve().parents[1]/'blender_tablet_remote/streaming/h264.py')
wire=importlib.util.module_from_spec(spec);spec.loader.exec_module(wire)

class H264StreamTests(unittest.TestCase):
    def test_chunks_preserve_complete_units_and_partial_tail(self):
        rng=random.Random(123)
        units=[]
        for index in range(25):
            start=b'\x00\x00\x01' if index%2 else b'\x00\x00\x00\x01'
            # Legal escaped RBSP: no embedded start code in slice data.
            body=rng.randbytes(45000 if index%5 else 200000).replace(b'\0\0',b'\0\0\x03')+b'\x80'
            units.append(start+b'\x09\xf0'+start+(b'\x65' if index%5==0 else b'\x41')+body)
        source=b''.join(units)
        pending=b'';received=[];offset=0
        while offset<len(source):
            length=rng.randint(1,65536)
            ready,pending=wire.split_access_units(pending+source[offset:offset+length])
            received.extend(ready);offset+=length
        ready,pending=wire.split_access_units(pending,final=True)
        received.extend(ready)
        self.assertEqual(received,units)
        self.assertEqual(pending,b'')

    def test_every_start_code_split_and_partial_headers(self):
        first=b'\0\0\0\1\x09\xf0\0\0\1\x65\x80'
        second=b'\0\0\1\x09\xf0\0\0\0\1\x41\x80'
        source=first+second
        for cut in range(len(source)+1):
            ready,pending=wire.split_access_units(source[:cut])
            rest,pending=wire.split_access_units(pending+source[cut:],final=True)
            self.assertEqual(ready+rest,[first,second])
        self.assertEqual(wire.nal_types(b'\0\0\1'),set())

    def test_configuration_keyframe_and_inter_frames(self):
        config=b'\0\0\0\1\x67\x80\0\0\1\x68\x80'
        key=b'\0\0\0\1\x65'+b'\x55'*200000
        self.assertEqual(wire.flags_for(config+key),wire.FLAG_CONFIG|wire.FLAG_KEYFRAME)
        self.assertEqual(wire.flags_for(b'\0\0\1\x41\x80'),0)
        self.assertEqual(wire.nal_types(config+key),{7,8,5})

if __name__=='__main__':unittest.main()
