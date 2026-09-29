"""Sketch handles and a bounded numerical constraint solver, in metres.

NumPy ships with Blender. Residuals validate the supported constraint system;
incompatible edits fail atomically instead of silently dropping rules.
"""
import copy
import math
import numpy as np
from . import document as model
from ..errors import BadPayload, CommandError

CONSTRAINTS = ('COINCIDENT', 'POINT_ON_LINE', 'HORIZONTAL', 'VERTICAL', 'PARALLEL', 'COLLINEAR', 'PERPENDICULAR',
               'TANGENT', 'EQUAL', 'DISTANCE', 'DISTANCE_X', 'DISTANCE_Y', 'RADIUS', 'FIX', 'MIDPOINT',
               'SYMMETRIC', 'SYMMETRIC_LINE', 'OFFSET')


def handles(e):
    typ = e['type']
    if typ in ('ORIGIN', 'POINT'): return {'POINT': (e.get('x',0.), e.get('y',0.))}
    if typ == 'LINE':
        return {'START': (e['x'],e['y']), 'END': (e['x2'],e['y2'])}
    if typ in ('RECTANGLE', 'NGON'):
        corners = {'P'+str(i): p for i, p in enumerate(model.outline(e))}
        return {'CENTER': (e['x'], e['y']), **corners} if typ == 'NGON' else corners
    if typ == 'SLOT':
        # SIDE sits on one straight side: dragging it widens or narrows the slot.
        a=math.radians(e['angle']); half=e['width']/2
        return {'CENTER': (e['x'],e['y']), **dict(zip(('START','END'),slot_centers(e))),
                'SIDE': (e['x']-math.sin(a)*half,e['y']+math.cos(a)*half)}
    if typ == 'GEAR':
        return {'CENTER': (e['x'],e['y'])}
    if typ == 'ARC':
        path = model.outline(e)
        return {'CENTER': (e['x'],e['y']), 'START': path[0], 'END': path[-1]}
    return {'CENTER': (e['x'],e['y']), 'RIM': (e['x']+e['diameter']/2,e['y'])}


def slot_centers(e):
    dx,dy=math.cos(math.radians(e['angle']))*e['length']/2,math.sin(math.radians(e['angle']))*e['length']/2
    return (e['x']-dx,e['y']-dy),(e['x']+dx,e['y']+dy)


def get_entity(sketch, ref):
    if ref.get('id') == 'ORIGIN': return dict(id='ORIGIN', type='ORIGIN', x=0., y=0.)
    return model.find(sketch, 'entities', ref.get('id'))


def point(sketch, ref):
    e = get_entity(sketch, ref)
    role = ref.get('part')
    if role not in handles(e):
        raise BadPayload('Selecciona un punto del boceto')
    return np.array(handles(e)[role], dtype=float)


def line(sketch, ref):
    e = get_entity(sketch, ref)
    if e['type'] in ('RECTANGLE', 'NGON') and str(ref.get('part','')).startswith('EDGE'):
        ring = model.outline(e)
        i = int(ref['part'][4:])
        if i not in range(len(ring)):
            raise BadPayload('Arista inexistente')
        return np.array(ring[i]), np.array(ring[(i+1)%len(ring)])
    if e['type'] == 'SLOT' and ref.get('part') == 'AXIS':
        return tuple(np.array(p) for p in slot_centers(e))
    if e['type'] != 'LINE':
        raise BadPayload('Selecciona líneas o lados rectos')
    return np.array((e['x'],e['y'])), np.array((e['x2'],e['y2']))


def point_line_refs(sketch, refs):
    """Canonical point/straight-edge pair, independent of touch order."""
    if len(refs) != 2 or refs[0]['id'] == refs[1]['id']:
        raise BadPayload('Selecciona un punto y una recta de otra figura')
    for point_ref, line_ref in (refs, refs[::-1]):
        p = get_entity(sketch, point_ref)
        e = get_entity(sketch, line_ref)
        part = line_ref.get('part', 'BODY')
        straight = ((e['type'] == 'LINE' and part == 'BODY') or
                    (e['type'] in ('RECTANGLE', 'NGON') and part.startswith('EDGE') and part[4:].isdigit()) or
                    (e['type'] == 'SLOT' and part == 'AXIS'))
        if point_ref.get('part') in handles(p) and straight:
            line(sketch, line_ref)  # Validate the side index as well as its role.
            return [point_ref, line_ref]
    raise BadPayload('Selecciona un punto y una línea, lado recto o eje de ranura')


def rounding_links(sketch):
    links={}
    for arc in sketch['entities']:
        sides=fillet_sides(sketch,arc)
        if sides:
            for own,other in (sides,list(reversed(sides))):
                links[(own['id'],own['part'])]=other
    return links


def measure_line(sketch, ref):
    """A rounded side retains its length between virtual, sharp corners."""
    a,b=line(sketch,ref)
    e=get_entity(sketch,ref)
    if e['type']!='LINE': return a,b
    links=sketch.get('_rounding_links')
    if links is None: links=rounding_links(sketch)
    result=[]
    for role,p in (('START',a),('END',b)):
        other=links.get((e['id'],role))
        result.append(_fillet_corner(sketch,[ref,other]) if other else p)
    return tuple(result)


