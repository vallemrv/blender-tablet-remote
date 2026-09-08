"""cad.*: intent commands; all geometry and bpy run in the bridge pump."""
import copy
import math
import bpy
from . import command
from ..cad import document as model
from ..cad import sketch as geometry
from ..cad.runtime import runtime, FEATURE_KEY, DOC_KEY
from ..errors import BadPayload, CommandError
from ..bpy_utils import undo_push


def _activate_feature(doc, identifier):
    obj = next((o for o in runtime.objects(doc) if o[FEATURE_KEY] == identifier), None)
    if obj is not None and not obj.hide_viewport:
        for other in bpy.context.view_layer.objects:
            if other.select_get():
                other.select_set(False)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj


@command('cad.state')
def state(payload):
    return runtime.status()


@command('cad.sketch.create')
def sketch_create(payload):
    plane = str(payload.get('plane','XY')).upper()
    if plane not in model.PLANES:
        raise BadPayload('Plano CAD no compatible')
    def change(doc):
        offset=model.number(payload.get('offset',0))
        support_id=payload.get('support_id')
        if support_id:
            feature=model.find(doc,'features',support_id)
            source,_=model.profile(doc,feature['profile_id'])
            plane_local=source['plane']
            offset=source.get('offset',0)+(feature['depth'] if feature['type']=='EXTRUDE' else 0)
        else: plane_local=plane
        sketch = dict(id=model.uid('sketch'),name='Sketch '+str(len(doc['sketches'])+1),plane=plane_local,
                      offset=offset,entities=[],constraints=[])
        if support_id: sketch['support_id']=support_id
        doc['sketches'].append(sketch)
        runtime.active_sketch_id = sketch['id']
        runtime.selection = None
        runtime.focus(sketch)
    return runtime.transaction(payload,change,'CAD crear sketch')


@command('cad.sketch.activate')
def sketch_activate(payload):
    runtime.require_workspace()
    if runtime.session:
        runtime.require(payload)
        runtime.cancel()
    sketch = model.find(runtime.doc(),'sketches',payload.get('sketch_id'))
    runtime.active_sketch_id = sketch['id']
    runtime.selection = None
    runtime.focus(sketch)
    return runtime.status()


@command('cad.sketch.finish')
def sketch_finish(payload):
    runtime.require_workspace()
    if runtime.session:
        runtime.require(payload)
        runtime.cancel()
    runtime.active_sketch_id = None
    runtime.selection = None
    return runtime.status()


def _endpoint(payload, sketch, previous=None):
    from .snap import query_sketch_endpoint
    from ..bpy_utils import find_view3d
    found=find_view3d()
    if not found: return None
    return query_sketch_endpoint(runtime.overlay(runtime.doc()),model.number(payload.get('u')),
                                 model.number(payload.get('v')),found[2].width/max(found[2].height,1),previous)


@command('cad.entity.begin')
def entity_begin(payload):
    typ = str(payload.get('type','')).upper()
    square=typ=='SQUARE'
    if square: typ='RECTANGLE'
    if typ not in model.TYPES:
        raise BadPayload('Tipo de entidad CAD no compatible')
    sketch = model.find(runtime.doc(),'sketches',runtime.active_sketch_id)
    start = runtime.point(payload,sketch['plane'])
    anchor=_endpoint(payload,sketch) if typ=='LINE' else None
    if anchor: start=geometry.handles(model.find(sketch,'entities',anchor['entity_id']))[anchor['part']]
    session = runtime.begin(payload,typ)
    session.update(sketch_id=sketch['id'],start=start,entity_id=model.uid('entity'),square=square,anchor=anchor)
    return runtime.status()


