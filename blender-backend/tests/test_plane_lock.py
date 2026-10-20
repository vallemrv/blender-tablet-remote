import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from mathutils import Quaternion,Vector,Matrix
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.camera import RemoteCamera
from blender_tablet_remote.commands import view
from blender_tablet_remote.errors import BadPayload

class PlaneLockTests(unittest.TestCase):
    def setUp(self):
        self.camera=RemoteCamera();self.camera._synced=True
        self.patches=[patch.object(view,'camera',self.camera),patch.object(view,'_region_view',return_value=None)]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
    def test_all_planes_keep_orientation_but_allow_zoom_and_pan(self):
        for name in ['TOP','FRONT','RIGHT','BOTTOM','BACK','LEFT']:
            self.camera.set_axis_view(name)
            view.plane_lock({'enabled':True})
            rotation=self.camera.rotation.copy();distance=self.camera.distance;location=self.camera.location.copy()
            self.camera.orbit(.4,.2,2);self.camera.roll(.7)
            self.camera.sync_from_region(object(),force=True)
            self.assertEqual(view._sketch_projection(),'ORTHO')
            self.camera.apply(rotation=Quaternion((1,1,0,0)),perspective='PERSP')
            self.assertEqual(self.camera.rotation,rotation)
            self.assertEqual(self.camera.perspective,'ORTHO')
            self.camera.zoom(2);self.camera.pan(.1,.1)
            self.assertLess(self.camera.distance,distance);self.assertNotEqual(self.camera.location,location)
            self.assertTrue(self.camera.as_dict()['plane_locked'])
    def test_unlock_reenables_orbit_and_reset_does_not_leak_lock_to_new_scene(self):
        self.camera.set_axis_view('TOP');view.plane_lock({'enabled':True})
        rotation=self.camera.rotation.copy();view.plane_lock({'enabled':False})
        self.camera.orbit(.3,.2,2);self.assertNotEqual(rotation,self.camera.rotation)
        self.camera.set_axis_view('TOP');view.plane_lock({'enabled':True});self.camera.reset()
        self.assertFalse(self.camera.plane_locked)
    def test_lock_requires_explicit_planar_view(self):
        with self.assertRaises(BadPayload):view.plane_lock({'enabled':True})
        self.assertFalse(self.camera.plane_locked)

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PlaneLockTests))
    if not result.wasSuccessful():raise SystemExit(1)
