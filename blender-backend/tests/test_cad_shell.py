"""Shells: captured openings, exact wall volumes and reversible tablet sessions."""
import copy
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import bpy
from mathutils import Vector, Matrix
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_cad import CadTests, OWNER, KERNEL, volume
from blender_tablet_remote.cad import document as model
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.cad.surface import stamp
from blender_tablet_remote.commands import cad, history
from blender_tablet_remote.errors import CommandError

occt_only=unittest.skipUnless(KERNEL=='OCCT','Shell requires OpenCascade')


class ShellTests(CadTests):
    def box(self):
        rectangle=self.draw('RECTANGLE',(0,0),(.04,.04))
        return rectangle,self.extrude(rectangle,depth=.04)

    def select_faces(self,*faces):
        obj=self.obj();runtime.surface.clear();runtime.surface.mode='FACE'
        scale=bpy.context.scene.unit_settings.scale_length
        transform=obj.matrix_world
        normals=transform.to_3x3().inverted().transposed()
        for index,(point,normal) in enumerate(faces):
            runtime.surface.items.append(dict(id=f'{obj.name}:FACE:{index}',kind='FACE',object=obj.name,feature_id=obj.get('btr_cad_feature_id'),
                planar=True,center=list(transform@(Vector(point)/scale)),normal=list((normals@Vector(normal)).normalized()),
                points=[list(transform@(Vector(point)/scale))],triangles=[],segments=[]))
        runtime.surface._stamps[obj.name]=stamp(obj)

    def top(self): self.select_faces(((.02,.02,.04),(0,0,1)))

    @occt_only
    def test_top_open_40mm_cube_has_exact_2mm_walls_and_one_undo(self):
        self.box();self.top();before=bpy.context.scene[model.KEY]
        with patch('blender_tablet_remote.commands.cad.undo_push') as undo:
            state=cad.shell_begin(OWNER)
            self.assertEqual(state['session']['operation'],'SHELL')
            self.assertAlmostEqual(state['session']['thickness'],.002)
            self.assertEqual(state['session']['side'],'INSIDE')
            self.assertEqual(state['session']['face_count'],1)
            self.assertTrue(state['session']['can_confirm'])
            self.assertEqual(bpy.context.scene[model.KEY],before)
            self.assertAlmostEqual(volume(self.obj()),.04**3-.036**2*.038,places=10)
            cad.confirm(OWNER);undo.assert_called_once()
        feature=runtime.doc()['features'][-1]
        self.assertIsNone(feature['sketch_id']);self.assertEqual(feature['type'],'SHELL')
        restored=model.loads(model.dumps(runtime.doc()));runtime.rebuild(restored)
        self.assertAlmostEqual(volume(self.obj()),.04**3-.036**2*.038,places=10)

    @occt_only
    def test_two_opposite_openings_and_post_confirmation_thickness_edit(self):
        self.box();self.select_faces(((.02,.02,0),(0,0,-1)),((.02,.02,.04),(0,0,1)))
        cad.shell_begin(OWNER);cad.confirm(OWNER)
        self.assertAlmostEqual(volume(self.obj()),(.04**2-.036**2)*.04,places=10)
        feature=runtime.doc()['features'][-1]
        cad.feature_set(dict(feature_id=feature['id'],thickness=.003,**OWNER))
        self.assertAlmostEqual(volume(self.obj()),(.04**2-.034**2)*.04,places=10)

    @occt_only
    def test_impossible_thickness_keeps_controls_and_never_confirms_old_candidate(self):
        self.box();self.top();before=bpy.context.scene[model.KEY]
        state=cad.shell_begin(dict(thickness=.05,**OWNER))
        self.assertTrue(state['session']['active']);self.assertFalse(state['session']['can_confirm'])
        self.assertTrue(state['error']);self.assertAlmostEqual(state['session']['thickness'],.05)
        with patch('blender_tablet_remote.commands.cad.undo_push') as undo:
            cad.confirm(OWNER);undo.assert_not_called()
        self.assertIsNotNone(runtime.session)
        self.assertEqual(bpy.context.scene[model.KEY],before)
        state=cad.shell_update(dict(thickness=.002,**OWNER));self.assertTrue(state['session']['can_confirm'])
        for thickness in (.02,.025,.05):
            state=cad.shell_update(dict(thickness=thickness,**OWNER));self.assertFalse(state['session']['can_confirm'])
        cad.cancel(OWNER)
        self.assertEqual(bpy.context.scene[model.KEY],before)
        self.assertAlmostEqual(volume(self.obj()),.04**3,places=10)

    @occt_only
    def test_base_height_change_follows_unique_parallel_face_and_missing_face_is_atomic(self):
        rectangle,base=self.box();self.top()
        cad.shell_begin(OWNER);cad.confirm(OWNER)
        cad.feature_set(dict(feature_id=base,depth=.06,**OWNER))
        self.assertAlmostEqual(volume(self.obj()),.04*.04*.06-.036*.036*.058,places=10)
        before=bpy.context.scene[model.KEY]
        with self.assertRaises(CommandError) as error:
            cad.entity_set(dict(entity_id=rectangle,values={'width':.01},**OWNER))
        self.assertEqual(error.exception.code,'cad_reference_missing')
        self.assertEqual(bpy.context.scene[model.KEY],before)
        with self.assertRaises(CommandError):cad.feature_delete(dict(feature_id=base,**OWNER))
        self.assertEqual(bpy.context.scene[model.KEY],before)

    @occt_only
    def test_outside_preserves_inner_volume_and_switching_rebuilds_from_baseline(self):
        self.box();self.top()
        cad.shell_begin(OWNER)
        baseline=volume(self.obj())
        cad.shell_update(dict(side='OUTSIDE',**OWNER))
        obj=self.obj()
        coordinates=[tuple(v.co) for v in obj.data.vertices]
        for axis in (0,1):
            self.assertAlmostEqual(min(p[axis] for p in coordinates),-.002,places=7)
            self.assertAlmostEqual(max(p[axis] for p in coordinates),.042,places=7)
        self.assertGreater(volume(obj),baseline)
        cad.shell_update(dict(side='INSIDE',**OWNER))
        self.assertAlmostEqual(volume(self.obj()),baseline,places=10)
        runtime.increment=True;runtime.step=.001
        cad.shell_update(dict(gesture=.08,baseline_thickness=.002,**OWNER))
        self.assertAlmostEqual(runtime.session['thickness'],.004)
        cad.shell_update(dict(thickness=.002,**OWNER));cad.confirm(OWNER)
        feature=runtime.doc()['features'][-1]
        cad.feature_set(dict(feature_id=feature['id'],side='OUTSIDE',**OWNER))
        self.assertEqual(runtime.doc()['features'][-1]['side'],'OUTSIDE')

    def test_selection_capture_uses_document_metres_after_object_transform(self):
        self.box();obj=self.obj()
        obj.matrix_world=Matrix.Translation((.3,-.1,.4))@Matrix.Rotation(.7,4,'Y')@Matrix.Diagonal((2.,.5,1.5,1.))
        bpy.context.view_layer.update();self.top()
        body,faces=cad._shell_faces()
        for a,b in zip(faces[0]['origin'],(.02,.02,.04)):self.assertAlmostEqual(a,b,places=7)
        for a,b in zip(faces[0]['normal'],(0,0,1)):self.assertAlmostEqual(a,b,places=7)
        self.assertEqual(body,runtime.doc()['bodies'][0]['id'])
        runtime.surface.items[0]['planar']=False
        with self.assertRaises(CommandError):cad.shell_begin(OWNER)
        self.assertIsNone(runtime.session)

    def test_same_body_faces_accumulate_and_tapping_again_removes_face(self):
        self.box();obj=self.obj();runtime.surface.mode='FACE'
        items=[dict(id=f'{obj.name}:FACE:{i}',kind='FACE',object=obj.name,feature_id=obj.get('btr_cad_feature_id'),
                    planar=True,center=[0,0,0],normal=[0,0,1],points=[],triangles=[],segments=[]) for i in range(3)]
        with patch('blender_tablet_remote.commands.snap.query_cad_surface',side_effect=items):
            for _ in items:runtime.surface.select(dict(u=.5,v=.5))
        self.assertEqual(len(runtime.surface.items),3)
        with patch('blender_tablet_remote.commands.snap.query_cad_surface',return_value=items[1]):
            runtime.surface.select(dict(u=.5,v=.5))
        self.assertEqual(len(runtime.surface.items),2)

    @occt_only
    def test_save_and_disconnect_restore_baseline_and_discard_pending_shell(self):
        import tempfile
        from blender_tablet_remote import bridge
        from blender_tablet_remote.commands import file as files
        self.box();self.top();before=model.dumps(runtime.doc())
        cad.shell_begin(OWNER)
        bridge._handle(None,dict(type='_client_gone',client_id=OWNER['_client_id']))
        self.assertIsNone(runtime.session)
        self.assertEqual(model.dumps(runtime.doc()),before)
        self.assertAlmostEqual(volume(self.obj()),.04**3,places=10)
        from blender_tablet_remote.commands import mode
        mode.mode_set(dict(mode='CAD',**OWNER));self.top();cad.shell_begin(OWNER)
        with tempfile.TemporaryDirectory() as folder:
            files.save_as(dict(path=str(Path(folder)/'saved.blend')))
        self.assertIsNone(runtime.session)
        self.assertEqual(model.dumps(runtime.doc()),before)
        self.assertAlmostEqual(volume(self.obj()),.04**3,places=10)

    @occt_only
    def test_shell_inserts_at_rollback_and_keeps_future_operations(self):
        rectangle,base=self.box()
        cad.sketch_create(dict(plane='XY',offset=.04,**OWNER))
        boss=self.extrude(self.draw('RECTANGLE',(0,0),(.01,.01)),depth=.01)
        cad.history_rollback(dict(node_id=base,**OWNER));self.top()
        state=cad.shell_begin(OWNER);shell=state['selection']['id']
        cad.confirm(OWNER)
        sequence=[n['id'] for n in model.history(runtime.doc())]
        self.assertEqual(sequence.index(shell),sequence.index(base)+1)
        self.assertEqual(runtime.rollback_id,shell)
        with self.assertRaises(CommandError):cad.feature_set(dict(feature_id=boss,depth=.02,**OWNER))
        cad.history_rollback(OWNER)
        self.assertEqual(runtime.doc()['features'][-1]['id'],shell) # order, not array position, owns the stack
        self.assertGreater(volume(self.obj()),.04**3-.036**2*.038)
        with self.assertRaises(CommandError):cad.sketch_create(dict(support_id=shell,**OWNER))

    @unittest.skipUnless(KERNEL!='OCCT','Native rejection only')
    def test_native_rejects_shell_without_preview_or_document_change(self):
        self.box();self.top();before=bpy.context.scene[model.KEY]
        with self.assertRaises(CommandError) as error:cad.shell_begin(OWNER)
        self.assertEqual(error.exception.code,'cad_kernel_unsupported')
        self.assertIsNone(runtime.session);self.assertEqual(bpy.context.scene[model.KEY],before)
        doc=runtime.doc();doc['features'].append(dict(id=model.uid('feature'),type='SHELL',name='Carcasa',order=model.next_order(doc),
            body_id=doc['bodies'][0]['id'],sketch_id=None,enabled=True,thickness=.002,side='INSIDE',faces=[dict(origin=[.02,.02,.04],normal=[0,0,1])]))
        with self.assertRaises(CommandError) as error:runtime.rebuild(model.loads(model.dumps(doc)))
        self.assertEqual(error.exception.code,'cad_kernel_unsupported')

    @occt_only
    @unittest.skipIf(bpy.app.background,'GUI undo stack required')
    def test_native_undo_redo_restore_shell(self):
        self.box();self.top();cad.shell_begin(OWNER);cad.confirm(OWNER)
        history.undo({});self.assertEqual(len(runtime.doc()['features']),1)
        self.assertAlmostEqual(volume(self.obj()),.04**3,places=10)
        history.redo({});self.assertEqual(runtime.doc()['features'][-1]['type'],'SHELL')
        self.assertAlmostEqual(volume(self.obj()),.04**3-.036**2*.038,places=10)


def run():
    suite=unittest.TestSuite(ShellTests(n) for n in ShellTests.__dict__ if n.startswith('test_'))
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():os._exit(1)
    if not bpy.app.background:bpy.ops.wm.quit_blender()

if __name__=='__main__':
    if bpy.app.background:run()
    else:bpy.app.timers.register(run,first_interval=1.)
