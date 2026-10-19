"""Editable wire copies of sketch geometry; no solids and no document mutations."""
import math
from . import document as model
from ..errors import BadPayload


def outline(entity, resolution):
    kind = entity['type']
    if kind == 'CIRCLE':
        radius = entity['diameter'] / 2
        return [(entity['x']+radius*math.cos(math.tau*i/resolution),
                 entity['y']+radius*math.sin(math.tau*i/resolution)) for i in range(resolution)], True
    if kind == 'ARC':
        count = max(1, math.ceil(abs(entity['sweep']) / 360 * resolution))
        return [(entity['x']+entity['radius']*math.cos(math.radians(entity['start']+entity['sweep']*i/count)),
                 entity['y']+entity['radius']*math.sin(math.radians(entity['start']+entity['sweep']*i/count)))
                for i in range(count+1)], False
    if kind == 'SLOT':
        angle = math.radians(entity['angle']); half = entity['length']/2; radius = entity['width']/2
        count = max(2, math.ceil(resolution/2)); points = []
        for sign, start in ((1,-math.pi/2),(-1,math.pi/2)):
            cx = entity['x']+sign*half*math.cos(angle); cy = entity['y']+sign*half*math.sin(angle)
            points.extend((cx+radius*math.cos(angle+start+math.pi*i/count),
                           cy+radius*math.sin(angle+start+math.pi*i/count)) for i in range(count+1))
        return points, True
    return model.outline(entity), kind not in {'LINE','POINT','ARC'}


def wire_geometry(entities, resolution):
    if isinstance(resolution, bool) or not isinstance(resolution, int) or not 3 <= resolution <= 4096:
        raise BadPayload('Vértices por círculo: un entero entre 3 y 4096')
    paths = []; total = 0
    for entity in entities:
        path = outline(entity, resolution); total += len(path[0])
        if total > 200000:
            raise BadPayload('Demasiados vértices: reduce la resolución o selecciona menos figuras')
        paths.append(path)
    # Reuse coincident samples, not intersections: two crossing edges stay two edges.
    vertices, edges, indices, edge_keys = [], [], {}, set()
    for points, closed in paths:
        chain = []
        for x,y in points:
            key = (round(x,12), round(y,12))
            if key not in indices:
                indices[key] = len(vertices); vertices.append((x,y,0.0))
            chain.append(indices[key])
        pairs = list(zip(chain,chain[1:]))
        if closed and len(chain)>1: pairs.append((chain[-1],chain[0]))
        for a,b in pairs:
            key = tuple(sorted((a,b)))
            if a != b and key not in edge_keys:
                edges.append((a,b)); edge_keys.add(key)
    return vertices, edges
