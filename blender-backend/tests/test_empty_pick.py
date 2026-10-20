"""Tocar un Empty lo selecciona por sus líneas: blender --factory-startup --python this_file."""
import sys, unittest
from pathlib import Path
import bpy
from mathutils import Vector, Quaternion
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import selection
from blender_tablet_remote.camera import camera
from blender_tablet_remote.bpy_utils import find_view3d


class EmptyPickTests(unittest.TestCase):
    def setUp(self):
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
        bpy.ops.object.empty_add(type='CUBE', location=(0, 0, 0)); self.cube = bpy.context.object
        bpy.ops.object.empty_add(type='PLAIN_AXES', location=(4, 0, 0)); self.axes = bpy.context.object
        bpy.ops.object.select_all(action='DESELECT')
        camera.reset(); camera._synced = True; camera.perspective = 'ORTHO'
        camera.location = Vector((2, 0, 0)); camera.rotation = Quaternion((1, 0, 0, 0)); camera.distance = 12
        self.rv = find_view3d()[3]

    def tap(self, point):
        u, v = camera.project(Vector(point), self.rv)
        return selection.pick(dict(u=u, v=v, mode='SET'))

    def test_tapping_the_drawn_cube_or_its_centre_selects_the_empty(self):
        self.assertTrue(self.tap((1, 0.3, 1))['hit'])
        self.assertEqual([o.name for o in bpy.context.selected_objects], [self.cube.name])
        self.assertEqual(bpy.context.view_layer.objects.active, self.cube)
        self.assertTrue(self.tap((4.6, 0, 0))['hit'])
        self.assertEqual([o.name for o in bpy.context.selected_objects], [self.axes.name])
        self.assertTrue(self.tap((0, 0, 0))['hit'])
        self.assertEqual([o.name for o in bpy.context.selected_objects], [self.cube.name])

    def test_empty_space_and_locked_empties_are_not_picked(self):
        self.assertFalse(self.tap((2, 3, 0)).get('hit'))
        self.cube.hide_select = True
        self.assertFalse(self.tap((1, 0.3, 1)).get('hit'))


def run():
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(EmptyPickTests))
    if not result.wasSuccessful():
        import os
        sys.stdout.flush(); sys.stderr.flush(); os._exit(1)
    bpy.ops.wm.quit_blender()
bpy.app.timers.register(run, first_interval=1)
