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
    try:operations.update(session['baseline'],feature,capture_parameters(session['baseline'],feature,payload))
    except CommandError as exc:
        session.update(candidate=None,error=exc.message)
        return runtime.status()
    if feature==session['feature'] and session.get('candidate'):return runtime.status()
    yield from preview(session,feature)
    return runtime.status()


@command('cad.pattern.begin')
def pattern_begin(payload):
    runtime.require_workspace();doc=runtime.doc()
    ids=payload.get('source_ids') or [payload.get('feature_id')]
    for identifier in ids:cad._require_reachable(doc,identifier)
    source=model.find(doc,'features',ids[0])
    if not all(model.find(doc,'features',i)['enabled'] for i in ids):raise BadPayload('Activa las operaciones fuente')
    feature=dict(type='PATTERN',sketch_id=None,body_id=source['body_id'],source_ids=ids,kind='LINEAR',direction='X',count=4,
                 spacing=.01,direction2=None,count2=2,spacing2=.01,symmetric=False,axis='Z',axis_origin=[0.,0.,0.],angle=360.)
    operations.update(doc,feature,payload)
    return (yield from begin(payload,feature))


def capture_parameters(doc, feature, payload):
    """Geometric directions are captured once under the tap, never by mesh index."""
    from .snap import query_cad_surface
    from ..cad.runtime import BODY_KEY
    from mathutils import Vector
    import bpy
    keys=[k for k in ('pick_direction','pick_direction2','pick_axis','pick_cylinder') if payload.get(k)]
    if not keys:return payload
    if feature['type']!='PATTERN':raise BadPayload('La operación no usa un eje de patrón')
    key=keys[0];item=query_cad_surface(payload,'FACE' if key=='pick_cylinder' else 'EDGE')
    if item is None:raise BadPayload('Toca una arista recta o una cara cilíndrica')
    obj=next((o for o in runtime.objects(doc) if o.get(BODY_KEY)==feature['body_id']),None)
    if obj is None:raise BadPayload('No se encuentra el cuerpo del patrón')
    inverse=obj.matrix_world.inverted_safe();scale=bpy.context.scene.unit_settings.scale_length
    points=[inverse@Vector(p) for p in item['points']]
    if key=='pick_cylinder':
        import numpy as np
        if item['planar'] or len(points)<6:raise BadPayload('Selecciona la pared de un cilindro')
        normals=[]
        for a,b,c in item['triangles']:
            a,b,c=(inverse@Vector(p) for p in (a,b,c))
            n=(b-a).cross(c-a)
            if n.length>1e-12:normals.append(list(n.normalized()))
        if len(normals)<3:raise BadPayload('La cara no describe un cilindro')
        ns=np.asarray(normals);values,vectors=np.linalg.eigh(ns.T@ns)
        if values[1]<1e-5 or values[0]>values[1]*1e-5:raise BadPayload('La cara no es cilíndrica')
        axis=Vector(vectors[:,0]);reference=max(range(3),key=lambda i:abs(axis[i]))
        if axis[reference]<0:axis=-axis
        x=axis.orthogonal().normalized();y=axis.cross(x);center=sum(points,Vector())/len(points)
        xy=np.array([((p-center).dot(x),(p-center).dot(y)) for p in points])
        a=np.column_stack((2*xy[:,0],2*xy[:,1],np.ones(len(xy))))
        cx,cy,c=np.linalg.lstsq(a,(xy*xy).sum(axis=1),rcond=None)[0]
        r2=c+cx*cx+cy*cy
        if r2<=0 or np.max(np.abs(((xy-[cx,cy])**2).sum(axis=1)-r2))>r2*1e-4:raise BadPayload('La cara no es cilíndrica')
        start=center+x*cx+y*cy;end=start+axis
    else:
        if len(points)<2:raise BadPayload('Toca una arista recta')
        start=points[0];end=max(points,key=lambda p:(p-start).length_squared);axis=end-start
        if axis.length<1e-9 or any((p-start).cross(axis.normalized()).length>axis.length*1e-5+1e-8 for p in points):
            raise BadPayload('El eje necesita una arista recta')
    start=start*scale;end=end*scale
    values=dict(payload)
    if key in ('pick_axis','pick_cylinder'):values['axis']=model.validate_face(dict(origin=list(start),normal=list((end-start).normalized())))
    else:values[key.removeprefix('pick_')]=[list(start),list(end)]
    return values
