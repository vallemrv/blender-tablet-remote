"""cad.*: intent commands; all geometry and bpy run in the bridge pump."""
import copy
import math
import bpy
from . import command
from ..cad import document as model
from ..cad import sketch as geometry
from ..cad import dimensions
from ..cad.runtime import runtime, FEATURE_KEY, DOC_KEY, BODY_KEY
from ..errors import BadPayload, CommandError
from ..bpy_utils import undo_push


def _activate_feature(doc, identifier):
    body=model.find(doc,'features',identifier)['body_id']
    obj = next((o for o in runtime.objects(doc) if o.get(BODY_KEY)==body or o[FEATURE_KEY] == identifier), None)
    if obj is not None and not obj.hide_viewport:
        for other in bpy.context.view_layer.objects:
            if other.select_get():
                other.select_set(False)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj


def _sequence(doc):
    return [n['id'] for n in model.history(doc)]


def _reachable_ids(doc):
    """History node ids up to and including the rollback bar; all when at the end."""
    sequence = _sequence(doc)
    bar = runtime.bar(doc)
    return set(sequence) if bar is None else set(sequence[:sequence.index(bar)+1])


def _require_reachable(doc, node_id):
    """Nodes beyond the rollback bar are future history: refuse to touch them."""
    bar = runtime.bar(doc)
    if bar is None:
        return
    sequence = _sequence(doc)
    if node_id in sequence and bar in sequence and sequence.index(node_id) > sequence.index(bar):
        raise CommandError('El nodo está después de la vista actual; avanza la pila para editarlo',
                           code='cad_rollback')


@command('cad.history.rollback')
def history_rollback(payload):
    runtime.require_workspace()
    if runtime.session:
        runtime.require(payload)
        runtime.cancel()
    identifier = payload.get('node_id')
    if identifier is not None:
        if identifier not in _sequence(runtime.doc()):
            raise CommandError('El nodo ya no existe en el documento', code='cad_reference_missing')
        runtime.rollback_id = identifier
    else:
        runtime.rollback_id = None
    doc = runtime.doc()
    bar = runtime.bar(doc)
    sequence = _sequence(doc)
    if bar and runtime.active_sketch_id in sequence and sequence.index(runtime.active_sketch_id) > sequence.index(bar):
        # Editing a node that is now future history: leave the sketch view.
        runtime.active_sketch_id = None
        runtime.selection = None
        runtime.surface.mode = 'PROFILE'
        runtime.surface.clear()
        runtime.solid_view()
    else:
        yield from runtime.rebuild_steps(doc, limit=bar)
    if not runtime.active_sketch_id and identifier:
        node=next(node for node in model.history(doc) if node['id']==identifier)
        runtime.active_body_id=node['body_id']
        if node['kind']=='SKETCH':
            runtime.selection=dict(kind='SKETCH',id=identifier) if model.profiles(node) else None
        else:
            runtime.selection=dict(kind='FEATURE',id=identifier)
            _activate_feature(doc,identifier)
    return runtime.status()


@command('cad.state')
def state(payload):
    return runtime.status()


@command('cad.sketch.create')
def sketch_create(payload):
    plane = str(payload.get('plane','XY')).upper()
    if plane not in model.PLANES:
        raise BadPayload('Plano CAD no compatible')
    return (yield from runtime.transaction_steps(payload,lambda doc: _new_sketch(doc,payload),'CAD crear sketch'))


def _new_sketch(doc,payload):
    offset=model.number(payload.get('offset',0))
    support_id=payload.get('support_id')
    if support_id:
        feature=model.find(doc,'features',support_id)
        if feature.get('mirror'): raise BadPayload('Usa Boceto en cara sobre el resultado de la simetría')
        if feature['type'] in model.FINISHES + ('LOFT','HELIX'):
            raise BadPayload('Un redondeo o solevado no sirve de apoyo; usa Boceto en cara sobre la cara que quieras')
        source,_=model.profile(doc,feature['profile_id'])
        plane_local=source['plane']
        offset=source.get('offset',0)+(feature['depth'] if feature['type']=='EXTRUDE' else 0)
    else: plane_local=str(payload.get('plane','XY')).upper()
    sketch = dict(id=model.uid('sketch'),name='Boceto '+str(len(doc['sketches'])+1),plane=plane_local,
                  offset=offset,entities=[],constraints=[],visible=True,order=model.next_order(doc),body_id=payload.get('body_id') or runtime.active_body_id or doc['bodies'][0]['id'])
    model.find(doc,'bodies',sketch['body_id'])
    if payload.get('plane_id'):
        model.find(doc,'planes',payload['plane_id']); sketch['plane_id']=payload['plane_id']
    if support_id: sketch['support_id']=support_id
    if payload.get('reference_sketch_id'):
        source=model.find(doc,'sketches',payload['reference_sketch_id'])
        for key in ('plane','offset','plane_id','support_id'):
            if key in source: sketch[key]=source[key]
    doc['sketches'].append(sketch)
    bar = runtime.bar(doc)
    if bar: model.insert_after(doc,sketch,bar)
    model.resolve_supports(doc)
    runtime.enter_sketch(sketch)
    return sketch


@command('cad.sketch.activate')
def sketch_activate(payload):
    runtime.require_workspace()
    if runtime.session:
        runtime.require(payload)
        runtime.cancel()
    doc = runtime.doc()
    sketch = model.find(doc,'sketches',payload.get('sketch_id'))
    _require_reachable(doc,sketch['id'])
    runtime.enter_sketch(sketch)
    return runtime.status()


@command('cad.sketch.rename')
def sketch_rename(payload):
    name=payload.get('name')
    if not isinstance(name,str) or not name.strip() or len(name.strip())>80:
        raise BadPayload('Escribe un nombre de croquis entre 1 y 80 caracteres')
    def change(doc):
        sketch=model.find(doc,'sketches',payload.get('sketch_id'))
        sketch['name']=name.strip()
    return (yield from runtime.transaction_steps(payload,change,'CAD renombrar croquis',geometry=False))


@command('cad.sketch.finish')
def sketch_finish(payload):
    runtime.require_workspace()
    if runtime.session:
        runtime.require(payload)
        runtime.cancel()
    active=runtime.active_sketch_id
    runtime.solid_view()
    doc=runtime.doc()
    sketch=next((s for s in doc['sketches'] if s['id']==active),None)
    profiles=model.profiles(sketch) if sketch else []
    if profiles and not any(f['sketch_id']==active for f in doc['features']):
        runtime.selection=(dict(kind='SKETCH',id=active) if len(profiles)>1 else dict(kind='PROFILE',id=profiles[0]['id']))
    # Leaving a used sketch must not open an unrelated operation's dimensions.
    # Existing operations are inspected only after an explicit selection in 3D.
    else: runtime.selection=None
    return runtime.status()


def _endpoint(payload, sketch, previous=None):
    from .snap import query_sketch_endpoint
    from ..bpy_utils import find_view3d
    found=find_view3d()
    if not found: return None
    return query_sketch_endpoint(runtime.overlay(runtime.doc()),model.number(payload.get('u')),
                                 model.number(payload.get('v')),found[2].width/max(found[2].height,1),previous)


def _on_grid(point):
    if not runtime.increment: return tuple(point)
    return tuple(round(c/runtime.step)*runtime.step for c in point)


def _corner(e, point):
    """Rectangle corner role lying on a drawn point, for its coincidence."""
    return min(geometry.handles(e).items(),key=lambda item:math.dist(item[1],point))[0]


# ISO 54 first-choice modules, in metres.
STANDARD_MODULES = tuple(m/1000 for m in (.1,.2,.25,.3,.4,.5,.6,.8,1,1.25,1.5,2,2.5,3,4,5,6,8,10,12,16,20,25,32,40,50))


@command('cad.entity.begin')
def entity_begin(payload):
    typ = str(payload.get('type','')).upper()
    if typ not in model.TYPES or typ == 'POINT':   # points only come from projection
        raise BadPayload('Tipo de entidad CAD no compatible')
    sketch = model.find(runtime.doc(),'sketches',runtime.active_sketch_id)
    # Drawing follows the same aids as editing: an existing point attracts the
    # start, otherwise Increment places it on the step grid.
    anchor=_endpoint(payload,sketch)
    start=(geometry.point(sketch,dict(id=anchor['entity_id'],part=anchor['part'])) if anchor
           else _on_grid(runtime.point(payload,sketch)))
    sides=payload.get('sides',6)
    if typ=='NGON' and (isinstance(sides,bool) or not isinstance(sides,int) or not model.SIDES[0]<=sides<=model.SIDES[1]):
        raise BadPayload(f'El polígono regular necesita entre {model.SIDES[0]} y {model.SIDES[1]} lados')
    gear=dict(teeth=payload.get('teeth',20),pressure=payload.get('pressure',20.))
    if typ=='GEAR': model.validate_entity(dict(type='GEAR',x=0,y=0,module=1,angle=0,**gear))
    session = runtime.begin(payload,typ)
    session.update(sketch_id=sketch['id'],start=start,entity_id=model.uid('entity'),anchor=anchor,sides=sides,gear=gear)
    return runtime.status()


@command('cad.entity.update')
def entity_update(payload):
    session = runtime.require(payload)
    if session['operation'] not in model.TYPES:
        raise CommandError('La sesión no es de dibujo',code='wrong_tool')
    doc = copy.deepcopy(session['baseline'])
    sketch = model.find(doc,'sketches',session['sketch_id'])
    x,y = session['start']
    x2,y2 = runtime.point(payload,sketch)
    endpoint=(_endpoint(payload,sketch,session.get('endpoint'))
              if session['operation'] in ('LINE','RECTANGLE','SLOT') else None)
    session['endpoint']=endpoint
    if endpoint: x2,y2=geometry.point(sketch,dict(id=endpoint['entity_id'],part=endpoint['part']))
    e = dict(id=session['entity_id'],type=session['operation'],x=x,y=y,construction=runtime.construction)
    if e['type']=='RECTANGLE':
        if not endpoint: x2,y2=x+_on_grid((x2-x,))[0],y+_on_grid((y2-y,))[0]
        e.update(x=min(x,x2),y=min(y,y2),width=abs(x2-x),height=abs(y2-y))
    elif e['type']=='NGON':
        # Center → vertex sets size and rotation; Increment rounds the across-flats size.
        n=session['sides']; circum=math.hypot(x2-x,y2-y)
        e.update(sides=n,flats=_on_grid((2*circum*math.cos(math.pi/n),))[0],angle=math.degrees(math.atan2(y2-y,x2-x)))
    elif e['type']=='SLOT':
        # First cap center → second cap center; Increment rounds the length.
        length=math.hypot(x2-x,y2-y) if endpoint else _on_grid((math.hypot(x2-x,y2-y),))[0]
        angle=math.atan2(y2-y,x2-x)
        width=_on_grid((length*.4,))[0] or runtime.step
        e.update(x=x+math.cos(angle)*length/2,y=y+math.sin(angle)*length/2,length=length,width=width,angle=math.degrees(angle))
    elif e['type']=='GEAR':
        # Center → pitch circle; Increment picks the nearest standard module.
        teeth=session['gear']['teeth']; module=2*math.hypot(x2-x,y2-y)/teeth
        if runtime.increment and module>0:
            module=min(STANDARD_MODULES,key=lambda m:abs(math.log(m/module)))
        e.update(module=module,angle=math.degrees(math.atan2(y2-y,x2-x)),**session['gear'])
    elif e['type'] in ('ARC','CIRCLE'):
        # Increment rounds the radius itself, not the rim position.
        radius=_on_grid((math.hypot(x2-x,y2-y),))[0]
        if e['type']=='ARC':
            e.update(radius=radius,start=math.degrees(math.atan2(y2-y,x2-x)),sweep=90.)
        else:
            e['diameter'] = 2*radius
    else:
        if not endpoint: x2,y2=_on_grid((x2,y2))
        e.update(x2=x2,y2=y2)
    # Returning to the start clears the candidate so a collapsed drag cannot
    # silently confirm an older rectangle.
    try:
        model.validate_entity(e)
    except BadPayload:
        session['preview'] = None
        session['candidate'] = None
        return runtime.status()
    sketch['entities'].append(e)
    roles={'LINE':('START','END'),'CIRCLE':('CENTER',None),'ARC':('CENTER',None),'NGON':('CENTER',None),
           'SLOT':('START','END'),'GEAR':('CENTER',None)}.get(e['type'])
    if e['type']=='RECTANGLE': roles=(_corner(e,(x,y)),_corner(e,(x2,y2)))
    for role,anchor,label in ((roles[0],session.get('anchor'),'START'),(roles[1],endpoint,'END')):
        if anchor:
            sketch.setdefault('constraints',[]).append(dict(id='join_'+e['id']+'_'+label,type='COINCIDENT',
                refs=[dict(id=e['id'],part=role),dict(id=anchor['entity_id'],part=anchor['part'])]))
    session['preview'] = doc
    session['candidate'] = e['id']
    _set_selection([dict(kind='ENTITY',id=e['id'],part='BODY')])
    return runtime.status()


