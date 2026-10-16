"""Named failing operations and explicit reversible recovery from sketch editing."""
import copy,sys,time,unittest
from pathlib import Path
from unittest.mock import patch
import bpy
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from test_cad import CadTests,OWNER,volume
from blender_tablet_remote.cad import document as model
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.cad.worker import worker
from blender_tablet_remote.commands import cad,history,mode
from blender_tablet_remote import commands
from blender_tablet_remote.errors import CommandError

class SketchFailureTests(CadTests):
    def pending(self,two=False):
        e=self.rect();sketch=runtime.active_sketch_id;self.extrude(e)
        doc=runtime.doc();body=doc['bodies'][0]['id']
        for i,edge in enumerate([[[.08,0,0],[.08,0,.02]]]+([[[.08,.045,0],[.08,.045,.02]]] if two else [])):
            doc['features'].append(dict(id='round'+str(i),name='Redondeo '+str(14+i),type='FILLET',order=model.next_order(doc),
                body_id=body,sketch_id=None,enabled=True,width=.003,segments=4,edges=[[edge]]))
        runtime.rebuild(doc);runtime.persist(doc)
        cad.sketch_activate(dict(sketch_id=sketch,**OWNER))
        cad.entity_set(dict(entity_id=e,values={'width':.09},**OWNER))
        return sketch
    def finish_error(self):
        with self.assertRaises(CommandError) as error:cad.sketch_finish(OWNER)
        return error.exception
    def test_failure_opens_the_stack_at_the_operation_and_keeps_the_draft(self):
        self.pending();before=bpy.context.scene[model.KEY];error=self.finish_error()
        self.assertIn('Redondeo 14',error.message);self.assertEqual(error.details['feature_id'],'round0')
        state=runtime.status();self.assertTrue(state['sketch_pending']);self.assertIsNone(state['active_sketch_id'])
        self.assertTrue(state['sketch_review']);self.assertEqual(state['selection'],dict(kind='FEATURE',id='round0'))
        self.assertEqual(state['sketch_failure']['name'],'Redondeo 14')
        self.assertEqual(before,bpy.context.scene[model.KEY])
    def test_delete_from_the_stack_finishes_in_one_undo(self):
        self.pending();self.finish_error();before=copy.deepcopy(runtime.doc())
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            state=cad.feature_delete(dict(feature_id='round0',**OWNER));undo.assert_called_once()
        self.assertFalse(state['sketch_pending']);self.assertIsNone(state['sketch_failure']);self.assertIsNone(state['active_sketch_id'])
        self.assertFalse(state['sketch_review']);self.assertIsNone(state['error'])
        doc=runtime.doc();self.assertEqual(len(doc['features']),len(before['features'])-1)
        self.assertNotIn('round0',[f['id'] for f in doc['features']]);self.assertEqual(doc['sketches'],before['sketches'])
        self.assertAlmostEqual(volume(self.obj()),.09*.045*.02,places=10)
    def test_advance_and_delete_each_failure_without_touching_later_steps(self):
        self.pending(two=True);self.finish_error()
        self.assertEqual(runtime.bar(),'round0')
        predecessor=runtime.doc()['features'][0]['id']
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            state=cad.feature_delete(dict(feature_id='round0',**OWNER));undo.assert_called_once()
        self.assertFalse(state['sketch_pending']);self.assertFalse(state['sketch_review'])
        self.assertEqual(runtime.bar(),predecessor)
        self.assertTrue(model.find(runtime.doc(),'features','round1')['enabled'])
        self.assertAlmostEqual(volume(self.obj()),.09*.045*.02,places=10)
        with self.assertRaises(CommandError):cad.history_rollback(dict(node_id='round1',**OWNER))
        self.assertEqual(runtime.bar(),'round1')
        self.assertEqual(runtime.status()['sketch_failure']['feature_id'],'round1')
        self.assertEqual(runtime.selection,dict(kind='FEATURE',id='round1'))
        cad.feature_delete(dict(feature_id='round1',**OWNER))
        self.assertEqual(runtime.bar(),predecessor)
        self.assertFalse(runtime.status()['sketch_review'])
    def test_rollback_from_failure_recalculates_only_the_requested_prefix(self):
        self.pending();self.finish_error()
        predecessor=runtime.doc()['features'][0]['id']
        state=cad.history_rollback(dict(node_id=predecessor,**OWNER))
        self.assertEqual(state['rollback_id'],predecessor);self.assertFalse(state['sketch_review'])
        self.assertIsNone(state['active_sketch_id']);self.assertIsNone(state['error'])
        self.assertAlmostEqual(volume(self.obj()),.09*.045*.02,places=10)
        with self.assertRaises(CommandError):cad.history_rollback(dict(node_id='round0',**OWNER))
        self.assertEqual(runtime.bar(),'round0');self.assertTrue(runtime.sketch_review)
    def test_finish_respects_pointer_before_invalid_fillet(self):
        sketch=self.pending()
        predecessor=runtime.doc()['features'][0]['id']
        cad.history_rollback(dict(node_id=predecessor,**OWNER))
        cad.sketch_activate(dict(sketch_id=sketch,**OWNER))
        entity=runtime.doc()['sketches'][0]['entities'][0]['id']
        cad.entity_set(dict(entity_id=entity,values={'width':.1},**OWNER))
        state=cad.sketch_finish(OWNER)
        self.assertEqual(state['rollback_id'],predecessor);self.assertIsNone(state['active_sketch_id'])
        self.assertIsNone(state['error']);self.assertAlmostEqual(volume(self.obj()),.1*.045*.02,places=10)
        self.assertTrue(model.find(runtime.doc(),'features','round0')['enabled'])
        with self.assertRaises(CommandError):cad.history_rollback(dict(node_id='round0',**OWNER))
    def test_rollback_request_sets_boundary_before_finishing_dirty_sketch(self):
        sketch=self.pending();state=cad.history_rollback(dict(node_id=sketch,**OWNER))
        self.assertEqual(state['rollback_id'],sketch);self.assertIsNone(state['active_sketch_id'])
        self.assertIsNone(state['error']);self.assertFalse(runtime.sketch_review)
        self.assertFalse(any(o.visible_get() for o in runtime.objects(runtime.doc())))
        predecessor=runtime.doc()['features'][0]['id']
        cad.history_rollback(dict(node_id=predecessor,**OWNER))
        self.assertAlmostEqual(volume(self.obj()),.09*.045*.02,places=10)

    def test_returning_to_the_source_sketch_allows_correction(self):
        sketch=self.pending();self.finish_error()
        cad.sketch_activate(dict(sketch_id=sketch,**OWNER))
        self.assertFalse(runtime.status()['sketch_review']);self.assertEqual(runtime.active_sketch_id,sketch)
        entity=runtime.doc()['sketches'][0]['entities'][0]['id']
        cad.entity_set(dict(entity_id=entity,values={'width':.08},**OWNER))
        self.assertIsNone(runtime.status()['sketch_failure'])
        cad.sketch_finish(OWNER)
        self.assertTrue(model.find(runtime.doc(),'features','round0')['enabled'])
    def test_existing_disable_action_also_recalculates_the_draft(self):
        self.pending();self.finish_error()
        state=cad.feature_set(dict(feature_id='round0',enabled=False,**OWNER))
        self.assertFalse(state['sketch_pending']);self.assertFalse(state['sketch_review'])
        self.assertFalse(model.find(runtime.doc(),'features','round0')['enabled'])

    def test_returning_to_cad_preserves_the_stack_review(self):
        self.pending();self.finish_error();runtime.leave()
        state=mode.mode_set(dict(mode='CAD',**OWNER))['cad']
        self.assertTrue(state['sketch_review']);self.assertIsNone(state['active_sketch_id'])
        self.assertEqual(state['selection'],dict(kind='FEATURE',id='round0'))
        self.assertEqual(state['rollback_id'],'round0')

    def test_feature_identity_crosses_the_real_worker(self):
        self.pending();commands.load_all();task=commands.get('cad.sketch.finish')(OWNER)
        deadline=time.monotonic()+30
        try:
            with self.assertRaises(CommandError) as error:
                while not task.poll():
                    self.assertLess(time.monotonic(),deadline);time.sleep(.005)
            self.assertEqual(error.exception.details['feature_id'],'round0')
            self.assertEqual(runtime.status()['sketch_failure']['name'],'Redondeo 14')
        finally:worker.shutdown()
    @unittest.skipIf(bpy.app.background,'GUI undo stack required')
    def test_undo_restores_the_deleted_operation_and_pending_edits(self):
        self.pending();self.finish_error();before=volume(self.obj())
        cad.feature_delete(dict(feature_id='round0',**OWNER))
        history.undo({})
        self.assertTrue(runtime.status()['sketch_pending']);self.assertTrue(model.find(runtime.doc(),'features','round0')['enabled'])
        self.assertAlmostEqual(volume(self.obj()),before,places=10)
        history.redo({});self.assertFalse(runtime.status()['sketch_pending']);self.assertNotIn('round0',[f['id'] for f in runtime.doc()['features']])

def run():
    suite=unittest.TestSuite(SketchFailureTests(n) for n in SketchFailureTests.__dict__ if n.startswith('test_'))
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
        import os
        os._exit(1)
    if not bpy.app.background:bpy.ops.wm.quit_blender()
if __name__=='__main__':
    if bpy.app.background:run()
    else:bpy.app.timers.register(run,first_interval=1.)
