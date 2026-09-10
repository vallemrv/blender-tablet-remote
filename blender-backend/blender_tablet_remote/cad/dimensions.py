"""One editable dimension per quantity, including equality-linked quantities."""
import copy
import math
from . import document as model, sketch as geometry
from ..errors import BadPayload, CommandError

NUMERIC = ('DISTANCE', 'RADIUS')


def quantity(sketch, ref):
    e=geometry.get_entity(sketch,ref)
    if e['type'] in ('CIRCLE','ARC'): return (e['id'],'radius')
    if e['type']=='LINE': return (e['id'],'length')
    if e['type']=='RECTANGLE' and ref.get('part','').startswith('EDGE'):
        return (e['id'],'width' if int(ref['part'][4:])%2==0 else 'height')
    return None


def groups(sketch):
    parents={}
    def root(key):
        if key not in parents: parents[key]=key
        if parents[key]!=key: parents[key]=root(parents[key])
        return parents[key]
    for c in sketch.get('constraints',[]):
        if c['type']=='EQUAL':
            a,b=[quantity(sketch,r) for r in c['refs']]
            if a is not None and b is not None: parents[root(b)]=root(a)
    return root


def key(sketch, constraint, root=None):
    if constraint['type'] not in NUMERIC: return None
    root=root or groups(sketch)
    refs=constraint['refs']
    if len(refs)==1: return root(quantity(sketch,refs[0]))
    if refs[0]['id']==refs[1]['id']:
        e=geometry.get_entity(sketch,refs[0]); parts={r.get('part') for r in refs}
        if e['type']=='LINE' and parts=={'START','END'} and not any((e['id'],role) in geometry.rounding_links(sketch) for role in ('START','END')):
            return root((e['id'],'length'))
        if e['type']=='CIRCLE' and parts=={'CENTER','RIM'}: return root((e['id'],'radius'))
        if e['type']=='RECTANGLE':
            for i in range(4):
                if parts=={'P'+str(i),'P'+str((i+1)%4)}:
                    return root((e['id'],'width' if i%2==0 else 'height'))
    return ('distance',tuple(sorted((r['id'],r.get('part','BODY')) for r in refs)))


def matching(sketch, constraint):
    root=groups(sketch); target=key(sketch,constraint,root)
    return [c for c in sketch.get('constraints',[]) if key(sketch,c,root)==target] if target is not None else []


def put(sketch, constraint):
    """Update the existing dimension, merging older duplicate measurements."""
    geometry.validate_constraints(dict(sketch,constraints=[constraint]))
    existing=matching(sketch,constraint)
    if existing:
        chosen=next((c for c in existing if c['id']==constraint['id']),existing[0])
        chosen['value']=constraint['value']
        sketch['constraints']=[c for c in sketch['constraints'] if c not in existing or c is chosen]
        return chosen
    sketch.setdefault('constraints',[]).append(constraint)
    return constraint


def remove(sketch, constraint):
    duplicates=matching(sketch,constraint) or [constraint]
    sketch['constraints']=[c for c in sketch['constraints'] if c not in duplicates]


def bindings(sketch, entity):
    fields={'RECTANGLE':('width','height'),'CIRCLE':('diameter',),'ARC':('radius',),'LINE':('length',)}[entity['type']]
    root=groups(sketch)
    result={}
    for field in fields:
        target=root((entity['id'],'radius' if field=='diameter' else field))
        result[field]=[c['id'] for c in sketch.get('constraints',[]) if key(sketch,c,root)==target]
    return result


def is_square(sketch, entity):
    root=groups(sketch)
    return entity['type']=='RECTANGLE' and root((entity['id'],'width'))==root((entity['id'],'height'))


