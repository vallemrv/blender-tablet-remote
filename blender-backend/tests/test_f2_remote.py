"""Native F2 with tablet projection: blender --factory-startup --python this_file."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import bpy
import bmesh
from mathutils import Vector, Quaternion
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import mesh, history, sessions
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
        return obj
    def run_f2(self,point):
        u,v=camera.project(Vector(point),self.rv)
        return mesh.f2_complete(dict(u=u,v=v))
    def test_vertex_completes_quad_without_pc_transform_modal(self):
        obj=self.shape([(0,0,0),(1,0,0),(0,1,0)],[(0,1),(0,2)],selected_vertex=0)
        matrix=obj.matrix_world.copy()
        with patch('blender_tablet_remote.bpy_utils.undo_push') as push:self.run_f2((1,1,0))
        bm=bmesh.from_edit_mesh(obj.data)
        self.assertEqual((len(bm.verts),len(bm.faces)),(4,1));push.assert_called_once()
        self.assertTrue(any((v.co-Vector((1,1,0))).length<1e-7 for v in bm.verts))
        self.assertEqual(obj.mode,'EDIT');self.assertEqual(obj.matrix_world,matrix)
        self.assertEqual((tuple(self.rv.view_location),tuple(self.rv.view_rotation),self.rv.view_distance,self.rv.view_perspective),self.pc)
    def test_edge_uses_the_tablet_side_of_the_selected_border(self):
        obj=self.shape([(0,0,0),(1,0,0),(0,1,0),(1,1,0),(0,-1,0),(1,-1,0)],[(0,1),(0,2),(1,3),(0,4),(1,5)],selected_edge=0)
        self.run_f2((.5,1,0))
        face=list(bmesh.from_edit_mesh(obj.data).faces)[0]
        self.assertTrue(all(v.co.y>=0 for v in face.verts))
    def test_invalid_corner_restores_without_undo(self):
        obj=self.shape([(0,0,0),(1,0,0)],[(0,1)],selected_vertex=0)
        with patch('blender_tablet_remote.bpy_utils.undo_push') as push:
            with self.assertRaises(CommandError):self.run_f2((1,1,0))
        self.assertEqual((len(bmesh.from_edit_mesh(obj.data).verts),len(bmesh.from_edit_mesh(obj.data).faces)),(2,0));push.assert_not_called()
        self.assertFalse(any(m.name.startswith('.remote_f2_backup') for m in bpy.data.meshes))
    def test_single_undo_and_redo_restore_face(self):
        obj=self.shape([(0,0,0),(1,0,0),(0,1,0)],[(0,1),(0,2)],selected_vertex=0)
        name=obj.name;undo_push('Before F2')
        self.run_f2((1,1,0))
        history.undo({});self.assertEqual(len(bmesh.from_edit_mesh(bpy.data.objects[name].data).faces),0)
        history.redo({});self.assertEqual(len(bmesh.from_edit_mesh(bpy.data.objects[name].data).faces),1)

def run():
    bpy.ops.preferences.addon_enable(module='bl_ext.blender_org.f2')
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RemoteF2Tests))
    if not result.wasSuccessful():
        import os
        sys.stdout.flush();sys.stderr.flush();os._exit(1)
    bpy.ops.wm.quit_blender()
bpy.app.timers.register(run,first_interval=1)
