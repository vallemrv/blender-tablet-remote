"""A point remains on a straight sketch reference with one sliding degree of freedom."""
import copy
import math
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_cad import CadTests,OWNER
from blender_tablet_remote.cad import document as model,sketch as geometry
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.commands import cad
from blender_tablet_remote.errors import CommandError


def ref(identifier,part):
    return dict(id=identifier,part=part)


class PointOnLineTests(CadTests):
    def fix(self,identifier):
        cad.constraint_add(dict(type='FIX',refs=[ref(identifier,'BODY')],**OWNER))

    def test_either_selection_order_persists_and_drag_slides_beyond_the_segment(self):
        line=self.draw('LINE',(-.04,.02),(.04,.02));self.fix(line)
        circle=self.draw('CIRCLE',(0,.04),(.005,.04))
        fixed=copy.deepcopy(model.entity(runtime.doc(),line)[1])
        point_ref=ref(circle,'CENTER');line_ref=ref(line,'BODY')
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            cad.constraint_add(dict(type='POINT_ON_LINE',refs=[line_ref,point_ref],**OWNER))
            undo.assert_called_once()
        sketch,entity=model.entity(runtime.doc(),circle)
        self.assertAlmostEqual(entity['y'],.02,places=8)
        self.assertEqual(model.find(sketch,'entities',line),fixed)
        rule=next(c for c in sketch['constraints'] if c['type']=='POINT_ON_LINE')
        self.assertEqual(rule['refs'],[point_ref,line_ref])
        hit=dict(kind='ENTITY',**point_ref);cad._set_selection([hit])
        with patch.object(cad,'_pick',return_value=hit),patch.object(runtime,'point',return_value=(0,.02)):
            cad.drag_begin(dict(u=.3,v=.3,**OWNER))
        with patch.object(runtime,'point',return_value=(.075,.06)):
            cad.drag_update(dict(u=.5,v=.5,**OWNER))
        with patch.object(runtime,'point',side_effect=AssertionError('END must use the visible sample')),patch.object(cad,'undo_push') as undo:
            cad.drag_end(OWNER);undo.assert_called_once()
        sketch,entity=model.entity(runtime.doc(),circle)
        self.assertAlmostEqual(entity['x'],.075,places=7)
        self.assertAlmostEqual(entity['y'],.02,places=8)
        self.assertAlmostEqual(entity['diameter'],.010,places=8)
        self.assertEqual(model.find(sketch,'entities',line),fixed)
        restored=model.loads(bpy.context.scene[model.KEY])
        self.assertEqual(next(c for c in restored['sketches'][0]['constraints'] if c['type']=='POINT_ON_LINE'),rule)

    def test_line_endpoint_slides_on_vertical_and_diagonal_reference(self):
        for a,b in [((.01,-.02),(.01,.04)),((.01,-.02),(.04,.02))]:
            cad.sketch_create(dict(plane='XY',**OWNER))
            line=self.draw('LINE',a,b);self.fix(line)
            other=self.draw('LINE',(.02,.06),(.07,.08))
            point_ref=ref(other,'START');line_ref=ref(line,'BODY')
            cad.constraint_add(dict(type='POINT_ON_LINE',refs=[point_ref,line_ref],**OWNER))
            sketch,e=model.entity(runtime.doc(),other)
            unchanged_end=(e['x2'],e['y2'])
            geometry.solve(sketch,geometry.move_goals(sketch,[point_ref],.023,.011),drag=True)
            p=geometry.point(sketch,point_ref);d=[b[i]-a[i] for i in range(2)]
            self.assertAlmostEqual((p[0]-a[0])*d[1]-(p[1]-a[1])*d[0],0,places=10)
            e=model.find(sketch,'entities',other)
            self.assertEqual((e['x2'],e['y2']),unchanged_end)

    def test_corner_can_slide_on_rectangle_side_or_slot_axis(self):
        for kind,part in (('RECTANGLE','EDGE0'),('SLOT','AXIS')):
            cad.sketch_create(dict(plane='XY',**OWNER))
            guide=self.draw(kind,(0,0),(.04,0 if kind=='SLOT' else .03));self.fix(guide)
            rectangle=self.draw('RECTANGLE',(.01,.02),(.025,.035))
            point_ref=ref(rectangle,'P0');line_ref=ref(guide,part)
            cad.constraint_add(dict(type='POINT_ON_LINE',refs=[point_ref,line_ref],**OWNER))
            sketch,_=model.entity(runtime.doc(),rectangle)
            self.assertAlmostEqual(geometry.point(sketch,point_ref)[1],0,places=8)

    def test_fixed_conflict_and_invalid_roles_do_not_change_document_or_undo(self):
        line=self.draw('LINE',(0,.02),(.04,.02));self.fix(line)
        circle=self.draw('CIRCLE',(0,.04),(.005,.04));self.fix(circle)
        baseline=bpy.context.scene[model.KEY]
        cases=[(ref(circle,'CENTER'),ref(line,'BODY')),
               (ref(circle,'CENTER'),ref(line,'START')),
               (ref(line,'START'),ref(line,'BODY')),
               (ref(line,'START'),ref(circle,'BODY'))]
        for refs in cases:
            with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
                with self.assertRaises(CommandError):cad.constraint_add(dict(type='POINT_ON_LINE',refs=list(refs),**OWNER))
                undo.assert_not_called()
            self.assertEqual(bpy.context.scene[model.KEY],baseline)

    def test_free_reference_can_be_constrained_through_origin_and_rule_removed(self):
        line=self.draw('LINE',(.01,.02),(.04,.02))
        cad.constraint_add(dict(type='POINT_ON_LINE',refs=[ref('ORIGIN','POINT'),ref(line,'BODY')],**OWNER))
        sketch,_=model.entity(runtime.doc(),line)
        rule=next(c for c in sketch['constraints'] if c['type']=='POINT_ON_LINE')
        self.assertLess(abs(geometry.residual(sketch,rule,1.)[0]),1e-8)
        cad.constraint_delete(dict(constraint_id=rule['id'],**OWNER))
        self.assertFalse(any(c['type']=='POINT_ON_LINE' for c in runtime.doc()['sketches'][0]['constraints']))


if __name__=='__main__':
    suite=unittest.TestSuite(PointOnLineTests(n) for n in PointOnLineTests.__dict__ if n.startswith('test_'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        import os;os._exit(1)
