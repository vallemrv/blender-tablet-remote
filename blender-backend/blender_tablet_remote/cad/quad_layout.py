"""Quad layout of CAD display meshes, derived from each planar design face.

Coplanar kernel polygons form one face. A face without holes becomes one
four-sided patch; a face with one hole becomes a frame of four patches joined to
the hole by straight connectors. Patches are filled by transfinite (Coons)
interpolation, so a circle cap is a grid without a central pole.

Opposite sides of a patch need equal subdivisions. Tessellated polylines (circle
and arc samples, edges already split by booleans) are fixed; a straight boundary
edge that is a whole side everywhere and every connector are free counts. The
counts are solved across all faces, so neighbours share their new vertices and
no T-junction appears. A face whose layout conflicts or would invert keeps its
kernel polygons, and `tidy_mesh` finishes those as before.
"""
import math
from mathutils import Vector

SHARP = math.radians(35)
# Connector cells may be this much longer than wide: rings stay light.
ASPECT = 2


def quad_mesh(vertices, faces):
    from .kernel import tidy_mesh
    points = [Vector(v) for v in vertices]
    regions = _regions(points, faces)
    rejected = set()
    for _ in range(len(regions) + 1):
        layouts = {}
        for index, region in enumerate(regions):
            if index not in rejected:
                layout = _layout(points, faces, region)
                if layout is not None:
                    layouts[index] = layout
        counts, conflict = _solve(points, layouts)
        if conflict is None:
            mesh, conflict = _build(points, faces, regions, layouts, counts)
            if conflict is None:
                return tidy_mesh(*mesh)
        rejected.add(conflict)
    return tidy_mesh(vertices, faces)


def _newell(points, face):
    normal = Vector()
    for a, b in zip(face, face[1:] + face[:1]):
        p, q = points[a], points[b]
        normal += Vector(((p.y-q.y)*(p.z+q.z), (p.z-q.z)*(p.x+q.x), (p.x-q.x)*(p.y+q.y)))
    return normal


def _regions(points, faces):
    extent = max((max(p[i] for p in points)-min(p[i] for p in points) for i in range(3)), default=0.)
    tolerance = extent*1e-6+1e-12
    normals = [_newell(points, face) for face in faces]
    normals = [n.normalized() if n.length > 0 else None for n in normals]
    linked = {}
    for index, face in enumerate(faces):
        for a, b in zip(face, face[1:] + face[:1]):
            linked.setdefault((min(a, b), max(a, b)), []).append(index)
    owner = [None]*len(faces)
    regions = []
    for seed, normal in enumerate(normals):
        if owner[seed] is not None:
            continue
        owner[seed] = len(regions)
        chosen = [seed]; pending = [seed]
        while pending and normal is not None:
            face = faces[pending.pop()]
            for a, b in zip(face, face[1:] + face[:1]):
                for other in linked[(min(a, b), max(a, b))]:
                    if owner[other] is None and normals[other] is not None and normals[other].dot(normal) > 1-1e-6 and \
                            all(abs((points[i]-points[faces[seed][0]]).dot(normal)) <= tolerance for i in faces[other]):
                        owner[other] = len(regions); chosen.append(other); pending.append(other)
        regions.append(dict(faces=chosen, normal=normal))
    return regions


def _turns(loop2d):
    result = []
    for a, b, c in zip(loop2d[-1:] + loop2d[:-1], loop2d, loop2d[1:] + loop2d[:1]):
        d, e = b-a, c-b
        result.append(math.atan2(d.x*e.y-d.y*e.x, d.dot(e)))
    return result


def _corners(loop2d):
    """Four patch corners: the sharp ones, else quarters of the total turning."""
    turns = _turns(loop2d)
    if any(t < -SHARP for t in turns):
        return None
    sharp = [i for i, t in enumerate(turns) if t > SHARP]
    if len(sharp) == 4:
        return sharp
    # Nearest vertex to each quarter: equal samples of a circle must not drift
    # to a neighbour through single-precision noise in their turns.
    total = sum(turns); cumulative = []
    for turn in turns:
        cumulative.append((cumulative[-1] if cumulative else 0.)+turn)
    corners = [min(range(len(turns)), key=lambda i: abs(cumulative[i]-total*k/4)) for k in (1, 2, 3, 4)]
    return corners if len(set(corners)) == 4 and corners == sorted(corners) else None


def _hole_corners(outer2d, corners, hole2d):
    """Hole vertices facing the outer corners, in the same angular order."""
    ccw = list(reversed(range(len(hole2d))))
    center = sum(hole2d, Vector((0., 0.)))/len(hole2d)
    def angle(p):
        return math.atan2(p.y-center.y, p.x-center.x)
    def gap(a, b):
        return abs((a-b+math.pi) % math.tau-math.pi)
    targets = [angle(outer2d[c]) for c in corners]
    turns = _turns([hole2d[i] for i in ccw])
    sharp = [ccw[i] for i, t in enumerate(turns) if t > SHARP]
    if len(sharp) == 4:
        chosen = min((sharp[k:]+sharp[:k] for k in range(4)),
                     key=lambda order: sum(gap(angle(hole2d[h]), t) for h, t in zip(order, targets)))
    else:
        chosen = [min(range(len(hole2d)), key=lambda i: gap(angle(hole2d[i]), t)) for t in targets]
    positions = [ccw.index(h) for h in chosen]
    steps = [(b-a) % len(ccw) for a, b in zip(positions, positions[1:]+positions[:1])]
    return chosen if len(set(chosen)) == 4 and sum(steps) == len(ccw) else None


