"""GUI: blender --factory-startup --python this_file (uses native cursor operators)."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import bpy
import bmesh
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import snap, sessions, curve_edit
from blender_tablet_remote.errors import CommandError

class CursorSelectionTests(unittest.TestCase):
    def setUp(self):
        sessions.cancel_all()
        if bpy.context.object and bpy.context.object.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
        for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
        bpy.ops.mesh.primitive_cube_add(location=(2,3,-1))
        self.obj=bpy.context.object
        self.obj.rotation_euler=(.2,.3,.4);self.obj.scale=(2,.5,3)
        bpy.context.view_layer.update()
        self.matrix=self.obj.matrix_world.copy()
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.context.scene.tool_settings.mesh_select_mode=(True,False,False)
        self.bm=bmesh.from_edit_mesh(self.obj.data);self.bm.verts.ensure_lookup_table()
        for seq in (self.bm.verts,self.bm.edges,self.bm.faces):
            for item in seq:item.select=False
        self.before=[v.co.copy() for v in self.bm.verts]
        bpy.context.scene.cursor.location=(4,-2,1)
        self.mock=patch.object(snap,'undo_push');self.undo=self.mock.start()
    def tearDown(self):self.mock.stop()
    def choose(self,*indices):
        for i in indices:self.bm.verts[i].select=True
        bmesh.update_edit_mesh(self.obj.data)
    def test_one_vertex_reaches_world_cursor_without_moving_object_or_other_vertices(self):
        self.choose(0)
        snap.selected_to_cursor({})
        self.assertLess((self.matrix@self.bm.verts[0].co-bpy.context.scene.cursor.location).length,1e-5)
        self.assertEqual(self.obj.matrix_world,self.matrix)
        self.assertEqual(self.obj.mode,'EDIT')
        for i in range(1,len(self.before)):self.assertEqual(self.bm.verts[i].co,self.before[i])
        self.undo.assert_called_once()
    def test_multiple_vertices_reach_cursor_or_keep_their_offset(self):
        self.choose(0,1)
        delta=self.before[1]-self.before[0]
        snap.selected_to_cursor({'keep_offset':True})
        self.assertLess((self.bm.verts[1].co-self.bm.verts[0].co-delta).length,1e-5)
        centre=self.matrix@((self.bm.verts[0].co+self.bm.verts[1].co)*.5)
        self.assertLess((centre-bpy.context.scene.cursor.location).length,1e-5)
        snap.selected_to_cursor({})
        for i in (0,1):self.assertLess((self.matrix@self.bm.verts[i].co-bpy.context.scene.cursor.location).length,1e-5)
    def test_empty_selection_is_rejected_without_undo(self):
        with self.assertRaises(CommandError):snap.selected_to_cursor({})
        self.undo.assert_not_called()
        self.assertEqual([v.co for v in self.bm.verts],self.before)
    def test_cursor_can_be_placed_on_selected_vertex(self):
        self.choose(0)
        snap.cursor_to_selected({})
        self.assertLess((bpy.context.scene.cursor.location-self.matrix@self.before[0]).length,1e-5)
    def test_curve_control_point_and_inverse_use_native_data(self):
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.curve.primitive_bezier_curve_add(location=(1,2,3))
        obj=bpy.context.object
        bpy.ops.object.mode_set(mode='EDIT')
        curve_edit.set_selection(obj,{(0,0,'POINT')})
        target=bpy.context.scene.cursor.location.copy()
        other=obj.data.splines[0].bezier_points[1].co.copy()
        matrix=obj.matrix_world.copy()
        snap.selected_to_cursor({})
        self.assertLess((matrix@obj.data.splines[0].bezier_points[0].co-target).length,1e-5)
        self.assertEqual(obj.data.splines[0].bezier_points[1].co,other)
        bpy.context.scene.cursor.location=(0,0,0)
        snap.cursor_to_selected({})
        self.assertLess((bpy.context.scene.cursor.location-target).length,1e-5)
        self.assertEqual(obj.matrix_world,matrix)

def run():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CursorSelectionTests))
    if not result.wasSuccessful():
        import os
        sys.stdout.flush();sys.stderr.flush();os._exit(1)
    bpy.ops.wm.quit_blender()
bpy.app.timers.register(run,first_interval=1)
