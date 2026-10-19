"""Picking de referencias: blender --background --factory-startup --python-exit-code 1 --python este_archivo."""
import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import selection
from blender_tablet_remote.camera import camera


class ReferencePickTests(unittest.TestCase):
    def setUp(self):
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        image = bpy.data.images.new('Referencia', width=400, height=200)
        self.image = bpy.data.objects.new('Referencia', None)
        self.image.empty_display_type = 'IMAGE'
        self.image.data = image
        self.image.empty_display_size = 4
        bpy.context.scene.collection.objects.link(self.image)
        camera.reset()
        camera._synced = True
        camera.location = Vector()
        camera.rotation = Quaternion((1, 0, 0, 0))
        camera.distance = 10
        camera.perspective = 'PERSP'
        camera.set_clipping(.001, 100)
        self.rv3d = SimpleNamespace(window_matrix=Matrix(((1,0,0,0),(0,2,0,0),(0,0,-1,-.02),(0,0,-1,0))))
        self.patches = [patch.object(selection, 'find_view3d', return_value=(None, None, SimpleNamespace(width=1000, height=500), self.rv3d)),
                        patch.object(selection.state, 'snapshot', return_value={})]
        for p in self.patches: p.start()

    def tearDown(self):
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for p in reversed(self.patches): p.stop()

    def tap(self, point=(0, 0, 0), mode='SET'):
        bpy.context.view_layer.update()
        u, v = camera.project(Vector(point), self.rv3d)
        return selection.pick(dict(u=u, v=v, mode=mode))

    def plane(self, z):
        bpy.ops.mesh.primitive_plane_add(size=10, location=(0, 0, z))
        return bpy.context.object

    def test_interior_selects_native_image_and_toggle_remove_work(self):
        self.assertEqual(self.tap((1.8, .8, 0))['object'], self.image.name)
        self.assertEqual(bpy.context.view_layer.objects.active, self.image)
        self.assertTrue(self.image.select_get())
        self.tap(mode='TOGGLE')
        self.assertFalse(self.image.select_get())
        self.tap(mode='ADD')
        self.assertTrue(self.image.select_get())
        self.tap(mode='REMOVE')
        self.assertFalse(self.image.select_get())

    def test_aspect_offset_rotation_scale_and_parent_follow_visible_rectangle(self):
        self.assertFalse(self.tap((0, 1.2, 0))['hit'])
        self.assertFalse(self.tap((2.2, 0, 0))['hit'])
        self.image.data.display_aspect = (1, 2)
        self.assertTrue(self.tap((0, 1.8, 0))['hit'])
        self.image.empty_image_offset = (0, 0)
        self.image.rotation_euler = (.3, .5, .7)
        self.image.scale = (2, .5, 1)
        parent = bpy.data.objects.new('Padre', None)
        bpy.context.scene.collection.objects.link(parent)
        parent.location = (1, 2, 0)
        self.image.parent = parent
        bpy.context.view_layer.update()
        self.assertTrue(self.tap(self.image.matrix_world @ Vector((1, 1, 0)))['hit'])
        self.assertFalse(self.tap(self.image.matrix_world @ Vector((-.1, 1, 0)))['hit'])

    def test_depth_matches_front_default_back_and_locked_geometry_occludes(self):
        plane = self.plane(-1)
        self.assertEqual(self.tap()['object'], self.image.name)
        plane.location.z = 1
        self.assertEqual(self.tap()['object'], plane.name)
        plane.hide_select = True
        self.assertFalse(self.tap()['hit'])
        self.image.empty_image_depth = 'FRONT'
        self.assertEqual(self.tap()['object'], self.image.name)
        plane.hide_select = False
        plane.location.z = -1
        self.image.empty_image_depth = 'BACK'
        self.assertEqual(self.tap()['object'], plane.name)
        plane.hide_set(True)
        self.assertEqual(self.tap()['object'], self.image.name)

    def test_hidden_locked_excluded_and_transparent_images_are_not_picked(self):
        self.image.hide_select = True
        self.assertFalse(self.tap()['hit'])
        self.image.hide_select = False
        self.image.hide_set(True)
        self.assertFalse(self.tap()['hit'])
        self.image.hide_set(False)
        self.image.use_empty_image_alpha = True
        self.image.color[3] = 0
        self.assertFalse(self.tap()['hit'])
        self.image.color[3] = .5
        self.assertTrue(self.tap()['hit'])
        collection = bpy.data.collections.new('Excluida')
        bpy.context.scene.collection.children.link(collection)
        collection.objects.link(self.image)
        bpy.context.scene.collection.objects.unlink(self.image)
        bpy.context.view_layer.layer_collection.children[collection.name].exclude = True
        self.assertFalse(self.tap()['hit'])

    def test_projection_sides_axis_only_and_behind_camera(self):
        for projection, flag in [('PERSP', 'show_empty_image_perspective'), ('ORTHO', 'show_empty_image_orthographic')]:
            camera.perspective = projection
            self.assertTrue(self.tap()['hit'])
            setattr(self.image, flag, False)
            self.assertFalse(self.tap()['hit'])
            setattr(self.image, flag, True)
        self.image.empty_image_side = 'BACK'
        self.assertFalse(self.tap()['hit'])
        self.image.empty_image_side = 'FRONT'
        self.assertTrue(self.tap()['hit'])
        self.image.rotation_euler.y = math.pi
        self.assertFalse(self.tap()['hit'])
        self.image.empty_image_side = 'DOUBLE_SIDED'
        self.image.rotation_euler.y = .2
        self.image.show_empty_image_only_axis_aligned = True
        self.assertFalse(self.tap()['hit'])
        self.image.rotation_euler.y = 0
        self.assertTrue(self.tap()['hit'])
        camera.perspective = 'PERSP'
        self.image.location.z = 11
        self.assertFalse(self.tap()['hit'])

    def test_reference_never_takes_selection_from_edit_mesh(self):
        plane = self.plane(-1)
        bpy.ops.object.mode_set(mode='EDIT')
        self.tap()
        self.assertEqual(bpy.context.view_layer.objects.active, plane)
        self.assertFalse(self.image.select_get())


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ReferencePickTests))
    if not result.wasSuccessful(): raise SystemExit(1)