@command('cad.entity.set')
def entity_set(payload):
    changes = payload.get('values')
    if not isinstance(changes,dict) or not changes:
        raise BadPayload('Faltan las dimensiones')
    constrain=payload.get('constrain',False)
    if not isinstance(constrain,bool): raise BadPayload('constrain debe ser booleano')
    equal_ids=payload.get('equal_ids') or []
    if not isinstance(equal_ids,list) or not all(isinstance(i,str) for i in equal_ids): raise BadPayload('equal_ids debe ser una lista de IDs')
    def change(doc):
        sketch, e = model.entity(doc,payload.get('entity_id'))
        if equal_ids:
            # Several selected arcs: the edited radius/angle applies to all of them
            # through equalities, in the same transaction and undo.
            if e['type']!='ARC': raise BadPayload('Aplicar a varios solo está disponible para arcos')
            for identifier in equal_ids:
                if not any(x['id']==identifier for x in sketch['entities']): raise BadPayload('Los arcos deben pertenecer al mismo croquis')
            dimensions.equalize_arcs(sketch,[dict(id=e['id'])]+[dict(id=i) for i in equal_ids])
        from ..cad.offset import rule_for, set_value
        offset_rule=rule_for(sketch,e['id'])
        if offset_rule:
            if set(changes)!={'offset'}: raise BadPayload('Edita solo el grosor del contorno vinculado')
            set_value(sketch,offset_rule,changes['offset'])
            return
        allowed = set(model.FIELDS[e['type']]) | ({'length'} if e['type']=='LINE' else set())
        if e['type']=='CIRCLE': allowed.add('radius')
        if e['type']=='SLOT': allowed.add('radius')
        if e['type']=='NGON': allowed.add('sides')
        if e['type']=='GEAR': allowed.update(('teeth','pressure'))
        if not set(changes)<=allowed:
            raise BadPayload('Dimensión no compatible con la entidad')
        values={k:model.number(v) for k,v in changes.items() if k not in ('sides','teeth','pressure')}
        if 'teeth' in changes or 'pressure' in changes:
            # Discrete: the module is kept, so its dimension follows the new pitch circle.
            e.update({k:changes[k] for k in ('teeth','pressure') if k in changes}); model.validate_entity(e)
            values.setdefault('module',e['module'])
        if 'sides' in changes:
            # Discrete: the across-flats size and constraints are kept.
            e['sides']=changes['sides']; model.validate_entity(e)
            if any(r['id']==e['id'] and r.get('part','').startswith(('P','EDGE')) for c in sketch.get('constraints',[]) for r in c['refs']):
                raise BadPayload('Quita antes las reglas de sus esquinas o lados para cambiar el número de lados')
        if e['type']=='SLOT' and 'radius' in values:
            width=2*model.number(values.pop('radius'),positive=True)
            if 'width' in values and not math.isclose(values['width'],width,rel_tol=1e-9,abs_tol=1e-12):
                raise BadPayload('Radio y ancho deben describir la misma ranura')
            values['width']=width
        if e['type']=='CIRCLE' and 'radius' in values:
            diameter=2*model.number(values.pop('radius'),positive=True)
            if 'diameter' in values and not math.isclose(values['diameter'],diameter,rel_tol=1e-9,abs_tol=1e-12):
                raise BadPayload('Radio y diámetro deben describir el mismo círculo')
            values['diameter']=diameter
        goals=dimensions.set_values(sketch,e,values)
        if constrain: dimensions.constrain_values(sketch,e,changes)
        geometry.solve(sketch,goals)
    return (yield from runtime.transaction_steps(payload,change,'CAD editar dimensiones'))


@command('cad.entity.construction')
def entity_construction(payload):
    value=payload.get('construction')
    if not isinstance(value,bool): raise BadPayload('construction debe ser booleano')
    def change(doc):
        sketch=model.find(doc,'sketches',runtime.active_sketch_id)
        refs=[r for r in _refs() if r['kind']=='ENTITY' and r['id']!='ORIGIN']
        if not refs: raise BadPayload('Selecciona geometría del boceto')
        for ref in refs: geometry.get_entity(sketch,ref)['construction']=value
    return (yield from runtime.transaction_steps(payload,change,'CAD geometría de construcción'))


@command('cad.entity.offset')
def entity_offset(payload):
    created=[]
    def change(doc):
        from ..cad import offset
        sketch=model.find(doc,'sketches',runtime.active_sketch_id)
        source=model.find(sketch,'entities',payload.get('entity_id'))
        rule=dict(id=model.uid('constraint'),type='OFFSET',value=model.number(payload.get('thickness'),positive=True),
                  side=payload.get('side','OUTWARD'),refs=[])
        entity=offset.shape(source,offset.distance(rule))
        entity={k:v for k,v in entity.items() if k in model.FIELDS[source['type']] or k=='type'}
        entity.update(id=model.uid('entity'),construction=False)
        model.validate_entity(entity)
        rule['refs']=[dict(id=source['id'],part='BODY'),dict(id=entity['id'],part='BODY')]
        sketch['entities'].append(entity);sketch['constraints'].append(rule)
        geometry.solve(sketch)
        created.append(entity['id'])
    yield from runtime.transaction_steps(payload,change,'CAD desfase de contorno')
    _set_selection([dict(kind='ENTITY',id=created[0],part='BODY')])
    return runtime.status()


def _preview_endpoint(payload, preview, previous=None):
    from .snap import query_sketch_endpoint
    from ..bpy_utils import find_view3d
    found=find_view3d()
    if not found: return None
    return query_sketch_endpoint(runtime.overlay(preview),model.number(payload.get('u')),
                                 model.number(payload.get('v')),found[2].width/max(found[2].height,1),previous)


def _polygon_join(previous_id, segment_id):
    return dict(id='join_'+segment_id+'_START',type='COINCIDENT',
                refs=[dict(id=previous_id,part='END'),dict(id=segment_id,part='START')])


def _polygon_closing(session, segment):
    """The last side ends on the first vertex: persist it, or the corner splits."""
    first=session['segments'][0][0]['id']
    return dict(id='join_'+segment['id']+'_END',type='COINCIDENT',
                refs=[dict(id=segment['id'],part='END'),dict(id=first,part='START')])


def _polygon_state(session, current=None):
    """Baseline + committed segments (+ provisional tail) as a preview document."""
    doc=copy.deepcopy(session['baseline'])
    sketch=model.find(doc,'sketches',session['sketch_id'])
    for segment,*joins in session['segments']:
        sketch['entities'].append(copy.deepcopy(segment))
        sketch['constraints'].extend(copy.deepcopy(join) for join in joins if join)
    if current is not None and session['points']:
        start=session['points'][-1]
        if math.dist(start,current)>=1e-7:
            sketch['entities'].append(dict(id=session['temp_id'],type='LINE',x=start[0],y=start[1],
                x2=current[0],y2=current[1],construction=runtime.construction))
    session['can_close']=len(session['points'])>=3
    return doc,sketch


@command('cad.polygon.begin')
def polygon_begin(payload):
    runtime.require_workspace()
    if not runtime.active_sketch_id: raise BadPayload('Abre un boceto para dibujar')
    session=runtime.session
    if session and (session['operation']!='POLYGON' or session['owner']!=payload.get('_client_id')):
        runtime.require(payload); runtime.cancel(); session=None
    if session is None:
        doc=runtime.doc()
        sketch=model.find(doc,'sketches',runtime.active_sketch_id)
        anchor=_endpoint(payload,sketch)
        start=geometry.point(sketch,dict(id=anchor['entity_id'],part=anchor['part'])) if anchor else runtime.point(payload,sketch)
        session=runtime.begin(payload,'POLYGON')
        session.update(sketch_id=sketch['id'],points=[start],segments=[],temp_id=model.uid('entity'),
                       can_close=False,provisional=None,anchor=None,start_anchor=anchor)
    return runtime.status()


@command('cad.polygon.update')
def polygon_update(payload):
    session=runtime.require(payload)
    if session['operation']!='POLYGON': raise CommandError('La sesión no es un polígono',code='wrong_tool')
    doc,sketch=_polygon_state(session,None)
    anchor=_preview_endpoint(payload,doc,session.get('anchor'))
    session['anchor']=anchor
    current=geometry.point(sketch,dict(id=anchor['entity_id'],part=anchor['part'])) if anchor else runtime.point(payload,sketch)
    doc,_=_polygon_state(session,current)
    session['provisional']=current
    session['preview']=doc
    return runtime.status()


