"""Sketch edits keep the last valid solid until the editing boundary."""
import copy,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import bpy
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from test_cad import CadTests,OWNER,volume
from blender_tablet_remote.cad import document as model,occt
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.commands import cad,mode
from blender_tablet_remote.errors import CommandError

class DeferredSketchTests(CadTests):
    def part(self,whole=False):
        e=self.rect();sketch=runtime.active_sketch_id
        if whole:
            cad.extrude_begin(dict(sketch_id=sketch,depth=.02,**OWNER));cad.confirm(OWNER)
        else:self.extrude(e)
        cad.sketch_activate(dict(sketch_id=sketch,**OWNER))
        return e,sketch
    def test_dimensions_do_not_evaluate_until_finish(self):
        e,sketch=self.part();baseline=volume(self.obj())
        with patch.object(occt.evaluator,'evaluate',side_effect=AssertionError('Solid evaluation during sketch editing')):
            status=cad.entity_set(dict(entity_id=e,values={'width':.1},**OWNER))
            self.assertTrue(status['sketch_pending']);self.assertEqual(runtime.active_sketch_id,sketch)
            self.assertAlmostEqual(volume(self.obj()),baseline)
            model.loads(model.dumps(runtime.doc()))
        state=cad.sketch_finish(OWNER)
        self.assertFalse(state['sketch_pending']);self.assertIsNone(runtime.active_sketch_id)
        self.assertAlmostEqual(volume(self.obj()),.1*.045*.02,places=10)
    def test_open_drawing_stays_editable_and_invalid_finish_keeps_it(self):
        _,sketch=self.part(whole=True);baseline=volume(self.obj())
        line=self.draw('LINE',(.1,0),(.12,.01))
        self.assertEqual(runtime.doc()[model.DEFERRED_SKETCH],sketch)
        model.loads(model.dumps(runtime.doc()))
        with self.assertRaises(CommandError):cad.sketch_finish(OWNER)
        self.assertEqual(runtime.active_sketch_id,sketch)
        self.assertTrue(runtime.status()['sketch_pending']);self.assertTrue(runtime.status()['error'])
        self.assertAlmostEqual(volume(self.obj()),baseline)
        cad.entity_delete(dict(entity_id=line,**OWNER));cad.sketch_finish(OWNER)
        self.assertFalse(runtime.status()['sketch_pending']);self.assertIsNone(runtime.status()['error'])
    def test_drag_and_cancel_never_rebuild_the_solid(self):
        e,sketch=self.part();before=model.dumps(runtime.doc());baseline=volume(self.obj())
        with patch.object(occt.evaluator,'evaluate',side_effect=AssertionError('Solid evaluation during drag')):
            with patch.object(cad,'_pick',return_value=dict(kind='ENTITY',id=e,part='BODY')),patch.object(runtime,'point',return_value=(0.,0.)):
                cad.drag_begin(dict(u=.5,v=.5,**OWNER))
            with patch.object(runtime,'point',return_value=(.005,0)):
                cad.drag_update(dict(u=.6,v=.5,**OWNER))
            cad.cancel(OWNER)
        self.assertEqual(model.dumps(runtime.doc()),before);self.assertAlmostEqual(volume(self.obj()),baseline)
    def test_downstream_fillet_error_does_not_block_sketch_updates(self):
        e,sketch=self.part();cad.sketch_finish(OWNER)
        doc=runtime.doc();doc['features'].append(dict(id='finish',name='Finish',order=model.next_order(doc),type='FILLET',
            body_id=doc['bodies'][0]['id'],sketch_id=None,enabled=True,width=.003,segments=4,
            edges=[[[[0.,0.,0.],[0.,0.,.02]]]]))
        runtime.rebuild(doc);runtime.persist(doc);cad.sketch_activate(dict(sketch_id=sketch,**OWNER))
        baseline=volume(self.obj())
        cad.entity_set(dict(entity_id=e,values={'width':.001},**OWNER))
        self.assertAlmostEqual(volume(self.obj()),baseline)
        with self.assertRaises(CommandError):cad.sketch_finish(OWNER)
        cad.entity_set(dict(entity_id=e,values={'width':.09},**OWNER));cad.sketch_finish(OWNER)
        self.assertGreater(volume(self.obj()),baseline)
    def test_sketch_fillet_remapping_is_deferred_too(self):
        e,sketch=self.part();baseline=volume(self.obj())
        cad._set_selection([dict(kind='ENTITY',id=e,part='BODY')])
        with patch.object(occt.evaluator,'evaluate',side_effect=AssertionError('Evaluation while rounding a sketch')):
            cad.fillet(dict(radius=.002,**OWNER))
            self.assertTrue(runtime.status()['sketch_pending'])
            self.assertAlmostEqual(volume(self.obj()),baseline)
        cad.sketch_finish(OWNER);self.assertLess(volume(self.obj()),baseline)

    def test_object_mode_finishes_the_deferred_sketch(self):
        e,_=self.part();cad.entity_set(dict(entity_id=e,values={'width':.1},**OWNER))
        state=mode.mode_set(dict(mode='OBJECT',**OWNER))
        self.assertEqual(state['mode'],'OBJECT');self.assertNotIn(model.DEFERRED_SKETCH,runtime.doc())
        self.assertAlmostEqual(volume(self.obj()),.1*.045*.02,places=10)
    def test_save_and_load_keep_open_sketch_and_frozen_solid(self):
        _,sketch=self.part(whole=True);baseline=volume(self.obj());line=self.draw('LINE',(.1,0),(.12,.01))
        with tempfile.TemporaryDirectory() as folder:
            path=str(Path(folder)/'draft.blend')
            with runtime.saving():bpy.ops.wm.save_as_mainfile(filepath=path)
            runtime.leave();bpy.ops.wm.open_mainfile(filepath=path);runtime.reset()
            with patch.object(occt.evaluator,'evaluate',side_effect=AssertionError('Evaluation on loading an open draft')):
                mode.mode_set(dict(mode='CAD',**OWNER))
                self.assertEqual(runtime.active_sketch_id,sketch);self.assertTrue(runtime.status()['sketch_pending'])
                self.assertAlmostEqual(volume(self.obj()),baseline)
            cad.entity_delete(dict(entity_id=line,**OWNER));cad.sketch_finish(OWNER)
    def test_cancel_solid_started_in_sketch_uses_cached_predecessor(self):
        target=self.extrude(self.rect());cad.sketch_create(dict(support_id=target,**OWNER))
        hole=self.draw('CIRCLE',(.02,.02),(.025,.02));baseline=volume(self.obj())
        cad.extrude_begin(dict(profile_id='profile_'+hole,operation='CUT',target_id=target,depth=.01,**OWNER))
        with patch('blender_tablet_remote.cad.jobs.Calculation.run',side_effect=AssertionError('Synchronous restore')):
            cad.cancel(OWNER)
        self.assertAlmostEqual(volume(self.obj()),baseline)

    @unittest.skipIf(bpy.app.background,'GUI undo stack required')
    def test_native_undo_redo_recover_draft_and_completed_solid(self):
        from blender_tablet_remote.commands import history
        e,sketch=self.part();baseline=volume(self.obj())
        cad.entity_set(dict(entity_id=e,values={'width':.1},**OWNER));cad.sketch_finish(OWNER)
        history.undo({});self.assertTrue(runtime.status()['sketch_pending']);self.assertAlmostEqual(volume(self.obj()),baseline)
        history.redo({});self.assertFalse(runtime.status()['sketch_pending']);self.assertAlmostEqual(volume(self.obj()),.1*.045*.02,places=10)

def run():
    suite=unittest.TestSuite(DeferredSketchTests(n) for n in sorted(DeferredSketchTests.__dict__) if n.startswith('test_'))
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
        import os
        os._exit(1)
    if not bpy.app.background:bpy.ops.wm.quit_blender()
if __name__=='__main__':
    if bpy.app.background:run()
    else:bpy.app.timers.register(run,first_interval=1.)
