"""Required OpenCascade CAD kernel: exact BREP evaluation, display mesh contract.

The document stays the source. Each feature is built as an OCCT solid with exact
planes, cylinders and tori; the host still receives compact meshes in metres, so
display, selection and copies keep their contract. OCP lives in a private site
directory (`occt_path`) loaded into the auxiliary Blender, never into the scene.
Internally the kernel works in millimetres: OCCT tolerances are absolute.
"""
import hashlib
import math
import os
import sys

from . import document as model
from . import mirror
from ..errors import CommandError

DEFAULT_PATH = os.path.join(os.path.expanduser('~'), '.local', 'share', 'blender-tablet-remote', 'occt')
MM = 1000.


INSTALL_HINT = 'Ejecuta blender-backend/tools/install_occt.sh y reinicia Blender.'


def configured_path():
    """Private OCP directory; the interactive host never imports OCP."""
    from .. import get_prefs
    prefs = get_prefs()
    return (getattr(prefs, 'occt_path', '') or DEFAULT_PATH) if prefs else DEFAULT_PATH


def require_available(path=None):
    path = path or configured_path()
    if not os.path.isdir(os.path.join(path, 'OCP')):
        raise CommandError('Falta OpenCascade (OCP), obligatorio para CAD. '+INSTALL_HINT, code='cad_kernel_missing')
    return path


def load(path=None):
    """Load the required BREP kernel in the evaluator process, without fallback."""
    path = require_available(path)
    if path not in sys.path:
        sys.path.append(path)
    try:
        import OCP.BRepAlgoAPI  # noqa: F401
    except Exception as exc:
        raise CommandError('No se puede cargar OpenCascade (OCP). '+INSTALL_HINT, code='cad_kernel_missing') from exc


def geometry_key(doc, limit, scale):
    """Unused sketches, names and revisions do not invalidate a displayed solid."""
    features = []
    sketches = {}
    for node in model.history(doc):
        if node['kind'] == 'FEATURE' and node['enabled']:
            feature = dict(model.find(doc,'features',node['id']))
            feature.pop('name', None)
            if feature.get('sketch_id'):
                source=model.find(doc,'sketches',feature['sketch_id'])
                sketches[source['id']]=dict(frame=model.frame(source),entities=source['entities'])
            features.append(feature)
            for key in ('profile_id', 'to_profile_id'):
                if node.get(key):
                    sketch, _ = model.profile(doc, node[key])
                    sketches[sketch['id']] = dict(frame=model.frame(sketch), entities=sketch['entities'])
            if node.get('path_sketch_id'):
                path = model.find(doc, 'sketches', node['path_sketch_id'])
                sketches[path['id']] = dict(frame=model.frame(path), entities=path['entities'])
        if node['id'] == limit:
            break
    return model.dumps(dict(id=doc['id'], features=features, sketches=sketches, scale=scale))


# ---------------------------------------------------------------- geometry

def _frame(sketch):
    from OCP.gp import gp_Pnt, gp_Dir
    f = model.frame(sketch)
    return (gp_Pnt(*(c*MM for c in f['origin'])), gp_Dir(*f['x']), gp_Dir(*f['y']), gp_Dir(*f['normal']))


def _point(basis, x, y):
    from OCP.gp import gp_Pnt
    o, fx, fy, _ = basis
    return gp_Pnt(o.X()+(fx.X()*x+fy.X()*y)*MM, o.Y()+(fx.Y()*x+fy.Y()*y)*MM, o.Z()+(fx.Z()*x+fy.Z()*y)*MM)


def _wire(pieces):
    """Closed or open chain of ('L', a, b) / ('A', a, mid, b) in 3D, sharing exact vertices."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeVertex
    from OCP.GC import GC_MakeArcOfCircle
    closed = pieces[0][1].Distance(pieces[-1][-1]) < 1e-6
    vertices = [BRepBuilderAPI_MakeVertex(p[1]).Vertex() for p in pieces]
    vertices.append(vertices[0] if closed else BRepBuilderAPI_MakeVertex(pieces[-1][-1]).Vertex())
    maker = BRepBuilderAPI_MakeWire()
    for i, piece in enumerate(pieces):
        a, b = vertices[i], vertices[i+1]
        if piece[0] == 'L':
            edge = BRepBuilderAPI_MakeEdge(a, b).Edge()
        else:
            edge = BRepBuilderAPI_MakeEdge(GC_MakeArcOfCircle(piece[1], piece[2], piece[3]).Value(), a, b).Edge()
        maker.Add(edge)
    if not maker.IsDone():
        raise CommandError('El contorno no forma un perfil continuo', code='cad_profile_invalid')
    return maker.Wire()


def _polygon(basis, points):
    ps = [_point(basis, *p) for p in points]
    return [('L', a, b) for a, b in zip(ps, ps[1:]+ps[:1])]


def _arc_points(e, reverse=False):
    start, sweep = math.radians(e['start']), math.radians(e['sweep'])
    at = lambda t: (e['x']+e['radius']*math.cos(start+sweep*t), e['y']+e['radius']*math.sin(start+sweep*t))
    points = (at(0), at(.5), at(1))
    return tuple(reversed(points)) if reverse else points


def _entity_wire(sketch, e):
    """Exact closed wire of one profile entity: lines, arcs and full circles."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
    from OCP.gp import gp_Ax2, gp_Circ
    basis = _frame(sketch)
    kind = e['type']
    if kind == 'CIRCLE':
        circle = gp_Circ(gp_Ax2(_point(basis, e['x'], e['y']), basis[3], basis[1]), e['diameter']/2*MM)
        return BRepBuilderAPI_MakeWire(BRepBuilderAPI_MakeEdge(circle).Edge()).Wire()
    if kind == 'SLOT':
        a, half, r = math.radians(e['angle']), e['length']/2, e['width']/2
        ux, uy = math.cos(a), math.sin(a)
        c1 = (e['x']+half*ux, e['y']+half*uy); c2 = (e['x']-half*ux, e['y']-half*uy)
        side = lambda c, s: (c[0]-s*r*uy, c[1]+s*r*ux)
        p = lambda q: _point(basis, *q)
        return _wire([('L', p(side(c2, -1)), p(side(c1, -1))),
                      ('A', p(side(c1, -1)), p((c1[0]+r*ux, c1[1]+r*uy)), p(side(c1, 1))),
                      ('L', p(side(c1, 1)), p(side(c2, 1))),
                      ('A', p(side(c2, 1)), p((c2[0]-r*ux, c2[1]-r*uy)), p(side(c2, -1)))])
    if kind == 'POLYGON':
        members = {m['id']: m for m in sketch['entities'] if m['id'] in e['members']}
        chain = []
        for identifier in e['members']:
            m = members[identifier]
            ends = model.outline(m)
            ends = (ends[0], ends[-1])
            if chain:
                last = chain[-1][-1]
                reverse = math.dist(last, ends[1]) < math.dist(last, ends[0])
            elif len(e['members']) > 1:
                nxt = model.outline(members[e['members'][1]])
                reverse = min(math.dist(ends[0], nxt[0]), math.dist(ends[0], nxt[-1])) < \
                    min(math.dist(ends[1], nxt[0]), math.dist(ends[1], nxt[-1]))
            else:
                reverse = False
            if m['type'] == 'LINE':
                pts = [(m['x'], m['y']), (m['x2'], m['y2'])]
                chain.append(tuple(reversed(pts)) if reverse else tuple(pts))
            else:
                chain.append(_arc_points(m, reverse))
        pieces = []
        for i, pts in enumerate(chain):
            # Share every junction exactly: each piece starts where the previous ended.
            start = chain[i-1][-1] if i else chain[-1][-1]
            pts = (start,)+tuple(pts[1:])
            pieces.append(('L' if len(pts) == 2 else 'A',)+tuple(_point(basis, *q) for q in pts))
        return _wire(pieces)
    # RECTANGLE, NGON and GEAR are straight-sided outlines.
    return _wire(_polygon(basis, model.outline(e)))


