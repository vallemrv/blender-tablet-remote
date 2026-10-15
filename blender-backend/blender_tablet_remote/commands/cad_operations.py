"""Snapshot previews for catalogued CAD operations. Geometry stays in the worker."""
import copy
from . import command
from . import cad
from ..cad import document as model, operations
from ..cad.runtime import runtime
from ..errors import BadPayload, CommandError


def preview(session, feature):
    doc=copy.deepcopy(session['baseline'])
    doc['features'].append(feature)
    if session.get('bar'): model.insert_after(doc,feature,session['bar'])
    session.update(preview=doc,feature=feature,candidate=None,error=None)
    try:
        operations.validate(doc,feature)
        yield from runtime.rebuild_steps(doc,limit=feature['id'] if session.get('bar') else None)
    except CommandError as exc:
        if exc.code in ('cad_cancelled','cad_kernel_missing'): raise
        session['error']=exc.message
    else: session['candidate']=feature['id']


def begin(payload, feature):
    doc=runtime.doc();bar=runtime.bar(doc)
    feature.update(id=model.uid('feature'),name=operations.LABELS[feature['type']]+' '+str(len(doc['features'])+1),
                   enabled=True,order=model.next_order(doc))
    operations.validate(doc,feature)
    session=runtime.begin(payload,feature['type']);session.update(feature_id=feature['id'],bar=bar,at_bar=bool(bar))
    try: yield from preview(session,feature)
    except Exception:
        runtime.cancel();raise
    runtime.surface.clear();runtime.selection=dict(kind='FEATURE',id=feature['id'])
    runtime.solid_view()
    return runtime.status()


@command('cad.hole.begin')
def hole_begin(payload):
    runtime.require_workspace()
    doc=runtime.doc();sketch=model.find(doc,'sketches',payload.get('sketch_id'))
    cad._require_reachable(doc,sketch['id'])
    feature=dict(type='HOLE',sketch_id=sketch['id'],body_id=sketch['body_id'],size='M3',kind='THROUGH',
                 point_ids=None,depth=.01,extent='THROUGH_ALL',tolerance=.0002)
    operations.update(doc,feature,payload)
    return (yield from begin(payload,feature))


@command('cad.operation.update')
def operation_update(payload):
    session=runtime.require(payload)
    if session['operation'] not in operations.TYPES: raise BadPayload('La sesión no admite estos parámetros')
    feature=copy.deepcopy(session['feature'])
    try:operations.update(session['baseline'],feature,payload)
    except CommandError as exc:
        session.update(candidate=None,error=exc.message)
        return runtime.status()
    if feature==session['feature'] and session.get('candidate'):return runtime.status()
    yield from preview(session,feature)
    return runtime.status()
