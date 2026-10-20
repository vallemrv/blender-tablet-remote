"""Native F2 with tablet projection: blender --factory-startup --python this_file."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import bpy
import bmesh
from mathutils import Vector, Quaternion, Matrix
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import tools, f2, history, sessions, snap
from blender_tablet_remote.camera import camera
from blender_tablet_remote.bpy_utils import find_view3d, undo_push
from blender_tablet_remote.errors import CommandError

class RemoteF2Tests(unittest.TestCase):
    def setUp(self):
        sessions.cancel_all()
        if bpy.context.object and bpy.context.object.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
        for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
        camera.reset();camera._synced=True;camera.location=Vector();camera.rotation=Quaternion((1,0,0,0));camera.distance=5;camera.perspective='ORTHO'
        camera.set_clipping(.001,100)
        self.rv=find_view3d()[3]
        self.pc=(tuple(self.rv.view_location),tuple(self.rv.view_rotation),self.rv.view_distance,self.rv.view_perspective)
    def shape(self,vertices,edges,selected_vertex=None,selected_edge=None):
        data=bpy.data.meshes.new('F2 fixture');data.from_pydata(vertices,edges,[])
        obj=bpy.data.objects.new('F2 fixture',data);bpy.context.collection.objects.link(obj)
        obj.select_set(True);bpy.context.view_layer.objects.active=obj
        bpy.ops.object.mode_set(mode='EDIT');bpy.context.scene.tool_settings.mesh_select_mode=(True,False,False)
        bm=bmesh.from_edit_mesh(data);bm.verts.ensure_lookup_table();bm.edges.ensure_lookup_table()
        for seq in (bm.verts,bm.edges,bm.faces):
            for e in seq:e.select=False
        if selected_vertex is not None:bm.verts[selected_vertex].select_set(True)
        if selected_edge is not None:
            bpy.context.scene.tool_settings.mesh_select_mode=(False,True,False);bm.edges[selected_edge].select_set(True)
        bmesh.update_edit_mesh(data)
        tools.begin(dict(tool='F2',parameters={},_client_id='tablet'))
        return obj
    def gesture(self,phase,point,identifier='touch'):
        u,v=camera.project(Vector(point),self.rv)
        return tools.f2_gesture(dict(phase=phase,u=u,v=v,gesture_id=identifier,_client_id='tablet'))
    def run_f2(self,point):
        self.gesture('BEGIN',point)
        return self.gesture('END',point)
    def tearDown(self):sessions.cancel_all()
    def test_vertex_completes_quad_without_pc_transform_modal(self):
        obj=self.shape([(0,0,0),(1,0,0),(0,1,0)],[(0,1),(0,2)],selected_vertex=0)
        matrix=obj.matrix_world.copy()
        with patch('blender_tablet_remote.bpy_utils.undo_push') as push:self.run_f2((1,1,0))
        bm=bmesh.from_edit_mesh(obj.data)
        self.assertEqual((len(bm.verts),len(bm.faces)),(4,1));push.assert_called_once()
        self.assertTrue(any((v.co-Vector((1,1,0))).length<1e-6 for v in bm.verts))
        self.assertEqual(obj.mode,'EDIT');self.assertEqual(obj.matrix_world,matrix)
        self.assertEqual((tuple(self.rv.view_location),tuple(self.rv.view_rotation),self.rv.view_distance,self.rv.view_perspective),self.pc)
    def test_edge_uses_the_tablet_side_of_the_selected_border(self):
        obj=self.shape([(0,0,0),(1,0,0),(0,1,0),(1,1,0),(0,-1,0),(1,-1,0)],[(0,1),(0,2),(1,3),(0,4),(1,5)],selected_edge=0)
        self.run_f2((.5,1,0))
        face=list(bmesh.from_edit_mesh(obj.data).faces)[0]
        self.assertTrue(all(v.co.y>=0 for v in face.verts))
    def test_edge_with_front_vertices_only_adds_the_front_edge_and_face(self):
        obj=self.shape([(0,0,0),(1,0,0),(0,1,0),(1,1.2,0)],[(0,1),(0,2),(1,3)],selected_edge=0)
        with patch('blender_tablet_remote.bpy_utils.undo_push') as push:
            self.gesture('BEGIN',(.5,1.5,0));self.gesture('UPDATE',(.5,3,0));self.gesture('END',(.5,3,0))
            push.assert_called_once()
        bm=bmesh.from_edit_mesh(obj.data)
        self.assertEqual((len(bm.verts),len(bm.edges),len(bm.faces)),(4,4,1))
        self.assertTrue(any((v.co-Vector((1,1.2,0))).length<1e-6 for v in bm.verts))
        selected=[e for e in bm.edges if e.select]
        self.assertEqual(len(selected),1)
        self.assertEqual({tuple(round(c,6) for c in v.co) for v in selected[0].verts},{(0,1,0),(1,1.2,0)})
    def test_edge_on_a_face_uses_front_vertices_on_the_open_side(self):
        obj=self.shape([(0,0,0),(1,0,0),(0,-1,0),(1,-1,0),(0,1,0),(1,1,0)],[(0,1),(0,2),(1,3),(2,3),(0,4),(1,5)])
        bm=bmesh.from_edit_mesh(obj.data);bm.verts.ensure_lookup_table()
        bm.faces.new([bm.verts[i] for i in (0,2,3,1)])
        bpy.context.scene.tool_settings.mesh_select_mode=(False,True,False)
        bm.edges.ensure_lookup_table();bm.edges[0].select_set(True);bmesh.update_edit_mesh(obj.data)
        self.run_f2((.5,-.5,0))
        bm=bmesh.from_edit_mesh(obj.data)
        self.assertEqual((len(bm.verts),len(bm.faces)),(6,2))
        self.assertTrue(any(all(v.co.y>=-1e-6 for v in f.verts) for f in bm.faces))
    def test_two_unconnected_vertices_create_two_new_vertices_and_drag_in_same_gesture(self):
        obj=self.shape([(0,0,0),(1,0,0)],[])
        bpy.ops.mesh.select_all(action='SELECT')
        with patch('blender_tablet_remote.bpy_utils.undo_push') as push:
            self.gesture('BEGIN',(.5,1,0))
            self.gesture('UPDATE',(.5,1.2,0))
            self.gesture('UPDATE',(.5,1.4,0))
            self.gesture('END',(.5,100,0))
            push.assert_called_once()
        bm=bmesh.from_edit_mesh(obj.data)
        self.assertEqual((len(bm.verts),len(bm.faces)),(4,1))
        self.assertEqual(len(list(bm.faces)[0].verts),4)
        selected=[v for v in bm.verts if v.select]
        self.assertEqual(len(selected),2)
        self.assertTrue(all(abs(v.co.y-1.4)<1e-6 for v in selected))
        self.assertFalse(__import__('blender_tablet_remote.commands.modal',fromlist=['session']).session.active)

    def test_three_vertices_create_fourth_and_leave_only_it_selected(self):
        obj=self.shape([(0,0,0),(1,0,0),(1,1,0)],[(0,1),(1,2)])
        bpy.ops.mesh.select_all(action='SELECT')
        self.gesture('BEGIN',(0,1,0));self.gesture('UPDATE',(-.5,1.2,0));self.gesture('END',(-.5,1.2,0))
        bm=bmesh.from_edit_mesh(obj.data)
        self.assertEqual((len(bm.verts),len(bm.faces)),(4,1))
        selected=[v for v in bm.verts if v.select]
        self.assertEqual(len(selected),1)
        self.assertLess((selected[0].co-Vector((-.5,1.2,0))).length,1e-6)

    def test_fourth_vertex_tap_automatically_closes_quad(self):
        obj=self.shape([(0,0,0),(1,0,0),(1,1,0),(0,1,0)],[(0,1),(1,2),(2,3)])
        for point in [(0,0,0),(1,0,0),(1,1,0)]:self.run_f2(point)
        self.assertEqual(len(bmesh.from_edit_mesh(obj.data).faces),0)
        self.run_f2((0,1,0))
        bm=bmesh.from_edit_mesh(obj.data)
        self.assertEqual((len(bm.verts),len(bm.faces)),(4,1))
        self.assertEqual(len(list(bm.faces)[0].verts),4)

    def test_edge_mode_selects_only_new_front_edge_for_continuation(self):
        obj=self.shape([(0,0,0),(1,0,0)],[(0,1)],selected_edge=0)
        self.run_f2((.5,1,0))
        bm=bmesh.from_edit_mesh(obj.data)
        selected=[e for e in bm.edges if e.select]
        self.assertEqual(len(selected),1)
        self.assertTrue(all(abs(v.co.y-1)<1e-6 for v in selected[0].verts))
        self.run_f2((.5,1.4,0))
        bm=bmesh.from_edit_mesh(obj.data)
        self.assertEqual((len(bm.verts),len(bm.faces)),(6,2))
        self.assertTrue(all(len(f.verts)==4 for f in bm.faces))

    def test_existing_quad_extends_nearest_border_without_duplicate_face(self):
        obj=self.shape([(0,0,0),(1,0,0),(1,1,0),(0,1,0)],[(0,1),(1,2),(2,3),(3,0)])
        bm=bmesh.from_edit_mesh(obj.data);bm.verts.ensure_lookup_table()
        bm.faces.new(list(bm.verts));bmesh.update_edit_mesh(obj.data)
        for point in [(0,0,0),(1,0,0),(1,1,0)]:self.run_f2(point)
        self.gesture('BEGIN',(0,1,0));self.gesture('UPDATE',(-1,2,0));self.gesture('END',(-1,2,0))
        bm=bmesh.from_edit_mesh(obj.data)
        self.assertEqual((len(bm.verts),len(bm.faces)),(6,2))
        self.assertTrue(all(len(face.verts)==4 for face in bm.faces))
        self.assertEqual(sum(v.select for v in bm.verts),2)

    def test_dragging_from_a_vertex_moves_it_like_tweak_without_creating(self):
        obj=self.shape([(0,0,0),(1,0,0),(0,1,0)],[(0,1),(0,2)],selected_vertex=1)
        with patch('blender_tablet_remote.bpy_utils.undo_push') as push:
            self.gesture('BEGIN',(0,0,0));self.gesture('UPDATE',(.5,.5,0));self.gesture('UPDATE',(-.4,-.3,0))
            self.gesture('END',(-.4,-.3,0))
            push.assert_called_once()
        bm=bmesh.from_edit_mesh(obj.data);bm.verts.ensure_lookup_table()
        self.assertEqual((len(bm.verts),len(bm.faces)),(3,0))
        self.assertLess((bm.verts[0].co-Vector((-.4,-.3,0))).length,1e-5)
        # La selección previa se conserva para seguir creando caras.
        self.assertEqual([v.index for v in bm.verts if v.select],[1])
        self.assertEqual(tools.tool_session.armed_tool,'F2')
    def test_small_jitter_on_a_vertex_is_still_a_tap(self):
        obj=self.shape([(0,0,0),(1,0,0),(0,1,0)],[(0,1),(0,2)])
        self.gesture('BEGIN',(0,0,0));self.gesture('UPDATE',(.001,0,0));self.gesture('END',(.001,0,0))
        bm=bmesh.from_edit_mesh(obj.data);bm.verts.ensure_lookup_table()
        self.assertEqual(bm.verts[0].co,Vector((0,0,0)));self.assertTrue(bm.verts[0].select)
    def test_cancelled_vertex_drag_restores_its_position(self):
        obj=self.shape([(0,0,0),(1,0,0),(0,1,0)],[(0,1),(0,2)])
        self.gesture('BEGIN',(0,0,0));self.gesture('UPDATE',(.5,.5,0));self.gesture('CANCEL',(.5,.5,0))
        bm=bmesh.from_edit_mesh(obj.data);bm.verts.ensure_lookup_table()
        self.assertEqual(bm.verts[0].co,Vector((0,0,0)))

    def test_invalid_drag_keeps_last_visible_quad_until_release(self):
        obj=self.shape([(0,0,0),(1,0,0)],[(0,1)],selected_edge=0)
        self.gesture('BEGIN',(.5,1,0))
        self.gesture('UPDATE',(.5,0,0))
        self.gesture('END',(.5,0,0))
        bm=bmesh.from_edit_mesh(obj.data)
        self.assertEqual(len(bm.faces),1)
        self.assertTrue(all(abs(v.co.y-1)<1e-6 for v in bm.verts if v.select))
        self.assertFalse(any(m.name.startswith('.remote_f2_') for m in bpy.data.meshes))

    def test_placement_respects_rotated_scaled_object_and_cancel_restores_selection(self):
        obj=self.shape([(0,0,0),(1,0,0)],[(0,1)],selected_edge=0)
        obj.matrix_world=Matrix.Translation((.1,0,0)) @ Matrix.Rotation(.2,4,'Z') @ Matrix.Diagonal((1.2,.7,1,1))
        bpy.context.view_layer.update();matrix=obj.matrix_world.copy()
        target=matrix@Vector((.5,1,0))
        self.gesture('BEGIN',target)
        bm=bmesh.from_edit_mesh(obj.data)
        selected=[obj.matrix_world@v.co for v in bm.verts if v.select]
        self.assertLess((sum(selected,Vector())/2-target).length,1e-6)
        self.gesture('UPDATE',matrix@Vector((.5,1.4,0)))
        self.gesture('CANCEL',target)
        bm=bmesh.from_edit_mesh(obj.data)
        self.assertEqual((len(bm.verts),len(bm.faces),sum(e.select for e in bm.edges)),(2,0,1))
        self.assertEqual(obj.matrix_world,matrix)
        self.assertFalse(any(m.name.startswith('.remote_f2_') for m in bpy.data.meshes))

    def test_invalid_corner_restores_without_undo(self):
        obj=self.shape([(0,0,0),(1,0,0)],[(0,1)],selected_vertex=0)
        with patch('blender_tablet_remote.bpy_utils.undo_push') as push:
            with self.assertRaises(CommandError):self.run_f2((1,1,0))
        self.assertEqual((len(bmesh.from_edit_mesh(obj.data).verts),len(bmesh.from_edit_mesh(obj.data).faces)),(2,0));push.assert_not_called()
        self.assertFalse(any(m.name.startswith('.remote_f2_') for m in bpy.data.meshes))
    def test_tap_selects_or_deselects_without_creating_a_face(self):
        obj=self.shape([(0,0,0),(1,0,0),(0,1,0)],[(0,1),(0,2)])
        with patch('blender_tablet_remote.bpy_utils.undo_push') as push:
            self.run_f2((0,0,0))
            bm=bmesh.from_edit_mesh(obj.data);self.assertEqual(sum(v.select for v in bm.verts),1)
            self.assertEqual(len(bm.faces),0)
            self.run_f2((0,0,0));self.assertEqual(sum(v.select for v in bmesh.from_edit_mesh(obj.data).verts),0)
            push.assert_not_called()
        self.assertEqual(tools.tool_session.armed_tool,'F2')
    def test_end_uses_last_preview_without_query_and_duplicate_end_is_harmless(self):
        obj=self.shape([(0,0,0),(1,0,0),(0,1,0)],[(0,1),(0,2)],selected_vertex=0)
        with patch('blender_tablet_remote.bpy_utils.undo_push') as push:
            self.gesture('BEGIN',(1,1,0))
            self.assertEqual(len(bmesh.from_edit_mesh(obj.data).faces),1);push.assert_not_called()
            with patch.object(snap,'query_edit_surface_candidate',side_effect=AssertionError('END raycast')):
                self.gesture('END',(10,10,0));self.gesture('END',(10,10,0))
            push.assert_called_once()
        self.assertEqual(len(bmesh.from_edit_mesh(obj.data).faces),1)
        self.assertEqual(tools.tool_session.armed_tool,'F2')
    def test_cancel_discards_preview_and_keeps_original_selection(self):
        obj=self.shape([(0,0,0),(1,0,0),(0,1,0)],[(0,1),(0,2)],selected_vertex=0)
        with patch('blender_tablet_remote.bpy_utils.undo_push') as push:
            self.gesture('BEGIN',(1,1,0));self.gesture('CANCEL',(1,1,0))
            bm=bmesh.from_edit_mesh(obj.data)
            self.assertEqual((len(bm.verts),len(bm.faces),sum(v.select for v in bm.verts)),(3,0,1))
            push.assert_not_called()
        self.assertEqual(tools.tool_session.armed_tool,'F2')
    def test_multiple_vertices_fill_without_creating_new_vertices(self):
        obj=self.shape([(0,0,0),(1,0,0),(1,1,0),(0,1,0)],[(0,1),(1,2),(2,3),(3,0)])
        bpy.ops.mesh.select_all(action='SELECT')
        self.run_f2((.5,.5,0))
        bm=bmesh.from_edit_mesh(obj.data);self.assertEqual((len(bm.verts),len(bm.faces)),(4,1))
    def test_switch_and_disconnect_restore_pending_face(self):
        obj=self.shape([(0,0,0),(1,0,0),(0,1,0)],[(0,1),(0,2)],selected_vertex=0)
        self.gesture('BEGIN',(1,1,0))
        tools.begin(dict(tool='KNIFE',parameters={},_client_id='tablet'))
        self.assertEqual(len(bmesh.from_edit_mesh(obj.data).faces),0)
        with self.assertRaises(CommandError):self.gesture('END',(1,1,0))
        tools.cancel(dict(_client_id='tablet'))
        tools.begin(dict(tool='F2',parameters={},_client_id='tablet'))
        self.gesture('BEGIN',(1,1,0))
        tools.tool_session.owner_disconnected('tablet')
        self.assertEqual(len(bmesh.from_edit_mesh(obj.data).faces),0)
        self.assertIsNone(f2._pending)

    def test_save_discards_pending_preview_without_committing_it(self):
        from blender_tablet_remote.cad import lifecycle
        import tempfile
        obj=self.shape([(0,0,0),(1,0,0),(0,1,0)],[(0,1),(0,2)],selected_vertex=0)
        lifecycle.register_handlers()
        try:
            self.gesture('BEGIN',(1,1,0))
            with tempfile.TemporaryDirectory() as folder:
                bpy.ops.wm.save_as_mainfile(filepath=str(Path(folder)/'f2.blend'))
            self.assertEqual(len(bmesh.from_edit_mesh(obj.data).faces),0)
            self.assertIsNone(f2._pending)
            self.gesture('END',(1,1,0))
            self.assertEqual(len(bmesh.from_edit_mesh(obj.data).faces),0)
        finally:lifecycle.unregister_handlers()
    def test_foreign_owner_cannot_commit_a_pending_face(self):
        self.shape([(0,0,0),(1,0,0),(0,1,0)],[(0,1),(0,2)],selected_vertex=0)
        self.gesture('BEGIN',(1,1,0))
        with self.assertRaises(CommandError):tools.f2_gesture(dict(phase='END',gesture_id='touch',_client_id='other'))
        self.assertIsNotNone(f2._pending)
        self.gesture('CANCEL',(1,1,0))

    def test_collinear_corner_does_not_commit_a_zero_area_face(self):
        obj=self.shape([(0,0,0),(1,0,0),(-1,0,0)],[(0,1),(0,2)],selected_vertex=0)
        with patch('blender_tablet_remote.bpy_utils.undo_push') as push:
            with self.assertRaises(CommandError):self.run_f2((0,1,0))
            push.assert_not_called()
        bm=bmesh.from_edit_mesh(obj.data);self.assertEqual((len(bm.verts),len(bm.faces)),(3,0))

    def test_single_undo_and_redo_restore_face(self):
        obj=self.shape([(0,0,0),(1,0,0),(0,1,0)],[(0,1),(0,2)],selected_vertex=0)
        name=obj.name;undo_push('Before F2')
        self.run_f2((1,1,0))
        history.undo({});self.assertEqual(len(bmesh.from_edit_mesh(bpy.data.objects[name].data).faces),0)
        history.redo({});self.assertEqual(len(bmesh.from_edit_mesh(bpy.data.objects[name].data).faces),1)

def run():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RemoteF2Tests))
    if not result.wasSuccessful():
        import os
        sys.stdout.flush();sys.stderr.flush();os._exit(1)
    bpy.ops.wm.quit_blender()
bpy.app.timers.register(run,first_interval=1)
