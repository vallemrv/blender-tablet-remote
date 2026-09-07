"""Alineación por caras: ejecutar con Blender --factory-startup, opcional -- --gpu."""
import math
import sys
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

import bpy
from mathutils import Vector, Matrix, Quaternion

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import alignment, tools, modal, sessions
from blender_tablet_remote.errors import CommandError, BadPayload


def face(obj, index):
    polygon = obj.data.polygons[index]
    return dict(object=obj.name, element=index, center=list(polygon.center), normal=list(polygon.normal),
                vertices=[list(obj.data.vertices[i].co) for i in polygon.vertices],
                position=list(obj.matrix_world @ polygon.center), snap_type='FACE', id=f'{obj.name}:FACE:{index}')


class AlignmentTests(unittest.TestCase):
    def setUp(self):
        sessions.cancel_all()
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add(location=(-.517063,-.016835,3.276941))
        self.source = bpy.context.object
        self.source.name = 'Source'
        self.source.rotation_euler = (.015885,.855982,-.013324)
        bpy.ops.mesh.primitive_cube_add(location=(-4,0,0))
        self.target = bpy.context.object
        self.target.name = 'Target'
        self.target.rotation_euler = (0,math.radians(50),0)
        bpy.context.view_layer.objects.active = self.source
        bpy.context.view_layer.update()
        self.baseline = self.source.matrix_world.copy()
        self.target_base = self.target.matrix_world.copy()

    def tearDown(self):
        sessions.cancel_all()

    def assertMatrix(self, a, b):
        self.assertLess(max(abs(a[i][j]-b[i][j]) for i in range(4) for j in range(4)), 2e-5)

    def begin(self):
        return tools.begin(dict(tool='ALIGN',parameters={'object':'Source'},_client_id='owner'))

    def pick(self, obj, index, role, phase='TAP'):
        with patch.object(alignment,'query_face_frame',return_value=face(obj,index)):
            return tools.face_pick(dict(role=role,phase=phase,_client_id='owner'))

    def ready(self):
        self.begin()
        self.pick(self.source,0,'SOURCE')
        return self.pick(self.target,1,'TARGET')

    def test_all_cube_face_pairs_contact_preserve_size(self):
        for a in range(6):
            for b in range(6):
                for twist in ('0','90','180','270'):
                    sf,tf = face(self.source,a),face(self.target,b)
                    params = alignment.parameters({'twist':twist})
                    result = alignment.aligned_matrix(self.baseline,sf,tf,self.target_base,params)
                    sc,sn,_,_ = alignment.face_world(sf,result)
                    tc,tn,_,_ = alignment.face_world(tf,self.target_base)
                    self.assertLess((sc-tc).length,2e-5)
                    self.assertLess((sn+tn).length,2e-5)
                    self.assertMatrix((result.to_3x3().transposed() @ result.to_3x3()).to_4x4(),
                                      (self.baseline.to_3x3().transposed() @ self.baseline.to_3x3()).to_4x4())

    def test_preview_parameters_do_not_accumulate_and_cancel_restores(self):
        status = self.ready()
        self.assertTrue(status['can_confirm'])
        initial = self.source.matrix_world.copy()
        for gap in (1.0,.5,2.0,0.0):
            tools.parameter(dict(parameters={'gap':gap},_client_id='owner'))
            sc,sn,_,_ = alignment.face_world(tools.tool_session.alignment.source,self.source.matrix_world)
            tc,tn,_,_ = alignment.face_world(tools.tool_session.alignment.target,self.target.matrix_world)
            self.assertLess((sc-tc-tn*gap).length,2e-5)
        self.assertMatrix(self.source.matrix_world,initial)
        self.assertMatrix(self.target.matrix_world,self.target_base)
        tools.cancel(dict(_client_id='owner'))
        self.assertMatrix(self.source.matrix_world,self.baseline)

    def test_copy_rotation_and_orient_keep_origin(self):
        self.ready()
        for mode in ('ORIENT','COPY_ROTATION'):
            tools.parameter(dict(parameters={'mode':mode},_client_id='owner'))
            self.assertLess((self.source.matrix_world.translation-self.baseline.translation).length,1e-5)
        self.assertAlmostEqual(abs(self.source.matrix_world.to_quaternion().dot(self.target.matrix_world.to_quaternion())),1,places=5)

    def test_release_uses_candidate_without_second_probe(self):
        self.begin()
        self.pick(self.source,0,'SOURCE',phase='UPDATE')
        with patch.object(alignment,'query_face_frame',side_effect=AssertionError('release probed')):
            tools.face_pick(dict(role='SOURCE',phase='END',u=.9,v=.9,_client_id='owner'))
        self.assertEqual(tools.tool_session.alignment.source['element'],0)
        self.assertEqual(tools.tool_session.params['pick_role'],'TARGET')

    def test_empty_release_and_navigation_cancel_do_not_pick(self):
        self.begin()
        tools.face_pick(dict(role='SOURCE',phase='END',_client_id='owner'))
        self.assertIsNone(tools.tool_session.alignment.source)
        self.pick(self.source,0,'SOURCE',phase='UPDATE')
        tools.face_pick(dict(role='SOURCE',phase='CANCEL',_client_id='owner'))
        self.assertIsNone(tools.tool_session.alignment.source)
        self.assertIsNone(tools.tool_session.alignment.candidate)

    def test_confirm_requires_faces_and_pushes_only_once(self):
        self.begin()
        with self.assertRaises(CommandError): tools.confirm(dict(_client_id='owner'))
        self.pick(self.source,0,'SOURCE')
        self.pick(self.target,1,'TARGET')
        with patch.object(tools,'undo_push') as undo:
            tools.parameter(dict(parameters={'gap':.5},_client_id='owner'))
            result=tools.confirm(dict(_client_id='owner'))
            undo.assert_called_once()
        self.assertEqual(result['phase'],'CONFIRMED')
        self.assertFalse(tools.tool_session.active)

    def test_foreign_owner_cannot_pick_cancel_or_replace(self):
        self.ready()
        for command,payload in ((tools.face_pick,{'phase':'TAP'}),(tools.cancel,{}),
                                (tools.begin,{'tool':'ALIGN','parameters':{}})):
            with self.assertRaises(CommandError): command(dict(payload,_client_id='other'))
        self.assertTrue(tools.tool_session.active)

    def test_target_deleted_invalidates_and_restores_source(self):
        self.ready()
        bpy.data.objects.remove(self.target,do_unlink=True)
        self.assertFalse(tools.tool_session.status()['active'])
        self.assertMatrix(self.source.matrix_world,self.baseline)

    def test_disconnect_and_new_transform_restore_source(self):
        self.ready()
        tools.tool_session.owner_disconnected('owner')
        self.assertMatrix(self.source.matrix_world,self.baseline)
        self.ready()
        modal.begin(dict(mode='ROTATE',axes=['Z'],_client_id='owner'))
        self.assertFalse(tools.tool_session.active)
        self.assertTrue(modal.session.active)
        self.assertMatrix(self.source.matrix_world,self.baseline)

    def test_invalid_parameters_leave_previous_preview(self):
        self.ready()
        current=self.source.matrix_world.copy()
        for value in (float('nan'),-1,'bad'):
            with self.assertRaises(BadPayload): tools.parameter(dict(parameters={'gap':value},_client_id='owner'))
            self.assertMatrix(self.source.matrix_world,current)

    def test_face_probe_uses_the_visible_evaluated_face(self):
        from blender_tablet_remote.commands import snap
        from blender_tablet_remote.camera import camera
        camera.reset()
        camera._synced=True
        camera.location=Vector((0,0,0))
        camera.distance=10
        camera.rotation=Quaternion((1,0,0,0))
        camera.perspective='PERSP'
        rv3d=SimpleNamespace(window_matrix=Matrix(((1,0,0,0),(0,2,0,0),(0,0,-1,-.02),(0,0,-1,0))))
        region=SimpleNamespace(width=1000,height=500)
        for obj in (self.source,self.target):
            polygon=max(obj.data.polygons,key=lambda f:(obj.matrix_world.to_3x3() @ f.normal).z)
            screen=camera.project(obj.matrix_world @ polygon.center,rv3d)
            with patch.object(snap,'find_view3d',return_value=(None,None,region,rv3d)):
                hit=snap.query_face_frame(dict(u=screen[0],v=screen[1],include_objects=[obj.name]))
            self.assertEqual(hit['object'],obj.name)
            self.assertEqual(hit['element'],polygon.index)
            self.assertEqual(len(hit['vertices']),4)

    @unittest.skipUnless('--gpu' in sys.argv,'requires GPU capture')
    def test_capture_draws_alignment_faces_and_independent_markers(self):
        from blender_tablet_remote.streaming.capture import ViewportCapture
        from blender_tablet_remote.streaming.frames import FrameBuffer
        from blender_tablet_remote.camera import camera
        self.ready()
        camera.reset()
        capture=ViewportCapture(FrameBuffer())
        frames=[]
        capture.encoder=SimpleNamespace(ensure=lambda *a:True,submit=frames.append,stop=lambda:None)
        try:
            self.assertTrue(capture._grab_offscreen())
            rgb=list(zip(frames[0][0::4],frames[0][1::4],frames[0][2::4]))
            self.assertGreater(sum(r>180 and g>120 and b<120 for r,g,b in rgb),5)
            self.assertGreater(sum(b>180 and g>120 and r<160 for r,g,b in rgb),5)
            camera.orbit(.1,.05,1.0)
            self.assertTrue(capture._grab_offscreen())
            self.assertNotEqual(frames[0],frames[1])
            self.assertMatrix(self.target.matrix_world,self.target_base)
        finally:
            capture.shutdown()

    @unittest.skipUnless('--gpu' in sys.argv,'requires UI undo stack')
    def test_one_undo_restores_baseline_and_redo_alignment(self):
        from blender_tablet_remote.commands import history
        bpy.ops.ed.undo_push(message='Alignment test baseline')
        self.ready()
        placed=self.source.matrix_world.copy()
        tools.confirm(dict(_client_id='owner'))
        history.undo({})
        self.assertMatrix(bpy.data.objects['Source'].matrix_world,self.baseline)
        history.redo({})
        self.assertMatrix(bpy.data.objects['Source'].matrix_world,placed)


def run():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(AlignmentTests))
    if not result.wasSuccessful():
        if '--gpu' in sys.argv:
            import os
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(1)
        raise RuntimeError('Alignment regression tests failed')
    if '--gpu' in sys.argv: bpy.ops.wm.quit_blender()

if '--gpu' in sys.argv: bpy.app.timers.register(run,first_interval=1.0)
else: run()
