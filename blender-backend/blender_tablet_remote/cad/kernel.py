"""Shared CAD geometry and lightweight pointer prisms, in metres.

OpenCascade is the only solid evaluator. The tessellation here only supplies
interactive extrusion/cut previews while the exact worker result is pending.
"""
from mathutils import Vector
from mathutils.geometry import delaunay_2d_cdt
from .document import outline, contains, closed_entities, frame
from ..errors import CommandError


class ExtrusionPreviewCache:
    """Session-local tessellation: depth changes only stretch the same solid.

    Build the compact solid in the sketch's local frame at unit depth.
    Coordinates are then mapped to the current frame in metres. A changed sketch
    invalidates its entry, including holes and associative support planes.
    """
    def __init__(self):
        self.entries = {}

    def extrude(self, sketch, source, depth, *, symmetric=False, to_face=None):
        from .document import dumps
        key = source['id']
        signature = dumps(sketch)
        cached = self.entries.get(key)
        if cached is None or cached['signature'] != signature:
            local = dict(sketch, plane='XY', offset=0)
            local.pop('plane_id', None)
            local.pop('support_id', None)
            vertices, faces = _preview_prism(local, source)
            cached = dict(signature=signature, solid=(vertices, faces))
            self.entries[key] = cached
        vertices, faces = cached['solid']
        basis = frame(sketch)
        origin, axis_x, axis_y, normal = (basis[k] for k in ('origin', 'x', 'y', 'normal'))
        def project(x, y, z):
            return tuple(origin[i] + x*axis_x[i] + y*axis_y[i] + z*normal[i] for i in range(3))
        if to_face is not None:
            return _to_face(vertices, faces, project, normal, to_face)
        if symmetric:
            vertices = [project(x, y, (z - .5) * 2 * abs(depth)) for x,y,z in vertices]
        else:
            vertices = [project(x, y, z * depth) for x,y,z in vertices]
            if depth < 0:
                faces = [tuple(reversed(face)) for face in faces]
        return vertices, faces


def _preview_prism(sketch, source, depth=1.0):
    """Tessellated prism template for pointer feedback only, never solid evaluation."""
    if source['type'] == 'SKETCH':
        profiles = closed_entities(sketch)
        outlines = [(item, outline(item)) for item in profiles]
        roots = [item for item, ring in outlines if not any(
            other['id'] != item['id'] and contains(other_ring, ring[0]) for other, other_ring in outlines)]
        if not roots:
            raise CommandError('El croquis no contiene regiones exteriores válidas', code='cad_profile_invalid')
        vertices, faces = [], []
        for item in roots:
            region_vertices, region_faces = _preview_prism(sketch, item, depth)
            offset = len(vertices)
            vertices.extend(region_vertices)
            faces.extend(tuple(i + offset for i in face) for face in region_faces)
        return vertices, faces
    rings = region(sketch, source)
    if len(rings)==1:
        ring=rings[0]; n=len(ring)
        # Perimeter order directly defines the walls. Convex even profiles
        # get quad caps without the arbitrary diagonals of a global CDT.
        turns=[(b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0])
               for a,b,c in zip(ring,ring[1:]+ring[:1],ring[2:]+ring[:2])]
        if n%2==0 and all(t>=-1e-20 for t in turns):
            vertices=[world(sketch,*p,z) for z in (0,depth) for p in ring]
            caps=[tuple(range(n))] if n==4 else []
            if n>4:
                center=tuple(sum(p[i] for p in ring)/n for i in (0,1))
                vertices.extend(world(sketch,*center,z) for z in (0,depth))
                caps=[(2*n,i,(i+1)%n,(i+2)%n) for i in range(0,n,2)]
            polygons=[]
            for cap in caps:
                polygons.append(tuple(reversed(cap)))
                polygons.append(tuple(2*n+1 if i==2*n else i+n for i in cap))
            polygons.extend((i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n))
            if depth<0: polygons=[tuple(reversed(f)) for f in polygons]
            return vertices,polygons
    points, edges = [], []
    for ring in rings:
        start = len(points)
        points.extend(Vector(p) for p in ring)
        edges.extend((start+i, start+(i+1)%len(ring)) for i in range(len(ring)))
    # CDT may reorder vertices; use its returned coordinates for caps and use
    # coordinate lookup for walls. No evaluated index is persisted as identity.
    verts, _, faces, _, _, _ = delaunay_2d_cdt(points, edges, [], 0, 1e-9)
    n = len(verts)
    vertices = [world(sketch, p.x,p.y,z) for z in (0,depth) for p in verts]
    polygons = []
    for face in faces:
        center = tuple(sum(verts[i][axis] for i in face)/len(face) for axis in (0,1))
        if contains(rings[0],center) and not any(contains(r,center) for r in rings[1:]):
            polygons.append(tuple(reversed(face)))
            polygons.append(tuple(i+n for i in face))
    for ring in rings:
        ids = [min(range(n),key=lambda i:(verts[i]-Vector(p)).length_squared) for p in ring]
        for a,b in zip(ids, ids[1:]+ids[:1]):
            polygons.append((a,b,b+n,a+n))
    if not polygons:
        raise CommandError('El perfil no genera un sólido', code='cad_profile_invalid')
    if depth < 0:
        polygons = [tuple(reversed(f)) for f in polygons]
    return vertices, polygons