def _face(sketch, outer, holes):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.ShapeFix import ShapeFix_Face
    maker = BRepBuilderAPI_MakeFace(_entity_wire(sketch, outer), True)
    for hole in holes:
        maker.Add(_entity_wire(sketch, hole))
    if not maker.IsDone():
        raise CommandError('El perfil no genera una cara plana', code='cad_profile_invalid')
    fix = ShapeFix_Face(maker.Face())
    fix.FixOrientation()
    fix.Perform()
    return fix.Face()


def _faces(sketch, source):
    """Exact faces of a profile: outer contour minus the contours it contains."""
    from .kernel import region
    closed = model.closed_entities(sketch)
    if source['type'] == 'SKETCH':
        rings = [(item, model.outline(item)) for item in closed]
        roots = [item for item, ring in rings if not any(
            other['id'] != item['id'] and model.contains(o, ring[0]) for other, o in rings)]
        if not roots:
            raise CommandError('El croquis no contiene regiones exteriores válidas', code='cad_profile_invalid')
        return [face for root in roots for face in _faces(sketch, root)]
    region(sketch, source)   # validate analytic sketch regions before building BREP
    outer = model.outline(source)
    holes = [e for e in closed if e['id'] != source['id'] and model.contains(outer, model.outline(e)[0])]
    return [_face(sketch, source, holes)]


def _compound(shapes):
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound
    builder = BRep_Builder(); compound = TopoDS_Compound(); builder.MakeCompound(compound)
    for shape in shapes:
        builder.Add(compound, shape)
    return compound


def _volume(shape):
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return props.Mass()


def _extent(shape):
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    if box.IsVoid():
        return 1.
    low, high = box.CornerMin(), box.CornerMax()
    return max(high.X()-low.X(), high.Y()-low.Y(), high.Z()-low.Z(), 1e-6)


def _clean(shape):
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    unify = ShapeUpgrade_UnifySameDomain(shape, True, True, True)
    unify.Build()
    return unify.Shape()


def _valid(shape, code):
    from OCP.BRepCheck import BRepCheck_Analyzer
    if shape is None or shape.IsNull() or not BRepCheck_Analyzer(shape).IsValid() or _volume(shape) <= 1e-9:
        raise CommandError('La operación produce un sólido vacío o geometría inválida', code=code)
    return shape


