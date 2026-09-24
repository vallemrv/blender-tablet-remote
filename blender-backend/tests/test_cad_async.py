"""Real isolated Blender calculations, deferred replies and cancellation barriers."""
import copy
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cad import CadTests, OWNER, volume
from blender_tablet_remote import bridge, commands
from blender_tablet_remote.cad import document as model
from blender_tablet_remote.cad.jobs import PendingCommand
from blender_tablet_remote.cad.kernel import kernel
from blender_tablet_remote.cad.runtime import runtime, mesh_copy, PRISM_KEY
from blender_tablet_remote.cad.worker import worker
from blender_tablet_remote.commands import cad
from blender_tablet_remote.errors import CommandError


class AsyncCadTests(CadTests):
    def tearDown(self):
        bridge._cancel_pending_cad()
        super().tearDown()

    def wait(self, task):
        deadline = time.monotonic() + 30
        while not task.poll():
            self.assertLess(time.monotonic(), deadline)
            time.sleep(.005)
        return task.result

    def task(self, name, **payload):
        result = commands.get(name)(dict(payload, **OWNER))
        self.assertIsInstance(result, PendingCommand)
        return result

    def cut_profile(self):
        first = self.extrude(self.rect())
        cad.sketch_create(dict(support_id=first, **OWNER))
        hole = self.draw('CIRCLE', (.04, .02), (.045, .02))
        return first, hole

    def test_worker_evaluates_boolean_without_main_thread_kernel_and_keeps_identity(self):
        first, hole = self.cut_profile()
        obj = self.obj()
        before = obj.as_pointer(), volume(obj)
        with patch.object(kernel, 'cut', side_effect=AssertionError('Boolean on UI thread')):
            result = self.wait(self.task('cad.extrude.begin', profile_id='profile_'+hole,
                                         operation='CUT', target_id=first, depth=.01))
            self.assertTrue(result['session']['can_confirm'])
            self.assertEqual(before[0], obj.as_pointer())
            self.assertLess(volume(obj), before[1])
            self.wait(self.task('cad.extrude.update', depth=.015))
            expected = volume(obj)
            self.wait(self.task('cad.session.confirm'))
            self.assertAlmostEqual(volume(obj), expected)
        self.assertIsNone(runtime.session)
        self.assertEqual(len(runtime.objects(runtime.doc())), 1)

    def test_pump_keeps_capturing_and_answers_reads_while_reply_is_pending(self):
        first, hole = self.cut_profile()
        client = Mock(id=OWNER['_client_id'])
        message = dict(type='command', id='cut', command='cad.extrude.begin',
                       payload=dict(profile_id='profile_'+hole, operation='CUT', target_id=first, depth=.01))
        bridge._handle_command(client, message)
        self.assertIsNotNone(bridge._pending_cad)
        client.send_json.assert_not_called()
        bridge._handle_command(client, dict(id='read', command='cad.state', payload={}))
        self.assertTrue(client.send_json.call_args.args[0]['ok'])
        with patch.object(bridge, '_server', Mock()), patch.object(bridge, '_capture') as capture, \
                patch.object(bridge, '_broadcast_events'), patch.object(bridge.screen, 'keep_awake'):
            deadline = time.monotonic()+30
            while bridge._pending_cad:
                bridge._pump()
                self.assertLess(time.monotonic(), deadline)
                time.sleep(.005)
            self.assertGreater(capture.tick.call_count, 0)
        responses = [call.args[0] for call in client.send_json.call_args_list]
        self.assertTrue(next(r for r in responses if r['id'] == 'cut')['ok'])

    def test_save_cancel_and_reset_discard_late_results_and_restore_baseline(self):
        first, hole = self.cut_profile()
        baseline = model.dumps(runtime.doc()), volume(self.obj())
        for action in ('save', 'cancel', 'reset'):
            task = self.task('cad.extrude.begin', profile_id='profile_'+hole,
                             operation='CUT', target_id=first, depth=.01)
            self.assertFalse(task.poll())
            if action == 'save':
                runtime.suspend_save(); runtime.resume_save()
            elif action == 'cancel':
                cad.cancel(OWNER)
            else:
                runtime.cancel(); runtime.reset()
            with self.assertRaises(CommandError) as rejected:
                task.poll()
            self.assertEqual(rejected.exception.code, 'cad_cancelled')
            self.assertEqual(model.dumps(runtime.doc()), baseline[0])
            self.assertAlmostEqual(volume(self.obj()), baseline[1])
            self.assertFalse(any(o.get(PRISM_KEY) for o in bpy.data.objects))
            runtime.workspace = True

    def test_worker_failure_does_not_publish_or_prevent_retry(self):
        first, hole = self.cut_profile()
        before = volume(self.obj())
        task = self.task('cad.extrude.begin', profile_id='profile_'+hole,
                         operation='CUT', target_id=first, depth=.01)
        self.assertFalse(task.poll())
        worker.process.kill(); worker.process.wait(timeout=5)
        with self.assertRaises(CommandError):
            task.poll()
        self.assertIsNone(runtime.session)
        self.assertAlmostEqual(volume(self.obj()), before)
        self.wait(self.task('cad.extrude.begin', profile_id='profile_'+hole,
                            operation='CUT', target_id=first, depth=.01))
        self.assertLess(volume(self.obj()), before)

    def test_first_preview_after_loading_restores_without_a_main_thread_rebuild(self):
        from blender_tablet_remote.commands import mode
        first, hole = self.cut_profile()
        before = volume(self.obj())
        runtime.reset()
        mode.mode_set(dict(mode='CAD', **OWNER))
        self.wait(self.task('cad.extrude.begin', profile_id='profile_'+hole,
                            operation='CUT', target_id=first, depth=.01))
        with patch('blender_tablet_remote.cad.jobs.Calculation.run', side_effect=AssertionError('Synchronous restore')):
            cad.cancel(OWNER)
        self.assertAlmostEqual(volume(self.obj()), before)

    def test_compact_preview_defers_quad_layout_until_editable_copy(self):
        outer = self.rect()
        self.draw('CIRCLE', (.02, .02), (.025, .02))
        with patch('blender_tablet_remote.cad.runtime.quad_mesh', side_effect=AssertionError('Dense preview')):
            feature = self.extrude(outer, confirm=False)
            mesh_count = len(bpy.data.meshes)
            for depth in (.03, .04, .05):
                cad.extrude_update(dict(depth=depth, **OWNER))
                self.assertLessEqual(len(bpy.data.meshes), mesh_count)
            cad.confirm(OWNER)
        obj = self.obj()
        compact_count = len(obj.data.polygons)
        editable = mesh_copy(obj)
        self.assertTrue(all(len(p.vertices) == 4 for p in editable.data.polygons))
        self.assertGreater(len(editable.data.polygons), compact_count)
        self.assertAlmostEqual(volume(editable), volume(obj), places=8)
        self.assertEqual(len(obj.data.polygons), compact_count)

    def test_solver_and_rebuild_resume_in_order_and_end_keeps_last_sample(self):
        rectangle = self.rect()
        hit = dict(id=rectangle, kind='ENTITY', part='BODY')
        with patch.object(cad, '_pick', return_value=hit), patch.object(runtime, 'point', return_value=(0., 0.)):
            cad.drag_begin(dict(u=.5, v=.5, **OWNER))
        task = self.task('cad.drag.update', u=.6, v=.6)
        with patch.object(runtime, 'point', return_value=(.01, .02)):
            self.wait(task)
        expected = copy.deepcopy(runtime.session['preview']['sketches'])
        with patch.object(runtime, 'point', side_effect=AssertionError('END samples again')):
            self.wait(self.task('cad.drag.end'))
        self.assertEqual(runtime.doc()['sketches'], expected)

    def test_disconnect_cancels_pending_reply_without_publishing(self):
        first, hole = self.cut_profile()
        before = volume(self.obj())
        client = Mock(id=OWNER['_client_id'])
        bridge._handle_command(client, dict(id='cut', command='cad.extrude.begin',
            payload=dict(profile_id='profile_'+hole, operation='CUT', target_id=first, depth=.01)))
        self.assertIsNotNone(bridge._pending_cad)
        bridge._handle(client, dict(type='_client_gone', client_id=client.id))
        self.assertIsNone(bridge._pending_cad)
        self.assertIsNone(worker.pending)
        self.assertIsNone(runtime.session)
        self.assertAlmostEqual(volume(self.obj()), before)

    @unittest.skipIf(bpy.app.background, 'Native undo needs a window')
    def test_worker_confirmation_is_one_native_undo_and_redo(self):
        from blender_tablet_remote.commands import history
        first, hole = self.cut_profile()
        before = volume(self.obj())
        self.wait(self.task('cad.extrude.begin', profile_id='profile_'+hole,
                            operation='CUT', target_id=first, depth=.01))
        self.wait(self.task('cad.session.confirm'))
        after = volume(self.obj())
        self.assertLess(after, before)
        history.undo({})
        self.assertAlmostEqual(volume(self.obj()), before)
        history.redo({})
        self.assertAlmostEqual(volume(self.obj()), after)


if __name__ == '__main__':
    suite = unittest.TestSuite(AsyncCadTests(name) for name in AsyncCadTests.__dict__ if name.startswith('test_'))
    try:
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    finally:
        worker.shutdown()
    if not result.wasSuccessful():
        raise SystemExit(1)