def _to_face(vertices, faces, project, normal, to_face):
    """Each wall runs along the sketch normal until it meets the plane of the face.

    The far cap lies on that plane, so it may be inclined to the profile. The
    whole profile must stay on one side of the plane, never touching it.
    """
    origin, plane = Vector(to_face['origin']), Vector(to_face['normal'])
    direction = Vector(normal)
    facing = direction.dot(plane)
    if abs(facing) < 1e-6:
        raise CommandError('La cara es paralela a la dirección de extrusión', code='cad_profile_invalid')
    result, travels = [], []
    for x, y, z in vertices:
        start = Vector(project(x, y, 0))
        travel = (origin - start).dot(plane) / facing
        travels.append(travel)
        result.append(tuple(start + direction * travel * z))
    extent = max(max(abs(t) for t in travels), 1e-9)
    if not (min(travels) > extent * 1e-6 or max(travels) < -extent * 1e-6):
        raise CommandError('La cara corta o toca el perfil; elige una que quede entera a un lado',
                           code='cad_profile_invalid')
    if travels[0] < 0:
        faces = [tuple(reversed(face)) for face in faces]
    return result, faces


def face_travel(sketch, to_face):
    """Signed distance along the sketch normal from its origin to the face plane."""
    basis = frame(sketch)
    plane = Vector(to_face['normal']); direction = Vector(basis['normal'])
    facing = direction.dot(plane)
    if abs(facing) < 1e-6:
        raise CommandError('La cara es paralela a la dirección de extrusión', code='cad_profile_invalid')
    return (Vector(to_face['origin']) - Vector(basis['origin'])).dot(plane) / facing


def through_depth(sketch, vertices, reflection=None):
    """Half-length enclosing the current body along the sketch normal, in metres."""
    if not vertices:
        raise CommandError('No hay sólido para perforar', code='cad_dependency')
    if reflection:
        from . import mirror
        vertices = [mirror.point(v, reflection) for v in vertices]
    basis = frame(sketch)
    origin, normal = Vector(basis['origin']), Vector(basis['normal'])
    depth = max(abs((Vector(v)-origin).dot(normal)) for v in vertices)
    span = max(max(v[i] for v in vertices)-min(v[i] for v in vertices) for i in range(3))
    margin = max(max(depth,span)*1e-4, 1e-7)
    return depth+margin


def operand(cache, sketch, source, feature, base=None):
    """Tool solid of an extrusion or cut before it joins or leaves its body."""
    extent = feature.get('extent', 'ONE')
    if extent == 'THROUGH_ALL':
        depth = through_depth(sketch, base[0] if base else [], feature.get('mirror'))
        return cache.extrude(sketch, source, depth, symmetric=True)
    if extent == 'TO_FACE':
        return cache.extrude(sketch, source, 0, to_face=feature['to_face'])
    depth = feature['depth']
    if extent == 'BOTH':
        return cache.extrude(sketch, source, depth, symmetric=True)
    cut = feature.get('operation', feature['type']) == 'CUT'
    return cache.extrude(sketch, source, -depth if cut else depth)


