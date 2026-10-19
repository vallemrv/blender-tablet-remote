"""Orígenes individuales: Blender nativo, previews reversibles y pivotes de objetos."""
import math
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import bpy
import bmesh
from mathutils import Matrix, Vector
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import modal, sessions
from blender_tablet_remote.bpy_utils import view3d_override


class IndividualCentersTests(unittest.TestCase):
    def setUp(self):
        sessions.cancel_all()
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.context.scene.tool_settings.use_proportional_edit = False
        bpy.context.scene.tool_settings.use_mesh_automerge = False
        bpy.context.scene.tool_settings.transform_pivot_point = 'CURSOR'
        self.patches = [patch.object(modal.state, 'snapshot', return_value={}), patch.object(modal, 'undo_push')]
        for p in self.patches: result = p.start()
        self.undo = result

    def tearDown(self):
        sessions.cancel_all()
        for p in reversed(self.patches): p.stop()

    def mesh(self, selection_mode=(False, False, True)):
        mesh = bpy.data.meshes.new('two-quads')
        mesh.from_pydata([(0,0,0),(2,0,0),(2,2,0),(0,2,0),(4,0,0),(6,0,0),(6,2,0),(4,2,0)], [], [(0,1,2,3),(4,5,6,7)])
        obj = bpy.data.objects.new('two-quads', mesh); bpy.context.collection.objects.link(obj)
        obj.select_set(True); bpy.context.view_layer.objects.active = obj
        bpy.context.scene.tool_settings.mesh_select_mode = selection_mode
        bpy.ops.object.mode_set(mode='EDIT')
        self.obj = obj; self.bm = bmesh.from_edit_mesh(mesh); self.bm.verts.ensure_lookup_table()
        self.original = [v.co.copy() for v in self.bm.verts]

    def coords(self): return [v.co.copy() for v in self.bm.verts]
    def assertCoords(self, expected):
        for got, want in zip(self.coords(), expected): self.assertLess((got-want).length, 1e-5)

    def test_individual_faces_scale_idempotently_and_cancel_restores(self):
        self.mesh()
        modal.begin(dict(mode='SCALE', center_mode='INDIVIDUAL'))
        modal.set_value(dict(values=[.5,.5,.5])); first = self.coords()
        self.assertLess((first[0]-Vector((.5,.5,0))).length, 1e-6)
        self.assertLess((first[4]-Vector((4.5,.5,0))).length, 1e-6)
        modal.set_value(dict(values=[.5,.5,.5])); self.assertCoords(first)
        self.assertEqual(bpy.context.scene.tool_settings.transform_pivot_point, 'CURSOR')
        self.undo.assert_not_called()
        modal.cancel({}); self.assertCoords(self.original)

    def test_rotating_faces_matches_native_with_nonidentity_object_matrix(self):
        self.mesh()
        self.obj.matrix_world = Matrix.Translation((2,3,1)) @ Matrix.Rotation(.4,4,'Y') @ Matrix.Diagonal((2,1,1,1))
        bpy.context.view_layer.update()
        pivot = bpy.context.scene.tool_settings.transform_pivot_point
        bpy.context.scene.tool_settings.transform_pivot_point = 'INDIVIDUAL_ORIGINS'
        with view3d_override():
            bpy.ops.transform.rotate('EXEC_DEFAULT', False, value=math.pi/4, orient_axis='Z', orient_type='GLOBAL')
        expected = self.coords()
        bpy.context.scene.tool_settings.transform_pivot_point = pivot
        for v, co in zip(self.bm.verts, self.original): v.co=co
        bmesh.update_edit_mesh(self.obj.data)
        modal.begin(dict(mode='ROTATE', axes=['Z'], center_mode='INDIVIDUAL'))
        modal.set_value(dict(angle=45)); self.assertCoords(expected)
        modal.confirm({}); self.undo.assert_called_once()
        self.assertEqual(bpy.context.scene.tool_settings.transform_pivot_point, pivot)

    def test_switching_between_individual_and_median_uses_same_baseline(self):
        self.mesh()
        modal.begin(dict(mode='SCALE', center_mode='INDIVIDUAL'))
        modal.set_value(dict(values=[.5,.5,.5])); individuals = self.coords()
        modal.set_reference_candidate(dict(role='CENTER', preset='SELECTION'))
        self.assertGreater((self.coords()[0]-individuals[0]).length, .5)
        modal.set_reference_candidate(dict(role='CENTER', preset='INDIVIDUAL'))
        self.assertCoords(individuals)
        modal.cancel({}); self.assertCoords(self.original)

    def test_vertex_edge_and_shared_face_centers_match_native(self):
        for select_mode in ((True,False,False),(False,True,False),(False,False,True)):
            with self.subTest(select_mode=select_mode):
                self.mesh(select_mode)
                # Caras adyacentes con vértices compartidos, no solo dos islas.
                self.bm.verts[4].co = self.bm.verts[1].co
                self.bm.verts[7].co = self.bm.verts[2].co
                bmesh.ops.remove_doubles(self.bm, verts=list(self.bm.verts), dist=.0001)
                bmesh.update_edit_mesh(self.obj.data)
                self.bm.verts.ensure_lookup_table()
                original=self.coords()
                bpy.context.scene.tool_settings.transform_pivot_point='INDIVIDUAL_ORIGINS'
                with view3d_override():
                    bpy.ops.transform.resize('EXEC_DEFAULT', False, value=(.7,.5,1), orient_type='GLOBAL')
                expected=self.coords()
                for v,co in zip(self.bm.verts,original):v.co=co
                bmesh.update_edit_mesh(self.obj.data)
                modal.begin(dict(mode='SCALE',center_mode='INDIVIDUAL'))
                modal.set_value(dict(values=[.7,.5,1]));self.assertCoords(expected)
                modal.cancel({});self.assertCoords(original)
                bpy.ops.object.mode_set(mode='OBJECT');bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)

    def test_proportional_cancel_restores_neighbors_and_operator_failure_restores_pivot(self):
        self.mesh()
        for v in self.bm.verts:v.select=False
        for e in self.bm.edges:e.select=False
        for f in self.bm.faces:f.select=False
        self.bm.faces.ensure_lookup_table();self.bm.faces[0].select_set(True)
        bmesh.update_edit_mesh(self.obj.data)
        modal.begin(dict(mode='SCALE',center_mode='INDIVIDUAL',proportional=True,proportional_radius=20))
        modal.set_value(dict(values=[.5,.5,.5]))
        first=self.coords();modal.set_value(dict(values=[.5,.5,.5]));self.assertCoords(first)
        modal.cancel({});self.assertCoords(self.original)
        modal.begin(dict(mode='SCALE',center_mode='INDIVIDUAL'))
        with patch.object(modal, 'view3d_override', side_effect=RuntimeError('test')):
            with self.assertRaises(RuntimeError):modal.set_value(dict(values=[.3,.3,.3]))
        self.assertCoords(self.original)
        self.assertEqual(bpy.context.scene.tool_settings.transform_pivot_point,'CURSOR')

    @unittest.skipIf(bpy.app.background, 'Undo requiere ventana')
    def test_native_preview_adds_only_one_undo_and_never_changes_pc_view(self):
        from blender_tablet_remote.bpy_utils import undo_push, find_view3d
        self.mesh()
        rv=find_view3d()[3]
        view=(tuple(rv.view_location),tuple(rv.view_rotation),rv.view_distance,rv.view_perspective)
        undo_push('Baseline individual')
        modal.begin(dict(mode='SCALE',center_mode='INDIVIDUAL'))
        for scale in (.8,.6,.5):modal.set_value(dict(values=[scale]*3))
        with patch.object(modal, 'undo_push', undo_push):modal.confirm({})
        with view3d_override():bpy.ops.ed.undo()
        self.obj=bpy.context.object;self.bm=bmesh.from_edit_mesh(self.obj.data)
        self.assertCoords(self.original)
        self.assertEqual(view,(tuple(rv.view_location),tuple(rv.view_rotation),rv.view_distance,rv.view_perspective))

    def test_curve_handles_and_radii_are_restored_on_cancel(self):
        bpy.ops.curve.primitive_bezier_curve_add()
        obj=bpy.context.object
        bpy.ops.object.mode_set(mode='EDIT')
        points=obj.data.splines[0].bezier_points
        original=[(p.co.copy(),p.handle_left.copy(),p.handle_right.copy(),p.radius) for p in points]
        modal.begin(dict(mode='SCALE',center_mode='INDIVIDUAL'))
        modal.set_value(dict(values=[2,2,2]))
        modal.set_value(dict(values=[.5,.5,.5]))
        modal.cancel({})
        for point,old in zip(points,original):
            for got,want in zip((point.co,point.handle_left,point.handle_right),old[:3]):
                self.assertLess((got-want).length,1e-6)
            self.assertAlmostEqual(point.radius,old[3])

    def test_objects_rotate_and_scale_without_moving_their_origins(self):
        objects=[]
        for x in (2,6):
            bpy.ops.mesh.primitive_cube_add(location=(x,0,0)); objects.append(bpy.context.object)
        for obj in objects: obj.select_set(True)
        modal.begin(dict(mode='ROTATE', axes=['Z'], center_mode='INDIVIDUAL'))
        modal.set_value(dict(angle=90))
        for obj,x in zip(objects,(2,6)):
            self.assertLess((obj.matrix_world.translation-Vector((x,0,0))).length, 1e-6)
            self.assertAlmostEqual(obj.matrix_world.to_euler().z, math.pi/2, places=5)
        modal.cancel({})
        modal.begin(dict(mode='SCALE', center_mode='INDIVIDUAL'))
        modal.set_value(dict(values=[2,2,2]))
        for obj,x in zip(objects,(2,6)):
            self.assertLess((obj.matrix_world.translation-Vector((x,0,0))).length, 1e-6)
        modal.cancel({})


def run():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(IndividualCentersTests))
    if not result.wasSuccessful(): raise SystemExit(1)
    if not bpy.app.background:bpy.ops.wm.quit_blender()

if __name__ == '__main__':
    if bpy.app.background:run()
    else:bpy.app.timers.register(run,first_interval=1)
