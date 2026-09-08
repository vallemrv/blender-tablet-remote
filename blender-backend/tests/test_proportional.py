"""blender --background --factory-startup --python-exit-code 1 --python this_file."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import bpy
import bmesh
from mathutils import Vector

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import modal, sessions, units
from blender_tablet_remote.errors import CommandError


class ProportionalTests(unittest.TestCase):
    def setUp(self):
        sessions.cancel_all()
        if bpy.context.object and bpy.context.object.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
        bpy.context.scene.unit_settings.scale_length=.001
        data=bpy.data.meshes.new('Proportional')
        data.from_pydata([(10,0,0),(15,0,0),(25,0,0),(160,0,0)],[],[])
        self.obj=bpy.data.objects.new('Proportional',data)
        bpy.context.collection.objects.link(self.obj)
        bpy.context.view_layer.objects.active=self.obj; self.obj.select_set(True)
        bpy.context.scene.tool_settings.mesh_select_mode=(True,False,False)
        bpy.ops.object.mode_set(mode='EDIT')
        self.bm=bmesh.from_edit_mesh(data); self.bm.verts.ensure_lookup_table()
        for v in self.bm.verts: v.select=False
        self.bm.verts[0].select=True
        self.original=[v.co.copy() for v in self.bm.verts]
        bmesh.update_edit_mesh(data)

    def tearDown(self):
        sessions.cancel_all()

    def test_radius_updates_live_weights_without_restarting_or_losing_transform(self):
        for mode in ('MOVE','ROTATE','SCALE'):
            with self.subTest(mode=mode), patch.object(modal,'undo_push') as undo:
                sessions.cancel_all()
                modal.begin(dict(mode=mode,axes=['Z'] if mode=='ROTATE' else [],
                                 proportional=True,proportional_radius=10,proportional_falloff='LINEAR'))
                modal.session.center_position=Vector()
                modal.set_value({'angle':90} if mode=='ROTATE' else {'values':[0,0,10] if mode=='MOVE' else [2,2,2]})
                session_id=modal.session.session_id
                values=modal.session.values.copy()
                selected=self.bm.verts[0].co.copy()
                self.assertNotEqual(self.bm.verts[1].co,self.original[1])
                self.assertEqual(self.bm.verts[2].co,self.original[2])
                for radius in (20,3,20):
                    result=modal.set_edit_settings({'radius':radius})
                    self.assertEqual(result['transform']['session_id'],session_id)
                    self.assertEqual(modal.session.values,values)
                    self.assertLess((self.bm.verts[0].co-selected).length,1e-5)
                    self.assertEqual(self.bm.verts[3].co,self.original[3])
                    if radius==3:
                        self.assertEqual(self.bm.verts[1].co,self.original[1])
                        self.assertEqual(self.bm.verts[2].co,self.original[2])
                    else:
                        self.assertNotEqual(self.bm.verts[2].co,self.original[2])
                undo.assert_not_called()
                modal.cancel({})
                for v,co in zip(self.bm.verts,self.original): self.assertEqual(v.co,co)

    def test_disabling_proportional_restores_neighbors_but_keeps_selected_transform(self):
        modal.begin(dict(mode='MOVE',proportional=True,proportional_radius=20))
        modal.set_value({'values':[0,0,10]})
        selected=self.bm.verts[0].co.copy()
        modal.set_edit_settings({'proportional':False})
        self.assertEqual(self.bm.verts[0].co,selected)
        for v,co in zip(list(self.bm.verts)[1:],self.original[1:]): self.assertEqual(v.co,co)
        modal.set_edit_settings({'proportional':True,'falloff':'CONSTANT'})
        self.assertAlmostEqual(self.bm.verts[1].co.z,10)

    def test_preset_radius_is_physical_in_millimeter_scene(self):
        for scale in (.001,1.0):
            bpy.context.scene.unit_settings.scale_length=scale
            units.apply_scale('SMALL')
            self.assertAlmostEqual(bpy.context.scene.tool_settings.proportional_size*scale,.01,places=7)

    def test_radius_changes_keep_reference_axes_and_one_confirmation_undo(self):
        modal.begin(dict(mode='MOVE',axes=['Z'],proportional=True,proportional_radius=10))
        modal.session.reference_position=Vector((10,0,0))
        modal.set_value({'values':[0,0,10]})
        with patch.object(modal,'undo_push') as undo:
            for radius in (20,3,15): modal.set_edit_settings({'radius':radius})
            self.assertEqual(modal.session.axes,['Z'])
            self.assertEqual(modal.session.reference_position,Vector((10,0,0)))
            undo.assert_not_called()
            modal.confirm({})
            self.assertEqual(undo.call_count,1)


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    if not result.wasSuccessful(): raise SystemExit(1)
