"""blender -b --factory-startup --python-exit-code 1 --python this_file."""
import sys
import tempfile
import unittest
from pathlib import Path
import bpy
import bmesh
from mathutils import Vector
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import units, tools, file


class DetailDimensionsTests(unittest.TestCase):
    def setUp(self):
        tools.tool_session.close()
        if bpy.context.object and bpy.context.object.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)

    def cube(self, conversion, object_scale=1):
        bpy.context.scene.unit_settings.scale_length = conversion
        units.apply_scale('SMALL')
        bpy.ops.mesh.primitive_cube_add(size=.001 / conversion / object_scale)
        bpy.context.object.scale = (object_scale,)*3
        bpy.context.view_layer.update()
        return bpy.context.object

    def test_one_mm_tool_step_and_initial_width_are_physical(self):
        for conversion in (.001,1,10):
            self.setUp()
            obj = self.cube(conversion, 2)
            bpy.ops.object.mode_set(mode='EDIT')
            self.assertAlmostEqual(units.detail_step(obj)*conversion, .00001, places=10)
            tools.begin({'tool':'BEVEL','parameters':{'auto_size':True, 'offset':.02,'snap_step':1}})
            self.assertAlmostEqual(tools.tool_session.params['offset']*conversion,.00002,places=10)
            bm=bmesh.from_edit_mesh(obj.data)
            xs=sorted({round(abs((obj.matrix_world@v.co).x)*conversion,8) for v in bm.verts})
            self.assertTrue(any(abs(x-.00048)<1e-7 for x in xs), xs)
            tools.cancel({})

    def test_explicit_width_and_step_remain_exact(self):
        obj=self.cube(1)
        bpy.ops.object.mode_set(mode='EDIT')
        tools.begin({'tool':'BEVEL','parameters':{'offset':.00003,'snap_step':.000007}})
        self.assertEqual(tools.tool_session.params['offset'],.00003)
        self.assertEqual(tools.tool_session.params['snap_step'],.000007)
        tools.cancel({})

    def test_bevel_nonuniform_object_scale_matches_applied_world_geometry(self):
        from blender_tablet_remote.commands import mesh
        from mathutils.kdtree import KDTree
        outputs=[]
        for applied in (True,False):
            self.setUp()
            obj=self.cube(1)
            obj.scale=(2,3,4)
            obj.rotation_euler=(.2,.3,.4)
            bpy.context.view_layer.update()
            if applied: bpy.ops.object.transform_apply(location=False,rotation=True,scale=True)
            matrix=obj.matrix_world.copy()
            bpy.ops.object.mode_set(mode='EDIT')
            mesh.bevel({'offset':.00003,'affect':'EDGES'})
            outputs.append([obj.matrix_world@v.co for v in bmesh.from_edit_mesh(obj.data).verts])
            self.assertEqual(obj.matrix_world,matrix)
        self.assertEqual(len(outputs[0]),len(outputs[1]))
        tree=KDTree(len(outputs[0]))
        for index,point in enumerate(outputs[0]): tree.insert(point,index)
        tree.balance()
        self.assertLess(max(tree.find(point)[2] for point in outputs[1]),1e-7)

    def test_presets_and_open_do_not_rescale_one_mm_geometry(self):
        for conversion in (.001,1):
            self.setUp()
            obj=self.cube(conversion)
            before=[tuple(v.co) for v in obj.data.vertices]
            for preset in ('LARGE','MEDIUM','SMALL'):
                units.apply_scale(preset)
                self.assertEqual([tuple(v.co) for v in obj.data.vertices],before)
                self.assertAlmostEqual(obj.dimensions.x*conversion,.001,places=9)
                self.assertAlmostEqual(bpy.context.scene.unit_settings.scale_length,conversion)
            with tempfile.TemporaryDirectory() as folder:
                path=str(Path(folder)/'one-mm.blend')
                bpy.ops.wm.save_as_mainfile(filepath=path)
                file.open_file({'path':path})
                self.assertEqual([tuple(v.co) for v in bpy.context.object.data.vertices],before)
                self.assertAlmostEqual(bpy.context.object.dimensions.x*conversion,.001,places=9)
                self.assertAlmostEqual(bpy.context.scene.unit_settings.scale_length,conversion)


result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DetailDimensionsTests))
if not result.wasSuccessful(): raise SystemExit(1)