@command('cad.entity.update')
def entity_update(payload):
    session = runtime.require(payload)
    if session['operation'] not in model.TYPES:
        raise CommandError('La sesión no es de dibujo',code='wrong_tool')
    doc = copy.deepcopy(session['baseline'])
    sketch = model.find(doc,'sketches',session['sketch_id'])
    x,y = session['start']
    x2,y2 = runtime.point(payload,sketch['plane'])
    endpoint=_endpoint(payload,sketch,session.get('endpoint')) if session['operation']=='LINE' else None
    session['endpoint']=endpoint
    if endpoint: x2,y2=geometry.handles(model.find(sketch,'entities',endpoint['entity_id']))[endpoint['part']]
    e = dict(id=session['entity_id'],type=session['operation'],x=x,y=y)
    if e['type']=='RECTANGLE':
        if session.get('square'):
            size=max(abs(x2-x),abs(y2-y))
            x2=x+math.copysign(size,x2-x); y2=y+math.copysign(size,y2-y)
        e.update(x=min(x,x2),y=min(y,y2),width=abs(x2-x),height=abs(y2-y))
    elif e['type']=='ARC':
        e.update(radius=math.hypot(x2-x,y2-y),start=math.degrees(math.atan2(y2-y,x2-x)),sweep=90.)
    elif e['type']=='CIRCLE':
        e['diameter'] = 2*math.hypot(x2-x,y2-y)
    else:
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
    for role,anchor in (('START',session.get('anchor')),('END',endpoint)):
        if anchor:
            sketch.setdefault('constraints',[]).append(dict(id='join_'+e['id']+'_'+role,type='COINCIDENT',
                refs=[dict(id=e['id'],part=role),dict(id=anchor['entity_id'],part=anchor['part'])]))
    if session.get('square'):
        sketch.setdefault('constraints',[]).append(dict(id='square_'+e['id'],type='EQUAL',
            refs=[dict(id=e['id'],part='EDGE0'),dict(id=e['id'],part='EDGE1')]))
    session['preview'] = doc
    session['candidate'] = e['id']
    _set_selection([dict(kind='ENTITY',id=e['id'],part='BODY')])
    return runtime.status()


@command('cad.entity.set')
def entity_set(payload):
    changes = payload.get('values')
    if not isinstance(changes,dict) or not changes:
        raise BadPayload('Faltan las dimensiones')
    def change(doc):
        sketch, e = model.entity(doc,payload.get('entity_id'))
        allowed = set(model.FIELDS[e['type']])
        if not set(changes)<=allowed:
            raise BadPayload('Dimensión no compatible con la entidad')
        goals=[dict(id=e['id'],field=k,value=model.number(v)) for k,v in changes.items()]
        geometry.solve(sketch,goals)
    return runtime.transaction(payload,change,'CAD editar dimensiones')


@command('cad.entity.delete')
def entity_delete(payload):
    def change(doc):
        sketch,e = model.entity(doc,payload.get('entity_id'))
        if any(f['sketch_id']==sketch['id'] for f in doc['features']):
            raise CommandError('El sketch tiene extrusiones; elimina primero sus features',code='cad_dependency')
        sketch['entities'].remove(e)
        sketch['constraints']=[c for c in sketch.get('constraints',[]) if not any(r['id']==e['id'] for r in c['refs'])]
    result = runtime.transaction(payload,change,'CAD eliminar entidad')
    runtime.selection = None
    return runtime.status()


@command('cad.extrude.begin')
def extrude_begin(payload):
    depth = model.number(payload.get('depth',.02),positive=True)
    doc = runtime.doc()
    sketch,e = model.profile(doc,payload.get('profile_id'))
    operation=str(payload.get('operation','EXTRUDE')).upper()
    if operation not in ('EXTRUDE','CUT'): raise BadPayload('Operación CAD no compatible')
    target=None
    if operation=='CUT':
        target=model.find(doc,'features',payload.get('target_id'))
        if not target['enabled']: raise BadPayload('El sólido destino está desactivado')
    session = runtime.begin(payload,operation)
    feature = dict(id=model.uid('feature'),name=('Vaciado ' if operation=='CUT' else 'Extrusión ')+str(len(doc['features'])+1),
                   type=operation,sketch_id=sketch['id'],profile_id='profile_'+e['id'],depth=depth,enabled=True)
    if target: feature['target_id']=target['id']
    preview = copy.deepcopy(session['baseline'])
    preview['features'].append(feature)
    try:
        runtime.rebuild(preview)
    except Exception:
        runtime.session = None
        raise
    session.update(feature_id=feature['id'],preview=preview,candidate=feature['id'],depth=depth)
    runtime.selection = dict(kind='FEATURE',id=feature['id'])
    runtime.active_sketch_id = None
    return runtime.status()


