"""Escalar métrico: blender --background --factory-startup --python-exit-code 1 --python este_archivo."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import bpy
import bmesh
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import modal, sessions
from blender_tablet_remote.errors import BadPayload


class ScaleUnitsTests(unittest.TestCase):
    def setUp(self):
        sessions.cancel_all()
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.context.scene.tool_settings.use_proportional_edit = False
        bpy.context.scene.unit_settings.scale_length = 1.0
        bpy.ops.mesh.primitive_cube_add()
        self.obj = bpy.context.object

    def tearDown(self):
        sessions.cancel_all()

    def begin(self, scene_scale=1.0, edit=False, axes=(), dimensions=(20, 40, 10), **options):
        sessions.cancel_all()
        if self.obj.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.context.scene.unit_settings.scale_length = scene_scale
        self.obj.scale = Vector(d / 2000 / scene_scale for d in dimensions)
        bpy.context.view_layer.update()
        if edit:
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
        return modal.begin(dict(mode='SCALE', axes=list(axes), snap=True,
                                snap_type='INCREMENT', step=.001 / scene_scale,
                                scale_step_unit='LENGTH', **options))

    def dimensions_mm(self):
        bpy.context.view_layer.update()
        if self.obj.mode == 'EDIT':
            points = [self.obj.matrix_world @ v.co for v in bmesh.from_edit_mesh(self.obj.data).verts]
        else:
            points = [self.obj.matrix_world @ Vector(co) for co in self.obj.bound_box]
        unit = bpy.context.scene.unit_settings.scale_length * 1000
        return [(max(p[i] for p in points) - min(p[i] for p in points)) * unit for i in range(3)]

    def assertDimensions(self, expected):
        for actual, wanted in zip(self.dimensions_mm(), expected):
            self.assertAlmostEqual(actual, wanted, places=4)

    def test_metric_gesture_on_axis_in_object_and_edit_with_scene_scale(self):
        for edit in (False, True):
            for scene_scale in (1.0, .001):
                with self.subTest(edit=edit, scene_scale=scene_scale):
                    self.begin(scene_scale, edit, axes=['X'])
                    modal.nudge(dict(dx=.03, dy=0))  # raw 6 % -> one mm on 20 mm
                    self.assertDimensions([21, 40, 10])

    def test_free_and_plane_gesture_use_largest_active_dimension(self):
        self.begin()
        modal.nudge(dict(dx=.014, dy=0))
        self.assertDimensions([20.5, 41, 10.25])
        self.begin(axes=['X', 'Z'])
        modal.nudge(dict(dx=.03, dy=0))
        self.assertDimensions([21, 40, 10.5])

    def test_exact_button_on_shorter_axis_is_not_resnapped(self):
        for edit in (False, True):
            self.begin(edit=edit, dimensions=(20, 37, 10))
            result = modal.set_value(dict(values=[1.05] * 3))
            self.assertDimensions([21, 38.85, 10.5])
            self.assertEqual(result['scale_step_unit'], 'LENGTH')
            modal.set_value(dict(values=[1.10, 1.05, 1.05]))
            self.assertDimensions([22, 38.85, 10.5])

    def test_unit_switch_snap_toggle_and_reset_keep_exact_input(self):
        initial = self.begin()
        modal.set_value(dict(values=[1.035] * 3))
        modal.set_snap(dict(step=.003, scale_step_unit='LENGTH'))
        self.assertDimensions([20.7, 41.4, 10.35])
        modal.set_value(dict(values=[1, 1, 1]))
        self.assertDimensions([20, 40, 10])
        result = modal.set_snap(dict(snap=False, snap_type='NONE'))
        self.assertEqual(result['scale_step_unit'], 'LENGTH')
        self.assertEqual(result['session_id'], initial['session_id'])
        modal.set_snap(dict(snap=True, snap_type='INCREMENT', step=.07, scale_step_unit='FACTOR'))
        self.assertDimensions([20, 40, 10])
        modal.nudge(dict(dx=.04, dy=0))
        self.assertDimensions([21.4, 42.8, 10.7])

    def test_exact_values_survive_confirm_with_one_undo_and_cancel_restores(self):
        self.begin()
        with patch.object(modal, 'undo_push') as undo, patch.object(modal.state, 'snapshot', return_value={}):
            modal.set_value(dict(values=[1.035] * 3))
            modal.confirm({})
            undo.assert_called_once_with('Remote scale')
            self.assertDimensions([20.7, 41.4, 10.35])
            self.begin()
            modal.nudge(dict(dx=.03, dy=0))
            modal.cancel({})
            self.assertDimensions([20, 40, 10])
            undo.assert_called_once()

    def test_percent_default_and_flat_metric_axis(self):
        self.begin()
        modal.session.scale_step_unit = 'FACTOR'
        modal.session.step = .07
        modal.session.axes = ['X']
        modal.nudge(dict(dx=.04, dy=0))
        self.assertDimensions([21.4, 40, 10])
        self.begin(axes=['Z'], dimensions=(20, 40, 0))
        modal.nudge(dict(dx=.03, dy=0))
        self.assertDimensions([20, 40, 0])

    def test_invalid_step_unit_is_rejected(self):
        with self.assertRaises(BadPayload):
            modal.begin(dict(mode='SCALE', scale_step_unit='MM'))
        self.assertFalse(modal.session.active)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ScaleUnitsTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