def _path(loop, start, end):
    result = [loop[start]]
    while start != end:
        start = (start+1) % len(loop); result.append(loop[start])
    return result


def _layout(points, faces, region):
    normal = region['normal']
    if normal is None:
        return None
    directed = [(a, b) for index in region['faces'] for a, b in zip(faces[index], faces[index][1:]+faces[index][:1])]
    present = set(directed)
    if len(present) != len(directed):
        return None
    following = {}
    for a, b in directed:
        if (b, a) not in present:
            if a in following:
                return None
            following[a] = b
    loops = []
    while following:
        start, current = next(iter(following.items()))
        del following[start]; loop = [start]
        while current != start:
            if current not in following:
                return None
            loop.append(current); current = following.pop(current)
        loops.append(loop)
    origin = points[loops[0][0]] if loops else None
    axis_u = normal.orthogonal().normalized(); axis_v = normal.cross(axis_u)
    def flat(loop):
        return [Vector(((points[i]-origin).dot(axis_u), (points[i]-origin).dot(axis_v))) for i in loop]
    def area(loop2d):
        return sum(a.x*b.y-a.y*b.x for a, b in zip(loop2d, loop2d[1:]+loop2d[:1]))
    flats = [flat(loop) for loop in loops]
    outer = [k for k, loop2d in enumerate(flats) if area(loop2d) > 0]
    holes = [k for k, loop2d in enumerate(flats) if area(loop2d) <= 0]
    if len(outer) != 1 or len(holes) > 1:
        return None
    loop, loop2d = loops[outer[0]], flats[outer[0]]
    corners = _corners(loop2d)
    if corners is None:
        return None
    frame = (origin, axis_u, axis_v)
    if not holes:
        sides = [('PATH', _path(loop, a, b)) for a, b in zip(corners, corners[1:]+corners[:1])]
        return dict(frame=frame, patches=[sides])
    hole, hole2d = loops[holes[0]], flats[holes[0]]
    chosen = _hole_corners(loop2d, corners, hole2d)
    if chosen is None:
        return None
    links = [('LINK', (loop[c], hole[h])) for c, h in zip(corners, chosen)]
    patches = []
    for k in range(4):
        m = (k+1) % 4
        patches.append([('PATH', _path(loop, corners[k], corners[m])), links[m],
                        ('PATH', _path(hole, chosen[m], chosen[k])), ('LINK', links[k][1], True)])
    return dict(frame=frame, patches=patches)


def _edges(side):
    return [(min(a, b), max(a, b)) for a, b in zip(side[1], side[1][1:])]


def _length(points, side):
    if side[0] == 'LINK':
        return (points[side[1][0]]-points[side[1][1]]).length
    return sum((points[a]-points[b]).length for a, b in zip(side[1], side[1][1:]))


def _solve(points, layouts):
    """Equal counts on opposite sides; returns counts or the conflicting face."""
    single = {}
    for layout in layouts.values():
        for patch in layout['patches']:
            for side in patch:
                if side[0] == 'PATH':
                    edges = _edges(side)
                    for edge in edges:
                        single[edge] = single.get(edge, True) and len(edges) == 1
    parent = {}; value = {}
    def root(item):
        parent.setdefault(item, item)
        while parent[item] != item:
            parent[item] = parent[parent[item]]; item = parent[item]
        return item
    def term(side):
        if side[0] == 'LINK':
            return ('LINK', side[1])
        edges = _edges(side)
        return edges[0] if len(edges) == 1 and single[edges[0]] else len(edges)
    for index, layout in layouts.items():
        for patch in layout['patches']:
            for a, b in ((patch[0], patch[2]), (patch[1], patch[3])):
                a, b = term(a), term(b)
                if isinstance(a, int) and isinstance(b, int):
                    if a != b: return None, index
                    continue
                if isinstance(a, int): a, b = b, a
                ra = root(a)
                if isinstance(b, int):
                    if value.setdefault(ra, b) != b: return None, index
                    continue
                rb = root(b)
                if ra != rb:
                    if ra in value and rb in value and value[ra] != value[rb]: return None, index
                    parent[rb] = ra
                    if rb in value: value[ra] = value.pop(rb)
    # A connector grows from the hole spacing to the outer spacing; its count
    # integrates 1/spacing so the rings keep a bounded aspect along the way.
    grading = {}; free = {}
    def count(side):
        t = term(side)
        return t if isinstance(t, int) else value.get(root(t), 1)
    for layout in layouts.values():
        for patch in layout['patches']:
            if patch[1][0] != 'LINK':
                continue
            total = count(patch[0])
            outer = _length(points, patch[0])/total; inner = _length(points, patch[2])/total
            for link in (patch[1], patch[3]):
                grading[link[1]] = (outer, inner)
                group = root(('LINK', link[1]))
                if group in value:
                    continue
                length = _length(points, link)
                n = length/outer if abs(outer-inner) <= 1e-9*outer else length*math.log(inner/outer)/(inner-outer)
                free[group] = max(free.get(group, 1), min(256, max(1, round(n/ASPECT))))
    value.update(free)
    return dict(count=lambda item: value.get(root(item), 1) if item in parent else 1, grading=grading), None