def _boolean(kind, base, tool):
    """Captured faces and solved sketches carry micrometre noise: a coplanar
    contact off by 1 µm leaves sliver faces inside an exact boolean. A small
    fuzzy value (1e-5 of the part) merges them; exact and coarser values are
    fallbacks when it fails."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse, BRepAlgoAPI_Cut
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.collections import List_TopoDS_Shape
    code = 'cad_union_invalid' if kind == 'UNION' else 'cad_cut_invalid'
    extent = _extent(base)
    result = None
    for fuzzy in (max(1e-4, extent*1e-5), 0., max(1e-3, extent*1e-4)):
        op = (BRepAlgoAPI_Fuse if kind == 'UNION' else BRepAlgoAPI_Cut)()
        arguments, tools = List_TopoDS_Shape(), List_TopoDS_Shape()
        arguments.Append(base); tools.Append(tool)
        op.SetArguments(arguments); op.SetTools(tools)
        if fuzzy:
            op.SetFuzzyValue(fuzzy)
        op.SetRunParallel(True)
        op.Build()
        if not op.IsDone() or op.Shape().IsNull():
            continue
        raw = op.Shape()
        if not BRepCheck_Analyzer(raw).IsValid() or _volume(raw) <= 1e-9:
            continue
        candidate = _clean(raw)
        if not candidate.IsNull() and BRepCheck_Analyzer(candidate).IsValid() and _volume(candidate) > 1e-9:
            result = candidate
        else:
            # Unifying coplanar faces can invalidate an otherwise valid union
            # along the micrometre offsets of captured sketch planes.
            result = raw
        break
    if result is None:
        raise CommandError('La operación produce un sólido vacío o geometría inválida', code=code)
    if kind == 'CUT':
        before = _volume(base)
        if before-_volume(result) <= max(before*1e-7, 1e-9):
            raise CommandError('El perfil no quita material del sólido destino', code='cad_cut_miss')
    return result


def _transformed(shape, trsf):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    return BRepBuilderAPI_Transform(shape, trsf, True).Shape()


def _prism(faces, vector):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.gp import gp_Vec
    shapes = [BRepPrimAPI_MakePrism(face, gp_Vec(*vector)).Shape() for face in faces]
    return shapes[0] if len(shapes) == 1 else _compound(shapes)


def _translated(shape, vector):
    from OCP.gp import gp_Trsf, gp_Vec
    trsf = gp_Trsf(); trsf.SetTranslation(gp_Vec(*vector))
    return _transformed(shape, trsf)


def operand(sketch, source, feature, base=None):
    """Tool solid of an extrusion or cut before it joins or leaves its body."""
    faces = _faces(sketch, source)
    normal = model.frame(sketch)['normal']
    extent = feature.get('extent', 'ONE')
    if extent == 'THROUGH_ALL':
        from itertools import product
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib
        from .kernel import through_depth
        if base is None:
            raise CommandError('No hay sólido para perforar', code='cad_dependency')
        box = Bnd_Box()
        BRepBndLib.Add_s(base, box)
        low, high = box.CornerMin(), box.CornerMax()
        corners = list(product((low.X()/MM, high.X()/MM), (low.Y()/MM, high.Y()/MM), (low.Z()/MM, high.Z()/MM)))
        depth = through_depth(sketch, corners, feature.get('mirror'))*MM
        moved = [_translated(f, [-c*depth for c in normal]) for f in faces]
        return _prism(moved, [c*2*depth for c in normal])
    if extent == 'TO_FACE':
        return _to_face(sketch, source, faces, feature['to_face'])
    depth = feature['depth']*MM
    if extent == 'BOTH':
        moved = [_translated(f, [-c*abs(depth) for c in normal]) for f in faces]
        return _prism(moved, [c*2*abs(depth) for c in normal])
    cut = feature.get('operation', feature['type']) == 'CUT'
    signed = -depth if cut else depth
    return _prism(faces, [c*signed for c in normal])


def hole_operand(sketch, feature, base):
    """All screw seats in one cutting compound, located by sketch point IDs."""
    from . import holes
    from .kernel import through_depth, world
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeCone
    from OCP.gp import gp_Pnt, gp_Dir, gp_Ax2
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from itertools import product
    values=holes.measures(feature); basis=model.frame(sketch)
    normal=basis['normal']; direction=gp_Dir(*[-v for v in normal])
    long=feature.get('depth') or .01
    if feature['extent']=='THROUGH_ALL':
        box=Bnd_Box();BRepBndLib.Add_s(base,box);a,b=box.CornerMin(),box.CornerMax()
        long=through_depth(sketch,list(product((a.X()/MM,b.X()/MM),(a.Y()/MM,b.Y()/MM),(a.Z()/MM,b.Z()/MM))))
    result=[];seen=set()
    for point in holes.points(sketch,feature):
        key=(round(point['x'],10),round(point['y'],10))
        if key in seen:continue
        seen.add(key)
        origin=world(sketch,point['x'],point['y'])
        def axis(offset=0):return gp_Ax2(gp_Pnt(*[(origin[i]+normal[i]*offset)*MM for i in range(3)]),direction,gp_Dir(*basis['x']))
        kind=feature['kind'];epsilon=1e-7
        if kind=='INSERT':
            tool=BRepPrimAPI_MakeCylinder(axis(epsilon),values['insert_diameter']*MM/2,(values['insert_depth']+epsilon)*MM).Shape()
        else:
            start=long if feature['extent']=='THROUGH_ALL' else epsilon
            tool=BRepPrimAPI_MakeCylinder(axis(start),values['diameter']*MM/2,(long+start)*MM).Shape()
            head=None
            if kind=='COUNTERBORE':
                head=BRepPrimAPI_MakeCylinder(axis(epsilon),values['head_diameter']*MM/2,(values['head_depth']+epsilon)*MM).Shape()
            elif kind=='COUNTERSINK':
                big,small=values['sink_diameter']/2,values['diameter']/2
                head=BRepPrimAPI_MakeCone(axis(epsilon),(big+epsilon)*MM,small*MM,(big-small+epsilon)*MM).Shape()
            elif kind=='NUT':
                hexagon=dict(id='nut',type='NGON',x=point['x'],y=point['y'],flats=values['nut_flats'],sides=6,angle=0.)
                face=_face(dict(sketch,entities=[hexagon]),hexagon,[])
                head=_prism([_translated(face,[v*epsilon*MM for v in normal])],[-v*(values['nut_depth']+epsilon)*MM for v in normal])
            if head is not None:tool=_boolean('UNION',tool,head)
        result.append(tool)
    return result[0] if len(result)==1 else _compound(result)


def feature_operand(doc, feature, base):
    if feature['type']=='HOLE':
        return hole_operand(model.find(doc,'sketches',feature['sketch_id']),feature,base)
    sketch,source=model.profile(doc,feature['profile_id'])
    return operand(sketch,source,feature,base)


def patterned(doc, feature, base):
    from . import pattern
    from OCP.gp import gp_Trsf,gp_Vec,gp_Ax1,gp_Pnt,gp_Dir
    transforms=[]
    for spec in pattern.copies(feature):
        trsf=gp_Trsf()
        if 'translation' in spec: trsf.SetTranslation(gp_Vec(*(v*MM for v in spec['translation'])))
        else:
            a=spec['axis'];trsf.SetRotation(gp_Ax1(gp_Pnt(*(v*MM for v in a['origin'])),gp_Dir(*a['normal'])),math.radians(spec['angle']))
        transforms.append(trsf)
    result=base
    for identifier in feature['source_ids']:
        source=model.find(doc,'features',identifier);tool=feature_operand(doc,source,base)
        copies=[_transformed(tool,trsf) for trsf in transforms]
        result=_boolean('CUT' if source['type'] in ('CUT','HOLE') else 'UNION',result,_compound(copies))
    return result


def _to_face(sketch, source, faces, to_face):
    """Walls run along the sketch normal and end on the (possibly inclined) face plane."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeHalfSpace
    from OCP.gp import gp_Pln, gp_Pnt, gp_Dir
    basis = model.frame(sketch)
    normal, plane_normal = basis['normal'], to_face['normal']
    facing = sum(a*b for a, b in zip(normal, plane_normal))
    if abs(facing) < 1e-6:
        raise CommandError('La cara es paralela a la dirección de extrusión', code='cad_profile_invalid')
    profiles = model.closed_entities(sketch) if source['type'] == 'SKETCH' else [source]
    points = [point for profile in profiles for point in model.outline(profile)]
    travels = []
    for x, y in points:
        start = [basis['origin'][i]+x*basis['x'][i]+y*basis['y'][i] for i in range(3)]
        travels.append(sum((to_face['origin'][i]-start[i])*plane_normal[i] for i in range(3))/facing)
    span = max(max(abs(t) for t in travels), 1e-9)
    if not (min(travels) > span*1e-6 or max(travels) < -span*1e-6):
        raise CommandError('La cara corta o toca el perfil; elige una que quede entera a un lado',
                           code='cad_profile_invalid')
    sign = 1. if travels[0] > 0 else -1.
    length = (span*2+.001)*MM
    prism = _prism(faces, [c*sign*length for c in normal])
    plane = BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(*(c*MM for c in to_face['origin'])), gp_Dir(*plane_normal))).Face()
    # The half-space that keeps the profile itself.
    x, y = points[0]
    inside = [(basis['origin'][i]+x*basis['x'][i]+y*basis['y'][i])*MM for i in range(3)]
    keep = BRepPrimAPI_MakeHalfSpace(plane, gp_Pnt(*inside)).Solid()
    common = BRepAlgoAPI_Common(prism, keep)
    return _clean(common.Shape())


