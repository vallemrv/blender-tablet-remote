"""Snapshots reuse only unchanged validated CAD data, including across undo and previews."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.cad import document as model
from blender_tablet_remote.cad.runtime import CadRuntime
from blender_tablet_remote.errors import CommandError


class SnapshotCacheTests(unittest.TestCase):
    def setUp(self):
        self.scene = bpy.context.scene
        if model.KEY in self.scene: del self.scene[model.KEY]
        self.runtime = CadRuntime()
        self.doc = model.new_document()
        self.doc['sketches'] = [dict(id='s', name='Sketch', plane='XY', offset=0,
            body_id=self.doc['bodies'][0]['id'], entities=[dict(id='e', type='LINE', x=0., y=0., x2=.02, y2=.03)], constraints=[])]
        self.raw = model.dumps(self.doc)
        self.scene[model.KEY] = self.raw

    def test_unchanged_document_validates_once_and_returns_independent_copies(self):
        with patch.object(model, 'loads', wraps=model.loads) as parse:
            first = self.runtime.doc()
            first['sketches'][0]['entities'][0]['x2'] = 99
            self.assertEqual(self.runtime.doc()['sketches'][0]['entities'][0]['x2'], .02)
            self.assertEqual(parse.call_count, 1)
        self.assertEqual(self.scene[model.KEY], self.raw)

    def test_same_revision_changes_and_restoring_undo_json_invalidate(self):
        self.runtime.doc()
        changed = copy.deepcopy(self.doc)
        changed['sketches'][0]['entities'][0]['x2'] = .08
        self.scene[model.KEY] = model.dumps(changed)
        self.assertEqual(self.runtime.doc()['sketches'][0]['entities'][0]['x2'], .08)
        self.scene[model.KEY] = self.raw
        self.assertEqual(self.runtime.doc()['sketches'][0]['entities'][0]['x2'], .02)
        self.scene[model.KEY] = '{broken'
        with self.assertRaises(CommandError): self.runtime.doc()
        self.scene[model.KEY] = self.raw
        self.assertEqual(self.runtime.doc()['sketches'][0]['entities'][0]['x2'], .02)

    def test_new_scene_revalidates_even_identical_json(self):
        self.runtime.doc()
        other = bpy.data.scenes.new('Other cache scene')
        other[model.KEY] = self.raw
        try:
            bpy.context.window.scene = other
            with patch.object(model, 'loads', wraps=model.loads) as parse:
                self.runtime.doc()
                self.assertEqual(parse.call_count, 1)
        finally:
            bpy.context.window.scene = self.scene
            bpy.data.scenes.remove(other)

    def test_public_snapshot_cache_preserves_previews_and_does_not_freeze_selection(self):
        self.runtime.active_sketch_id = 's'
        with patch.object(model, 'public', wraps=model.public) as public:
            first = self.runtime.status()
            first['document']['sketches'][0]['entities'][0]['x2'] = 99
            self.runtime.selection = dict(kind='ENTITY', id='e', part='BODY', items=[dict(kind='ENTITY', id='e', part='BODY')])
            second = self.runtime.status()
            self.assertEqual(second['selection']['id'], 'e')
            self.assertEqual(second['document']['sketches'][0]['entities'][0]['x2'], .02)
            self.assertEqual(public.call_count, 1)
            preview = self.runtime.doc()
            preview['sketches'][0]['entities'][0]['x2'] = .04
            self.runtime.session = dict(id='session', operation='DRAG', preview=preview)
            self.assertEqual(self.runtime.status()['document']['sketches'][0]['entities'][0]['x2'], .04)
            self.assertEqual(public.call_count, 2)
            preview['sketches'][0]['entities'][0]['x2'] = .05
            self.assertEqual(self.runtime.status()['document']['sketches'][0]['entities'][0]['x2'], .05)
            self.runtime.session = None
            self.assertEqual(self.runtime.status()['document']['sketches'][0]['entities'][0]['x2'], .02)
            self.assertEqual(public.call_count, 4)


result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SnapshotCacheTests))
if not result.wasSuccessful(): raise SystemExit(1)
