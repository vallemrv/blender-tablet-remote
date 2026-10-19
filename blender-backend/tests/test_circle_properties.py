"""blender --background --factory-startup --python-exit-code 1 --python este_archivo."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import object_properties as props, circle_properties, selection
from blender_tablet_remote.camera import camera


class CircleTests(unittest.TestCase):
    def setUp(self):
        if bpy.context.object and bpy.context.object.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
        for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
        bpy.ops.mesh.primitive_circle_add(vertices=32,radius=1)
        self.obj=bpy.context.object
        bpy.context.scene.unit_settings.scale_length=1
        camera.reset();camera._synced=True
        camera.location=Vector();camera.rotation=Quaternion((1,0,0,0));camera.distance=4
        camera.perspective='PERSP';camera.set_clipping(.001,100)
        self.rv=SimpleNamespace(window_matrix=Matrix(((1,0,0,0),(0,2,0,0),(0,0,-1,-.02),(0,0,-1,0))))
        self.found=(None,None,SimpleNamespace(width=1000,height=500),self.rv)
        self.patches=[patch.object(selection,'find_view3d',return_value=self.found),
                      patch.object(props,'undo_push'),patch.object(selection.state,'snapshot',return_value={})]
        started=[p.start() for p in self.patches];self.undo=started[1]

    def tearDown(self):
        for p in reversed(self.patches):p.stop()

    def resize(self,count):
        state=props.describe(self.obj)
        return props.apply(dict(object_id=state['id'],revision=state['revision'],values={'circle_vertices':count}))

    def tap(self,point,mode='SET'):
        bpy.context.view_layer.update()
        u,v=camera.project(Vector(point),self.rv)
        return selection.pick(dict(u=u,v=v,mode=mode))

    def test_resolution_up_and_down_preserves_circle_transform_and_linked_mesh(self):
        twin=self.obj.copy();bpy.context.scene.collection.objects.link(twin)
        data=twin.data
        self.obj.location=(1,2,3);self.obj.scale=(2,3,1);self.obj.rotation_euler=(.2,.3,.4)
        bpy.context.view_layer.update();matrix=self.obj.matrix_world.copy()
        for count in (64,12,3,128):
            self.resize(count)
            self.assertEqual(len(self.obj.data.vertices),count)
            self.assertEqual(len(self.obj.data.edges),count)
            self.assertEqual(len(self.obj.data.polygons),0)
            self.assertAlmostEqual(circle_properties.describe(self.obj)['radius'],1.,places=5)
            self.assertEqual(self.obj.matrix_world,matrix)
            self.assertEqual(twin.data,data);self.assertEqual(len(data.vertices),32)
        self.assertEqual(self.undo.call_count,4)
        self.resize(128);self.assertEqual(self.undo.call_count,4)

    def test_deformed_mesh_and_custom_data_never_offer_rebuild(self):
        self.obj.data.vertices[0].co.x+=.2;self.obj.data.update()
        self.assertNotIn('circle_vertices',props.describe(self.obj)['values'])
        bpy.ops.mesh.primitive_circle_add();self.obj=bpy.context.object
        self.obj.vertex_groups.new(name='Pesos')
        self.assertIsNone(circle_properties.describe(self.obj))

    def test_noninteger_resolution_is_rejected_without_changing_mesh(self):
        from blender_tablet_remote.errors import BadPayload
        data=self.obj.data
        for count in (2,3.5,4097):
            with self.assertRaises(BadPayload):self.resize(count)
            self.assertEqual(self.obj.data,data)
        self.undo.assert_not_called()

    def test_saved_circle_remains_adjustable(self):
        self.resize(48)
        with tempfile.TemporaryDirectory() as folder:
            path=str(Path(folder)/'circle.blend')
            bpy.ops.wm.save_as_mainfile(filepath=path);bpy.ops.wm.open_mainfile(filepath=path)
            self.obj=bpy.context.object
            self.assertEqual(props.describe(self.obj)['values']['circle_vertices'],48)
            self.resize(24)
            self.assertEqual(len(self.obj.data.vertices),24)

    def test_bezier_circle_native_resolution_and_contour_selection(self):
        bpy.data.objects.remove(self.obj,do_unlink=True)
        bpy.ops.curve.primitive_bezier_circle_add(radius=1)
        self.obj=bpy.context.object
        self.assertEqual(self.tap((1,0,0))['object'],self.obj.name)
        control_points=[tuple(p.co) for p in self.obj.data.splines[0].bezier_points]
        old=self.obj.data
        twin=self.obj.copy();bpy.context.scene.collection.objects.link(twin)
        state=props.describe(self.obj)
        self.assertIn('curve_resolution',state['values'])
        props.apply(dict(object_id=state['id'],revision=state['revision'],values={'curve_resolution':64}))
        self.assertEqual(self.obj.data.resolution_u,64)
        self.assertEqual(twin.data,old)
        self.assertNotEqual(twin.data.resolution_u,64)
        self.assertEqual([tuple(p.co) for p in self.obj.data.splines[0].bezier_points],control_points)
        self.undo.assert_called_once()

    def test_tap_selects_contour_in_both_views_but_not_empty_center(self):
        for projection in ('PERSP','ORTHO'):
            camera.perspective=projection
            self.assertEqual(self.tap((1.01,0,0))['object'],self.obj.name)
            self.assertTrue(self.obj.select_get())
            self.tap((1,0,0),mode='TOGGLE');self.assertFalse(self.obj.select_get())
            self.assertFalse(self.tap((0,0,0))['hit'])

    def test_occlusion_hidden_locked_and_evaluated_geometry(self):
        bpy.ops.mesh.primitive_plane_add(size=10,location=(0,0,.5));plane=bpy.context.object
        self.assertEqual(self.tap((1,0,0))['object'],plane.name)
        plane.hide_set(True)
        self.obj.hide_select=True;self.assertFalse(self.tap((1,0,0))['hit'])
        self.obj.hide_select=False;self.obj.hide_set(True);self.assertFalse(self.tap((1,0,0))['hit'])
        self.obj.hide_set(False)
        mirror=self.obj.modifiers.new('Espejo','MIRROR');mirror.use_axis[0]=False;mirror.use_axis[2]=True
        self.obj.location.z=-1
        self.assertEqual(self.tap((1,0,-1))['object'],self.obj.name)


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CircleTests))
    if not result.wasSuccessful():raise SystemExit(1)