@command('cad.polygon.segment')
def polygon_segment(payload):
    session=runtime.require(payload)
    if session['operation']!='POLYGON': raise CommandError('La sesión no es un polígono',code='wrong_tool')
    doc,sketch=_polygon_state(session,None)
    session['preview']=doc
    current=session.get('provisional')
    anchor=session.get('anchor')
    if current is None:
        anchor=_preview_endpoint(payload,doc,session.get('anchor'))
        current=geometry.point(sketch,dict(id=anchor['entity_id'],part=anchor['part'])) if anchor else runtime.point(payload,sketch)
    session['provisional']=None
    if math.dist(current,session['points'][-1])<1e-7:
        return runtime.status()  # a tap on the last vertex commits nothing
    closes=math.dist(current,session['points'][0])<1e-9 or (
        anchor is not None and session['segments']
        and anchor['entity_id']==session['segments'][0][0]['id'] and anchor['part']=='START')
    if closes and len(session['points'])<3:
        return runtime.status()  # two vertices cannot enclose a profile
    segment=dict(id=model.uid('entity'),type='LINE',x=session['points'][-1][0],y=session['points'][-1][1],
                 x2=current[0],y2=current[1],construction=runtime.construction)
    try:
        model.validate_entity(segment)
    except BadPayload:
        return runtime.status()
    if session['segments']:
        join=_polygon_join(session['segments'][-1][0]['id'],segment['id'])
    else:
        # A chain started on an existing point stays attached to it.
        start=session.get('start_anchor')
        join=start and dict(id='join_'+segment['id']+'_START',type='COINCIDENT',
                            refs=[dict(id=segment['id'],part='START'),dict(id=start['entity_id'],part=start['part'])])
    session['segments'].append((segment,join,_polygon_closing(session,segment) if closes else None))
    if closes:
        session['points'].append(tuple(session['points'][0]))
        doc,_=_polygon_state(session,None)
        yield from _polygon_confirm(session,doc)
        return runtime.status()
    session['points'].append(current)
    # Publish the released side and its new vertex now: the close button must
    # become available after two sides, without waiting for another stroke.
    session['preview'],_=_polygon_state(session,None)
    _set_selection([dict(kind='ENTITY',id=segment['id'],part='BODY')])
    return runtime.status()


@command('cad.polygon.close')
def polygon_close(payload):
    session=runtime.require(payload)
    if session['operation']!='POLYGON': raise CommandError('La sesión no es un polígono',code='wrong_tool')
    if len(session['points'])<3: raise BadPayload('El polígono necesita al menos tres vértices')
    doc,sketch=_polygon_state(session,None)
    first=tuple(session['points'][0])
    if math.dist(session['points'][-1],first)>1e-9:
        segment=dict(id=model.uid('entity'),type='LINE',x=session['points'][-1][0],y=session['points'][-1][1],
                     x2=first[0],y2=first[1],construction=runtime.construction)
        model.validate_entity(segment)
        session['segments'].append((segment,_polygon_join(session['segments'][-1][0]['id'],segment['id']),
                                    _polygon_closing(session,segment)))
        session['points'].append(first)
        doc,_=_polygon_state(session,None)
    yield from _polygon_confirm(session,doc)
    return runtime.status()


def _polygon_confirm(session, doc):
    yield from runtime.rebuild_steps(doc,limit=runtime.bar(doc))
    runtime.persist(doc,advance=True)
    runtime.session=None
    sketch=model.find(doc,'sketches',session['sketch_id'])
    members={segment['id'] for segment,*_ in session['segments']}
    profile=next(('profile_'+p['id'] for p in model.closed_entities(sketch)
                  if not any(e.get('construction') for e in sketch['entities'] if e['id'] in members)
                  and set(p.get('members',[]))==members),None)
    runtime.selection=dict(kind='PROFILE',id=profile) if profile else dict(kind='ENTITY',id=session['segments'][-1][0]['id'],part='BODY')
    with runtime.saving():
        undo_push('CAD polígono')


@command('cad.sketch.visibility')
def sketch_visibility(payload):
    value=payload.get('visible')
    if not isinstance(value,bool): raise BadPayload('visible debe ser booleano')
    def change(doc):
        sketch=model.find(doc,'sketches',payload.get('sketch_id'))
        _require_reachable(doc,sketch['id'])
        sketch['visible']=value; sketch['visibility_explicit']=True
    return (yield from runtime.transaction_steps(payload,change,'CAD visibilidad de boceto'))


@command('cad.entity.delete')
def entity_delete(payload):
    selection=copy.deepcopy(_refs())
    if runtime.session:
        runtime.require(payload); runtime.cancel()
    def change(doc):
        if payload.get('entity_id'):
            sketch,e=model.entity(doc,payload['entity_id'])
            refs=[dict(id=e['id'],part='BODY')]
        else:
            sketch=model.find(doc,'sketches',runtime.active_sketch_id)
            refs=[r for r in selection if r.get('kind')=='ENTITY' and r['id']!='ORIGIN']
        if not refs: raise BadPayload('Selecciona dibujos, puntos o aristas; el origen no se borra')
        removed={r['id'] for r in refs}
        if any(c['type']=='OFFSET' and c['refs'][0]['id'] in removed and c['refs'][1]['id'] not in removed
               for c in sketch.get('constraints',[])):
            raise CommandError('El contorno tiene un desfase dependiente; elimina primero su desfase',code='cad_dependency')
        geometry.delete_selected(sketch,refs)
        for feature in doc['features']:
            for sketch_key,profile_key in (('sketch_id','profile_id'),('to_sketch_id','to_profile_id')):
                if feature.get(sketch_key)!=sketch['id']: continue
                try: model.profile(doc,feature[profile_key])
                except CommandError as exc:
                    raise CommandError('El borrado abriría un perfil utilizado; elimina primero su operación CAD',code='cad_dependency') from exc
            if feature.get('type')=='HELIX' and feature['sketch_id']==sketch['id'] and feature['axis'] not in ('X','Y') and \
                    not any(e['id']==feature['axis'] for e in sketch['entities']):
                raise CommandError('Esa línea es el eje de un barrido helicoidal; cambia antes su eje',code='cad_dependency')
    yield from runtime.transaction_steps(payload,change,'CAD borrar selección')
    runtime.selection=None
    return runtime.status()


def direction_labels(normal):
    """World names for positive and negative depth along the sketch normal."""
    axis = max(range(3), key=lambda i: abs(normal[i]))
    pairs = (('Derecha', 'Izquierda'), ('Atrás', 'Adelante'), ('Arriba', 'Abajo'))
    positive, negative = pairs[axis]
    if normal[axis] < 0:
        positive, negative = negative, positive
    return positive, negative


def _normal_travel(sketch, source, start, end):
    """Metres along the sketch normal between two pen positions, or None if edge-on."""
    basis = model.frame(sketch)
    try:
        ring = model.outline(source)
        cx, cy = sum(p[0] for p in ring)/len(ring), sum(p[1] for p in ring)/len(ring)
    except Exception:
        cx = cy = 0.
    anchor = [basis['origin'][i]+cx*basis['x'][i]+cy*basis['y'][i] for i in range(3)]
    return _travel_along(anchor, basis['normal'], start, end)


def _travel_along(anchor, normal, start, end):
    """Metres along the line anchor+t·normal between two pen positions.

    Each pen ray is intersected (closest point) with that line, so what moves stays
    under the tip at any zoom or perspective. None when the line points at the camera.
    """
    from ..bpy_utils import find_view3d
    from ..camera import camera
    from mathutils import Vector
    found = find_view3d()
    if found is None:
        return None
    rv3d = found[3]
    camera.sync_from_region(rv3d)
    scale = max(float(bpy.context.scene.unit_settings.scale_length), 1e-12)
    anchor = Vector(anchor) / scale
    normal = Vector(normal).normalized()
    def parameter(u, v):
        origin, direction = camera.ray(u, v, rv3d)
        direction = direction.normalized()
        b = normal.dot(direction)
        denominator = 1. - b*b
        if denominator < 1e-4:  # The normal points at the camera: no 1:1 reading.
            return None
        w = anchor - origin
        return (b*direction.dot(w) - normal.dot(w)) / denominator
    first, last = parameter(*start), parameter(*end)
    if first is None or last is None:
        return None
    return (last - first) * scale


def _screen_axis(sketch):
    """Unit screen direction of the sketch normal. v grows downward."""
    from ..bpy_utils import find_view3d
    from ..camera import camera
    from mathutils import Vector
    found = find_view3d()
    if found is None:
        return 0.0, -1.0
    rv3d = found[3]
    camera.sync_from_region(rv3d)
    scale = max(float(bpy.context.scene.unit_settings.scale_length), 1e-12)
    basis = model.frame(sketch)
    origin = Vector(basis['origin']) / scale
    tip = origin + Vector(basis['normal']) / scale
    start = camera.project(origin, rv3d)
    end = camera.project(tip, rv3d)
    if not start or not end:
        return 0.0, -1.0
    sx, sy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(sx, sy)
    if length < .02:
        return 0.0, -1.0
    return sx / length, sy / length


def _depth_value(session, payload):
    """Signed extrude depth, or a positive cut depth. Gesture may cross zero."""
    cut = session['operation'] == 'CUT'
    if payload.get('settle'):
        depth = session['depth']
        if runtime.increment:
            snapped = max(runtime.step, round(abs(depth) / runtime.step) * runtime.step)
            depth = max(snapped, 1e-7) if cut else math.copysign(snapped, depth or 1)
        return depth
    if 'gesture_u' in payload or 'gesture_v' in payload or 'gesture' in payload:
        if 'gesture_u' in payload or 'gesture_v' in payload:
            sketch, source = model.profile(session['preview'], model.find(session['preview'], 'features', session['feature_id'])['profile_id'])
            gu, gv = model.number(payload.get('gesture_u', 0)), model.number(payload.get('gesture_v', 0))
            along = None
            if 'u' in payload and 'v' in payload:
                # The pen tip follows the profile's normal 1:1, also in perspective.
                u, v = model.number(payload['u']), model.number(payload['v'])
                along = _normal_travel(sketch, source, (u-gu, v-gv), (u, v))
            if along is None:
                sx, sy = _screen_axis(sketch)
                along = (gu * sx + gv * sy) / .04 * runtime.step
            distance = -along if cut else along
            if runtime.increment:
                # Whole steps while drawing: 1 mm of pen is 1 mm of depth, in 1 mm jumps.
                base = model.number(payload.get('baseline_depth', session['depth']), positive=cut)
                distance = round((base + distance) / runtime.step) * runtime.step - base
        else:
            distance = model.number(payload['gesture']) / .04 * runtime.step
            if runtime.increment:
                distance = round(distance / runtime.step) * runtime.step
        base = model.number(payload.get('baseline_depth', session['depth']), positive=cut)
        depth = base + distance
    elif 'depth' in payload:
        depth = model.number(payload.get('depth'), positive=cut)
    else:
        depth = session['depth']
    if cut:
        return max(1e-7, depth)
    if abs(depth) < 1e-7:
        return math.copysign(1e-7, depth or 1)
    return depth


def _extent(value):
    value=str(value or 'ONE').upper()
    if value not in ('ONE','BOTH'):
        raise BadPayload('La extensión debe ser una dirección o dos')
    return value


