"""GUI: blender --factory-startup --python this_file. CAD requires installed OCP."""
import sys
import math
import unittest
from pathlib import Path
import bpy
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_cad import CadTests, OWNER
from blender_tablet_remote.cad import document as model
from blender_tablet_remote.cad.sketch_mesh import wire_geometry
from blender_tablet_remote.cad.runtime import runtime, DOC_KEY, FEATURE_KEY
from blender_tablet_remote.cad.kernel import world
from blender_tablet_remote.commands import cad, mode, history
from blender_tablet_remote.errors import CommandError
from blender_tablet_remote.bpy_utils import undo_push

class SketchMeshTests(CadTests):
    def export(self, **values):
        sketch=runtime.doc()['sketches'][0]
        return cad.sketch_to_mesh(dict(sketch_id=sketch['id'],**values,**OWNER))
    def test_wire_circle_is_closed_editable_and_preserves_document(self):
        entity=self.draw('CIRCLE',(.1,.2),(.13,.2))
        before=model.dumps(runtime.doc())
        self.export(entity_ids=[entity],vertices_per_circle=64)
        obj=bpy.context.object
        self.assertEqual((len(obj.data.vertices),len(obj.data.edges),len(obj.data.polygons)),(64,64,0))
        for vertex in obj.data.vertices:self.assertAlmostEqual((vertex.co-Vector((.1,.2,0))).length,.03,places=6)
        self.assertEqual(model.dumps(runtime.doc()),before)
        self.assertNotIn(DOC_KEY,obj);self.assertNotIn(FEATURE_KEY,obj)
        self.assertFalse(runtime.workspace)
        mode.mode_set(dict(mode='EDIT',**OWNER));self.assertEqual(obj.mode,'EDIT')
    def test_wire_lines_rectangles_and_polygons_keep_their_points(self):
        entities=[dict(type='LINE',x=0,y=0,x2=1,y2=0),dict(type='RECTANGLE',x=2,y=0,width=1,height=1),
                  dict(type='NGON',x=5,y=0,flats=1,angle=0,sides=5)]
        first=wire_geometry(entities,32);second=wire_geometry(entities,4096)
        self.assertEqual(first,second)
        self.assertEqual((len(first[0]),len(first[1])),(11,10))
    def test_wire_arc_preserves_endpoints_and_shares_connected_line_endpoint(self):
        entities=[dict(type='ARC',x=0,y=0,radius=1,start=0,sweep=90),dict(type='LINE',x=1,y=0,x2=2,y2=0)]
        vertices,edges=wire_geometry(entities,64)
        self.assertEqual((len(vertices),len(edges)),(18,17))
        self.assertIn((1.0,0.0,0.0),vertices)
        self.assertAlmostEqual(vertices[16][0],0,places=12);self.assertAlmostEqual(vertices[16][1],1,places=12)
    def test_wire_partial_export_omits_other_figures_and_matches_rotated_plane_in_mm(self):
        entity=self.rect();self.draw('CIRCLE',(.2,0),(.21,0))
        doc=runtime.doc();sketch=doc['sketches'][0];sketch.update(plane='XZ',offset=.012)
        runtime.persist(doc)
        bpy.context.scene.unit_settings.scale_length=.001
        self.export(entity_ids=[entity],vertices_per_circle=128)
        obj=bpy.context.object
        self.assertEqual((len(obj.data.vertices),len(obj.data.edges),len(obj.data.polygons)),(4,4,0))
        expected=[Vector(world(sketch,*p))/.001 for p in model.outline(sketch['entities'][0])]
        for actual,wanted in zip(obj.data.vertices,expected):self.assertLess((obj.matrix_world@actual.co-wanted).length,1e-4)
    def test_wire_exported_profile_can_be_used_by_native_spin(self):
        from blender_tablet_remote.commands import tools
        self.draw('LINE',(.02,0),(.02,.04))
        before=model.dumps(runtime.doc());self.export()
        mode.mode_set(dict(mode='EDIT',**OWNER));bpy.ops.mesh.select_all(action='SELECT')
        bpy.context.scene.cursor.location=(0,0,0)
        result=tools.begin(dict(tool='REVOLVE',parameters=dict(angle=360,steps=16,axis='Y'),**OWNER))
        self.assertTrue(result['active'])
        import bmesh
        self.assertEqual(len(bmesh.from_edit_mesh(bpy.context.object.data).faces),16)
        tools.confirm(OWNER)
        self.assertEqual(model.dumps(runtime.doc()),before)

    def test_wire_invalid_request_is_atomic(self):
        self.rect();before=model.dumps(runtime.doc());count=len(bpy.data.objects)
        for values in (dict(vertices_per_circle=2),dict(vertices_per_circle=True),dict(entity_ids=[]),dict(entity_ids=['missing']),dict(revision=9999)):
            with self.assertRaises(CommandError):self.export(**values)
            self.assertEqual(len(bpy.data.objects),count);self.assertEqual(model.dumps(runtime.doc()),before)
            self.assertTrue(runtime.workspace)
    def test_wire_profile_expands_original_chain_members(self):
        for a,b in (((0,0),(1,0)),((1,0),(1,1)),((1,1),(0,1)),((0,1),(0,0))):self.draw('LINE',a,b)
        sketch=runtime.doc()['sketches'][0];profile=model.profiles(sketch)[0]
        self.assertEqual(len(profile['entity_ids']),4)
        self.export(profile_ids=[profile['id']],vertices_per_circle=128)
        self.assertEqual((len(bpy.context.object.data.vertices),len(bpy.context.object.data.edges)),(4,4))
    def test_wire_preview_blocks_conversion(self):
        self.extrude(self.rect(),confirm=False)
        count=len(bpy.data.objects)
        with self.assertRaises(CommandError):self.export()
        self.assertEqual(len(bpy.data.objects),count);self.assertIsNotNone(runtime.session)
    @unittest.skipIf(bpy.app.background,'Native undo requires GUI')
    def test_wire_undo_removes_only_copy(self):
        self.rect();before=model.dumps(runtime.doc());undo_push('Before drawing copy')
        self.export();name=bpy.context.object.name
        history.undo({});self.assertNotIn(name,bpy.data.objects)
        self.assertEqual(model.dumps(runtime.doc()),before)
        history.redo({});self.assertIn(name,bpy.data.objects)

def run():
    suite=unittest.TestSuite(SketchMeshTests(name) for name in SketchMeshTests.__dict__ if name.startswith('test_wire'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        import os
        sys.stdout.flush();sys.stderr.flush();os._exit(1)
    if not bpy.app.background:bpy.ops.wm.quit_blender()
if bpy.app.background:run()
else:bpy.app.timers.register(run,first_interval=1)
