"""Interactive plane placement: live preview, pen separation and one undo."""
import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy
from mathutils import Vector

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_cad import CadTests, OWNER
from blender_tablet_remote.cad import document as model
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.camera import camera
from blender_tablet_remote.commands import cad
from blender_tablet_remote.errors import CommandError


class PlaneSessionTests(CadTests):
    def test_preview_changes_nothing_until_confirm_creates_plane_and_sketch_in_one_undo(self):
        before=model.dumps(runtime.doc())
        state=cad.plane_begin(dict(base='XZ',**OWNER))
        self.assertEqual(state['session']['operation'],'PLANE')
        self.assertEqual(state['session']['plane']['base'],'XZ')
        cad.plane_update(dict(offset=.02,tilt=[45.,0.],**OWNER))
        self.assertEqual(model.dumps(runtime.doc()),before)
        frame=runtime.session['plane_frame']
        # Frontal normal is −Y; a 45° tilt about the plane's X turns it towards −Z.
        self.assertAlmostEqual(Vector(frame['normal']).dot(Vector((0,-math.sqrt(.5),-math.sqrt(.5)))),1.,places=6)
        # Separation follows the tilted normal, not the base one.
        self.assertAlmostEqual(Vector(frame['origin']).length,.02,places=8)
        self.assertAlmostEqual(Vector(frame['origin']).normalized().dot(Vector(frame['normal'])),1.,places=6)
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            state=cad.confirm(OWNER); undo.assert_called_once()
        doc=runtime.doc()
        self.assertEqual(len(doc['planes']),1)
        sketch=doc['sketches'][-1]
        self.assertEqual(sketch['plane_id'],doc['planes'][0]['id'])
        self.assertEqual(state['active_sketch_id'],sketch['id'])
        self.assertAlmostEqual(Vector(model.frame(sketch)['origin']).length,.02,places=8)

    def test_cancel_discards_and_face_base_requires_a_face(self):
        before=model.dumps(runtime.doc())
        cad.plane_begin(dict(base='YZ',**OWNER)); cad.plane_update(dict(offset=.05,**OWNER))
        with self.assertRaises(CommandError): cad.plane_update(dict(base='FACE',**OWNER))
        self.assertEqual(runtime.session['plane']['base'],'YZ')
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            cad.cancel(OWNER); undo.assert_not_called()
        self.assertIsNone(runtime.session); self.assertEqual(model.dumps(runtime.doc()),before)

    def test_pen_drags_the_separation_under_the_tip_with_whole_steps(self):
        cad.plane_begin(dict(base='XY',**OWNER))
        ray=lambda u,v,rv3d:(Vector((u,-10.,.5-v)),Vector((0.,1.,0.)))
        view=(None,None,SimpleNamespace(width=100,height=100),object())
        runtime.increment=True; runtime.step=.001
        with patch('blender_tablet_remote.bpy_utils.find_view3d',return_value=view), \
             patch.object(camera,'sync_from_region'),patch.object(camera,'ray',side_effect=ray):
            cad.plane_update(dict(gesture_u=.1,gesture_v=-.0123,u=.6,v=.4877,baseline_offset=0.,**OWNER))
        self.assertAlmostEqual(runtime.session['plane']['offset'],.012,places=9)
        self.assertAlmostEqual(runtime.session['plane_frame']['origin'][2],.012,places=9)
        cad.cancel(OWNER)

    def test_saved_plane_is_repositioned_with_the_same_controls(self):
        cad.plane_begin(dict(base='XY',**OWNER)); cad.plane_update(dict(offset=.01,tilt=[30.,10.],shift=[.02,-.01],**OWNER))
        cad.confirm(OWNER); cad.sketch_finish(OWNER)
        plane=runtime.doc()['planes'][0]; sketches=len(runtime.doc()['sketches'])
        state=cad.plane_begin(dict(plane_id=plane['id'],**OWNER))
        for got,expected in zip([state['session']['plane']['offset']]+state['session']['plane']['tilt']+state['session']['plane']['shift'],
                                [.01,30.,10.,.02,-.01]):
            self.assertAlmostEqual(got,expected,places=9)
        cad.plane_update(dict(offset=.03,**OWNER))
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            cad.confirm(OWNER); undo.assert_called_once()
        doc=runtime.doc()
        self.assertEqual(len(doc['planes']),1); self.assertEqual(len(doc['sketches']),sketches)
        frame=model.find(doc,'planes',plane['id'])['frame']
        shifted=Vector(frame['origin'])-Vector((.02,-.01,0))
        self.assertAlmostEqual(shifted.dot(Vector(frame['normal'])),.03,places=8)


if __name__=='__main__':
    suite=unittest.TestSuite(PlaneSessionTests(n) for n in PlaneSessionTests.__dict__ if n.startswith('test_'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        import os
        os._exit(1)
