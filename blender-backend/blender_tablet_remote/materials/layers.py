"""Persistent, independently editable paint layers over native Blender shaders."""
import json
import hashlib
import uuid
import bpy
import numpy as np
from . import recipes
from ..errors import CommandError

STACK = 'tablet_paint_stack'
PROPS = ('operation', 'blend_type', 'wave_type', 'bands_direction', 'rings_direction',
         'noise_dimensions', 'normalize', 'distance', 'feature', 'voronoi_dimensions',
         'uv_map', 'interpolation', 'extension')


def entries(material):
    if material is None: return []
    if STACK in material: return json.loads(material[STACK])
    # Read old files without changing them. Their shader groups and masks become
    # ordinary editable layers at the next write; no pixels are resampled.
    if not material.use_nodes: return []
    output = next((n for n in material.node_tree.nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output), None)
    socket = output.inputs['Surface'].links[0].from_socket if output and output.inputs['Surface'].is_linked else None
    result = []
    while socket and socket.node.type == 'MIX_SHADER':
        node = socket.node
        if not all(s.is_linked for s in node.inputs): break
        texture = node.inputs[0].links[0].from_node
        source = node.inputs[2].links[0].from_node
        if texture.type != 'TEX_IMAGE' or not texture.image or source.type != 'GROUP': break
        result.append(dict(id='legacy_'+hashlib.sha256(texture.image.name.encode()).hexdigest()[:24], label=source.node_tree.name.removeprefix('Pintura · '),
            kind='MATERIAL', color='#B8B8B8', image=texture.image.name, visible=True, opacity=1.,
            signature=material.get('tablet_top_recipe') if not result else None))
        socket = node.inputs[1].links[0].from_socket
    return list(reversed(result))


def _group(tree, socket, name):
    """Copy the reachable native shader, retaining image and immutable group references."""
    group = bpy.data.node_groups.new(name, 'ShaderNodeTree')
    group.interface.new_socket(name='Shader', in_out='OUTPUT', socket_type='NodeSocketShader')
    mapping = {}
    def visit(node):
        if node in mapping: return mapping[node]
        clone = group.nodes.new(node.bl_idname); mapping[node] = clone
        if node.type == 'GROUP': clone.node_tree = node.node_tree
        if node.type == 'TEX_IMAGE': clone.image = node.image
        for prop in PROPS:
            if hasattr(node, prop): setattr(clone, prop, getattr(node, prop))
        for i, inp in enumerate(node.inputs):
            if hasattr(inp, 'default_value'):
                try: clone.inputs[i].default_value = inp.default_value
                except (TypeError, ValueError): pass
            if inp.is_linked:
                link = inp.links[0]; parent = visit(link.from_node)
                group.links.new(parent.outputs[list(link.from_node.outputs).index(link.from_socket)], clone.inputs[i])
        return clone
    origin = visit(socket.node)
    out = group.nodes.new('NodeGroupOutput')
    group.links.new(origin.outputs[list(socket.node.outputs).index(socket)], out.inputs[0])
    return group


def sources(material, stack):
    nodes = material.node_tree.nodes
    if STACK in material:
        return {key: nodes['Source:' + key].node_tree for key in ['base'] + [e['id'] for e in stack if e['kind']=='MATERIAL']}
    output = next(n for n in nodes if n.type=='OUTPUT_MATERIAL' and n.is_active_output)
    socket = output.inputs['Surface'].links[0].from_socket
    result = {}
    for entry in reversed(stack):
        mix = socket.node
        result[entry['id']] = mix.inputs[2].links[0].from_node.node_tree
        socket = mix.inputs[1].links[0].from_socket
    result['base'] = _group(material.node_tree, socket, 'Base de pintura')
    return result


def _render_copy(source):
    group = source.copy()
    for node in group.nodes:
        if node.type == 'GROUP': node.node_tree = _render_copy(node.node_tree)
    return group


def _mask(tree, entry):
    uv = tree.nodes.new('ShaderNodeUVMap'); uv.uv_map = 'TabletPaintUV'
    texture = tree.nodes.new('ShaderNodeTexImage'); texture.image = bpy.data.images[entry['image']]
    texture.interpolation = 'Linear'; texture.extension = 'CLIP'
    tree.links.new(uv.outputs['UV'], texture.inputs['Vector'])
    amount = tree.nodes.new('ShaderNodeMath'); amount.operation = 'MULTIPLY'
    amount.inputs[1].default_value = entry['opacity'] if entry['visible'] else 0.
    tree.links.new(texture.outputs['Color'], amount.inputs[0])
    return amount.outputs[0]


def _color(tree, entry):
    # Only Base Color changes: normals, roughness, metal, coat and transmission
    # keep their original connections, including procedural grain.
    for node in list(tree.nodes):
        if node.type == 'GROUP': _color(node.node_tree, entry)
        elif node.type == 'BSDF_PRINCIPLED':
            inp = node.inputs['Base Color']; mix = tree.nodes.new('ShaderNodeMixRGB')
            mix.inputs[1].default_value = inp.default_value
            mix.inputs[2].default_value = recipes.linear(entry['color'])
            if inp.is_linked: tree.links.new(inp.links[0].from_socket, mix.inputs[1])
            tree.links.new(_mask(tree, entry), mix.inputs[0])
            tree.links.new(mix.outputs[0], inp)