@command('cad.extrude.begin')
def extrude_begin(payload):
    depth = model.number(payload.get('depth',.02),positive=True)
    doc = runtime.doc()
    profile_id = 'profile_' + str(payload['sketch_id']) if payload.get('sketch_id') else payload.get('profile_id')
    sketch,e = model.profile(doc,profile_id)
    _require_reachable(doc,sketch['id'])
    operation=str(payload.get('operation','EXTRUDE')).upper()
    if operation not in ('EXTRUDE','CUT'): raise BadPayload('Operación CAD no compatible')
    extent=_extent(payload.get('extent','ONE'))
    target=None
    if operation=='CUT':
        target=model.find(doc,'features',payload.get('target_id'))
        if not target['enabled']: raise BadPayload('El sólido destino está desactivado')
    bar = runtime.bar(doc)
    session = runtime.begin(payload,operation)
    from ..cad.kernel import ExtrusionPreviewCache
    session['extrusion_cache'] = ExtrusionPreviewCache()
    feature = dict(id=model.uid('feature'),name=('Vaciado ' if operation=='CUT' else 'Extrusión ')+str(len(doc['features'])+1),
                   type=operation,order=model.next_order(doc),sketch_id=sketch['id'],profile_id='profile_'+e['id'],depth=depth,enabled=True,body_id=target['body_id'] if target else sketch['body_id'])
    feature['extent']=extent
    if target: feature['target_id']=target['id']
    preview = copy.deepcopy(session['baseline'])
    preview['features'].append(feature)
    if bar: model.insert_after(preview,feature,bar)
    try:
        yield from runtime.rebuild_steps(preview,limit=feature['id'] if bar else None,extrusion_cache=session['extrusion_cache'])
    except Exception:
        runtime.session = None
        raise
    session.update(feature_id=feature['id'],preview=preview,candidate=feature['id'],depth=depth,extent=extent,at_bar=bool(bar))
    runtime.selection = dict(kind='FEATURE',id=feature['id'])
    runtime.solid_view()
    return runtime.status()


def _loft_profile(doc, payload, prefix):
    sketch_id=payload.get(prefix+'_sketch_id')
    identifier='profile_'+str(sketch_id) if sketch_id else payload.get(prefix+'_profile_id')
    sketch,e=model.profile(doc,identifier)
    _require_reachable(doc,sketch['id'])
    if e['type']=='SKETCH':
        closed=model.closed_entities(sketch)
        if len(closed)!=1: raise BadPayload(sketch['name']+' tiene varios contornos; elige uno de sus perfiles')
        e=closed[0]
    return sketch,'profile_'+e['id']


@command('cad.loft.create')
def loft_create(payload):
    """Solid transition between one closed contour of each of two sketches; one undo."""
    def change(doc):
        first,source=_loft_profile(doc,payload,'from'); second,target=_loft_profile(doc,payload,'to')
        if first['id']==second['id']: raise BadPayload('Elige perfiles de dos croquis distintos')
        feature=dict(id=model.uid('feature'),name='Solevado '+str(len(doc['features'])+1),type='LOFT',order=model.next_order(doc),
                     sketch_id=first['id'],profile_id=source,to_sketch_id=second['id'],to_profile_id=target,
                     enabled=True,body_id=first['body_id'])
        doc['features'].append(feature)
        bar=runtime.bar(doc)
        if bar:
            model.insert_after(doc,feature,bar)
            runtime.rollback_id=feature['id']  # a node inserted at the bar becomes the viewed state
        created.append(feature['id'])
    created=[]
    yield from runtime.transaction_steps(payload,change,'CAD solevado')
    runtime.selection=dict(kind='FEATURE',id=created[0])
    return runtime.status()


def _helix_axis(sketch, axis):
    if axis in ('X','Y'): return axis
    if not any(e['id']==axis and e['type']=='LINE' for e in sketch['entities']):
        raise BadPayload('El eje debe ser X, Y o una línea del mismo croquis')
    return axis


@command('cad.helix.create')
def helix_create(payload):
    """Helical sweep of one closed contour around an axis of its sketch; one undo."""
    from ..cad.kernel import helix_axis
    def change(doc):
        sketch,identifier=_loft_profile(doc,dict(from_sketch_id=payload.get('sketch_id'),from_profile_id=payload.get('profile_id')),'from')
        _,source=model.profile(doc,identifier)
        ring=model.outline(source)
        axis=payload.get('axis')
        if axis is None:
            # The first sketch axis the profile does not cross, so a fresh sweep works.
            def clear(name):
                (ax,ay),(dx,dy)=helix_axis(sketch,name)
                side=[-(x-ax)*dy+(y-ay)*dx for x,y in ring]
                return min(side)>1e-9 or max(side)<-1e-9
            axis=next((name for name in ('Y','X') if clear(name)),'Y')
        axis=_helix_axis(sketch,axis)
        (ax,ay),(dx,dy)=helix_axis(sketch,axis)
        heights=[(x-ax)*dx+(y-ay)*dy for x,y in ring]
        span=max(heights)-min(heights)
        pitch=payload.get('pitch') or max(span*1.25,span+runtime.step)
        feature=model.validate_helix(dict(id=model.uid('feature'),name='Barrido helicoidal '+str(len(doc['features'])+1),type='HELIX',
            order=model.next_order(doc),sketch_id=sketch['id'],profile_id=identifier,enabled=True,body_id=sketch['body_id'],
            axis=axis,pitch=pitch,turns=payload.get('turns',5),hand=payload.get('hand','RIGHT')))
        doc['features'].append(feature)
        bar=runtime.bar(doc)
        if bar:
            model.insert_after(doc,feature,bar)
            runtime.rollback_id=feature['id']
        created.append(feature['id'])
    created=[]
    yield from runtime.transaction_steps(payload,change,'CAD barrido helicoidal')
    runtime.selection=dict(kind='FEATURE',id=created[0])
    return runtime.status()


@command('cad.extrude.update')
def extrude_update(payload):
    session = runtime.require(payload)
    if session['operation'] not in ('EXTRUDE','CUT'):
        raise CommandError('La sesión no es una extrusión',code='wrong_tool')
    if 'extent' in payload and session['operation'] not in ('EXTRUDE','CUT'):
        raise BadPayload('Solo extruir o vaciar eligen una dirección o dos')
    extent=_extent(payload['extent']) if 'extent' in payload else session.get('extent','ONE')
    stylus = 'gesture_u' in payload or 'gesture_v' in payload
    settle = bool(payload.get('settle'))
    depth = _depth_value(session, payload)
    if not settle and depth == session['depth'] and extent == session.get('extent','ONE'):
        return runtime.status()
    preview = copy.deepcopy(session['preview'])
    feature=model.find(preview,'features',session['feature_id'])
    feature['depth'] = depth
    feature['extent']=extent
    if feature['type']=='EXTRUDE' and extent=='BOTH':
        feature['depth']=abs(feature['depth'])
    if stylus and not settle:
        previous = dict(preview=session['preview'], depth=session['depth'], extent=session.get('extent', 'ONE'))
        session.update(preview=preview,depth=depth,extent=extent)
        try:
            runtime.fast_depth(session)
            return runtime.status()
        except CommandError:
            session.update(previous)
            runtime.drop_prisms()
    yield from runtime.rebuild_steps(preview,limit=session['feature_id'] if session.get('at_bar') else None,
                    extrusion_cache=session['extrusion_cache'])
    session.update(preview=preview,depth=depth,extent=extent)
    return runtime.status()


def _finish_edges():
    """Selected solid edges as design segments in metres, with their body."""
    runtime.surface.validate()
    items=[i for i in runtime.surface.items if i['kind']=='EDGE']
    if not items or len(items)!=len(runtime.surface.items):
        raise BadPayload('Selecciona una o varias aristas del sólido (Aristas)')
    obj=bpy.data.objects.get(items[0]['object'])
    body=obj.get(BODY_KEY) if obj else None
    if not body or any(i['object']!=items[0]['object'] for i in items):
        raise BadPayload('Las aristas deben pertenecer a una misma pieza CAD')
    from mathutils import Vector
    inverse=obj.matrix_world.inverted_safe(); scale=bpy.context.scene.unit_settings.scale_length
    edges=[[[list(inverse@Vector(p)*scale) for p in segment] for segment in item['segments']] for item in items]
    return body,edges


def _finish_step(payload, session):
    width=session['width']
    if 'gesture' in payload:
        distance=model.number(payload['gesture'])/.04*runtime.step
        if runtime.increment: distance=round(distance/runtime.step)*runtime.step
        width=max(1e-7,model.number(payload.get('baseline_width',session['width']),positive=True)+distance)
    elif 'width' in payload: width=model.number(payload['width'],positive=True)
    return width


@command('cad.finish.begin')
def finish_begin(payload):
    """Fillet/chamfer the selected solid edges as a new operation of their body."""
    operation=str(payload.get('operation','FILLET')).upper()
    if operation not in model.FINISHES: raise BadPayload('Operación CAD no compatible')
    body,edges=_finish_edges()
    doc=runtime.doc()
    segments=1 if operation=='CHAMFER' else payload.get('segments',4)
    feature=model.validate_finish(dict(id=model.uid('feature'),type=operation,order=model.next_order(doc),
        name=('Chaflán ' if operation=='CHAMFER' else 'Redondeo ')+str(len(doc['features'])+1),
        sketch_id=None,body_id=body,enabled=True,edges=edges,segments=segments,
        width=model.number(payload.get('width',runtime.step),positive=True)))
    bar=runtime.bar(doc)
    session=runtime.begin(payload,operation)
    preview=copy.deepcopy(session['baseline']); preview['features'].append(feature)
    if bar: model.insert_after(preview,feature,bar)
    try:
        yield from runtime.rebuild_steps(preview,limit=feature['id'] if bar else None)
    except Exception:
        runtime.session=None
        raise
    session.update(feature_id=feature['id'],preview=preview,candidate=feature['id'],width=feature['width'],
                   segments=feature['segments'],at_bar=bool(bar))
    runtime.surface.clear()
    runtime.selection=dict(kind='FEATURE',id=feature['id'])
    return runtime.status()


@command('cad.finish.update')
def finish_update(payload):
    session=runtime.require(payload)
    if session['operation'] not in model.FINISHES: raise CommandError('La sesión no es un redondeo',code='wrong_tool')
    width=_finish_step(payload,session)
    segments=payload.get('segments',session['segments'])
    if width==session['width'] and segments==session['segments']: return runtime.status()
    preview=copy.deepcopy(session['preview'])
    feature=model.find(preview,'features',session['feature_id'])
    feature.update(width=width,segments=segments); model.validate_finish(feature)
    yield from runtime.rebuild_steps(preview,limit=session['feature_id'] if session.get('at_bar') else None)
    session.update(preview=preview,width=width,segments=segments)
    return runtime.status()


@command('cad.session.confirm')
def confirm(payload):
    session = runtime.require(payload)
    if not session['candidate']:
        runtime.cancel()
        return runtime.status()
    doc = session['preview']
    if session['operation'] == 'PLANE':
        runtime.session = None
        yield from runtime.commit_steps(doc, 'CAD plano', geometry=False)
        target = model.find(doc,'sketches',session['sketch_id']) if session.get('sketch_id') else (
            model.find(doc,'sketches',runtime.active_sketch_id) if runtime.active_sketch_id else None)
        if target is not None:
            if session.get('sketch_id'): runtime.enter_sketch(target)
            else: runtime.focus(target)
        return runtime.status()
    if session.get('at_bar'):
        # A node inserted at the bar becomes the viewed state immediately.
        runtime.rollback_id = session['feature_id']
    if not session.get('annotation_id'):
        yield from runtime.rebuild_steps(doc, limit=runtime.bar(doc), extrusion_cache=session.get('extrusion_cache'))
    runtime.persist(doc, advance=True)
    runtime.session = None
    if session['operation'] in ('EXTRUDE','CUT'):
        _activate_feature(doc, session['feature_id'])
    with runtime.saving():
        undo_push('CAD '+session['operation'].lower())
    return runtime.status()


