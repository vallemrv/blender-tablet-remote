"""blender --background --factory-startup --python-exit-code 1 --python este_archivo."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy
import bmesh
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import selection, modal, curve_edit
from blender_tablet_remote.camera import camera
from blender_tablet_remote import state


class CurveEditTests(unittest.TestCase):
    def setUp(self):
        modal.session.reset()
        if bpy.context.object and bpy.context.object.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
        for o in list(bpy.data.objects):bpy.data.objects.remove(o,do_unlink=True)
        bpy.ops.curve.primitive_bezier_circle_add(radius=1)
        self.obj=bpy.context.object
        bpy.ops.object.mode_set(mode='EDIT')
        curve_edit.set_selection(self.obj,set())
        camera.reset();camera._synced=True
        camera.location=Vector();camera.rotation=Quaternion((1,0,0,0));camera.distance=4;camera.perspective='PERSP'
        camera.set_clipping(.001,100)
        self.rv=SimpleNamespace(window_matrix=Matrix(((1,0,0,0),(0,2,0,0),(0,0,-1,-.02),(0,0,-1,0))))
        self.found=(None,None,SimpleNamespace(width=1000,height=500),self.rv)
        self.patches=[patch.object(selection,'find_view3d',return_value=self.found),patch.object(modal,'undo_push')]
        started=[p.start() for p in self.patches];self.undo=started[1]

    def tearDown(self):
        modal.session.reset()
        if bpy.context.object and bpy.context.object.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
        for p in reversed(self.patches):p.stop()

    def tap(self,point,mode='SET'):
        u,v=camera.project(self.obj.matrix_world@point,self.rv)
        return selection.pick(dict(u=u,v=v,mode=mode,threshold=.015))

    def test_select_control_and_handle_and_empty_deselect(self):
        p=self.obj.data.splines[0].bezier_points[0]
        self.assertEqual(self.tap(p.co)['control'],[0,0,'POINT'])
        self.assertTrue(p.select_control_point)
        self.assertGreater(state.context_snapshot()['selection_counts']['verts'],0)
        self.assertEqual(self.tap(p.handle_left)['control'],[0,0,'LEFT'])
        self.assertFalse(p.select_control_point);self.assertTrue(p.select_left_handle)
        selection.sel_all({'value':True});self.assertEqual(len(curve_edit.selected(self.obj)),12)
        selection.invert({});self.assertEqual(curve_edit.selected(self.obj),set())
        self.assertFalse(self.tap(Vector((0,0,0)),mode='TOGGLE')['hit'])

    def test_move_control_rebuilds_from_baseline_and_cancel_restores(self):
        p=self.obj.data.splines[0].bezier_points[0]
        baseline=[(q.co.copy(),q.handle_left.copy(),q.handle_right.copy()) for q in self.obj.data.splines[0].bezier_points]
        matrix=self.obj.matrix_world.copy()
        self.tap(p.co)
        modal.session.begin('MOVE',[],False,1.,owner_id='test')
        for value in (.2,.4):
            modal.session.values=Vector((value,0,0));modal.session.apply()
            self.assertLess((p.co-(baseline[0][0]+Vector((value,0,0)))).length,1e-6)
            self.assertTrue(modal.session.status()['active'])
        self.assertEqual(self.obj.matrix_world,matrix)
        modal.cancel({'_client_id':'test'})
        for q,old in zip(self.obj.data.splines[0].bezier_points,baseline):
            for actual,want in zip((q.co,q.handle_left,q.handle_right),old):self.assertLess((actual-want).length,1e-6)

    def test_handle_move_is_editable_and_cancel_restores_handle_type(self):
        p=self.obj.data.splines[0].bezier_points[0]
        before=p.handle_left.copy();kind=p.handle_left_type;center=p.co.copy()
        self.tap(p.handle_left)
        modal.session.begin('MOVE',[],False,1.,owner_id='test')
        modal.session.values=Vector((0,.2,0));modal.session.apply()
        self.assertLess((p.handle_left-before-Vector((0,.2,0))).length,1e-6)
        self.assertEqual(p.co,center)
        modal.cancel({'_client_id':'test'})
        self.assertEqual(p.handle_left_type,kind);self.assertLess((p.handle_left-before).length,1e-6)

    def test_scale_confirm_is_one_undo_and_stays_native_curve(self):
        selection.sel_all({'value':True})
        before=[p.co.copy() for p in self.obj.data.splines[0].bezier_points]
        modal.session.begin('SCALE',[],False,1.,owner_id='test')
        modal.session.values=Vector((2,2,2));modal.confirm({'_client_id':'test'})
        self.undo.assert_called_once()
        for p,co in zip(self.obj.data.splines[0].bezier_points,before):self.assertLess((p.co-co*2).length,1e-6)
        self.assertEqual(self.obj.type,'CURVE');self.assertEqual(self.obj.mode,'EDIT')

    def test_rotate_and_continue_move_selection_without_moving_object(self):
        selection.sel_all({'value':True})
        before=[p.co.copy() for p in self.obj.data.splines[0].bezier_points]
        matrix=self.obj.matrix_world.copy()
        modal.session.begin('ROTATE',['Z'],False,1.,owner_id='test')
        modal.session.values=Vector((0,0,.5));modal.session.apply()
        for p,co in zip(self.obj.data.splines[0].bezier_points,before):
            self.assertLess((p.co-Matrix.Rotation(.5,3,'Z')@co).length,1e-6)
        modal.cancel({'_client_id':'test'})
        p=self.obj.data.splines[0].bezier_points[0]
        self.tap(p.co)
        modal.session.begin('MOVE',[],False,1.,owner_id='test')
        modal.session.values=Vector((.2,0,0));modal.session.apply()
        target=self.obj.data.splines[0].bezier_points[1].co.copy()
        u,v=camera.project(target,self.rv)
        result=modal.select_next({'u':u,'v':v,'mode':'SET','threshold':.015,'_client_id':'test'})
        self.assertTrue(result['selection_changed']);self.assertTrue(result['active'])
        self.undo.assert_called_once()
        self.assertEqual(curve_edit.selected(self.obj),{(0,1,'POINT')})
        self.assertEqual(self.obj.matrix_world,matrix)
        modal.cancel({'_client_id':'test'})

    def test_nurbs_points_keep_weight_and_cancel_restores(self):
        bpy.ops.object.mode_set(mode='OBJECT');bpy.data.objects.remove(self.obj,do_unlink=True)
        bpy.ops.curve.primitive_nurbs_circle_add();self.obj=bpy.context.object
        bpy.ops.object.mode_set(mode='EDIT');curve_edit.set_selection(self.obj,{(0,0,'POINT')})
        point=self.obj.data.splines[0].points[0];before=point.co.copy()
        modal.session.begin('MOVE',[],False,1.,owner_id='test')
        modal.session.values=Vector((.2,0,0));modal.session.apply()
        self.assertAlmostEqual(point.co.x,before.x+.2,places=5);self.assertEqual(point.co.w,before.w)
        modal.cancel({'_client_id':'test'})
        self.assertLess((point.co-before).length,1e-6)

    def test_native_curve_duplicate_delete_and_hide_keep_edit_mode(self):
        from blender_tablet_remote.commands import mesh
        p=self.obj.data.splines[0].bezier_points[0]
        self.tap(p.co)
        with patch('blender_tablet_remote.bpy_utils.undo_push') as undo:
            mesh.duplicate({})
            self.assertEqual(sum(len(s.bezier_points) for s in self.obj.data.splines),5)
            mesh.delete({'what':'VERTS'})
            self.assertEqual(sum(len(s.bezier_points) for s in self.obj.data.splines),4)
            curve_edit.set_selection(self.obj,{(0,0,'POINT')})
            selection.hide({})
            self.assertTrue(self.obj.data.splines[0].bezier_points[0].hide)
            self.assertEqual(undo.call_count,3)
        self.assertEqual(self.obj.mode,'EDIT')

    def test_mesh_circle_vertices_and_edges_are_selectable_without_faces(self):
        bpy.ops.object.mode_set(mode='OBJECT');bpy.data.objects.remove(self.obj,do_unlink=True)
        bpy.ops.mesh.primitive_circle_add(vertices=32,radius=1);self.obj=bpy.context.object
        bpy.ops.object.mode_set(mode='EDIT');selection.sel_vertex({});selection.sel_all({'value':False})
        bm=bmesh.from_edit_mesh(self.obj.data);bm.verts.ensure_lookup_table();bm.edges.ensure_lookup_table()
        hit=self.tap(bm.verts[0].co)
        self.assertTrue(hit['hit']);self.assertEqual(hit['element'],'vert')
        self.assertEqual(sum(v.select for v in bm.verts),1)
        selection.sel_edge({});selection.sel_all({'value':False})
        edge=bm.edges[0];mid=(edge.verts[0].co+edge.verts[1].co)/2
        hit=self.tap(mid)
        self.assertTrue(hit['hit']);self.assertEqual(hit['element'],'edge')
        self.assertEqual(sum(e.select for e in bm.edges),1)


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CurveEditTests))
    if not result.wasSuccessful():raise SystemExit(1)