def _mirrored(shape, spec):
    from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir, gp_Trsf
    axis = mirror.AXIS[spec['plane']]
    origin = [0., 0., 0.]; origin[axis] = spec['offset']*MM
    direction = [0., 0., 0.]; direction[axis] = 1.
    trsf = gp_Trsf(); trsf.SetMirror(gp_Ax2(gp_Pnt(*origin), gp_Dir(*direction)))
    return _transformed(shape, trsf)


# ------------------------------------------------------------- operations

def _axis(sketch, axis):
    from OCP.gp import gp_Ax1, gp_Dir
    from .kernel import helix_axis
    (ax, ay), (dx, dy) = helix_axis(sketch, axis)
    f = model.frame(sketch)
    d = [f['x'][i]*dx+f['y'][i]*dy for i in range(3)]
    return gp_Ax1(_point(_frame(sketch), ax, ay), gp_Dir(*d)), (ax, ay), (dx, dy)


def revolve(sketch, source, axis, angle):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeRevol
    from .kernel import region
    if len(region(sketch, source)) != 1:
        raise CommandError('La revolución usa un contorno sin huecos', code='cad_profile_invalid')
    ring = model.outline(source)
    ax1, (ax, ay), (dx, dy) = _axis(sketch, axis)
    heights = [(x-ax)*dx+(y-ay)*dy for x, y in ring]
    radial = [-(x-ax)*dy+(y-ay)*dx for x, y in ring]
    span = max(max(heights)-min(heights), max(abs(r) for r in radial), 1e-12)
    eps = span*1e-9
    if min(radial) < -eps and max(radial) > eps:
        raise CommandError('El perfil cruza el eje; déjalo a un lado del eje (puede apoyarse en él)', code='cad_profile_invalid')
    if max(abs(r) for r in radial) <= eps:
        raise CommandError('El perfil está sobre el eje y no encierra volumen', code='cad_profile_invalid')
    face = _faces(sketch, source)[0]
    full = angle >= 360-1e-9
    maker = BRepPrimAPI_MakeRevol(face, ax1, 2*math.pi if full else math.radians(angle))
    return _clean(maker.Shape())


def loft(sketch_a, source_a, sketch_b, source_b):
    from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
    from .kernel import region
    for sketch, source in ((sketch_a, source_a), (sketch_b, source_b)):
        if len(region(sketch, source)) != 1:
            raise CommandError('El solevado une contornos exteriores sin huecos', code='cad_profile_invalid')
    fa, fb = model.frame(sketch_a), model.frame(sketch_b)
    ca = [sum(c)/len(c) for c in zip(*model.outline(source_a))]
    cb = [sum(c)/len(c) for c in zip(*model.outline(source_b))]
    pa = [fa['origin'][i]+ca[0]*fa['x'][i]+ca[1]*fa['y'][i] for i in range(3)]
    pb = [fb['origin'][i]+cb[0]*fb['x'][i]+cb[1]*fb['y'][i] for i in range(3)]
    gap = [pb[i]-pa[i] for i in range(3)]
    if abs(sum(g*n for g, n in zip(gap, fa['normal']))) < 1e-7 and abs(sum(g*n for g, n in zip(gap, fb['normal']))) < 1e-7:
        raise CommandError('Los dos croquis están en el mismo plano; separa uno de ellos', code='cad_profile_invalid')
    maker = BRepOffsetAPI_ThruSections(True, True)
    maker.AddWire(_entity_wire(sketch_a, source_a))
    maker.AddWire(_entity_wire(sketch_b, source_b))
    maker.CheckCompatibility(True)
    maker.Build()
    if not maker.IsDone():
        raise CommandError('El solevado no encierra volumen', code='cad_profile_invalid')
    return _valid(maker.Shape(), 'cad_profile_invalid')


def _path_pieces(sketch):
    """Ordered (kind, 2D points) of the single open line/arc chain of a path sketch."""
    from .kernel import sweep_path
    sweep_path(sketch)   # validation and messages shared with the mesh kernel
    edges = [e for e in sketch['entities'] if not e.get('construction', False) and e['type'] in ('LINE', 'ARC')]
    span = max(max(abs(c) for p in model.outline(e) for c in p) for e in edges)
    near = lambda a, b: math.dist(a, b) <= max(span*1e-6, 1e-9)
    def points(e, reverse):
        if e['type'] == 'LINE':
            pts = ((e['x'], e['y']), (e['x2'], e['y2']))
            return tuple(reversed(pts)) if reverse else pts
        return _arc_points(e, reverse)
    remaining = list(edges)
    chain = [points(remaining.pop(0), False)]
    grown = True
    while remaining and grown:
        grown = False
        for e in list(remaining):
            for reverse in (False, True):
                pts = points(e, reverse)
                if near(chain[-1][-1], pts[0]):
                    chain.append(pts)
                elif near(chain[0][0], pts[-1]):
                    chain.insert(0, pts)
                else:
                    continue
                remaining.remove(e); grown = True
                break
    return chain