@command('cad.session.cancel')
def cancel(payload):
    if runtime.session:
        runtime.require(payload)
        runtime.cancel()
    return runtime.status()


@command('cad.feature.set')
def feature_set(payload):
    def change(doc):
        feature = model.find(doc,'features',payload.get('feature_id'))
        _require_reachable(doc,feature['id'])
        if feature.get('mirror'):
            if 'depth' in payload or 'extent' in payload:
                raise BadPayload('La simetría hereda la profundidad de su operación fuente')
            for key in ('plane','offset'):
                if key in payload: feature['mirror'][key]=payload[key]
            model.resolve_supports(doc)
        if feature['type'] in model.FINISHES:
            if 'width' in payload: feature['width']=payload['width']
            if 'segments' in payload: feature['segments']=payload['segments']
            model.validate_finish(feature)
        if feature['type']=='HELIX':
            for key in ('pitch','turns','hand'):
                if key in payload: feature[key]=payload[key]
            if 'axis' in payload: feature['axis']=_helix_axis(model.find(doc,'sketches',feature['sketch_id']),payload['axis'])
            model.validate_helix(feature)
        if 'depth' in payload:
            if feature['type'] not in ('EXTRUDE','CUT'): raise BadPayload('Esta operación no tiene profundidad')
            feature['depth'] = _depth_value(dict(operation=feature['type'], depth=feature['depth'], preview=doc), dict(depth=payload['depth']))
        if 'extent' in payload:
            if feature['type'] not in ('EXTRUDE','CUT'):
                raise BadPayload('Solo extruir o vaciar eligen una dirección o dos')
            feature['extent']=_extent(payload['extent'])
        if 'enabled' in payload:
            if not isinstance(payload['enabled'],bool):
                raise BadPayload('enabled debe ser booleano')
            feature['enabled'] = payload['enabled']
    return (yield from runtime.transaction_steps(payload,change,'CAD editar extrusión'))


@command('cad.feature.mirror')
def feature_mirror(payload):
    created=[];old_bar=runtime.rollback_id
    def change(doc):
        source=model.find(doc,'features',payload.get('feature_id'))
        _require_reachable(doc,source['id'])
        if source['type'] not in ('EXTRUDE','CUT') or source.get('mirror'):
            raise BadPayload('Selecciona una extrusión o vaciado original')
        if not source['enabled']: raise BadPayload('Activa la operación antes de crear su simetría')
        feature=copy.deepcopy(source)
        feature.update(id=model.uid('feature'),name='Simetría de '+source['name'],type='MIRROR',operation=source['type'],order=model.next_order(doc),
                       mirror=dict(source_id=source['id'],plane=payload.get('plane','XZ'),offset=payload.get('offset',0.)))
        doc['features'].append(feature)
        bar=runtime.bar(doc)
        if bar:
            model.insert_after(doc,feature,bar);runtime.rollback_id=feature['id']
        model.resolve_supports(doc);created.append(feature['id'])
    try:
        yield from runtime.transaction_steps(payload,change,'CAD simetría de operación')
    except BaseException:
        runtime.rollback_id=old_bar
        raise
    runtime.selection=dict(kind='FEATURE',id=created[0])
    _activate_feature(runtime.doc(),created[0])
    return runtime.status()


@command('cad.feature.delete')
def feature_delete(payload):
    def change(doc):
        feature=model.find(doc,'features',payload.get('feature_id'))
        _require_reachable(doc,feature['id'])
        _require_no_dependents(doc,feature['id'])
        doc['features'].remove(feature)
    yield from runtime.transaction_steps(payload,change,'CAD eliminar extrusión')
    runtime.selection = None
    return runtime.status()


@command('cad.convert')
def convert(payload):
    runtime.require_workspace()
    if runtime.session:
        raise CommandError('Confirma o cancela antes de convertir',code='session_active')
    doc = runtime.doc()
    if any(not obj.get(BODY_KEY) for obj in runtime.objects(doc)):
        yield from runtime.rebuild_steps(doc,limit=runtime.bar(doc))
    if payload.get('body_id'):
        body=model.find(doc,'bodies',payload['body_id'])['id']
    else:
        feature=model.find(doc,'features',payload.get('feature_id'))
        _require_reachable(doc,feature['id']);body=feature['body_id']
    objs = [o for o in runtime.objects(doc) if o.get(BODY_KEY)==body and not o.hide_viewport]
    if not objs:
        raise CommandError('Activa la operación antes de crear su malla',code='cad_reference_missing')
    copies=[]
    from ..cad.runtime import mesh_copy, archive_copy_sources
    for obj in objs:
        mesh=mesh_copy(obj)
        bpy.context.scene.collection.objects.link(mesh)
        copies.append(mesh)
    # Export a snapshot for Edit while retaining the entire parametric document.
    runtime.leave()
    archive_copy_sources(objs)
    for obj in bpy.context.view_layer.objects: obj.select_set(False)
    for obj in copies: obj.select_set(True)
    bpy.context.view_layer.objects.active=copies[-1]
    undo_push('CAD crear copia de malla')
    runtime.selection = None
    return runtime.status()


def _require_no_dependents(doc, identifier):
    if any(f.get('mirror',{}).get('source_id')==identifier for f in doc['features']):
        raise CommandError('La operación tiene una simetría dependiente',code='cad_dependency')
    if any(f.get('target_id')==identifier for f in doc['features']) or any(s.get('support_id')==identifier for s in doc['sketches']) or any(p.get('support_id')==identifier for p in doc.get('planes',[])):
        raise CommandError('El sólido tiene bocetos o vaciados dependientes',code='cad_dependency')


def _refs():
    selection=runtime.selection or {}
    return selection.get('items',[selection] if selection else [])


def _pick(payload):
    u,v=model.number(payload.get('u')),model.number(payload.get('v'))
    from ..bpy_utils import find_view3d
    found=find_view3d()
    aspect=found[2].width/max(found[2].height,1) if found else 1.
    from .snap import query_sketch_annotation
    overlay=runtime.overlay(runtime.doc())
    annotation=query_sketch_annotation(overlay,u,v,aspect)
    if runtime.active_sketch_id and annotation: return annotation
    candidates=[]
    for item in overlay:
        if item.get('kind') in ('DIMENSION','CONSTRAINT'): continue
        ring=item['points']
        if runtime.active_sketch_id:
            for handle in item.get('handles',[]):
                p=handle['point']; distance=math.hypot((u-p[0])*aspect,v-p[1])
                if distance<.024:
                    ref=dict(kind='ENTITY',id=item['id'],part=handle['part'])
                    if handle.get('intent')=='ANGLE': ref['intent']='ANGLE'
                    candidates.append((0,distance+(1e-8 if item['id']=='ORIGIN' else 0),ref))
        elif item['closed'] and model.contains(ring,(u,v)):
            area=abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(ring,ring[1:]+ring[:1])))
            candidates.append((0,area,dict(kind='PROFILE',id='profile_'+item['id'])))
        for index,(a,b) in enumerate(zip(ring,ring[1:]+(ring[:1] if item['closed'] else []))):
            dx,dy=(b[0]-a[0])*aspect,b[1]-a[1]
            t=max(0,min(1,((u-a[0])*aspect*dx+(v-a[1])*dy)/max(dx*dx+dy*dy,1e-20)))
            distance=math.hypot((u-a[0])*aspect-t*dx,v-a[1]-t*dy)
            if distance<.024 and runtime.active_sketch_id:
                _,e=model.entity(runtime.doc(),item['id'])
                part='EDGE'+str(index) if e['type'] in ('RECTANGLE','NGON') else 'BODY'
                candidates.append((1,distance,dict(kind='ENTITY',id=item['id'],part=part)))
    return min(candidates,key=lambda c:c[:2])[2] if candidates else (
        query_sketch_annotation(overlay,u,v,aspect,labels_only=False) if runtime.active_sketch_id else None)


def _set_selection(refs):
    runtime.selection=dict(refs[-1],items=refs) if refs else None


def _covers(selected, hit):
    if selected['id']!=hit['id']: return False
    part=selected.get('part','BODY'); target=hit.get('part','BODY')
    if part=='BODY' or part==target: return True
    if part.startswith('EDGE') and target.startswith('P'):
        index=int(part[4:])
        try: count=model.entity(runtime.doc(),selected['id'])[1].get('sides',4)
        except CommandError: count=4
        return target in ('P'+str(index),'P'+str((index+1)%count))
    return False


def _toggle_refs(refs, hit):
    if hit is None: return []
    if hit.get('kind')=='CONSTRAINT': return [hit]
    # A finished polygon keeps its profile selected for extrusion. Picking a
    # sketch side enters element selection; the profile is not another element.
    if hit.get('kind')=='ENTITY': refs=[r for r in refs if r.get('kind')=='ENTITY']
    if any(_covers(r,hit) for r in refs):
        return [r for r in refs if not _covers(r,hit)]
    return [r for r in refs if not _covers(hit,r)]+[hit]


@command('cad.select_all')
def select_all(payload):
    runtime.require_workspace()
    if runtime.session:
        runtime.require(payload); runtime.cancel()
    action=payload.get('action','SELECT')
    if action not in ('SELECT','DESELECT'): raise BadPayload('action: SELECT o DESELECT')
    doc = runtime.doc()
    if action == 'DESELECT':
        _set_selection([])
    else:
        sketch=model.find(doc,'sketches',runtime.active_sketch_id or payload.get('sketch_id'))
        if runtime.active_sketch_id:
            _set_selection([dict(kind='ENTITY',id=e['id'],part='BODY') for e in sketch['entities']])
        else:
            _require_reachable(doc, sketch['id'])
            _set_selection([dict(kind='SKETCH',id=sketch['id'])])
    return runtime.status()


@command('cad.select')
def select(payload):
    runtime.require_workspace()
    if runtime.session: raise CommandError('Termina la preview antes de seleccionar',code='session_active')
    doc=runtime.doc(); identifier=payload.get('id'); kind=str(payload.get('kind','')).upper()
    if identifier:
        ref=dict(kind=kind,id=identifier,part=payload.get('part','BODY'))
        if kind=='ENTITY' and identifier=='ORIGIN':
            if not runtime.active_sketch_id: raise BadPayload('Abre un boceto para seleccionar su origen')
            ref['part']='POINT'
        elif kind=='ENTITY':
            sketch,e=model.entity(doc,identifier)
            if sketch['id']!=runtime.active_sketch_id: raise BadPayload('Abre el boceto antes de seleccionar sus entidades')
        elif kind=='CONSTRAINT':
            sketch=model.find(doc,'sketches',runtime.active_sketch_id)
            if model.find(sketch,'constraints',identifier).get('value') is None:
                raise BadPayload('Solo las cotas se seleccionan; las reglas se gestionan en su lista')
            ref['part']='LABEL'
        elif kind=='SKETCH':
            sketch=model.find(doc,'sketches',identifier)
            _require_reachable(doc,sketch['id'])
            if runtime.active_sketch_id: raise BadPayload('Finaliza el boceto antes de seleccionar el croquis completo para extruir')
            runtime.active_body_id=sketch.get('body_id')
        elif kind=='PROFILE':
            sketch,_=model.profile(doc,identifier)
            _require_reachable(doc,sketch['id'])
        elif kind=='FEATURE':
            feature=model.find(doc,'features',identifier)
            _require_reachable(doc,feature['id'])
            _activate_feature(doc,identifier)
            runtime.active_body_id=feature.get('body_id')
        else: raise BadPayload('Selección CAD no compatible')
    else: ref=_pick(payload)
    refs=copy.deepcopy(_refs()) if payload.get('additive') else []
    _set_selection(_toggle_refs(refs,ref))
    return runtime.status()