def set_values(sketch, entity, changes):
    """Editing a measured quantity updates its dimension instead of fighting it."""
    bound=bindings(sketch,entity); updated={}; root=groups(sketch)
    for field,value in changes.items():
        for identifier in bound.get(field,[]):
            c=model.find(sketch,'constraints',identifier)
            target=key(sketch,c,root); amount=value/2 if field=='diameter' else value
            if target in updated and not math.isclose(updated[target],amount,rel_tol=1e-9,abs_tol=1e-12):
                raise BadPayload('Estas medidas están enlazadas por Igualdad; escribe un único valor')
            updated[target]=amount
    # Resolve IDs before removing duplicates (both square fields can share one dimension).
    candidates=[(copy.deepcopy(c),updated[key(sketch,c,root)]) for c in sketch.get('constraints',[]) if key(sketch,c,root) in updated]
    for c,value in candidates:
        c['value']=model.number(value,positive=True); put(sketch,c)
    goals=[]
    for field,value in changes.items():
        if field=='length':
            if any((entity['id'],role) in geometry.rounding_links(sketch) for role in ('START','END')):
                goals.append(dict(constraint=dict(type='DISTANCE',refs=[dict(id=entity['id'],part='BODY')],value=model.number(value,positive=True))))
                continue
            if value<1e-7: raise BadPayload('La longitud debe ser positiva')
            dx,dy=entity['x2']-entity['x'],entity['y2']-entity['y']
            length=math.hypot(dx,dy)
            goals.extend(dict(id=entity['id'],field=k,value=v) for k,v in
                         [('x',entity['x']),('y',entity['y']),('x2',entity['x']+dx/length*value),('y2',entity['y']+dy/length*value)])
        else: goals.append(dict(id=entity['id'],field=field,value=value))
    for arc in sketch['entities']:
        target=root((arc['id'],'radius'))
        radius=updated.get(target)
        if arc['id']==entity['id'] and arc['type']=='ARC' and 'radius' in changes: radius=changes['radius']
        if radius is not None: goals.extend(geometry.resize_fillet(sketch,arc,radius))
    return goals


def solve_dimension(sketch, constraint):
    root=groups(sketch); target=key(sketch,constraint,root); goals=[]
    for arc in sketch['entities']:
        if arc['type']=='ARC' and root((arc['id'],'radius'))==target:
            goals.extend(geometry.resize_fillet(sketch,arc,constraint['value']))
    geometry.solve(sketch,goals)


def describe(sketch, entity):
    bound=bindings(sketch,entity); typ=entity['type']
    fields={'RECTANGLE':[('width','Lado' if is_square(sketch,entity) else 'Ancho','DISTANCE','EDGE0',1.),('height','Alto','DISTANCE','EDGE1',1.)],
            'CIRCLE':[('diameter','Diámetro','RADIUS','BODY',.5)],
            'ARC':[('radius','Radio del redondeo' if geometry.fillet_sides(sketch,entity) else 'Radio','RADIUS','BODY',1.)],
            'LINE':[('length','Lado completo' if any((entity['id'],role) in geometry.rounding_links(sketch) for role in ('START','END')) else 'Longitud','DISTANCE','BODY',1.)]}[typ]
    if typ=='RECTANGLE' and is_square(sketch,entity): fields=fields[:1]
    return [dict(field=field,label=label,constraint_type=kind,value_factor=factor,
                 refs=[dict(id=entity['id'],part=part)],constraint_ids=bound[field])
            for field,label,kind,part,factor in fields]


def offers(sketch, refs):
    result={}
    for typ in NUMERIC:
        try:
            if typ=='RADIUS':
                if len(refs)!=1: continue
                value=geometry.radius(sketch,refs[0])
            elif len(refs)==1:
                a,b=geometry.measure_line(sketch,refs[0]); value=math.dist(a,b)
            elif len(refs)==2:
                a,b=[geometry.point(sketch,r) for r in refs]; value=math.dist(a,b)
            else: continue
            if value<1e-7: continue
            c=dict(id='offer',type=typ,refs=refs,value=value)
            geometry.validate_constraints(dict(sketch,constraints=[c]))
            existing=matching(sketch,c)
            result[typ]=dict(value=existing[0]['value'] if existing else value,
                             constraint_id=existing[0]['id'] if existing else None)
        except (CommandError,ValueError,KeyError): continue
    return result


def visible_constraints(sketch):
    """Old duplicate dimensions share one control; editing/removing it merges storage."""
    root=groups(sketch); seen=set(); result=[]
    for c in sketch.get('constraints',[]):
        target=key(sketch,c,root)
        if target is not None:
            if target in seen: continue
            seen.add(target)
        result.append(c)
    return result
