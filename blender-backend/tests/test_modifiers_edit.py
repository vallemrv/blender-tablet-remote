"""blender --background --factory-startup --python-exit-code 1 --python este_archivo."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import bpy
import bmesh
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import modifiers, modal
from blender_tablet_remote.errors import CommandError


class ModifiersEditTests(unittest.TestCase):
    def setUp(self):
        modal.session.reset()
        if bpy.context.object and bpy.context.object.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
        for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
        bpy.ops.mesh.primitive_cube_add();self.obj=bpy.context.object
        bpy.ops.object.mode_set(mode='EDIT')
        self.before=[tuple(v.co) for v in bmesh.from_edit_mesh(self.obj.data).verts]
        self.patch=patch.object(modifiers,'undo_push');self.undo=self.patch.start()

    def tearDown(self):
        modal.session.reset()
        if bpy.context.object and bpy.context.object.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
        self.patch.stop()

    def test_edit_add_clipping_subdivision_order_visibility_and_remove(self):
        mirror=modifiers.add({'type':'MIRROR'})['modifier']
        modifiers.set_params({'name':mirror,'parameters':{'use_clip':True}})
        self.assertTrue(self.obj.modifiers[mirror].use_clip)
        sub=modifiers.add({'type':'SUBSURF','parameters':{'levels':2}})['modifier']
        self.assertEqual(self.obj.modifiers[sub].levels,2)
        modifiers.move({'name':sub,'index':0})
        self.assertEqual(self.obj.modifiers[0].name,sub)
        result=modifiers.toggle({'name':mirror,'editmode':False})
        state=next(m for m in result['modifiers'] if m['name']==mirror)
        self.assertFalse(state['show_in_editmode']);self.assertTrue(state['show_viewport'])
        modifiers.toggle({'name':mirror,'editmode':True})
        self.assertTrue(self.obj.modifiers[mirror].show_in_editmode)
        modifiers.remove({'name':sub})
        self.assertEqual(self.obj.mode,'EDIT')
        self.assertEqual([tuple(v.co) for v in bmesh.from_edit_mesh(self.obj.data).verts],self.before)
        self.assertEqual(self.undo.call_count,7)

    def test_apply_and_changes_during_transform_are_rejected(self):
        name=modifiers.add({'type':'MIRROR'})['modifier']
        self.undo.reset_mock()
        with self.assertRaises(CommandError):modifiers.apply({'name':name})
        modal.session.begin('MOVE',[],False,1.)
        with self.assertRaises(CommandError):modifiers.set_params({'name':name,'parameters':{'use_clip':True}})
        self.undo.assert_not_called()


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ModifiersEditTests))
    if not result.wasSuccessful():raise SystemExit(1)
