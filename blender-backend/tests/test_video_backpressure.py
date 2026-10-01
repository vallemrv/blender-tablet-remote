"""Bounded H.264 lag and cleanup of clients suspended without closing TCP."""
import importlib
import socket
import struct
import sys
import time
import types
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

root = Path(__file__).resolve().parents[1] / 'blender_tablet_remote'
for name, path in [('video_test_package', root), ('video_test_package.streaming', root / 'streaming')]:
    package = types.ModuleType(name); package.__path__ = [str(path)]; sys.modules[name] = package
frames = importlib.import_module('video_test_package.streaming.frames')
http = importlib.import_module('video_test_package.streaming.mjpeg')
wire = importlib.import_module('video_test_package.streaming.h264')
KEY = b'\0\0\0\1\x67\x80\0\0\0\1\x68\x80\0\0\0\1\x65\x80'
P = b'\0\0\0\1\x41\x80'


class VideoBackpressureTests(unittest.TestCase):
    def test_burst_keeps_every_access_unit(self):
        q = frames.FrameQueue()
        with patch.object(frames.time, 'monotonic', return_value=10.):
            for n in range(50): q.push((P, n, 100.))
            for n in range(50): self.assertEqual(q.pop(), ((P, n, 100.), False))

    def test_age_not_just_capacity_recovers_a_stalled_consumer(self):
        q = frames.FrameQueue()
        with patch.object(frames.time, 'monotonic', return_value=10.): q.push((P, 1, 100.))
        with patch.object(frames.time, 'monotonic', return_value=10.3):
            q.push((KEY, 2, 100.3))
            self.assertEqual(q.pop(), ((KEY, 2, 100.3), True))
            q.push((P, 3, 100.3))
            self.assertEqual(q.pop(), ((P, 3, 100.3), False))

    def test_pop_also_detects_age_and_close_releases_queued_bytes(self):
        q = frames.FrameQueue()
        with patch.object(frames.time, 'monotonic', return_value=10.):
            q.push((P, 1, 100.)); q.push((KEY, 2, 100.))
        with patch.object(frames.time, 'monotonic', return_value=11.):
            self.assertEqual(q.pop(), ((KEY, 2, 100.), True))
        q.push((KEY, 3, 101.)); q.close(); q.push((P, 4, 102.))
        self.assertEqual(q.pop(0), (None, False))

    def make_server(self):
        server = http.StreamServer(frames.FrameBuffer(), lambda: {'resolution': [64, 64]})
        server.start('127.0.0.1', 0)
        server.port = server._httpd.server_address[1]
        self.addCleanup(server.stop)
        return server

    def wait_for(self, predicate, seconds=2):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            if predicate(): return
            time.sleep(.005)
        self.fail('Timed out waiting for stream state')

    def test_reconnections_start_from_fresh_sps_pps_and_idr(self):
        server = self.make_server()
        for _ in range(3):
            with urllib.request.urlopen(f'http://127.0.0.1:{server.port}/stream.h264', timeout=2) as response:
                self.wait_for(lambda: server.h264_frames.subscribers == 1)
                server.h264_frames.publish(KEY, time.time() - 2)  # stale IDR cannot restart playback
                server.h264_frames.publish(P, time.time())
                server.h264_frames.publish(KEY, time.time())
                header = struct.unpack('>4sBBHIQIII', response.read(32))
                self.assertEqual(header[2], wire.FLAG_KEYFRAME | wire.FLAG_CONFIG)
                self.assertLess(time.time() - header[5] / 1e6, .25)
                self.assertEqual(response.read(header[6]), KEY)
            # Wake the handler so its next write observes the closed peer.
            for _ in range(4): server.h264_frames.publish(KEY, time.time()); time.sleep(.01)
            self.wait_for(lambda: server.h264_frames.subscribers == 0)

    def test_suspended_tcp_client_cannot_keep_encoder_and_capture_alive(self):
        server = self.make_server()
        client = socket.socket()
        self.addCleanup(client.close)
        client.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024)
        client.connect(('127.0.0.1', server.port))
        client.sendall(b'GET /stream.h264 HTTP/1.1\r\nHost: localhost\r\n\r\n')
        self.wait_for(lambda: server.h264_frames.subscribers == 1)
        server.h264_frames.publish(KEY + b'x' * (2 * 1024 * 1024), time.time())
        # Leave TCP open and stop reading, as a suspended Android process can do.
        self.wait_for(lambda: server.clients == 0, seconds=3)
        self.assertEqual(server.h264_frames.subscribers, 0)
        self.assertFalse(server.wanted())
        self.assertEqual(server.formats_wanted(), set())


if __name__ == '__main__': unittest.main()
