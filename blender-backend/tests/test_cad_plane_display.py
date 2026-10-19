"""blender --background --factory-startup --python-exit-code 1 --python este_archivo."""
import copy
import itertools
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.cad import document as model, occt
from blender_tablet_remote.cad.plane_display import plane_gizmo
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.commands import cad
from blender_tablet_remote.camera import camera
from blender_tablet_remote.protocol import SCENE_SCALES

occt.load()


class PlaneDisplayTests(unittest.TestCase):
    def setUp(self):
        runtime.reset()
        camera.reset(); camera._synced=True
        camera.location=Vector(); camera.rotation=Quaternion((1,0,0,0))
        camera.distance=20; camera.perspective='ORTHO'; camera.set_clipping(.00001,10000)
        self.rv=SimpleNamespace(window_matrix=Matrix(((1,0,0,0),(0,2,0,0),(0,0,-1,-.02),(0,0,-1,0))))
        self.session={'plane_frame':model.base_frame('XY')}
        self.patches=[patch.object(runtime,'objects',return_value=[]),patch.object(runtime,'doc',return_value=model.new_document())]
        for p in self.patches:p.start()

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        runtime.reset()

    def side_meters(self,gizmo):
        return (gizmo['quad'][1]-gizmo['quad'][0]).length*bpy.context.scene.unit_settings.scale_length

    def test_empty_plane_obeys_preset_and_unit_conversion_without_mutating_frame(self):
        baseline=copy.deepcopy(self.session)
        for preset,scale in itertools.product(SCENE_SCALES.values(),(.001,1.,1000.)):
            bpy.context.scene.unit_settings.scale_length=scale
            with patch('blender_tablet_remote.commands.units.current_scale',return_value=preset):
                gizmo=plane_gizmo(self.session)
            self.assertAlmostEqual(self.side_meters(gizmo),preset['primitive_size']*1.2,places=5)
            self.assertEqual(self.session,baseline)
            self.assertAlmostEqual(bpy.context.scene.unit_settings.scale_length,scale,places=6)

    def test_distant_plane_and_handles_keep_screen_footprint_in_both_projections(self):
        bpy.context.scene.unit_settings.scale_length=.001
        for mode in ('ORTHO','PERSP'):
            camera.apply(distance=40000,perspective=mode)
            with patch('blender_tablet_remote.commands.units.current_scale',return_value=SCENE_SCALES['SMALL']):
                gizmo=plane_gizmo(self.session,self.rv)
            screen=[camera.project(p,self.rv) for p in gizmo['quad']]
            self.assertGreaterEqual(max(p[1] for p in screen)-min(p[1] for p in screen),.299)
            a,b,*_=gizmo['handles']['Y']
            self.assertGreater(abs(camera.project(a,self.rv)[1]-camera.project(b,self.rv)[1]),.06)

    def test_visible_cad_body_still_sets_extent(self):
        bpy.context.scene.unit_settings.scale_length=1
        box=SimpleNamespace(visible_get=lambda:True,matrix_world=Matrix.Identity(4),
                            bound_box=list(itertools.product((-10,10),(-5,5),(-2,2))))
        with patch.object(runtime,'objects',return_value=[box]),patch('blender_tablet_remote.commands.units.current_scale',return_value=SCENE_SCALES['SMALL']):
            gizmo=plane_gizmo(self.session)
        self.assertAlmostEqual(self.side_meters(gizmo),24,places=5)

    def test_offscreen_plane_is_framed_but_visible_plane_does_not_move_camera(self):
        bpy.context.scene.unit_settings.scale_length=1
        camera.apply(location=(100,200,0),distance=10,perspective='ORTHO')
        found=(None,None,None,self.rv)
        baseline=copy.deepcopy(self.session)
        with patch('blender_tablet_remote.bpy_utils.find_view3d',return_value=found):
            cad._show_placed_plane(self.session)
            uv=camera.project(Vector(),self.rv)
            self.assertAlmostEqual(uv[0],.5,places=5);self.assertAlmostEqual(uv[1],.5,places=5)
            previous=camera.as_dict()
            cad._show_placed_plane(self.session)
            self.assertEqual(camera.as_dict(),previous)
        self.assertEqual(self.session,baseline)

    def test_opening_empty_large_sketch_frames_meter_scale_without_changing_document(self):
        bpy.context.scene.unit_settings.scale_length=.001
        sketch={'plane':'XY','offset':0.,'entities':[]}
        baseline=copy.deepcopy(sketch)
        camera.apply(distance=200,perspective='ORTHO')
        with patch('blender_tablet_remote.cad.runtime.find_view3d',return_value=(None,None,None,self.rv)), \
             patch('blender_tablet_remote.commands.units.current_scale',return_value=SCENE_SCALES['LARGE']):
            runtime.focus(sketch)
        span=camera.screen_span(camera.projection_matrix(self.rv))[1]*bpy.context.scene.unit_settings.scale_length
        self.assertGreater(span,SCENE_SCALES["LARGE"]["primitive_size"])
        self.assertLess(span,SCENE_SCALES["LARGE"]["primitive_size"]*2)
        self.assertEqual(sketch,baseline)


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PlaneDisplayTests))
    if not result.wasSuccessful(): raise SystemExit(1)
