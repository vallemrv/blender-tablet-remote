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
    prepare_uv(obj)
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


def make_layer(obj, recipe, tint, erase=False, **options):
    from .layers import make_layer as create
    if len(obj.data.materials) != 1 or not obj.data.materials[0] or not obj.data.materials[0].get(KEY):
        raise CommandError('Aplica un material base antes de pintar', code='paint_needs_base')
    return create(obj, recipe, tint, erase=erase, **options)


def prepare_uv(obj):
    """Unwrap an isolated copy: continuous charts, area-based packing, no user mode edits.

    Existing painting UVs remain untouched so saved masks never move. User UVs
    and face/vertex selection are copied back neither from nor to the helper.
    """
    mesh=obj.data
    if mesh.uv_layers.get(UV_NAME): return
    temp_mesh=mesh.copy(); temp=bpy.data.objects.new('.Tablet UV',temp_mesh)
    bpy.context.scene.collection.objects.link(temp)
    selected=list(bpy.context.selected_objects); active=bpy.context.view_layer.objects.active
    uv_active=mesh.uv_layers.active_index
    for item in selected: item.select_set(False)
    temp.select_set(True); bpy.context.view_layer.objects.active=temp
    try:
        uv=temp_mesh.uv_layers.new(name=UV_NAME)
        temp_mesh.uv_layers.active=uv
        with bpy.context.temp_override(object=temp,active_object=temp,selected_objects=[temp],selected_editable_objects=[temp]):
            bpy.ops.object.mode_set(mode='EDIT')
            try:
                bpy.ops.mesh.select_all(action='SELECT')
                bpy.ops.uv.smart_project(angle_limit=math.radians(66),island_margin=.015,
                                         area_weight=0.,correct_aspect=False,scale_to_bounds=True)
            finally:
                bpy.ops.object.mode_set(mode='OBJECT')
        coords=np.empty(len(temp_mesh.loops)*2,dtype=np.float32)
        temp_mesh.uv_layers[UV_NAME].data.foreach_get('uv',coords)
        target=mesh.uv_layers.new(name=UV_NAME); target.data.foreach_set('uv',coords)
        mesh.uv_layers.active_index=uv_active
        mesh.update()
    finally:
        if temp.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
        temp.select_set(False)
        for item in selected: item.select_set(True)
        bpy.context.view_layer.objects.active=active
        bpy.data.objects.remove(temp,do_unlink=True)
        if temp_mesh.users==0: bpy.data.meshes.remove(temp_mesh)


def publish_mask(image, pixels, indexes):
    """Extend edge pixels into the UV gutter for linear filtering, never into another chart."""
    size=image.size[0]
    occupied=np.zeros(size*size,dtype=bool); occupied[indexes]=True; occupied=occupied.reshape(size,size)
    values=pixels[::4].reshape(size,size).copy()
    for _ in range(2):
        count=np.zeros_like(values); total=np.zeros_like(values)
        for axis in (0,1):
            for shift in (-1,1):
                valid=np.roll(occupied,shift,axis=axis)
                if axis==0: valid[0 if shift==1 else -1,:]=False
                else: valid[:,0 if shift==1 else -1]=False
                total+=np.roll(values,shift,axis=axis)*valid; count+=valid
        fill=~occupied & (count>0)
        values[fill]=total[fill]/count[fill]; occupied|=fill
    output=pixels.copy()
    for channel in range(3): output[channel::4]=values.ravel()
    image.pixels.foreach_set(output); image.update()


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
