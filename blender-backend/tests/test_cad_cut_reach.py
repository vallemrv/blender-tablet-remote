"""An initially empty cut remains editable until it reaches material."""
import sys,time,unittest
from pathlib import Path
from unittest.mock import patch
import bpy
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from test_cad import CadTests,OWNER,volume
from blender_tablet_remote.cad import document as model
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.cad.worker import worker
from blender_tablet_remote.commands import cad,history
from blender_tablet_remote import commands

class CutReachTests(CadTests):
    def cavity(self):
        target=self.extrude(self.rect(),.006)
        cad.sketch_create(dict(plane='XY',offset=.04,**OWNER))
        circle=self.draw('CIRCLE',(.04,.02),(.042,.02))
        cad.sketch_finish(OWNER)
        return dict(profile_id='profile_'+circle,operation='CUT',target_id=target,depth=.01,**OWNER)
    def test_empty_begin_keeps_controls_without_persisting_or_confirming(self):
        payload=self.cavity();before=model.dumps(runtime.doc());baseline=volume(self.obj())
        state=cad.extrude_begin(payload)
        self.assertTrue(state['session']['active']);self.assertFalse(state['session']['can_confirm'])
        self.assertEqual(state['session']['depth'],.01);self.assertIn('Perforar todo',state['error'])
        self.assertEqual(model.dumps(runtime.doc()),before);self.assertAlmostEqual(volume(self.obj()),baseline)
        with patch.object(cad,'undo_push') as undo:cad.confirm(OWNER);undo.assert_not_called()
        self.assertIsNotNone(runtime.session);self.assertEqual(model.dumps(runtime.doc()),before)
        cad.cancel(OWNER);self.assertEqual(model.dumps(runtime.doc()),before)
    def test_depth_can_reach_material_then_retreat_without_stale_preview(self):
        payload=self.cavity();before=model.dumps(runtime.doc());baseline=volume(self.obj());cad.extrude_begin(payload)
        state=cad.extrude_update(dict(depth=.04,**OWNER))
        self.assertTrue(state['session']['can_confirm']);self.assertIsNone(state['error'])
        self.assertLess(volume(self.obj()),baseline)
        state=cad.extrude_update(dict(depth=.01,**OWNER))
        self.assertFalse(state['session']['can_confirm']);self.assertAlmostEqual(volume(self.obj()),baseline)
        self.assertEqual(state['session']['depth'],.01);self.assertEqual(model.dumps(runtime.doc()),before)
        cad.extrude_update(dict(depth=.04,**OWNER))
        with patch.object(cad,'undo_push') as undo:cad.confirm(OWNER);undo.assert_called_once()
        self.assertEqual(runtime.doc()['features'][-1]['depth'],.04)
    def test_through_all_can_be_selected_after_empty_begin(self):
        payload=self.cavity();baseline=volume(self.obj());cad.extrude_begin(payload)
        state=cad.extrude_update(dict(extent='THROUGH_ALL',**OWNER))
        self.assertTrue(state['session']['can_confirm']);self.assertIsNone(state['error'])
        cad.confirm(OWNER);self.assertLess(volume(self.obj()),baseline)
        self.assertEqual(runtime.doc()['features'][-1]['extent'],'THROUGH_ALL')
    def test_face_extent_can_be_adjusted_after_empty_begin(self):
        cad.extrude_begin(self.cavity())
        for z,valid in ((.03,False),(0.,True)):
            with patch.object(cad,'_face_target',return_value=dict(origin=[0,0,z],normal=[0,0,1])):
                state=cad.extrude_update(dict(extent='TO_FACE',u=.5,v=.5,**OWNER))
            self.assertEqual(state['session']['can_confirm'],valid)
        cad.confirm(OWNER);self.assertEqual(runtime.doc()['features'][-1]['extent'],'TO_FACE')
    def test_empty_begin_crosses_worker_as_an_adjustable_session(self):
        payload=self.cavity();commands.load_all();task=commands.get('cad.extrude.begin')(payload)
        deadline=time.monotonic()+30
        try:
            while not task.poll():
                self.assertLess(time.monotonic(),deadline);time.sleep(.005)
            self.assertTrue(task.result['session']['active']);self.assertFalse(task.result['session']['can_confirm'])
        finally:worker.shutdown()
    @unittest.skipIf(bpy.app.background,'GUI undo stack required')
    def test_reaching_material_commits_one_reversible_cut(self):
        payload=self.cavity();before=model.dumps(runtime.doc());baseline=volume(self.obj())
        cad.extrude_begin(payload);cad.extrude_update(dict(depth=.04,**OWNER));cad.confirm(OWNER)
        result=volume(self.obj());history.undo({})
        self.assertEqual(model.dumps(runtime.doc()),before);self.assertAlmostEqual(volume(self.obj()),baseline)
        history.redo({});self.assertAlmostEqual(volume(self.obj()),result)

def run():
    suite=unittest.TestSuite(CutReachTests(n) for n in CutReachTests.__dict__ if n.startswith('test_'))
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
        import os
        os._exit(1)
    if not bpy.app.background:bpy.ops.wm.quit_blender()
if __name__=='__main__':
    if bpy.app.background:run()
    else:bpy.app.timers.register(run,first_interval=1.)