def radius(sketch, ref):
    e = get_entity(sketch, ref)
    if e['type'] not in ('CIRCLE', 'ARC', 'NGON', 'SLOT', 'GEAR'):
        raise BadPayload('Selecciona un círculo, arco, polígono regular, ranura o engranaje')
    # A regular polygon's radius is its inscribed one: half the across-flats size.
    # A slot's is its end caps; a gear's, its pitch circle.
    return {'CIRCLE': lambda: e['diameter']/2, 'NGON': lambda: e['flats']/2, 'SLOT': lambda: e['width']/2,
            'GEAR': lambda: e['module']*e['teeth']/2}.get(e['type'], lambda: e['radius'])()


def residual(sketch, c, scale):
    typ, refs = c['type'], c['refs']
    if typ == 'POINT_ON_LINE':
        point_ref, line_ref = point_line_refs(sketch, refs)
        p = point(sketch, point_ref)
        a, b = line(sketch, line_ref)
        d = b-a
        length = np.linalg.norm(d)
        if length < 1e-12:
            raise BadPayload('La recta necesita dos puntos distintos')
        # Signed perpendicular distance only; position along the infinite line
        # remains free, including beyond the visible segment's endpoints.
        return [(d[0]*(p[1]-a[1])-d[1]*(p[0]-a[0]))/(length*scale)]
    if typ == 'OFFSET':
        from .offset import shape, distance
        expected = shape(get_entity(sketch, refs[0]), distance(c))
        target = get_entity(sketch, refs[1])
        if target['type'] != expected['type']:
            raise BadPayload('Los contornos de desfase deben tener el mismo tipo')
        return [(target[k]-expected[k])/(180. if k in model.ANGULAR else scale)
                for k in model.FIELDS[target['type']]]
    if typ == 'FIX':
        e = get_entity(sketch, refs[0])
        if 'points' in c:
            return [(handles(e)[role][i]-p[i])/scale for role,p in c['points'].items() for i in (0,1)]
        return [(e[k]-v)/(1 if k in model.ANGULAR else scale) for k,v in c['values'].items()]
    if typ == 'SYMMETRIC':
        return ((point(sketch,refs[0])+point(sketch,refs[1]))*.5-point(sketch,refs[2]))/scale
    if typ == 'SYMMETRIC_LINE':
        p1, p2 = point(sketch,refs[0]), point(sketch,refs[1])
        a, b = line(sketch,refs[2])
        length = np.linalg.norm(b-a)
        if length < 1e-9: raise BadPayload('El eje de simetría necesita dos puntos distintos')
        d = (b-a)/length; n = np.array([-d[1], d[0]])
        mid = (p1+p2)*.5
        return [np.dot(mid-a,n)/scale, np.dot(p2-p1,d)/scale]
    if typ == 'MIDPOINT':
        a,b = line(sketch,refs[1])
        return (point(sketch,refs[0])-(a+b)*.5)/scale
    if typ == 'COINCIDENT':
        return (point(sketch,refs[0])-point(sketch,refs[1]))/scale
    if typ in ('DISTANCE', 'DISTANCE_X', 'DISTANCE_Y'):
        if len(refs) == 1:
            a,b = measure_line(sketch,refs[0])
        else:
            a,b = [point(sketch,r) for r in refs]
        measured = np.linalg.norm(b-a) if typ=='DISTANCE' else abs((b-a)[0 if typ=='DISTANCE_X' else 1])
        return [(measured-c['value'])/scale]
    if typ == 'RADIUS':
        return [(radius(sketch,refs[0])-c['value'])/scale]
    if typ == 'EQUAL':
        es = [get_entity(sketch,r) for r in refs]
        if all(e['type'] in ('ARC','CIRCLE') for e in es):
            return [(radius(sketch,refs[0])-radius(sketch,refs[1]))/scale]
        lengths = [np.linalg.norm(b-a) for a,b in [measure_line(sketch,r) for r in refs]]
        return [(lengths[0]-lengths[1])/scale]
    if typ == 'TANGENT':
        curve = next((r for r in refs if get_entity(sketch,r)['type'] in ('ARC','CIRCLE')),None)
        straight = next((r for r in refs if get_entity(sketch,r)['type']=='LINE'),None)
        if curve is None or straight is None:
            raise BadPayload('Tangencia: selecciona una línea y un arco o círculo')
        a,b = line(sketch,straight)
        e = get_entity(sketch,curve)
        d = b-a; center = np.array((e['x'],e['y']))
        distance = abs(d[0]*(center-a)[1]-d[1]*(center-a)[0])/max(np.linalg.norm(d),1e-12)
        return [(distance-radius(sketch,curve))/scale]
    a,b = line(sketch,refs[0]); d = b-a
    if typ == 'HORIZONTAL':
        return [d[1]/scale]
    if typ == 'VERTICAL':
        return [d[0]/scale]
    c0,c1 = line(sketch,refs[1]); other = c1-c0
    if typ == 'COLLINEAR':
        # Both endpoints lie on the same infinite line; their longitudinal
        # positions and the two lengths remain independent.
        length = max(np.linalg.norm(d), 1e-12)
        normal = np.array([-d[1], d[0]]) / length
        return [np.dot(c0-a,normal)/scale, np.dot(c1-a,normal)/scale]
    denom = max(np.linalg.norm(d)*np.linalg.norm(other),1e-20)
    return [(d[0]*other[1]-d[1]*other[0])/denom if typ=='PARALLEL' else np.dot(d,other)/denom]


