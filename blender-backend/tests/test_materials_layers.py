"""Native regressions for editable paint stacks and continuous UV charts."""
import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import bpy
import bmesh
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.materials import painting, layers, recipes
from blender_tablet_remote.materials.runtime import runtime
from blender_tablet_remote.commands import material
from blender_tablet_remote.errors import BadPayload, CommandError


def shaders(tree):
    for node in tree.nodes:
        if node.type=='BSDF_PRINCIPLED': yield node
        if node.type=='GROUP' and not node.name.startswith('Source:'): yield from shaders(node.node_tree)


class PaintLayersTests(unittest.TestCase):
    def setUp(self):
        runtime.leave()
        bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add(); self.obj=bpy.context.object
        runtime.enter('test'); runtime.preset='iron'; runtime.tint=None; runtime.finish='satin'
        runtime.surface={}; runtime.grain='noise'; runtime.erase=False
        runtime.apply(); painting.atlas(self.obj)

    def tearDown(self): runtime.leave()

    def add(self, color, kind='COLOR'):
        mat,img,pixels=painting.make_layer(self.obj,runtime.selected_recipe(),color,kind=kind)
        pixels[::4]=.7; pixels[1::4]=.7; pixels[2::4]=.7
        img.pixels.foreach_set(pixels); img.pack()
        return mat,img,layers.entries(mat)[-1]['id']

    def command(self, action, ident=None, **args):
        return material.layer(dict(_client_id='test',action=action,layer_id=ident,**args))

    def test_color_keeps_every_surface_parameter_and_bump(self):
        old=self.obj.data.materials[0]
        original=next(n for n in old.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
        expected={k:original.inputs[k].default_value for k in ('Metallic','Roughness','Coat Weight','Transmission Weight','IOR')}
        mat,img,_=self.add('#2244FF')
        painted=list(shaders(mat.node_tree)); self.assertEqual(len(painted),1)
        for key,value in expected.items(): self.assertEqual(painted[0].inputs[key].default_value,value)
        self.assertTrue(painted[0].inputs['Normal'].is_linked)
        self.assertEqual(painted[0].inputs['Normal'].links[0].from_node.type,'BUMP')
        self.assertEqual(painted[0].inputs['Base Color'].links[0].from_node.type,'MIX_RGB')
        self.assertNotEqual(original.inputs['Base Color'].links[0].from_node,painted[0].inputs['Base Color'].links[0].from_node)
        self.assertEqual(old.get('tablet_layers',0),0)

    def test_edit_lower_layer_preserves_upper_pixels_and_cancel_restores(self):
        _,first,low=self.add('#FF0000'); _,upper,high=self.add('#00FF00')
        before=np.array(upper.pixels[:]); old=self.obj.data
        self.command('select',low)
        runtime.frame=(np.full((64,64),.5),np.eye(4),64,64); runtime.erase=True
        runtime.begin(dict(stroke_id='erase',_client_id='test'))
        record=runtime.stroke['objects'][0]
        self.assertEqual(layers.entries(record['material'])[0]['id'],low)
        self.assertNotEqual(record['image'].name,first.name)
        self.assertEqual(layers.entries(record['material'])[-1]['image'],upper.name)
        record['pixels'][::4]=0
        painting.publish_mask(record['image'],record['pixels'],record['padding_indexes'])
        np.testing.assert_array_equal(before,np.array(upper.pixels[:]))
        self.assertAlmostEqual(first.pixels[0],.7,places=2)
        runtime.cancel(); self.assertIs(self.obj.data,old)

    def test_visibility_opacity_delete_are_isolated_and_undo_once(self):
        old,_,low=self.add('#112233'); _,upper,high=self.add('#445566')
        shared=self.obj.copy(); bpy.context.collection.objects.link(shared); shared.data=self.obj.data
        original=shared.data.materials[0]
        with patch('blender_tablet_remote.materials.runtime.undo_push') as undo:
            self.command('set',low,visible=False,opacity=.25)
            undo.assert_called_once()
        stack=layers.entries(self.obj.data.materials[0]); self.assertFalse(stack[0]['visible'])
        self.assertEqual(stack[0]['opacity'],.25); self.assertEqual(stack[1]['image'],upper.name)
        self.assertTrue(layers.entries(original)[0]['visible'])
        self.command('select',low); self.command('delete',low)
        self.assertEqual([e['id'] for e in layers.entries(self.obj.data.materials[0])],[high])
        self.assertIsNone(runtime.active_layer)
        self.assertEqual(len(layers.entries(shared.data.materials[0])),2)

    def test_invalid_and_hidden_layer_do_not_change_material(self):
        old,_,ident=self.add('#FF0000')
        with self.assertRaises(BadPayload): self.command('set',ident,opacity=float('nan'))
        self.assertIs(self.obj.data.materials[0],old)
        self.command('set',ident,visible=False); self.command('select',ident)
        before=self.obj.data
        runtime.frame=(np.full((64,64),.5),np.eye(4),64,64)
        with self.assertRaises(CommandError): runtime.begin(dict(stroke_id='hidden'))
        self.assertIs(self.obj.data,before)
        self.assertIsNone(runtime.stroke)
        with self.assertRaises(CommandError): material.layer(dict(_client_id='other',action='delete',layer_id=ident))

    def test_uv_is_continuous_across_coplanar_faces_and_preserves_user_selection(self):
        bpy.ops.mesh.primitive_grid_add(x_subdivisions=30,y_subdivisions=30,size=2)
        obj=bpy.context.object; mesh=obj.data
        user_uv=mesh.uv_layers.new(name='User UV'); original=[d.uv[:] for d in user_uv.data]
        for face in mesh.polygons: face.select=face.index%2==0
        selected=[p.select for p in mesh.polygons]
        painting.prepare_uv(obj)
        self.assertEqual(obj.mode,'OBJECT'); self.assertIs(bpy.context.view_layer.objects.active,obj)
        self.assertEqual(selected,[p.select for p in mesh.polygons])
        self.assertEqual(original,[d.uv[:] for d in mesh.uv_layers['User UV'].data])
        uv=mesh.uv_layers[painting.UV_NAME]; positions={}
        for loop in mesh.loops:
            positions.setdefault(loop.vertex_index,[]).append(np.array(uv.data[loop.index].uv[:]))
        self.assertTrue(all(np.max(np.ptp(values,axis=0))<1e-5 for values in positions.values()))
        coords=np.array([d.uv[:] for d in uv.data]); self.assertGreater(np.prod(np.ptp(coords,axis=0)),.8)

    def test_gutter_extension_never_changes_other_surface_pixels(self):
        image=bpy.data.images.new('gutter',width=8,height=8)
        try:
            pixels=np.zeros(8*8*4,dtype=np.float32); pixels[9*4:9*4+3]=1
            painting.publish_mask(image,pixels,np.array([9,10]))
            output=np.array(image.pixels[:])[::4]
            self.assertEqual(output[9],1); self.assertEqual(output[10],0)
            self.assertGreater(output[8],0)
        finally: bpy.data.images.remove(image)

    def test_new_layer_survives_brush_configuration_and_same_color(self):
        _,_,first=self.add('#112233')
        self.command('new')
        material.settings(dict(_client_id='test',color='#112233',paint_kind='COLOR'))
        self.assertTrue(runtime.fresh_layer)
        runtime.frame=(np.full((64,64),.5),np.eye(4),64,64)
        runtime.begin(dict(stroke_id='new'))
        record=runtime.stroke['objects'][0]
        self.assertEqual(len(layers.entries(record['material'])),2)
        self.assertNotEqual(record['material']['tablet_active_layer'],first)
        runtime.cancel()

    def test_legacy_shader_layers_migrate_without_losing_pixels_or_surface(self):
        old=self.obj.data.materials[0].copy(); tree=old.node_tree
        output=next(n for n in tree.nodes if n.type=='OUTPUT_MATERIAL')
        baseline=output.inputs['Surface'].links[0].from_socket
        source=bpy.data.node_groups.new('Pintura · Óxido antiguo','ShaderNodeTree')
        source.interface.new_socket(name='Shader',in_out='OUTPUT',socket_type='NodeSocketShader')
        shader=source.nodes.new('ShaderNodeBsdfPrincipled'); shader.inputs['Roughness'].default_value=.83
        gout=source.nodes.new('NodeGroupOutput'); source.links.new(shader.outputs[0],gout.inputs[0])
        group=tree.nodes.new('ShaderNodeGroup'); group.node_tree=source
        image=bpy.data.images.new('LegacyMask',width=painting.SIZE,height=painting.SIZE)
        values=np.full(painting.SIZE**2*4,.35,dtype=np.float32); image.pixels.foreach_set(values); image.pack()
        tex=tree.nodes.new('ShaderNodeTexImage'); tex.image=image
        uv=tree.nodes.new('ShaderNodeUVMap'); uv.uv_map=painting.UV_NAME
        tree.links.new(uv.outputs[0],tex.inputs['Vector'])
        mix=tree.nodes.new('ShaderNodeMixShader')
        tree.links.new(tex.outputs['Color'],mix.inputs[0]); tree.links.new(baseline,mix.inputs[1])
        tree.links.new(group.outputs[0],mix.inputs[2]); tree.links.new(mix.outputs[0],output.inputs['Surface'])
        values=np.array(image.pixels[:])
        old['tablet_layers']=1; old['tablet_top_mask']=image.name; old['tablet_top_recipe']='legacy'
        self.obj.data.materials[0]=old
        entry=layers.entries(old)[0]; self.assertEqual(entry['label'],'Óxido antiguo')
        self.command('set',entry['id'],opacity=.5)
        migrated=self.obj.data.materials[0]
        self.assertEqual(layers.entries(migrated)[0]['image'],image.name)
        np.testing.assert_array_equal(np.array(image.pixels[:]),values)
        self.assertTrue(any(abs(n.inputs['Roughness'].default_value-.83)<1e-6 for n in shaders(migrated.node_tree)))
        self.assertNotIn(layers.STACK,old)

    def test_saved_stack_can_edit_lower_layer_after_reload(self):
        _,_,low=self.add('#AA1122'); _,_,high=self.add('#22AA11')
        self.command('set',high,opacity=.4)
        path=str(Path(tempfile.mkdtemp())/'layers.blend'); name=self.obj.name
        runtime.leave(); bpy.ops.wm.save_as_mainfile(filepath=path); bpy.ops.wm.open_mainfile(filepath=path)
        self.obj=bpy.data.objects[name]; runtime.enter('test')
        stack=layers.entries(self.obj.data.materials[0])
        self.assertEqual([e['id'] for e in stack],[low,high]); self.assertEqual(stack[-1]['opacity'],.4)
        self.assertTrue(all(bpy.data.images[e['image']].packed_file for e in stack))
        self.command('delete',low); self.assertEqual(len(layers.entries(self.obj.data.materials[0])),1)


result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PaintLayersTests))
if not result.wasSuccessful(): raise SystemExit(1)
