"""Referencias: blender --background --factory-startup --python-exit-code 1 --python este_archivo."""
import base64
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import reference
from blender_tablet_remote.camera import camera
from blender_tablet_remote.errors import BadPayload


def png_base64(width=4, height=2):
    image = bpy.data.images.new("tmp", width, height)
    path = Path(tempfile.mkdtemp()) / "tmp.png"
    image.filepath_raw = str(path)
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)
    return base64.b64encode(path.read_bytes()).decode()


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add(size=.02)
        camera.reset()
        camera._synced = True
        camera.location = Vector((1, 2, 3))
        camera.rotation = Quaternion((0.9238795, 0.3826834, 0, 0))  # 45° sobre X
        camera.distance = .1
        camera.perspective = 'PERSP'
        rv3d = SimpleNamespace(window_matrix=Matrix(((1,0,0,0),(0,2,0,0),(0,0,-1,-.02),(0,0,-1,0))))
        self.patches = [patch.object(reference, 'find_view3d', return_value=(None, None, None, rv3d)),
                        patch.object(reference.state, 'snapshot', return_value={}),
                        patch.object(reference, 'undo_push')]
        started = [p.start() for p in self.patches]
        self.undo = started[-1]

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()

    def test_adds_packed_image_facing_the_tablet_camera(self):
        result = reference.add(dict(name='Plano', format='png', data=png_base64(), opacity=.5))
        empty = bpy.data.objects[result['reference']]
        self.assertEqual(empty.empty_display_type, 'IMAGE')
        self.assertTrue(empty.data.packed_file)
        self.assertEqual(tuple(empty.data.size), (4, 2))
        self.assertEqual(empty.data.filepath, '')
        self.assertEqual(tuple(empty.location), (1, 2, 3))
        self.assertAlmostEqual(empty.rotation_euler.x, 0.785398, places=5)
        self.assertTrue(empty.use_empty_image_alpha)
        self.assertAlmostEqual(empty.color[3], .5, places=5)
        self.assertAlmostEqual(empty.empty_display_size, .1 * reference.VIEW_FRACTION, places=6)
        self.assertEqual(bpy.context.view_layer.objects.active, empty)
        self.assertEqual([o.name for o in bpy.context.selected_objects], [empty.name])
        self.undo.assert_called_once()

    def test_edit_mode_keeps_the_edited_object_active(self):
        cube = bpy.context.object
        bpy.ops.object.mode_set(mode='EDIT')
        result = reference.add(dict(format='png', data=png_base64()))
        self.assertEqual(bpy.context.view_layer.objects.active, cube)
        self.assertEqual(cube.mode, 'EDIT')
        self.assertIn(result['reference'], bpy.data.objects)
        bpy.ops.object.mode_set(mode='OBJECT')

    def test_rejects_bad_input_without_creating_objects(self):
        before = len(bpy.data.objects)
        for payload in (dict(format='gif', data=png_base64()), dict(format='png', data='***'),
                        dict(format='png', data=png_base64(), opacity=0)):
            with self.assertRaises(BadPayload):
                reference.add(payload)
        self.assertEqual(len(bpy.data.objects), before)
        self.undo.assert_not_called()


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ReferenceTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful(): raise SystemExit(1)
