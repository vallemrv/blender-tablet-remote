"""UV mask painting against the exact depth and camera of the tablet frame.

A private UV atlas avoids touching artist UVs. Masks mix complete native shaders,
so the same brush can paint a color, wood, glass or any imported recipe.
"""
import math
import hashlib
import bpy
import numpy as np
from ..errors import CommandError
from .recipes import compile_material, configure_transmission, KEY

UV_NAME = 'TabletPaintUV'
SIZE = 1024
MAX_LAYERS = 8
MAX_BASE_FACES = 20000
REGION_ATTRIBUTE = '.tablet_paint_region'


def check_size(obj):
    count=len(obj.data.polygons)
    if count>MAX_BASE_FACES:
        raise CommandError(f'{obj.name}: {count:,} caras base. El pincel admite 20 000; puedes aplicar la base '
                           'al objeto completo o pintar una base simplificada con Subdivisión sin aplicar.', code='paint_mesh_limit')


def atlas(obj, cache=None, scope='ALL'):
    """The face mask propagates through modifiers; never indexes evaluated faces as base faces."""
    check_size(obj)
    if scope=='ALL': return _atlas(obj,cache)
    mesh=obj.data
    if scope=='SELECTED':
        selected=[p.select for p in mesh.polygons]
    else:
        group=obj.vertex_groups.get(scope.removeprefix('GROUP:'))
        if group is None: raise CommandError('Este objeto no tiene el grupo elegido',code='paint_region_missing')
        vertices={v.index for v in mesh.vertices if any(g.group==group.index and g.weight>0 for g in v.groups)}
        selected=[all(v in vertices for v in p.vertices) for p in mesh.polygons]
    if not any(selected): raise CommandError('La zona no contiene caras completas. Selecciónalas en Edit o elige otro grupo.',code='paint_region_empty')
    attribute=mesh.attributes.new(REGION_ATTRIBUTE,'FLOAT','FACE')
    name=attribute.name
    try:
        attribute.data.foreach_set('value',selected); mesh.update()
        return _atlas(obj,cache,region=name)
    finally:
        mesh.attributes.remove(mesh.attributes[name]); mesh.update()


def surface_key(obj, mesh=None, *, include_uv=False):
    """Content identity survives per-stroke mesh copies and detects desktop edits."""
    if mesh is None: mesh=obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
    digest=hashlib.blake2b(digest_size=16)
    coords=np.empty(len(mesh.vertices)*3,dtype=np.float32); mesh.vertices.foreach_get('co',coords)
    loops=np.empty(len(mesh.loops),dtype=np.int32); mesh.loops.foreach_get('vertex_index',loops)
    starts=np.empty(len(mesh.polygons),dtype=np.int32); mesh.polygons.foreach_get('loop_start',starts)
    for array in (coords,loops,starts,np.asarray(obj.matrix_world,dtype=np.float32)): digest.update(array.tobytes())
    if include_uv:
        uv=mesh.uv_layers.get(UV_NAME)
        if uv is None: raise CommandError('El modificador no conserva la superficie pintable',code='paint_uv_missing')
        values=np.empty(len(uv.data)*2,dtype=np.float32); uv.data.foreach_get('uv',values); digest.update(values.tobytes())
    return digest.digest()


