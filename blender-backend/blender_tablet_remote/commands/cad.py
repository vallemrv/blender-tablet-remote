"""cad.*: intent commands; all geometry and bpy run in the bridge pump."""
import copy
import math
import bpy
from . import command
from ..cad import document as model
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
        sketch = dict(id=model.uid('sketch'),name='Sketch '+str(len(doc['sketches'])+1),plane=plane,entities=[])
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


@command('cad.entity.begin')
def entity_begin(payload):
    typ = str(payload.get('type','')).upper()
    if typ not in model.TYPES:
        raise BadPayload('Tipo de entidad CAD no compatible')
    sketch = model.find(runtime.doc(),'sketches',runtime.active_sketch_id)
    start = runtime.point(payload,sketch['plane'])
    session = runtime.begin(payload,typ)
    session.update(sketch_id=sketch['id'],start=start,entity_id=model.uid('entity'))
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
    e = dict(id=session['entity_id'],type=session['operation'],x=x,y=y)
    if e['type']=='RECTANGLE':
        e.update(x=min(x,x2),y=min(y,y2),width=abs(x2-x),height=abs(y2-y))
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
    session['preview'] = doc
    session['candidate'] = e['id']
    runtime.selection = dict(kind='ENTITY',id=e['id'])
    return runtime.status()


@command('cad.entity.set')
def entity_set(payload):
    changes = payload.get('values')
    if not isinstance(changes,dict) or not changes:
        raise BadPayload('Faltan las dimensiones')
    def change(doc):
        _, e = model.entity(doc,payload.get('entity_id'))
        allowed = set(e)-{'id','type'}
        if not set(changes)<=allowed:
            raise BadPayload('Dimensión no compatible con la entidad')
        e.update(changes)
        model.validate_entity(e)
    return runtime.transaction(payload,change,'CAD editar dimensiones')


@command('cad.entity.delete')
def entity_delete(payload):
    def change(doc):
        sketch,e = model.entity(doc,payload.get('entity_id'))
        if any(f['sketch_id']==sketch['id'] for f in doc['features']):
            raise CommandError('El sketch tiene extrusiones; elimina primero sus features',code='cad_dependency')
        sketch['entities'].remove(e)
    result = runtime.transaction(payload,change,'CAD eliminar entidad')
    runtime.selection = None
    return runtime.status()


@command('cad.extrude.begin')
def extrude_begin(payload):
    depth = model.number(payload.get('depth',.02),positive=True)
    doc = runtime.doc()
    sketch,e = model.profile(doc,payload.get('profile_id'))
    session = runtime.begin(payload,'EXTRUDE')
    feature = dict(id=model.uid('feature'),name='Extrusión '+str(len(doc['features'])+1),
                   type='EXTRUDE',sketch_id=sketch['id'],profile_id='profile_'+e['id'],depth=depth,enabled=True)
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
    if session['operation']!='EXTRUDE':
        raise CommandError('La sesión no es una extrusión',code='wrong_tool')
    depth = model.number(payload.get('depth'),positive=True)
    preview = copy.deepcopy(session['preview'])
    model.find(preview,'features',session['feature_id'])['depth'] = depth
    runtime.rebuild(preview)
    session.update(preview=preview,depth=depth)
    return runtime.status()


@command('cad.session.confirm')
def confirm(payload):
    session = runtime.require(payload)
    if not session['candidate']:
        raise CommandError('Dibuja una entidad válida antes de confirmar',code='cad_empty_preview')
    doc = session['preview']
    runtime.rebuild(doc)
    runtime.persist(doc, advance=True)
    runtime.session = None
    if session['operation'] == 'EXTRUDE':
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
        doc['features'].remove(model.find(doc,'features',payload.get('feature_id')))
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


@command('cad.select')
def select(payload):
    runtime.require_workspace()
    doc = runtime.doc()
    kind = str(payload.get('kind','')).upper()
    identifier = payload.get('id')
    if identifier:
        if kind=='ENTITY':
            model.entity(doc,identifier)
        elif kind=='PROFILE':
            model.profile(doc,identifier)
        elif kind=='FEATURE':
            model.find(doc,'features',identifier)
            _activate_feature(doc,identifier)
        else:
            raise BadPayload('Selección CAD no compatible')
        runtime.selection = dict(kind=kind,id=identifier)
    else:
        u,v = model.number(payload.get('u')),model.number(payload.get('v'))
        runtime.selection = None
        overlay = runtime.overlay(doc)
        candidates = []
        for item in overlay:
            ring = item['points']
            if not runtime.active_sketch_id and item['closed'] and model.contains(ring,(u,v)):
                area = abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(ring,ring[1:]+ring[:1])))
                candidates.append((area,'PROFILE','profile_'+item['id']))
            else:
                for a,b in zip(ring,ring[1:]+(ring[:1] if item['closed'] else [])):
                    dx,dy=b[0]-a[0],b[1]-a[1]
                    t=max(0,min(1,((u-a[0])*dx+(v-a[1])*dy)/max(dx*dx+dy*dy,1e-20)))
                    distance=math.hypot(u-a[0]-t*dx,v-a[1]-t*dy)
                    if distance<.03:
                        candidates.append((distance,'ENTITY',item['id']))
        if candidates:
            _,kind,identifier=min(candidates)
            runtime.selection=dict(kind=kind,id=identifier)
    return runtime.status()
