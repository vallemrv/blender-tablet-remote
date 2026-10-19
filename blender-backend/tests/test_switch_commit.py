"""Cambiar herramienta confirma el resultado; Cancelar sigue restaurando el baseline."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import bpy
import bmesh
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import modal,tools,sessions
from blender_tablet_remote.errors import CommandError

class SwitchTests(unittest.TestCase):
    def setUp(self):
        sessions.cancel_all()
        if bpy.context.object and bpy.context.object.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add(location=(0,0,0))
        self.obj=bpy.context.object
        self.patches=[patch.object(modal,'undo_push'),patch.object(tools,'undo_push'),patch.object(modal.state,'snapshot',return_value={})]
        self.move_undo=self.patches[0].start();self.tool_undo=self.patches[1].start();self.patches[2].start()
    def tearDown(self):
        sessions.cancel_all()
        for p in reversed(self.patches):p.stop()
    def test_move_then_rotate_keeps_translation_and_cancel_only_reverts_rotation(self):
        modal.begin(dict(mode='MOVE',_client_id='tablet'))
        modal.set_value(dict(values=[2,0,0]))
        modal.begin(dict(mode='ROTATE',axes=['Z'],_client_id='tablet'))
        self.assertAlmostEqual(self.obj.location.x,2)
        self.move_undo.assert_called_once()
        modal.set_value(dict(angle=45));modal.cancel({'_client_id':'tablet'})
        self.assertAlmostEqual(self.obj.location.x,2)
        self.assertAlmostEqual(self.obj.rotation_euler.z,0)
    def test_unchanged_transform_and_armed_tool_create_no_undo(self):
        modal.begin(dict(mode='MOVE',_client_id='tablet'))
        sessions.finish({'_client_id':'tablet'});self.move_undo.assert_not_called()
        bpy.ops.object.mode_set(mode='EDIT')
        tools.begin(dict(tool='LOOP_CUT',_client_id='tablet'))
        sessions.finish({'_client_id':'tablet'});self.tool_undo.assert_not_called()
        self.assertFalse(tools.tool_session.armed_tool)
    def test_extrude_then_move_keeps_topology_and_can_cancel_new_move(self):
        bpy.ops.object.mode_set(mode='EDIT')
        tools.begin(dict(tool='EXTRUDE',parameters={'offset':1.,'variant':'REGION'},_client_id='tablet'))
        bm=bmesh.from_edit_mesh(self.obj.data);count=len(bm.verts);coords=[v.co.copy() for v in bm.verts]
        modal.begin(dict(mode='MOVE',_client_id='tablet'))
        self.tool_undo.assert_called_once()
        modal.set_value(dict(values=[2,0,0]));modal.cancel({'_client_id':'tablet'})
        bm=bmesh.from_edit_mesh(self.obj.data)
        self.assertEqual(len(bm.verts),count)
        for got,want in zip(bm.verts,coords):self.assertLess((got.co-want).length,1e-6)
    @unittest.skipIf(bpy.app.background, 'Undo requiere ventana')
    def test_switch_creates_separate_native_undo_steps(self):
        from blender_tablet_remote.bpy_utils import undo_push,view3d_override
        undo_push('Baseline switch')
        with patch.object(modal,'undo_push',undo_push):
            modal.begin(dict(mode='MOVE',_client_id='tablet'))
            modal.set_value(dict(values=[2,0,0]))
            modal.begin(dict(mode='ROTATE',axes=['Z'],_client_id='tablet'))
            modal.set_value(dict(angle=45));modal.confirm({'_client_id':'tablet'})
        with view3d_override():bpy.ops.ed.undo()
        obj=bpy.context.object
        self.assertAlmostEqual(obj.location.x,2);self.assertAlmostEqual(obj.rotation_euler.z,0)
        with view3d_override():bpy.ops.ed.undo()
        self.assertAlmostEqual(bpy.context.object.location.x,0)

    def test_other_client_cannot_finish_preview(self):
        modal.begin(dict(mode='MOVE',_client_id='tablet'))
        modal.set_value(dict(values=[2,0,0]))
        with self.assertRaises(CommandError):sessions.finish({'_client_id':'other'})
        self.assertTrue(modal.session.active);self.move_undo.assert_not_called()
        modal.cancel({'_client_id':'tablet'});self.assertAlmostEqual(self.obj.location.x,0)
    def test_two_tool_starts_in_flight_preserve_first_without_android_status(self):
        bpy.ops.object.mode_set(mode='EDIT')
        tools.begin(dict(tool='SUBDIVIDE',parameters={'cuts':1},_client_id='tablet'))
        count=len(bmesh.from_edit_mesh(self.obj.data).verts)
        tools.begin(dict(tool='SUBDIVIDE',parameters={'cuts':1},_client_id='tablet'))
        self.tool_undo.assert_called_once()
        tools.cancel({'_client_id':'tablet'})
        self.assertEqual(len(bmesh.from_edit_mesh(self.obj.data).verts),count)

def run():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SwitchTests))
    if not result.wasSuccessful():raise SystemExit(1)
    if not bpy.app.background:bpy.ops.wm.quit_blender()

if __name__=='__main__':
    if bpy.app.background:run()
    else:bpy.app.timers.register(run,first_interval=1)
