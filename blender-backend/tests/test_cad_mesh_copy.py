"""CAD copies are independent Blender meshes usable by native Edit and Sculpt."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import bpy
import bmesh
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_cad import CadTests, OWNER
from blender_tablet_remote.cad import document as model
from blender_tablet_remote.cad.runtime import runtime, FEATURE_KEY, DOC_KEY, BODY_KEY, COPY_SOURCE_KEY
from blender_tablet_remote.commands import cad, objects, mode, mesh, modifiers


class MeshCopyTests(CadTests):
    def body(self):
        feature=self.extrude(self.rect())
        obj=self.obj();bpy.context.view_layer.objects.active=obj;obj.select_set(True)
        bevel=obj.modifiers.new('Bevel','BEVEL');bevel.width=.001;bevel.segments=3
        return obj,feature

    def assert_independent(self,original,copy):
        self.assertNotEqual(original.as_pointer(),copy.as_pointer())
        self.assertNotEqual(original.data.as_pointer(),copy.data.as_pointer())
        for key in (FEATURE_KEY,DOC_KEY,BODY_KEY,COPY_SOURCE_KEY): self.assertNotIn(key,copy)
        self.assertEqual(copy.modifiers[0].type,'BEVEL')
        self.assertEqual(copy.modifiers[0].segments,3)
        self.assertTrue(original.hide_get())
        self.assertFalse(copy.hide_get())
        self.assertTrue(copy.select_get())
        self.assertFalse(runtime.workspace)

    def test_duplicate_cad_body_is_editable_even_if_linked_was_requested(self):
        original,_=self.body();before=model.dumps(runtime.doc())
        mode.mode_set(dict(mode='OBJECT',**OWNER))
        with patch.object(objects,'undo_push') as undo:
            result=objects.duplicate(dict(linked=True));undo.assert_called_once()
        copy=bpy.context.view_layer.objects.active
        self.assertEqual(result['created'],[copy.name])
        self.assert_independent(original,copy)
        mode.mode_set(dict(mode='EDIT',**OWNER))
        bm=bmesh.from_edit_mesh(copy.data);bm.verts.ensure_lookup_table();bm.verts[0].co.x+=.01
        bmesh.update_edit_mesh(copy.data)
        mode.mode_set(dict(mode='OBJECT',**OWNER))
        self.assertNotEqual(copy.data.vertices[0].co.x,original.data.vertices[0].co.x)
        copy.modifiers[0].width=.003
        self.assertAlmostEqual(original.modifiers[0].width,.001)
        self.assertEqual(model.dumps(runtime.doc()),before)

    def test_convert_and_reenter_cad_restore_the_right_visible_model(self):
        original,feature=self.body();before=model.dumps(runtime.doc())
        with patch.object(cad,'undo_push') as undo:
            cad.convert(dict(feature_id=feature,**OWNER));undo.assert_called_once()
        copy=bpy.context.view_layer.objects.active
        self.assert_independent(original,copy)
        mode.mode_set(dict(mode='CAD',**OWNER))
        self.assertFalse(original.hide_get());self.assertTrue(copy.hide_get())
        with runtime.saving():
            self.assertTrue(original.hide_get());self.assertFalse(copy.hide_get())
        self.assertFalse(original.hide_get());self.assertTrue(copy.hide_get())
        mode.mode_set(dict(mode='OBJECT',**OWNER))
        self.assertTrue(original.hide_get());self.assertFalse(copy.hide_get())
        self.assertEqual(model.dumps(runtime.doc()),before)

    def test_normal_linked_duplicate_keeps_native_linked_behavior(self):
        mode.mode_set(dict(mode='OBJECT',**OWNER))
        bpy.ops.mesh.primitive_cube_add()
        original=bpy.context.object
        objects.duplicate(dict(linked=True));copy=bpy.context.object
        self.assertEqual(copy.data.as_pointer(),original.data.as_pointer())
        self.assertFalse(original.hide_get())

    def test_mesh_copy_can_bevel_selected_face_or_edge_and_whole_object(self):
        for selection in ('FACE','EDGE'):
            self.setUp()
            original,feature=self.body();before=model.dumps(runtime.doc())
            cad.convert(dict(feature_id=feature,**OWNER));copy=bpy.context.object
            # The copied modifier is still parametrically adjustable on the mesh.
            modifiers.set_params(dict(name='Bevel',parameters={'width':.002,'segments':4}))
            self.assertAlmostEqual(copy.modifiers[0].width,.002)
            self.assertAlmostEqual(original.modifiers[0].width,.001)
            mode.mode_set(dict(mode='EDIT',**OWNER))
            bm=bmesh.from_edit_mesh(copy.data)
            for face in bm.faces:face.select_set(False)
            for edge in bm.edges:edge.select_set(False)
            for vert in bm.verts:vert.select_set(False)
            bpy.context.tool_settings.mesh_select_mode=(False,selection=='EDGE',selection=='FACE')
            bm.select_mode={selection}
            if selection=='FACE':next(iter(bm.faces)).select_set(True)
            else:next(iter(bm.edges)).select_set(True)
            bm.select_flush_mode();bmesh.update_edit_mesh(copy.data)
            with patch.object(mesh,'undo_push') as undo:
                result=mesh.bevel(dict(offset=.001,segments=3));undo.assert_called_once()
            self.assertGreater(result['new_faces'],0)
            self.assertEqual(model.dumps(runtime.doc()),before)
            self.assertEqual(len(original.data.polygons),6)
            mode.mode_set(dict(mode='OBJECT',**OWNER))

    @unittest.skipIf(bpy.app.background,'Native sculpt requires a viewport')
    def test_copy_enters_native_sculpt(self):
        original,feature=self.body()
        cad.convert(dict(feature_id=feature,**OWNER));copy=bpy.context.object
        state=mode.mode_set(dict(mode='SCULPT',**OWNER))
        self.assertEqual(state['mode'],'SCULPT')
        self.assertEqual(copy.mode,'SCULPT')
        self.assertIn(FEATURE_KEY,original)
        mode.mode_set(dict(mode='OBJECT',**OWNER))

    @unittest.skipIf(bpy.app.background,'Native undo requires a viewport')
    def test_duplicate_is_one_undo_including_source_visibility(self):
        from blender_tablet_remote.commands import history
        from blender_tablet_remote.bpy_utils import undo_push
        original,_=self.body();name=original.name
        mode.mode_set(dict(mode='OBJECT',**OWNER));undo_push('Before mesh copy')
        result=objects.duplicate({});copy_name=result['created'][0]
        self.assertTrue(bpy.data.objects[name].hide_get())
        history.undo({})
        self.assertIsNone(bpy.data.objects.get(copy_name))
        self.assertFalse(bpy.data.objects[name].hide_get())
        self.assertNotIn(COPY_SOURCE_KEY,bpy.data.objects[name])


def run():
    suite=unittest.TestSuite(MeshCopyTests(name) for name in MeshCopyTests.__dict__ if name.startswith('test_'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        import os;os._exit(1)
    if not bpy.app.background:bpy.ops.wm.quit_blender()

if __name__=='__main__':
    if bpy.app.background:run()
    else:bpy.app.timers.register(run,first_interval=1.)
