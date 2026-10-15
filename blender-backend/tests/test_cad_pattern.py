"""Feature patterns duplicate operands, follow sources and retain dependency guards."""
import math,sys,unittest
from pathlib import Path
from unittest.mock import patch
import bpy
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from test_cad import CadTests, OWNER, volume
from blender_tablet_remote.cad import document as model,occt,pattern
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.commands import cad,cad_operations as ops
from blender_tablet_remote.errors import CommandError

class PatternTests(CadTests):
    def hole(self,p=(.02,.02)):
        base=self.extrude(self.rect(),.005)
        cad.sketch_create(dict(support_id=base,**OWNER))
        self.draw('POINT',p,p)
        ops.hole_begin(dict(sketch_id=runtime.active_sketch_id,**OWNER));cad.confirm(OWNER)
        return runtime.doc()['features'][-1]['id']
    def exact(self):
        result=occt.evaluator.evaluate(runtime.doc());tip=next(iter(result['tips'].values()))
        return occt._volume(occt.evaluator._shapes[tip][1])/occt.MM**3
    def test_four_holes_and_source_edits(self):
        hole=self.hole();before=model.dumps(runtime.doc())
        state=ops.pattern_begin(dict(source_ids=[hole],count=4,spacing=.01,**OWNER))
        self.assertTrue(state['session']['can_confirm']);self.assertEqual(model.dumps(runtime.doc()),before)
        with patch.object(cad,'undo_push') as undo:cad.confirm(OWNER);undo.assert_called_once()
        self.assertAlmostEqual(self.exact(),.08*.045*.005-4*math.pi*.0018**2*.005,places=11)
        cad.feature_set(dict(feature_id=hole,extent='ONE',depth=.002,**OWNER))
        self.assertAlmostEqual(self.exact(),.08*.045*.005-4*math.pi*.0018**2*.002,places=11)
        with self.assertRaises(CommandError):cad.feature_delete(dict(feature_id=hole,**OWNER))
        cad.feature_set(dict(feature_id=hole,enabled=False,**OWNER))
        self.assertAlmostEqual(self.exact(),.08*.045*.005,places=11)
    def test_circular_six_and_partial_arc_include_endpoints(self):
        hole=self.hole((.055,.0225))
        state=ops.pattern_begin(dict(source_ids=[hole],kind='CIRCULAR',count=6,axis='Z',axis_origin=[.04,.0225,0],**OWNER))
        self.assertTrue(state['session']['can_confirm']);cad.confirm(OWNER)
        self.assertAlmostEqual(self.exact(),.08*.045*.005-6*math.pi*.0018**2*.005,places=11)
        f=runtime.doc()['features'][-1]
        cad.feature_set(dict(feature_id=f['id'],angle=180,count=4,**OWNER))
        f=runtime.doc()['features'][-1]
        self.assertEqual([t['angle'] for t in pattern.copies(f)],[60,120,180])
        self.assertAlmostEqual(self.exact(),.08*.045*.005-4*math.pi*.0018**2*.005,places=11)
    def test_grid_and_cancel(self):
        hole=self.hole((.02,.012));before=bpy.context.scene[model.KEY]
        ops.pattern_begin(dict(source_ids=[hole],count=3,spacing=.01,direction2='Y',count2=3,spacing2=.01,**OWNER))
        self.assertTrue(runtime.session['candidate']);cad.cancel(OWNER)
        self.assertEqual(before,bpy.context.scene[model.KEY])
        ops.pattern_begin(dict(source_ids=[hole],count=3,spacing=.01,direction2='Y',count2=3,spacing2=.01,**OWNER));cad.confirm(OWNER)
        self.assertAlmostEqual(self.exact(),.08*.045*.005-9*math.pi*.0018**2*.005,places=11)
    def test_captured_direction_is_metric_and_invalid_source_is_atomic(self):
        hole=self.hole();ops.pattern_begin(dict(source_ids=[hole],**OWNER))
        item=dict(kind='EDGE',points=[[0,0,0],[.01,0,0]],planar=False)
        with patch('blender_tablet_remote.commands.snap.query_cad_surface',return_value=item):
            state=ops.operation_update(dict(pick_direction=True,u=.5,v=.5,**OWNER))
        self.assertTrue(state['session']['can_confirm']);cad.confirm(OWNER)
        f=runtime.doc()['features'][-1]
        for p,q in zip(f['direction'],[[0.,0.,0.],[.01,0.,0.]]):
            for a,b in zip(p,q):self.assertAlmostEqual(a,b,places=8)
        before=bpy.context.scene[model.KEY]
        with self.assertRaises(CommandError):ops.pattern_begin(dict(source_ids=[f['id']],**OWNER))
        self.assertEqual(before,bpy.context.scene[model.KEY])
        model.loads(model.dumps(runtime.doc()))

if __name__=='__main__':
    suite=unittest.TestSuite(PatternTests(n) for n in PatternTests.__dict__ if n.startswith('test_'))
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():raise SystemExit(1)
