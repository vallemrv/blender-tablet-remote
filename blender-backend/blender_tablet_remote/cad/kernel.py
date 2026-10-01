"""CadKernel V1: deterministic native mesh extrusion, no binary dependencies.

Constrained triangulation keeps holes; analytic sketch source remains exact while
circles are tessellated only for evaluation/display. No BREP/STEP claim.
"""
from abc import ABC, abstractmethod
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
            vertices, faces = kernel.extrude(local, source, 1.0)
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


def operand(cache, sketch, source, feature):
    """Tool solid of an extrusion or cut before it joins or leaves its body."""
    extent = feature.get('extent', 'ONE')
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


class CadKernel(ABC):
    @abstractmethod
    def extrude(self, sketch, source, depth):
        """Return vertices and polygon indices in metres."""


    @abstractmethod
    def cut(self, base, cutter):
        """Subtract two evaluated meshes, returning a validated solid in metres."""


class BlenderNativeKernel(CadKernel):
    name = 'BLENDER_NATIVE_MESH'

    def cut(self, base, cutter):
        return cut_mesh(base, cutter)

    def union(self, base, addition):
        extent=max(max(v[axis] for v in base[0]+addition[0])-min(v[axis] for v in base[0]+addition[0]) for axis in range(3))
        tolerance=max(extent*1e-7,1e-10)
        if any(max(v[axis] for v in base[0]) < min(v[axis] for v in addition[0])-tolerance or
               max(v[axis] for v in addition[0]) < min(v[axis] for v in base[0])-tolerance for axis in range(3)):
            count=len(base[0])
            return list(base[0])+list(addition[0]), list(base[1])+[tuple(i+count for i in face) for face in addition[1]]
        return cut_mesh(base, addition, operation='UNION')

    def extrude(self, sketch, source, depth):
        if source['type'] == 'SKETCH':
            profiles = closed_entities(sketch)
            outlines = [(item, outline(item)) for item in profiles]
            roots = [item for item, ring in outlines if not any(
                other['id'] != item['id'] and contains(other_ring, ring[0]) for other, other_ring in outlines)]
            if not roots:
                raise CommandError('El croquis no contiene regiones exteriores válidas', code='cad_profile_invalid')
            vertices, faces = [], []
            for item in roots:
                region_vertices, region_faces = self.extrude(sketch, item, depth)
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



kernel = BlenderNativeKernel()


def cut_mesh(base, cutter, *, operation='DIFFERENCE'):
    """Native manifold boolean on closed CAD operands; no scene residue."""
    import bpy
    import bmesh
    meshes, objects = [], []
    try:
        for label,(vertices,faces) in zip(('CAD target','CAD cutter'),(base,cutter)):
            mesh=bpy.data.meshes.new(label); meshes.append(mesh)
            mesh.from_pydata(vertices,[],faces); mesh.update()
            obj=bpy.data.objects.new(label,mesh); objects.append(obj)
            bpy.context.scene.collection.objects.link(obj)
        modifier=objects[0].modifiers.new('CAD difference','BOOLEAN')
        # CAD operands are closed solids. Manifold preserves that invariant when
        # opposite cuts meet cap n-gons produced by previous unions/differences.
        modifier.operation=operation; modifier.solver='MANIFOLD'; modifier.object=objects[1]
        bpy.context.view_layer.update()
        evaluated=objects[0].evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh=evaluated.to_mesh()
        try:
            result=([tuple(v.co) for v in mesh.vertices],[tuple(f.vertices) for f in mesh.polygons])
            bm=bmesh.new()
            try:
                bm.from_mesh(mesh)
                result_volume = bm.calc_volume()
                valid=bool(bm.faces) and all(e.is_manifold for e in bm.edges) and result_volume>1e-18
            finally: bm.free()
            if not valid:
                raise CommandError('La operación produce un sólido vacío o geometría inválida',code='cad_cut_invalid' if operation=='DIFFERENCE' else 'cad_union_invalid')
            def volume(data):
                bm=bmesh.new()
                try:
                    vertices = [bm.verts.new(v) for v in data[0]]
                    for face in data[1]: bm.faces.new([vertices[i] for i in face])
                    bm.normal_update()
                    return abs(bm.calc_volume())
                finally:
                    bm.free()
            if operation=='DIFFERENCE':
                base_volume=volume(base)
                if base_volume-result_volume <= max(base_volume*1e-7,1e-18):
                    raise CommandError('El perfil no quita material del sólido destino',code='cad_cut_miss')
            return result
        finally: evaluated.to_mesh_clear()
    finally:
        for obj in objects: bpy.data.objects.remove(obj,do_unlink=True)
        for mesh in meshes:
            if mesh.users==0: bpy.data.meshes.remove(mesh)


