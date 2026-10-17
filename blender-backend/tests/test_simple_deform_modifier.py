"""Native Simple Deform controls and atomic validation."""
import sys,math,unittest
from pathlib import Path
from unittest.mock import patch
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import modifiers
from blender_tablet_remote.errors import BadPayload

class SimpleDeformTests(unittest.TestCase):
    def setUp(self):
        bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add()
        self.obj=bpy.context.object
        bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.subdivide(number_cuts=3);bpy.ops.object.mode_set(mode='OBJECT')
    def coords(self,obj):
        bpy.context.view_layer.update()
        return [tuple(v.co) for v in obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices]
    def test_four_methods_and_axes_match_native_geometry(self):
        original=self.coords(self.obj)
        expected=self.obj.copy();expected.data=self.obj.data.copy();bpy.context.scene.collection.objects.link(expected)
        native=expected.modifiers.new('Native','SIMPLE_DEFORM')
        name=modifiers.add(dict(type='SIMPLE_DEFORM'))['modifier']
        for method in ('TWIST','BEND','TAPER','STRETCH'):
            for axis in 'XYZ':
                params=dict(deform_method=method,deform_axis=axis,angle=63.25,factor=.37)
                modifiers.set_params(dict(name=name,parameters=params))
                native.deform_method=method;native.deform_axis=axis
                if method in ('TWIST','BEND'):native.angle=math.radians(63.25)
                else:native.factor=.37
                with self.subTest(method=method,axis=axis):
                    self.assertEqual(self.coords(self.obj),self.coords(expected))
                    self.assertNotEqual(self.coords(self.obj),original)
        self.assertEqual([tuple(v.co) for v in self.obj.data.vertices],original)
    def test_angle_factor_alias_is_not_overwritten_on_other_edits(self):
        name=modifiers.add(dict(type='SIMPLE_DEFORM',parameters=dict(angle=-123.456)))['modifier']
        modifiers.set_params(dict(name=name,parameters=dict(limit_lower=.2,limit_upper=.8)))
        self.assertAlmostEqual(math.degrees(self.obj.modifiers[name].angle),-123.456,places=4)
        modifiers.set_params(dict(name=name,parameters=dict(deform_method='TAPER',factor=1000)))
        modifiers.set_params(dict(name=name,parameters=dict(lock_x=True)))
        self.assertEqual(self.obj.modifiers[name].factor,1000)
        self.assertTrue(self.obj.modifiers[name].lock_x)
    def test_invalid_edits_are_atomic_and_failed_add_leaves_no_modifier(self):
        name=modifiers.add(dict(type='SIMPLE_DEFORM'))['modifier']
        before=modifiers.stack()
        for params in [dict(deform_axis='Q'),dict(deform_method='OTHER'),dict(limit_lower=.8,limit_upper=.2),
                       dict(angle=float('nan')),dict(origin=self.obj.name),dict(origin='missing'),dict(lock_x=1)]:
            with self.subTest(params=params),self.assertRaises(BadPayload):modifiers.set_params(dict(name=name,parameters=params))
            self.assertEqual(modifiers.stack(),before)
        with self.assertRaises(BadPayload):modifiers.add(dict(type='SIMPLE_DEFORM',parameters=dict(limit_upper=2)))
        self.assertEqual(len(self.obj.modifiers),1)
    def test_origin_other_object_and_remove_apply_share_standard_stack(self):
        origin=bpy.data.objects.new('Origin',None);bpy.context.scene.collection.objects.link(origin)
        with patch.object(modifiers,'undo_push') as undo:
            name=modifiers.add(dict(type='SIMPLE_DEFORM',parameters=dict(origin=origin.name)))['modifier'];undo.assert_called_once()
        self.assertIs(self.obj.modifiers[name].origin,origin)
        modifiers.set_params(dict(name=name,parameters=dict(origin=None)))
        self.assertIsNone(self.obj.modifiers[name].origin)
        evaluated=self.coords(self.obj);modifiers.apply(dict(name=name))
        self.assertFalse(self.obj.modifiers);self.assertEqual(self.coords(self.obj),evaluated)
    def test_schema_shows_angle_or_factor_in_degrees(self):
        spec=modifiers.add_options({})['types']['SIMPLE_DEFORM']['parameters']
        self.assertEqual(spec['angle']['unit'],'ANGLE')
        self.assertEqual(spec['angle']['visible_when']['deform_method'],['TWIST','BEND'])
        self.assertEqual(spec['factor']['visible_when']['deform_method'],['TAPER','STRETCH'])
        self.assertTrue(spec['origin']['object_filter']['exclude_self'])

result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SimpleDeformTests))
if not result.wasSuccessful():raise SystemExit(1)
