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


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ObjectPropertiesTests))
    if not result.wasSuccessful(): raise SystemExit(1)
