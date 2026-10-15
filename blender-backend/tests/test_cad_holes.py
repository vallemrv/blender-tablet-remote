"""Metric drill seats, exact dimensions, point dependencies and preview lifecycle."""
import math,sys,unittest
from pathlib import Path
from unittest.mock import patch
import bpy
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from test_cad import CadTests, OWNER, volume
from blender_tablet_remote.cad import document as model, occt, holes
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.commands import cad, cad_operations as ops
from blender_tablet_remote.errors import CommandError

class HoleTests(CadTests):
    def plate(self,depth=.005):
        base=self.extrude(self.rect(),depth)
        cad.sketch_create(dict(support_id=base,**OWNER))
        p=self.draw('POINT',(.02,.02),(.02,.02))
        return runtime.active_sketch_id,p
    def exact_volume(self):
        result=occt.evaluator.evaluate(runtime.doc())
        tip=next(iter(result['tips'].values()))
        return occt._volume(occt.evaluator._shapes[tip][1])/occt.MM**3
    def test_m3_through_is_3_6mm_and_one_undo(self):
        sketch,p=self.plate();before=bpy.context.scene[model.KEY]
        state=ops.hole_begin(dict(sketch_id=sketch,**OWNER))
        self.assertTrue(state['session']['can_confirm']);self.assertEqual(state['operation_controls']['type'],'HOLE')
        self.assertEqual(before,bpy.context.scene[model.KEY])
        with patch.object(cad,'undo_push') as undo:cad.confirm(OWNER);undo.assert_called_once()
        expected=.08*.045*.005-math.pi*.0018**2*.005
        self.assertAlmostEqual(self.exact_volume(),expected,places=11)
        restored=model.loads(model.dumps(runtime.doc()));self.assertEqual(restored['features'][-1]['kind'],'THROUGH')
    def test_counterbore_and_countersink_have_exact_seat_depths(self):
        sketch,p=self.plate(.01)
        ops.hole_begin(dict(sketch_id=sketch,kind='COUNTERBORE',**OWNER));cad.confirm(OWNER)
        f=runtime.doc()['features'][-1]
        expected=.08*.045*.01-math.pi*(.0031**2*.0032+.0018**2*(.01-.0032))
        self.assertAlmostEqual(self.exact_volume(),expected,places=11)
        cad.feature_set(dict(feature_id=f['id'],kind='COUNTERSINK',**OWNER))
        h=(.0071-.0036)/2
        cone=math.pi*h/3*(.00355**2+.00355*.0018+.0018**2)
        self.assertAlmostEqual(self.exact_volume(),.08*.045*.01-cone-math.pi*.0018**2*(.01-h),places=10)
    def test_hex_nut_and_editable_insert(self):
        sketch,p=self.plate(.02)
        ops.hole_begin(dict(sketch_id=sketch,kind='NUT',**OWNER));cad.confirm(OWNER)
        f=runtime.doc()['features'][-1]
        expected=.08*.045*.02-math.sqrt(3)/2*.0057**2*.0024-math.pi*.0018**2*(.02-.0024)
        self.assertAlmostEqual(self.exact_volume(),expected,places=11)
        cad.feature_set(dict(feature_id=f['id'],kind='INSERT',insert_diameter=.0045,insert_depth=.007,**OWNER))
        self.assertAlmostEqual(self.exact_volume(),.08*.045*.02-math.pi*(.0047/2)**2*.007,places=11)
    def test_partial_points_follow_edits_and_deleting_used_point_is_atomic(self):
        sketch,p=self.plate();q=self.draw('POINT',(.05,.02),(.05,.02))
        ops.hole_begin(dict(sketch_id=sketch,point_ids=[p],**OWNER));cad.confirm(OWNER)
        f=runtime.doc()['features'][-1]
        baseline=self.exact_volume()
        cad.entity_set(dict(entity_id=p,values={'x':.03},**OWNER))
        self.assertAlmostEqual(self.exact_volume(),baseline,places=11)
        doc=runtime.doc();sk=model.find(doc,'sketches',sketch)
        self.assertAlmostEqual(holes.points(sk,doc['features'][-1])[0]['x'],.03)
        before=model.dumps(doc)
        with self.assertRaises(CommandError):cad.entity_delete(dict(entity_id=p,**OWNER))
        self.assertEqual(model.dumps(runtime.doc()),before)
        cad.feature_set(dict(feature_id=f['id'],point_ids=None,**OWNER))
        self.assertAlmostEqual(self.exact_volume(),.08*.045*.005-2*math.pi*.0018**2*.005,places=11)
        with self.assertRaises(CommandError):cad.sketch_delete(dict(sketch_id=sketch,**OWNER))
    def test_failed_preview_cannot_confirm_previous_hole_and_cancel_restores(self):
        sketch,p=self.plate();before=bpy.context.scene[model.KEY]
        ops.hole_begin(dict(sketch_id=sketch,**OWNER))
        state=ops.operation_update(dict(tolerance=.5,**OWNER))
        self.assertFalse(state['session']['can_confirm']);self.assertTrue(state['error'])
        cad.confirm(OWNER);self.assertIsNotNone(runtime.session)
        cad.cancel(OWNER);self.assertEqual(bpy.context.scene[model.KEY],before)
    def test_profile_only_sketch_rejects_without_session(self):
        self.rect()
        with self.assertRaises(CommandError):ops.hole_begin(dict(sketch_id=runtime.active_sketch_id,**OWNER))
        self.assertIsNone(runtime.session)

if __name__=='__main__':
    suite=unittest.TestSuite(HoleTests(n) for n in HoleTests.__dict__ if n.startswith('test_'))
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():raise SystemExit(1)
