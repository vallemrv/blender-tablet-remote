"""Revolution: closed solids from contours on or beside an in-sketch axis."""
import math
import sys
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import bpy

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_cad import CadTests, OWNER, volume
from blender_tablet_remote.cad import document as model
from blender_tablet_remote.cad.kernel import revolve
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.commands import cad
from blender_tablet_remote.errors import CommandError


def closed(mesh):
    vertices,faces=mesh
    edges=Counter(tuple(sorted((f[i],f[(i+1)%len(f)]))) for f in faces for i in range(len(f)))
    return all(count==2 for count in edges.values())


class RevolveTests(CadTests):
    def test_contour_resting_on_the_axis_becomes_a_closed_cylinder(self):
        rectangle=self.draw('RECTANGLE',(0,0),(.02,.03))
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            state=cad.revolve_create(dict(profile_id='profile_'+rectangle,**OWNER)); undo.assert_called_once()
        feature=model.find(runtime.doc(),'features',state['selection']['id'])
        self.assertEqual((feature['type'],feature['axis'],feature['angle']),('REVOLVE','Y',360.))
        polygon=64*.5*math.sin(math.tau/64)/math.pi       # tessellated circle / true circle
        self.assertAlmostEqual(volume(self.obj()),math.pi*.02**2*.03*polygon,places=9)
        sketch,source=model.profile(runtime.doc(),'profile_'+rectangle)
        self.assertTrue(closed(revolve(sketch,source,'Y',360.)))

    def test_partial_angle_has_caps_and_a_ring_beside_the_axis(self):
        rectangle=self.draw('RECTANGLE',(.01,0),(.02,.03))
        sketch,source=model.profile(runtime.doc(),'profile_'+rectangle)
        for angle in (90.,180.,360.):
            mesh=revolve(sketch,source,'Y',angle)
            self.assertTrue(closed(mesh),angle)
        state=cad.revolve_create(dict(profile_id='profile_'+rectangle,angle=180,**OWNER))
        ring=math.pi*(.02**2-.01**2)*.03*.5
        self.assertAlmostEqual(volume(self.obj()),ring,delta=ring*.01)
        cad.feature_set(dict(feature_id=state['selection']['id'],angle=360,**OWNER))
        self.assertAlmostEqual(volume(self.obj()),2*ring,delta=2*ring*.01)

    def test_contour_crossing_the_axis_is_rejected_without_changes(self):
        rectangle=self.draw('RECTANGLE',(-.01,0),(.02,.03))
        before=model.dumps(runtime.doc())
        with self.assertRaises(CommandError): cad.revolve_create(dict(profile_id='profile_'+rectangle,axis='Y',**OWNER))
        self.assertEqual(model.dumps(runtime.doc()),before)

    def test_construction_line_is_the_default_axis_and_cannot_be_deleted_while_used(self):
        axis=self.draw('LINE',(0,.05),(.1,.05)); cad._set_selection([dict(kind='ENTITY',id=axis,part='BODY')])
        cad.entity_construction(dict(construction=True,**OWNER))
        sketch=runtime.doc()['sketches'][0]
        self.assertTrue(model.find(sketch,'entities',axis)['construction'])
        rectangle=self.draw('RECTANGLE',(.02,.05),(.06,.07))
        state=cad.revolve_create(dict(profile_id='profile_'+rectangle,**OWNER))
        self.assertEqual(model.find(runtime.doc(),'features',state['selection']['id'])['axis'],axis)
        cad.sketch_activate(dict(sketch_id=sketch['id'],**OWNER))
        cad._set_selection([dict(kind='ENTITY',id=axis,part='BODY')])
        with self.assertRaises(CommandError): cad.entity_delete(OWNER)


if __name__=='__main__':
    suite=unittest.TestSuite(RevolveTests(n) for n in RevolveTests.__dict__ if n.startswith('test_'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        import os
        os._exit(1)
