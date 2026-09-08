"""blender --background --factory-startup --python-exit-code 1 --python this_file."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy
import bmesh
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import knife, tools, snap, sessions
from blender_tablet_remote.camera import camera
from blender_tablet_remote.errors import CommandError


class KnifeGeometryTests(unittest.TestCase):
    def setUp(self):
        self.bm = bmesh.new()

    def tearDown(self):
        self.bm.free()

    def face(self, coords):
        face = self.bm.faces.new([self.bm.verts.new(co) for co in coords])
        self.bm.normal_update()
        return face

    def cut(self, points):
        return knife.cut_polyline(self.bm, points, False)

    def test_interior_chain_creates_only_two_ngons(self):
        self.face([(-1,-1,0),(1,-1,0),(1,1,0),(-1,1,0)])
        self.cut([(-1,0,0),(-.3,.4,0),(.2,-.3,0),(1,0,0)])
        self.assertEqual(len(self.bm.faces), 2)
        self.assertTrue(all(len(f.verts) == 6 for f in self.bm.faces))
        self.assertEqual(len(self.bm.verts), 8)

    def test_concave_cut_accepts_next_stroke_at_created_vertex(self):
        self.face([(-1,-1,0),(1,-1,0),(1,1,0),(-1,1,0)])
        self.cut([(-1,0,0),(0,.5,0),(1,0,0)])
        self.cut([(0,.5,0),(0,1,0)])
        self.assertEqual(len(self.bm.faces), 3)
        self.assertEqual(sum((v.co-Vector((0,.5,0))).length < 1e-6 for v in self.bm.verts), 1)
        self.assertAlmostEqual(sum(f.calc_area() for f in self.bm.faces), 4, places=6)

    def test_cube_cut_does_not_split_adjacent_or_back_faces(self):
        bmesh.ops.create_cube(self.bm, size=2)
        self.cut([(-1,0,1),(0,.3,1),(1,0,1)])
        self.assertEqual(len(self.bm.faces), 7)
        self.assertEqual(sum(f.normal.z > .9 for f in self.bm.faces), 2)
        self.assertEqual(sum(f.normal.z < -.9 for f in self.bm.faces), 1)
        self.assertTrue(all(abs(v.co.z-1) < 1e-6 for v in self.bm.verts if abs(v.co.x) < .9))

    def test_continuing_after_a_boundary_point_reuses_it(self):
        self.face([(-1,-1,0),(1,-1,0),(1,1,0),(-1,1,0)])
        self.cut([(-1,0,0),(1,0,0),(0,1,0)])
        self.assertEqual(len(self.bm.faces), 3)
        self.assertEqual(len(self.bm.verts), 7)
        self.assertAlmostEqual(sum(f.calc_area() for f in self.bm.faces), 4, places=6)

    def test_chord_through_cube_is_rejected_before_mutation(self):
        bmesh.ops.create_cube(self.bm, size=2)
        with self.assertRaises(CommandError):
            self.cut([(-1,0,1),(1,0,-1)])
        self.assertEqual((len(self.bm.verts),len(self.bm.edges),len(self.bm.faces)),(8,12,6))

    def test_starting_or_ending_inside_never_pokes_face(self):
        self.face([(-1,-1,0),(1,-1,0),(1,1,0),(-1,1,0)])
        self.cut([(0,0,0),(1,0,0)])
        self.cut([(-1,0,0),(0,0,0)])
        self.assertEqual((len(self.bm.verts),len(self.bm.faces)),(4,1))

    def test_segment_crosses_multiple_coplanar_faces(self):
        verts = [self.bm.verts.new((x,y,0)) for y in (-1,1) for x in (-1,0,1)]
        self.bm.faces.new([verts[i] for i in (0,1,4,3)])
        self.bm.faces.new([verts[i] for i in (1,2,5,4)])
        self.cut([(-1,0,0),(1,0,0)])
        self.assertEqual(len(self.bm.faces),4)
        self.assertEqual(len(self.bm.verts),9)


class EditToolsTests(unittest.TestCase):
    def setUp(self):
        sessions.cancel_all()
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add()
        self.obj = bpy.context.object
        bpy.context.scene.tool_settings.mesh_select_mode = (False, False, True)
        bpy.context.scene.unit_settings.scale_length = 1
        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(self.obj.data)
        for face in bm.faces:
            face.select_set(False)
        top = max(bm.faces, key=lambda f:f.calc_center_median().z)
        top.select_set(True)
        bmesh.update_edit_mesh(self.obj.data)
        camera.reset()
        camera._synced = True
        camera.location = Vector((0,0,0))
        camera.rotation = Quaternion((1,0,0,0))
        camera.distance = 10
        camera.perspective = 'PERSP'
        self.rv3d = SimpleNamespace(window_matrix=Matrix(((1,0,0,0),(0,2,0,0),(0,0,-1,-.02),(0,0,-1,0))))
        found = (None,None,SimpleNamespace(width=1000,height=500),self.rv3d)
        self.patches = [patch.object(tools,'find_view3d',return_value=found),
                        patch.object(snap,'find_view3d',return_value=found)]
        for p in self.patches:p.start()

    def tearDown(self):
        sessions.cancel_all()
        for p in self.patches:p.stop()

    def begin(self, tool, **params):
        return tools.begin(dict(tool=tool,parameters=params))

    def test_increment_accumulates_small_samples_and_reports_visual_value(self):
        for tool, primary in [('EXTRUDE','offset'),('INSET','thickness'),('BEVEL','offset')]:
            with self.subTest(tool=tool):
                self.begin(tool, **{primary:0.0,'snap_type':'INCREMENT','snap_step':.1})
                for _ in range(6):
                    state = tools.nudge({'delta':.01})
                self.assertAlmostEqual(state['parameters'][primary],.1)
                self.assertAlmostEqual(tools.tool_session.params[primary],.06)
                for _ in range(6):
                    state = tools.nudge({'delta':-.01})
                self.assertAlmostEqual(state['parameters'][primary],0.0)
                tools.cancel({})

    def test_extrude_live_candidate_moves_preview_without_lock(self):
        self.begin('EXTRUDE', offset=0, snap_type='VERTEX')
        candidate = dict(hit=True,position=[0,0,2],id='target',snap_type='VERTEX')
        with patch.object(snap,'query_candidate',return_value=candidate):
            state = tools.snap_candidate(dict(u=.5,v=.5,lock=False))
        self.assertEqual(state['snap_candidate']['id'],'target')
        self.assertAlmostEqual(state['parameters']['offset'],1)
        bm = bmesh.from_edit_mesh(self.obj.data)
        self.assertAlmostEqual(max(v.co.z for v in bm.verts),2)
        state = tools.parameter({'parameters':{'offset':1.002}})
        self.assertIsNone(state['snap_candidate'])
        self.assertAlmostEqual(state['parameters']['offset'],1.002)
        self.assertAlmostEqual(max(v.co.z for v in bm.verts),2.002,places=6)
        tools.cancel({})
        self.assertEqual(len(bmesh.from_edit_mesh(self.obj.data).verts),8)

    def test_extrude_candidate_respects_constraint_and_object_scale(self):
        self.obj.scale = (2,3,4)
        bpy.context.view_layer.update()
        self.begin('EXTRUDE', offset=0, constraint='Z', orientation='GLOBAL')
        candidate = dict(hit=True,position=[5,4,8],id='target',snap_type='VERTEX')
        with patch.object(snap,'query_candidate',return_value=candidate):
            state = tools.snap_candidate(dict(u=.5,v=.5,lock=False))
        self.assertAlmostEqual(state['parameters']['offset'],1)
        bm = bmesh.from_edit_mesh(self.obj.data)
        self.assertAlmostEqual(max(v.co.z for v in bm.verts),2)
        self.assertAlmostEqual(max(v.co.x for v in bm.verts),1)

    def test_knife_snap_mode_and_end_confirm_last_candidate(self):
        self.begin('KNIFE', snap=True)
        tools.parameter({'parameters':{'snap_mode':'VERTEX'}})
        self.assertEqual(tools.tool_session.params['snap_mode'],'VERTEX')
        candidate = dict(hit=True,local_position=[-1,0,1],position=[-1,0,1],id='first',snap_type='EDGE')
        with patch.object(tools,'_knife_candidate',return_value=candidate) as query:
            tools.knife_drag(dict(phase='BEGIN',u=.4,v=.5))
            tools.knife_drag(dict(phase='END',u=.9,v=.9))
            self.assertEqual(query.call_count,1)
        self.assertEqual(tools.tool_session.points,[[-1,0,1]])

    def test_knife_snap_reuses_new_vertex_from_previous_stroke(self):
        self.begin('KNIFE', snap=True)
        tools.tool_session.points = [[-1,0,1],[0,.5,1],[1,0,1]]
        tools.knife_new_stroke({})
        u,v = camera.project(Vector((0,.5,1)),self.rv3d)
        result = tools._knife_candidate(self.obj,u,v,True,'VERTEX')
        self.assertTrue(result['hit'])
        self.assertEqual(result['snap_type'],'VERTEX')
        self.assertLess((Vector(result['local_position'])-Vector((0,.5,1))).length,1e-6)
        tools.tool_session.points = [[0,.5,1],[0,1,1]]
        tools.knife_new_stroke({})
        self.assertEqual(len(bmesh.from_edit_mesh(self.obj.data).faces),8)
        tools.cancel({})
        self.assertEqual(len(bmesh.from_edit_mesh(self.obj.data).faces),6)

    def test_invalid_endpoint_preserves_previous_strokes_and_active_points(self):
        self.begin('KNIFE', snap=True)
        tools.tool_session.points = [[-1,0,1],[0,.5,1],[1,0,1]]
        tools.knife_new_stroke({})
        tools.tool_session.points = [[0,.5,1]]
        candidate = dict(hit=True,local_position=[0,0,-1],position=[0,0,-1],id='back',snap_type='FACE')
        with patch.object(tools,'_knife_candidate',return_value=candidate):
            tools.knife_drag(dict(phase='BEGIN',u=.5,v=.5))
            with self.assertRaises(CommandError):
                tools.knife_drag(dict(phase='END',u=.5,v=.5))
        self.assertEqual(tools.tool_session.points,[[0,.5,1]])
        self.assertEqual(len(tools.tool_session.knife_strokes),1)
        self.assertEqual(len(bmesh.from_edit_mesh(self.obj.data).faces),7)

    def test_knife_surface_is_occluded_by_another_object(self):
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.mesh.primitive_plane_add(size=4, location=(0,0,2))
        wall = bpy.context.object
        wall.select_set(False)
        self.obj.select_set(True)
        bpy.context.view_layer.objects.active = self.obj
        bpy.ops.object.mode_set(mode='EDIT')
        result = tools._knife_candidate(self.obj,.5,.5,True,'AUTO')
        self.assertFalse(result['hit'])

    def test_knife_rejects_hidden_back_vertex_and_sees_silhouette(self):
        u,v = camera.project(Vector((1,1,-1)),self.rv3d)
        result = tools._knife_candidate(self.obj,u,v,True,'VERTEX')
        if result['snap_type']=='VERTEX':
            self.assertGreater(result['local_position'][2],0)
        u,v = camera.project(Vector((1,1,1)),self.rv3d)
        result = tools._knife_candidate(self.obj,u+.005,v,True,'VERTEX')
        self.assertEqual(result['snap_type'],'VERTEX')
        self.assertEqual(result['local_position'],[1,1,1])


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    if not result.wasSuccessful():raise SystemExit(1)
