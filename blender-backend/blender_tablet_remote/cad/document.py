"""Versioned CAD source model. SI metres; no bpy or mesh indices."""
import copy
import json
import math
import uuid
from ..errors import BadPayload, CommandError

VERSION = 1
KEY = 'btr_cad_document'
PLANES = ('XY', 'XZ', 'YZ')
TYPES = ('LINE', 'RECTANGLE', 'CIRCLE', 'ARC', 'NGON', 'SLOT', 'GEAR')
# NGON is a regular polygon: its across-flats size (inscribed diameter, the
# wrench size of a nut) and the rotation of its first vertex are solver
# parameters; `sides` is a discrete property, never solved.
FIELDS = {'LINE': ('x','y','x2','y2'), 'RECTANGLE': ('x','y','width','height'),
          'CIRCLE': ('x','y','diameter'), 'ARC': ('x','y','radius','start','sweep'),
          'NGON': ('x','y','flats','angle'),
          'SLOT': ('x','y','length','width','angle'), 'GEAR': ('x','y','module','angle')}
# SLOT is a straight slot: two semicircles of diameter `width` whose centers lie
# `length` apart, joined by two tangent lines; (x,y) is its middle point.
# GEAR is an involute spur gear: `module` is its size (pitch diameter = module ×
# teeth); `teeth` and the pressure angle are discrete properties, never solved.
ANGULAR = ('start','sweep','angle')  # degrees, independent of the sketch size
# Edge finishes act on a body's solid: no sketch or profile, only design edges
# stored as their segments in metres (never mesh indices). Chamfer is one segment.
FINISHES = ('FILLET', 'CHAMFER')
HANDS = ('RIGHT', 'LEFT')


def validate_helix(feature):
    """Helical sweep: `pitch` metres per turn, `turns`, hand and an in-sketch axis."""
    feature['pitch'] = number(feature.get('pitch'), positive=True)
    feature['turns'] = number(feature.get('turns'), positive=True)
    if feature['turns'] > 200:
        raise BadPayload('El barrido helicoidal admite hasta 200 vueltas')
    if feature.setdefault('hand', 'RIGHT') not in HANDS:
        raise BadPayload('Sentido: RIGHT o LEFT')
    axis = feature.setdefault('axis', 'Y')
    if not isinstance(axis, str) or not axis:
        raise BadPayload('Eje no válido')
    return feature


def validate_finish(feature):
    edges = feature.get('edges')
    if not isinstance(edges, list) or not edges or len(edges) > 200:
        raise BadPayload('Selecciona las aristas del sólido')
    for edge in edges:
        if not isinstance(edge, list) or not edge or len(edge) > 2000:
            raise BadPayload('Arista del sólido no válida')
        for segment in edge:
            if not isinstance(segment, list) or len(segment) != 2: raise BadPayload('Arista del sólido no válida')
            for p in segment:
                if not isinstance(p, list) or len(p) != 3: raise BadPayload('Arista del sólido no válida')
                for c in p: number(c)
    feature['width'] = number(feature.get('width'), positive=True)
    segments = feature.get('segments', 1)
    if isinstance(segments, bool) or not isinstance(segments, int) or not 1 <= segments <= 16:
        raise BadPayload('Los segmentos del redondeo van de 1 a 16')
    if feature['type'] == 'CHAMFER' and segments != 1:
        raise BadPayload('El chaflán es un único segmento')
    return feature
SIDES = (3, 32)
TEETH = (6, 150)
PRESSURE_ANGLES = (14.5, 20., 25.)


def circumradius(e):
    return e['flats']/2/math.cos(math.pi/e['sides'])


def gear_radii(e):
    """Pitch, base, tip and root radii of a standard (1 m addendum, 1.25 m dedendum) gear."""
    pitch = e['module']*e['teeth']/2
    return pitch, pitch*math.cos(math.radians(e.get('pressure', 20.))), pitch+e['module'], pitch-1.25*e['module']