@command('cad.extrude.update')
def extrude_update(payload):
    session = runtime.require(payload)
    if session['operation'] not in ('EXTRUDE','CUT'):
        raise CommandError('La sesión no es una extrusión',code='wrong_tool')
    if 'gesture' in payload:
        delta=model.number(payload['gesture'])
        base=model.number(payload.get('baseline_depth',session['depth']),positive=True)
        distance=delta/.04*runtime.step
        if runtime.increment: distance=round(distance/runtime.step)*runtime.step
        depth=max(1e-7,base+distance)
    else: depth = model.number(payload.get('depth'),positive=True)
    preview = copy.deepcopy(session['preview'])
    model.find(preview,'features',session['feature_id'])['depth'] = depth
    runtime.rebuild(preview)
    session.update(preview=preview,depth=depth)
    return runtime.status()


@command('cad.session.confirm')
def confirm(payload):
    session = runtime.require(payload)
    if not session['candidate']:
        runtime.cancel()
        return runtime.status()
    doc = session['preview']
    runtime.rebuild(doc)
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
        if 'depth' in payload:
            feature['depth'] = model.number(payload['depth'],positive=True)
        if 'enabled' in payload:
            if not isinstance(payload['enabled'],bool):
                raise BadPayload('enabled debe ser booleano')
            feature['enabled'] = payload['enabled']
    return runtime.transaction(payload,change,'CAD editar extrusión')


@command('cad.feature.delete')
def feature_delete(payload):
    def change(doc):
        feature=model.find(doc,'features',payload.get('feature_id'))
        _require_no_dependents(doc,feature['id'])
        doc['features'].remove(feature)
    runtime.transaction(payload,change,'CAD eliminar extrusión')
    runtime.selection = None
    return runtime.status()


@command('cad.convert')
def convert(payload):
    runtime.require_workspace()
    if runtime.session:
        raise CommandError('Confirma o cancela antes de convertir',code='session_active')
    doc = runtime.doc()
    feature = model.find(doc,'features',payload.get('feature_id'))
    _require_no_dependents(doc,feature['id'])
    objs = [o for o in runtime.objects(doc) if o[FEATURE_KEY]==feature['id']]
    if not objs:
        raise CommandError('Activa la extrusión antes de convertirla',code='cad_reference_missing')
    _activate_feature(doc,feature['id'])
    for obj in objs:
        del obj[FEATURE_KEY]
        del obj[DOC_KEY]
    doc['features'].remove(feature)
    runtime.persist(doc, advance=True)
    runtime.leave()
    undo_push('CAD convertir a malla')
    runtime.selection = None
    return runtime.status()


def _require_no_dependents(doc, identifier):
    if any(f.get('target_id')==identifier for f in doc['features']) or any(s.get('support_id')==identifier for s in doc['sketches']):
        raise CommandError('El sólido tiene bocetos o vaciados dependientes',code='cad_dependency')


def _refs():
    selection=runtime.selection or {}
    return selection.get('items',[selection] if selection else [])