def world(plane, x, y, z=0):
    if isinstance(plane,dict):
        basis=frame(plane)
        return tuple(basis['origin'][i]+x*basis['x'][i]+y*basis['y'][i]+z*basis['normal'][i] for i in range(3))
    return {'XY': (x,y,z), 'XZ': (x,-z,y), 'YZ': (z,x,y)}[plane]


def _intersects(a,b,c,d):
    def cross(p,q,r):
        return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    def on(p,q,r):
        return min(p[0],q[0])-1e-10 <= r[0] <= max(p[0],q[0])+1e-10 and min(p[1],q[1])-1e-10 <= r[1] <= max(p[1],q[1])+1e-10
    s,t,u,v = cross(a,b,c),cross(a,b,d),cross(c,d,a),cross(c,d,b)
    if s*t < 0 and u*v < 0:
        return True
    return any(abs(k)<1e-12 and on(p,q,r) for k,p,q,r in ((s,a,b,c),(t,a,b,d),(u,c,d,a),(v,c,d,b)))


def region(sketch, source):
    outer = outline(source)
    # Slots and gears are simple by construction; their dense outlines skip the O(n²) test.
    if source['type'] not in ('SLOT', 'GEAR') and any(_intersects(a,b,c,d) for i,(a,b) in enumerate(zip(outer,outer[1:]+outer[:1]))
           for j,(c,d) in enumerate(zip(outer,outer[1:]+outer[:1]))
           if j>i+1 and not(i==0 and j==len(outer)-1)):
        raise CommandError('El contorno se cruza consigo mismo',code='cad_profile_invalid')
    rings = [outer]
    others = [outline(e) for e in closed_entities(sketch) if e['id'] != source['id']]
    for other in others:
        if any(_intersects(a,b,c,d) for a,b in zip(outer,outer[1:]+outer[:1])
               for c,d in zip(other,other[1:]+other[:1])):
            raise CommandError('Los contornos se cruzan o se tocan; sepáralos antes de extruir', code='cad_profile_invalid')
        if contains(outer, other[0]):
            rings.append(list(reversed(other)))
    for i, a in enumerate(rings[1:]):
        for b in rings[i+2:]:
            if contains(a,b[0]) or contains(b,a[0]) or any(
                    _intersects(p,q,r,s) for p,q in zip(a,a[1:]+a[:1]) for r,s in zip(b,b[1:]+b[:1])):
                raise CommandError('Los huecos anidados o solapados no están admitidos en V1', code='cad_profile_invalid')
    return rings


def helix_axis(sketch, axis):
    """Axis point and direction in the sketch's local 2D frame: 'X', 'Y' or a line id."""
    if axis in ('X', 'Y', None):
        return (0., 0.), ((1., 0.) if axis == 'X' else (0., 1.))
    line = next((e for e in sketch['entities'] if e['id'] == axis and e['type'] == 'LINE'), None)
    if line is None:
        raise CommandError('El eje del barrido helicoidal ya no existe en el croquis', code='cad_reference_missing')
    dx, dy = line['x2']-line['x'], line['y2']-line['y']
    length = (dx*dx+dy*dy)**.5
    return (line['x'], line['y']), (dx/length, dy/length)


