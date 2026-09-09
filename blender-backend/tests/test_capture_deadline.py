"""blender -b --factory-startup --python-exit-code 1 --python this_file."""
import sys
import unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.streaming.capture import ViewportCapture,MAX_CONSECUTIVE_ERRORS
from blender_tablet_remote.streaming.frames import FrameBuffer

class CaptureDeadlineTests(unittest.TestCase):
    def setUp(self):
        self.capture=ViewportCapture(FrameBuffer(),has_viewers=lambda:True)
        self.capture.enabled=True;self.capture.fps=24;self.capture._last_capture=100

    def test_render_cost_does_not_delay_next_frame_by_full_poll_interval(self):
        with patch('blender_tablet_remote.streaming.capture.time.monotonic',return_value=100.035):
            self.assertAlmostEqual(self.capture.next_delay(1/60),1/24-.035)
        with patch('blender_tablet_remote.streaming.capture.time.monotonic',return_value=100.1):
            self.assertEqual(self.capture.next_delay(1/60),.001)

    def test_no_video_preserves_control_poll_and_no_busy_loop(self):
        for disabled in ('viewers','enabled','errors'):
            self.setUp()
            if disabled=='viewers':self.capture.has_viewers=lambda:False
            elif disabled=='enabled':self.capture.enabled=False
            else:self.capture._errors=MAX_CONSECUTIVE_ERRORS
            self.assertEqual(self.capture.next_delay(1/60),1/60)

    def test_discrete_frame_request_wakes_early(self):
        self.capture.request_frame()
        self.assertEqual(self.capture.next_delay(1/60),.001)

result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CaptureDeadlineTests))
if not result.wasSuccessful():raise SystemExit(1)
