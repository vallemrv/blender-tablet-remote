"""Bodies own one evaluated object; previews reuse unchanged predecessors."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_cad import CadTests, OWNER, volume
from blender_tablet_remote.cad.runtime import runtime, BODY_KEY, FEATURE_KEY
from blender_tablet_remote.cad.kernel import kernel
from blender_tablet_remote.cad import document as model
from blender_tablet_remote.commands import cad, snap, history


class BodyEfficiencyTests(CadTests):
    def stacked(self):
        first=self.extrude(self.rect())
        obj=self.obj(); pointer=obj.as_pointer()
        cad.sketch_create(dict(support_id=first,**OWNER))
        second=self.extrude(self.draw('RECTANGLE',(.02,.01),(.06,.035)),.01)
        self.assertEqual(len(runtime.objects(runtime.doc())),1)
        self.assertEqual(self.obj().as_pointer(),pointer)
        self.assertAlmostEqual(volume(self.obj()),.08*.045*.02+.04*.025*.01,places=9)
        return first,second

    def test_extrude_cut_history_and_export_are_one_complete_body(self):
        first,second=self.stacked()
        cad.sketch_create(dict(support_id=second,**OWNER))
        hole=self.draw('RECTANGLE',(.03,.015),(.04,.025))
        cad.extrude_begin(dict(profile_id='profile_'+hole,depth=.03,operation='CUT',target_id=second,**OWNER))
        cad.confirm(OWNER)
        body=runtime.doc()['bodies'][0]['id']
        expected=.08*.045*.02+.04*.025*.01-.01*.01*.03
        self.assertAlmostEqual(volume(self.obj()),expected,places=9)
        self.assertEqual(self.obj()[BODY_KEY],body)
        cad.history_rollback(dict(node_id=first,**OWNER))
        self.assertAlmostEqual(volume(self.obj()),.08*.045*.02,places=9)
        cad.history_rollback(OWNER)
        self.assertAlmostEqual(volume(self.obj()),expected,places=9)
        doc=model.dumps(runtime.doc())
        cad.convert(dict(body_id=body,**OWNER))
        copy=bpy.context.view_layer.objects.active
        self.assertNotIn(FEATURE_KEY,copy);self.assertNotIn(BODY_KEY,copy)
        self.assertAlmostEqual(volume(copy),expected,places=9)
        self.assertEqual(model.dumps(runtime.doc()),doc)

    def test_other_body_stays_independent_and_new_sketch_does_not_rebuild_solids(self):
        first,second=self.stacked()
        original=self.obj(); mesh=original.data.as_pointer()
        with patch.object(kernel,'extrude',side_effect=AssertionError('unchanged extrusion')), \
             patch.object(kernel,'union',side_effect=AssertionError('unchanged union')), \
             patch.object(kernel,'cut',side_effect=AssertionError('unchanged cut')):
            cad.body_create(OWNER)
            cad.sketch_create(dict(plane='XY',**OWNER))
            circle=self.draw('CIRCLE',(0,0),(.004,0))
            self.assertEqual(original.data.as_pointer(),mesh)
        self.extrude(circle)
        self.assertEqual(len(runtime.objects(runtime.doc())),2)
        self.assertEqual(original.data.as_pointer(),mesh)

    def test_extrusion_on_a_boolean_top_fuses_despite_float_roundoff(self):
        import bmesh
        first=self.extrude(self.rect())
        cad.sketch_create(dict(support_id=first,**OWNER))
        hole=self.draw('RECTANGLE',(.01,.01),(.02,.02))
        state=cad.extrude_begin(dict(profile_id='profile_'+hole,depth=.02,operation='CUT',target_id=first,**OWNER))
        cut=state['selection']['id'];cad.confirm(OWNER)
        cad.sketch_create(dict(support_id=cut,**OWNER))
        self.extrude(self.draw('RECTANGLE',(.04,.01),(.06,.03)),.01)
        bm=bmesh.new();bm.from_mesh(self.obj().data)
        try:
            seen=set();pending=[next(iter(bm.verts))]
            while pending:
                vertex=pending.pop()
                if vertex in seen:continue
                seen.add(vertex);pending.extend(edge.other_vert(vertex) for edge in vertex.link_edges)
            self.assertEqual(len(seen),len(bm.verts))
            self.assertTrue(all(edge.is_manifold for edge in bm.edges))
        finally:bm.free()

    def test_rename_preserves_ids_mesh_and_one_undo(self):
        self.extrude(self.rect());before=runtime.doc();sketch=before['sketches'][0]['id']
        mesh=self.obj().data.as_pointer()
        with patch.object(runtime,'rebuild',side_effect=AssertionError('rename geometry')),patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            cad.sketch_rename(dict(sketch_id=sketch,name='Placa base',**OWNER));undo.assert_called_once()
        after=model.loads(model.dumps(runtime.doc()))
        self.assertEqual(after['sketches'][0]['id'],sketch)
        self.assertEqual(after['sketches'][0]['name'],'Placa base')
        self.assertEqual(after['features'],before['features'])
        self.assertEqual(self.obj().data.as_pointer(),mesh)

    def test_offset_plane_and_sketch_are_created_together(self):
        before=len(runtime.doc()['sketches'])
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            cad.plane_create(dict(base='XZ',translation=[0,0,.01],rotation=[0,0,0],start_sketch=True,**OWNER))
            undo.assert_called_once()
        doc=runtime.doc();sketch=doc['sketches'][-1]
        self.assertEqual(len(doc['sketches']),before+1)
        self.assertEqual(runtime.active_sketch_id,sketch['id'])
        self.assertEqual(sketch['plane_id'],doc['planes'][-1]['id'])
        self.assertAlmostEqual(model.frame(sketch)['origin'][1],-.01)

    def test_entering_legacy_document_consolidates_operation_objects(self):
        from blender_tablet_remote.commands import mode
        first,second=self.stacked()
        expected=volume(self.obj());before=model.dumps(runtime.doc())
        original=self.obj();del original[BODY_KEY];original[FEATURE_KEY]=first
        legacy=original.copy();legacy.data=original.data.copy();legacy[FEATURE_KEY]=second
        bpy.context.scene.collection.objects.link(legacy)
        self.assertEqual(len(runtime.objects(runtime.doc())),2)
        mode.mode_set(dict(mode='CAD',**OWNER))
        self.assertEqual(len(runtime.objects(runtime.doc())),1)
        self.assertEqual(self.obj()[FEATURE_KEY],second)
        self.assertAlmostEqual(volume(self.obj()),expected,places=9)
        self.assertEqual(model.dumps(runtime.doc()),before)

    @unittest.skipIf(bpy.app.background,'GPU context and native undo required')
    def test_surface_graph_measurements_and_gpu_batches_reuse_then_invalidate(self):
        from test_cad_surface import SurfaceTests
        from blender_tablet_remote.bpy_utils import find_view3d
        from blender_tablet_remote.streaming import cad_selection
        import gpu
        self.extrude(self.rect())
        SurfaceTests.pick(self,'FACE',(.04,.02,.02))
        obj=self.obj(); graph=snap._cad_mesh(obj)
        self.assertIs(snap._cad_mesh(obj),graph)
        from blender_tablet_remote.camera import camera
        from mathutils import Vector
        screen=camera.project(Vector((.04,.02,.02)),find_view3d()[3])
        self.assertIs(snap.query_cad_surface(dict(u=screen[0],v=screen[1]),'FACE'),runtime.surface.items[0])
        with patch('blender_tablet_remote.cad.surface.measurements',side_effect=AssertionError('same measurements')):
            runtime.surface.status();runtime.surface.status()
        offscreen=gpu.types.GPUOffScreen(512,512)
        try:
            with offscreen.bind():
                cad_selection.draw_cad_selection(find_view3d()[3],512,512)
                with patch.object(cad_selection,'batch_for_shader',side_effect=AssertionError('same GPU geometry')):
                    cad_selection.draw_cad_selection(find_view3d()[3],512,512)
        finally:offscreen.free()
        obj.data.vertices[0].co.x+=.001;obj.data.update();bpy.context.view_layer.update()
        self.assertIsNot(snap._cad_mesh(obj),graph)
        runtime.surface.validate();self.assertFalse(runtime.surface.items)

    @unittest.skipIf(bpy.app.background,'Native undo required')
    def test_one_undo_restores_previous_body_and_redo_restores_union(self):
        first,second=self.stacked()
        expected=volume(self.obj())
        history.undo({})
        self.assertEqual(len(runtime.objects(runtime.doc())),1)
        self.assertAlmostEqual(volume(self.obj()),.08*.045*.02,places=9)
        history.redo({})
        self.assertEqual(len(runtime.objects(runtime.doc())),1)
        self.assertAlmostEqual(volume(self.obj()),expected,places=9)


def run():
    suite=unittest.TestSuite(BodyEfficiencyTests(name) for name in BodyEfficiencyTests.__dict__ if name.startswith('test_'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        import os;os._exit(1)
    if not bpy.app.background:bpy.ops.wm.quit_blender()

if __name__=='__main__':
    if bpy.app.background:run()
    else:bpy.app.timers.register(run,first_interval=1.)
