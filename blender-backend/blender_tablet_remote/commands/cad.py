"""cad.*: intent commands; all geometry and bpy run in the bridge pump."""
import copy
import math
import bpy
from . import command
from ..cad import document as model
from ..cad import sketch as geometry
from ..cad import dimensions
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
        sketch = dict(id=model.uid('sketch'),name='Boceto '+str(len(doc['sketches'])+1),plane=plane_local,
                      offset=offset,entities=[],constraints=[],visible=True,body_id=payload.get('body_id') or runtime.active_body_id or doc['bodies'][0]['id'])
        model.find(doc,'bodies',sketch['body_id'])
        if payload.get('plane_id'):
            model.find(doc,'planes',payload['plane_id']); sketch['plane_id']=payload['plane_id']
        if support_id: sketch['support_id']=support_id
        if payload.get('reference_sketch_id'):
            source=model.find(doc,'sketches',payload['reference_sketch_id'])
            for key in ('plane','offset','plane_id','support_id'):
                if key in source: sketch[key]=source[key]
        doc['sketches'].append(sketch)
        model.resolve_supports(doc)
        runtime.active_body_id=sketch['body_id']
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
    runtime.active_body_id = sketch.get('body_id')
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
    start = runtime.point(payload,sketch)
    anchor=_endpoint(payload,sketch) if typ=='LINE' else None
    if anchor: start=geometry.point(sketch,dict(id=anchor['entity_id'],part=anchor['part']))
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
    x2,y2 = runtime.point(payload,sketch)
    endpoint=_endpoint(payload,sketch,session.get('endpoint')) if session['operation']=='LINE' else None
    session['endpoint']=endpoint
    if endpoint: x2,y2=geometry.point(sketch,dict(id=endpoint['entity_id'],part=endpoint['part']))
    e = dict(id=session['entity_id'],type=session['operation'],x=x,y=y,construction=runtime.construction)
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
        allowed = set(model.FIELDS[e['type']]) | ({'length'} if e['type']=='LINE' else set())
        if not set(changes)<=allowed:
            raise BadPayload('Dimensión no compatible con la entidad')
        values={k:model.number(v) for k,v in changes.items()}
        goals=dimensions.set_values(sketch,e,values)
        geometry.solve(sketch,goals)
    return runtime.transaction(payload,change,'CAD editar dimensiones')


@command('cad.entity.construction')
def entity_construction(payload):
    value=payload.get('construction')
    if not isinstance(value,bool): raise BadPayload('construction debe ser booleano')
    def change(doc):
        sketch=model.find(doc,'sketches',runtime.active_sketch_id)
        refs=[r for r in _refs() if r['kind']=='ENTITY' and r['id']!='ORIGIN']
        if not refs: raise BadPayload('Selecciona geometría del boceto')
        for ref in refs: geometry.get_entity(sketch,ref)['construction']=value
    return runtime.transaction(payload,change,'CAD geometría de construcción')


@command('cad.sketch.visibility')
def sketch_visibility(payload):
    value=payload.get('visible')
    if not isinstance(value,bool): raise BadPayload('visible debe ser booleano')
    def change(doc): model.find(doc,'sketches',payload.get('sketch_id'))['visible']=value
    return runtime.transaction(payload,change,'CAD visibilidad de boceto')


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
        geometry.delete_selected(sketch,refs)
        for feature in doc['features']:
            if feature['sketch_id']==sketch['id']:
                try: model.profile(doc,feature['profile_id'])
                except CommandError as exc:
                    raise CommandError('El borrado abriría un perfil utilizado; elimina primero su operación CAD',code='cad_dependency') from exc
    runtime.transaction(payload,change,'CAD borrar selección')
    runtime.selection=None
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
                   type=operation,sketch_id=sketch['id'],profile_id='profile_'+e['id'],depth=depth,enabled=True,body_id=target['body_id'] if target else sketch['body_id'])
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
    objs = [o for o in runtime.objects(doc) if o[FEATURE_KEY]==feature['id']]
    if not objs or not feature['enabled']:
        raise CommandError('Activa la operación antes de crear su malla',code='cad_reference_missing')
    copies=[]
    for obj in objs:
        mesh=obj.copy(); mesh.data=obj.data.copy(); mesh.name=obj.name+' · malla'
        del mesh[FEATURE_KEY]; del mesh[DOC_KEY]
        mesh.hide_viewport=False; mesh.hide_render=False
        bpy.context.scene.collection.objects.link(mesh)
        copies.append(mesh)
    # Export a snapshot for Edit while retaining the entire parametric document.
    runtime.leave()
    for obj in bpy.context.view_layer.objects: obj.select_set(False)
    for obj in copies: obj.select_set(True)
    bpy.context.view_layer.objects.active=copies[-1]
    undo_push('CAD crear copia de malla')
    runtime.selection = None
    return runtime.status()


