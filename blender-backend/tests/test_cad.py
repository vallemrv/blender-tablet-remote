"""CAD vertical slice. blender -b --factory-startup --python tests/test_cad.py.
Use GUI Blender with -- --gpu for real undo and camera projection checks.
"""
import copy
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import bpy
import bmesh
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.cad import document as model
from blender_tablet_remote.cad.kernel import kernel
from blender_tablet_remote.cad.runtime import runtime, FEATURE_KEY
from blender_tablet_remote.commands import cad, mode, sessions
from blender_tablet_remote.errors import CommandError

OWNER = {'_client_id':'test'}


def volume(obj):
    bm=bmesh.new()
    bm.from_mesh(obj.data)
    result=bm.calc_volume(signed=True)
    assert all(e.is_manifold for e in bm.edges)
    bm.free()
    return result


class CadTests(unittest.TestCase):
    def setUp(self):
        sessions.cancel_all()
        if bpy.context.view_layer.objects.active and bpy.context.view_layer.objects.active.mode!='OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj,do_unlink=True)
        if model.KEY in bpy.context.scene:
            del bpy.context.scene[model.KEY]
        bpy.context.scene.unit_settings.scale_length=1
        runtime.reset()
        mode.mode_set(dict(mode='CAD',**OWNER))
        cad.sketch_create(dict(plane='XY',**OWNER))

    def tearDown(self):
        sessions.cancel_all()

    def draw(self,typ,a,b):
        with patch.object(cad,'_endpoint',return_value=None):
            return self.draw_unsnapped(typ,a,b)

    def draw_unsnapped(self,typ,a,b):
        with patch.object(runtime,'point',return_value=a):
            cad.entity_begin(dict(type=typ,u=.1,v=.1,**OWNER))
        with patch.object(runtime,'point',return_value=b):
            status=cad.entity_update(dict(u=.5,v=.5,**OWNER))
        identifier=status['selection']['id']
        cad.confirm(OWNER)
        return identifier

    def rect(self):
        return self.draw('RECTANGLE',(0,0),(.08,.045))

    def extrude(self,entity,depth=.02,confirm=True):
        status=cad.extrude_begin(dict(profile_id='profile_'+entity,depth=depth,**OWNER))
        identifier=status['selection']['id']
        if confirm:
            cad.confirm(OWNER)
        return identifier

    def obj(self):
        return runtime.objects(runtime.doc())[0]

    def test_full_rectangle_resize_volume_stable_identity(self):
        e=self.rect()
        feature=self.extrude(e)
        obj=self.obj()
        self.assertAlmostEqual(volume(obj),.08*.045*.02,places=10)
        cad.entity_set(dict(entity_id=e,values={'width':.1},**OWNER))
        self.assertEqual(obj.as_pointer(),self.obj().as_pointer())
        self.assertEqual(obj[FEATURE_KEY],feature)
        self.assertAlmostEqual(volume(obj),.1*.045*.02,places=10)
        self.assertEqual(runtime.doc()['revision'],4)

    def test_circle_hole_rebuild_is_manifold(self):
        e=self.rect()
        c=self.draw('CIRCLE',(.04,.0225),(.043,.0225))
        self.extrude(e)
        expected=(.08*.045-math.pi*.003**2)*.02
        self.assertAlmostEqual(volume(self.obj()),expected,delta=expected*1e-5)
        cad.entity_set(dict(entity_id=c,values={'diameter':.012},**OWNER))
        expected=(.08*.045-math.pi*.006**2)*.02
        self.assertAlmostEqual(volume(self.obj()),expected,delta=expected*2e-5)

    def test_circle_extrusion(self):
        c=self.draw('CIRCLE',(0,0),(.003,0))
        self.extrude(c)
        self.assertAlmostEqual(volume(self.obj()),math.pi*.003**2*.02,delta=3e-10)

    def test_all_planes_positive_manifold_volumes(self):
        for plane in model.PLANES:
            doc=model.new_document()
            sketch=dict(id='s',plane=plane,entities=[])
            e=dict(id='e',type='RECTANGLE',x=0,y=0,width=.08,height=.045)
            sketch['entities'].append(e)
            vertices,faces=kernel.extrude(sketch,e,.02)
            mesh=bpy.data.meshes.new('test')
            mesh.from_pydata(vertices,[],faces)
            obj=bpy.data.objects.new('test',mesh)
            self.assertAlmostEqual(volume(obj),.08*.045*.02,places=10)
            bpy.data.objects.remove(obj)
            bpy.data.meshes.remove(mesh)

    def test_invalid_dimension_is_atomic(self):
        e=self.rect()
        self.extrude(e)
        raw=bpy.context.scene[model.KEY]
        before=volume(self.obj())
        for value in (0,-1,float('nan'),float('inf'),'oops'):
            with self.assertRaises(CommandError):
                cad.entity_set(dict(entity_id=e,values={'width':value},**OWNER))
            self.assertEqual(raw,bpy.context.scene[model.KEY])
            self.assertEqual(before,volume(self.obj()))

    def test_crossing_profile_does_not_destroy_previous_mesh(self):
        e=self.rect()
        c=self.draw('CIRCLE',(.04,.0225),(.043,.0225))
        self.extrude(e)
        before=volume(self.obj())
        with self.assertRaises(CommandError):
            cad.entity_set(dict(entity_id=c,values={'diameter':.06},**OWNER))
        self.assertEqual(before,volume(self.obj()))

    def test_entity_preview_confirm_last_and_cancel(self):
        raw=bpy.context.scene[model.KEY]
        with patch.object(runtime,'point',return_value=(0,0)):
            cad.entity_begin(dict(type='RECTANGLE',u=.1,v=.1,**OWNER))
        with patch.object(runtime,'point',return_value=(.08,.045)):
            cad.entity_update(dict(u=.5,v=.5,**OWNER))
        self.assertEqual(raw,bpy.context.scene[model.KEY])
        cad.cancel(OWNER)
        self.assertEqual(raw,bpy.context.scene[model.KEY])
        self.assertFalse(runtime.doc()['sketches'][0]['entities'])
        self.rect()
        self.assertEqual(len(runtime.doc()['sketches'][0]['entities']),1)

    def test_extrusion_preview_depth_cancel_no_accumulation(self):
        e=self.rect()
        raw=bpy.context.scene[model.KEY]
        self.extrude(e,confirm=False)
        for depth in (.03,.01,.02):
            cad.extrude_update(dict(depth=depth,**OWNER))
            self.assertAlmostEqual(volume(self.obj()),.08*.045*depth,places=10)
        cad.cancel(OWNER)
        self.assertFalse(runtime.objects(runtime.doc()))
        self.assertEqual(raw,bpy.context.scene[model.KEY])

    def test_session_ownership_and_mutual_exclusion(self):
        e=self.rect()
        self.extrude(e,confirm=False)
        with self.assertRaises(CommandError):
            cad.confirm({'_client_id':'other'})
        sessions.cancel_transform()
        self.assertIsNone(runtime.session)
        self.assertFalse(runtime.objects(runtime.doc()))

    def test_suppression_and_rebuild_preserve_object_transform(self):
        e=self.rect()
        f=self.extrude(e)
        obj=self.obj()
        obj.location=(3,2,1)
        obj.rotation_euler=(.4,.2,.3)
        bpy.context.view_layer.update()
        matrix=obj.matrix_world.copy()
        cad.feature_set(dict(feature_id=f,enabled=False,**OWNER))
        self.assertTrue(obj.hide_viewport)
        cad.feature_set(dict(feature_id=f,enabled=True,depth=.03,**OWNER))
        self.assertFalse(obj.hide_viewport)
        self.assertLess(max(abs(obj.matrix_world[i][j]-matrix[i][j]) for i in range(4) for j in range(4)),1e-6)
        self.assertAlmostEqual(volume(obj),.08*.045*.03,places=10)

    def test_scene_scale_conversion(self):
        bpy.context.scene.unit_settings.scale_length=.001
        e=self.rect()
        self.extrude(e)
        self.assertAlmostEqual(volume(self.obj()),80*45*20,delta=.02)
        self.assertEqual(runtime.doc()['sketches'][0]['entities'][0]['width'],.08)

    def test_corrupt_cad_allows_escape_and_ordinary_edit(self):
        mode.mode_set(dict(mode='OBJECT',**OWNER))
        bpy.ops.mesh.primitive_cube_add()
        obj=bpy.context.view_layer.objects.active
        mode.mode_set(dict(mode='CAD',**OWNER))
        self.assertTrue(obj.hide_get())
        for raw in ('{broken', '{"version":99}'):
            bpy.context.scene[model.KEY]=raw
            mode.mode_set(dict(mode='OBJECT',**OWNER))
            self.assertFalse(runtime.workspace)
            self.assertFalse(obj.hide_get())
            mode.mode_set(dict(mode='EDIT',**OWNER))
            self.assertEqual(obj.mode,'EDIT')
            with self.assertRaises(CommandError) as error:
                mode.mode_set(dict(mode='CAD',**OWNER))
            self.assertEqual(error.exception.code,'cad_document_invalid')
            self.assertEqual(obj.mode,'EDIT')
            mode.mode_set(dict(mode='OBJECT',**OWNER))

    def test_document_validation(self):
        e=self.rect()
        self.extrude(e)
        doc=runtime.doc()
        self.assertEqual(model.loads(model.dumps(doc)),doc)
        for edit in (lambda d:d.update(version=99),
                     lambda d:d['sketches'][0]['entities'][0].update(width=-1),
                     lambda d:d['features'][0].update(profile_id='missing'),
                     lambda d:d['sketches'][0].update(id=d['id'])):
            bad=copy.deepcopy(doc)
            edit(bad)
            with self.assertRaises(CommandError):
                model.loads(json.dumps(bad))

    def test_edit_guard_and_convert(self):
        e=self.rect()
        f=self.extrude(e)
        obj=self.obj()
        bpy.context.view_layer.objects.active=obj
        obj.select_set(True)
        with self.assertRaises(CommandError):
            mode.mode_set(dict(mode='EDIT',**OWNER))
        cad.convert(dict(feature_id=f,**OWNER))
        self.assertIn(FEATURE_KEY,obj)
        self.assertEqual(runtime.doc()['features'][0]['id'],f)
        exported=bpy.context.view_layer.objects.active
        self.assertNotIn(FEATURE_KEY,exported)
        self.assertIsNot(exported.data,obj.data)
        mode.mode_set(dict(mode='EDIT',**OWNER))
        self.assertEqual(exported.mode,'EDIT')

    def test_z_save_reopen_recovers_stable_document_and_rebuild(self):
        e=self.rect()
        self.extrude(e)
        doc=runtime.doc()
        mode.mode_set(dict(mode='OBJECT',**OWNER))
        bpy.ops.mesh.primitive_cube_add()
        bpy.context.view_layer.objects.active.name='Saved unrelated'
        mode.mode_set(dict(mode='CAD',**OWNER))
        self.assertTrue(bpy.data.objects['Saved unrelated'].hide_get())
        from blender_tablet_remote.cad.lifecycle import register_handlers, unregister_handlers
        register_handlers()
        with tempfile.TemporaryDirectory() as folder:
            path=str(Path(folder)/'cad.blend')
            bpy.ops.wm.save_as_mainfile(filepath=path)
            self.assertTrue(bpy.data.objects['Saved unrelated'].hide_get())
            bpy.ops.wm.open_mainfile(filepath=path)
            self.assertFalse(bpy.data.objects['Saved unrelated'].hide_get())
            runtime.reset()
            self.assertEqual(runtime.doc(),doc)
            mode.mode_set(dict(mode='CAD',**OWNER))
            cad.entity_set(dict(entity_id=e,values={'width':.1},**OWNER))
            self.assertAlmostEqual(volume(self.obj()),.1*.045*.02,places=10)
        unregister_handlers()

    def test_isolation_preserves_existing_hidden_and_local_view(self):
        from blender_tablet_remote.commands import view
        mode.mode_set(dict(mode='OBJECT',**OWNER))
        bpy.ops.mesh.primitive_cube_add()
        visible=bpy.context.view_layer.objects.active
        visible.name='Unrelated'
        bpy.ops.mesh.primitive_cube_add()
        hidden=bpy.context.view_layer.objects.active
        hidden.name='Previously hidden'
        hidden.hide_set(True)
        view._local_hidden=['Previously hidden']
        mode.mode_set(dict(mode='CAD',**OWNER))
        self.assertTrue(visible.hide_get())
        self.assertTrue(hidden.hide_get())
        self.assertTrue(runtime.status()['isolated'])
        mode.mode_set(dict(mode='OBJECT',**OWNER))
        self.assertFalse(visible.hide_get())
        self.assertTrue(hidden.hide_get())
        self.assertEqual(view._local_hidden,['Previously hidden'])
        view._local_hidden=[]

    def test_save_visibility_context_and_owner_disconnect(self):
        from blender_tablet_remote import bridge
        mode.mode_set(dict(mode='OBJECT',**OWNER))
        bpy.ops.mesh.primitive_cube_add()
        obj=bpy.context.view_layer.objects.active
        mode.mode_set(dict(mode='CAD',**OWNER))
        self.assertTrue(obj.hide_get())
        with runtime.saving():
            self.assertFalse(obj.hide_get())
        self.assertTrue(obj.hide_get())
        bridge._handle(None,{'type':'_client_gone','client_id':'other'})
        self.assertTrue(runtime.workspace)
        bridge._handle(None,{'type':'_client_gone','client_id':'test'})
        self.assertFalse(runtime.workspace)
        self.assertFalse(obj.hide_get())

    @unittest.skipIf(bpy.app.background,'GUI viewport required')
    def test_enter_existing_document_frames_part_without_changing_pc_view(self):
        from blender_tablet_remote.bpy_utils import find_view3d
        from blender_tablet_remote.camera import camera
        self.rect()
        cad.sketch_finish(OWNER)
        mode.mode_set(dict(mode='OBJECT',**OWNER))
        camera.apply(location=(10,20,0),distance=40)
        rv3d=find_view3d()[3]
        original=(tuple(rv3d.view_location),tuple(rv3d.view_rotation),rv3d.view_distance,rv3d.view_perspective)
        mode.mode_set(dict(mode='CAD',**OWNER))
        self.assertIsNone(runtime.active_sketch_id)
        self.assertAlmostEqual(camera.location.x,.04,places=6)
        self.assertAlmostEqual(camera.location.y,.0225,places=6)
        self.assertLess(camera.distance,.3)
        camera.apply(location=(.01,.02,0),distance=.4)
        previous=camera.as_dict()
        mode.mode_set(dict(mode='CAD',**OWNER))
        self.assertEqual(camera.as_dict(),previous)
        self.assertEqual((tuple(rv3d.view_location),tuple(rv3d.view_rotation),rv3d.view_distance,rv3d.view_perspective),original)

    @unittest.skipIf(bpy.app.background,'GUI viewport required')
    def test_projection_roundtrip_and_overlay_follows_camera(self):
        from blender_tablet_remote.bpy_utils import find_view3d
        from blender_tablet_remote.camera import camera
        from blender_tablet_remote.cad.kernel import world
        e=self.rect()
        sketch=runtime.doc()['sketches'][0]
        rv3d=find_view3d()[3]
        for plane in model.PLANES:
            sketch['plane']=plane
            runtime.focus(sketch)
            p=camera.project(Vector(world(plane,.04,.0225)),rv3d)
            result=runtime.point(dict(u=p[0],v=p[1]),plane)
            self.assertAlmostEqual(result[0],.04,places=5)
            self.assertAlmostEqual(result[1],.0225,places=5)
        runtime.focus(runtime.doc()['sketches'][0])
        before=next(item for item in runtime.status()['overlay'] if item['id']==e)['points']
        camera.apply(location=(.03,.01,0))
        after=next(item for item in runtime.status()['overlay'] if item['id']==e)['points']
        self.assertNotEqual(before,after)
        self.assertEqual(runtime.doc()['sketches'][0]['entities'][0]['id'],e)

    @unittest.skipIf(bpy.app.background,'GUI undo stack required')
    def test_undo_after_leaving_cad_keeps_original_visibility(self):
        from blender_tablet_remote.commands import history
        mode.mode_set(dict(mode='OBJECT',**OWNER))
        bpy.ops.mesh.primitive_cube_add()
        bpy.context.view_layer.objects.active.name='Original cube'
        mode.mode_set(dict(mode='CAD',**OWNER))
        e=self.rect()
        self.extrude(e)
        mode.mode_set(dict(mode='OBJECT',**OWNER))
        self.assertFalse(bpy.data.objects['Original cube'].hide_get())
        history.undo({})
        self.assertFalse(runtime.workspace)
        self.assertFalse(bpy.data.objects['Original cube'].hide_get())

    @unittest.skipIf(bpy.app.background,'GUI undo stack required')
    def test_one_undo_reverts_confirmed_extrusion(self):
        from blender_tablet_remote.commands import history
        e=self.rect()
        self.extrude(e,confirm=False)
        cad.extrude_update(dict(depth=.03,**OWNER))
        cad.confirm(OWNER)
        history.undo({})
        self.assertFalse(runtime.doc()['features'])
        self.assertTrue(runtime.workspace)
        self.assertFalse(runtime.objects(runtime.doc()))
        history.redo({})
        self.assertEqual(len(runtime.doc()['features']),1)
        self.assertAlmostEqual(volume(self.obj()),.08*.045*.03,places=10)


def run():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CadTests))
    if not result.wasSuccessful():
        os._exit(1)
    if not bpy.app.background:
        bpy.ops.wm.quit_blender()

if __name__ == '__main__':
    if bpy.app.background:
        run()
    else:
        bpy.app.timers.register(run,first_interval=1)
