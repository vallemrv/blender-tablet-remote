"""blender -b --factory-startup --python-exit-code 1 --python tests/test_materials.py"""
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
import json
import math
import bpy
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.materials import recipes, painting
from blender_tablet_remote.materials.runtime import runtime
from blender_tablet_remote.commands import material
from blender_tablet_remote.errors import BadPayload, CommandError

class MaterialsTests(unittest.TestCase):
    def setUp(self):
        runtime.leave()
        bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add()
        self.obj=bpy.context.object
        runtime.enter('test')
        runtime.preset='wood';runtime.tint='#B87D43';runtime.erase=False;runtime.finish='natural'

    def tearDown(self): runtime.leave()

    def test_wireframe_requests_are_normalized_to_solid_only_in_materials(self):
        from blender_tablet_remote.commands import view
        shading=SimpleNamespace(type='SOLID',show_xray_wireframe=False,xray_alpha_wireframe=.2)
        space=SimpleNamespace(shading=shading)
        with patch.object(view,'_shading_space',return_value=(None,space)):
            for mode in ('WIREFRAME','TOGGLE','SOLID'):
                self.assertEqual(view.shading({'mode':mode})['shading'],'SOLID')
                self.assertEqual(shading.type,'SOLID')
            runtime.leave()
            self.assertEqual(view.shading({'mode':'WIREFRAME'})['shading'],'WIREFRAME')
            self.assertTrue(shading.show_xray_wireframe)

    def test_paint_capture_never_restores_wireframe_even_after_failure(self):
        shading=SimpleNamespace(type='WIREFRAME',use_scene_lights=True,use_scene_world=True,
            studio_light='studio.exr',studiolight_intensity=.7,studiolight_rotate_z=.3,
            studiolight_background_alpha=.4,studiolight_background_blur=.2)
        space=SimpleNamespace(shading=shading,overlay=SimpleNamespace(show_overlays=True),show_gizmo=True)
        before=vars(shading).copy(); before['type']='SOLID'
        for _ in range(2):
            with self.assertRaises(RuntimeError):
                with runtime.presentation(space):
                    self.assertEqual(shading.type,'MATERIAL')
                    raise RuntimeError('capture interrupted')
            self.assertEqual(vars(shading),before)
            self.assertTrue(space.overlay.show_overlays); self.assertTrue(space.show_gizmo)
        runtime.leave(); shading.type='WIREFRAME'
        with runtime.presentation(space): self.assertEqual(shading.type,'WIREFRAME')
        self.assertEqual(shading.type,'WIREFRAME')

    def test_all_presets_compile_and_invalid_recipe_is_atomic(self):
        for recipe in recipes.BUILTINS:
            mat=recipes.compile_material(recipe)
            self.assertTrue(mat.use_nodes)
        before=len(bpy.data.materials)
        r=dict(recipes.BUILTINS[0],surface={'roughness':float('nan')})
        with self.assertRaises(BadPayload):recipes.compile_material(r)
        self.assertEqual(len(bpy.data.materials),before)
        with self.assertRaises(BadPayload):recipes.validate(dict(recipes.BUILTINS[0],python='print(1)'))

    def test_apply_multiple_objects_does_not_modify_linked_unselected(self):
        second=self.obj.copy();bpy.context.collection.objects.link(second);second.select_set(True)
        hidden=self.obj.copy();bpy.context.collection.objects.link(hidden);hidden.select_set(False)
        original=hidden.data
        runtime.leave();runtime.enter('test');runtime.apply()
        self.assertEqual(len(runtime.objects()),2)
        self.assertEqual(len(hidden.data.materials),0)
        self.assertIs(hidden.data,original)
        self.assertIsNot(self.obj.data,original)
        self.assertIsNot(self.obj.data,second.data)

    def test_atlas_preserves_original_uv_and_layer_compiles_every_recipe(self):
        runtime.apply()
        old_uv=[v.uv[:] for v in self.obj.data.uv_layers.active.data]
        indexes,positions=painting.atlas(self.obj)
        self.assertGreater(len(indexes),100000)
        self.assertTrue(np.isfinite(positions).all())
        self.assertEqual(old_uv,[v.uv[:] for v in self.obj.data.uv_layers[0].data])
        for recipe in recipes.BUILTINS:
            self.obj.data.materials[0]=recipes.compile_material(recipe)
            mat,image,pixels=painting.make_layer(self.obj,recipe,recipe['color'])
            self.assertEqual(mat['tablet_layers'],1)
            self.assertEqual(len(pixels),painting.SIZE**2*4)
            self.assertTrue(image.packed_file)

    def test_cancel_restores_mesh_and_discards_mask_without_undo(self):
        runtime.apply();old=self.obj.data
        runtime.frame=(np.full((64,64),.5),np.eye(4),64,64)
        before=set(bpy.data.images.keys())
        runtime.begin({'stroke_id':'s1','_client_id':'test'})
        self.assertIsNot(self.obj.data,old)
        runtime.cancel()
        self.assertIs(self.obj.data,old)
        self.assertEqual(set(bpy.data.images.keys()),before)
        self.assertIsNone(runtime.stroke)

    def test_depth_masks_occluded_pixels_and_preserves_zero_pressure(self):
        indexes=np.array([0,1,2]);positions=np.array([[0,0,0],[0,0,.6],[.8,0,0]])
        frame=(np.full((10,10),.5),np.eye(4),10,10)
        pixels=np.zeros(12,dtype=np.float32)
        self.assertFalse(painting.paint_pixels(indexes,positions,pixels,frame,[dict(u=.5,v=.5,pressure=0)],.2,1))
        self.assertTrue(painting.paint_pixels(indexes,positions,pixels,frame,[dict(u=.5,v=.5,pressure=1)],.2,1))
        self.assertEqual(pixels[0],1)
        self.assertEqual(pixels[4],0)
        self.assertEqual(pixels[8],0)

    def test_subpixel_depth_does_not_paint_through_a_thin_wall(self):
        # The back sample differs by only 1e-5 in depth; the old coarse tolerance
        # would consider it visible. A sloped front sample needs interpolation.
        yy,xx=np.mgrid[:10,:10]
        depth=.5+xx*.001
        positions=np.array([[0,0,.009],[0,0,.00902]])
        pixels=np.zeros(8,dtype=np.float32)
        painting.paint_pixels(np.array([0,1]),positions,pixels,(depth,np.eye(4),10,10),[dict(u=.5,v=.5,pressure=1)],.2,1)
        self.assertEqual(pixels[0],1)
        self.assertEqual(pixels[4],0)

    def test_examples_and_finish_compile_without_changing_recipe(self):
        folder=Path(__file__).resolve().parents[2]/'docs/material-examples'
        for path in folder.glob('*.json'):
            recipes.compile_material(json.loads(path.read_text()))
        original=runtime.selected_recipe()['surface']['roughness']
        material.settings({'_client_id':'test','finish':'polished'})
        self.assertEqual(runtime.selected_recipe()['surface']['roughness'],.12)
        self.assertEqual(next(r for r in recipes.catalog() if r['id']=='wood')['surface']['roughness'],original)
        before=runtime.status()
        with self.assertRaises(BadPayload):material.settings({'_client_id':'test','color':'#112233','radius':float('inf')})
        self.assertEqual(runtime.status(),before)

    def test_repeated_material_reuses_logical_layer_and_erasing_is_reversible(self):
        runtime.apply()
        painting.atlas(self.obj)
        recipe=runtime.selected_recipe()
        mat,image,pixels=painting.make_layer(self.obj,recipe,'#112233')
        pixels[0:3]=1;image.pixels.foreach_set(pixels);image.pack()
        next_mat,next_image,next_pixels=painting.make_layer(self.obj,recipe,'#112233')
        self.assertEqual(next_mat['tablet_layers'],1)
        self.assertNotEqual(image.name,next_image.name)
        self.assertEqual(next_pixels[0],1)
        frame=(np.full((10,10),.5),np.eye(4),10,10)
        painting.paint_pixels(np.array([0]),np.array([[0,0,0]]),next_pixels,frame,[dict(u=.5,v=.5,pressure=1)],.2,1,erase=True)
        self.assertEqual(next_pixels[0],0)
        self.assertEqual(image.pixels[0],1)

    def test_atlas_samples_evaluated_subdivision_surface(self):
        runtime.apply()
        mod=self.obj.modifiers.new('Detail','SUBSURF');mod.levels=1
        indexes,positions=painting.atlas(self.obj)
        self.assertGreater(len(indexes),10000)
        # A subdivided cube no longer reaches the base cube's corner (+1,+1,+1).
        self.assertLess(np.max(np.linalg.norm(positions,axis=1)),1.6)

    def test_preset_preserves_custom_tint_and_finish_unless_explicit(self):
        material.settings({'_client_id':'test','color':'#DD1122','finish':'polished'})
        material.settings({'_client_id':'test','preset':'iron'})
        self.assertEqual(runtime.tint,'#DD1122')
        self.assertEqual(runtime.finish,'polished')
        runtime.apply()
        recipe=json.loads(self.obj.data.materials[0][recipes.KEY])
        self.assertEqual(recipe['color'],'#DD1122')
        self.assertEqual(recipe['surface']['metallic'],1.)
        material.settings({'_client_id':'test','preset':'rust','color':'#A34C24'})
        self.assertEqual(runtime.tint,'#A34C24')
        self.assertEqual(runtime.preset,'rust')

    def test_details_mix_above_red_metal_base_without_replacing_it(self):
        runtime.preset='iron'; runtime.tint='#DD1122'; runtime.apply()
        base=self.obj.data.materials[0]
        painting.atlas(self.obj)
        for ident in ('rust','dirt','scratches'):
            recipe=next(r for r in recipes.BUILTINS if r['id']==ident)
            mat,image,pixels=painting.make_layer(self.obj,recipe,recipe['color'])
            self.assertEqual(json.loads(mat[recipes.KEY])['color'],'#DD1122')
        self.assertEqual(mat['tablet_layers'],3)
        self.assertEqual(json.loads(base[recipes.KEY])['id'],'iron')

    def test_atlas_cache_survives_mesh_copy_and_invalidates_geometry_change(self):
        runtime.apply(); cache={}
        a,b=painting.atlas(self.obj,cache)
        self.obj.data=self.obj.data.copy()
        aa,bb=painting.atlas(self.obj,cache)
        self.assertIs(a,aa); self.assertIs(b,bb)
        self.obj.data.vertices[0].co.x+=.1; self.obj.data.update(); bpy.context.view_layer.update()
        aaa,bbb=painting.atlas(self.obj,cache)
        self.assertIsNot(bb,bbb)
        self.assertFalse(np.array_equal(b,bbb))

    def test_projected_tiles_match_exhaustive_brush_and_report_cost(self):
        import time
        side=512; yy,xx=np.mgrid[:side,:side]
        sx=(xx.ravel()+.5)/side; sy=(yy.ravel()+.5)/side
        positions=np.column_stack((2*sx-1,1-2*sy,np.zeros(side*side)))
        indexes=np.arange(side*side); frame=(np.full((side,side),.5),np.eye(4),side,side)
        points=[dict(u=.15+i*.7/127,v=.5+.1*math.sin(i/10),pressure=.2+.8*i/127) for i in range(128)]
        radius=.025; strength=.7
        pixels=np.zeros(side*side*4,dtype=np.float32)
        start=time.perf_counter(); projection=painting.project_surface(indexes,positions,frame)
        projected=time.perf_counter()-start
        start=time.perf_counter(); painting.paint_projected(projection,pixels,points,radius,strength)
        tiled=time.perf_counter()-start
        expected=np.zeros(side*side,dtype=np.float32)
        start=time.perf_counter()
        for p in points:
            distance=np.hypot(sx-p['u'],sy-p['v'])
            amount=np.clip((1-distance/radius)*4,0,1)*strength*p['pressure']
            expected=np.maximum(expected,amount).astype(np.float32)
        exhaustive=time.perf_counter()-start
        np.testing.assert_allclose(pixels[::4],expected,atol=1e-6)
        print(f'PAINT BENCH {side*side} texels / 128 dabs: projection={projected*1000:.1f} ms; tiles={tiled*1000:.1f} ms; exhaustive={exhaustive*1000:.1f} ms',flush=True)

    def test_import_is_persistent_and_owner_protected(self):
        r=dict(recipes.BUILTINS[0],id='custom-stone',label='Piedra azul')
        with self.assertRaises(CommandError):material.import_recipe({'recipe':r,'_client_id':'other'})
        material.import_recipe({'recipe':r,'_client_id':'test'})
        self.assertEqual(json.loads(bpy.context.scene[recipes.CATALOG_KEY])[r['id']]['label'],r['label'])
        self.assertEqual(runtime.preset,r['id'])
        with self.assertRaises(BadPayload):material.import_recipe({'recipe':recipes.BUILTINS[0],'_client_id':'test'})

result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(MaterialsTests))
if not result.wasSuccessful():raise SystemExit(1)
