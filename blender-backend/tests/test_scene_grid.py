"""blender --background --factory-startup --python-exit-code 1 --python este_archivo"""
import sys
import unittest
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import units
from blender_tablet_remote.bpy_utils import find_view3d
from blender_tablet_remote.camera import camera
from blender_tablet_remote.streaming.capture import _tablet_grid_extent


class SceneGridTests(unittest.TestCase):
    def test_presets_have_physical_spacing_without_rescaling_geometry(self):
        space = find_view3d()[1].spaces.active
        original = bpy.context.object.matrix_world.copy()
        for scale in (1., .001, 10.):
            bpy.context.scene.unit_settings.scale_length = scale
            for preset, meters in [('SMALL', .001), ('MEDIUM', .01), ('LARGE', 1.)]:
                units.apply_scale(preset)
                self.assertAlmostEqual(space.overlay.grid_scale_unit * scale, meters, places=6)
                self.assertAlmostEqual(bpy.context.scene.unit_settings.scale_length, scale, places=6)
                self.assertEqual(bpy.context.object.matrix_world, original)

    def test_reset_restores_large_grid_and_camera_clipping_from_scene_units(self):
        settings = bpy.context.scene.unit_settings
        settings.system, settings.length_unit, settings.scale_length = 'METRIC', 'METERS', .001
        space = find_view3d()[1].spaces.active
        space.overlay.grid_scale = .001
        units.reset()
        self.assertAlmostEqual(space.overlay.grid_scale_unit * settings.scale_length, 1., places=6)
        self.assertAlmostEqual(camera.clip_end * settings.scale_length, 1000., places=5)

    def test_tablet_grid_extent_is_temporary_even_on_draw_failure(self):
        space = find_view3d()[1].spaces.active
        space.clip_end = 1000.
        camera.clip_end, camera.distance = 1_000_000., 45_000.
        with self.assertRaises(RuntimeError):
            with _tablet_grid_extent(space):
                self.assertGreaterEqual(space.clip_end, 4 * camera.distance)
                raise RuntimeError('Simulated capture failure')
        self.assertEqual(space.clip_end, 1000.)


if __name__ == '__main__':
    r = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SceneGridTests))
    if not r.wasSuccessful(): raise SystemExit(1)
