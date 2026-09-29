"""Design surfaces of extrusions and pockets, derived from their source sketches.

Each evaluated face is labelled by the analytic surface it lies on: a cap
plane, the plane of a straight side or the cylinder of an arc/circle side.
Booleans may split or trim faces, but never move them off those surfaces, so
the labels need no bookkeeping through the kernel. Faces that match nothing
(fillets, lofts, helices, gear flanks) keep label 0 and the mesh heuristics.
"""
import math
from mathutils import Vector
from . import document as model


def _sides(e):
    """Straight segments and circular arcs bounding one closed sketch entity."""
    typ = e['type']
    if typ in ('RECTANGLE', 'NGON'):
        ring = model.outline(e)
        return [('LINE', a, b) for a, b in zip(ring, ring[1:]+ring[:1])], []
    if typ == 'CIRCLE':
        return [], [((e['x'], e['y']), e['diameter']/2)]
    if typ == 'SLOT':
        a = math.radians(e['angle']); half, r = e['length']/2, e['width']/2
        d = (math.cos(a), math.sin(a)); n = (-d[1], d[0])
        c1 = (e['x']-d[0]*half, e['y']-d[1]*half); c2 = (e['x']+d[0]*half, e['y']+d[1]*half)
        lines = [('LINE', (c1[0]+n[0]*r*s, c1[1]+n[1]*r*s), (c2[0]+n[0]*r*s, c2[1]+n[1]*r*s)) for s in (1, -1)]
        return lines, [(c1, r), (c2, r)]
    if typ == 'LINE':
        return [('LINE', (e['x'], e['y']), (e['x2'], e['y2']))], []
    if typ == 'ARC':
        return [], [((e['x'], e['y']), e['radius'])]
    return [], []   # GEAR flanks and anything else keep the mesh heuristics


def surfaces(doc, body_id, scale):
    """Analytic surfaces in Blender units: ('PLANE', normal, offset) or ('CYLINDER', point, axis, radius)."""
    result = []
    from . import mirror
    for feature in doc['features']:
        if feature.get('body_id') != body_id or not mirror.active(doc,feature) or feature['type'] not in ('EXTRUDE', 'CUT', 'MIRROR'):
            continue
        first_surface=len(result)
        try:
            sketch, _ = model.profile(doc, feature['profile_id'])
        except Exception:
            continue
        f = model.frame(sketch)
        origin, fx, fy, fn = (Vector(f[k]) for k in ('origin', 'x', 'y', 'normal'))
        depth = feature['depth']
        levels = ((-abs(depth), abs(depth)) if feature.get('extent') == 'BOTH'
                  else (0., -depth if feature.get('operation',feature['type']) == 'CUT' else depth))
        for z in levels:
            result.append(('PLANE', fn.copy(), (origin+fn*z).dot(fn)/scale))
        def world(p):
            return origin+fx*p[0]+fy*p[1]
        entities = []
        for e in model.closed_entities(sketch):
            members = e.get('members')
            entities.extend(model.find(sketch, 'entities', m) for m in members) if members else entities.append(e)
        for e in entities:
            lines, arcs = _sides(e)
            for _, a, b in lines:
                a, b = world(a), world(b)
                if (b-a).length < 1e-12: continue
                normal = (b-a).normalized().cross(fn).normalized()
                result.append(('PLANE', normal, a.dot(normal)/scale))
            for center, radius in arcs:
                result.append(('CYLINDER', world(center)/scale, fn.copy(), radius/scale))
        if feature.get('mirror'):
            spec=feature['mirror'];reflected=[]
            for surface in result[first_surface:]:
                if surface[0]=='PLANE':
                    normal=Vector(mirror.point(surface[1],spec,direction=True))
                    origin=Vector(mirror.point(surface[1]*surface[2],spec,scale=scale))
                    reflected.append(('PLANE',normal,origin.dot(normal)))
                else:
                    reflected.append(('CYLINDER',Vector(mirror.point(surface[1],spec,scale=scale)),
                                      Vector(mirror.point(surface[2],spec,direction=True)),surface[3]))
            result[first_surface:]=reflected
    return result


def label_faces(points, faces, normals, found, tolerance):
    """1-based surface label per face, 0 when the face lies on no design surface."""
    keys = {}
    def key(surface):
        if surface[0] == 'PLANE':
            n = surface[1] if max(surface[1], key=abs) > 0 else -surface[1]
            d = surface[2] if n == surface[1] else -surface[2]
            k = ('P', tuple(round(c, 5) for c in n), round(d/tolerance/10))
        else:
            axis = surface[2] if max(surface[2], key=abs) > 0 else -surface[2]
            foot = surface[1]-axis*surface[1].dot(axis)
            k = ('C', tuple(round(c, 5) for c in axis), tuple(round(c/tolerance/10) for c in foot), round(surface[3]/tolerance/10))
        return keys.setdefault(k, len(keys)+1)
    # Planes first: a straight side whose corners touch a circle is still flat.
    candidates = sorted(((s, key(s)) for s in found), key=lambda item: item[0][0] != 'PLANE')
    labels = []
    for face, normal in zip(faces, normals):
        label = 0
        vertices = [points[i] for i in face]
        for s, k in candidates:
            if s[0] == 'PLANE':
                if abs(normal.dot(s[1])) < 1-1e-4: continue
                if all(abs(v.dot(s[1])-s[2]) <= tolerance for v in vertices):
                    label = k; break
            else:
                point, axis, radius = s[1], s[2], s[3]
                if abs(normal.dot(axis)) > 1e-3: continue
                def distance(v):
                    w = v-point
                    return (w-axis*w.dot(axis)).length
                if all(abs(distance(v)-radius) <= tolerance for v in vertices):
                    label = k; break
        labels.append(label)
    return labels
