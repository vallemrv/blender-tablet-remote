"""Patterns of feature operands, by stable IDs and captured metric axes."""
import math
from . import document as model
from ..errors import BadPayload, CommandError

FIELDS=('source_ids','kind','direction','count','spacing','direction2','count2','spacing2','symmetric','axis','axis_origin','angle')
AXES={'X':[1.,0.,0.],'Y':[0.,1.,0.],'Z':[0.,0.,1.]}


def direction(value):
    if isinstance(value,str) and value in AXES:return AXES[value]
    if not isinstance(value,list) or len(value)!=2:raise BadPayload('Elige un eje o una arista recta')
    a,b=value
    if not all(isinstance(p,list) and len(p)==3 for p in (a,b)):raise BadPayload('Arista de dirección inválida')
    d=[model.number(b[i])-model.number(a[i]) for i in range(3)]
    n=math.sqrt(sum(v*v for v in d))
    if n<1e-9:raise BadPayload('La arista necesita longitud')
    return [v/n for v in d]


def axis(feature):
    value=feature.get('axis','Z')
    if isinstance(value,str) and value in AXES:return model.validate_face(dict(origin=feature.get('axis_origin',[0.,0.,0.]),normal=AXES[value]))
    return model.validate_face(value)


def validate(doc, feature):
    ids=feature.get('source_ids')
    if not isinstance(ids,list) or not ids or not all(isinstance(i,str) for i in ids) or len(set(ids))!=len(ids):
        raise BadPayload('Selecciona operaciones distintas para repetir')
    order={n['id']:i for i,n in enumerate(model.history(doc))}
    for identifier in ids:
        source=model.find(doc,'features',identifier)
        if source['type'] not in ('EXTRUDE','CUT','HOLE') or source['body_id']!=feature['body_id'] or order[source['id']]>=order.get(feature.get('id'),len(order)):
            raise CommandError('Patrón requiere extrusiones, vaciados o taladros anteriores del mismo cuerpo',code='cad_dependency')
    if feature.get('kind') not in ('LINEAR','CIRCULAR'):raise BadPayload('Patrón lineal o circular')
    for key in ('count','count2'):
        n=model.number(feature.get(key,2))
        if int(n)!=n or not 2<=n<=100:raise BadPayload('Número de copias: de 2 a 100')
        feature[key]=int(n)
    if not isinstance(feature.get('symmetric',False),bool):raise BadPayload('Simetría inválida')
    if feature['kind']=='LINEAR':
        direction(feature['direction']);feature['spacing']=model.number(feature['spacing'],positive=True)
        if feature.get('direction2')=='NONE':feature['direction2']=None
        if feature.get('direction2') is not None:
            direction(feature['direction2']);feature['spacing2']=model.number(feature['spacing2'],positive=True)
    else:
        axis(feature);feature['angle']=model.number(feature['angle'],positive=True)
        if feature['angle']>360:raise BadPayload('Ángulo máximo: 360°')
    return feature


def active(doc, feature):
    return feature['enabled'] and all(model.find(doc,'features',i)['enabled'] for i in feature['source_ids'])


def copies(feature):
    """Yield transforms excluding the existing source; count includes that source."""
    n=feature['count']
    if feature['kind']=='CIRCULAR':
        step=feature['angle']/(n if feature['angle']==360 else n-1)
        for i in range(1,n):yield dict(axis=axis(feature),angle=i*step)
        return
    def indices(count):return range(-(count//2),(count-1)//2+1) if feature.get('symmetric') else range(count)
    a=direction(feature['direction']);second=feature.get('direction2')
    b=direction(second) if second else [0.,0.,0.]
    for i in indices(n):
        for j in indices(feature['count2']) if second else (0,):
            if i or j:yield dict(translation=[i*feature['spacing']*a[k]+j*feature.get('spacing2',0)*b[k] for k in range(3)])
