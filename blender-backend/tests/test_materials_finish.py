"""blender -b --factory-startup --python-exit-code 1 --python tests/test_materials_finish.py"""
import sys
import unittest
from pathlib import Path
import json
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.materials import recipes
from blender_tablet_remote.materials.runtime import runtime
from blender_tablet_remote.commands import material
from blender_tablet_remote.errors import BadPayload


class FinishTests(unittest.TestCase):
    def setUp(self):
        runtime.leave()
        bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add()
        self.obj=bpy.context.object
        bpy.context.scene.pop(recipes.CATALOG_KEY,None)
        runtime.enter('test')
        runtime.preset='plastic';runtime.tint=None;runtime.finish='natural'
        runtime.surface={};runtime.grain='none'

    def tearDown(self):
        runtime.leave()
        bpy.context.scene.pop(recipes.CATALOG_KEY,None)

    def settings(self,**payload): return material.settings(dict(payload,_client_id='test'))

    def test_material_keeps_its_own_colour_until_a_tint_is_chosen(self):
        self.settings(preset='gold')
        self.assertEqual(runtime.status()['color'],'#EBC16B')
        self.assertFalse(runtime.status()['tinted'])
        runtime.apply()
        self.assertEqual(json.loads(self.obj.data.materials[0][recipes.KEY])['color'],'#EBC16B')
        # Un tinte explícito manda, y sobrevive al cambio de material.
        self.settings(color='#2255CC')
        self.assertTrue(runtime.status()['tinted'])
        self.settings(preset='iron')
        self.assertEqual(runtime.status()['color'],'#2255CC')
        # `color: null` devuelve cada material a su propio color: se puede simular otro.
        self.settings(color=None)
        self.assertEqual(runtime.status()['color'],'#74787E')
        self.settings(preset='gold')
        self.assertEqual(runtime.status()['color'],'#EBC16B')

    def test_finishes_write_only_their_own_parameters_and_survive_the_catalog(self):
        self.settings(preset='plastic',finish='metal')
        surface=runtime.status()['surface']
        self.assertEqual(surface['metallic'],1.)
        self.assertEqual(surface['coat'],.2)  # el barniz del plástico sigue siendo suyo
        self.settings(finish='translucent')
        self.assertEqual(runtime.status()['surface']['transmission'],1.)
        self.assertEqual(runtime.status()['surface']['metallic'],0.)
        self.assertEqual(next(r for r in recipes.catalog() if r['id']=='plastic')['surface']['metallic'],0.)
        with self.assertRaises(BadPayload): self.settings(finish='chrome')

    def test_loose_adjustments_beat_the_finish_and_a_finish_clears_them(self):
        self.settings(finish='polished')
        self.settings(surface={'roughness':.9,'metallic':.5})
        self.assertEqual(runtime.status()['surface']['roughness'],.9)
        self.assertTrue(runtime.status()['custom'])
        self.assertEqual(runtime.status()['finish'],'polished')
        self.settings(finish='polished')
        self.assertEqual(runtime.status()['surface']['roughness'],.12)
        self.assertFalse(runtime.status()['custom'])
        with self.assertRaises(BadPayload): self.settings(surface={'sheen':.5})
        with self.assertRaises(BadPayload): self.settings(surface={'ior':9.})

    def test_grain_adds_one_layer_over_the_recipe_without_touching_it(self):
        self.settings(preset='wood',grain='bands',grain_scale=60,grain_amount=.8,grain_relief=1.)
        recipe=runtime.selected_recipe()
        self.assertEqual(len(recipe['patterns']),2)   # las vetas de la madera siguen ahí
        added=recipe['patterns'][-1]
        self.assertEqual(added['kind'],'bands')
        self.assertEqual(added['bump'],recipes.GRAIN_MAX_BUMP)
        self.assertEqual(added['color'],recipes.shade('#B87D43',.45))
        self.assertEqual(len(next(r for r in recipes.catalog() if r['id']=='wood')['patterns']),1)
        recipes.compile_material(recipe)
        self.settings(grain='none')
        self.assertEqual(len(runtime.selected_recipe()['patterns']),1)
        with self.assertRaises(BadPayload): self.settings(grain='marble')

    def test_saving_keeps_what_is_on_screen_and_never_collides(self):
        self.settings(preset='iron',color='#B03A2E',finish='metal',surface={'roughness':.35},
                      grain='noise',grain_amount=.6)
        material.save_recipe({'_client_id':'test','label':'Hierro pintado'})
        saved=json.loads(bpy.context.scene[recipes.CATALOG_KEY])
        self.assertEqual(list(saved),['hierro-pintado'])
        self.assertEqual(saved['hierro-pintado']['color'],'#B03A2E')
        self.assertEqual(saved['hierro-pintado']['surface']['roughness'],.35)
        self.assertEqual(len(saved['hierro-pintado']['patterns']),1)
        # Queda seleccionado y en limpio: seguir tocando no aplica el grano dos veces.
        self.assertEqual(runtime.preset,'hierro-pintado')
        self.assertIsNone(runtime.tint)
        self.assertEqual(runtime.grain,'none')
        self.assertEqual(runtime.status()['color'],'#B03A2E')
        self.assertEqual(len(runtime.selected_recipe()['patterns']),1)
        material.save_recipe({'_client_id':'test','label':'Hierro pintado'})
        self.assertEqual(sorted(json.loads(bpy.context.scene[recipes.CATALOG_KEY])),
                         ['hierro-pintado','hierro-pintado-2'])
        with self.assertRaises(BadPayload): material.save_recipe({'_client_id':'test','label':'  '})

    def test_state_survives_a_preset_the_open_file_no_longer_has(self):
        self.settings(preset='plastic',finish='metal')
        runtime.preset='ghost'
        status=runtime.status()   # el snapshot de escena no puede romperse por esto
        self.assertEqual(status['color'],'#B8B8B8')
        self.assertEqual(status['surface']['metallic'],1.)
        with self.assertRaises(BadPayload): self.settings()
        self.settings(preset='gold')
        self.assertEqual(runtime.status()['color'],'#EBC16B')

    def test_saved_material_applies_and_paints_like_any_other_preset(self):
        self.settings(preset='gold',finish='worn',grain='bands',grain_amount=.7)
        material.save_recipe({'_client_id':'test','label':'Oro cepillado'})
        runtime.apply()
        stored=json.loads(self.obj.data.materials[0][recipes.KEY])
        self.assertEqual(stored['color'],'#EBC16B')
        self.assertEqual(stored['surface']['roughness'],.8)
        self.assertEqual(stored['surface']['metallic'],1.)
        self.assertEqual(len(stored['patterns']),1)
        self.assertTrue(runtime.status()['paint_ready'])


if __name__=='__main__':
    unittest.main(argv=[__file__],verbosity=2,exit=True)
