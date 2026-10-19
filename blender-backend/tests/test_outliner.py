"""blender --background --factory-startup --python-exit-code 1 --python este_archivo"""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import outliner, objects, selection, modal, sessions
from blender_tablet_remote.errors import CommandError, BadPayload


class OutlinerTests(unittest.TestCase):
    def setUp(self):
        sessions.cancel_all()
        if bpy.context.object and bpy.context.object.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
        for obj in list(bpy.data.objects): bpy.data.objects.remove(obj, do_unlink=True)
        bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection
        bpy.ops.mesh.primitive_cube_add()
        self.first = bpy.context.object
        self.first.name = 'Primero'
        bpy.ops.mesh.primitive_cube_add(location=(5, 0, 0))
        self.second = bpy.context.object
        self.second.name = 'Segundo'
        bpy.context.view_layer.update()
        self.undo_patch = patch.object(outliner, 'undo_push')
        self.undo = self.undo_patch.start()

    def tearDown(self):
        sessions.cancel_all()
        self.undo_patch.stop()

    def row(self, obj): return next(row for row in outliner.describe() if row['name'] == obj.name)
    def action(self, obj, kind, **kwargs):
        return outliner.action(dict(object_id=self.row(obj)['id'], action=kind, **kwargs))

    def test_lists_visible_hidden_locked_and_excluded_objects(self):
        self.first.hide_set(True)
        self.second.hide_select = True
        coll = bpy.data.collections.new('Excluida')
        bpy.context.scene.collection.children.link(coll)
        empty = bpy.data.objects.new('Referencia excluida', None)
        coll.objects.link(empty)
        bpy.context.view_layer.layer_collection.children[coll.name].exclude = True
        rows = {r['name']: r for r in outliner.listing({})['objects']}
        self.assertEqual(len(rows), 3)
        self.assertTrue(rows['Primero']['hidden'])
        self.assertTrue(rows['Segundo']['locked'])
        self.assertFalse(rows[empty.name]['in_view_layer'])
        self.assertEqual(rows[empty.name]['collections'], ['Excluida'])

    def test_rename_keeps_identity_and_old_id_never_targets_replacement(self):
        identity = self.row(self.first)['id']
        self.action(self.first, 'RENAME', name='Referencia nueva')
        self.assertEqual(self.row(self.first)['id'], identity)
        self.assertEqual(self.first.name, 'Referencia nueva')
        self.undo.assert_called_once()
        bpy.data.objects.remove(self.first, do_unlink=True)
        self.second.name = 'Referencia nueva'
        with self.assertRaises(CommandError):
            outliner.action(dict(object_id=identity, action='LOCK', value=True))
        self.assertFalse(self.second.hide_select)

    def test_lock_deselects_and_cannot_be_bypassed_by_select_or_reveal(self):
        self.action(self.second, 'LOCK', value=True)
        self.assertTrue(self.second.hide_select)
        self.assertFalse(self.second.select_get())
        self.assertNotEqual(bpy.context.view_layer.objects.active, self.second)
        with self.assertRaises(CommandError): objects.select({'name': self.second.name})
        with self.assertRaises(CommandError): self.action(self.second, 'SELECT')
        objects.select_all({'value': True})
        self.assertTrue(self.first.select_get())
        self.assertFalse(self.second.select_get())
        objects.reveal({'objects': [self.second.name], 'select': True})
        self.assertFalse(self.second.select_get())
        self.action(self.second, 'LOCK', value=False)
        self.action(self.second, 'SELECT')
        self.assertTrue(self.second.select_get())

    def test_pick_and_box_ignore_locked_objects(self):
        self.action(self.first, 'LOCK', value=True)
        self.second.select_set(False)
        self.action(self.second, 'SELECT')
        with patch.object(selection, 'find_view3d', return_value=(None, None, None, SimpleNamespace())), \
             patch.object(selection.camera, 'sync_from_region'), \
             patch.object(selection.camera, 'ray', return_value=(Vector((0, 0, 10)), Vector((0, 0, -1)))), \
             patch.object(selection, '_object_hit', return_value=(self.first, Vector(), 0)):
            self.assertFalse(selection.pick({'u': .5, 'v': .5, 'mode': 'SET'})['hit'])
            self.assertEqual(bpy.context.view_layer.objects.active, self.second)
        with patch.object(selection, 'find_view3d', return_value=(None, None, None, SimpleNamespace())), \
             patch.object(selection.camera, 'sync_from_region'), \
             patch.object(selection.camera, 'project', return_value=(.5, .5)):
            selection._object_shape_select({'mode': 'SET'}, lambda u, v: True)
        self.assertFalse(self.first.select_get())
        self.assertTrue(self.second.select_get())

    def test_hide_show_preserves_lock_and_saves_native_flags(self):
        self.action(self.first, 'LOCK', value=True)
        self.action(self.first, 'VISIBLE', value=False)
        self.assertTrue(self.first.hide_get())
        self.action(self.first, 'VISIBLE', value=True)
        self.assertFalse(self.first.hide_get())
        self.assertTrue(self.first.hide_select)
        self.assertEqual(self.undo.call_count, 3)
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'objects.blend')
            bpy.ops.wm.save_as_mainfile(filepath=path)
            bpy.ops.wm.open_mainfile(filepath=path)
            self.assertTrue(bpy.data.objects['Primero'].hide_select)

    def test_move_targets_only_the_row_and_uses_existing_modal_undo(self):
        self.first.select_set(True)
        rv3d = SimpleNamespace(view_matrix=Matrix.Identity(4), view_rotation=Matrix.Identity(3).to_quaternion(),
                               view_distance=10., window_matrix=Matrix.Identity(4))
        with patch.object(modal, 'require_rv3d', return_value=rv3d), patch.object(modal, 'undo_push') as undo:
            result = outliner.move(dict(object_id=self.row(self.second)['id'], _client_id='tablet',
                transform=dict(axes=['X'], step=.25, snap=False, snap_type='NONE', orientation='GLOBAL', value_mode='RELATIVE')))
            self.assertEqual(result['transform']['mode'], 'MOVE')
            self.assertEqual(modal.session.step, .25)
            self.assertEqual([obj for obj, _ in modal.session.originals], [self.second])
            modal.set_value({'_client_id': 'tablet', 'values': [2., 0., 0.]})
            self.assertAlmostEqual(self.second.location.x, 7.)
            self.assertAlmostEqual(self.first.location.x, 0.)
            modal.confirm({'_client_id': 'tablet'})
            undo.assert_called_once()
        self.undo.assert_not_called()

    def test_failed_move_keeps_selection_and_does_not_open_modal(self):
        selected = [o.name for o in bpy.context.selected_objects]
        with self.assertRaises(BadPayload): outliner.move(dict(object_id=self.row(self.first)['id'], transform=None))
        self.assertEqual([o.name for o in bpy.context.selected_objects], selected)
        self.assertEqual(bpy.context.view_layer.objects.active, self.second)
        self.assertFalse(modal.session.active)


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(OutlinerTests))
    if not result.wasSuccessful(): raise SystemExit(1)
