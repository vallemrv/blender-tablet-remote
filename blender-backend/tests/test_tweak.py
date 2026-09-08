"""Tweak: blender --background --factory-startup --python-exit-code 1 --python este_archivo."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy
import bmesh
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import selection, modal, sessions
from blender_tablet_remote.camera import camera
from blender_tablet_remote.errors import CommandError


class TweakTests(unittest.TestCase):
    def setUp(self):
        sessions.cancel_all()
        selection._reset_tweak()
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add()
        self.obj = bpy.context.object
        bpy.context.scene.tool_settings.mesh_select_mode = (True, False, False)
        bpy.context.scene.tool_settings.use_proportional_edit = False
        bpy.ops.object.mode_set(mode='EDIT')
        self.bm = bmesh.from_edit_mesh(self.obj.data)
        for seq in (self.bm.verts, self.bm.edges, self.bm.faces):
            seq.ensure_lookup_table()
        self.coords = [v.co.copy() for v in self.bm.verts]
        camera.reset()
        camera._synced = True
        camera.location = Vector((0, 0, 0))
        camera.rotation = Quaternion((1, 0, 0, 0))
        camera.distance = 10
        camera.perspective = 'PERSP'
        self.rv3d = SimpleNamespace(window_matrix=Matrix(((1,0,0,0),(0,2,0,0),(0,0,-1,-.02),(0,0,-1,0))))
        region = SimpleNamespace(width=1000, height=500)
        self.patches = [patch.object(selection, 'find_view3d', return_value=(None,None,region,self.rv3d)),
                        patch.object(modal, 'require_rv3d', return_value=self.rv3d),
                        patch.object(selection.state, 'snapshot', return_value={})]
        for p in self.patches: p.start()
        self.select()

    def tearDown(self):
        sessions.cancel_all()
        selection._reset_tweak()
        for p in self.patches: p.stop()

    def select(self, indices=()):
        selection.sel_elements(dict(mode='SET', verts=list(indices)))

    def gesture(self, phase, **kwargs):
        return selection.tweak(dict(phase=phase, _client_id='tablet', **kwargs))

    def begin(self, position=(.98,.98,1), **kwargs):
        u,v = camera.project(Vector(position), self.rv3d)
        return self.gesture('BEGIN',u=u,v=v,**kwargs)

    def assertUnmoved(self):
        for v,co in zip(self.bm.verts,self.coords):
            self.assertLess((v.co-co).length,1e-6)

    def test_terminal_response_identifies_only_the_finished_tweak(self):
        with patch.object(modal, 'undo_push'):
            for phase in ('END', 'CANCEL'):
                self.begin()
                identity = modal.session.session_id
                response = self.gesture(phase)
                self.assertEqual(response['tweak_finished'], identity)
                self.assertFalse(response['active'])
                self.assertFalse(modal.session.active)

    def test_tap_selects_without_moving_or_undo(self):
        with patch.object(modal,'undo_push') as undo:
            result=self.begin()
            self.assertTrue(result['hit'])
            self.assertEqual(sum(v.select for v in self.bm.verts),1)
            self.assertFalse(self.gesture('END')['moved'])
            undo.assert_not_called()
        self.assertUnmoved()
        self.assertFalse(modal.session.active)

    def test_drag_moves_only_picked_element_and_commits_once(self):
        result=self.begin()
        index=result['index']
        with patch.object(modal,'undo_push') as undo:
            self.gesture('UPDATE',dx=.03,dy=.02)
            self.gesture('UPDATE',dx=.02,dy=0)
            self.assertTrue(self.gesture('END')['moved'])
            self.gesture('END')
            undo.assert_called_once()
        for v,co in zip(self.bm.verts,self.coords):
            if v.index==index: self.assertGreater((v.co-co).length,.01)
            else: self.assertLess((v.co-co).length,1e-6)
        self.assertFalse(modal.session.active)

    def test_selected_group_moves_together(self):
        self.select(range(8))
        self.begin()
        self.assertEqual(len(modal.session.edit_coords),8)
        self.gesture('UPDATE',dx=.03,dy=0)
        offset=self.bm.verts[0].co-self.coords[0]
        self.assertGreater(offset.length,.01)
        for v,co in zip(self.bm.verts,self.coords):
            self.assertLess((v.co-co-offset).length,1e-6)

    def test_next_gesture_can_change_selection(self):
        first=self.begin()['index']
        self.gesture('END')
        second=self.begin(position=(-.98,.98,1))['index']
        self.assertNotEqual(first,second)
        self.assertFalse(self.bm.verts[first].select)
        self.assertEqual(sum(v.select for v in self.bm.verts),1)

    def test_edge_and_face_select_and_move(self):
        for flags,position,count in (((False,True,False),(0,.98,1),2),
                                     ((False,False,True),(0,0,1),4)):
            bpy.context.scene.tool_settings.mesh_select_mode=flags
            self.select()
            result=self.begin(position=position)
            self.assertTrue(result['hit'])
            self.assertEqual(len(modal.session.edit_coords),count)
            self.gesture('UPDATE',dx=.03,dy=0)
            self.assertEqual(sum((v.co-co).length>1e-6 for v,co in zip(self.bm.verts,self.coords)),count)
            self.gesture('CANCEL')
            self.assertUnmoved()

    def test_face_uses_free_even_if_slide_was_remembered(self):
        bpy.context.scene.tool_settings.mesh_select_mode=(False,False,True)
        self.begin(position=(0,0,1),motion='SLIDE')
        self.assertEqual(modal.session.motion,'FREE')

    def test_cancel_and_disconnect_restore_without_undo(self):
        for disconnect in (False,True):
            self.begin()
            self.gesture('UPDATE',dx=.03,dy=0)
            with patch.object(modal,'undo_push') as undo:
                if disconnect: modal.session.owner_disconnected('tablet')
                else: self.gesture('CANCEL')
                self.gesture('CANCEL')
                undo.assert_not_called()
            self.assertUnmoved()
            self.assertFalse(modal.session.active)

    def test_switch_to_transform_ignores_late_tweak_messages(self):
        for mode in ('MOVE','ROTATE','SCALE'):
            self.begin()
            self.gesture('UPDATE',dx=.03,dy=0)
            modal.begin(dict(mode=mode,_client_id='tablet'))
            session_id=modal.session.session_id
            values=modal.session.values.copy()
            self.assertUnmoved()
            for phase in ('UPDATE','END','CANCEL'):
                self.gesture(phase,dx=.4,dy=.2)
                self.assertTrue(modal.session.active)
                self.assertEqual(modal.session.session_id,session_id)
                self.assertEqual(modal.session.values,values)
            sessions.cancel_all()

    def test_miss_preserves_selection_and_orbits(self):
        self.select(range(8))
        self.assertFalse(self.gesture('BEGIN',u=.9,v=.9)['hit'])
        from blender_tablet_remote.commands import view
        with patch.object(view,'orbit_delta') as orbit:
            self.gesture('UPDATE',dx=.03,dy=.02)
            orbit.assert_called_once_with(.03,.02)
        self.gesture('END')
        self.assertEqual(sum(v.select for v in self.bm.verts),8)
        self.assertUnmoved()
        self.assertFalse(modal.session.active)

    def test_foreign_client_cannot_cancel_or_replace_gesture(self):
        self.begin()
        original=modal.session.session_id
        for phase in ('BEGIN','UPDATE','END','CANCEL'):
            with self.assertRaises(CommandError):
                selection.tweak(dict(phase=phase,_client_id='other'))
            self.assertEqual(modal.session.session_id,original)


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(TweakTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful(): raise SystemExit(1)