def finish_edges(solid, edges, width, segments):
    """Fillet (segments > 1) or chamfer (1) the design edges on a compact solid.

    Each design edge is stored as its segments in metres, never mesh indices:
    a solid edge on the line of one of them that overlaps it is bevelled, so a
    straight edge survives a changed length (e.g. a deeper extrusion). A design
    edge with nothing left (the design moved away) is an explicit error.
    """
    import bmesh
    from mathutils.geometry import intersect_point_line
    vertices, faces = solid
    extent = max(max(v[i] for v in vertices)-min(v[i] for v in vertices) for i in range(3))
    tolerance = extent*1e-6+1e-9
    lines = [[(Vector(a), Vector(b)) for a, b in edge] for edge in edges]
    def on(edge, segments):
        p, q = edge.verts[0].co, edge.verts[1].co
        for a, b in segments:
            (cp, tp), (cq, tq) = intersect_point_line(p, a, b), intersect_point_line(q, a, b)
            overlap = min(max(tp, tq), 1.) - max(min(tp, tq), 0.)
            if (cp-p).length <= tolerance and (cq-q).length <= tolerance and overlap > 1e-6: return True
        return False
    bm = bmesh.new()
    try:
        verts = [bm.verts.new(v) for v in vertices]
        for face in faces: bm.faces.new([verts[i] for i in face])
        bm.normal_update()
        # Coplanar boolean tessellation is not a design edge; merge it first.
        bmesh.ops.dissolve_limit(bm, angle_limit=1e-4, verts=list(bm.verts), edges=list(bm.edges))
        chosen = set()
        for segments_of in lines:
            found = [e for e in bm.edges if on(e, segments_of)]
            if not found:
                raise CommandError('Una arista del redondeo ya no existe; edita o borra la operación', code='cad_reference_missing')
            chosen.update(found)
        bmesh.ops.bevel(bm, geom=list(chosen)+list({v for e in chosen for v in e.verts}), offset=width,
                        offset_type='OFFSET', profile_type='SUPERELLIPSE', segments=segments,
                        profile=.5, affect='EDGES', clamp_overlap=True, loop_slide=True)
        bm.normal_update()
        if not all(e.is_manifold for e in bm.edges) or bm.calc_volume() <= 1e-18:
            raise CommandError('El redondeo no cabe en esas aristas; reduce el ancho', code='cad_finish_invalid')
        bm.verts.index_update()
        return [tuple(v.co) for v in bm.verts], [tuple(v.index for v in f.verts) for f in bm.faces]
    finally:
        bm.free()


def _ring_parameters(ring):
    lengths = [(Vector(b)-Vector(a)).length for a, b in zip(ring, ring[1:]+ring[:1])]
    total = sum(lengths)
    result, run = [], 0.
    for length in lengths:
        result.append(run/total); run += length
    return result, lengths, total


def _ring_at(ring, lengths, total, t):
    target = (t % 1.)*total
    for i, length in enumerate(lengths):
        if target <= length or i == len(lengths)-1:
            a, b = Vector(ring[i]), Vector(ring[(i+1) % len(ring)])
            return a.lerp(b, min(1., target/length) if length > 0 else 0.)
        target -= length