@command('cad.settings')
def settings(payload):
    runtime.require_workspace()
    if runtime.session: runtime.require(payload)
    if 'show_scene' in payload:
        if not isinstance(payload['show_scene'],bool): raise BadPayload('show_scene debe ser booleano')
        runtime.show_scene=payload['show_scene']
        if runtime.show_scene: runtime.restore_visibility()
    if 'construction' in payload:
        if not isinstance(payload['construction'],bool): raise BadPayload('construction debe ser booleano')
        runtime.construction=payload['construction']
    if 'step' in payload: runtime.step=model.number(payload['step'],positive=True)
    if 'increment' in payload:
        if not isinstance(payload['increment'],bool): raise BadPayload('increment debe ser booleano')
        runtime.increment=payload['increment']
    return runtime.status()


@command('cad.drag.begin')
def drag_begin(payload):
    runtime.require_workspace()
    if not runtime.active_sketch_id: raise BadPayload('Abre un boceto para mover sus puntos')
    if runtime.session:
        runtime.require(payload); runtime.cancel()
    hit=_pick(payload)
    selection_before=copy.deepcopy(runtime.selection)
    refs=copy.deepcopy(_refs())
    sketch=model.find(runtime.doc(),'sketches',runtime.active_sketch_id)
    if hit and (hit.get('intent')=='ANGLE' or not any(_covers(r,hit) for r in refs)): refs=[hit]
    start=runtime.point(payload,sketch) if hit else None
    session=runtime.begin(payload,'DRAG')
    session.update(sketch_id=sketch['id'],refs=refs,start=start,hit=hit,
                   selection_before=selection_before,dragged=False)
    if hit and hit['kind']=='CONSTRAINT':
        from ..cad import annotations, dimensions
        rules=dimensions.visible_constraints(sketch)
        rule=model.find(sketch,'constraints',hit['id'])
        index=next((i for i,c in enumerate(rules) if c['id']==rule['id']),0)
        session.update(annotation_id=rule['id'],annotation_start=annotations.layout(sketch,rule,index)['label'],refs=[hit])
    # A tap toggles only on END; a second finger can still cancel without changing selection.
    return runtime.status()


@command('cad.drag.update')
def drag_update(payload):
    if not runtime.session: return runtime.status()
    session=runtime.require(payload)
    if session['operation']!='DRAG': raise BadPayload('La sesión no es de arrastre')
    session['dragged']=True
    if session.get('hit') is None: return runtime.status()
    _set_selection(session['refs'])
    doc=copy.deepcopy(session['baseline']); sketch=model.find(doc,'sketches',session['sketch_id'])
    p=runtime.point(payload,sketch); dx,dy=[p[i]-session['start'][i] for i in (0,1)]
    if session.get('annotation_id'):
        rule=model.find(sketch,'constraints',session['annotation_id'])
        position=[session['annotation_start'][0]+dx,session['annotation_start'][1]+dy]
        rule['label_position']=[model.number(value) for value in position]
        changed=math.hypot(dx,dy)>1e-10
        session.update(preview=doc,candidate=rule['id'] if changed else None)
        return runtime.status()
    if runtime.increment: dx,dy=[round(d/runtime.step)*runtime.step for d in (dx,dy)]
    try:
        if session['hit'].get('intent')=='ANGLE':
            arc=geometry.get_entity(sketch,session['hit'])
            goals=geometry.arc_angle_goals(arc,p,session.get('last_sweep',arc['sweep']))
        else:
            goals=geometry.move_goals(sketch,session['refs'],dx,dy)
        from ..cad.jobs import Calculation
        solved = yield Calculation(operation='solve', sketch=sketch, goals=[{k: v.tolist() if hasattr(v, 'tolist') else v for k, v in goal.items()} for goal in goals])
        sketch.update(solved)
        yield from runtime.rebuild_steps(doc,limit=runtime.bar(doc))
    except CommandError:
        # Keep the last visible valid preview. END never retries the pointer.
        raise
    baseline=model.find(session['baseline'],'sketches',sketch['id'])
    changed=any(abs(e[k]-original[k])>(1e-7 if k in model.ANGULAR else 1e-9)
                for e,original in zip(sketch['entities'],baseline['entities']) for k in model.FIELDS[e['type']])
    session.update(preview=doc,candidate=sketch['id'] if changed else None)
    if session['hit'].get('intent')=='ANGLE':
        session['last_sweep']=geometry.get_entity(sketch,session['hit'])['sweep']
    return runtime.status()


@command('cad.drag.end')
def drag_end(payload):
    if not runtime.session: return runtime.status()
    session=runtime.require(payload)
    if session['operation']!='DRAG': raise BadPayload('La sesión no es de arrastre')
    if session.get('candidate'): return (yield from confirm.__wrapped__(payload))
    if not session.get('dragged'):
        previous=session.get('selection_before') or {}
        refs=previous.get('items',[previous] if previous else [])
        _set_selection(_toggle_refs(refs,session.get('hit')))
    runtime.session=None
    return runtime.status()


@command('cad.points.weld')
def points_weld(payload):
    runtime.require_workspace()
    if runtime.session: raise CommandError('Termina la preview antes de soldar',code='session_active')
    doc=runtime.doc()
    sketch=model.find(doc,'sketches',runtime.active_sketch_id)
    refs=[dict(id=r['id'],part=r.get('part','BODY')) for r in _refs() if r.get('kind')=='ENTITY']
    if geometry.weld_points(sketch,refs): yield from runtime.commit_steps(doc,'CAD soldar puntos')
    return runtime.status()


@command('cad.constraint.add')
def constraint_add(payload):
    typ=str(payload.get('type','')).upper()
    def change(doc):
        sketch=model.find(doc,'sketches',runtime.active_sketch_id)
        source=payload.get('refs') if 'refs' in payload else [r for r in _refs() if r['kind']=='ENTITY']
        if not isinstance(source,list) or not all(isinstance(r,dict) and isinstance(r.get('id'),str) and isinstance(r.get('part','BODY'),str) for r in source):
            raise BadPayload('Referencias de cota inválidas')
        refs=[dict(id=r['id'],part=r.get('part','BODY')) for r in source]
        if typ=='POINT_ON_LINE': refs=geometry.point_line_refs(sketch,refs)
        c=dict(id=model.uid('constraint'),type=typ,refs=refs)
        if typ in dimensions.NUMERIC: c['value']=_dimension_value(typ,payload.get('value'))
        if typ in ('HORIZONTAL','VERTICAL'):
            if not refs: raise BadPayload('Selecciona una o varias líneas o lados rectos')
            existing={(rule['type'],r['id'],r.get('part','BODY'))
                      for rule in sketch.get('constraints',[]) if rule['type'] in ('HORIZONTAL','VERTICAL')
                      for r in rule['refs']}
            for ref in refs:
                entity=geometry.get_entity(sketch,ref);part=ref['part']
                if not ((entity['type']=='LINE' and part=='BODY') or
                        (entity['type'] in ('RECTANGLE','NGON') and part.startswith('EDGE') and part[4:].isdigit())):
                    raise BadPayload('Horizontal/Vertical requiere líneas o lados rectos completos')
                rule=dict(id=model.uid('constraint'),type=typ,refs=[ref])
                geometry.validate_constraints(dict(sketch,constraints=[rule]))
                key=(typ,ref['id'],part)
                if key not in existing:
                    sketch.setdefault('constraints',[]).append(rule);existing.add(key)
            geometry.solve(sketch)
            return
        if typ=='EQUAL' and len({r['id'] for r in refs})>=2 and all(geometry.get_entity(sketch,r)['type']=='ARC' for r in refs):
            # Drawn arcs keep the radius and angle of the first one; roundings only the radius.
            first,angles=dimensions.equalize_arcs(sketch,refs); arc=geometry.get_entity(sketch,first)
            goals=[dict(constraint=dict(type='RADIUS',refs=[first],value=arc['radius']))]
            if angles: goals.append(dict(constraint=dict(type='ANGLE',refs=[first],value=abs(arc['sweep']))))
            geometry.solve(sketch,goals)
            return
        if typ=='EQUAL':
            unique=[]; quantities=set()
            for ref in refs:
                quantity=dimensions.quantity(sketch,ref)
                if quantity is None: raise BadPayload('Igualdad requiere círculos/arcos o líneas/lados del mismo croquis')
                if quantity not in quantities: unique.append(ref); quantities.add(quantity)
            if len(unique)<2: raise BadPayload('Selecciona al menos dos medidas distintas del mismo croquis')
            curves=all(geometry.get_entity(sketch,r)['type'] in ('CIRCLE','ARC') for r in unique)
            first=unique[0]
            value=geometry.radius(sketch,first) if curves else math.dist(*geometry.measure_line(sketch,first))
            for ref in unique[1:]:
                rule=dict(id=model.uid('constraint'),type='EQUAL',refs=[first,ref])
                geometry.validate_constraints(dict(sketch,constraints=[rule]))
                root=dimensions.groups(sketch)
                if root(dimensions.quantity(sketch,first)) != root(dimensions.quantity(sketch,ref)):
                    sketch.setdefault('constraints',[]).append(rule)
            geometry.solve(sketch,[dict(constraint=dict(type='RADIUS' if curves else 'DISTANCE',refs=[first],value=value))])
            return
        if typ=='MIDPOINT' and len(refs)==2:
            refs.sort(key=lambda r: 0 if r.get('part') in geometry.handles(geometry.get_entity(sketch,r)) else 1)
        if typ=='FIX':
            if not refs or any(r['id']=='ORIGIN' for r in refs): raise BadPayload('Selecciona geometría; el origen ya está fijo')
            for ref in refs:
                e=geometry.get_entity(sketch,ref); part=ref.get('part','BODY')
                fixed=dict(id=model.uid('constraint'),type='FIX',refs=[ref])
                if part in geometry.handles(e): fixed['points']={part:list(geometry.handles(e)[part])}
                elif e['type'] in ('RECTANGLE','NGON') and part.startswith('EDGE'):
                    index=int(part[4:]); roles=['P'+str(index),'P'+str((index+1)%e.get('sides',4))]
                    fixed['points']={role:list(geometry.handles(e)[role]) for role in roles}
                else: fixed['values']={k:e[k] for k in model.FIELDS[e['type']]}
                sketch.setdefault('constraints',[]).append(fixed)
        elif typ in dimensions.NUMERIC:
            c=dimensions.put(sketch,c)
        else: sketch.setdefault('constraints',[]).append(c)
        if typ in dimensions.NUMERIC: dimensions.solve_dimension(sketch,c)
        else: geometry.solve(sketch)
    return (yield from runtime.transaction_steps(payload,change,'CAD restringir boceto'))


