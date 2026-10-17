"""RNA-driven Lattice properties and explicit cage creation."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
import bpy
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import modifiers
from blender_tablet_remote.errors import BadPayload
from blender_tablet_remote import state

class LatticeTests(unittest.TestCase):
    def setUp(self):
        bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add();self.obj=bpy.context.object
    def coords(self):
        bpy.context.view_layer.update()
        return [v.co.copy() for v in self.obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices]
    def test_rna_controls_and_object_filter(self):
        option=modifiers.add_options({})['types']['LATTICE'];spec=option['parameters']
        self.assertEqual(option['source'],'RNA');self.assertIn('Jaula',option['label'])
        self.assertEqual(spec['strength']['default'],bpy.types.LatticeModifier.bl_rna.properties['strength'].default)
        self.assertEqual(spec['object']['object_filter']['type'],'LATTICE')
        self.assertEqual(spec['vertex_group']['type'],'vertex_group')
    def test_cage_fits_source_and_native_deformation_uses_strength(self):
        self.obj.location=(3,4,5);self.obj.rotation_euler=(.2,.3,.4);self.obj.scale=(2,3,4)
        bpy.context.view_layer.update();before=self.coords()
        name=modifiers.add(dict(type='LATTICE'))['modifier']
        with patch.object(modifiers,'undo_push') as undo:
            modifiers.set_params(dict(name=name,parameters=dict(create_cage=True)));undo.assert_called_once()
        mod=self.obj.modifiers[name];cage=mod.object
        self.assertEqual(cage.type,'LATTICE');self.assertIs(bpy.context.object,self.obj)
        self.assertEqual((cage.data.points_u,cage.data.points_v,cage.data.points_w),(4,4,4))
        for a,b in zip(self.coords(),before):self.assertLess((a-b).length,1e-5)
        local=[self.obj.matrix_world.inverted()@cage.matrix_world@p.co_deform for p in cage.data.points]
        for axis in range(3):
            self.assertAlmostEqual(min(p[axis] for p in local),-1.,places=5)
            self.assertAlmostEqual(max(p[axis] for p in local),1.,places=5)
        for p in cage.data.points:p.co_deform.x+=.2
        cage.data.update_tag();self.assertTrue(any((a-b).length>1e-4 for a,b in zip(self.coords(),before)))
        sig=state._modifiers_sig(self.obj)
        modifiers.set_params(dict(name=name,parameters=dict(strength=0)))
        self.assertNotEqual(state._modifiers_sig(self.obj),sig)
        for a,b in zip(self.coords(),before):self.assertLess((a-b).length,1e-5)
        with self.assertRaises(BadPayload):modifiers.set_params(dict(name=name,parameters=dict(create_cage=True)))
    def test_wrong_object_and_bad_values_do_not_partially_apply(self):
        name=modifiers.add(dict(type='LATTICE'))['modifier'];before=modifiers.stack()
        bpy.ops.mesh.primitive_cube_add();other=bpy.context.object
        for params in [dict(object=other.name,strength=.2),dict(strength=float('nan')),dict(vertex_group='missing')]:
            with self.assertRaises(BadPayload):modifiers.set_params(dict(object=self.obj.name,name=name,parameters=params))
            self.assertEqual(modifiers.stack(self.obj),before)
    def test_existing_lattice_and_group_bind_without_copying_geometry(self):
        data=bpy.data.lattices.new('Existing');cage=bpy.data.objects.new('Existing',data);bpy.context.scene.collection.objects.link(cage)
        self.obj.vertex_groups.new(name='Zona')
        name=modifiers.add(dict(type='LATTICE',parameters=dict(object=cage.name,vertex_group='Zona',invert_vertex_group=True,strength=.37)))['modifier']
        mod=self.obj.modifiers[name];self.assertIs(mod.object,cage);self.assertEqual(mod.vertex_group,'Zona')
        self.assertTrue(mod.invert_vertex_group);self.assertAlmostEqual(mod.strength,.37,places=6)
        modifiers.remove(dict(name=name));self.assertIsNotNone(bpy.data.objects.get(cage.name))

result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(LatticeTests))
if not result.wasSuccessful():raise SystemExit(1)