def validate_constraints(sketch):
    ids = set()
    for c in sketch.get('constraints',[]):
        if c.get('type') not in CONSTRAINTS or not isinstance(c.get('id'),str) or c['id'] in ids:
            raise BadPayload('Restricción CAD no válida')
        ids.add(c['id'])
        refs = c.get('refs')
        typ = c['type']
        count = (3,) if typ in ('SYMMETRIC','SYMMETRIC_LINE') else (1,2) if typ in ('DISTANCE','DISTANCE_X','DISTANCE_Y') else (1,) if typ in ('FIX','HORIZONTAL','VERTICAL','RADIUS') else (2,)
        if not isinstance(refs,list) or len(refs) not in count or (len(refs)==2 and refs[0]==refs[1]):
            raise BadPayload('Número de elementos incorrecto para la restricción')
        for ref in refs:
            get_entity(sketch,ref)
        if typ in ('DISTANCE','RADIUS'):
            model.number(c.get('value'),positive=True)
        if typ in ('DISTANCE_X','DISTANCE_Y') and model.number(c.get('value')) < 0:
            raise BadPayload('La distancia horizontal o vertical no puede ser negativa')
        if typ == 'FIX':
            e = get_entity(sketch,refs[0])
            if 'points' in c:
                if not isinstance(c['points'],dict) or not c['points'] or not set(c['points']) <= set(handles(e)) or e['type']=='ORIGIN':
                    raise BadPayload('Fijación de puntos inválida')
                for p in c['points'].values():
                    if not isinstance(p,(list,tuple)) or len(p)!=2: raise BadPayload('Punto fijo inválido')
                    for value in p: model.number(value)
                residual(sketch,c,1.)
                continue
            if not isinstance(c.get('values'),dict) or set(c['values']) != set(model.FIELDS.get(e['type'],())) or e['type']=='ORIGIN':
                raise BadPayload('Fijación inválida')
            for value in c['values'].values(): model.number(value)
        residual(sketch,c,1.)
    from .offset import validate
    validate(sketch)


def solve(sketch, goals=(), *, drag=False):
    """Closest local solution with hard constraints and optional drag targets.

    A failed solve never mutates the caller. Parameter edits are hard FIX_FIELD
    goals; touch targets are soft, so locked geometry retains its constraints.
    """
    validate_constraints(sketch)
    work = copy.deepcopy(sketch)
    work['_rounding_links']=rounding_links(work)
    # Fully fixed drawings (projected references, FIX of the whole figure) are
    # constants: they never count towards the parameter limit.
    fixed = {c['refs'][0]['id'] for c in work.get('constraints',[]) if c['type']=='FIX' and 'values' in c}
    layout = [(e,k) for e in work['entities'] if e['id'] not in fixed for k in model.FIELDS[e['type']]]
    if len(layout)>300:
        raise CommandError('Este solver admite hasta 300 parámetros por boceto',code='cad_solver_limit')
    scale = max([abs(e[k]) for e,k in layout if k not in model.ANGULAR]+[.001])
    units = np.array([180. if k in model.ANGULAR else scale for e,k in layout])
    x = np.array([e[k] for e,k in layout])/units
    def evaluate(values):
        for (e,k),v,u in zip(layout,values,units): e[k]=float(v*u)
        result = []
        for c in work.get('constraints',[]): result.extend(residual(work,c,scale))
        for goal in goals:
            goal_start=len(result)
            if 'constraint' in goal:
                result.extend(residual(work,goal['constraint'],scale))
            elif 'field' in goal:
                e = get_entity(work,goal)
                divisor = 180 if goal['field'] in model.ANGULAR else scale
                result.append((e[goal['field']]-goal['value'])/divisor)
            elif 'center' in goal:
                e = get_entity(work,goal)
                cx,cy = goal['center']
                result.extend([(e['x']+e['width']/2-cx)/scale, (e['y']+e['height']/2-cy)/scale])
            else:
                result.extend((point(work,goal)-goal['point'])/scale)
            if drag and not goal.get('hard'):
                result[goal_start:]=[v*.001 for v in result[goal_start:]]
        return np.array(result,dtype=float)
    def jacobian(values,r):
        columns=[]
        for i in range(len(values)):
            p=values.copy(); p[i]+=1e-6
            columns.append((evaluate(p)-r)/1e-6)
        evaluate(values)
        return np.array(columns).T
    r=evaluate(x)
    for _ in range(60 if layout else 0):
        if not len(r) or np.max(np.abs(r))<1e-8: break
        j=jacobian(x,r)
        step=np.linalg.lstsq(j,-r,rcond=1e-9)[0]
        improved=False
        for factor in (1.,.5,.25,.125,.0625,.015625):
            candidate=x+step*factor; rr=evaluate(candidate)
            if np.linalg.norm(rr)<np.linalg.norm(r):
                x,r=candidate,rr; improved=True; break
        if not improved: break
    r=evaluate(x)
    if drag:
        # Reproject onto the hard constraint manifold after fitting the pointer.
        # A locked or constrained point follows only its remaining freedom.
        solve(work,[g for g in goals if g.get('hard')])
    elif len(r) and np.max(np.abs(r))>1e-7:
        raise CommandError('Restricciones incompatibles con este cambio; revisa o elimina una restricción',code='cad_constraint_conflict')
    for e in work['entities']: model.validate_entity(e)
    sketch['entities']=work['entities']
    return sketch


