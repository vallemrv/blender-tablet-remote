"""Pasos Edit: blender --background --factory-startup --python-exit-code 1 --python este_archivo."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy
import bmesh
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import modal, selection, sessions
from blender_tablet_remote.camera import camera
from blender_tablet_remote.errors import CommandError


class TransformStepsTests(unittest.TestCase):
    def setUp(self):
        sessions.cancel_all()
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add(size=.02)
        self.obj = bpy.context.object
        bpy.context.scene.tool_settings.use_proportional_edit = False
        bpy.context.scene.tool_settings.use_mesh_automerge = False
        bpy.context.scene.tool_settings.mesh_select_mode = (True, False, False)
        bpy.ops.object.mode_set(mode='EDIT')
        self.bm = bmesh.from_edit_mesh(self.obj.data)
        for seq in (self.bm.verts, self.bm.edges, self.bm.faces):
            seq.ensure_lookup_table()
        self.original = [v.co.copy() for v in self.bm.verts]
        self.a = next(v.index for v in self.bm.verts if all(c > 0 for c in v.co))
        self.b = next(v.index for v in self.bm.verts if v.co.x < 0 and v.co.y > 0 and v.co.z > 0)
        self.c = next(v.index for v in self.bm.verts if v.co.x < 0 and v.co.y < 0 and v.co.z > 0)
        selection.sel_elements(dict(mode='SET', verts=[self.a]))
        camera.reset()
        camera._synced = True
        camera.location = Vector()
        camera.rotation = Quaternion((1, 0, 0, 0))
        camera.distance = .1
        camera.perspective = 'PERSP'
        camera.set_clipping(.0001, 10)
        self.rv3d = SimpleNamespace(window_matrix=Matrix(((1,0,0,0),(0,2,0,0),(0,0,-1,-.02),(0,0,-1,0))))
        region = SimpleNamespace(width=1000, height=500)
        self.patches = [patch.object(selection, 'find_view3d', return_value=(None,None,region,self.rv3d)),
                        patch.object(modal, 'require_rv3d', return_value=self.rv3d),
                        patch.object(modal.state, 'snapshot', return_value={}),
                        patch.object(modal, 'undo_push')]
        for p in self.patches:
            result = p.start()
        self.undo = result

    def tearDown(self):
        sessions.cancel_all()
        for p in reversed(self.patches): p.stop()

    def begin(self, mode='MOVE', **kw):
        return modal.begin(dict(mode=mode, _client_id='tablet', **kw))

    def select_next(self, index, kind='vert', **kw):
        # Sesión y geometría reales; el test de sondeo inferior comprueba el raycast.
        with patch.object(selection, 'pick', return_value=dict(hit=True, element=kind, index=index)):
            return modal.select_next(dict({'_client_id': 'tablet', 'mode': 'SET'}, **kw))

    def assert_position(self, index, value):
        self.assertLess((self.bm.verts[index].co - Vector(value)).length, 1e-7)

    def test_move_z_10mm_then_another_vertex_x_30mm(self):
        first = self.begin(axes=['Z'], step=.001, snap_type='INCREMENT')
        modal.set_value(dict(values=[0, 0, .01]))
        next_step = self.select_next(self.b)
        self.assertNotEqual(first['session_id'], next_step['session_id'])
        self.assertEqual(next_step['values'], [0, 0, 0])
        self.assertEqual(next_step['axes'], ['Z'])
        self.assertAlmostEqual(next_step['step'], .001)
        self.assert_position(self.a, self.original[self.a] + Vector((0, 0, .01)))
        modal.set_axes(dict(axes=['X']))
        modal.set_value(dict(values=[.03, 0, 0]))
        self.select_next(self.c)
        self.assert_position(self.b, self.original[self.b] + Vector((.03, 0, 0)))
        self.assertEqual(self.undo.call_count, 2)
        modal.set_value(dict(values=[.02, 0, 0]))
        modal.cancel({})
        self.assert_position(self.c, self.original[self.c])
        self.assert_position(self.a, self.original[self.a] + Vector((0, 0, .01)))
        self.assert_position(self.b, self.original[self.b] + Vector((.03, 0, 0)))
        self.assertEqual(self.undo.call_count, 2)

    def test_probe_does_not_change_selection_and_uses_preview(self):
        self.begin(axes=['Z'])
        modal.set_value(dict(values=[0, 0, .01]))
        point = self.bm.verts[self.b].co.copy()
        point.x *= .98
        point.y *= .98
        u, v = camera.project(point, self.rv3d)
        before = [vert.select for vert in self.bm.verts]
        probe = selection.pick(dict(u=u, v=v, _probe=True))
        self.assertTrue(probe['hit'])
        self.assertEqual(probe['index'], self.b)
        self.assertEqual(before, [vert.select for vert in self.bm.verts])
        result = modal.select_next(dict(u=u, v=v, _client_id='tablet'))
        self.assertTrue(result['selection_changed'])
        self.assertEqual(modal.session.selection_signature, frozenset([self.b]))
        self.undo.assert_called_once()

    def test_miss_same_selection_and_empty_toggle_keep_current_step(self):
        original = self.begin()
        modal.set_value(dict(values=[0, 0, .01]))
        self.assertFalse(self.select_next(self.a)['selection_changed'])
        self.assertFalse(self.select_next(self.a, mode='TOGGLE')['selection_changed'])
        result = modal.select_next(dict(u=0, v=0, _client_id='tablet'))
        self.assertFalse(result['selection_changed'])
        self.assertEqual(result['session_id'], original['session_id'])
        self.undo.assert_not_called()

    def test_change_unmodified_selection_has_no_empty_undo(self):
        self.begin()
        self.select_next(self.b)
        self.select_next(self.c)
        self.undo.assert_not_called()
        modal.cancel({})
        for i, co in enumerate(self.original): self.assert_position(i, co)

    def test_rotate_and_scale_continue_with_fresh_values_and_pivot(self):
        for mode in ('ROTATE', 'SCALE'):
            with self.subTest(mode=mode):
                sessions.cancel_all()
                selection.sel_elements(dict(mode='SET', verts=[self.a, self.b]))
                first = self.begin(mode, axes=['Z'] if mode == 'ROTATE' else [], orientation='LOCAL')
                modal.set_value(dict(angle=30) if mode == 'ROTATE' else dict(values=[2, 2, 2]))
                committed = [v.co.copy() for v in self.bm.verts]
                result = self.select_next(self.c)
                self.assertNotEqual(first['session_id'], result['session_id'])
                self.assertEqual(result['mode'], mode)
                self.assertEqual(result['values'], [0, 0, 0] if mode == 'ROTATE' else [1, 1, 1])
                self.assertEqual(result['orientation'], 'LOCAL')
                self.assertLess((modal.session.pivot - self.obj.matrix_world @ self.bm.verts[self.c].co).length, 1e-7)
                modal.cancel({})
                for i, co in enumerate(committed): self.assert_position(i, co)

    def test_edges_and_faces_rebuild_effective_selection(self):
        for kind, flags, seq in [('edge', (False, True, False), self.bm.edges),
                                 ('face', (False, False, True), self.bm.faces)]:
            with self.subTest(kind=kind):
                sessions.cancel_all()
                bpy.context.scene.tool_settings.mesh_select_mode = flags
                for collection in (self.bm.verts, self.bm.edges, self.bm.faces):
                    for elem in collection: elem.select = False
                seq[0].select = True
                self.bm.select_flush_mode()
                bmesh.update_edit_mesh(self.obj.data)
                self.begin()
                modal.set_value(dict(values=[0, 0, .01]))
                self.select_next(len(seq)-1, kind=kind)
                self.assertEqual(modal.session.selection_signature,
                                 frozenset(v.index for v in seq[-1].verts))

    def test_auto_merge_keeps_picked_stationary_vertex_after_indices_change(self):
        bpy.context.scene.tool_settings.use_mesh_automerge = True
        self.begin()
        delta = self.bm.verts[self.b].co - self.bm.verts[self.a].co
        target = self.bm.verts[self.b]
        modal.set_value(dict(values=list(delta)))
        result = self.select_next(self.b)
        self.assertTrue(result['active'])
        self.assertEqual(len(self.bm.verts), 7)
        self.assertTrue(target.is_valid)
        self.assertEqual(modal.session.selection_signature, frozenset([target.index]))
        modal.set_value(dict(values=[0, 0, .01]))
        modal.cancel({})
        self.assertLess((target.co - self.original[self.b]).length, 1e-7)
        self.undo.assert_called_once()

    def test_reset_restores_only_new_baseline(self):
        self.begin()
        modal.set_value(dict(values=[0, 0, .01]))
        self.select_next(self.b)
        modal.set_value(dict(values=[.03, 0, 0]))
        modal.set_value(dict(values=[0, 0, 0]))
        self.assert_position(self.b, self.original[self.b])
        self.assert_position(self.a, self.original[self.a] + Vector((0, 0, .01)))

    def test_finishing_unchanged_next_step_does_not_add_empty_undo(self):
        self.begin()
        modal.set_value(dict(values=[0, 0, .01]))
        self.select_next(self.b)
        modal.confirm({})
        self.undo.assert_called_once()

    def test_owner_and_object_mode_are_rejected_without_modifying_session(self):
        first = self.begin()
        with self.assertRaises(CommandError):
            modal.select_next(dict(_client_id='another'))
        self.assertEqual(modal.session.session_id, first['session_id'])
        modal.cancel({})
        bpy.ops.object.mode_set(mode='OBJECT')
        first = self.begin()
        with self.assertRaises(CommandError): modal.select_next(dict(_client_id='tablet'))
        self.assertEqual(modal.session.session_id, first['session_id'])


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TransformStepsTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful(): raise SystemExit(1)