def _require_no_dependents(doc, identifier):
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
    candidates=[]
    for item in runtime.overlay(runtime.doc()):
        if item.get('kind')=='DIMENSION': continue
        ring=item['points']
        if runtime.active_sketch_id:
            for handle in item.get('handles',[]):
                p=handle['point']; distance=math.hypot((u-p[0])*aspect,v-p[1])
                if distance<.024:
                    candidates.append((0,distance+(1e-8 if item['id']=='ORIGIN' else 0),dict(kind='ENTITY',id=item['id'],part=handle['part'])))
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


def _covers(selected, hit):
    if selected['id']!=hit['id']: return False
    part=selected.get('part','BODY'); target=hit.get('part','BODY')
    if part=='BODY' or part==target: return True
    if part.startswith('EDGE') and target.startswith('P'):
        index=int(part[4:])
        return target in ('P'+str(index),'P'+str((index+1)%4))
    return False


def _toggle_refs(refs, hit):
    if hit is None: return []
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
    sketch=model.find(runtime.doc(),'sketches',runtime.active_sketch_id)
    _set_selection([dict(kind='ENTITY',id=e['id'],part='BODY') for e in sketch['entities']] if action=='SELECT' else [])
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
        elif kind=='PROFILE': model.profile(doc,identifier)
        elif kind=='FEATURE':
            model.find(doc,'features',identifier); _activate_feature(doc,identifier)
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
    if hit and not any(_covers(r,hit) for r in refs): refs=[hit]
    start=runtime.point(payload,sketch) if hit else None
    session=runtime.begin(payload,'DRAG')
    session.update(sketch_id=sketch['id'],refs=refs,start=start,hit=hit,
                   selection_before=selection_before,dragged=False)
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
    if not session.get('dragged'):
        previous=session.get('selection_before') or {}
        refs=previous.get('items',[previous] if previous else [])
        _set_selection(_toggle_refs(refs,session.get('hit')))
    runtime.session=None
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
        c=dict(id=model.uid('constraint'),type=typ,refs=refs)
        if typ in ('DISTANCE','RADIUS'): c['value']=model.number(payload.get('value'),positive=True)
        if typ=='MIDPOINT' and len(refs)==2:
            refs.sort(key=lambda r: 0 if r.get('part') in geometry.handles(geometry.get_entity(sketch,r)) else 1)
        if typ=='FIX':
            if not refs or any(r['id']=='ORIGIN' for r in refs): raise BadPayload('Selecciona geometría; el origen ya está fijo')
            for ref in refs:
                e=geometry.get_entity(sketch,ref); part=ref.get('part','BODY')
                fixed=dict(id=model.uid('constraint'),type='FIX',refs=[ref])
                if part in geometry.handles(e): fixed['points']={part:list(geometry.handles(e)[part])}
                elif e['type']=='RECTANGLE' and part.startswith('EDGE'):
                    index=int(part[4:]); roles=['P'+str(index),'P'+str((index+1)%4)]
                    fixed['points']={role:list(geometry.handles(e)[role]) for role in roles}
                else: fixed['values']={k:e[k] for k in model.FIELDS[e['type']]}
                sketch.setdefault('constraints',[]).append(fixed)
        elif typ in dimensions.NUMERIC:
            c=dimensions.put(sketch,c)
        else: sketch.setdefault('constraints',[]).append(c)
        if typ in dimensions.NUMERIC: dimensions.solve_dimension(sketch,c)
        else: geometry.solve(sketch)
    return runtime.transaction(payload,change,'CAD restringir boceto')


@command('cad.constraint.delete')
def constraint_delete(payload):
    def change(doc):
        sketch=model.find(doc,'sketches',payload.get('sketch_id') or runtime.active_sketch_id)
        c=model.find(sketch,'constraints',payload.get('constraint_id'))
        dimensions.remove(sketch,c)
    return runtime.transaction(payload,change,'CAD quitar restricción')


@command('cad.fillet')
def fillet(payload):
    created=[]
    def change(doc):
        sketch=model.find(doc,'sketches',runtime.active_sketch_id)
        previous={p['id'] for p in model.profiles(sketch)}
        arc=geometry.fillet(sketch,_refs(),model.number(payload.get('radius'),positive=True))
        created.append(arc['id'])
        current=model.closed_entities(sketch)
        replacement=next((p for p in current if arc['id'] in p.get('members',[])),None)
        remaining={'profile_'+p['id'] for p in current}
        for f in doc['features']:
            if f['sketch_id']==sketch['id'] and f['profile_id'] in previous-remaining:
                if replacement is None: raise BadPayload('El redondeo debe conservar cerrado el perfil de la operación')
                f['profile_id']='profile_'+replacement['id']
    runtime.transaction(payload,change,'CAD redondear esquina')
    _set_selection([dict(kind='ENTITY',id=created[0],part='BODY')])
    return runtime.status()


