"""Actual ffmpeg: single-frame delivery, timestamps and Annex B decoding."""
import importlib
import shutil
import subprocess
import sys
import time
import types
import unittest
from pathlib import Path

# Load only streaming's pure Python modules, without initializing bpy/gpu.
root=Path(__file__).resolve().parents[1]/'blender_tablet_remote'
for name,path in [('encoder_test_package',root),('encoder_test_package.streaming',root/'streaming')]:
    package=types.ModuleType(name);package.__path__=[str(path)];sys.modules[name]=package
encoder_module=importlib.import_module('encoder_test_package.streaming.encoder')
frames_module=importlib.import_module('encoder_test_package.streaming.frames')
wire=importlib.import_module('encoder_test_package.streaming.h264')

@unittest.skipUnless(shutil.which('ffmpeg') and encoder_module.h264_available(),'ffmpeg/libx264 required')
class H264EncoderTests(unittest.TestCase):
    def test_each_frame_arrives_before_another_is_submitted_and_decodes(self):
        frames=frames_module.FrameBuffer();queue=frames.subscribe()
        encoder=encoder_module.H264Encoder(frames)
        width,height=160,120
        units=[]
        try:
            self.assertTrue(encoder.ensure(width,height,24,70))
            for index in range(12):
                raw=bytes([index*15,40,90,255])*(width*height)
                stamp=time.time()
                encoder.submit(raw,stamp)
                # No next input frame and no EOF is available to delimit this AU.
                frame,gap=queue.pop(timeout=5)
                self.assertIsNotNone(frame, 'Encoder waited for another input frame')
                data,seq,captured_at=frame
                self.assertFalse(gap);self.assertEqual(seq,index+1)
                self.assertEqual(captured_at,stamp)
                self.assertTrue(wire.nal_types(data) & {1,5})
                if wire.flags_for(data) & wire.FLAG_KEYFRAME:
                    self.assertEqual(wire.flags_for(data),wire.FLAG_CONFIG|wire.FLAG_KEYFRAME)
                units.append(data)
            decoded=subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','h264','-i','pipe:0',
                                    '-pix_fmt','rgb24','-f','rawvideo','pipe:1'],input=b''.join(units),
                                   capture_output=True,timeout=15,check=True)
            self.assertEqual(decoded.stderr,b'')
            self.assertEqual(len(decoded.stdout),12*width*height*3)
            self.assertEqual(encoder.stats['encoded'],12)
            for index, unit in enumerate(units):
                if wire.flags_for(unit) & wire.FLAG_KEYFRAME:
                    reconnect=subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','h264','-i','pipe:0',
                                              '-pix_fmt','rgb24','-f','rawvideo','pipe:1'],input=b''.join(units[index:]),
                                             capture_output=True,timeout=15,check=True)
                    self.assertEqual(reconnect.stderr,b'')
                    self.assertEqual(len(reconnect.stdout),(12-index)*width*height*3)
        finally:
            process=encoder._proc
            encoder.stop();frames.unsubscribe(queue)
            if process and process.stdout:process.stdout.close()

if __name__=='__main__':unittest.main()
