"""Exact split, associative derived bodies and reversible plane placement."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
import bpy
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from test_cad import CadTests, OWNER, volume
from blender_tablet_remote.cad import document as model,occt
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.commands import cad
from blender_tablet_remote.errors import CommandError

class SplitTests(CadTests):
    def part(self):
        e=self.draw('RECTANGLE',(0,0),(.04,.04));f=self.extrude(e,.04)
        return e,f,runtime.doc()['features'][-1]['body_id']
    def split(self,body):
        cad.plane_begin(dict(split_body_id=body,**OWNER))
        return cad.plane_update(dict(offset=.02,**OWNER))
    def test_two_halves_follow_original_and_serialize(self):
        e,f,body=self.part();state=self.split(body)
        self.assertTrue(state['session']['can_confirm'],state['error'])
        with patch.object(cad,'undo_push') as undo:cad.confirm(OWNER);undo.assert_called_once()
        self.assertEqual(len(runtime.objects(runtime.doc())),2)
        self.assertAlmostEqual(sum(volume(o) for o in runtime.objects(runtime.doc())),.04**3,places=10)
        cad.entity_set(dict(entity_id=e,values={'width':.06},**OWNER))
        self.assertAlmostEqual(sum(volume(o) for o in runtime.objects(runtime.doc())),.06*.04*.04,places=10)
        model.loads(model.dumps(runtime.doc()))
    def test_cancel_and_invalid_plane(self):
        e,f,body=self.part();before=bpy.context.scene[model.KEY];self.split(body)
        state=cad.plane_update(dict(offset=.08,**OWNER))
        self.assertFalse(state['session']['can_confirm']);self.assertTrue(state['error'])
        with patch.object(cad,'undo_push') as undo:cad.confirm(OWNER);undo.assert_not_called()
        self.assertIsNotNone(runtime.session);cad.cancel(OWNER)
        self.assertEqual(before,bpy.context.scene[model.KEY]);self.assertEqual(len(runtime.objects(runtime.doc())),1)
    def test_derived_body_accepts_features_and_protects_source(self):
        e,f,body=self.part();self.split(body);cad.confirm(OWNER)
        doc=runtime.doc();split=doc['features'][-1]['id'];child=doc['bodies'][-1]['id']
        cad.body_activate(dict(body_id=child,**OWNER));cad.sketch_create(dict(plane='XY',offset=.04,**OWNER))
        rectangle=self.draw('RECTANGLE',(0,0),(.02,.02));self.extrude(rectangle,.01)
        result=occt.evaluator.evaluate(runtime.doc());tip=result['tips'][child]
        self.assertAlmostEqual(occt._volume(occt.evaluator._shapes[tip][1])/1e9,.04*.04*.02+.02*.02*.01,places=10)
        with self.assertRaises(CommandError):cad.feature_delete(dict(feature_id=split,**OWNER))
        with self.assertRaises(CommandError):cad.feature_set(dict(feature_id=split,keep='BELOW',**OWNER))
        cad.feature_set(dict(feature_id=f,depth=.05,**OWNER))
        model.loads(model.dumps(runtime.doc()))
    def test_saved_plane_association_and_history(self):
        e,f,body=self.part();cad.plane_create(dict(base='XY',translation=[0,0,.02],**OWNER))
        plane=runtime.doc()['planes'][-1]['id']
        cad.plane_begin(dict(split_body_id=body,plane_id=plane,**OWNER));cad.confirm(OWNER)
        split=runtime.doc()['features'][-1]['id']
        cad.plane_set(dict(plane_id=plane,translation=[0,0,.01],**OWNER))
        self.assertAlmostEqual(sorted(volume(o) for o in runtime.objects(runtime.doc()))[0],.04*.04*.01,places=10)
        cad.history_rollback(dict(node_id=f,**OWNER));self.assertEqual(len(runtime.objects(runtime.doc())),1)
        cad.history_rollback(dict(node_id=split,**OWNER));self.assertEqual(len(runtime.objects(runtime.doc())),2)
    def test_cut_can_target_initial_derived_solid(self):
        e,f,body=self.part();self.split(body);cad.confirm(OWNER)
        split=runtime.doc()['features'][-1]['id'];child=runtime.doc()['bodies'][-1]['id']
        cad.body_activate(dict(body_id=child,**OWNER));cad.sketch_create(dict(plane='XY',offset=.04,**OWNER))
        hole=self.draw('CIRCLE',(.02,.02),(.025,.02))
        cad.extrude_begin(dict(operation='CUT',profile_id='profile_'+hole,target_id=split,target_body_id=child,depth=.01,**OWNER))
        cad.confirm(OWNER)
        doc=runtime.doc();self.assertEqual(doc['features'][-1]['body_id'],child)
        result=occt.evaluator.evaluate(doc)
        self.assertAlmostEqual(occt._volume(occt.evaluator._shapes[result['tips'][body]][1])/1e9,.04*.04*.02,places=10)
        self.assertAlmostEqual(occt._volume(occt.evaluator._shapes[result['tips'][child]][1])/1e9,.04*.04*.02-3.141592653589793*.005**2*.01,places=10)
        model.loads(model.dumps(doc))

    def test_derived_history_cannot_precede_split(self):
        e,f,body=self.part();self.split(body);cad.confirm(OWNER)
        child=runtime.doc()['bodies'][-1]['id']
        cad.history_rollback(dict(node_id=f,**OWNER));cad.body_activate(dict(body_id=child,**OWNER))
        before=bpy.context.scene[model.KEY]
        with self.assertRaises(CommandError):cad.sketch_create(dict(plane='XY',**OWNER))
        self.assertEqual(before,bpy.context.scene[model.KEY])

    @unittest.skipIf(bpy.app.background,'GUI undo stack required')
    def test_native_undo_redo_restores_split(self):
        e,f,body=self.part();before=model.dumps(runtime.doc());self.split(body);cad.confirm(OWNER)
        from blender_tablet_remote.commands import history
        history.undo({});self.assertEqual(model.dumps(runtime.doc()),before);self.assertEqual(len(runtime.objects(runtime.doc())),1)
        history.redo({});self.assertEqual(len(runtime.objects(runtime.doc())),2)

    def test_one_side_and_deleting_unused_split(self):
        e,f,body=self.part();self.split(body);cad.confirm(OWNER);identifier=runtime.doc()['features'][-1]['id']
        cad.feature_set(dict(feature_id=identifier,keep='ABOVE',**OWNER))
        self.assertEqual(len(runtime.doc()['bodies']),1);self.assertAlmostEqual(volume(self.obj()),.04*.04*.02,places=10)
        cad.feature_set(dict(feature_id=identifier,keep='BOTH',**OWNER))
        cad.feature_delete(dict(feature_id=identifier,**OWNER));self.assertEqual(len(runtime.doc()['bodies']),1)
        self.assertAlmostEqual(volume(self.obj()),.04**3,places=10)

if __name__=='__main__':
    suite=unittest.TestSuite(SplitTests(n) for n in SplitTests.__dict__ if n.startswith('test_'))
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():raise SystemExit(1)