def arc_angle_goals(arc, target, previous_sweep):
    """The angular handle moves the end around a fixed center, radius and start."""
    dx,dy=target[0]-arc['x'],target[1]-arc['y']
    if math.hypot(dx,dy)<1e-9:
        sweep=previous_sweep
    else:
        angle=math.degrees(math.atan2(dy,dx))
        sweep=previous_sweep+(angle-arc['start']-previous_sweep+180.)%360.-180.
    sweep=max(.01,min(359.99,sweep)) if arc['sweep']>0 else min(-.01,max(-359.99,sweep))
    return [dict(id=arc['id'],field=k,value=arc[k],hard=True) for k in ('x','y','radius','start')]+[
        dict(id=arc['id'],field='sweep',value=sweep)]


def weld_points(sketch, refs):
    """Join endpoints with persistent coincidences, keeping the last point in place."""
    keys=list(dict.fromkeys((r['id'],r.get('part','BODY')) for r in refs))
    if len(keys)<2: raise BadPayload('Selecciona al menos dos extremos para soldar')
    refs=[dict(id=i,part=p) for i,p in keys]
    for ref in refs:
        e=get_entity(sketch,ref)
        allowed={'LINE':('START','END'),'ARC':('START','END'),'RECTANGLE':('P0','P1','P2','P3'),'ORIGIN':('POINT',),'POINT':('POINT',),
                 'NGON':tuple(p for p in handles(e) if p!='CENTER') if e['type']=='NGON' else ()}
        if ref['part'] not in allowed.get(e['type'],()):
            raise BadPayload('Soldar requiere extremos de líneas/arcos o esquinas, no figuras completas')
    anchor=next((r for r in refs if r['id']=='ORIGIN'),refs[-1])
    position=point(sketch,anchor)
    parent={}
    def root(key):
        parent.setdefault(key,key)
        if parent[key]!=key: parent[key]=root(parent[key])
        return parent[key]
    def join(a,b):
        a,b=root((a['id'],a['part'])),root((b['id'],b['part']))
        if a==b: return False
        parent[a]=b
        return True
    for c in sketch.get('constraints',[]):
        if c['type']=='COINCIDENT': join(*c['refs'])
    added=False
    for ref in refs:
        if join(ref,anchor):
            sketch.setdefault('constraints',[]).append(dict(id=model.uid('constraint'),type='COINCIDENT',refs=[ref,dict(anchor)]))
            added=True
    if added: solve(sketch,[dict(anchor,point=position,hard=True)])
    return added


def move_goals(sketch, refs, dx, dy):
    goals=[]; seen=set()
    for ref in refs:
        e=get_entity(sketch,ref); part=ref.get('part','BODY')
        if e['type']=='ORIGIN': continue
        points=handles(e)
        single_handle=sum(r['id']==e['id'] for r in refs)==1
        if part in points:
            roles=[part]
            if e['type']=='CIRCLE' and part=='RIM' and single_handle:
                goals.append(dict(id=e['id'],part='CENTER',point=np.array(points['CENTER']),hard=True))
            if e['type']=='RECTANGLE' and single_handle:
                # A symmetric shape: the center stays put and all four corners follow.
                goals.append(dict(id=e['id'],center=(e['x']+e['width']/2.,e['y']+e['height']/2.),hard=True))
            if e['type']=='NGON' and single_handle and part!='CENTER':
                # A vertex resizes and turns the polygon around its fixed center.
                goals.append(dict(id=e['id'],part='CENTER',point=np.array(points['CENTER']),hard=True))
            if e['type']=='SLOT' and single_handle and part=='SIDE':
                # Only the width follows: both cap centers stay where they are.
                goals.extend(dict(id=e['id'],part=role,point=np.array(points[role]),hard=True) for role in ('START','END'))
            if e['type']=='SLOT' and single_handle and part in ('START','END'):
                # One end center moves; the other stays, so length and direction follow.
                other='END' if part=='START' else 'START'
                goals.append(dict(id=e['id'],part=other,point=np.array(points[other]),hard=True))
        elif e['type']=='RECTANGLE' and part.startswith('EDGE'):
            index=int(part[4:]); roles=['P'+str(index),'P'+str((index+1)%4)]
        else:
            roles=list(points) if e['type'] in ('LINE','RECTANGLE','POINT') else ['CENTER']
        for role in roles:
            key=(e['id'],role)
            if key in seen: continue
            seen.add(key)
            goals.append(dict(id=e['id'],part=role,point=np.array(points[role])+[dx,dy]))
    return goals


