"""Directional dimensions and equality from the first selected quantity."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_cad_dimensions import DimensionTests
from test_cad import OWNER
from blender_tablet_remote.cad import document as model, sketch as geometry, dimensions
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.commands import cad
from blender_tablet_remote.errors import CommandError


class MeasurementControlTests(DimensionTests):
    def test_horizontal_vertical_and_diagonal_are_separate_quantities(self):
        line=self.draw('LINE',(0,0),(.03,.04))
        self.refs((line,'START'),(line,'END'))
        offers=runtime.status()['dimension_options']
        for kind,value in [('DISTANCE',.05),('DISTANCE_X',.03),('DISTANCE_Y',.04)]:
            self.assertAlmostEqual(offers[kind]['value'],value)
            self.dimension(kind,value)
        sketch=runtime.doc()['sketches'][0]
        self.assertEqual(len(dimensions.visible_constraints(sketch)),3)
        self.assertEqual(len(sketch['constraints']),3)
        model.loads(model.dumps(runtime.doc()))
        c=next(c for c in sketch['constraints'] if c['type']=='DISTANCE_X')
        before=model.dumps(runtime.doc())
        with self.assertRaises(CommandError): cad.constraint_set(dict(constraint_id=c['id'],value=.06,**OWNER))
        self.assertEqual(model.dumps(runtime.doc()),before)

    def test_directional_cota_keeps_other_coordinate_free_and_accepts_zero(self):
        circle=self.draw('CIRCLE',(.03,.04),(.035,.04))
        self.refs(('ORIGIN','POINT'),(circle,'CENTER'))
        self.dimension('DISTANCE_X',.02)
        _,entity=model.entity(runtime.doc(),circle)
        self.assertAlmostEqual(entity['x'],.02,places=7)
        self.assertAlmostEqual(entity['y'],.04,places=7)
        c=runtime.doc()['sketches'][0]['constraints'][0]
        cad.constraint_set(dict(constraint_id=c['id'],value=0,**OWNER))
        self.assertAlmostEqual(model.entity(runtime.doc(),circle)[1]['x'],0,places=7)
        before=model.dumps(runtime.doc())
        with self.assertRaises(CommandError): cad.constraint_set(dict(constraint_id=c['id'],value=-.01,**OWNER))
        self.assertEqual(model.dumps(runtime.doc()),before)

    def test_equal_circles_keep_first_diameter_and_share_later_edits(self):
        circles=[self.draw('CIRCLE',(x,0),(x+r,0)) for x,r in [(0,.01),(.05,.02),(.1,.015)]]
        self.refs(*[(i,'CENTER') for i in circles])
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            cad.constraint_add(dict(type='EQUAL',**OWNER));undo.assert_called_once()
        for identifier in circles: self.assertAlmostEqual(model.entity(runtime.doc(),identifier)[1]['diameter'],.02,places=7)
        self.refs((circles[0],'BODY')); self.dimension('RADIUS',.01)
        cad.entity_set(dict(entity_id=circles[0],values={'diameter':.03},**OWNER))
        for identifier in circles: self.assertAlmostEqual(model.entity(runtime.doc(),identifier)[1]['diameter'],.03,places=7)
        sketch=runtime.doc()['sketches'][0]
        self.assertEqual(len([c for c in sketch['constraints'] if c['type']=='EQUAL']),2)
        self.assertEqual(len([c for c in sketch['constraints'] if c['type']=='RADIUS']),1)

    def test_equal_conflicting_fixed_radii_leave_document_untouched(self):
        a=self.draw('CIRCLE',(0,0),(.01,0));b=self.draw('CIRCLE',(.05,0),(.07,0))
        self.refs((a,'BODY'));self.dimension('RADIUS',.01)
        self.refs((b,'BODY'));self.dimension('RADIUS',.02)
        self.refs((a,'BODY'),(b,'BODY'))
        before=model.dumps(runtime.doc())
        with self.assertRaises(CommandError):cad.constraint_add(dict(type='EQUAL',**OWNER))
        self.assertEqual(model.dumps(runtime.doc()),before)

    def test_equal_lines_keep_first_length(self):
        a=self.draw('LINE',(0,0),(.03,0));b=self.draw('LINE',(0,.04),(.05,.04))
        self.refs((a,'BODY'),(b,'BODY'));cad.constraint_add(dict(type='EQUAL',**OWNER))
        for identifier in (a,b):
            self.assertAlmostEqual(dimensions.offers(runtime.doc()['sketches'][0],[dict(id=identifier,part='BODY')])['DISTANCE']['value'],.03,places=7)


if __name__=='__main__':
    suite=unittest.TestSuite(MeasurementControlTests(name) for name in MeasurementControlTests.__dict__ if name.startswith('test_'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():raise SystemExit(1)