def _gear_outline(e):
    x, y, z = e['x'], e['y'], e['teeth']
    pitch, base, tip, root = gear_radii(e)
    involute = lambda r: math.tan(math.acos(min(1., base/r)))-math.acos(min(1., base/r))
    half_base = math.pi/(2*z)+involute(pitch)          # half tooth angle on the base circle
    start = max(base, root)
    samples = 6 if z <= 60 else 4
    flank = [start+(tip-start)*i/(samples-1) for i in range(samples)]
    ring = []
    def add(r, a): ring.append((x+r*math.cos(a), y+r*math.sin(a)))
    for k in range(z):
        c = math.radians(e['angle'])+k*math.tau/z
        if root < base: add(root, c-half_base)
        for r in flank: add(r, c-half_base+involute(r))
        for r in reversed(flank): add(r, c+half_base-involute(r))
        if root < base: add(root, c+half_base)
        gap_start, gap_end = c+half_base-involute(start), c+math.tau/z-half_base+involute(start)
        for i in (1, 2): add(root, gap_start+(gap_end-gap_start)*i/3)
    return ring


def uid(prefix):
    return prefix + '_' + uuid.uuid4().hex


def new_document():
    return dict(version=VERSION, revision=0, id=uid('doc'), sketches=[], features=[], planes=[], bodies=[dict(id=uid('body'),name='Cuerpo 1')])


def loads(raw):
    if not raw:
        return new_document()
    try:
        doc = json.loads(raw)
        if not isinstance(doc, dict) or doc.get('version') != VERSION:
            raise ValueError('unsupported version')
        if not isinstance(doc.get('sketches'), list) or not isinstance(doc.get('features'), list):
            raise ValueError('missing collections')
        if not isinstance(doc.get('id'),str) or not doc['id']:
            raise ValueError('invalid document ID')
        doc.setdefault('planes',[])
        doc.setdefault('bodies',[dict(id='body_'+doc['id'],name='Cuerpo 1')])
        if not isinstance(doc['planes'],list) or not isinstance(doc['bodies'],list) or not doc['bodies']: raise ValueError('invalid bodies/planes')
        ids = {doc['id']}
        if not isinstance(doc.get('revision', 0), int) or doc.get('revision', 0) < 0:
            raise ValueError('invalid revision')
        def unique(value):
            if not isinstance(value, str) or not value or value in ids:
                raise ValueError('duplicate or missing ID')
            ids.add(value)
        for body in doc['bodies']:
            unique(body['id'])
            if not isinstance(body.get('name'),str): raise ValueError('invalid body name')
        for plane in doc['planes']:
            unique(plane['id'])
            validate_plane(plane)
        for sketch in doc['sketches']:
            unique(sketch['id'])
            sketch.setdefault('body_id',doc['bodies'][0]['id'])
            find(doc,'bodies',sketch['body_id'])
            if not isinstance(sketch.get('visible',True),bool): raise ValueError('invalid visibility')
            if not isinstance(sketch.get('name'),str):
                raise ValueError('invalid sketch name')
            if sketch['plane'] not in PLANES:
                raise ValueError('invalid plane')
            number(sketch.get('offset', 0))
            for e in sketch['entities']:
                unique(e['id'])
                validate_entity(e)
            from .sketch import validate_constraints
            validate_constraints(sketch)
        seen_features = set()
        for feature in doc['features']:
            unique(feature['id'])
            if not isinstance(feature.get('name'),str):
                raise ValueError('invalid feature name')
            if feature.get('type') in FINISHES:
                find(doc,'bodies',feature['body_id'])
                if not isinstance(feature.get('enabled'),bool) or feature.get('sketch_id') is not None:
                    raise ValueError('invalid feature')
                validate_finish(feature)
                seen_features.add(feature['id'])
                continue
            if feature.get('type') == 'LOFT':
                first, _ = profile(doc, feature['profile_id'])
                second, _ = profile(doc, feature.get('to_profile_id'))
                feature.setdefault('body_id', first['body_id'])
                find(doc,'bodies',feature['body_id'])
                if first['id'] != feature['sketch_id'] or second['id'] != feature.get('to_sketch_id') or \
                        first['id'] == second['id'] or not isinstance(feature['enabled'], bool):
                    raise ValueError('invalid loft')
                seen_features.add(feature['id'])
                continue
            if feature.get('type') == 'HELIX':
                sketch, _ = profile(doc, feature['profile_id'])
                feature.setdefault('body_id', sketch['body_id'])
                find(doc,'bodies',feature['body_id'])
                if sketch['id'] != feature['sketch_id'] or not isinstance(feature['enabled'], bool):
                    raise ValueError('invalid helix')
                validate_helix(feature)
                seen_features.add(feature['id'])
                continue
            sketch, _ = profile(doc, feature['profile_id'])
            feature.setdefault('body_id',sketch['body_id'])
            find(doc,'bodies',feature['body_id'])
            if feature['type'] not in ('EXTRUDE', 'CUT') or sketch['id'] != feature['sketch_id'] or not isinstance(feature['enabled'], bool):
                raise ValueError('invalid feature')
            depth = number(feature['depth'])
            if feature['type'] == 'CUT':
                if depth < 1e-7:
                    raise ValueError('invalid feature')
            elif abs(depth) < 1e-7:
                raise ValueError('invalid feature')
            feature['depth'] = depth
            feature.setdefault('extent', 'ONE')
            if feature['extent'] not in ('ONE', 'BOTH'):
                raise ValueError('invalid feature extent')
            if feature['type'] == 'CUT' and feature.get('target_id') not in seen_features:
                raise ValueError('invalid cut dependency')
            seen_features.add(feature['id'])
        for index,node in enumerate(history(doc),1):
            find(doc,'sketches' if node['kind']=='SKETCH' else 'features',node['id']).setdefault('order',index)
        resolve_supports(doc)
        return doc
    except (ValueError, TypeError, KeyError, CommandError) as exc:
        raise CommandError('Documento CAD ilegible o versión no compatible', code='cad_document_invalid') from exc