def _circumcenter(pts):
    (x1, y1), (x2, y2), (x3, y3) = pts
    det = 2*(x1*(y2-y3)+x2*(y3-y1)+x3*(y1-y2))
    return (((x1*x1+y1*y1)*(y2-y3)+(x2*x2+y2*y2)*(y3-y1)+(x3*x3+y3*y3)*(y1-y2))/det,
            ((x1*x1+y1*y1)*(x3-x2)+(x2*x2+y2*y2)*(x1-x3)+(x3*x3+y3*y3)*(x2-x1))/det)


def sweep(sketch, source, path_sketch):
    """Rigid transport of the profile along tangent lines/arcs: cylinders and tori.

    Each line extrudes and each arc revolves, so a tangent path keeps analytic
    surfaces that later accept fillets. Real corners use a pipe shell with
    mitred transitions.
    """
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeRevol
    from OCP.gp import gp_Ax1, gp_Trsf
    from .kernel import sweep_frames, sweep_path
    sweep_frames(sketch, sweep_path(path_sketch))   # profile must cross the path start
    faces = _faces(sketch, source)
    basis = _frame(path_sketch)
    chain = _path_pieces(path_sketch)
    def tangent(pts, end):
        if len(pts) == 2:
            d = (pts[1][0]-pts[0][0], pts[1][1]-pts[0][1])
        else:
            # Arc through three points: tangent at an end is perpendicular to its radius.
            (x1, y1), (x2, y2), (x3, y3) = pts
            cx, cy = _circumcenter(pts)
            p = pts[-1] if end else pts[0]
            d = (-(p[1]-cy), p[0]-cx)
            cross = (x2-x1)*(y3-y1)-(y2-y1)*(x3-x1)
            if cross < 0: d = (-d[0], -d[1])
        n = math.hypot(*d)
        return (d[0]/n, d[1]/n)
    smooth = all(sum(a*b for a, b in zip(tangent(chain[i], True), tangent(chain[i+1], False))) > 1-1e-6
                 for i in range(len(chain)-1))
    if not smooth:
        return _pipe(faces, path_sketch, chain)
    section = list(faces); parts = []
    for pts in chain:
        a, b = _point(basis, *pts[0]), _point(basis, *pts[-1])
        if len(pts) == 2:
            vector = [b.X()-a.X(), b.Y()-a.Y(), b.Z()-a.Z()]
            parts.append(_prism(section, vector))
            section = [_translated(f, vector) for f in section]
            continue
        (x1, y1), (x2, y2), (x3, y3) = pts
        cx, cy = _circumcenter(pts)
        a1 = math.atan2(y1-cy, x1-cx); a3 = math.atan2(y3-cy, x3-cx)
        ccw = (x2-x1)*(y3-y1)-(y2-y1)*(x3-x1) > 0
        span = (a3-a1) % math.tau if ccw else (a1-a3) % math.tau
        normal = basis[3] if ccw else basis[3].Reversed()
        axis = gp_Ax1(_point(basis, cx, cy), normal)
        turned=[]
        for face in section:
            turn=BRepPrimAPI_MakeRevol(face,axis,span)
            if not turn.IsDone():
                raise CommandError('El perfil no cabe en el giro del recorrido',code='cad_profile_invalid')
            turned.append(turn.Shape())
        parts.append(_compound(turned) if len(turned)>1 else turned[0])
        trsf = gp_Trsf(); trsf.SetRotation(axis, span)
        section = [_transformed(f, trsf) for f in section]
    result = parts[0]
    for part in parts[1:]:
        result = _boolean('UNION', result, part)
    return _valid(_clean(result), 'cad_profile_invalid')


def _pipe(faces, path_sketch, chain):
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipeShell
    from OCP.BRepBuilderAPI import BRepBuilderAPI_TransitionMode
    from OCP.BRepTools import BRepTools
    basis = _frame(path_sketch)
    spine = _wire([('L' if len(p) == 2 else 'A',)+tuple(_point(basis, *q) for q in p) for p in chain])
    solids = []
    for face in faces:
        outer = BRepTools.OuterWire_s(face)
        pieces = []
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_WIRE
        from OCP.TopoDS import TopoDS
        explorer = TopExp_Explorer(face, TopAbs_WIRE)
        while explorer.More():
            wire = TopoDS.Wire(explorer.Current())
            shell = BRepOffsetAPI_MakePipeShell(spine)
            shell.SetTransitionMode(BRepBuilderAPI_TransitionMode.BRepBuilderAPI_RightCorner)
            shell.Add(wire, False, False)
            shell.Build()
            if not shell.IsDone() or not shell.MakeSolid():
                raise CommandError('El perfil es demasiado grande para la curvatura del recorrido', code='cad_profile_invalid')
            pieces.append((wire.IsSame(outer), shell.Shape()))
            explorer.Next()
        solid = next(s for outer_wire, s in pieces if outer_wire)
        for outer_wire, hole in pieces:
            if not outer_wire:
                solid = _boolean('CUT', solid, hole)
        solids.append(solid)
    result = solids[0]
    for solid in solids[1:]:
        result = _boolean('UNION', result, solid)
    return _valid(result, 'cad_profile_invalid')