def _pick(payload):
    u,v=model.number(payload.get('u')),model.number(payload.get('v'))
    from ..bpy_utils import find_view3d
    found=find_view3d()
    aspect=found[2].width/max(found[2].height,1) if found else 1.
    candidates=[]
    for item in runtime.overlay(runtime.doc()):
        ring=item['points']
        if runtime.active_sketch_id:
            for handle in item.get('handles',[]):
                p=handle['point']; distance=math.hypot((u-p[0])*aspect,v-p[1])
                if distance<.024:
                    candidates.append((0,distance,dict(kind='ENTITY',id=item['id'],part=handle['part'])))
        elif item['closed'] and model.contains(ring,(u,v)):
            area=abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(ring,ring[1:]+ring[:1])))
            candidates.append((0,area,dict(kind='PROFILE',id='profile_'+item['id'])))
        for index,(a,b) in enumerate(zip(ring,ring[1:]+(ring[:1] if item['closed'] else []))):
            dx,dy=(b[0]-a[0])*aspect,b[1]-a[1]
            t=max(0,min(1,((u-a[0])*aspect*dx+(v-a[1])*dy)/max(dx*dx+dy*dy,1e-20)))
            distance=math.hypot((u-a[0])*aspect-t*dx,v-a[1]-t*dy)
            if distance<.024 and runtime.active_sketch_id:
                _,e=model.entity(runtime.doc(),item['id'])
                part='EDGE'+str(index) if e['type']=='RECTANGLE' else 'BODY'
                candidates.append((1,distance,dict(kind='ENTITY',id=item['id'],part=part)))
    return min(candidates,key=lambda c:c[:2])[2] if candidates else None


def _set_selection(refs):
    runtime.selection=dict(refs[-1],items=refs) if refs else None


@command('cad.select')
def select(payload):
    runtime.require_workspace()
    if runtime.session: raise CommandError('Termina la preview antes de seleccionar',code='session_active')
    doc=runtime.doc(); identifier=payload.get('id'); kind=str(payload.get('kind','')).upper()
    if identifier:
        ref=dict(kind=kind,id=identifier,part=payload.get('part','BODY'))
        if kind=='ENTITY':
            sketch,e=model.entity(doc,identifier)
            if sketch['id']!=runtime.active_sketch_id: raise BadPayload('Abre el boceto antes de seleccionar sus entidades')
        elif kind=='PROFILE': model.profile(doc,identifier)
        elif kind=='FEATURE':
            model.find(doc,'features',identifier); _activate_feature(doc,identifier)
        else: raise BadPayload('Selección CAD no compatible')
    else: ref=_pick(payload)
    refs=copy.deepcopy(_refs()) if payload.get('additive') else []
    if ref:
        old=next((r for r in refs if r['id']==ref['id'] and r.get('part')==ref.get('part')),None)
        if old: refs.remove(old)
        else: refs.append(ref)
    _set_selection(refs)
    return runtime.status()


@command('cad.settings')
def settings(payload):
    runtime.require_workspace()
    if runtime.session: runtime.require(payload)
    if 'step' in payload: runtime.step=model.number(payload['step'],positive=True)
    if 'increment' in payload:
        if not isinstance(payload['increment'],bool): raise BadPayload('increment debe ser booleano')
        runtime.increment=payload['increment']
    return runtime.status()


@command('cad.drag.begin')
def drag_begin(payload):
    runtime.require_workspace()
    if not runtime.active_sketch_id: raise BadPayload('Abre un boceto para mover sus puntos')
    hit=_pick(payload)
    if hit is None: return runtime.status()
    refs=copy.deepcopy(_refs())
    if not any(r['id']==hit['id'] and r.get('part')==hit.get('part') for r in refs): refs=[hit]
    sketch=model.find(runtime.doc(),'sketches',runtime.active_sketch_id)
    start=runtime.point(payload,sketch['plane'])
    session=runtime.begin(payload,'DRAG')
    session.update(sketch_id=sketch['id'],refs=refs,start=start)
    _set_selection(refs)
    return runtime.status()