def dumps(doc):
    return json.dumps(doc, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def number(value, *, positive=False):
    if isinstance(value, bool):
        raise BadPayload('La medida debe ser numérica, no booleana')
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise BadPayload('La medida debe ser un número finito') from exc
    if not math.isfinite(value) or abs(value) > 10000 or (positive and value < 1e-7):
        raise BadPayload('Medida fuera de rango (mínimo 0.0001 mm, máximo 10000 m)')
    return value


def find(doc, collection, identifier):
    for item in doc[collection]:
        if item['id'] == identifier:
            return item
    raise CommandError('Referencia CAD inexistente', code='cad_reference_missing')


def entity(doc, identifier):
    for sketch in doc['sketches']:
        for item in sketch['entities']:
            if item['id'] == identifier:
                return sketch, item
    raise CommandError('Entidad CAD inexistente', code='cad_reference_missing')


def closed_entities(sketch):
    """Analytic primitives plus unbranched closed chains of lines/arcs.

    A chain profile identity derives from its member IDs, never mesh topology.
    """
    import hashlib
    result = [e for e in sketch['entities'] if not e.get('construction',False) and e['type'] in ('RECTANGLE', 'CIRCLE', 'NGON', 'SLOT', 'GEAR')]
    edges = [e for e in sketch['entities'] if not e.get('construction',False) and e['type'] in ('LINE', 'ARC')]
    remaining = {e['id']: e for e in edges}
    def near(a, b):
        return math.dist(a,b) < 1e-7
    while remaining:
        first = remaining.pop(next(iter(remaining)))
        points, members = outline(first), [first['id']]
        while not near(points[0], points[-1]):
            matches = [(e, reverse) for e in remaining.values() for reverse in (False, True)
                       if near(points[-1], outline(e)[-1 if reverse else 0])]
            if len(matches) != 1:
                break
            e, reverse = matches[0]
            remaining.pop(e['id'])
            path = outline(e)
            points.extend((list(reversed(path)) if reverse else path)[1:])
            members.append(e['id'])
        if len(points) > 3 and near(points[0], points[-1]):
            points.pop()
            area = sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(points,points[1:]+points[:1]))
            if area < 0:
                points.reverse()
            identifier = 'chain_' + hashlib.sha256('|'.join(sorted(members)).encode()).hexdigest()[:24]
            result.append(dict(id=identifier,type='POLYGON',points=points,members=members))
    return result


