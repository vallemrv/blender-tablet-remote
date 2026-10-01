"""Extrude up to a face: the far cap lies on the plane of a tapped solid face."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import bpy
import bmesh
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cad import CadTests, OWNER, volume
from blender_tablet_remote.cad import document as model
from blender_tablet_remote.cad.kernel import ExtrusionPreviewCache
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.commands import cad
from blender_tablet_remote.errors import CommandError

SLOPE = dict(origin=[0., 0., .03], normal=[.7071067811865476, 0., .7071067811865476])


def square(to_face):
    entity = dict(id='square', type='RECTANGLE', x=0, y=0, width=.02, height=.02)
    sketch = dict(id='sketch', plane='XY', offset=0, entities=[entity])
    return ExtrusionPreviewCache().extrude(sketch, entity, 0, to_face=to_face)


def closed_volume(data):
    bm = bmesh.new()
    try:
        vertices = [bm.verts.new(v) for v in data[0]]
        for face in data[1]: bm.faces.new([vertices[i] for i in face])
        assert all(e.is_manifold for e in bm.edges)
        return bm.calc_volume(signed=True)
    finally: bm.free()


class ToFaceKernelTests(unittest.TestCase):
    def test_inclined_face_cuts_the_far_cap(self):
        data = square(SLOPE)
        # Height .03 - x over the 20 mm square.
        self.assertAlmostEqual(closed_volume(data), .02*(.03*.02-.02**2/2), places=10)
        for x, y, z in data[0]:
            if z > 1e-9: self.assertAlmostEqual(z, .03-x, places=7)

    def test_face_below_the_profile_extrudes_downwards(self):
        data = square(dict(origin=[0, 0, -.03], normal=[0, 0, 1]))
        self.assertAlmostEqual(closed_volume(data), .02*.02*.03, places=10)
        self.assertAlmostEqual(min(v[2] for v in data[0]), -.03, places=7)

    def test_crossing_or_parallel_faces_are_rejected(self):
        with self.assertRaises(CommandError):
            square(dict(origin=[0, 0, .01], normal=[.7071067811865476, 0, .7071067811865476]))
        with self.assertRaises(CommandError):
            square(dict(origin=[.05, 0, 0], normal=[1, 0, 0]))


class ToFaceCommandTests(CadTests):
    def test_session_and_edit_end_on_the_tapped_face_without_a_cut(self):
        rectangle = self.rect()
        cad.extrude_begin(dict(profile_id='profile_'+rectangle, depth=.02, **OWNER))
        with patch.object(cad, '_face_target', return_value=dict(SLOPE, origin=[0., 0., .1])):
            status = cad.extrude_update(dict(extent='TO_FACE', u=.5, v=.5, **OWNER))
        self.assertEqual(status['session']['extent'], 'TO_FACE')
        # Pen samples carry u/v too and never re-sample the face.
        cad.extrude_update(dict(gesture_u=0, gesture_v=-.3, u=.5, v=.2, baseline_depth=.02, **OWNER))
        cad.confirm(OWNER)
        feature = runtime.doc()['features'][-1]
        self.assertEqual(feature['extent'], 'TO_FACE')
        self.assertAlmostEqual(feature['depth'], .1, places=7)
        obj = self.obj()
        top = [(obj.matrix_world @ v.co) for v in obj.data.vertices if (obj.matrix_world @ v.co).z > 1e-9]
        for p in top: self.assertAlmostEqual(p.z, .1-p.x, places=6)
        self.assertAlmostEqual(volume(obj), .045*(.1*.08-.08**2/2), places=7)
        model.loads(model.dumps(runtime.doc()))
        cad.feature_set(dict(feature_id=feature['id'], extent='ONE', **OWNER))
        feature = runtime.doc()['features'][-1]
        self.assertNotIn('to_face', feature)
        self.assertAlmostEqual(volume(self.obj()), .045*.08*.1, places=7)
        with patch.object(cad, '_face_target', return_value=dict(origin=[0, 0, .05], normal=[0, 0, -1])):
            cad.feature_set(dict(feature_id=feature['id'], extent='TO_FACE', u=.5, v=.5, **OWNER))
        self.assertAlmostEqual(volume(self.obj()), .045*.08*.05, places=7)
        with self.assertRaises(CommandError):
            cad.sketch_create(dict(support_id=feature['id'], **OWNER))


if __name__ == '__main__':
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(case)
                               for case in (ToFaceKernelTests, ToFaceCommandTests))
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
        raise SystemExit(1)
