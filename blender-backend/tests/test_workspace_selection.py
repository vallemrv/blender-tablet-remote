"""blender --background --factory-startup --python-exit-code 1 --python este_archivo."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import nullcontext
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import material, workspace_selection as selection
from blender_tablet_remote.materials.runtime import runtime

class WorkspaceSelectionTests(unittest.TestCase):
    def setUp(self):
        runtime.leave()
        if bpy.context.object and bpy.context.object.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
        for o in list(bpy.data.objects):bpy.data.objects.remove(o,do_unlink=True)
        bpy.ops.mesh.primitive_cube_add();self.a=bpy.context.object
        bpy.ops.mesh.primitive_cube_add(location=(3,0,0));self.b=bpy.context.object
        runtime.enter('test');runtime.select([self.a.name])
    def tearDown(self):runtime.leave()
    def tap(self,name,additive=False):
        with patch('blender_tablet_remote.commands.snap.query_candidate',return_value={'hit':name is not None,'object':name}),patch.object(runtime,'presentation',return_value=nullcontext()):
            return material.select(dict(u=.5,v=.5,additive=additive,_client_id='test'))
    def test_replace_toggle_and_empty_follow_common_intent(self):
        self.tap(self.b.name);self.assertEqual(runtime.targets,[self.b.name])
        self.tap(self.b.name);self.assertEqual(runtime.targets,[self.b.name])
        self.tap(self.a.name,True);self.assertEqual(set(runtime.targets),{self.a.name,self.b.name})
        self.tap(self.a.name,True);self.assertEqual(runtime.targets,[self.b.name])
        self.tap(None,True);self.assertEqual(runtime.targets,[self.b.name])
        self.tap(None);self.assertEqual(runtime.targets,[])
    def test_region_adapter_and_cancel_restore_material_target_context(self):
        runtime.active_layer='saved';runtime.scope='SELECTED'
        before=selection.snapshot()
        selection.apply([self.b.name],'SET');self.assertEqual(runtime.targets,[self.b.name])
        selection.apply([self.a.name,self.a.name],'TOGGLE');self.assertEqual(set(runtime.targets),{self.a.name,self.b.name})
        selection.restore(before)
        self.assertEqual(runtime.targets,[self.a.name]);self.assertEqual(runtime.active_layer,'saved');self.assertEqual(runtime.scope,'SELECTED')
    def test_locked_objects_are_not_offered_or_selected(self):
        self.b.hide_select=True
        self.tap(self.b.name)
        self.assertEqual(runtime.targets,[self.a.name])
        self.assertNotIn(self.b,runtime.selectable_objects())

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(WorkspaceSelectionTests))
    if not result.wasSuccessful():raise SystemExit(1)
