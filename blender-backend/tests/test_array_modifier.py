"""Matriz con desplazamiento de objeto (matriz circular): blender -b --python this_file."""
import sys, math, unittest
from pathlib import Path
import bpy
from mathutils import Vector
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import modifiers
from blender_tablet_remote.errors import BadPayload


class ArrayModifierTests(unittest.TestCase):
    def setUp(self):
        bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
        bpy.context.object.data.transform(__import__('mathutils').Matrix.Translation((3, 0, 0)))
        self.obj = bpy.context.object
        bpy.ops.object.empty_add(type='CUBE', location=(0, 0, 0), rotation=(0, 0, math.radians(45)))
        self.empty = bpy.context.object
        bpy.context.view_layer.objects.active = self.obj
        self.obj.select_set(True)

    def evaluated(self):
        bpy.context.view_layer.update()
        return self.obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).data

    def test_object_offset_with_a_rotated_empty_makes_a_circular_array(self):
        name = modifiers.add(dict(type='ARRAY'))['modifier']
        modifiers.set_params(dict(name=name, parameters=dict(
            count=8, use_relative_offset=False, use_object_offset=True, offset_object=self.empty.name)))
        mod = self.obj.modifiers[name]
        self.assertTrue(mod.use_object_offset); self.assertFalse(mod.use_relative_offset)
        self.assertEqual(mod.offset_object, self.empty)
        data = self.evaluated()
        self.assertEqual(len(data.vertices), 8 * 8)
        # Ocho copias girando 45° alrededor del Empty: ninguna queda solapada.
        centers = [sum((data.vertices[i * 8 + j].co for j in range(8)), Vector()) / 8 for i in range(8)]
        self.assertGreater(min((a - b).length for k, a in enumerate(centers) for b in centers[k + 1:]), 0.1)
        read = next(m for m in modifiers.describe(self.obj) if m['name'] == name)['parameters']
        self.assertEqual(read['offset_object'], self.empty.name)
        self.assertTrue(read['use_object_offset']); self.assertFalse(read['use_relative_offset'])
        # Editar otro campo conserva el Empty y los desplazamientos elegidos.
        modifiers.set_params(dict(name=name, parameters=dict(count=6)))
        self.assertEqual(mod.offset_object, self.empty); self.assertFalse(mod.use_relative_offset)
        modifiers.set_params(dict(name=name, parameters=dict(offset_object=None)))
        self.assertIsNone(mod.offset_object)

    def test_choosing_the_object_alone_enables_the_circular_array(self):
        name = modifiers.add(dict(type='ARRAY'))['modifier']
        modifiers.set_params(dict(name=name, parameters=dict(count=8)))
        modifiers.set_params(dict(name=name, parameters=dict(offset_object=self.empty.name)))
        mod = self.obj.modifiers[name]
        self.assertTrue(mod.use_object_offset); self.assertFalse(mod.use_relative_offset)
        before = [v.co.copy() for v in self.evaluated().vertices]
        # Girar el Empty después redistribuye las copias.
        self.empty.rotation_euler.z = math.radians(30)
        after = [v.co.copy() for v in self.evaluated().vertices]
        self.assertGreater(max((a - b).length for a, b in zip(before, after)), 0.1)
        # Un interruptor explícito sigue mandando.
        modifiers.set_params(dict(name=name, parameters=dict(offset_object=self.empty.name, use_relative_offset=True)))
        self.assertTrue(mod.use_relative_offset)

    def test_array_cannot_use_itself_as_offset_object(self):
        name = modifiers.add(dict(type='ARRAY'))['modifier']
        with self.assertRaises(BadPayload):
            modifiers.set_params(dict(name=name, parameters=dict(offset_object=self.obj.name)))


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    if not result.wasSuccessful(): raise SystemExit(1)
