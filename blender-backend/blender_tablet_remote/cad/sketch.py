"""Sketch handles and a bounded numerical constraint solver, in metres.

NumPy ships with Blender. Residuals validate the supported constraint system;
incompatible edits fail atomically instead of silently dropping rules.
"""
import copy
import math
import numpy as np
from . import document as model
from ..errors import BadPayload, CommandError

CONSTRAINTS = ('COINCIDENT', 'HORIZONTAL', 'VERTICAL', 'PARALLEL', 'PERPENDICULAR',
               'TANGENT', 'EQUAL', 'DISTANCE', 'RADIUS', 'FIX', 'MIDPOINT', 'SYMMETRIC')


def handles(e):
    typ = e['type']
    if typ == 'ORIGIN': return {'POINT': (0., 0.)}
    if typ == 'LINE':
        return {'START': (e['x'],e['y']), 'END': (e['x2'],e['y2'])}
    if typ == 'RECTANGLE':
        return dict(zip(('P0','P1','P2','P3'),model.outline(e)))
    if typ == 'ARC':
        path = model.outline(e)
        return {'CENTER': (e['x'],e['y']), 'START': path[0], 'END': path[-1]}
    return {'CENTER': (e['x'],e['y']), 'RIM': (e['x']+e['diameter']/2,e['y'])}


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
    if e['type'] == 'RECTANGLE' and str(ref.get('part','')).startswith('EDGE'):
        ring = model.outline(e)
        i = int(ref['part'][4:])
        if i not in range(4):
            raise BadPayload('Arista inexistente')
        return np.array(ring[i]), np.array(ring[(i+1)%4])
    if e['type'] != 'LINE':
        raise BadPayload('Selecciona líneas o lados rectos')
    return np.array((e['x'],e['y'])), np.array((e['x2'],e['y2']))


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
    if e['type'] not in ('CIRCLE', 'ARC'):
        raise BadPayload('Selecciona un círculo o arco')
    return e['diameter']/2 if e['type']=='CIRCLE' else e['radius']


def residual(sketch, c, scale):
    typ, refs = c['type'], c['refs']
    if typ == 'FIX':
        e = get_entity(sketch, refs[0])
        if 'points' in c:
            return [(handles(e)[role][i]-p[i])/scale for role,p in c['points'].items() for i in (0,1)]
        return [(e[k]-v)/(1 if k in ('start','sweep') else scale) for k,v in c['values'].items()]
    if typ == 'SYMMETRIC':
        return ((point(sketch,refs[0])+point(sketch,refs[1]))*.5-point(sketch,refs[2]))/scale
    if typ == 'MIDPOINT':
        a,b = line(sketch,refs[1])
        return (point(sketch,refs[0])-(a+b)*.5)/scale
    if typ == 'COINCIDENT':
        return (point(sketch,refs[0])-point(sketch,refs[1]))/scale
    if typ == 'DISTANCE':
        if len(refs) == 1:
            a,b = measure_line(sketch,refs[0])
        else:
            a,b = [point(sketch,r) for r in refs]
        return [(np.linalg.norm(b-a)-c['value'])/scale]
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
        count = (3,) if typ=='SYMMETRIC' else (1,2) if typ=='DISTANCE' else (1,) if typ in ('FIX','HORIZONTAL','VERTICAL','RADIUS') else (2,)
        if not isinstance(refs,list) or len(refs) not in count or (len(refs)==2 and refs[0]==refs[1]):
            raise BadPayload('Número de elementos incorrecto para la restricción')
        for ref in refs:
            get_entity(sketch,ref)
        if typ in ('DISTANCE','RADIUS'):
            model.number(c.get('value'),positive=True)
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


def solve(sketch, goals=(), *, drag=False):
    """Closest local solution with hard constraints and optional drag targets.

    A failed solve never mutates the caller. Parameter edits are hard FIX_FIELD
    goals; touch targets are soft, so locked geometry retains its constraints.
    """
    validate_constraints(sketch)
    work = copy.deepcopy(sketch)
    work['_rounding_links']=rounding_links(work)
    layout = [(e,k) for e in work['entities'] for k in model.FIELDS[e['type']]]
    if len(layout)>300:
        raise CommandError('Este solver admite hasta 300 parámetros por boceto',code='cad_solver_limit')
    scale = max([abs(e[k]) for e,k in layout if k not in ('start','sweep')]+[.001])
    units = np.array([180. if k in ('start','sweep') else scale for e,k in layout])
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
                divisor = 180 if goal['field'] in ('start','sweep') else scale
                result.append((e[goal['field']]-goal['value'])/divisor)
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
    for _ in range(60):
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
                opposite='P'+str((int(part[1:])+2)%4)
                goals.append(dict(id=e['id'],part=opposite,point=np.array(points[opposite]),hard=True))
        elif e['type']=='RECTANGLE' and part.startswith('EDGE'):
            index=int(part[4:]); roles=['P'+str(index),'P'+str((index+1)%4)]
        else:
            roles=list(points) if e['type'] in ('LINE','RECTANGLE') else ['CENTER']
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


def _rectangle_corner(sketch, refs):
    """Expose rectangle sides as a constrained chain, preserving reference roles."""
    if not refs or len({r['id'] for r in refs})!=1: return refs,None
    rectangle=get_entity(sketch,refs[0])
    if rectangle['type']!='RECTANGLE': return refs,None
    parts=[ref.get('part','BODY') for ref in refs]
    if len(parts)==1 and parts[0] in ('P0','P1','P2','P3'): corner=int(parts[0][1:])
    elif len(parts)==2 and all(p.startswith('EDGE') for p in parts):
        edges=[int(p[4:]) for p in parts]
        shared=set((edges[0],(edges[0]+1)%4)) & set((edges[1],(edges[1]+1)%4))
        if len(shared)!=1: raise BadPayload('Elige dos lados contiguos del rectángulo')
        corner=shared.pop()
    else: raise BadPayload('Toca una esquina del rectángulo o selecciona dos lados contiguos')
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
    return [dict(id=lines[(corner-1)%4]['id'],part='BODY'),dict(id=lines[corner]['id'],part='BODY')],rectangle['id']


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
    """Trim two connected straight edges and insert their tangent circular arc."""
    refs,_ = _rectangle_corner(sketch,refs)
    if len(refs)!=2:
        raise BadPayload('Redondeo: selecciona dos líneas conectadas')
    es=[get_entity(sketch,ref) for ref in refs]
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
    constraints.append(dict(id=model.uid('constraint'),type='RADIUS',refs=[dict(id=arc['id'],part='BODY')],value=r))
    solve(sketch)
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
