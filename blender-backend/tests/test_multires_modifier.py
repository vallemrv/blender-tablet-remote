"""blender -b --factory-startup --python-exit-code 1 --python this_file."""
import sys
import unittest
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import modifiers
from blender_tablet_remote.errors import BadPayload

class MultiresModifierTests(unittest.TestCase):
    def setUp(self):
        if bpy.context.object and bpy.context.object.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add()

    def test_catalog_add_and_subdivision_create_real_resolution(self):
        option=modifiers.add_options({})['types']['MULTIRES']['parameters']
        self.assertEqual(option['subdivide']['type'],'action')
        self.assertTrue(option['total_levels']['read_only'])
        response=modifiers.add({'type':'MULTIRES'})
        name=response['modifier'];obj=bpy.context.object
        self.assertEqual(obj.modifiers[name].total_levels,1)
        modifiers.set_params({'name':name,'parameters':{'subdivide':True}})
        state=modifiers.stack()['modifiers'][0]['parameters']
        self.assertEqual((state['levels'],state['sculpt_levels'],state['total_levels']),(2,2,2))
        self.assertEqual(len(obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.polygons),96)
        self.assertEqual(obj.mode,'OBJECT')
        modifiers.add({'type':'MULTIRES'})
        self.assertEqual(len(obj.modifiers),1)

    def test_levels_cannot_exceed_created_resolution(self):
        name=modifiers.add({'type':'MULTIRES'})['modifier']
        with self.assertRaises(BadPayload):modifiers.set_params({'name':name,'parameters':{'levels':2}})
        self.assertEqual(bpy.context.object.modifiers[name].levels,1)
        with self.assertRaises(BadPayload):modifiers.set_params({'name':name,'parameters':{'subdivide':True,'sculpt_levels':99}})
        self.assertEqual(bpy.context.object.modifiers[name].total_levels,1)
        modifiers.set_params({'name':name,'parameters':{'levels':0}})
        self.assertEqual(bpy.context.object.modifiers[name].sculpt_levels,1)

    def test_named_inactive_target_uses_its_own_modifier(self):
        target=bpy.context.object;target.name='Target'
        bpy.ops.mesh.primitive_cube_add();active=bpy.context.object
        modifiers.add({'type':'MULTIRES','object':target.name})
        self.assertIs(bpy.context.object,active)
        self.assertEqual(len(active.modifiers),0)
        self.assertEqual(target.modifiers[0].total_levels,1)

    def test_existing_mirror_and_subsurf_are_preserved(self):
        obj=bpy.context.object
        mirror=obj.modifiers.new('Mirror','MIRROR')
        subsurf=obj.modifiers.new('Subdivision','SUBSURF');subsurf.levels=2
        modifiers.add({'type':'MULTIRES'})
        self.assertEqual(len(obj.modifiers),3)
        self.assertEqual(obj.modifiers['Subdivision'].levels,2)
        self.assertEqual(obj.modifiers['Mirror'].type,'MIRROR')
        self.assertEqual(obj.modifiers['Multires'].total_levels,1)

result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(MultiresModifierTests))
if not result.wasSuccessful():raise SystemExit(1)