def delete_selected(sketch, refs):
    """Delete analytic drawings or selected rectangle sides, keeping surviving rules.

    A primitive cannot exist without its defining point: deleting a line/arc
    endpoint or circle center removes that primitive. Rectangle corners remove
    their two incident sides; the other sides become constrained lines.
    """
    requests={}
    for ref in refs:
        if ref['id']=='ORIGIN': continue
        e=get_entity(sketch,ref)
        requests.setdefault(e['id'],set()).add(ref.get('part','BODY'))
    removed=set(); replacements={}; entities=[]
    for e in sketch['entities']:
        parts=requests.get(e['id'])
        if not parts:
            entities.append(e); continue
        if e['type']!='RECTANGLE' or 'BODY' in parts:
            removed.add(e['id']); continue
        deleted=set()
        for part in parts:
            if part in ('P0','P1','P2','P3'):
                index=int(part[1:]); deleted.update((index,(index-1)%4))
            elif part in ('EDGE0','EDGE1','EDGE2','EDGE3'): deleted.add(int(part[4:]))
            else: raise BadPayload('Selecciona un punto o lado del rectángulo')
        ring=model.outline(e)
        lines={i:dict(id=model.uid('entity'),type='LINE',x=a[0],y=a[1],x2=b[0],y2=b[1],
                      construction=e.get('construction',False))
               for i,(a,b) in enumerate(zip(ring,ring[1:]+ring[:1])) if i not in deleted}
        replacements[e['id']]=lines
        entities.extend(lines.values())
    def remap(ref):
        if ref['id'] in removed: return None
        if ref['id'] not in replacements: return copy.deepcopy(ref)
        lines=replacements[ref['id']]; part=ref.get('part','BODY')
        if part.startswith('EDGE'):
            line=lines.get(int(part[4:])); return dict(id=line['id'],part='BODY') if line else None
        if part in ('P0','P1','P2','P3'):
            index=int(part[1:])
            if index in lines: return dict(id=lines[index]['id'],part='START')
            if (index-1)%4 in lines: return dict(id=lines[(index-1)%4]['id'],part='END')
        return None
    constraints=[]
    for c in sketch.get('constraints',[]):
        if c['type']=='FIX' and c['refs'][0]['id'] in replacements:
            lines=replacements[c['refs'][0]['id']]
            if 'values' in c:
                for line in lines.values():
                    constraints.append(dict(id=model.uid('constraint'),type='FIX',refs=[dict(id=line['id'],part='BODY')],values={k:line[k] for k in model.FIELDS['LINE']}))
            else:
                for role,point_value in c['points'].items():
                    ref=remap(dict(id=c['refs'][0]['id'],part=role))
                    if ref: constraints.append(dict(id=model.uid('constraint'),type='FIX',refs=[ref],points={ref['part']:point_value}))
            continue
        mapped=[remap(r) for r in c['refs']]
        if all(r is not None for r in mapped):
            clone=copy.deepcopy(c); clone['refs']=mapped; constraints.append(clone)
    for lines in replacements.values():
        for index,line in lines.items():
            constraints.append(dict(id=model.uid('constraint'),type='HORIZONTAL' if index%2==0 else 'VERTICAL',refs=[dict(id=line['id'],part='BODY')]))
            neighbor=lines.get((index+1)%4)
            if neighbor:
                constraints.append(dict(id=model.uid('constraint'),type='COINCIDENT',refs=[dict(id=line['id'],part='END'),dict(id=neighbor['id'],part='START')]))
    sketch['entities']=entities; sketch['constraints']=constraints
    solve(sketch)


def _rectangle_lines(sketch, rectangle):
    """Expose rectangle sides as a constrained chain, preserving reference roles."""
    ring=model.outline(rectangle)
    lines=[dict(id=model.uid('entity'),type='LINE',x=a[0],y=a[1],x2=b[0],y2=b[1],
                construction=rectangle.get('construction',False)) for a,b in zip(ring,ring[1:]+ring[:1])]
    def remap(ref):
        if ref['id']!=rectangle['id']: return ref
        part=ref.get('part','BODY')
        if part.startswith('EDGE'): return dict(id=lines[int(part[4:])]['id'],part='BODY')
        if part.startswith('P'): return dict(id=lines[int(part[1:])]['id'],part='START')
        raise BadPayload('Quita la restricción de figura completa antes de redondear')
    constraints=[]
    for c in sketch.get('constraints',[]):
        if c['type']=='FIX' and c['refs'][0]['id']==rectangle['id']:
            if 'values' in c:
                for line in lines: constraints.append(dict(id=model.uid('constraint'),type='FIX',refs=[dict(id=line['id'],part='BODY')],values={k:line[k] for k in model.FIELDS['LINE']}))
            else:
                for role,p in c['points'].items(): constraints.append(dict(id=model.uid('constraint'),type='FIX',refs=[remap(dict(id=rectangle['id'],part=role))],points={'START':p}))
        else:
            clone=copy.deepcopy(c); clone['refs']=[remap(ref) for ref in c['refs']]; constraints.append(clone)
    sketch['entities'].remove(rectangle); sketch['entities'].extend(lines)
    for i,line in enumerate(lines):
        constraints.append(dict(id=model.uid('constraint'),type='COINCIDENT',refs=[dict(id=line['id'],part='END'),dict(id=lines[(i+1)%4]['id'],part='START')]))
        constraints.append(dict(id=model.uid('constraint'),type='HORIZONTAL' if i%2==0 else 'VERTICAL',refs=[dict(id=line['id'],part='BODY')]))
    sketch['constraints']=constraints
    return lines