def build(old, stack, templates):
    material = old.copy(); material.node_tree.nodes.clear()
    tree = material.node_tree
    # Keep templates referenced even when hidden. Rebuilding never edits a
    # committed shader or image, so Blender undo owns complete snapshots.
    for key, source in templates.items():
        if key != 'base' and not any(e['id']==key for e in stack): continue
        node = tree.nodes.new('ShaderNodeGroup'); node.name='Source:'+key; node.node_tree=source
    output = tree.nodes.new('ShaderNodeOutputMaterial')
    base = tree.nodes.new('ShaderNodeGroup'); base.node_tree = _render_copy(templates['base'])
    rendered = [base.node_tree]; socket = base.outputs[0]
    for entry in stack:
        if entry['kind'] == 'COLOR':
            for group in rendered: _color(group, entry)
        else:
            layer = tree.nodes.new('ShaderNodeGroup'); layer.node_tree = _render_copy(templates[entry['id']])
            rendered.append(layer.node_tree)
            mix = tree.nodes.new('ShaderNodeMixShader')
            tree.links.new(_mask(tree, entry), mix.inputs[0])
            tree.links.new(socket, mix.inputs[1]); tree.links.new(layer.outputs[0], mix.inputs[2]); socket=mix.outputs[0]
    tree.links.new(socket, output.inputs['Surface'])
    if material.use_raytrace_refraction: recipes.configure_transmission(material)
    material[STACK] = json.dumps(stack)
    material['tablet_layers'] = len(stack)
    for key in ('tablet_top_mask','tablet_top_recipe'):
        if key in material: del material[key]
    if stack:
        material['tablet_top_mask']=stack[-1]['image']
        material['tablet_top_recipe']=stack[-1].get('signature') or ''
    return material


def make_layer(obj, recipe, tint, *, erase=False, kind='MATERIAL', active=None, fresh=False):
    from .painting import SIZE, MAX_LAYERS
    old = obj.data.materials[0]; stack=entries(old)
    chosen = next((e for e in stack if e['id']==active), None)
    if active and chosen is None: raise CommandError('La capa ya no existe; elige otra', code='paint_layer_missing')
    color=tint or recipe['color']
    source = recipes.compile_material(recipe, tint) if kind=='MATERIAL' else None
    signature=source[recipes.KEY] if source else 'COLOR:'+color
    if chosen is None and stack and not fresh and (erase or stack[-1].get('signature')==signature): chosen=stack[-1]
    if erase and chosen is None: raise CommandError('No hay una capa que borrar', code='paint_layer_missing')
    if chosen and not chosen['visible']: raise CommandError('Muestra la capa antes de pintar', code='paint_layer_hidden')
    if chosen is None and len(stack)>=MAX_LAYERS:
        raise CommandError('Máximo ocho capas; elimina una desde Capas', code='paint_layer_limit')
    templates=sources(old,stack)
    image=None; material=None
    try:
        if chosen:
            previous=bpy.data.images[chosen['image']]; image=previous.copy()
            pixels=np.empty(len(previous.pixels),dtype=np.float32); previous.pixels.foreach_get(pixels)
            image.pixels.foreach_set(pixels); chosen['image']=image.name
        else:
            image=bpy.data.images.new('Pintura · '+obj.name,width=SIZE,height=SIZE,alpha=False)
            image.colorspace_settings.name='Non-Color'
            pixels=np.zeros(SIZE*SIZE*4,dtype=np.float32); image.pixels.foreach_set(pixels)
            chosen=dict(id=uuid.uuid4().hex,label=('Pintura '+str(len(stack)+1)) if kind=='COLOR' else recipe['label'],
                        kind=kind,color=color,image=image.name,visible=True,opacity=1.,signature=signature)
            stack.append(chosen)
            if source:
                output=next(n for n in source.node_tree.nodes if n.type=='OUTPUT_MATERIAL' and n.is_active_output)
                templates[chosen['id']]=_group(source.node_tree,output.inputs['Surface'].links[0].from_socket,recipe['label'])
        image.pack()
        material=build(old,stack,templates)
        if source and source.use_raytrace_refraction: recipes.configure_transmission(material)
        material['tablet_active_layer']=chosen['id']
        obj.data.materials[0]=material
        return material,image,pixels
    except Exception:
        if material: dispose(material)
        if image and image.users==0: bpy.data.images.remove(image)
        raise


def dispose(material):
    """Release only unreferenced temporary shaders, recursively."""
    groups=[n.node_tree for n in material.node_tree.nodes if n.type=='GROUP']
    bpy.data.materials.remove(material)
    def remove(group):
        if group.users: return
        children=[n.node_tree for n in group.nodes if n.type=='GROUP']
        bpy.data.node_groups.remove(group)
        for child in children:
            try: remove(child)
            except ReferenceError: pass
    for group in groups:
        try: remove(group)
        except ReferenceError: pass