def helix(sketch, source, axis, pitch, turns, hand='RIGHT'):
    """Exact thread: the contour follows a helix on a cylinder, its pose kept against the axis."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
    from OCP.BRepLib import BRepLib
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipeShell
    from OCP.Geom2d import Geom2d_Line, Geom2d_TrimmedCurve
    from OCP.Geom import Geom_CylindricalSurface
    from OCP.gp import gp_Ax3, gp_Dir, gp_Dir2d, gp_Pnt2d
    from .kernel import region
    if len(region(sketch, source)) != 1:
        raise CommandError('El barrido helicoidal usa un contorno sin huecos', code='cad_profile_invalid')
    ring = model.outline(source)
    ax1, (ax, ay), (dx, dy) = _axis(sketch, axis)
    heights = [(x-ax)*dx+(y-ay)*dy for x, y in ring]
    radial = [-(x-ax)*dy+(y-ay)*dx for x, y in ring]
    if min(radial) <= 1e-9 and max(radial) >= -1e-9:
        raise CommandError('El perfil toca o cruza el eje; sepáralo del eje para barrerlo', code='cad_profile_invalid')
    if pitch <= max(heights)-min(heights)+1e-9:
        raise CommandError('El paso debe superar la altura del perfil a lo largo del eje, o las vueltas se solapan', code='cad_profile_invalid')
    f = model.frame(sketch)
    side = 1. if radial[0] > 0 else -1.
    u = [(f['x'][i]*-dy+f['y'][i]*dx)*side for i in range(3)]
    radius = sum(abs(r) for r in radial)/len(radial)*MM
    start = sum(heights)/len(heights)*MM
    surface = Geom_CylindricalSurface(gp_Ax3(ax1.Location(), ax1.Direction(), gp_Dir(*u)), radius)
    turn = 1. if hand == 'RIGHT' else -1.
    du, dv = turn*math.tau*turns, pitch*MM*turns
    segment = Geom2d_TrimmedCurve(Geom2d_Line(gp_Pnt2d(0., start), gp_Dir2d(du, dv)), 0., math.hypot(du, dv))
    edge = BRepBuilderAPI_MakeEdge(segment, surface).Edge()
    BRepLib.BuildCurves3d_s(edge, 1e-6)
    shell = BRepOffsetAPI_MakePipeShell(BRepBuilderAPI_MakeWire(edge).Wire())
    shell.SetMode(ax1.Direction())   # binormal: the section keeps its pose against the axis
    shell.Add(_entity_wire(sketch, source), False, False)
    shell.Build()
    if not shell.IsDone() or not shell.MakeSolid():
        raise CommandError('El barrido helicoidal no encierra volumen', code='cad_profile_invalid')
    solid = shell.Shape()
    if _volume(solid) < 0:
        solid.Reverse()
    return _valid(solid, 'cad_profile_invalid')


# ------------------------------------------------------------ edge finishes

def _shell_faces(shape, references):
    """Match outward planar faces by an interior point and oriented normal."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.GeomAbs import GeomAbs_Plane
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED, TopAbs_IN, TopAbs_ON
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Pnt
    tolerance=max(_extent(shape)*2e-6,1e-5)
    candidates=[]
    explorer=TopExp_Explorer(shape,TopAbs_FACE)
    while explorer.More():
        face=TopoDS.Face(explorer.Current()); surface=BRepAdaptor_Surface(face)
        if surface.GetType()==GeomAbs_Plane:
            plane=surface.Plane(); normal=plane.Axis().Direction()
            sign=-1 if face.Orientation()==TopAbs_REVERSED else 1
            candidates.append((face,plane.Location(),[sign*normal.X(),sign*normal.Y(),sign*normal.Z()]))
        explorer.Next()
    selected=[]
    for ref in references:
        point=[v*MM for v in ref['origin']]
        matches=[]
        for face,origin,normal in candidates:
            if sum(a*b for a,b in zip(normal,ref['normal']))<=.9999: continue
            distance=sum((p-o)*n for p,o,n in zip(point,(origin.X(),origin.Y(),origin.Z()),normal))
            projected=gp_Pnt(*(p-distance*n for p,n in zip(point,normal)))
            if BRepClass_FaceClassifier(face,projected,tolerance).State() in (TopAbs_IN,TopAbs_ON):
                matches.append((abs(distance),face))
        exact=[face for distance,face in matches if distance<=tolerance]
        # A unique parallel face follows a changed extrusion height. Ambiguous
        # or removed faces fail rather than opening an arbitrary replacement.
        choices=exact if exact else [face for _,face in matches]
        if len(choices)!=1:
            raise CommandError('No se encuentra la cara de la carcasa; vuelve a seleccionarla',code='cad_reference_missing')
        if not any(choices[0].IsSame(face) for face in selected): selected.append(choices[0])
    return selected,tolerance


def shell(shape, faces, thickness, side):
    """Hollow the current exact solid, opening the captured planar faces."""
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeThickSolid
    from OCP.collections import List_TopoDS_Shape as TopTools_ListOfShape
    selected,tolerance=_shell_faces(shape,faces)
    removed=TopTools_ListOfShape()
    for face in selected: removed.Append(face)
    try:
        builder=BRepOffsetAPI_MakeThickSolid()
        builder.MakeThickSolidByJoin(shape,removed,(-1 if side=='INSIDE' else 1)*thickness*MM,tolerance)
        if not builder.IsDone(): raise ValueError('No thick solid')
        result=_valid(_clean(builder.Shape()),'cad_shell_invalid')
        if side=='INSIDE':
            # OCCT can return a valid but inverted offset after opposite walls
            # cross. Verify the actual cavity stays at least `thickness` away
            # from every retained original face, not merely BREP validity.
            from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
            from OCP.BRepExtrema import BRepExtrema_DistShapeShape
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_FACE
            cavity=_valid(BRepAlgoAPI_Cut(shape,result).Shape(),'cad_shell_invalid')
            original_volume=_volume(shape)
            if abs(_volume(result)+_volume(cavity)-original_volume)>max(original_volume*1e-6,1e-8):
                raise ValueError('Inward shell extends beyond the body')
            explorer=TopExp_Explorer(shape,TopAbs_FACE)
            while explorer.More():
                face=explorer.Current()
                if not any(face.IsSame(opening) for opening in selected):
                    distance=BRepExtrema_DistShapeShape(face,cavity)
                    if not distance.IsDone() or distance.Value()<thickness*MM-tolerance*5:
                        raise ValueError('Offset walls cross')
                explorer.Next()
        return result
    except Exception as exc:
        raise CommandError('La carcasa no cabe con ese grosor; redúcelo',code='cad_shell_invalid') from exc