def _corner_pairs(sketch, refs):
    """Corners to round, as pairs of line references sharing an endpoint.

    A whole rectangle gives its four corners; a rectangle corner or two adjacent
    sides give one. A line endpoint pairs with the line joined to it, so corners
    keep working after a rectangle became lines. Selected lines form every
    corner where two of them share an endpoint.
    """
    pairs=[]
    rectangles={}
    for ref in refs:
        e=get_entity(sketch,ref)
        if e['type']=='RECTANGLE': rectangles.setdefault(e['id'],[]).append(ref.get('part','BODY'))
    for identifier,parts in rectangles.items():
        rectangle=get_entity(sketch,dict(id=identifier))
        if 'BODY' in parts: corners=[0,1,2,3]
        else:
            corners=[int(p[1:]) for p in parts if p in ('P0','P1','P2','P3')]
            edges=[int(p[4:]) for p in parts if p.startswith('EDGE')]
            if edges:
                if len(edges)!=2: raise BadPayload('Elige dos lados contiguos del rectángulo')
                shared=set((edges[0],(edges[0]+1)%4)) & set((edges[1],(edges[1]+1)%4))
                if len(shared)!=1: raise BadPayload('Elige dos lados contiguos del rectángulo')
                corners.append(shared.pop())
        lines=_rectangle_lines(sketch,rectangle)
        pairs.extend((dict(id=lines[(c-1)%4]['id'],part='BODY'),dict(id=lines[c]['id'],part='BODY')) for c in sorted(set(corners)))
    others=[r for r in refs if r['id']!='ORIGIN' and r['id'] not in rectangles]
    lines=[get_entity(sketch,r) for r in others if r.get('part','BODY')=='BODY' and get_entity(sketch,r)['type']=='LINE']
    for i,a in enumerate(lines):
        for b in lines[i+1:]:
            if any(math.dist(p,q)<1e-7 for p in handles(a).values() for q in handles(b).values()):
                pairs.append((dict(id=a['id'],part='BODY'),dict(id=b['id'],part='BODY')))
    for ref in others:
        e=get_entity(sketch,ref); role=ref.get('part','BODY')
        if e['type']!='LINE' or role not in ('START','END'): continue
        p=handles(e)[role]
        partner=next((o for o in sketch['entities'] if o['type']=='LINE' and o['id']!=e['id']
                      and any(math.dist(p,q)<1e-7 for q in handles(o).values())),None)
        if partner is None: raise BadPayload('Ese extremo no forma esquina con otra línea')
        pairs.append((dict(id=e['id'],part='BODY'),dict(id=partner['id'],part='BODY')))
    unique=[]; seen=set()
    for a,b in pairs:
        key=frozenset((a['id'],b['id']))
        if key not in seen: seen.add(key); unique.append((a,b))
    return unique


def _round_corner(corner, ends, radius, old_start=None):
    radius=model.number(radius,positive=True)
    lengths=[np.linalg.norm(p-corner) for p in ends]
    if any(length<1e-7 for length in lengths): raise BadPayload('La esquina no tiene lados suficientes')
    dirs=[(p-corner)/length for p,length in zip(ends,lengths)]
    theta=math.acos(float(np.clip(np.dot(*dirs),-1,1)))
    if theta<.001 or abs(theta-math.pi)<.001: raise BadPayload('Las líneas no forman una esquina válida')
    distance=radius/math.tan(theta/2)
    if any(distance>=length-1e-7 for length in lengths): raise BadPayload('El radio no cabe en los lados')
    touches=[corner+d*distance for d in dirs]
    bisector=dirs[0]+dirs[1]; bisector/=np.linalg.norm(bisector)
    center=corner+bisector*radius/math.sin(theta/2)
    angles=[math.degrees(math.atan2(*(p-center)[::-1])) for p in touches]
    start=angles[0] if old_start is None else angles[0]+360*round((old_start-angles[0])/360)
    return touches,dict(x=float(center[0]),y=float(center[1]),radius=radius,start=start,sweep=(angles[1]-angles[0]+180)%360-180)


