"""blender --background --factory-startup --python-exit-code 1 --python este_archivo"""
import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import object_properties as props
from blender_tablet_remote.errors import BadPayload, CommandError


class ObjectPropertiesTests(unittest.TestCase):
    def setUp(self):
        if bpy.context.object and bpy.context.object.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add(size=2)
        self.obj = bpy.context.object
        bpy.context.scene.unit_settings.scale_length = .001
        self.undo_patch = patch.object(props, 'undo_push')
        self.undo = self.undo_patch.start()

    def tearDown(self): self.undo_patch.stop()

    def apply(self, values, snapshot=None):
        snapshot = snapshot or props.describe(bpy.context.object)
        return props.apply(dict(object_id=snapshot['id'], revision=snapshot['revision'], values=values))

    def image(self):
        obj = bpy.data.objects.new('Referencia', None)
        obj.empty_display_type = 'IMAGE'
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'image.png')
            generated = bpy.data.images.new('Plano', 40, 20)
            generated.filepath_raw = path
            generated.file_format = 'PNG'
            generated.save()
            bpy.data.images.remove(generated)
            obj.data = bpy.data.images.load(path)
            obj.data.pack()
            obj.data.filepath = ''
        bpy.context.collection.objects.link(obj)
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        return obj

    def test_metric_position_and_dimensions_one_undo(self):
        self.obj.scale = (2, 3, 4)
        bpy.context.view_layer.update()
        self.apply({'location_x': .0125, 'dimension_x': .01, 'dimension_y': .006})
        self.assertAlmostEqual(self.obj.location.x, 12.5, places=5)
        self.assertAlmostEqual(self.obj.dimensions.x, 10., places=5)
        self.assertAlmostEqual(self.obj.dimensions.y, 6., places=5)
        self.assertAlmostEqual(self.obj.dimensions.z, 8., places=5)
        self.undo.assert_called_once()

    def test_zero_dimension_stays_editable_and_recovers_without_changing_geometry(self):
        vertices = [tuple(v.co) for v in self.obj.data.vertices]
        for axis in 'xyz':
            key = 'dimension_' + axis
            baseline = tuple(self.obj.dimensions)
            self.apply({key: 0.})
            fields = {f['id']: f for f in props.describe(self.obj)['fields']}
            self.assertFalse(fields[key]['read_only'])
            self.assertEqual(self.obj.dimensions['xyz'.index(axis)], 0.)
            self.apply({key: .007})
            self.assertAlmostEqual(self.obj.dimensions['xyz'.index(axis)], 7., places=5)
            for index in range(3):
                if index != 'xyz'.index(axis):
                    self.assertAlmostEqual(self.obj.dimensions[index], baseline[index], places=5)
            self.assertEqual([tuple(v.co) for v in self.obj.data.vertices], vertices)
        self.assertEqual(self.undo.call_count, 6)

    def test_all_zero_dimensions_can_be_recovered_after_saving_and_loading(self):
        self.apply({f'dimension_{axis}': 0. for axis in 'xyz'})
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'zero-size.blend')
            bpy.ops.wm.save_as_mainfile(filepath=path)
            bpy.ops.wm.open_mainfile(filepath=path)
            self.apply({'dimension_x': .003, 'dimension_y': .004, 'dimension_z': .005})
            for actual, expected in zip(bpy.context.object.dimensions, (3., 4., 5.)):
                self.assertAlmostEqual(actual, expected, places=5)

    def test_genuinely_flat_geometry_and_locked_axis_remain_read_only(self):
        for vertex in self.obj.data.vertices:
            vertex.co.z = 0.
        self.obj.data.update()
        self.obj.lock_scale[0] = True
        bpy.context.view_layer.update()
        fields = {f['id']: f for f in props.describe(self.obj)['fields']}
        self.assertTrue(fields['dimension_z']['read_only'])
        self.assertTrue(fields['dimension_x']['read_only'])
        self.assertFalse(fields['dimension_y']['read_only'])

    def test_image_native_properties_and_persistence(self):
        obj = self.image()
        self.apply({'display_size': .04, 'opacity': .35, 'orthographic': True, 'perspective': False,
                    'axis_only': True, 'depth': 'BACK', 'side': 'FRONT', 'location_z': .02})
        self.assertAlmostEqual(obj.empty_display_size, 40.)
        self.assertAlmostEqual(obj.color[3], .35)
        self.assertTrue(obj.use_empty_image_alpha)
        self.assertFalse(obj.show_empty_image_perspective)
        self.assertTrue(obj.show_empty_image_orthographic)
        self.assertTrue(obj.show_empty_image_only_axis_aligned)
        self.assertEqual(obj.empty_image_depth, 'BACK')
        self.assertEqual(obj.empty_image_side, 'FRONT')
        name = obj.name
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'reference.blend')
            bpy.ops.wm.save_as_mainfile(filepath=path)
            bpy.ops.wm.open_mainfile(filepath=path)
            restored = bpy.data.objects[name]
            self.assertTrue(restored.data.packed_file)
            self.assertFalse(restored.show_empty_image_perspective)
            self.assertAlmostEqual(restored.color[3], .35)
        self.undo.assert_called_once()

    def test_atomic_validation_and_stale_snapshot(self):
        baseline = props.describe(self.obj)
        for values in ({'location_x': .012, 'render': 'false'}, {'location_x': math.nan},
                       {'location_x': .012, 'not_a_property': 1}, {'dimension_x': -.01}):
            with self.assertRaises(BadPayload): self.apply(values, baseline)
            self.assertEqual(tuple(self.obj.location), (0., 0., 0.))
        self.obj.location.y = 1.
        with self.assertRaises(CommandError): self.apply({'location_x': .012}, baseline)
        self.undo.assert_not_called()

    def test_reference_rejects_invalid_enum_without_partial_write(self):
        obj = self.image()
        with self.assertRaises(BadPayload): self.apply({'opacity': .5, 'side': 'BOTH'})
        self.assertEqual(obj.color[3], 1.)
        with self.assertRaises(BadPayload): self.apply({'opacity': 1.1})
        self.undo.assert_not_called()

    def test_hidden_active_can_be_restored_and_zero_opacity_is_exact(self):
        obj = self.image()
        self.apply({'visible': False, 'opacity': 0.})
        self.assertTrue(obj.hide_get())
        self.assertEqual(obj.color[3], 0.)
        self.assertEqual(bpy.context.view_layer.objects.active, obj)
        self.apply({'visible': True})
        self.assertFalse(obj.hide_get())

    def test_new_active_or_modal_session_cannot_receive_old_draft(self):
        snapshot = props.describe(self.obj)
        self.image()
        with self.assertRaises(CommandError): self.apply({'location_x': .01}, snapshot)
        from blender_tablet_remote.commands.modal import session
        with patch.object(session, 'active', True):
            self.assertIsNone(props.describe(bpy.context.object))
            with self.assertRaises(CommandError): self.apply({'location_x': .01}, snapshot)
        self.undo.assert_not_called()

    def test_locked_axes_and_identical_values_do_not_create_undo(self):
        self.obj.lock_location[0] = True
        with self.assertRaises(BadPayload): self.apply({'location_x': .01})
        self.apply({'location_y': 0.})
        self.undo.assert_not_called()

    def test_reference_rotation_uses_degrees_and_keeps_other_properties(self):
        obj = self.image()
        fields = props.describe(obj)['fields']
        self.assertEqual([f['id'] for f in fields if f['group'] == 'Tamaño'], ['display_size'])
        self.assertEqual(next(f['label'] for f in fields if f['id'] == 'display_size'), 'Tamaño')
        obj.location = (2, 3, 4)
        obj.scale = (2, 2, 2)
        obj.rotation_euler = (.2, .3, .4)
        self.apply({'rotation_z': 90.})
        self.assertAlmostEqual(obj.rotation_euler.z, math.pi / 2, places=6)
        self.assertAlmostEqual(obj.rotation_euler.x, .2, places=6)
        self.assertAlmostEqual(obj.rotation_euler.y, .3, places=6)
        self.assertEqual(tuple(obj.location), (2., 3., 4.))
        self.assertEqual(tuple(obj.scale), (2., 2., 2.))
        self.assertAlmostEqual(props.describe(obj)['values']['rotation_z'], 90., places=4)
        self.undo.assert_called_once()

    def test_quaternion_and_axis_angle_rotation_keep_native_mode(self):
        for mode in ('QUATERNION', 'AXIS_ANGLE'):
            obj = self.image()
            obj.rotation_mode = mode
            self.apply({'rotation_x': 90., 'rotation_y': 0., 'rotation_z': 0.})
            self.assertEqual(obj.rotation_mode, mode)
            self.assertAlmostEqual(props.describe(obj)['values']['rotation_x'], 90., places=4)

    def test_locked_rotation_is_rejected_before_any_change(self):
        obj = self.image()
        obj.lock_rotation[2] = True
        with self.assertRaises(BadPayload): self.apply({'location_x': 1., 'rotation_z': 90.})
        self.assertEqual(obj.location.x, 0.)
        self.assertEqual(obj.rotation_euler.z, 0.)
        self.undo.assert_not_called()


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ObjectPropertiesTests))
    if not result.wasSuccessful(): raise SystemExit(1)