def _match(shape, design_edges):
    """BREP edges that carry each stored design edge (segments in metres).

    A stored segment belongs to an edge when both ends lie on its curve. Lines
    compare against the infinite line and only need to overlap, so a straight
    edge survives a changed length.
    """
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_CurveType
    from OCP.ShapeAnalysis import ShapeAnalysis_Curve
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedMapOfShape
    from OCP.TopoDS import TopoDS
    from OCP.BRep import BRep_Tool
    from OCP.gp import gp_Pnt
    tol = max(_extent(shape)*2e-6, 1e-5)
    edges = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_EDGE, edges)
    candidates = []
    for i in range(1, edges.Extent()+1):
        edge = TopoDS.Edge(edges(i))
        if BRep_Tool.Degenerated_s(edge):
            continue
        candidates.append((edge, BRepAdaptor_Curve(edge)))
    analysis = ShapeAnalysis_Curve()
    def on(curve, p):
        kind = curve.GetType()
        if kind == GeomAbs_CurveType.GeomAbs_Line:
            return curve.Line().Distance(p) <= tol, curve.Line().Position().Direction()
        if kind == GeomAbs_CurveType.GeomAbs_Circle:
            c = curve.Circle(); axis = c.Axis()
            v = [p.X()-c.Location().X(), p.Y()-c.Location().Y(), p.Z()-c.Location().Z()]
            d = axis.Direction(); h = v[0]*d.X()+v[1]*d.Y()+v[2]*d.Z()
            radial = math.sqrt(max(sum(x*x for x in v)-h*h, 0.))
            return math.hypot(h, radial-c.Radius()) <= tol, None
        projection = gp_Pnt()
        distance = analysis.Project(curve, p, tol, projection, 0., True)
        return (distance[0] if isinstance(distance, tuple) else distance) <= tol, None
    chosen = []
    for design in design_edges:
        hit = False
        for edge, curve in candidates:
            for a, b in design:
                pa, pb = gp_Pnt(*(c*MM for c in a)), gp_Pnt(*(c*MM for c in b))
                ok_a, direction = on(curve, pa)
                if not ok_a or not on(curve, pb)[0]:
                    continue
                if direction is not None:
                    line = curve.Line(); o = line.Location()
                    t = lambda p: (p.X()-o.X())*direction.X()+(p.Y()-o.Y())*direction.Y()+(p.Z()-o.Z())*direction.Z()
                    lo, hi = sorted((t(pa), t(pb)))
                    first, last = sorted((curve.FirstParameter(), curve.LastParameter()))
                    if min(hi, last)-max(lo, first) <= tol:
                        continue
                if not any(edge.IsSame(e) for e in chosen):
                    chosen.append(edge)
                hit = True
                break
        if not hit:
            raise CommandError('Una arista del redondeo ya no existe; edita o borra la operación', code='cad_reference_missing')
    return chosen


def finish_edges(shape, edges, width, segments):
    from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet, BRepFilletAPI_MakeChamfer
    chosen = _match(shape, edges)
    maker = BRepFilletAPI_MakeFillet(shape) if segments > 1 else BRepFilletAPI_MakeChamfer(shape)
    for edge in chosen:
        maker.Add(width*MM, edge)
    try:
        maker.Build()
        ok = maker.IsDone()
        result = maker.Shape() if ok else None
    except Exception:
        ok, result = False, None
    if not ok:
        raise CommandError('El redondeo no cabe en esas aristas; reduce el ancho', code='cad_finish_invalid')
    return _valid(_clean(result), 'cad_finish_invalid')


# ------------------------------------------------------------- tessellation

