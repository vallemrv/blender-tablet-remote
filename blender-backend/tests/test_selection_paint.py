"""blender --background --factory-startup --python-exit-code 1 --python este_archivo."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import bpy
import bmesh
from mathutils import Matrix,Quaternion,Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import selection_paint as paint, selection, curve_edit
from blender_tablet_remote.camera import camera


class PaintSelectionTests(unittest.TestCase):
    def setUp(self):
        paint.cancel()
        if bpy.context.object and bpy.context.object.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
        for o in list(bpy.data.objects):bpy.data.objects.remove(o,do_unlink=True)
        camera.reset();camera._synced=True
        camera.location=Vector();camera.rotation=Quaternion((1,0,0,0));camera.distance=4;camera.perspective='PERSP'
        camera.set_clipping(.001,100)
        self.rv=SimpleNamespace(window_matrix=Matrix(((1,0,0,0),(0,2,0,0),(0,0,-1,-.02),(0,0,-1,0))))
        self.found=(None,None,SimpleNamespace(width=1000,height=500),self.rv)
        self.patches=[patch.object(paint,'find_view3d',return_value=self.found),patch.object(paint,'undo_push')]
        started=[p.start() for p in self.patches];self.undo=started[1]

    def tearDown(self):
        paint.cancel()
        if bpy.context.object and bpy.context.object.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
        for p in reversed(self.patches):p.stop()

    def send(self,phase,a,b=None,stroke='one',radius=.015):
        u0,v0=camera.project(Vector(a),self.rv);u1,v1=camera.project(Vector(b or a),self.rv)
        return paint.paint(dict(phase=phase,stroke_id=stroke,_client_id='test',u0=u0,v0=v0,u1=u1,v1=v1,radius=radius))

    def test_object_stroke_inverts_once_and_end_does_not_probe_another_object(self):
        bpy.ops.mesh.primitive_cube_add(size=.5,location=(-.7,0,0));a=bpy.context.object
        bpy.ops.mesh.primitive_cube_add(size=.5,location=(.7,0,0));b=bpy.context.object
        a.select_set(True);b.select_set(False);bpy.context.view_layer.update()
        self.send('BEGIN',(-.7,0,.25));self.assertFalse(a.select_get())
        self.send('UPDATE',(-.7,0,.25));self.assertFalse(a.select_get())
        self.send('END',(.7,0,.25));self.assertFalse(b.select_get())
        self.undo.assert_called_once()
        self.send('BEGIN',(-.7,0,.25),stroke='two');self.assertTrue(a.select_get())
        self.send('UPDATE',(-.7,0,.25),(.7,0,.25),stroke='two');self.assertTrue(b.select_get())
        self.send('CANCEL',(.7,0,.25),stroke='two')
        self.assertFalse(a.select_get());self.assertFalse(b.select_get())
        self.undo.assert_called_once()

    def test_mesh_vertices_toggle_once_and_disconnect_restores(self):
        bpy.ops.mesh.primitive_circle_add(vertices=8,radius=1);obj=bpy.context.object
        bpy.ops.object.mode_set(mode='EDIT');selection.sel_vertex({});selection.sel_all({'value':False})
        bm=bmesh.from_edit_mesh(obj.data);bm.verts.ensure_lookup_table();v=bm.verts[0];point=tuple(v.co)
        self.send('BEGIN',point);self.assertTrue(v.select)
        self.send('UPDATE',point);self.assertTrue(v.select)
        paint.owner_disconnected('test');self.assertFalse(v.select)
        self.send('UPDATE',point);self.assertFalse(v.select)
        self.undo.assert_not_called()

    def test_faces_and_edges_and_cancel_preserve_other_selection(self):
        bpy.ops.mesh.primitive_cube_add();obj=bpy.context.object
        bpy.ops.object.mode_set(mode='EDIT');selection.sel_face({});selection.sel_all({'value':False})
        bm=bmesh.from_edit_mesh(obj.data);bm.faces.ensure_lookup_table()
        face=max(bm.faces,key=lambda f:f.calc_center_median().z)
        self.send('BEGIN',(0,0,1));self.assertTrue(face.select)
        self.send('UPDATE',(0,0,1));self.assertTrue(face.select)
        self.send('CANCEL',(0,0,1));self.assertFalse(face.select)
        selection.sel_edge({});selection.sel_all({'value':False})
        bm.edges.ensure_lookup_table();edge=next(e for e in bm.edges if all(v.co.z>0 for v in e.verts))
        point=tuple((edge.verts[0].co+edge.verts[1].co)/2)
        self.send('BEGIN',point);self.assertTrue(edge.select)
        self.send('UPDATE',point);self.assertTrue(edge.select)
        self.send('END',point);self.undo.assert_called_once()

    def test_curve_controls_and_stale_end_do_not_close_new_stroke(self):
        bpy.ops.curve.primitive_bezier_circle_add();obj=bpy.context.object
        bpy.ops.object.mode_set(mode='EDIT');curve_edit.set_selection(obj,set())
        point=tuple(obj.data.splines[0].bezier_points[0].co)
        self.send('BEGIN',point);self.assertTrue(obj.data.splines[0].bezier_points[0].select_control_point)
        self.send('CANCEL',point)
        self.send('BEGIN',point,stroke='two')
        self.send('END',point,stroke='one')
        self.assertIsNotNone(paint._session)
        self.send('CANCEL',point,stroke='two');self.assertEqual(curve_edit.selected(obj),set())

    def test_locked_object_is_not_selected(self):
        bpy.ops.mesh.primitive_cube_add();obj=bpy.context.object
        obj.select_set(False);obj.hide_select=True;bpy.context.view_layer.update()
        self.send('BEGIN',(0,0,1));self.send('END',(0,0,1))
        self.assertFalse(obj.select_get());self.undo.assert_not_called()


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PaintSelectionTests))
    if not result.wasSuccessful():raise SystemExit(1)
