"""blender --background --factory-startup --python-exit-code 1 --python this_file."""
import unittest
import sys
from pathlib import Path
from unittest.mock import patch

import bmesh
import bpy
from mathutils import Quaternion, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_edit_tools import EditToolsTests
from blender_tablet_remote.commands import extrude_cursor, tools, mesh
from blender_tablet_remote.camera import camera
from blender_tablet_remote.errors import CommandError


class ExtrudeCursorTests(unittest.TestCase):
    def setUp(self):
        bpy.context.scene.cursor.location = (0,0,0)
        EditToolsTests.setUp(self)
        self.view_patch = patch.object(extrude_cursor, 'find_view3d', return_value=tools.find_view3d())
        self.view_patch.start()

    def tearDown(self):
        self.view_patch.stop()
        EditToolsTests.tearDown(self)

    def arm(self, rotate=False):
        return tools.begin({'tool': 'EXTRUDE', '_client_id': 'tablet',
                            'parameters': {'variant': 'CURSOR', 'rotate_source': rotate}})

    def tap(self, u, v):
        return tools.extrude_cursor({'u': u, 'v': v, '_client_id': 'tablet'})

    def selection_center(self):
        selected = [self.obj.matrix_world @ v.co for v in bmesh.from_edit_mesh(self.obj.data).verts if v.select]
        return sum(selected, Vector()) / len(selected)

    def empty_or_edge(self, edge):
        bm = bmesh.from_edit_mesh(self.obj.data)
        bm.clear()
        bpy.context.scene.tool_settings.mesh_select_mode = (not edge, edge, False)
        if edge:
            bm.edges.new([bm.verts.new((-1,0,0)), bm.verts.new((1,0,0))]).select_set(True)
        bmesh.update_edit_mesh(self.obj.data)

    def test_repeated_edge_taps_create_faces_and_one_undo_each(self):
        self.empty_or_edge(True)
        state = self.arm()
        self.assertFalse(state['active'])
        self.assertEqual(state['input'], 'REPEAT_TAP')
        with patch.object(tools, 'undo_push') as undo:
            for count, point in enumerate(((.6,.3),(.7,.2)),1):
                state = self.tap(*point)
                self.assertTrue(state['armed'])
                bm = bmesh.from_edit_mesh(self.obj.data)
                self.assertEqual(len(bm.verts),2+count*2)
                self.assertEqual(len(bm.faces),count)
                for actual, expected in zip(camera.project(self.selection_center(),self.rv3d),point):
                    self.assertAlmostEqual(actual,expected,places=6)
            self.assertEqual(undo.call_count,2)
        before = [tuple(v.co) for v in bm.verts]
        tools.cancel({'_client_id': 'tablet'})
        self.assertEqual(before,[tuple(v.co) for v in bm.verts])
        with self.assertRaises(CommandError): self.tap(.8,.2)

    def test_no_selection_starts_at_cursor_depth_then_extrudes_vertices(self):
        self.empty_or_edge(False)
        bpy.context.scene.cursor.location.z = 3
        self.arm()
        with patch.object(tools, 'undo_push'):
            self.tap(.6,.4)
            self.tap(.7,.3)
        bm = bmesh.from_edit_mesh(self.obj.data)
        self.assertEqual((len(bm.verts),len(bm.edges)),(2,1))
        self.assertTrue(all(abs(v.co.z-3) < 1e-6 for v in bm.verts))

    def test_faces_follow_remote_view_with_scaled_rotated_object(self):
        self.obj.scale = (2,3,4)
        self.obj.rotation_euler.z = .5
        bpy.context.view_layer.update()
        camera.rotation = Quaternion((1,0,0), .3)
        camera.perspective = 'ORTHO'
        before = self.selection_center()
        normal = camera.rotation @ Vector((0,0,1))
        self.arm()
        with patch.object(tools, 'undo_push'):
            self.tap(.65,.3)
        after = self.selection_center()
        self.assertAlmostEqual((after-before).dot(normal),0,places=5)
        for actual, expected in zip(camera.project(after,self.rv3d),(.65,.3)):
            self.assertAlmostEqual(actual,expected,places=6)

    def test_rotate_source_halves_corner_rotation(self):
        self.empty_or_edge(True)
        self.arm(True)
        with patch.object(tools, 'undo_push'):
            self.tap(*camera.project(Vector((2,2,0)),self.rv3d))
        bm = bmesh.from_edit_mesh(self.obj.data)
        source = [v for v in bm.verts if not v.select]
        self.assertTrue(all(abs(v.co.y) > .1 for v in source))
        self.assertAlmostEqual((source[0].co-source[1].co).length,2,places=6)
        self.assertAlmostEqual(self.selection_center().x,2,places=5)
        self.assertAlmostEqual(self.selection_center().y,2,places=5)

    def test_wrong_owner_and_failed_extrusion_leave_mesh_unchanged(self):
        self.empty_or_edge(True)
        self.arm(True)
        before = [tuple(v.co) for v in bmesh.from_edit_mesh(self.obj.data).verts]
        with patch.object(tools,'undo_push') as undo:
            with self.assertRaises(CommandError):
                tools.extrude_cursor({'u':.6,'v':.3,'_client_id':'other'})
            with patch.object(mesh,'extrude',side_effect=RuntimeError('failure')):
                with self.assertRaises(RuntimeError): self.tap(.6,.3)
            undo.assert_not_called()
        self.assertEqual(before,[tuple(v.co) for v in bmesh.from_edit_mesh(self.obj.data).verts])
        self.assertFalse(any(m.name.startswith('.remote_cursor_backup') for m in bpy.data.meshes))

    def test_tap_on_selection_center_does_not_duplicate(self):
        self.arm()
        with patch.object(tools,'undo_push') as undo:
            self.assertFalse(self.tap(.5,.5)['result']['changed'])
            undo.assert_not_called()
        self.assertEqual(len(bmesh.from_edit_mesh(self.obj.data).verts),8)

    def test_vertex_selection_of_an_edge_creates_faces_when_tapping(self):
        self.empty_or_edge(True)
        bpy.context.scene.tool_settings.mesh_select_mode = (True,False,False)
        self.arm()
        with patch.object(tools,'undo_push'):
            self.tap(.6,.3)
            self.tap(.7,.2)
        bm = bmesh.from_edit_mesh(self.obj.data)
        self.assertEqual((len(bm.verts),len(bm.faces)),(6,2))
        self.assertEqual(tuple(bpy.context.scene.tool_settings.mesh_select_mode),(True,False,False))


if __name__ == '__main__':
    unittest.main(argv=[__file__], defaultTest='ExtrudeCursorTests', verbosity=2)