def fillet(sketch, refs, r):
    """Round every selected corner with tangent arcs of one shared radius.

    The first arc owns the radius dimension and the rest are Igualdad to it, so
    four corners of a rectangle are edited with a single value.
    """
    pairs=_corner_pairs(sketch,refs)
    if not pairs:
        raise BadPayload('Redondeo: toca una esquina, un rectángulo entero o dos líneas conectadas')
    arcs=[]
    for a,b in pairs:
        arc=_fillet_pair(sketch,a,b,r)
        constraints=sketch['constraints']
        if arcs: constraints.append(dict(id=model.uid('constraint'),type='EQUAL',refs=[dict(id=arcs[0]['id'],part='BODY'),dict(id=arc['id'],part='BODY')]))
        else: constraints.append(dict(id=model.uid('constraint'),type='RADIUS',refs=[dict(id=arc['id'],part='BODY')],value=r))
        arcs.append(arc)
    solve(sketch)
    return arcs


def _fillet_pair(sketch, ref_a, ref_b, r):
    """Trim two connected straight edges and insert their tangent circular arc."""
    es=[get_entity(sketch,ref) for ref in (ref_a,ref_b)]
    if es[0]['id']==es[1]['id'] or any(e['type']!='LINE' for e in es):
        raise BadPayload('Redondeo: selecciona dos líneas distintas')
    pairs=[(ra,rb) for ra,pa in handles(es[0]).items() for rb,pb in handles(es[1]).items() if math.dist(pa,pb)<1e-7]
    if len(pairs)!=1:
        raise BadPayload('Las líneas deben compartir un extremo')
    ra,rb=pairs[0]; corner=np.array(handles(es[0])[ra])
    ends=[np.array(handles(e)['END' if role=='START' else 'START']) for e,role in zip(es,(ra,rb))]
    touches,parameters=_round_corner(corner,ends,r)
    for e,role,p in zip(es,(ra,rb),touches):
        kx,ky=('x','y') if role=='START' else ('x2','y2')
        e[kx],e[ky]=map(float,p)
    arc=dict(id=model.uid('entity'),type='ARC',**parameters,construction=all(e.get('construction',False) for e in es))
    sketch['entities'].append(arc)
    constraints=sketch.setdefault('constraints',[])
    # Replace exactly the joined corner constraint; preserve all unrelated constraints.
    joined={(es[0]['id'],ra),(es[1]['id'],rb)}
    constraints[:]=[c for c in constraints if not(c['type']=='COINCIDENT' and {(v['id'],v.get('part')) for v in c['refs']}==joined)]
    for e,role,arc_role in zip(es,(ra,rb),('START','END')):
        constraints.append(dict(id=model.uid('constraint'),type='COINCIDENT',refs=[dict(id=e['id'],part=role),dict(id=arc['id'],part=arc_role)]))
        constraints.append(dict(id=model.uid('constraint'),type='TANGENT',refs=[dict(id=e['id'],part='BODY'),dict(id=arc['id'],part='BODY')]))
    return arc


def fillet_sides(sketch, arc):
    """Recognize existing roundings by their joins/tangencies, including saved files."""
    if arc['type']!='ARC' or abs(arc['sweep'])>=179.999: return None
    result=[]
    for role in ('START','END'):
        candidates=[]
        for c in sketch.get('constraints',[]):
            if c['type']!='COINCIDENT': continue
            own=next((r for r in c['refs'] if r['id']==arc['id'] and r.get('part')==role),None)
            if own is None: continue
            other=next((r for r in c['refs'] if r is not own),None)
            if other is None: continue
            e=get_entity(sketch,other)
            if e['type']!='LINE' or other.get('part') not in ('START','END'): continue
            if any(t['type']=='TANGENT' and {r['id'] for r in t['refs']}=={arc['id'],e['id']} for t in sketch.get('constraints',[])):
                candidates.append(dict(id=e['id'],part=other['part']))
        if len(candidates)!=1: return None
        result.append(candidates[0])
    return result if result[0]['id']!=result[1]['id'] else None


def _fillet_corner(sketch, sides):
    a,b=line(sketch,sides[0]); c,d=line(sketch,sides[1])
    matrix=np.column_stack((b-a,c-d))
    if abs(np.linalg.det(matrix))<1e-10*np.linalg.norm(b-a)*np.linalg.norm(d-c):
        raise BadPayload('Los lados del redondeo ya no forman una esquina')
    return a+(b-a)*np.linalg.solve(matrix,c-a)[0]


def resize_fillet(sketch, arc, radius):
    """Recompute trim points at the current corner and retain the outer endpoints."""
    sides=fillet_sides(sketch,arc)
    if sides is None: return []
    corner=_fillet_corner(sketch,sides)
    es=[get_entity(sketch,r) for r in sides]
    ends=[np.array(handles(e)['END' if ref['part']=='START' else 'START']) for e,ref in zip(es,sides)]
    touches,parameters=_round_corner(corner,ends,radius,arc['start'])
    arc.update(parameters)
    for e,ref,p in zip(es,sides,touches):
        kx,ky=('x','y') if ref['part']=='START' else ('x2','y2')
        e[kx],e[ky]=map(float,p)
    return [dict(id=arc['id'],field='radius',value=radius)]