@command('cad.constraint.delete')
def constraint_delete(payload):
    def change(doc):
        sketch=model.find(doc,'sketches',payload.get('sketch_id') or runtime.active_sketch_id)
        c=model.find(sketch,'constraints',payload.get('constraint_id'))
        dimensions.remove(sketch,c)
    return (yield from runtime.transaction_steps(payload,change,'CAD quitar restricción'))


@command('cad.fillet')
def fillet(payload):
    created=[]
    def change(doc):
        sketch=model.find(doc,'sketches',runtime.active_sketch_id)
        previous={p['id'] for p in model.profiles(sketch)}
        arcs=geometry.fillet(sketch,_refs(),model.number(payload.get('radius'),positive=True))
        created.extend(arc['id'] for arc in arcs)
        current=model.closed_entities(sketch)
        replacement=next((p for p in current if set(created)&set(p.get('members',[]))),None)
        remaining={'profile_'+p['id'] for p in current}
        for f in doc['features']:
            for sketch_key,profile_key in (('sketch_id','profile_id'),('to_sketch_id','to_profile_id')):
                if f.get(sketch_key)==sketch['id'] and f[profile_key] in previous-remaining:
                    if replacement is None: raise BadPayload('El redondeo debe conservar cerrado el perfil de la operación')
                    f[profile_key]='profile_'+replacement['id']
    yield from runtime.transaction_steps(payload,change,'CAD redondear esquina')
    _set_selection([dict(kind='ENTITY',id=identifier,part='BODY') for identifier in created])
    return runtime.status()


@command('cad.fillet.remove')
def fillet_remove(payload):
    def change(doc):
        sketch,arc=model.entity(doc,payload.get('entity_id'))
        old_profiles=model.closed_entities(sketch)
        geometry.remove_fillet(sketch,arc)
        new_profiles=model.closed_entities(sketch)
        for feature in doc['features']:
            for key in ('profile_id','to_profile_id'):
                before=next((p for p in old_profiles if 'profile_'+p['id']==feature.get(key) and arc['id'] in p.get('members',[])),None)
                if before:
                    members=set(before['members'])-{arc['id']}
                    after=next((p for p in new_profiles if set(p.get('members',[]))==members),None)
                    if after is None: raise BadPayload('No se puede cerrar el perfil al quitar este redondeo')
                    feature[key]='profile_'+after['id']
    yield from runtime.transaction_steps(payload,change,'CAD quitar redondeo')
    runtime.selection=None
    return runtime.status()


def _dimension_value(typ, value):
    # An arc's sweep sign is its drawing direction; its angle dimension is a magnitude.
    if typ=='ANGLE': return abs(model.number(value))
    return model.number(value,positive=typ in ('DISTANCE','RADIUS'))


@command('cad.constraint.set')
def constraint_set(payload):
    def change(doc):
        sketch=model.find(doc,'sketches',payload.get('sketch_id') or runtime.active_sketch_id)
        c=model.find(sketch,'constraints',payload.get('constraint_id'))
        if c['type']=='OFFSET':
            from ..cad.offset import set_value
            set_value(sketch,c,payload.get('value'))
            return
        if c['type'] not in dimensions.NUMERIC: raise BadPayload('Esta restricción no tiene una cota editable')
        updated=dict(c,value=_dimension_value(c['type'],payload.get('value')))
        c=dimensions.put(sketch,updated)
        dimensions.solve_dimension(sketch,c)
    return (yield from runtime.transaction_steps(payload,change,'CAD editar restricción'))


@command('cad.sketch.delete')
def sketch_delete(payload):
    identifier=payload.get('sketch_id')
    def change(doc):
        _require_reachable(doc,identifier)
        if any(identifier in (f['sketch_id'],f.get('to_sketch_id')) for f in doc['features']) or any(p.get('reference_sketch_id')==identifier for p in doc.get('planes',[])):
            raise CommandError('Elimina primero las operaciones del boceto',code='cad_dependency')
        removed=model.find(doc,'sketches',identifier)
        doc['sketches'].remove(removed)
        plane_id=removed.get('plane_id')
        if plane_id and not any(s.get('plane_id')==plane_id for s in doc['sketches']):
            plane=model.find(doc,'planes',plane_id)
            if plane.get('implicit'): doc['planes'].remove(plane)
    yield from runtime.transaction_steps(payload,change,'CAD eliminar boceto')
    if runtime.active_sketch_id==identifier: runtime.active_sketch_id=None
    runtime.selection=None
    return runtime.status()


@command('cad.sketch.copy')
def sketch_copy(payload):
    """Copy a sketch onto a parallel plane `offset` metres along its normal.

    The plane references the source sketch, so the copy follows it and its
    separation remains editable (cad.plane.set translation Z). IDs are new.
    """
    offset=model.number(payload.get('offset',0))
    def change(doc):
        source=model.find(doc,'sketches',payload.get('sketch_id'))
        _require_reachable(doc,source['id'])
        plane=dict(id=model.uid('plane'),name='Plano de '+source['name'],base='XY',implicit=True,
                   reference_sketch_id=source['id'],translation=[0.,0.,offset],rotation=[0.,0.,0.])
        model.validate_plane(plane); doc['planes'].append(plane)
        ids={e['id']:model.uid('entity') for e in source['entities']}
        entities=[dict(copy.deepcopy(e),id=ids[e['id']]) for e in source['entities']]
        constraints=[]
        for c in source.get('constraints',[]):
            clone=copy.deepcopy(c); clone['id']=model.uid('constraint')
            clone['refs']=[dict(r,id=ids.get(r['id'],r['id'])) for r in c['refs']]
            constraints.append(clone)
        sketch=dict(id=model.uid('sketch'),name=source['name']+' (copia)',plane=source['plane'],offset=0,plane_id=plane['id'],
                    entities=entities,constraints=constraints,visible=True,order=model.next_order(doc),body_id=source.get('body_id'))
        doc['sketches'].append(sketch)
        bar=runtime.bar(doc)
        if bar: model.insert_after(doc,sketch,bar)
        model.resolve_supports(doc)
        runtime.selection=dict(kind='SKETCH',id=sketch['id'])
    yield from runtime.transaction_steps(payload,change,'CAD copiar croquis a otro plano')
    return runtime.status()


@command('cad.body.create')
def body_create(payload):
    def change(doc):
        body=dict(id=model.uid('body'),name='Cuerpo '+str(len(doc['bodies'])+1))
        doc['bodies'].append(body); runtime.active_body_id=body['id']
        runtime.active_sketch_id=None; runtime.selection=None
    return (yield from runtime.transaction_steps(payload,change,'CAD crear cuerpo'))


@command('cad.body.activate')
def body_activate(payload):
    runtime.require_workspace()
    if runtime.session: raise CommandError('Termina la preview antes de cambiar de cuerpo',code='session_active')
    body=model.find(runtime.doc(),'bodies',payload.get('body_id'))
    runtime.active_body_id=body['id']; runtime.selection=None
    runtime.solid_view()
    return runtime.status()


@command('cad.plane.create')
def plane_create(payload):
    def change(doc):
        plane=dict(id=model.uid('plane'),name='Plano '+str(len(doc['planes'])+1),base=payload.get('base','XY'),
                   translation=payload.get('translation',[0,0,0]),rotation=payload.get('rotation',[0,0,0]))
        for key in ('reference_sketch_id','support_id'):
            if payload.get(key): plane[key]=payload[key]
        if 'u' in payload or 'v' in payload: raise BadPayload('Selecciona una cara y pulsa Boceto en cara')
        model.validate_plane(plane); doc['planes'].append(plane); model.resolve_supports(doc)
        if payload.get('start_sketch'): _new_sketch(doc,dict(plane_id=plane['id']))
    return (yield from runtime.transaction_steps(payload,change,'CAD crear plano'))


@command('cad.plane.set')
def plane_set(payload):
    def change(doc):
        plane=model.find(doc,'planes',payload.get('plane_id'))
        for key in ('translation','rotation'):
            if key in payload: plane[key]=payload[key]
        model.validate_plane(plane)
    result = yield from runtime.transaction_steps(payload,change,'CAD colocar plano')
    if runtime.active_sketch_id: runtime.focus(model.find(runtime.doc(),'sketches',runtime.active_sketch_id))
    return runtime.status()


@command('cad.surface.mode')
def surface_mode(payload):
    runtime.require_workspace()
    if runtime.session: raise CommandError('Termina la preview antes de seleccionar referencias',code='session_active')
    value=payload.get('mode')
    if value not in ('PROFILE','FACE','EDGE','VERTEX'): raise BadPayload('Selección: PROFILE, FACE, EDGE o VERTEX')
    runtime.surface.mode=value
    if value=='PROFILE': runtime.surface.clear(); runtime.selection=None
    return runtime.status()


@command('cad.surface.select')
def surface_select(payload):
    runtime.require_workspace()
    if runtime.session: raise CommandError('Termina la preview antes de medir',code='session_active')
    runtime.surface.select(payload,accumulate=runtime.active_sketch_id is not None)
    last=runtime.surface.items[-1] if runtime.surface.items else None
    runtime.selection=dict(kind='SURFACE',id=last['id'],feature_id=last['feature_id']) if last else None
    if last and last['feature_id'] and not runtime.active_sketch_id:
        runtime.active_body_id=model.find(runtime.doc(),'features',last['feature_id']).get('body_id')
    return runtime.status()


@command('cad.surface.clear')
def surface_clear(payload):
    runtime.require_workspace(); runtime.surface.clear(); runtime.selection=None
    return runtime.status()


def _face_plane(doc, frame, source, offset=0.):
    """Plane on a captured face frame; a CAD top face keeps an associative support."""
    from mathutils import Vector
    plane=dict(id=model.uid('plane'),name='Cara de '+source['object'],base='XY',implicit=True,
               translation=[0,0,offset],rotation=[0,0,0],face_frame=frame)
    feature=next((f for f in doc['features'] if f['id']==source['feature_id']),None)
    candidates=[node for node in reversed(model.history(doc)) if node['kind']=='FEATURE' and node['enabled'] and not node.get('mirror') and
                node['type'] in ('EXTRUDE','CUT') and
                feature and node['body_id']==feature['body_id'] and node['id'] in _reachable_ids(doc)]
    for support in candidates:
        source_sketch=model.find(doc,'sketches',support['sketch_id']); base=model.frame(source_sketch)
        normal=Vector(base['normal'])
        top=Vector(base['origin'])+normal*(support['depth'] if support['type']=='EXTRUDE' else 0)
        delta=Vector(frame['origin'])-top
        if Vector(frame['normal']).dot(normal)>1-1e-6 and abs(delta.dot(normal))<1e-7:
            plane.pop('face_frame'); plane['support_id']=support['id']
            plane['translation']=[delta.dot(Vector(base['x'])),delta.dot(Vector(base['y'])),offset]
            plane['rotation']=[0.,0.,math.degrees(math.atan2(Vector(frame['x']).dot(Vector(base['y'])),Vector(frame['x']).dot(Vector(base['x']))))]
            break
    return plane,(feature.get('body_id') if feature else None)