def sweep_path(sketch):
    """Open chain of lines/arcs in a path sketch: world points and exact tangents.

    Each vertex carries the analytic tangent of its line or arc. Where two
    entities meet tangentially that tangent is shared; at a real corner it is
    None and the sweep mitres the section there.
    """
    import math
    edges = [e for e in sketch['entities'] if not e.get('construction', False) and e['type'] in ('LINE', 'ARC')]
    if not edges:
        raise CommandError('El croquis del recorrido no tiene líneas ni arcos', code='cad_profile_invalid')
    if any(not e.get('construction', False) and e['type'] not in ('LINE', 'ARC', 'POINT') for e in sketch['entities']):
        raise CommandError('El recorrido solo admite líneas y arcos; pasa el resto a construcción', code='cad_profile_invalid')
    span = max(max(abs(c) for p in outline(e) for c in p) for e in edges)
    tolerance = max(span*1e-6, 1e-9)
    near = lambda a, b: math.dist(a, b) <= tolerance
    def samples(e, reverse):
        points = outline(e)
        if e['type'] == 'LINE':
            d = (e['x2']-e['x'], e['y2']-e['y']); length = math.hypot(*d)
            tangents = [(d[0]/length, d[1]/length)]*len(points)
        else:
            sign = 1. if e['sweep'] > 0 else -1.
            tangents = [(-(y-e['y'])/e['radius']*sign, (x-e['x'])/e['radius']*sign) for x, y in points]
        pairs = list(zip(points, tangents))
        return [(p, (-t[0], -t[1])) for p, t in reversed(pairs)] if reverse else pairs
    def joint(a, b):
        # Shared tangent where the entities meet smoothly, None at a corner.
        return a if a is not None and b is not None and a[0]*b[0]+a[1]*b[1] > 1-1e-6 else None
    remaining = {e['id']: e for e in edges}
    chain = samples(remaining.pop(edges[0]['id']), False)
    grown = True
    while remaining and grown:
        grown = False
        for e in list(remaining.values()):
            for end, reverse in ((-1, False), (-1, True), (0, False), (0, True)):
                piece = samples(e, reverse)
                if end == -1 and near(chain[-1][0], piece[0][0]):
                    chain[-1] = (chain[-1][0], joint(chain[-1][1], piece[0][1])); chain.extend(piece[1:])
                elif end == 0 and near(chain[0][0], piece[-1][0]):
                    chain[0] = (chain[0][0], joint(piece[-1][1], chain[0][1])); chain[:0] = piece[:-1]
                else:
                    continue
                remaining.pop(e['id']); grown = True
                break
    if remaining:
        raise CommandError('El recorrido debe ser una sola cadena de líneas y arcos unidos por sus extremos', code='cad_profile_invalid')
    if near(chain[0][0], chain[-1][0]):
        raise CommandError('El recorrido es cerrado; el barrido usa un recorrido abierto', code='cad_profile_invalid')
    origin = Vector(world(sketch, 0, 0))
    points, tangents = [], []
    for (x, y), t in chain:
        p = Vector(world(sketch, x, y))
        if points and (p-points[-1]).length <= tolerance: continue
        points.append(p)
        tangents.append(None if t is None else (Vector(world(sketch, *t))-origin).normalized())
    return points, tangents


def sweep_frames(sketch, sampled):
    """Path points, chord tangents, section tangents, rotations and mitred corners per vertex."""
    path, exact = sampled
    if len(path) < 2:
        raise CommandError('El recorrido es demasiado corto', code='cad_profile_invalid')
    tangents = [(b-a).normalized() for a, b in zip(path, path[1:])]
    first = exact[0] or tangents[0]; last = exact[-1] or tangents[-1]
    facing = Vector(frame(sketch)['normal']).dot(first)
    if abs(facing) < 1e-3:
        raise CommandError('El perfil debe cortar el recorrido; dibújalo en un plano transversal a su inicio', code='cad_profile_invalid')
    # Exact tangents keep straight runs truly cylindrical; corners use the bisector.
    directions = [first]+[exact[i] or (tangents[i-1]+tangents[i]).normalized() for i in range(1, len(path)-1)]+[last]
    corners = [False]+[exact[i] is None for i in range(1, len(path)-1)]+[False]
    matrices = [first.rotation_difference(first).to_matrix()]
    for i in range(1, len(path)):
        matrices.append(directions[i-1].rotation_difference(directions[i]).to_matrix() @ matrices[-1])
    return path, tangents, directions, matrices, facing, corners
