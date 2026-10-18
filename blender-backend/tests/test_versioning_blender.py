"""Real .blend save/recover integration; Git runs off the main thread."""
import sys,time,tempfile,unittest,threading
from pathlib import Path
from unittest.mock import patch
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.versioning.runtime import Runtime,identifier,KEY
from blender_tablet_remote.versioning.core import Store
from blender_tablet_remote.errors import CommandError

class BlenderVersionTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name)
        bpy.ops.wm.read_factory_settings(use_empty=False)
        for s in bpy.data.scenes:
            if KEY in s:del s[KEY]
        bpy.ops.wm.save_as_mainfile(filepath=str(self.root/'drawing.blend'))
        self.runtime=Runtime();self.runtime.store=Store(self.root/'versions')
        self.runtime.store.identity('Test','test@example.invalid')
    def finish(self):
        deadline=time.monotonic()+40
        while self.runtime.future:
            self.assertLess(time.monotonic(),deadline)
            self.runtime.poll();time.sleep(.01)
        status=self.runtime.status();self.assertFalse(status.get('error'),status.get('error'))
        return status
    def test_exploration_keeps_latest_unsaved_edits_and_resumes_each_idea(self):
        self.runtime.start('commit',dict(message='First'));first=self.finish()['head']
        bpy.data.objects['Cube'].location.x=7
        self.runtime.start('commit',dict(message='Second'));second=self.finish()['head']
        gate=threading.Event();original=self.runtime.store.prepare_navigation
        def slow(*args):gate.wait(10);return original(*args)
        with patch.object(self.runtime.store,'prepare_navigation',side_effect=slow):
            self.runtime.start('explore',dict(revision=first,label='Alternativa'))
            bpy.data.objects['Cube'].location.x=9
            gate.set();result=self.finish()
        self.assertAlmostEqual(bpy.data.objects['Cube'].location.x,0)
        self.assertEqual(result['branch'],'ideas/alternativa');self.assertEqual(result['head'],first)
        main=self.runtime.store.status(identifier(),bpy.data.filepath,history_branch='main')
        self.assertIn(second,[x['id'] for x in main['commits']])
        bpy.data.objects['Cube'].location.x=3
        self.runtime.start('commit',dict(message='Different idea'));idea=self.finish()
        self.assertEqual(idea['commits'][0]['parents'],[first])
        self.runtime.start('switch',dict(branch='main'));self.finish()
        self.assertAlmostEqual(bpy.data.objects['Cube'].location.x,9)
        self.runtime.start('switch',dict(branch='ideas/alternativa'));self.finish()
        self.assertAlmostEqual(bpy.data.objects['Cube'].location.x,3)

    def test_legacy_clone_gets_a_separate_working_file_before_switching(self):
        self.runtime.start('commit',dict(message='First'));first=self.finish()['head'];repo_id=identifier()
        internal=self.runtime.store.repo(repo_id)/'model.blend'
        bpy.ops.wm.open_mainfile(filepath=str(internal),use_scripts=False)
        bpy.data.objects['Cube'].location.x=5
        self.runtime.start('explore',dict(revision=first,label='Desde copia'));self.finish()
        self.assertNotEqual(Path(bpy.data.filepath),internal)
        self.assertAlmostEqual(bpy.data.objects['Cube'].location.x,0)
        self.runtime.start('switch',dict(branch='main'));self.finish()
        self.assertAlmostEqual(bpy.data.objects['Cube'].location.x,5)

    def test_worker_does_not_block_status_and_bad_message_does_not_start_repo(self):
        with self.assertRaises(CommandError):self.runtime.start('commit',dict(message=''))
        self.assertIsNone(identifier())
        gate=threading.Event();original=self.runtime.store.status
        def slow(*args):gate.wait(10);return original(*args)
        with patch.object(self.runtime.store,'status',side_effect=slow):
            result=self.runtime.start('status',{})
            start=time.monotonic();self.assertTrue(result['busy'])
            self.assertTrue(self.runtime.status()['busy']);self.assertLess(time.monotonic()-start,.1)
            gate.set();self.finish()
    def test_other_file_opened_during_restore_is_not_overwritten(self):
        self.runtime.start('commit',dict(message='First'));first=self.finish()['commits'][0]['id']
        gate=threading.Event();original=self.runtime.store.prepare_navigation
        def slow(*args):gate.wait(10);return original(*args)
        with patch.object(self.runtime.store,'prepare_navigation',side_effect=slow):
            self.runtime.start('restore',dict(revision=first))
            bpy.ops.wm.read_factory_settings(use_empty=True)
            gate.set()
            deadline=time.monotonic()+30
            while self.runtime.future:
                self.assertLess(time.monotonic(),deadline);self.runtime.poll();time.sleep(.01)
        self.assertFalse(bpy.data.objects);self.assertEqual(bpy.data.filepath,'')
        self.assertFalse(list(self.root.glob('.valletrack-restore-*')))

result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(BlenderVersionTests))
if not result.wasSuccessful():raise SystemExit(1)