def _atlas(obj, cache=None, region=None):
    mesh = obj.data
    uv = mesh.uv_layers.get(UV_NAME)
    if uv is None:
        uv = mesh.uv_layers.new(name=UV_NAME)
        grid = math.ceil(math.sqrt(max(1, len(mesh.polygons))))
        tile = 1 / grid
        margin = min(2 / SIZE, tile * .15)
        for poly in mesh.polygons:
            axis = max(range(3), key=lambda i: abs(poly.normal[i]))
            axes = [i for i in range(3) if i != axis]
            points = np.array([[mesh.vertices[mesh.loops[l].vertex_index].co[a] for a in axes] for l in poly.loop_indices])
            lo, hi = points.min(axis=0), points.max(axis=0)
            span = max(float((hi-lo).max()), 1e-12)
            origin = np.array([poly.index % grid, poly.index // grid]) * tile + margin
            coords = origin + (points-lo) / span * (tile - margin*2)
            for l, co in zip(poly.loop_indices, coords): uv.data[l].uv = co
        mesh.update()
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.data
    if len(mesh.polygons) > 200000:
        raise CommandError('Baja el nivel de detalle visible para pintar (máximo 200 000 caras evaluadas)', code='paint_mesh_limit')
    uv = mesh.uv_layers.get(UV_NAME)
    if uv is None: raise CommandError('El modificador no conserva la superficie pintable', code='paint_uv_missing')
    key=surface_key(obj,mesh,include_uv=True)
    mask=None
    if region:
        attr=mesh.attributes.get(region)
        if attr is None: raise CommandError('El modificador no conserva la zona elegida',code='paint_region_missing')
        mask=np.empty(len(mesh.polygons),dtype=np.float32); attr.data.foreach_get('value',mask)
        key+=(mask>.5).tobytes()
    cached=cache.get(obj.name) if cache is not None else None
    if cached and cached[0]==key: return cached[1],cached[2]
    mesh.calc_loop_triangles()
    # Compact atlas: only occupied texels carry a world surface sample.
    indexes, positions = [], []
    for tri in mesh.loop_triangles:
        if mask is not None and mask[tri.polygon_index]<=.5: continue
        t = np.array([uv.data[l].uv[:] for l in tri.loops]) * SIZE - .5
        lo = np.maximum(0, np.floor(t.min(axis=0)).astype(int))
        hi = np.minimum(SIZE-1, np.ceil(t.max(axis=0)).astype(int))
        if np.any(hi < lo): continue
        xx, yy = np.meshgrid(np.arange(lo[0],hi[0]+1), np.arange(lo[1],hi[1]+1))
        points = np.stack([xx.ravel(),yy.ravel()],axis=1)
        mat = np.stack([t[1]-t[0],t[2]-t[0]],axis=1)
        if abs(np.linalg.det(mat)) < 1e-12: continue
        bc = (points-t[0]) @ np.linalg.inv(mat).T
        valid = (bc[:,0]>=-.001)&(bc[:,1]>=-.001)&(bc.sum(axis=1)<=1.001)
        points, bc = points[valid], bc[valid]
        if not len(points): continue
        verts = np.array([(obj.matrix_world @ mesh.vertices[v].co)[:] for v in tri.vertices])
        positions.append(verts[0] + bc[:,0,None]*(verts[1]-verts[0]) + bc[:,1,None]*(verts[2]-verts[0]))
        indexes.append(points[:,1]*SIZE+points[:,0])
    if not indexes: raise CommandError('La malla no tiene superficie pintable', code='paint_empty')
    result=np.concatenate(indexes),np.concatenate(positions)
    if cache is not None: cache[obj.name]=(key,*result)
    return result


def make_layer(obj, recipe, tint, erase=False):
    """Append a top shader layer with a UV mask, preserving all preceding layers."""
    if len(obj.data.materials) != 1 or not obj.data.materials[0] or not obj.data.materials[0].get(KEY):
        raise CommandError('Pulsa «Aplicar a todo» antes de pintar este objeto', code='paint_needs_base')
    old = obj.data.materials[0]
    source = compile_material(recipe, tint)
    if (erase or old.get('tablet_top_recipe') == source[KEY]) and old.get('tablet_top_mask') in bpy.data.images:
        # Immutable images across commits make global Blender undo/save reliable.
        # Consecutive strokes of the same material share a logical layer, while
        # each committed material points at its own packed image snapshot.
        material = old.copy()
        if old.use_raytrace_refraction or (not erase and source.use_raytrace_refraction):
            configure_transmission(material)
        previous = bpy.data.images[old['tablet_top_mask']]
        image = previous.copy()
        pixels = np.empty(SIZE*SIZE*4,dtype=np.float32)
        previous.pixels.foreach_get(pixels)
        image.pixels.foreach_set(pixels)
        for node in material.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image == previous: node.image = image
        material['tablet_top_mask'] = image.name
        obj.data.materials[0] = material
        return material,image,pixels
    if int(old.get('tablet_layers',0)) >= MAX_LAYERS:
        raise CommandError('Máximo ocho capas. Deshaz la última o aplica un material a todo para comenzar de nuevo', code='paint_layer_limit')
    material = old.copy()
    material.name = old.name + ' · pintura'
    material.use_raytrace_refraction = old.use_raytrace_refraction or source.use_raytrace_refraction
    if material.use_raytrace_refraction: configure_transmission(material)
    image = bpy.data.images.new('Pintura · '+obj.name, width=SIZE, height=SIZE, alpha=False, float_buffer=False)
    image.colorspace_settings.name = 'Non-Color'
    zeros = np.zeros(SIZE*SIZE*4, dtype=np.float32)
    image.pixels.foreach_set(zeros)
    image.pack()
    try:
        nodes, links = material.node_tree.nodes, material.node_tree.links
        output = next(n for n in nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output)
        baseline = output.inputs['Surface'].links[0].from_socket
        # A shader group copied from the same compiler keeps advanced recipes identical.
        group = bpy.data.node_groups.new('Pintura · '+recipe['label'], 'ShaderNodeTree')
        group.interface.new_socket(name='Shader', in_out='OUTPUT', socket_type='NodeSocketShader')
        mapping = {}
        for n in source.node_tree.nodes:
            if n.type == 'OUTPUT_MATERIAL': continue
            clone = group.nodes.new(n.bl_idname); mapping[n] = clone
            for prop in ('operation','blend_type','wave_type','bands_direction','rings_direction','noise_dimensions','normalize','distance','feature','voronoi_dimensions'):
                if hasattr(n,prop): setattr(clone,prop,getattr(n,prop))
            for i, sock in enumerate(n.inputs):
                if hasattr(sock,'default_value'):
                    try: clone.inputs[i].default_value = sock.default_value
                    except (TypeError, ValueError): pass
        gout = group.nodes.new('NodeGroupOutput')
        for link in source.node_tree.links:
            if link.to_node.type == 'OUTPUT_MATERIAL':
                if link.to_socket.name=='Surface':
                    group.links.new(mapping[link.from_node].outputs[link.from_socket.identifier],gout.inputs[0])
            else:
                group.links.new(mapping[link.from_node].outputs[link.from_socket.identifier],mapping[link.to_node].inputs[link.to_socket.identifier])
        layer = nodes.new('ShaderNodeGroup'); layer.node_tree = group
        uv = nodes.new('ShaderNodeUVMap'); uv.uv_map = UV_NAME
        texture = nodes.new('ShaderNodeTexImage'); texture.image = image; texture.interpolation = 'Linear'; texture.extension='CLIP'
        links.new(uv.outputs['UV'],texture.inputs['Vector'])
        mix = nodes.new('ShaderNodeMixShader')
        links.new(texture.outputs['Color'],mix.inputs[0]); links.new(baseline,mix.inputs[1]); links.new(layer.outputs[0],mix.inputs[2])
        links.new(mix.outputs[0],output.inputs['Surface'])
        material['tablet_layers'] = int(old.get('tablet_layers',0))+1
        material['tablet_top_recipe'] = source[KEY]
        material['tablet_top_mask'] = image.name
        obj.data.materials[0] = material
        return material, image, zeros
    except Exception:
        bpy.data.materials.remove(material)
        bpy.data.images.remove(image)
        raise


def project_surface(indexes, positions, frame):
    """Project/occlude once per stroke; index visible texels in screen tiles."""
    depth, matrix, width, height = frame
    xyz = np.concatenate([positions,np.ones((len(positions),1))],axis=1) @ np.asarray(matrix).T
    valid_w = xyz[:,3] > 1e-9
    ndc = xyz[:,:3] / np.maximum(xyz[:,3,None],1e-9)
    sx, sy = (ndc[:,0]+1)*.5, (1-ndc[:,1])*.5
    px = np.clip((sx*width).astype(int),0,width-1)
    py = np.clip(((1-sy)*height).astype(int),0,height-1)
    visible = valid_w & (sx>=0)&(sx<=1)&(sy>=0)&(sy<=1)&(ndc[:,2]>=-1)&(ndc[:,2]<=1)
    # Reconstruct the visible plane at the exact subpixel location. A fixed large
    # depth tolerance paints through thin walls; a nearest-pixel comparison alone
    # rejects slanted front faces. Use the quieter one-sided slope at silhouettes.
    center = depth[py,px]
    left = center-depth[py,np.maximum(px-1,0)]
    right = depth[py,np.minimum(px+1,width-1)]-center
    down = center-depth[np.maximum(py-1,0),px]
    up = depth[np.minimum(py+1,height-1),px]-center
    dx = np.where(np.abs(left)<np.abs(right),left,right)
    dy = np.where(np.abs(down)<np.abs(up),down,up)
    expected = center + dx*(sx*width-.5-px) + dy*((1-sy)*height-.5-py)
    z = (ndc[:,2]+1)*.5
    visible &= (center<1) & (np.abs(expected-z) < 4e-7)
    aspect = width / height
    xy = np.column_stack((sx[visible] * aspect, sy[visible]))
    ids = indexes[visible]
    tiles = np.floor(xy * 32).astype(np.int32)
    columns = math.ceil(aspect * 32) + 1
    keys = tiles[:, 1] * columns + tiles[:, 0]
    order = np.argsort(keys, kind='stable')
    unique, starts = np.unique(keys[order], return_index=True)
    ends = np.r_[starts[1:], len(order)]
    bins = {int(key): order[start:end] for key, start, end in zip(unique, starts, ends)}
    return ids, xy, bins, columns, aspect


def paint_projected(projection, pixels, points, radius, strength, erase=False, brush='ROUND'):
    """Only visit tiles touched by each dab; the immutable projection is reused."""
    indexes, xy, bins, columns, aspect = projection
    changed = False
    for p in points:
        pressure = p.get('pressure', 1)
        if pressure <= 0 or strength <= 0: continue
        center = np.array((p['u'] * aspect, p['v']))
        lo = np.maximum(0, np.floor((center-radius)*32).astype(int))
        hi = np.minimum((columns-1, 32), np.floor((center+radius)*32).astype(int))
        chunks = [bins[y*columns+x] for y in range(lo[1],hi[1]+1)
                  for x in range(lo[0],hi[0]+1) if y*columns+x in bins]
        if not chunks: continue
        candidates = np.concatenate(chunks)
        delta = xy[candidates]-center
        d = np.sqrt(np.einsum('ij,ij->i',delta,delta))
        amount = np.clip((1-d/radius)*4,0,1)*strength*pressure
        if brush=='AIRBRUSH':
            amount=np.maximum(0,1-(d/radius)**2)**3*strength*pressure
        elif brush=='SPRAY':
            # Stable screen-space droplets: packet boundaries never reseed a dab.
            cell_size=radius*.12
            cells=np.floor(xy[candidates]/cell_size)
            def noise(a,b):
                value=np.sin(cells[:,0]*a+cells[:,1]*b)*43758.5453
                return value-np.floor(value)
            droplet=(cells+np.column_stack((noise(127.1,311.7),noise(269.5,183.3))))*cell_size
            spot=np.linalg.norm(xy[candidates]-droplet,axis=1)/(cell_size*.24)
            amount=np.maximum(0,1-spot)*np.maximum(0,1-d/radius)*strength*pressure
        active = amount > 0
        ids = indexes[candidates[active]]
        if not len(ids): continue
        values = 1-amount[active] if erase else amount[active]
        before = pixels[ids*4].copy()
        # Shared triangle edges can address the same texel more than once.
        operation = np.minimum.at if erase else np.maximum.at
        operation(pixels, ids*4, values)
        changed |= bool(np.any(before != pixels[ids*4]))
        pixels[ids*4+1] = pixels[ids*4]
        pixels[ids*4+2] = pixels[ids*4]
    return changed


def paint_pixels(indexes, positions, pixels, frame, points, radius, strength, erase=False):
    return paint_projected(project_surface(indexes,positions,frame),pixels,points,radius,strength,erase)
