"""blender --background --factory-startup --python-exit-code 1 --python este_archivo."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bpy

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import file, units
from blender_tablet_remote.protocol import SCENE_SCALES
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.bpy_utils import find_view3d
from blender_tablet_remote.errors import BadPayload, CommandError


class NewSceneScaleTests(unittest.TestCase):
    def test_invalid_or_missing_choice_does_not_discard_current_scene(self):
        scene=bpy.context.scene
        before=[o.session_uid for o in scene.objects]
        with patch.object(file,'_reset_session') as reset:
            for preset in (None,'UNKNOWN',42):
                with self.assertRaises(BadPayload):file.new({'preset':preset,'empty':True})
                self.assertEqual(bpy.context.scene,scene)
                self.assertEqual([o.session_uid for o in scene.objects],before)
            reset.assert_not_called()

    def test_new_scene_initializes_units_grid_and_cad_step_for_each_preset(self):
        identities=[]
        for name,preset in SCENE_SCALES.items():
            result=file.new({'preset':name,'empty':True})
            self.assertFalse(result['saved'])
            state=units.current_scale()
            self.assertEqual(state['id'],name)
            self.assertEqual(state['length_unit'],preset['length_unit'])
            self.assertEqual(bpy.context.scene[units.SCENE_SCALE_KEY],name)
            self.assertAlmostEqual(runtime.step,preset['snap_step'])
            space=find_view3d()[1].spaces.active
            self.assertAlmostEqual(space.overlay.grid_scale_unit*state['scale_length'],preset['grid_scale'],places=6)
            identities.append(state['scene_id'])
        self.assertEqual(len(set(identities)),3)

    def test_initial_cube_uses_same_physical_size_as_added_cube_in_each_preset(self):
        from blender_tablet_remote.commands import objects
        from blender_tablet_remote.camera import camera
        from mathutils import Vector
        # Una plantilla de usuario milimétrica ya no impone el tamaño de su cubo.
        for name,size in [('SMALL',.01),('MEDIUM',.5),('LARGE',1.)]:
            file.new({'preset':name})
            cube=bpy.context.object
            conversion=bpy.context.scene.unit_settings.scale_length
            self.assertEqual(len(bpy.context.scene.objects),1)
            for dimension in cube.dimensions:
                self.assertAlmostEqual(dimension*conversion,size,places=6)
            rv3d=find_view3d()[3]
            points=[camera.project(cube.matrix_world@Vector(corner),rv3d) for corner in cube.bound_box]
            self.assertLess(max(abs(c-.5)*2 for p in points for c in p),.6)
            objects.add_primitive({'primitive':'CUBE'})
            bpy.context.view_layer.update()
            for dimension in bpy.context.object.dimensions:
                self.assertAlmostEqual(dimension*conversion,size,places=6)

    def test_scale_command_cannot_change_existing_scene_or_units(self):
        file.new({'preset':'LARGE','empty':True})
        before=units.current_scale()
        for payload in ({'preset':'SMALL'},{'length_unit':'MILLIMETERS'},{'preset':'LARGE'}):
            with self.assertRaises(CommandError) as error:units.set_scale(payload)
            self.assertEqual(error.exception.code,'scene_scale_locked')
            self.assertEqual(units.current_scale(),before)

    def test_preset_survives_blend_load_and_two_scenes_do_not_share_cached_choice(self):
        file.new({'preset':'SMALL','empty':True})
        first=bpy.context.scene
        other=bpy.data.scenes.new('Grande')
        bpy.context.window.scene=other
        units.apply_scale('LARGE')
        bpy.context.window.scene=first
        self.assertEqual(units.current_scale()['id'],'SMALL')
        with tempfile.TemporaryDirectory() as folder:
            path=str(Path(folder)/'escala.blend')
            bpy.ops.wm.save_as_mainfile(filepath=path)
            file.new({'preset':'MEDIUM','empty':True})
            file.open_file({'path':path})
            self.assertEqual(units.current_scale()['id'],'SMALL')
            self.assertEqual(bpy.context.scene.unit_settings.length_unit,'MILLIMETERS')
            self.assertAlmostEqual(runtime.step,.001)

    def test_legacy_scene_uses_native_units_without_rescaling_objects(self):
        for name in ('SMALL','MEDIUM','LARGE'):
            file.new({'preset':name,'empty':True})
            del bpy.context.scene[units.SCENE_SCALE_KEY]
            bpy.context.scene.unit_settings.scale_length=.001
            bpy.ops.mesh.primitive_cube_add(size=2)
            cube=bpy.context.object
            matrix=cube.matrix_world.copy()
            units.reset()
            self.assertEqual(units.current_scale()['id'],name)
            self.assertAlmostEqual(bpy.context.scene.unit_settings.scale_length,.001)
            self.assertEqual(cube.matrix_world,matrix)


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(NewSceneScaleTests))
    if not result.wasSuccessful():raise SystemExit(1)