def loft(sketch_a, source_a, sketch_b, source_b):
    """Join two closed outer contours on different planes with ruled walls.

    Each ring keeps its own corners: both are sampled at the union of their
    normalized perimeter parameters. The start of the second ring is the vertex
    that best matches the first one around their centroids (least twist).
    """
    from mathutils.geometry import tessellate_polygon
    rings = []
    for sketch, source in ((sketch_a, source_a), (sketch_b, source_b)):
        if len(region(sketch, source)) != 1:
            raise CommandError('El solevado une contornos exteriores sin huecos', code='cad_profile_invalid')
        rings.append([Vector(world(sketch, *p)) for p in outline(source)])
    a, b = rings
    def newell(ring):
        n = Vector((0., 0., 0.))
        for p, q in zip(ring, ring[1:]+ring[:1]):
            n += Vector((p.y*q.z-p.z*q.y, p.z*q.x-p.x*q.z, p.x*q.y-p.y*q.x))
        return n
    ca, cb = sum(a, Vector())/len(a), sum(b, Vector())/len(b)
    axis = newell(a).normalized()
    if abs((cb-ca).dot(axis)) < 1e-7 and abs((cb-ca).dot(newell(b).normalized())) < 1e-7:
        raise CommandError('Los dos croquis están en el mismo plano; separa uno de ellos', code='cad_profile_invalid')
    if newell(b).dot(newell(a)) < 0: b.reverse()
    def local(ring, center):
        return [(p-center)-axis*(p-center).dot(axis) for p in ring]
    la, lb = local(a, ca), local(b, cb)
    ta, lengths_a, total_a = _ring_parameters(a)
    probes = [_ring_at(la, lengths_a, total_a, i/64) for i in range(64)]
    tb0, lengths_b, total_b = _ring_parameters(b)
    candidates = range(len(b)) if len(b) <= 512 else range(0, len(b), len(b)//512+1)
    def cost(start):
        return sum((_ring_at(lb, lengths_b, total_b, tb0[start]+i/64)-p).length_squared for i, p in enumerate(probes))
    start = min(candidates, key=cost)
    b = b[start:]+b[:start]
    tb, lengths_b, total_b = _ring_parameters(b)
    params = sorted(set(round(t, 12) for t in ta+tb))
    ring_a = [_ring_at(a, lengths_a, total_a, t) for t in params]
    ring_b = [_ring_at(b, lengths_b, total_b, t) for t in params]
    n = len(params)
    side = 1. if (cb-ca).dot(axis) > 0 else -1.
    vertices = [tuple(p) for p in ring_a+ring_b]
    faces = [(i, (i+1) % n, (i+1) % n+n, i+n) if side > 0 else (i+n, (i+1) % n+n, (i+1) % n, i) for i in range(n)]
    for ring, offset, flip in ((ring_a, 0, True), (ring_b, n, False)):
        for tri in tessellate_polygon([[p.copy() for p in ring]]):
            tri = tuple(i+offset for i in tri)
            # Orient every cap triangle along the loft axis before the global check.
            p, q, r = (Vector(vertices[i]) for i in tri)
            if ((q-p).cross(r-p).dot(axis)*side > 0) == flip: tri = tuple(reversed(tri))
            faces.append(tri)
    volume = sum(Vector(vertices[f[0]]).dot(Vector(vertices[f[i]]).cross(Vector(vertices[f[i+1]])))
                 for f in faces for i in range(1, len(f)-1))
    if abs(volume) < 1e-18:
        raise CommandError('El solevado no encierra volumen', code='cad_profile_invalid')
    if volume < 0: faces = [tuple(reversed(f)) for f in faces]
    return vertices, faces


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


def helix(sketch, source, axis, pitch, turns, hand='RIGHT'):
    """Sweep a closed contour around an in-plane axis while it advances `pitch` per turn."""
    import math
    from mathutils.geometry import tessellate_polygon
    if len(region(sketch, source)) != 1:
        raise CommandError('El barrido helicoidal usa un contorno sin huecos', code='cad_profile_invalid')
    ring = outline(source)
    (ax, ay), (dx, dy) = helix_axis(sketch, axis)
    heights = [(x-ax)*dx+(y-ay)*dy for x, y in ring]
    radial = [-(x-ax)*dy+(y-ay)*dx for x, y in ring]   # signed distance to the axis
    if min(radial) <= 1e-9 and max(radial) >= -1e-9:
        raise CommandError('El perfil toca o cruza el eje; sepáralo del eje para barrerlo', code='cad_profile_invalid')
    if pitch <= max(heights)-min(heights)+1e-9:
        raise CommandError('El paso debe superar la altura del perfil a lo largo del eje, o las vueltas se solapan', code='cad_profile_invalid')
    basis = frame(sketch)
    o, fx, fy, fn = (Vector(basis[k]) for k in ('origin', 'x', 'y', 'normal'))
    origin = o+fx*ax+fy*ay
    d = (fx*dx+fy*dy).normalized()
    side = 1. if radial[0] > 0 else -1.
    u = (fx*-dy+fy*dx)*side                                  # from the axis toward the profile
    turn = 1. if hand == 'RIGHT' else -1.
    w = d.cross(u)*turn
    steps = max(8, math.ceil(turns*48))
    n = len(ring)
    vertices = []
    for k in range(steps+1):
        theta = math.tau*turns*k/steps
        c, s = math.cos(theta), math.sin(theta)
        for h, r in zip(heights, radial):
            vertices.append(tuple(origin+d*(h+pitch*turns*k/steps)+(u*c+w*s)*abs(r)))
    # Moving direction along the sketch normal decides which side faces outward.
    sigma = 1. if w.dot(fn) > 0 else -1.
    faces = []
    for k in range(steps):
        a, b = k*n, (k+1)*n
        for i in range(n):
            quad = (a+i, a+(i+1) % n, b+(i+1) % n, b+i)
            faces.append(quad if sigma > 0 else tuple(reversed(quad)))
    for tri in tessellate_polygon([[Vector((x, y, 0.)) for x, y in ring]]):
        (x0, y0), (x1, y1), (x2, y2) = (ring[i] for i in tri)
        if (x1-x0)*(y2-y0)-(y1-y0)*(x2-x0) < 0: tri = tuple(reversed(tri))   # CCW about the sketch normal
        faces.append(tuple(reversed(tri)) if sigma > 0 else tuple(tri))
        end = tuple(i+steps*n for i in tri)
        faces.append(end if sigma > 0 else tuple(reversed(end)))
    volume = sum(Vector(vertices[f[0]]).dot(Vector(vertices[f[i]]).cross(Vector(vertices[f[i+1]])))
                 for f in faces for i in range(1, len(f)-1))
    if volume < 0: faces = [tuple(reversed(f)) for f in faces]
    return vertices, faces


def revolve(sketch, source, axis, angle):
    """Revolve a closed contour `angle` degrees (≤ 360) around an in-plane axis.

    Unlike the helix, the contour may rest on the axis (cones, domes): those points
    are shared by every step so the solid stays closed. A full turn welds its last
    step to the first and has no end caps.
    """
    import math
    from mathutils.geometry import tessellate_polygon
    if len(region(sketch, source)) != 1:
        raise CommandError('La revolución usa un contorno sin huecos', code='cad_profile_invalid')
    ring = outline(source)
    (ax, ay), (dx, dy) = helix_axis(sketch, axis)
    heights = [(x-ax)*dx+(y-ay)*dy for x, y in ring]
    radial = [-(x-ax)*dy+(y-ay)*dx for x, y in ring]
    span = max(max(heights)-min(heights), max(abs(r) for r in radial), 1e-12)
    eps = span*1e-9
    if min(radial) < -eps and max(radial) > eps:
        raise CommandError('El perfil cruza el eje; déjalo a un lado del eje (puede apoyarse en él)', code='cad_profile_invalid')
    if max(abs(r) for r in radial) <= eps:
        raise CommandError('El perfil está sobre el eje y no encierra volumen', code='cad_profile_invalid')
    full = angle >= 360-1e-9
    basis = frame(sketch)
    o, fx, fy, fn = (Vector(basis[k]) for k in ('origin', 'x', 'y', 'normal'))
    origin = o+fx*ax+fy*ay
    d = (fx*dx+fy*dy).normalized()
    side = 1. if max(radial) > eps else -1.
    u = (fx*-dy+fy*dx)*side
    w = d.cross(u)
    steps = max(4, math.ceil(angle/360*64))
    rings = steps if full else steps+1
    n = len(ring)
    on_axis = [abs(r) <= eps for r in radial]
    vertices, index = [], {}
    for i in range(n):
        if on_axis[i]:
            index[(None, i)] = len(vertices); vertices.append(tuple(origin+d*heights[i]))
    for k in range(rings):
        theta = math.radians(angle)*k/steps
        c, s = math.cos(theta), math.sin(theta)
        for i in range(n):
            if not on_axis[i]:
                index[(k, i)] = len(vertices)
                vertices.append(tuple(origin+d*heights[i]+(u*c+w*s)*abs(radial[i])))
    def at(k, i):
        return index[(None, i)] if on_axis[i] else index[(k % rings if full else k, i)]
    faces = []
    for k in range(steps):
        for i in range(n):
            j = (i+1) % n
            loop = []
            for v in (at(k, i), at(k, j), at(k+1, j), at(k+1, i)):
                if v not in loop: loop.append(v)
            if len(loop) >= 3: faces.append(tuple(loop))
    caps = []
    if not full:
        for tri in tessellate_polygon([[Vector((x, y, 0.)) for x, y in ring]]):
            caps.append(tuple(at(0, i) for i in tri))
            caps.append(tuple(at(steps, i) for i in reversed(tri)))
        # Side quads share one winding; a cap wound like its neighbouring side
        # repeats a directed edge and must be flipped to close the surface.
        directed = {(f[i], f[(i+1) % len(f)]) for f in faces for i in range(len(f))}
        caps = [tuple(reversed(f)) if any((f[i], f[(i+1) % len(f)]) in directed for i in range(len(f))) else f
                for f in caps]
    faces += caps
    volume = sum(Vector(vertices[f[0]]).dot(Vector(vertices[f[i]]).cross(Vector(vertices[f[i+1]])))
                 for f in faces for i in range(1, len(f)-1))
    if volume < 0: faces = [tuple(reversed(f)) for f in faces]
    return vertices, faces