@command('cad.sketch.on_face')
def sketch_on_face(payload):
    frame=runtime.surface.face_frame()  # The visible selection, never a second raycast.
    source=runtime.surface.items[0]
    # Metres along the face normal: positive leaves the material, negative enters it.
    offset=model.number(payload.get('offset',0))
    def change(doc):
        from mathutils import Vector
        plane,body=_face_plane(doc,frame,source,offset)
        model.validate_plane(plane); doc['planes'].append(plane)
        _new_sketch(doc,dict(plane_id=plane['id'],body_id=body))
        from ..bpy_utils import find_view3d
        from ..camera import camera
        found=find_view3d()
        if found: camera.look_at(Vector(source['center']),[Vector(p) for p in source['points']],found[3])
    return (yield from runtime.transaction_steps(payload,change,'CAD boceto en cara seleccionada'))


# ---- Interactive plane placement -------------------------------------------------
# The plane is a preview drawn in the capture while its base, separation, tilt and
# in-plane shift are adjusted; confirming creates the plane (and a sketch) in one undo.

def _rotation(degrees):
    import numpy as np
    rx,ry,rz=map(math.radians,degrees)
    cx,sx,cy,sy,cz,sz=math.cos(rx),math.sin(rx),math.cos(ry),math.sin(ry),math.cos(rz),math.sin(rz)
    return np.array([[cz,-sz,0],[sz,cz,0],[0,0,1]])@np.array([[cy,0,sy],[0,1,0],[-sy,0,cy]])@np.array([[1,0,0],[0,cx,-sx],[0,sx,cx]])


def _session_plane(doc, session):
    """Document plane for the session parameters. Separation follows the tilted normal."""
    import numpy as np
    p=session['plane']
    if p.get('plane_id'):
        plane=copy.deepcopy(model.find(doc,'planes',p['plane_id'])); body=None
        base_translation=[0.,0.,0.]; base_rz=plane['rotation'][2]
    elif p['base']=='FACE':
        plane,body=_face_plane(doc,session['face'][0],session['face'][1])
        base_translation=list(plane['translation']); base_rz=plane['rotation'][2]
    else:
        plane=dict(id=model.uid('plane'),name='Plano '+str(len(doc['planes'])+1),base=p['base'],
                   translation=[0,0,0],rotation=[0,0,0]); body=None
        base_translation=[0.,0.,0.]; base_rz=0.
    rotation=[p['tilt'][0],p['tilt'][1],base_rz]
    lifted=_rotation(rotation)@np.array([0.,0.,p['offset']])
    plane['translation']=[base_translation[0]+p['shift'][0]+float(lifted[0]),
                          base_translation[1]+p['shift'][1]+float(lifted[1]),float(lifted[2])]
    plane['rotation']=rotation
    return plane,body


def _plane_preview(session):
    """Rebuild the preview document and the frame the capture draws."""
    doc=copy.deepcopy(session['baseline'])
    plane,body=_session_plane(doc,session)
    model.validate_plane(plane)
    p=session['plane']
    if p.get('plane_id'):
        doc['planes']=[plane if q['id']==plane['id'] else q for q in doc['planes']]
        model.resolve_supports(doc)
        frame=model.find(doc,'planes',plane['id'])['frame']; sketch_id=None
    else:
        doc['planes'].append(plane)
        sketch=dict(id=model.uid('sketch'),name='Boceto '+str(len(doc['sketches'])+1),plane='XY',offset=0,
                    plane_id=plane['id'],entities=[],constraints=[],visible=True,order=model.next_order(doc),
                    body_id=body or runtime.active_body_id or doc['bodies'][0]['id'])
        doc['sketches'].append(sketch)
        bar=runtime.bar(doc)
        if bar: model.insert_after(doc,sketch,bar)
        model.resolve_supports(doc)
        frame=model.find(doc,'planes',plane['id'])['frame']; sketch_id=sketch['id']
    session.update(preview=doc,candidate=plane['id'],plane_frame=frame,sketch_id=sketch_id)


def _plane_public(session):
    p=session['plane']
    from ..cad import document as _model
    labels=direction_labels(session['plane_frame']['normal']) if session.get('plane_frame') else ('','')
    return dict(base=p['base'],plane_id=p.get('plane_id'),offset=p['offset'],tilt=list(p['tilt']),shift=list(p['shift']),
                positive_label=labels[0],negative_label=labels[1])


@command('cad.plane.begin')
def plane_begin(payload):
    """Start placing a plane: `base` XY/XZ/YZ/FACE, or `plane_id` to move a saved one."""
    import numpy as np
    runtime.require_workspace()
    plane_id=payload.get('plane_id')
    base=str(payload.get('base','XY')).upper()
    face=None
    if plane_id:
        saved=model.find(runtime.doc(),'planes',plane_id)
        # Decompose the stored translation into in-plane shift + separation along the tilted normal.
        R=_rotation(saved['rotation']); t=saved['translation']
        offset=t[2]/R[2,2] if abs(R[2,2])>1e-9 else 0.
        params=dict(base=saved.get('base','XY'),plane_id=plane_id,offset=offset,tilt=[saved['rotation'][0],saved['rotation'][1]],
                    shift=[t[0]-offset*R[0,2],t[1]-offset*R[1,2]])
    else:
        if base not in model.PLANES+('FACE',): raise BadPayload('Base de plano: XY, XZ, YZ o FACE')
        if base=='FACE':
            face=(runtime.surface.face_frame(),copy.deepcopy(runtime.surface.items[0]))
        params=dict(base=base,offset=0.,tilt=[0.,0.],shift=[0.,0.])
    session=runtime.begin(payload,'PLANE')
    session.update(plane=params,face=face)
    _plane_preview(session)
    return runtime.status()


@command('cad.plane.update')
def plane_update(payload):
    session=runtime.require(payload)
    if session['operation']!='PLANE': raise CommandError('La sesión no coloca un plano',code='wrong_tool')
    p=dict(session['plane'],tilt=list(session['plane']['tilt']),shift=list(session['plane']['shift']))
    if 'base' in payload:
        base=str(payload['base']).upper()
        if p.get('plane_id'): raise BadPayload('Un plano guardado conserva su base')
        if base not in model.PLANES+('FACE',): raise BadPayload('Base de plano: XY, XZ, YZ o FACE')
        if base=='FACE' and session.get('face') is None:
            raise BadPayload('Selecciona antes una cara plana del sólido')
        p['base']=base
    if 'offset' in payload: p['offset']=model.number(payload['offset'])
    if 'tilt' in payload:
        values=payload['tilt']
        if not isinstance(values,list) or len(values)!=2: raise BadPayload('Inclinación: dos ángulos en grados')
        p['tilt']=[model.number(v) for v in values]
    if 'shift' in payload:
        values=payload['shift']
        if not isinstance(values,list) or len(values)!=2: raise BadPayload('Desplazamiento: dos distancias en metros')
        p['shift']=[model.number(v) for v in values]
    if 'gesture_u' in payload or 'gesture_v' in payload:
        # The pen drags the plane along its own normal, 1:1 under the tip.
        frame=session['plane_frame']
        gu,gv=model.number(payload.get('gesture_u',0)),model.number(payload.get('gesture_v',0))
        u,v=model.number(payload.get('u',.5)),model.number(payload.get('v',.5))
        travel=_travel_along(frame['origin'],frame['normal'],(u-gu,v-gv),(u,v))
        if travel is not None:
            value=model.number(payload.get('baseline_offset',p['offset']))+travel
            if runtime.increment: value=round(value/runtime.step)*runtime.step
            p['offset']=value
    previous=session['plane']; session['plane']=p
    try: _plane_preview(session)
    except (BadPayload,CommandError):
        session['plane']=previous; _plane_preview(session); raise
    return runtime.status()


@command('cad.reference.project')
def project_reference(payload):
    from mathutils import Vector
    runtime.surface.validate()
    items=copy.deepcopy(runtime.surface.items)
    if not items: raise BadPayload('Selecciona un punto, una arista o una cara para proyectarla')
    def change(doc):
        sketch=model.find(doc,'sketches',runtime.active_sketch_id); frame=model.frame(sketch)
        scale=bpy.context.scene.unit_settings.scale_length; origin=Vector(frame['origin'])
        def project(point):
            offset=Vector(point)*scale-origin
            return (offset.dot(Vector(frame['x'])),offset.dot(Vector(frame['y'])))
        def add(entity):
            entity=dict(entity,id=model.uid('entity'),construction=True,reference=True)
            sketch['entities'].append(entity)
            created.append(entity['id'])
            sketch.setdefault('constraints',[]).append(dict(id=model.uid('constraint'),type='FIX',
                refs=[dict(id=entity['id'],part='BODY')],values={k:entity[k] for k in model.FIELDS[entity['type']]}))
        created=[]; seen=set(); segments=[]
        for item in items:
            if item['kind']=='VERTEX':
                for p in item['points']: add(dict(type='POINT',x=project(p)[0],y=project(p)[1]))
                continue
            for a,b in item['segments']:
                a,b=project(a),project(b)
                identity=tuple(sorted(tuple(round(v,10) for v in p) for p in (a,b)))
                if identity not in seen: seen.add(identity); segments.append((a,b))
        if segments:
            coords=[c for segment in segments for p in segment for c in [p]]
            size=math.dist((min(p[0] for p in coords),min(p[1] for p in coords)),(max(p[0] for p in coords),max(p[1] for p in coords)))
            tol=max(size*1e-5,1e-7)
            # Straight runs, arcs and round loops, not one line per tessellated segment.
            for points,closed in geometry.chain_segments(segments,tol):
                for shape in geometry.fit_polyline(points,closed,tol): add(shape)
        if not created: raise BadPayload('La referencia se proyecta como un punto; elige otra arista')
        geometry.solve(sketch)
    yield from runtime.transaction_steps(payload,change,'CAD proyectar referencia fija')
    runtime.surface.clear(); runtime.surface.mode='PROFILE'; runtime.selection=None
    return runtime.status()


@command('cad.view.roll')
def view_roll(payload):
    """Spin the sketch view around its plane normal. Drawing stays on the plane."""
    runtime.require_workspace()
    if not runtime.active_sketch_id:
        raise BadPayload('Abre un boceto para girar su vista')
    from .view import roll_delta
    roll_delta(math.radians(model.number(payload.get('degrees', 90))))
    return runtime.status()


@command('cad.view.align')
def view_align(payload):
    """Look straight at the sketch, with world up on screen. No document change."""
    runtime.require_workspace()
    sketch = model.find(runtime.doc(), 'sketches', runtime.active_sketch_id)
    runtime.focus(sketch)
    return runtime.status()


@command('cad.view.solid')
def view_solid(payload):
    runtime.require_workspace()
    if runtime.session:
        runtime.require(payload); runtime.cancel()
    runtime.solid_view()
    return runtime.status()
