"""blender --background --factory-startup --python-exit-code 1 --python este_archivo."""
import itertools
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import view
from blender_tablet_remote.camera import camera


class ReferenceFrameTests(unittest.TestCase):
    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        self.image = bpy.data.objects.new('Referencia', None)
        self.image.empty_display_type = 'IMAGE'
        self.image.data = bpy.data.images.new('Panorámica', width=400, height=200)
        self.image.empty_display_size = .02
        bpy.context.scene.collection.objects.link(self.image)
        self.image.select_set(True)
        bpy.context.view_layer.objects.active = self.image
        self.rv = SimpleNamespace(window_matrix=Matrix(((2/1.7,0,0,0),(0,2,0,0),(0,0,-1,-.02),(0,0,-1,0))))
        camera.reset()
        camera._synced = True
        camera.rotation = Quaternion((1, 0, 0, 0))
        camera.set_clipping(.00001, 100)
        self.patch = patch.object(view, '_region_view', return_value=self.rv)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()

    def test_reference_uses_four_corners_and_fills_85_percent_in_both_projections(self):
        for mode, size in itertools.product(('PERSP', 'ORTHO'), (.001, .02, 4)):
            with self.subTest(mode=mode, size=size):
                camera.perspective = mode
                self.image.empty_display_size = size
                self.image.empty_image_offset = (.2, -.8)
                self.image.location = (size * 2, -size, size)
                self.image.rotation_euler = (.3, -.2, .5)
                self.image.scale = (2, .5, 1)
                bpy.context.view_layer.update()
                expected = [self.image.matrix_world @ Vector((x * size, y * size, 0))
                            for x, y in ((.2, -.4), (1.2, -.4), (1.2, .1), (.2, .1))]
                matrix = self.image.matrix_world.copy()
                rotation = camera.rotation.copy()
                result = view.frame_selected({})
                center, corners = view._bounds([self.image])
                self.assertEqual(len(corners), 4)
                for actual, want in zip(corners, expected):
                    self.assertLess((actual-want).length, size * 1e-5)
                screens = [camera.project(p, self.rv) for p in expected]
                edge = max(abs(c-.5)*2 for point in screens for c in point)
                self.assertAlmostEqual(edge, .85, places=4)
                self.assertEqual(self.image.matrix_world, matrix)
                self.assertEqual(camera.rotation, rotation)
                self.assertEqual(result['framed'], 'selected')
                distance = camera.distance
                view.frame_selected({})
                self.assertAlmostEqual(camera.distance, distance, places=7)

    def test_pixel_aspect_and_parent_transform_define_actual_center(self):
        self.image.data.display_aspect = (1, 2)
        self.image.empty_image_offset = (0, 0)
        parent = bpy.data.objects.new('Padre', None)
        bpy.context.scene.collection.objects.link(parent)
        parent.location = (2, 3, 4)
        parent.rotation_euler.z = .5
        parent.scale = (2, 3, 1)
        self.image.parent = parent
        bpy.context.view_layer.update()
        center, corners = view._bounds([self.image])
        expected = self.image.matrix_world @ Vector((.01, .01, 0))
        self.assertLess((center-expected).length, 1e-6)
        camera.perspective = 'ORTHO'
        view.frame_selected({})
        self.assertLess((camera.location-expected).length, 1e-6)

    def test_active_reference_fallback_does_not_frame_distant_cube(self):
        bpy.ops.mesh.primitive_cube_add(location=(100, 100, 100))
        bpy.ops.object.select_all(action='DESELECT')
        bpy.context.view_layer.objects.active = self.image
        camera.perspective = 'PERSP'
        view.frame_selected({})
        self.assertLess(camera.distance, .1)
        self.assertLess(camera.location.length, 1e-6)

    def test_cube_keeps_eight_bounds_and_same_framing(self):
        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.mesh.primitive_cube_add(size=.02)
        cube = bpy.context.object
        bpy.context.view_layer.update()
        self.assertEqual(len(view._bounds([cube])[1]), 8)
        for mode in ('ORTHO', 'PERSP'):
            camera.perspective = mode
            view.frame_selected({})
            points = [cube.matrix_world @ Vector(p) for p in cube.bound_box]
            edge = max(abs(c-.5)*2 for point in points for c in camera.project(point, self.rv))
            self.assertAlmostEqual(edge, .85, places=4)


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ReferenceFrameTests))
    if not result.wasSuccessful(): raise SystemExit(1)