@command('cad.drag.update')
def drag_update(payload):
    if not runtime.session: return runtime.status()
    session=runtime.require(payload)
    if session['operation']!='DRAG': raise BadPayload('La sesión no es de arrastre')
    doc=copy.deepcopy(session['baseline']); sketch=model.find(doc,'sketches',session['sketch_id'])
    p=runtime.point(payload,sketch['plane']); dx,dy=[p[i]-session['start'][i] for i in (0,1)]
    if runtime.increment: dx,dy=[round(d/runtime.step)*runtime.step for d in (dx,dy)]
    try:
        geometry.solve(sketch,geometry.move_goals(sketch,session['refs'],dx,dy),drag=True)
        runtime.rebuild(doc)
    except CommandError:
        # Keep the last visible valid preview. END never retries the pointer.
        raise
    baseline=model.find(session['baseline'],'sketches',sketch['id'])
    changed=any(abs(e[k]-original[k])>(1e-7 if k in ('start','sweep') else 1e-9)
                for e,original in zip(sketch['entities'],baseline['entities']) for k in model.FIELDS[e['type']])
    session.update(preview=doc,candidate=sketch['id'] if changed else None)
    return runtime.status()


@command('cad.drag.end')
def drag_end(payload):
    if not runtime.session: return runtime.status()
    session=runtime.require(payload)
    if session['operation']!='DRAG': raise BadPayload('La sesión no es de arrastre')
    if session.get('candidate'): return confirm(payload)
    runtime.session=None
    return runtime.status()


@command('cad.constraint.add')
def constraint_add(payload):
    typ=str(payload.get('type','')).upper()
    def change(doc):
        sketch=model.find(doc,'sketches',runtime.active_sketch_id)
        refs=[{k:r[k] for k in ('id','part') if k in r} for r in _refs() if r['kind']=='ENTITY']
        c=dict(id=model.uid('constraint'),type=typ,refs=refs)
        if typ in ('DISTANCE','RADIUS'): c['value']=model.number(payload.get('value'),positive=True)
        if typ=='FIX' and len(refs)==1:
            e=geometry.get_entity(sketch,refs[0]); c['values']={k:e[k] for k in model.FIELDS[e['type']]}
        sketch.setdefault('constraints',[]).append(c)
        geometry.solve(sketch)
    return runtime.transaction(payload,change,'CAD restringir boceto')


@command('cad.constraint.delete')
def constraint_delete(payload):
    def change(doc):
        sketch=model.find(doc,'sketches',runtime.active_sketch_id)
        constraints=sketch.setdefault('constraints',[])
        constraints.remove(model.find(sketch,'constraints',payload.get('constraint_id')))
    return runtime.transaction(payload,change,'CAD quitar restricción')


@command('cad.fillet')
def fillet(payload):
    def change(doc):
        sketch=model.find(doc,'sketches',runtime.active_sketch_id)
        geometry.fillet(sketch,_refs(),model.number(payload.get('radius'),positive=True))
    return runtime.transaction(payload,change,'CAD redondear esquina')


@command('cad.constraint.set')
def constraint_set(payload):
    def change(doc):
        sketch=model.find(doc,'sketches',runtime.active_sketch_id)
        c=model.find(sketch,'constraints',payload.get('constraint_id'))
        if c['type'] not in ('RADIUS','DISTANCE'): raise BadPayload('Esta restricción no tiene una cota editable')
        c['value']=model.number(payload.get('value'),positive=True)
        geometry.solve(sketch)
    return runtime.transaction(payload,change,'CAD editar restricción')


@command('cad.sketch.delete')
def sketch_delete(payload):
    identifier=payload.get('sketch_id')
    def change(doc):
        if any(f['sketch_id']==identifier for f in doc['features']):
            raise CommandError('Elimina primero las operaciones del boceto',code='cad_dependency')
        doc['sketches'].remove(model.find(doc,'sketches',identifier))
    runtime.transaction(payload,change,'CAD eliminar boceto')
    if runtime.active_sketch_id==identifier: runtime.active_sketch_id=None
    runtime.selection=None
    return runtime.status()
