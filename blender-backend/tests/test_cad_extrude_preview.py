"""Depth preview regression: four holes, tessellation reuse and solid geometry."""
import math
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import bpy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cad import CadTests, OWNER, volume
from blender_tablet_remote.cad import document as model
from blender_tablet_remote.cad.kernel import kernel, ExtrusionPreviewCache
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.commands import cad


class ExtrudePreviewTests(CadTests):
    def plate(self):
        outer = self.draw('RECTANGLE', (0, 0), (.27, .15))
        for x, y in ((.04, .03), (.04, .12), (.23, .03), (.23, .12)):
            self.draw('CIRCLE', (x, y), (x + .01, y))
        return outer

    def test_four_holes_depth_changes_reuse_tessellation_and_confirm_one_solid(self):
        outer = self.plate()
        bpy.context.scene.unit_settings.scale_length = .001
        before = model.dumps(runtime.doc())
        with patch.object(kernel, 'extrude', wraps=kernel.extrude) as tessellate:
            self.extrude(outer, .02, confirm=False)
            self.assertEqual(tessellate.call_count, 1)
            topology = (len(self.obj().data.vertices), len(self.obj().data.polygons))
            for depth in (.04, .1, 1e-7, .035):
                status = cad.extrude_update(dict(depth=depth, **OWNER))
                self.assertTrue(status['session']['can_confirm'])
                self.assertTrue(self.obj().visible_get())
                self.assertEqual(topology, (len(self.obj().data.vertices), len(self.obj().data.polygons)))
                area = .27 * .15 - 4 * .5 * 128 * .01**2 * math.sin(2 * math.pi / 128)
                self.assertAlmostEqual(volume(self.obj()) * .001**3, area * depth, delta=area * depth * 1e-5)
            self.assertEqual(model.dumps(runtime.doc()), before)
            with patch('blender_tablet_remote.commands.cad.undo_push') as undo:
                cad.confirm(OWNER)
                undo.assert_called_once()
            self.assertEqual(tessellate.call_count, 1)
        self.assertEqual(len(runtime.objects(runtime.doc())), 1)
        self.assertEqual(runtime.doc()['features'][0]['depth'], .035)
        self.assertIsNone(runtime.session)

    def test_repeated_snap_depth_does_not_replace_mesh_and_cancel_removes_preview(self):
        outer = self.rect()
        self.extrude(outer, .02, confirm=False)
        pointer = self.obj().data.as_pointer()
        cad.extrude_update(dict(gesture=.001, baseline_depth=.02, **OWNER))
        self.assertEqual(self.obj().data.as_pointer(), pointer)
        cad.extrude_update(dict(depth=.03, **OWNER))
        cad.cancel(OWNER)
        self.assertFalse(runtime.objects(runtime.doc()))
        self.assertFalse(runtime.doc()['features'])

    def test_cache_follows_tilted_plane_and_invalidates_changed_profile(self):
        entity = self.rect()
        doc = runtime.doc()
        sketch, source = model.profile(doc, 'profile_' + entity)
        sketch['plane_id'] = 'tilted-plane'
        sketch['frame'] = dict(origin=(.2, .3, .4), x=(0,1,0), y=(0,0,1), normal=(1,0,0))
        cache = ExtrusionPreviewCache()
        with patch.object(kernel, 'extrude', wraps=kernel.extrude) as tessellate:
            for depth in (.02, .04, -.03):
                vertices, faces = cache.extrude(sketch, source, depth, display=True)
                expected, expected_faces = kernel.extrude(sketch, source, depth)
                self.assertEqual(faces, expected_faces)
                for a,b in zip(vertices, expected):
                    for x,y in zip(a,b): self.assertAlmostEqual(x,y,places=7)
            self.assertEqual(tessellate.call_count, 4)  # One template plus three references.
            source['width'] = .12
            cache.extrude(sketch, source, .04, display=True)
            self.assertEqual(tessellate.call_count, 5)

    def test_cache_preserves_each_base_plane_and_offset(self):
        entity = self.rect()
        sketch, source = model.profile(runtime.doc(), 'profile_' + entity)
        cache = ExtrusionPreviewCache()
        for plane in model.PLANES:
            sketch.update(plane=plane, offset=.12)
            for depth in (.02, -.04):
                vertices, faces = cache.extrude(sketch, source, depth, display=True)
                expected, expected_faces = kernel.extrude(sketch, source, depth)
                self.assertEqual(faces, expected_faces)
                for a,b in zip(vertices, expected):
                    for x,y in zip(a,b): self.assertAlmostEqual(x,y,places=7)


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ExtrudePreviewTests))
    if not result.wasSuccessful():
        raise SystemExit(1)
