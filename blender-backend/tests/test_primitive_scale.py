"""blender --background --factory-startup --python-exit-code 1 --python this_file."""
import sys
import unittest
from pathlib import Path
import bpy
import bmesh
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import objects, units


class PrimitiveScaleTests(unittest.TestCase):
    def setUp(self):
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.context.scene.unit_settings.scale_length = 1.0
        units.reset()

    def add(self, primitive, scale):
        bpy.context.scene.unit_settings.scale_length = scale
        objects.add_primitive({'primitive':primitive})
        bpy.context.view_layer.update()
        obj = bpy.context.object
        return tuple(d * scale for d in obj.dimensions)

    def test_small_cube_is_ten_mm_in_millimeter_scene(self):
        units.apply_scale('SMALL')
        dimensions = self.add('CUBE', .001)
        for size in dimensions:self.assertAlmostEqual(size, .01, places=7)
        self.assertAlmostEqual(bpy.context.scene.unit_settings.scale_length, .001)

    def test_all_presets_keep_physical_size_across_scene_scales(self):
        for preset, size in [('SMALL',.01),('MEDIUM',.5),('LARGE',2.0)]:
            units.apply_scale(preset)
            for scale in (.001,.01,1.0,10.0):
                with self.subTest(preset=preset, scale=scale):
                    for dimension in self.add('CUBE', scale):
                        self.assertAlmostEqual(dimension, size, places=6)

    def test_radii_depths_and_curves_keep_physical_dimensions(self):
        units.apply_scale('SMALL')
        for kind in ('PLANE','SPHERE','CYLINDER','CONE','TORUS','BEZIER_CIRCLE'):
            reference = self.add(kind, 1.0)
            for scale in (.001,.01):
                with self.subTest(kind=kind, scale=scale):
                    measured = self.add(kind, scale)
                    for expected, actual in zip(reference, measured):
                        self.assertAlmostEqual(actual, expected, places=6)

    def test_adding_preserves_existing_geometry_and_cursor(self):
        units.apply_scale('SMALL')
        self.add('CUBE', .001)
        obj = bpy.context.object
        before = tuple(tuple(v.co) for v in obj.data.vertices)
        bpy.context.scene.cursor.location = (20,30,40)
        self.add('CUBE', .001)
        self.assertEqual(tuple(bpy.context.object.location), (20,30,40))
        self.assertEqual(tuple(tuple(v.co) for v in obj.data.vertices), before)

    def test_edit_add_uses_same_physical_size(self):
        units.apply_scale('SMALL')
        self.add('CUBE', .001)
        bpy.context.object.scale = (2,3,4)
        bpy.context.view_layer.update()
        bpy.ops.object.mode_set(mode='EDIT')
        before = len(bmesh.from_edit_mesh(bpy.context.object.data).verts)
        bpy.ops.mesh.select_all(action='DESELECT')
        objects.add_primitive({'primitive':'CUBE'})
        obj = bpy.context.object
        bm = bmesh.from_edit_mesh(obj.data)
        self.assertEqual(len(bm.verts), before+8)
        points = [obj.matrix_world @ v.co for v in bm.verts if v.select]
        self.assertEqual(len(points),8)
        for axis in range(3):
            size = (max(p[axis] for p in points)-min(p[axis] for p in points))*.001
            self.assertAlmostEqual(size,.01,places=6)


result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PrimitiveScaleTests))
if not result.wasSuccessful():raise RuntimeError('Primitive scale regression failed')
