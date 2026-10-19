"""La identidad de las referencias sobrevive al archivo y nunca pasa a una escena nueva."""
import sys
import tempfile
import unittest
from pathlib import Path
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands.units import reference_board_id, current_scale, REFERENCE_BOARD_KEY

class BoardIdentityTests(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.read_homefile(use_empty=True)
    def test_new_scenes_have_independent_boards(self):
        first=reference_board_id()
        self.assertEqual(first,current_scale()['reference_board_id'])
        from blender_tablet_remote.commands.file import new
        new({'preset': 'MEDIUM', 'empty': True})
        self.assertNotEqual(first,reference_board_id())
    def test_saved_scene_recovers_same_board_after_reopening(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as folder:
            first=reference_board_id()
            path=str(Path(folder)/'references.blend')
            bpy.ops.wm.save_as_mainfile(filepath=path)
            bpy.ops.wm.read_homefile(use_empty=True)
            self.assertNotEqual(first,reference_board_id())
            bpy.ops.wm.open_mainfile(filepath=path)
            self.assertEqual(first,reference_board_id())
    def test_invalid_saved_id_is_replaced_once(self):
        bpy.context.scene[REFERENCE_BOARD_KEY]='invalid'
        first=reference_board_id()
        self.assertEqual(first,reference_board_id())
        self.assertEqual(len(first),36)

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(BoardIdentityTests))
    if not result.wasSuccessful():raise SystemExit(1)
