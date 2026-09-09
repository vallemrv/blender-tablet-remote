"""blender --background --factory-startup --python-exit-code 1 --python this_file."""
import itertools
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.camera import RemoteCamera


class CameraViewTests(unittest.TestCase):
    def test_one_mm_and_smaller_pieces_fill_view_independent_of_scene_units(self):
        for meters, unit_scale, mode in itertools.product((.001, .00001), (.001, 1, 1000), ('ORTHO','PERSP')):
            with self.subTest(meters=meters, unit_scale=unit_scale, mode=mode):
                camera = RemoteCamera()
                camera.apply(perspective=mode)
                size = meters / unit_scale
                points = [Vector((x*size/2,y*size/2,z*size/2)) for x,y,z in itertools.product((-1,1),repeat=3)]
                rv = self.region()
                camera.look_at(Vector(), points, rv)
                edge = max(abs(c-.5)*2 for p in points for c in camera.project(p,rv))
                self.assertAlmostEqual(edge,.85,places=4)
                old = camera.distance
                camera.zoom(2)
                self.assertAlmostEqual(camera.distance / old, .5)

    def region(self, aspect=1.7, ortho=False):
        matrix = Matrix(((2/aspect,0,0,0),(0,2,0,0),(0,0,-1,-.02),(0,0,-1,0)))
        if ortho:
            matrix = Matrix(((2/aspect/400,0,0,0),(0,2/400,0,0),(0,0,-.001,0),(0,0,0,1)))
        return SimpleNamespace(window_matrix=matrix, view_distance=400,
                               view_location=Vector(), view_rotation=Quaternion())

    def test_orthographic_zoom_does_not_slice_front_surface(self):
        camera = RemoteCamera()
        rv3d = self.region()
        camera.sync_from_region(rv3d)
        camera.apply(perspective='ORTHO')
        camera.set_clipping(.0005,5)
        front = Vector((0,0,150,1))
        for distance in (400,150,50,1,.01):
            camera.apply(distance=distance)
            projected = camera.perspective_matrix(rv3d) @ front
            self.assertLess(abs(projected.z/projected.w),1, f'front clipped at distance {distance}')
            origin, direction = camera.ray(.5,.5,rv3d)
            self.assertGreater(origin.z,front.z)
            self.assertLess(direction.z,-.99)

    def test_frame_fills_85_percent_without_cutting_corners(self):
        for mode, aspect, ortho, scale in itertools.product(('ORTHO','PERSP'),(.65,1.7), (False,True),(.001,1.0)):
            with self.subTest(mode=mode,aspect=aspect,pc_ortho=ortho,scale=scale):
                camera = RemoteCamera()
                camera.apply(perspective=mode,rotation=Quaternion(Vector((1,1,0)).normalized(),.4))
                rv3d = self.region(aspect,ortho)
                points = [Vector((x*scale,y*scale,z*scale))
                          for x,y,z in itertools.product((-75,75),(-149.3,149.3),(-150,150))]
                camera.look_at(Vector(),points,rv3d)
                screens = [camera.project(p,rv3d) for p in points]
                self.assertTrue(all(p is not None for p in screens))
                edge = max(abs(c-.5)*2 for point in screens for c in point)
                self.assertAlmostEqual(edge,.85,places=4)
                self.assertLess(edge,1)

    def test_orthographic_depth_stays_centered_after_pan_and_rotation(self):
        camera = RemoteCamera()
        rv3d = self.region()
        camera.sync_from_region(rv3d)
        camera.apply(location=[20,30,40], perspective='ORTHO', distance=.1,
                     rotation=Quaternion(Vector((1,1,0)).normalized(),.7))
        front = camera.location + camera.rotation @ Vector((0,0,150))
        clip = camera.perspective_matrix(rv3d) @ front.to_4d()
        self.assertLess(abs(clip.z/clip.w),1)
        self.assertEqual(rv3d.view_distance,400)
        self.assertEqual(tuple(rv3d.view_location),(0,0,0))


if __name__ == '__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    if not result.wasSuccessful(): raise SystemExit(1)
