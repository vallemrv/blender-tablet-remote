"""blender --background --factory-startup --python-exit-code 1 --python this_file."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import bmesh
import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import tools, sessions
from blender_tablet_remote.errors import BadPayload, CommandError


class ProfileToolsTests(unittest.TestCase):
    def setUp(self):
        sessions.cancel_all()
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        data = bpy.data.meshes.new('Profile')
        data.from_pydata([(1,0,0),(1,0,2)],[(0,1)],[])
        self.obj = bpy.data.objects.new('Profile',data)
        bpy.context.collection.objects.link(self.obj)
        self.obj.select_set(True)
        bpy.context.view_layer.objects.active = self.obj
        bpy.context.scene.cursor.location = (0,0,0)
        bpy.context.scene.unit_settings.scale_length = 1
        bpy.context.scene.tool_settings.mesh_select_mode = (False,True,False)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')

    def tearDown(self):
        sessions.cancel_all()

    def begin(self, **params):
        return tools.begin({'tool':'REVOLVE', 'parameters':dict(steps=8,**params)})

    def test_full_revolution_closes_seam_and_rebuilds_segments(self):
        state = self.begin()
        self.assertEqual(state['input'],'PARAMETERS')
        bm = bmesh.from_edit_mesh(self.obj.data)
        self.assertEqual((len(bm.verts),len(bm.faces)),(16,8))
        self.assertEqual(sum(e.is_boundary for e in bm.edges),16)
        tools.parameter({'parameters':{'steps':16}})
        bm = bmesh.from_edit_mesh(self.obj.data)
        self.assertEqual((len(bm.verts),len(bm.faces)),(32,16))
        tools.cancel({})
        bm = bmesh.from_edit_mesh(self.obj.data)
        self.assertEqual((len(bm.verts),len(bm.edges),len(bm.faces)),(2,1,0))

    def test_partial_revolution_uses_world_axis_with_nonuniform_scale(self):
        self.obj.scale = (2,3,4)
        bpy.context.view_layer.update()
        self.begin(angle=90)
        world = [self.obj.matrix_world @ v.co for v in bmesh.from_edit_mesh(self.obj.data).verts]
        self.assertTrue(all(abs(Vector((co.x,co.y)).length-2) < 1e-5 for co in world))
        self.assertAlmostEqual(max(co.z for co in world),8,places=5)
        self.assertTrue(any(abs(co.x) < 1e-5 and abs(abs(co.y)-2) < 1e-5 for co in world))

    def test_zero_angle_and_invalid_parameter_preserve_session(self):
        self.begin(angle=0)
        self.assertEqual(len(bmesh.from_edit_mesh(self.obj.data).verts),2)
        with self.assertRaises(BadPayload):
            tools.parameter({'parameters':{'steps':0}})
        self.assertTrue(tools.tool_session.active)
        self.assertEqual(len(bmesh.from_edit_mesh(self.obj.data).verts),2)
        tools.parameter({'parameters':{'angle':180}})
        with patch.object(tools,'undo_push') as undo:
            tools.confirm({})
            undo.assert_called_once_with('Remote revolve')

    def test_cursor_center_and_negative_angle(self):
        bpy.context.scene.cursor.location = (1,1,0)
        state = self.begin(angle=-90)
        self.assertEqual(state['parameters']['center_y'],1)
        world = [v.co for v in bmesh.from_edit_mesh(self.obj.data).verts]
        self.assertTrue(all(abs(Vector((co.x-1,co.y-1)).length-1) < 1e-5 for co in world))

    def contour(self, closed=False):
        bm = bmesh.from_edit_mesh(self.obj.data)
        bm.clear()
        verts = [bm.verts.new(co) for co in [(0,0,0),(0,0,2),(1,0,2),(1,0,0)]]
        for i in range(4 if closed else 3):
            bm.edges.new((verts[i],verts[(i+1)%4])).select_set(True)
        bmesh.update_edit_mesh(self.obj.data)

    def test_sweep_builds_open_door_frame_with_shared_miters_and_caps(self):
        self.contour()
        state = tools.begin({'tool':'SWEEP','parameters':{'width':.1,'depth':.2}})
        self.assertEqual(state['input'],'PARAMETERS')
        bm = bmesh.from_edit_mesh(self.obj.data)
        self.assertEqual((len(bm.verts),len(bm.faces)),(16,14))
        self.assertTrue(all(e.is_manifold for e in bm.edges))
        self.assertAlmostEqual(min(v.co.x for v in bm.verts),-.05,places=6)
        self.assertAlmostEqual(max(v.co.z for v in bm.verts),2.05,places=6)
        self.assertAlmostEqual(max(v.co.y for v in bm.verts)-min(v.co.y for v in bm.verts),.2,places=6)
        tools.parameter({'parameters':{'width':.2}})
        bm = bmesh.from_edit_mesh(self.obj.data)
        self.assertEqual(len(bm.verts),16)
        self.assertAlmostEqual(min(v.co.x for v in bm.verts),-.1,places=6)
        tools.cancel({})
        bm = bmesh.from_edit_mesh(self.obj.data)
        self.assertEqual((len(bm.verts),len(bm.edges),len(bm.faces)),(4,3,0))

    def test_closed_sweep_preserves_hole_and_is_manifold(self):
        self.contour(closed=True)
        tools.begin({'tool':'SWEEP','parameters':{'width':.1,'depth':.2}})
        bm = bmesh.from_edit_mesh(self.obj.data)
        self.assertEqual((len(bm.verts),len(bm.faces)),(16,16))
        self.assertTrue(all(e.is_manifold for e in bm.edges))
        self.assertAlmostEqual(abs(bm.calc_volume()),.12,places=5)
        with patch.object(tools,'undo_push') as undo:
            tools.confirm({})
            undo.assert_called_once_with('Remote sweep')

    def test_sweep_rejects_branch_without_changing_mesh(self):
        self.contour()
        bm = bmesh.from_edit_mesh(self.obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.new((bm.verts[1],bm.verts.new((-1,0,2)))).select_set(True)
        bmesh.update_edit_mesh(self.obj.data)
        with self.assertRaises(CommandError):
            tools.begin({'tool':'SWEEP','parameters':{}})
        self.assertEqual((len(bm.verts),len(bm.edges),len(bm.faces)),(5,4,0))

    def test_revolution_merges_vertices_on_axis(self):
        bm = bmesh.from_edit_mesh(self.obj.data)
        bm.verts.ensure_lookup_table()
        bm.verts[0].co = (0,0,0)
        bm.verts[1].co = (1,0,0)
        bmesh.update_edit_mesh(self.obj.data)
        self.begin()
        bm = bmesh.from_edit_mesh(self.obj.data)
        self.assertEqual(sum(v.co.length < 1e-6 for v in bm.verts),1)
        self.assertEqual(len(bm.verts),9)
        self.assertEqual(len(bm.faces),8)

    def test_sweep_preserves_unselected_geometry_attached_to_path(self):
        self.contour()
        bm = bmesh.from_edit_mesh(self.obj.data)
        bm.verts.ensure_lookup_table()
        endpoint = bm.verts[0]
        extra = bm.verts.new((-1,0,0))
        bm.edges.new((endpoint,extra))
        bmesh.update_edit_mesh(self.obj.data)
        tools.begin({'tool':'SWEEP','parameters':{}})
        bm = bmesh.from_edit_mesh(self.obj.data)
        loose = [e for e in bm.edges if e.is_wire]
        self.assertEqual(len(loose),1)
        self.assertEqual({tuple(v.co) for v in loose[0].verts},{(0,0,0),(-1,0,0)})

    def test_sweep_defaults_convert_scene_units_and_object_scale(self):
        self.contour()
        self.obj.scale = (1000,1000,1000)
        bpy.context.scene.unit_settings.scale_length = .001
        bpy.context.view_layer.update()
        state = tools.begin({'tool':'SWEEP','parameters':{}})
        self.assertAlmostEqual(state['parameters']['width'],50,places=4)
        self.assertAlmostEqual(state['parameters']['depth'],100,places=4)
        bm = bmesh.from_edit_mesh(self.obj.data)
        world = [self.obj.matrix_world @ v.co for v in bm.verts]
        self.assertAlmostEqual((max(v.y for v in world)-min(v.y for v in world))*.001,.1,places=6)


if __name__ == '__main__':
    unittest.main(argv=[__file__], verbosity=2)
