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
            a,b = line(sketch,refs[0])
        else:
            a,b = [point(sketch,r) for r in refs]
        return [(np.linalg.norm(b-a)-c['value'])/scale]
    if typ == 'RADIUS':
        return [(radius(sketch,refs[0])-c['value'])/scale]
    if typ == 'EQUAL':
        es = [get_entity(sketch,r) for r in refs]
        if all(e['type'] in ('ARC','CIRCLE') for e in es):
            return [(radius(sketch,refs[0])-radius(sketch,refs[1]))/scale]
        lengths = [np.linalg.norm(b-a) for a,b in [line(sketch,r) for r in refs]]
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
            if 'field' in goal:
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
    dirs=[(p-corner)/np.linalg.norm(p-corner) for p in ends]
    theta=math.acos(float(np.clip(np.dot(*dirs),-1,1)))
    if theta<.001 or abs(theta-math.pi)<.001: raise BadPayload('Las líneas no forman una esquina')
    distance=r/math.tan(theta/2)
    if any(distance>=np.linalg.norm(p-corner)-1e-7 for p in ends): raise BadPayload('El radio no cabe en los lados')
    touches=[corner+d*distance for d in dirs]
    bisector=dirs[0]+dirs[1]; bisector/=np.linalg.norm(bisector)
    center=corner+bisector*r/math.sin(theta/2)
    angles=[math.degrees(math.atan2(*(p-center)[::-1])) for p in touches]
    sweep=(angles[1]-angles[0]+180)%360-180
    for e,role,p in zip(es,(ra,rb),touches):
        kx,ky=('x','y') if role=='START' else ('x2','y2')
        e[kx],e[ky]=map(float,p)
    arc=dict(id=model.uid('entity'),type='ARC',x=float(center[0]),y=float(center[1]),radius=r,start=angles[0],sweep=sweep,construction=all(e.get('construction',False) for e in es))
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