def profile(doc, identifier):
    for sketch in doc['sketches']:
        if identifier == 'profile_' + sketch['id']:
            closed = closed_entities(sketch)
            covered = {member for item in closed for member in item.get('members', [item['id']])}
            if not closed or any(e['id'] not in covered for e in sketch['entities'] if not e.get('construction', False)):
                raise CommandError('El croquis contiene geometría abierta: ciérrala o márcala como construcción antes de extruirlo completo', code='cad_profile_invalid')
            return sketch, dict(id=sketch['id'], type='SKETCH')
        for item in closed_entities(sketch):
            if 'profile_' + item['id'] == identifier:
                return sketch, item
    raise CommandError('El perfil está abierto o ya no existe', code='cad_profile_invalid')


def profiles(sketch):
    return [dict(id='profile_' + e['id'], entity_id=e['id'],
                 label={'RECTANGLE':'Rectángulo','CIRCLE':'Círculo','NGON':'Polígono regular','SLOT':'Ranura','GEAR':'Engranaje','POLYGON':'Contorno cerrado'}[e['type']])
            for e in closed_entities(sketch)]


def outline(e):
    if e['type'] == 'POLYGON':
        return e['points']
    x, y = e['x'], e['y']
    if e['type'] == 'ARC':
        count = max(8, int(abs(e['sweep']) / 3))
        return [(x + e['radius']*math.cos(math.radians(e['start']+e['sweep']*i/count)),
                 y + e['radius']*math.sin(math.radians(e['start']+e['sweep']*i/count))) for i in range(count+1)]
    if e['type'] == 'LINE':
        return [(x, y), (e['x2'], e['y2'])]
    if e['type'] == 'NGON':
        r = circumradius(e)
        return [(x + r*math.cos(math.radians(e['angle'])+i*math.tau/e['sides']),
                 y + r*math.sin(math.radians(e['angle'])+i*math.tau/e['sides'])) for i in range(e['sides'])]
    if e['type'] == 'SLOT':
        a, half, r = math.radians(e['angle']), e['length']/2, e['width']/2
        ring = []
        for sign, turn in ((1, -math.pi/2), (-1, math.pi/2)):   # end cap, then start cap
            cx, cy = x+sign*half*math.cos(a), y+sign*half*math.sin(a)
            ring.extend((cx+r*math.cos(a+turn+math.pi*i/24), cy+r*math.sin(a+turn+math.pi*i/24)) for i in range(25))
        return ring
    if e['type'] == 'GEAR':
        return _gear_outline(e)
    if e['type'] == 'RECTANGLE':
        w, h = e['width'], e['height']
        return [(x, y), (x+w, y), (x+w, y+h), (x, y+h)]
    r = e['diameter'] / 2
    return [(x + r*math.cos(i*math.tau/128), y + r*math.sin(i*math.tau/128)) for i in range(128)]