@command('cad.fillet.remove')
def fillet_remove(payload):
    def change(doc):
        sketch,arc=model.entity(doc,payload.get('entity_id'))
        old_profiles=model.closed_entities(sketch)
        geometry.remove_fillet(sketch,arc)
        new_profiles=model.closed_entities(sketch)
        for feature in doc['features']:
            before=next((p for p in old_profiles if 'profile_'+p['id']==feature['profile_id'] and arc['id'] in p.get('members',[])),None)
            if before:
                members=set(before['members'])-{arc['id']}
                after=next((p for p in new_profiles if set(p.get('members',[]))==members),None)
                if after is None: raise BadPayload('No se puede cerrar el perfil al quitar este redondeo')
                feature['profile_id']='profile_'+after['id']
    runtime.transaction(payload,change,'CAD quitar redondeo')
    runtime.selection=None
    return runtime.status()


@command('cad.constraint.set')
def constraint_set(payload):
    def change(doc):
        sketch=model.find(doc,'sketches',payload.get('sketch_id') or runtime.active_sketch_id)
        c=model.find(sketch,'constraints',payload.get('constraint_id'))
        if c['type'] not in ('RADIUS','DISTANCE'): raise BadPayload('Esta restricción no tiene una cota editable')
        updated=dict(c,value=model.number(payload.get('value'),positive=True))
        c=dimensions.put(sketch,updated)
        dimensions.solve_dimension(sketch,c)
    return runtime.transaction(payload,change,'CAD editar restricción')


@command('cad.sketch.delete')
def sketch_delete(payload):
    identifier=payload.get('sketch_id')
    def change(doc):
        if any(f['sketch_id']==identifier for f in doc['features']) or any(p.get('reference_sketch_id')==identifier for p in doc.get('planes',[])):
            raise CommandError('Elimina primero las operaciones del boceto',code='cad_dependency')
        doc['sketches'].remove(model.find(doc,'sketches',identifier))
    runtime.transaction(payload,change,'CAD eliminar boceto')
    if runtime.active_sketch_id==identifier: runtime.active_sketch_id=None
    runtime.selection=None
    return runtime.status()


@command('cad.body.create')
def body_create(payload):
    def change(doc):
        body=dict(id=model.uid('body'),name='Cuerpo '+str(len(doc['bodies'])+1))
        doc['bodies'].append(body); runtime.active_body_id=body['id']
        runtime.active_sketch_id=None; runtime.selection=None
    return runtime.transaction(payload,change,'CAD crear cuerpo')


@command('cad.body.activate')
def body_activate(payload):
    runtime.require_workspace()
    if runtime.session: raise CommandError('Termina la preview antes de cambiar de cuerpo',code='session_active')
    body=model.find(runtime.doc(),'bodies',payload.get('body_id'))
    runtime.active_body_id=body['id']; runtime.active_sketch_id=None; runtime.selection=None
    return runtime.status()


@command('cad.plane.create')
def plane_create(payload):
    def change(doc):
        plane=dict(id=model.uid('plane'),name='Plano '+str(len(doc['planes'])+1),base=payload.get('base','XY'),
                   translation=payload.get('translation',[0,0,0]),rotation=payload.get('rotation',[0,0,0]))
        for key in ('reference_sketch_id','support_id'):
            if payload.get(key): plane[key]=payload[key]
        if 'u' in payload:
            from .snap import query_face_frame
            from mathutils import Vector
            hit=query_face_frame(payload)
            if hit is None: raise BadPayload('Toca una cara plana visible')
            obj=bpy.data.objects[hit['object']]; matrix=obj.matrix_world
            location=Vector(hit['position'])
            vertices=[matrix@Vector(v) for v in hit['vertices']]
            normal=(matrix.to_3x3().inverted().transposed()@Vector(hit['normal'])).normalized()
            tolerance=max((v-vertices[0]).length for v in vertices)*1e-5+1e-9
            if any(abs((v-vertices[0]).dot(normal))>tolerance for v in vertices): raise BadPayload('La cara no es plana')
            x=(vertices[1]-vertices[0]).normalized(); y=normal.cross(x).normalized(); x=y.cross(normal).normalized()
            scale=bpy.context.scene.unit_settings.scale_length
            plane['face_frame']=dict(origin=list(location*scale),x=list(x),y=list(y),normal=list(normal))
        model.validate_plane(plane); doc['planes'].append(plane); model.resolve_supports(doc)
    return runtime.transaction(payload,change,'CAD crear plano')


@command('cad.plane.set')
def plane_set(payload):
    def change(doc):
        plane=model.find(doc,'planes',payload.get('plane_id'))
        for key in ('translation','rotation'):
            if key in payload: plane[key]=payload[key]
        model.validate_plane(plane)
    result=runtime.transaction(payload,change,'CAD colocar plano')
    if runtime.active_sketch_id: runtime.focus(model.find(runtime.doc(),'sketches',runtime.active_sketch_id))
    return runtime.status()