def _planar_polygon(face, triangles):
    """Boundary loop of a planar face with a single wire, or None (curved/holed)."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_SurfaceType
    from OCP.TopAbs import TopAbs_WIRE
    from OCP.TopExp import TopExp_Explorer
    if len(triangles) < 2 or BRepAdaptor_Surface(face).GetType() != GeomAbs_SurfaceType.GeomAbs_Plane:
        return None
    wires = TopExp_Explorer(face, TopAbs_WIRE)
    wires.Next()
    if wires.More():
        return None
    directed = {(t[i], t[(i+1) % 3]) for t in triangles for i in range(3)}
    following = {a: b for a, b in directed if (b, a) not in directed}
    if not following:
        return None
    start = next(iter(following)); loop = [start]
    while True:
        nxt = following.get(loop[-1])
        if nxt is None or len(loop) > len(following):
            return None
        if nxt == start:
            break
        loop.append(nxt)
    return tuple(loop) if len(loop) == len(following) and len(loop) >= 3 else None


def tessellate(shape):
    """Compact triangle mesh in metres; nodes shared along BREP edges are welded."""
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS
    extent = _extent(shape)
    # 0.1 rad keeps a circle sagitta at 1.25e-3 of its radius, inside the 2.2e-3
    # that analytic cylinder labels accept for the displayed surface.
    BRepMesh_IncrementalMesh(shape, max(extent*3e-4, 1e-4), False, .1, True)
    vertices, faces, index = [], [], {}
    key = lambda p: (round(p.X(), 6), round(p.Y(), 6), round(p.Z(), 6))
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face(explorer.Current())
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)
        explorer.Next()
        if triangulation is None:
            continue
        trsf = location.Transformation()
        ids = [None]
        for i in range(1, triangulation.NbNodes()+1):
            p = triangulation.Node(i).Transformed(trsf)
            k = key(p)
            if k not in index:
                index[k] = len(vertices)
                vertices.append((p.X()/MM, p.Y()/MM, p.Z()/MM))
            ids.append(index[k])
        reverse = face.Orientation() == TopAbs_REVERSED
        triangles = []
        for i in range(1, triangulation.NbTriangles()+1):
            t = triangulation.Triangle(i)
            tri = (ids[t.Value(1)], ids[t.Value(2)], ids[t.Value(3)])
            if len(set(tri)) == 3:
                triangles.append(tuple(reversed(tri)) if reverse else tri)
        polygon = _planar_polygon(face, triangles)
        faces.extend([polygon] if polygon else triangles)
    if not faces:
        raise CommandError('La operación produce un sólido vacío o geometría inválida', code='cad_profile_invalid')
    return vertices, faces


# --------------------------------------------------------------- evaluator

class Evaluator:
    """Same history semantics and result contract as evaluation.Evaluator."""

    def __init__(self):
        self._shapes = {}
        self._meshes = {}
        self._body_meshes = {}

    def evaluate(self, doc, *, limit=None, scale=1.):
        model.resolve_supports(doc)
        sequence = model.history(doc)
        if limit:
            end = next((i for i, node in enumerate(sequence) if node['id'] == limit), None)
            if end is not None:
                sequence = sequence[:end+1]
        tips, shapes, keys = {}, {}, {}
        def store(identifier, signature, build):
            text = model.dumps(signature)
            cached = self._shapes.get(identifier)
            if cached is None or cached[0] != text:
                cached = (text, build())
                self._shapes[identifier] = cached
            shapes[identifier] = cached[1]
            keys[identifier] = hashlib.blake2b(text.encode(), digest_size=16).hexdigest()
        def sketch_key(*items):
            return model.dumps([dict(frame=model.frame(s), entities=s['entities']) for s in items])
        for feature in sequence:
            if feature['kind'] != 'FEATURE' or not mirror.active(doc, feature):
                continue
            feature=model.find(doc,'features',feature['id'])
            identifier = feature['id']; body = feature['body_id']
            previous = tips.get(body)
            base = shapes.get(previous)
            def joined(build, base=base):
                return lambda: _boolean('UNION', base, build()) if base is not None else _valid(build(), 'cad_profile_invalid')
            kind = feature['type']
            if kind == 'PATTERN':
                if base is None:raise CommandError('El patrón necesita un cuerpo anterior',code='cad_dependency')
                store(identifier,('PATTERN',model.dumps(feature),keys.get(previous),[keys.get(i) for i in feature['source_ids']]),
                      lambda: patterned(doc,feature,base))
            elif kind == 'HOLE':
                sketch=model.find(doc,'sketches',feature['sketch_id'])
                if base is None: raise CommandError('El cuerpo no tiene sólido para taladrar',code='cad_dependency')
                store(identifier,('HOLE',model.dumps(feature),sketch_key(sketch),keys.get(previous)),
                      lambda: _boolean('CUT',base,hole_operand(sketch,feature,base)))
            elif kind == 'SHELL':
                if base is None:
                    raise CommandError('El cuerpo no tiene un sólido para crear la carcasa',code='cad_dependency')
                store(identifier,('OCCT',kind,model.dumps(feature['faces']),feature['thickness'],feature['side'],keys.get(previous)),
                      lambda: shell(base,feature['faces'],feature['thickness'],feature['side']))
            elif kind in model.FINISHES:
                if previous is None:
                    raise CommandError('El cuerpo no tiene un sólido que redondear', code='cad_dependency')
                store(identifier, ('OCCT', kind, feature['width'], feature.get('segments', 1),
                                   model.dumps(feature['edges']), keys.get(previous)),
                      lambda: finish_edges(base, feature['edges'], feature['width'], feature.get('segments', 1)))
            elif kind == 'HELIX':
                sketch, source = model.profile(doc, feature['profile_id'])
                store(identifier, ('OCCT', kind, feature['profile_id'], feature['axis'], feature['pitch'],
                                   feature['turns'], feature['hand'], sketch_key(sketch), keys.get(previous)),
                      joined(lambda: helix(sketch, source, feature['axis'], feature['pitch'],
                                           feature['turns'], feature['hand'])))
            elif kind == 'REVOLVE':
                sketch, source = model.profile(doc, feature['profile_id'])
                store(identifier, ('OCCT', kind, feature['profile_id'], feature['axis'], feature['angle'],
                                   sketch_key(sketch), keys.get(previous)),
                      joined(lambda: revolve(sketch, source, feature['axis'], feature['angle'])))
            elif kind == 'SWEEP':
                sketch, source = model.profile(doc, feature['profile_id'])
                path = model.find(doc, 'sketches', feature['path_sketch_id'])
                store(identifier, ('OCCT', kind, feature['profile_id'], sketch_key(sketch, path), keys.get(previous)),
                      joined(lambda: sweep(sketch, source, path)))
            elif kind == 'LOFT':
                first, source = model.profile(doc, feature['profile_id'])
                second, target = model.profile(doc, feature['to_profile_id'])
                store(identifier, ('OCCT', kind, feature['profile_id'], feature['to_profile_id'],
                                   sketch_key(first, second), keys.get(previous)),
                      joined(lambda: loft(first, source, second, target)))
            else:
                sketch, entity = model.profile(doc, feature['profile_id'])
                cut = feature.get('operation', kind) == 'CUT'
                depth = model.number(feature['depth'], positive=cut)
                if cut and feature.get('target_id') not in shapes:
                    raise CommandError('Activa el sólido destino antes del vaciado', code='cad_dependency')
                if cut and base is None:
                    raise CommandError('El cuerpo no tiene un sólido para vaciar', code='cad_dependency')
                def tool(sketch=sketch, entity=entity, feature=feature):
                    shape = operand(sketch, entity, feature, base)
                    return _mirrored(shape, feature['mirror']) if feature.get('mirror') else shape
                store(identifier, ('OCCT', feature['profile_id'], kind, depth, feature.get('extent', 'ONE'),
                                   feature.get('to_face'), sketch_key(sketch), keys.get(previous), feature.get('mirror')),
                      (lambda: _boolean('CUT', base, tool())) if cut else joined(tool))
            tips[body] = identifier
        solids = {}
        for identifier, shape in shapes.items():
            cached = self._meshes.get(identifier)
            if cached is None or cached[0] != keys[identifier]:
                cached = (keys[identifier], tessellate(shape))
                self._meshes[identifier] = cached
            solids[identifier] = (self._shapes[identifier][0], cached[1])
        display = {}
        for body, identifier in tips.items():
            signature = model.dumps((keys[identifier], scale))
            cached = self._body_meshes.get(body)
            if cached is None or cached[0] != signature:
                vertices, faces = solids[identifier][1]
                cached = (signature, ([tuple(c/scale for c in v) for v in vertices], faces))
                self._body_meshes[body] = cached
            display[body] = cached
        feature_ids = {f['id'] for f in doc['features']}
        self._shapes = {k: v for k, v in self._shapes.items() if k in feature_ids}
        self._meshes = {k: v for k, v in self._meshes.items() if k in feature_ids}
        self._body_meshes = {k: v for k, v in self._body_meshes.items() if k in tips}
        return dict(display=display, tips=tips, solids=solids, profiles={})


evaluator = Evaluator()