def remove_fillet(sketch, arc):
    sides=fillet_sides(sketch,arc)
    if sides is None: raise BadPayload('Selecciona un redondeo unido a dos líneas tangentes')
    corner=_fillet_corner(sketch,sides)
    es=[get_entity(sketch,r) for r in sides]
    for e,ref in zip(es,sides):
        kx,ky=('x','y') if ref['part']=='START' else ('x2','y2')
        e[kx],e[ky]=map(float,corner)
    sketch['entities'].remove(arc)
    sketch['constraints']=[c for c in sketch.get('constraints',[]) if not any(r['id']==arc['id'] for r in c['refs'])]
    sketch['constraints'].append(dict(id=model.uid('constraint'),type='COINCIDENT',refs=sides))
    solve(sketch)


def chain_segments(segments, tol):
    """Join 2D segments into polylines; returns (points, closed) pairs."""
    key=lambda p:(round(p[0]/tol),round(p[1]/tol))
    links={}
    for a,b in segments:
        if math.dist(a,b)<tol: continue
        links.setdefault(key(a),[]).append((a,b)); links.setdefault(key(b),[]).append((b,a))
    used=set(); chains=[]
    def walk(start):
        points=[start[0],start[1]]; used.add(frozenset((key(start[0]),key(start[1]))))
        while True:
            options=[s for s in links[key(points[-1])] if frozenset((key(s[0]),key(s[1]))) not in used]
            if len(options)!=1 or len(links[key(points[-1])])>2: return points
            used.add(frozenset((key(options[0][0]),key(options[0][1])))); points.append(options[0][1])
    ends=[k for k,v in links.items() if len(v)!=2]
    for k in ends+list(links):
        for segment in links[k]:
            if frozenset((key(segment[0]),key(segment[1]))) in used: continue
            points=walk(segment)
            closed=len(points)>3 and key(points[0])==key(points[-1])
            chains.append((points[:-1] if closed else points,closed))
    return chains


def _circle(a, b, c):
    ax,ay=a; bx,by=b; cx,cy=c
    d=2*(ax*(by-cy)+bx*(cy-ay)+cx*(ay-by))
    if abs(d)<1e-24: return None
    ux=((ax*ax+ay*ay)*(by-cy)+(bx*bx+by*by)*(cy-ay)+(cx*cx+cy*cy)*(ay-by))/d
    uy=((ax*ax+ay*ay)*(cx-bx)+(bx*bx+by*by)*(ax-cx)+(cx*cx+cy*cy)*(bx-ax))/d
    return (ux,uy),math.dist((ux,uy),a)


def fit_polyline(points, closed, tol):
    """Straight runs become LINEs, co-circular runs ARCs, a whole round loop a CIRCLE.

    Tessellated solids arrive as many short segments; fitting them keeps a
    projection light and gives Onshape-like references (centers to snap to).
    """
    def on_line(run):
        a,b=np.array(run[0]),np.array(run[-1]); d=b-a; length=np.linalg.norm(d)
        if length<tol: return False
        return all(abs(d[0]*(p[1]-a[1])-d[1]*(p[0]-a[0]))/length<=tol for p in run[1:-1])
    def round_run(run, fit):
        # Tessellation steps are small; polygon corners (a rectangle's, on its
        # circumcircle) are not an arc.
        return fit is not None and all(abs(math.dist(fit[0],p)-fit[1])<=tol for p in run) and \
            all(math.dist(a,b)<=2*fit[1]*math.sin(math.radians(12.5)) for a,b in zip(run,run[1:]))
    def on_arc(run):
        fit=_circle(run[0],run[len(run)//2],run[-1])
        if fit is None and len(run)>3: fit=_circle(run[0],run[1],run[-1])
        return fit if round_run(run,fit) else None
    if closed and len(points)>=8:
        fit=_circle(points[0],points[len(points)//3],points[2*len(points)//3])
        if round_run(points+[points[0]],fit):
            return [dict(type='CIRCLE',x=fit[0][0],y=fit[0][1],diameter=2*fit[1])]
    path=list(points)+([points[0]] if closed else [])
    result=[]; i=0
    while i<len(path)-1:
        j=i+1
        while j+1<len(path) and on_line(path[i:j+2]): j+=1
        k=i+2
        arc=None
        while k<len(path) and on_arc(path[i:k+1]): arc=on_arc(path[i:k+1]); k+=1
        k-=1
        if arc and k-i>=3 and k>j:
            (cx,cy),r=arc
            a0=math.degrees(math.atan2(path[i][1]-cy,path[i][0]-cx)); a1=math.degrees(math.atan2(path[k][1]-cy,path[k][0]-cx))
            am=math.degrees(math.atan2(path[(i+k)//2][1]-cy,path[(i+k)//2][0]-cx))
            sweep=(a1-a0)%360.
            if (am-a0)%360.>sweep: sweep-=360.
            if .01<=abs(sweep)<360: result.append(dict(type='ARC',x=cx,y=cy,radius=r,start=a0,sweep=sweep)); i=k; continue
        a,b=path[i],path[j]
        result.append(dict(type='LINE',x=a[0],y=a[1],x2=b[0],y2=b[1])); i=j
    return result