def _build(points, faces, regions, layouts, counts):
    positions = list(points)
    edge_cache = {}; link_cache = {}
    def edge_vertices(a, b):
        key = (min(a, b), max(a, b))
        if key not in edge_cache:
            k = counts['count'](key)
            p, q = positions[key[0]], positions[key[1]]
            middle = []
            for i in range(1, k):
                positions.append(p.lerp(q, i/k)); middle.append(len(positions)-1)
            edge_cache[key] = [key[0], *middle, key[1]]
        result = edge_cache[key]
        return result if a == key[0] else list(reversed(result))
    def link_vertices(key):
        if key not in link_cache:
            n = counts['count'](('LINK', key))
            start, end = counts['grading'].get(key, (1., 1.))
            ratio = (end/start)**(1/max(n-1, 1)) if start > 0 and end > 0 else 1.
            weights = [ratio**i for i in range(n)]
            p, q = positions[key[0]], positions[key[1]]
            middle = []; walked = 0.
            for w in weights[:-1]:
                walked += w
                positions.append(p.lerp(q, walked/sum(weights))); middle.append(len(positions)-1)
            link_cache[key] = [key[0], *middle, key[1]]
        return link_cache[key]
    def side_vertices(side):
        if side[0] == 'LINK':
            result = link_vertices(side[1])
            return list(reversed(result)) if len(side) > 2 else result
        result = [side[1][0]]
        for a, b in zip(side[1], side[1][1:]):
            result.extend(edge_vertices(a, b)[1:])
        return result
    output = []
    for index, region in enumerate(regions):
        layout = layouts.get(index)
        if layout is None:
            for face in (faces[i] for i in region['faces']):
                polygon = []
                for a, b in zip(face, face[1:]+face[:1]):
                    polygon.extend(edge_vertices(a, b)[:-1])
                output.append(polygon)
            continue
        origin, axis_u, axis_v = layout['frame']
        def flat(i):
            p = positions[i]-origin
            return (p.dot(axis_u), p.dot(axis_v))
        quads = []
        for patch in layout['patches']:
            bottom, right, top, left = (side_vertices(side) for side in patch)
            top.reverse(); left.reverse()
            m, n = len(bottom)-1, len(right)-1
            if len(top)-1 != m or len(left)-1 != n:
                return None, index
            def params(ids):
                steps = [0.]
                for a, b in zip(ids, ids[1:]):
                    steps.append(steps[-1]+(positions[b]-positions[a]).length)
                return [s/steps[-1] if steps[-1] > 0 else 0. for s in steps]
            sb, st, tl, tr = params(bottom), params(top), params(left), params(right)
            c00, c10, c01, c11 = (positions[i] for i in (bottom[0], bottom[-1], top[0], top[-1]))
            grid = [[None]*(n+1) for _ in range(m+1)]
            for i in range(m+1):
                grid[i][0] = bottom[i]; grid[i][n] = top[i]
            for j in range(n+1):
                grid[0][j] = left[j]; grid[m][j] = right[j]
            for i in range(1, m):
                for j in range(1, n):
                    du, dv = st[i]-sb[i], tr[j]-tl[j]
                    u = (sb[i]+tl[j]*du)/(1-du*dv); v = tl[j]+u*dv
                    point = ((1-v)*positions[bottom[i]]+v*positions[top[i]]+(1-u)*positions[left[j]]+u*positions[right[j]]
                             -((1-u)*(1-v)*c00+u*(1-v)*c10+(1-u)*v*c01+u*v*c11))
                    positions.append(point); grid[i][j] = len(positions)-1
            for i in range(m):
                for j in range(n):
                    quad = (grid[i][j], grid[i+1][j], grid[i+1][j+1], grid[i][j+1])
                    corners = [flat(q) for q in quad]
                    size = sum(abs(a[0]-b[0])+abs(a[1]-b[1]) for a, b in zip(corners, corners[1:]+corners[:1]))
                    for a, b, c in zip(corners[-1:]+corners[:-1], corners, corners[1:]+corners[:1]):
                        if (b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]) < -1e-9*size*size:
                            return None, index
                    if sum(a[0]*b[1]-a[1]*b[0] for a, b in zip(corners, corners[1:]+corners[:1])) <= 1e-12*size*size:
                        return None, index
                    quads.append(quad)
        output.extend(quads)
    used = sorted({i for face in output for i in face})
    remap = {old: new for new, old in enumerate(used)}
    return ([tuple(positions[i]) for i in used], [tuple(remap[i] for i in face) for face in output]), None