def contains(ring, point):
    x, y = point
    inside = False
    for a, b in zip(ring, ring[1:] + ring[:1]):
        if (a[1] > y) != (b[1] > y) and x < (b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:
            inside = not inside
    return inside


def validate_entity(e):
    if not isinstance(e.get('construction',False),bool): raise BadPayload('construction debe ser booleano')
    if e.get('type') not in TYPES:
        raise BadPayload('Tipo de entidad CAD no compatible')
    for key in FIELDS[e['type']]:
        e[key] = number(e.get(key), positive=key in ('width','height','diameter','radius','flats','length','module'))
    if e['type'] == 'ARC' and not .01 <= abs(e['sweep']) < 360:
        raise BadPayload('El arco necesita un barrido entre 0.01° y menos de 360°')
    if e['type'] == 'LINE' and math.hypot(e['x2']-e['x'], e['y2']-e['y']) < 1e-7:
        raise BadPayload('La línea necesita dos puntos distintos')
    if e['type'] == 'NGON':
        sides = e.get('sides')
        if isinstance(sides, bool) or not isinstance(sides, int) or not SIDES[0] <= sides <= SIDES[1]:
            raise BadPayload(f'El polígono regular necesita entre {SIDES[0]} y {SIDES[1]} lados')
    if e['type'] == 'GEAR':
        teeth = e.get('teeth')
        if isinstance(teeth, bool) or not isinstance(teeth, int) or not TEETH[0] <= teeth <= TEETH[1]:
            raise BadPayload(f'El engranaje necesita entre {TEETH[0]} y {TEETH[1]} dientes')
        if e.setdefault('pressure', 20.) not in PRESSURE_ANGLES:
            raise BadPayload('Ángulo de presión admitido: 14,5°, 20° o 25°')
    return e


def base_frame(plane='XY', offset=0):
    x,y,n={'XY':([1,0,0],[0,1,0],[0,0,1]), 'XZ':([1,0,0],[0,0,1],[0,-1,0]),
           'YZ':([0,1,0],[0,0,1],[1,0,0])}[plane]
    return dict(origin=[v*offset for v in n],x=x,y=y,normal=n)


def frame(sketch):
    if sketch.get('plane_id') or sketch.get('support_id'): return sketch['frame']
    return base_frame(sketch['plane'],sketch.get('offset',0))


def validate_plane(plane):
    if not isinstance(plane.get('name'),str) or plane.get('base','XY') not in PLANES:
        raise BadPayload('Plano no válido')
    for key in ('translation','rotation'):
        values=plane.get(key,[0,0,0])
        if not isinstance(values,list) or len(values)!=3: raise BadPayload('El plano requiere tres coordenadas y tres ángulos')
        for v in values: number(v)
    if 'face_frame' in plane:
        import numpy as np
        f=plane['face_frame']
        for key in ('origin','x','y','normal'):
            if not isinstance(f.get(key),list) or len(f[key])!=3: raise BadPayload('Referencia de cara inválida')
            for v in f[key]: number(v)
        basis=np.array([f['x'],f['y'],f['normal']])
        if not np.allclose(basis@basis.T,np.eye(3),atol=1e-5) or np.linalg.det(basis)<.999:
            raise BadPayload('La referencia debe ser ortonormal')


def resolve_supports(doc):
    """Resolve datum planes and associative top faces without evaluated mesh IDs."""
    import numpy as np
    visiting=set(); resolved=set()
    def enter(item):
        if item['id'] in visiting: raise BadPayload('Dependencia circular entre planos y bocetos')
        visiting.add(item['id'])
    def finish(item):
        visiting.remove(item['id']); resolved.add(item['id'])
    def supported(feature_id):
        f=find(doc,'features',feature_id)
        if f['type'] in FINISHES + ('LOFT','HELIX'):
            raise BadPayload('Un redondeo o solevado no sirve de apoyo; usa Boceto en cara sobre la cara que quieras')
        source=find(doc,'sketches',f['sketch_id']); resolve(source)
        result=copy.deepcopy(frame(source))
        depth=f['depth'] if f['type']=='EXTRUDE' else 0
        result['origin']=[v+n*depth for v,n in zip(result['origin'],result['normal'])]
        return result,source
    def resolve_plane(plane):
        if plane['id'] in resolved: return
        enter(plane); validate_plane(plane)
        if plane.get('reference_sketch_id'):
            source=find(doc,'sketches',plane['reference_sketch_id']); resolve(source); base=frame(source)
        elif plane.get('support_id'): base,_=supported(plane['support_id'])
        else: base=plane.get('face_frame') or base_frame(plane.get('base','XY'))
        basis=np.array([base['x'],base['y'],base['normal']],dtype=float).T
        origin=np.array(base['origin'])+basis@np.array(plane.get('translation',[0,0,0]))
        rx,ry,rz=map(math.radians,plane.get('rotation',[0,0,0]))
        cx,sx,cy,sy,cz,sz=math.cos(rx),math.sin(rx),math.cos(ry),math.sin(ry),math.cos(rz),math.sin(rz)
        rot=np.array([[cz,-sz,0],[sz,cz,0],[0,0,1]])@np.array([[cy,0,sy],[0,1,0],[-sy,0,cy]])@np.array([[1,0,0],[0,cx,-sx],[0,sx,cx]])
        basis=basis@rot
        plane['frame']=dict(origin=origin.tolist(),x=basis[:,0].tolist(),y=basis[:,1].tolist(),normal=basis[:,2].tolist())
        finish(plane)
    def resolve(sketch):
        if sketch['id'] in resolved: return
        enter(sketch)
        if sketch.get('plane_id'):
            plane=find(doc,'planes',sketch['plane_id']); resolve_plane(plane)
            sketch['frame']=copy.deepcopy(plane['frame'])
        elif sketch.get('support_id'):
            supported_frame,source=supported(sketch['support_id'])
            feature=find(doc,'features',sketch['support_id'])
            sketch['plane']=source['plane']
            sketch['offset']=source.get('offset',0)+(feature['depth'] if feature['type']=='EXTRUDE' else 0)
            sketch['frame']=supported_frame
        else: sketch['frame']=base_frame(sketch['plane'],sketch.get('offset',0))
        finish(sketch)
    for plane in doc.get('planes',[]): resolve_plane(plane)
    for sketch in doc['sketches']: resolve(sketch)


def sketch_visible(doc, sketch):
    return bool(sketch.get('visible',True) and (sketch.get('visibility_explicit',False) or
        not any(sketch['id'] in (f['sketch_id'],f.get('to_sketch_id')) and f['enabled'] for f in doc['features'])))


def history(doc):
    nodes=[]; seen=set()
    # Older documents had no order. Preserve feature order and place each source
    # sketch immediately before its first operation; unused sketches follow.
    for feature in doc['features']:
        if feature.get('sketch_id') is None:
            nodes.append(dict(feature,kind='FEATURE')); continue
        sketch=find(doc,'sketches',feature['sketch_id'])
        if sketch['id'] not in seen:
            nodes.append(dict(sketch,kind='SKETCH')); seen.add(sketch['id'])
        nodes.append(dict(feature,kind='FEATURE'))
    nodes.extend(dict(s,kind='SKETCH') for s in doc['sketches'] if s['id'] not in seen)
    order={node['id']:node.get('order',index) for index,node in enumerate(nodes,1)}
    return sorted(nodes,key=lambda node:order[node['id']])


def next_order(doc):
    return max([n.get('order',i) for i,n in enumerate(history(doc),1)]+[0])+1


def insert_after(doc, item, after_id):
    """Renumber every node so `item` follows `after_id`; None appends at the end.

    The rollback bar inserts new nodes at the viewed position instead of the end.
    """
    sequence = [n['id'] for n in history(doc)]
    if item['id'] in sequence:
        sequence.remove(item['id'])
    sequence.insert(sequence.index(after_id)+1 if after_id in sequence else len(sequence), item['id'])
    placed = dict(zip(sequence, range(1, len(sequence)+1)))
    for kind in ('sketches', 'features'):
        for node in doc[kind]:
            if node['id'] in placed:
                node['order'] = placed[node['id']]


def public(doc):
    result = copy.deepcopy(doc)
    result['history']=[{k:n[k] for k in ('id','kind','name','body_id','sketch_id') if k in n} for n in history(doc)]
    for sketch in result['sketches']:
        sketch['visible']=sketch_visible(doc,sketch)
        sketch['profiles'] = profiles(sketch)
        from . import dimensions, sketch as geometry
        sketch['constraints']=dimensions.visible_constraints(sketch)
        for e in sketch['entities']:
            if e['type']=='CIRCLE': e['radius']=e['diameter']/2
            e['dimensions']=dimensions.describe(sketch,e)
            e['is_square']=dimensions.is_square(sketch,e)
            e['is_fillet']=geometry.fillet_sides(sketch,e) is not None
            if e['type']=='LINE': e['length']=math.dist(*geometry.measure_line(sketch,dict(id=e['id'],part='BODY')))
        sketch['plane_label'] = find(result,'planes',sketch['plane_id'])['name'] if sketch.get('plane_id') else sketch['plane']
    return result
