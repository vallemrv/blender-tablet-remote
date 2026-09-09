"""Pure Python packet framing checks: python blender-backend/tests/test_h264_stream.py."""
import importlib.util
import io
import random
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location('wire',Path(__file__).resolve().parents[1]/'blender_tablet_remote/streaming/h264.py')
wire=importlib.util.module_from_spec(spec);spec.loader.exec_module(wire)
START=b'\0\0\0\1'
HEADER=b'FLV\x01\x01\0\0\0\x09\0\0\0\0'
SPS=b'\x67\x42\0\x1e'
PPS=b'\x68\x80'

def tag(payload, kind=9):
    return bytes([kind])+len(payload).to_bytes(3,'big')+bytes(7)+payload+(11+len(payload)).to_bytes(4,'big')

def config(length_size=4):
    data=b'\x01\x42\0\x1e'+bytes([0xfc | (length_size-1),0xe1])+len(SPS).to_bytes(2,'big')+SPS+b'\x01'+len(PPS).to_bytes(2,'big')+PPS
    return tag(b'\x17\0\0\0\0'+data)

def frame(nals, key=False, length_size=4):
    return tag(bytes([0x17 if key else 0x27,1,0,0,0])+b''.join(len(n).to_bytes(length_size,'big')+n for n in nals))

class Fragments(io.BytesIO):
    def __init__(self, data, maximum):
        super().__init__(data);self.maximum=maximum
    def read(self,size=-1):
        return super().read(min(size,self.maximum))

class H264StreamTests(unittest.TestCase):
    def test_complete_frame_is_emitted_without_next_frame_or_eof(self):
        source=HEADER+config()+frame([b'\x09\xf0',b'\x65\x80'],key=True)
        class LivePipe(io.BytesIO):
            def read(self,size=-1):
                if self.tell()==len(source):raise AssertionError('Waited for the following frame')
                return super().read(size)
        unit=next(wire.flv_access_units(LivePipe(source)))
        self.assertEqual(wire.nal_types(unit),{9,7,8,5})
        self.assertTrue(unit.startswith(START+b'\x09'))

    def test_fragmented_tags_preserve_all_frames_and_configuration(self):
        rng=random.Random(123)
        units=[];encoded=[]
        for index in range(25):
            body=rng.randbytes(45000 if index%5 else 200000).replace(b'\0\0',b'\0\0\x03')+b'\x80'
            nals=[b'\x09\xf0',(b'\x65' if index%5==0 else b'\x41')+body]
            encoded.append(frame(nals,key=index%5==0))
            if index%5==0:nals[1:1]=[SPS,PPS]
            units.append(b''.join(START+n for n in nals))
        stream=HEADER+tag(b'metadata',18)+config()+b''.join(encoded)+tag(b'\x17\x02\0\0\0')
        self.assertEqual(list(wire.flv_access_units(Fragments(stream,137))),units)

    def test_small_fragment_boundaries_and_variable_nal_lengths(self):
        for length_size in (1,2,4):
            data=HEADER+config(length_size)+frame([b'\x65\x80'],True,length_size)
            for maximum in range(1,18):
                with self.subTest(length_size=length_size,fragment=maximum):
                    self.assertEqual(list(wire.flv_access_units(Fragments(data,maximum))),[START+SPS+START+PPS+START+b'\x65\x80'])

    def test_truncated_or_invalid_packet_is_not_published(self):
        data=HEADER+config()+frame([b'\x65\x80'],True)
        for cut in range(len(HEADER)+len(config())+1,len(data)):
            with self.assertRaises(EOFError):list(wire.flv_access_units(io.BytesIO(data[:cut])))
        with self.assertRaises(ValueError):list(wire.flv_access_units(io.BytesIO(data[:-1]+b'\0')))
        with self.assertRaises(ValueError):list(wire.flv_access_units(io.BytesIO(HEADER+frame([b'\x65\x80'],True))))
        with self.assertRaises(ValueError):list(wire.flv_access_units(io.BytesIO(HEADER+config()+tag(b'\x27\1\0\0\0\0\0\xff\xffx'))))

    def test_configuration_keyframe_and_inter_frames(self):
        config_bytes=START+b'\x67\x80\0\0\1\x68\x80'
        key=START+b'\x65'+b'\x55'*200000
        self.assertEqual(wire.flags_for(config_bytes+key),wire.FLAG_CONFIG|wire.FLAG_KEYFRAME)
        self.assertEqual(wire.flags_for(b'\0\0\1\x41\x80'),0)
        self.assertEqual(wire.nal_types(config_bytes+key),{7,8,5})
        self.assertEqual(wire.nal_types(b'\0\0\1'),set())

if __name__=='__main__':unittest.main()
