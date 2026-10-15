"""Associative split bodies. Only source IDs and metric planes are persisted."""
from . import document as model
from ..errors import BadPayload, CommandError

FIELDS=('keep','offset')


def validate(doc, feature):
    model.find(doc,'bodies',feature['body_id'])
    if feature.get('keep') not in ('BOTH','ABOVE','BELOW'):
        raise BadPayload('Conservar: ambas mitades, encima o debajo')
    feature['offset']=model.number(feature.get('offset',0))
    plane=feature.get('plane')
    if isinstance(plane,str): model.find(doc,'planes',plane)
    else: feature['plane']=model.validate_face(plane)
    return feature


def frame(doc, feature):
    plane=feature['plane']
    f=model.find(doc,'planes',plane)['frame'] if isinstance(plane,str) else plane
    return dict(origin=[p+feature.get('offset',0)*n for p,n in zip(f['origin'],f['normal'])],normal=list(f['normal']))


def sync_body(doc, feature):
    children=[b for b in doc['bodies'] if b.get('source',{}).get('feature_id')==feature['id']]
    if feature['keep']=='BOTH':
        if not children:
            doc['bodies'].append(dict(id=feature.setdefault('derived_body_id',model.uid('body')),name=feature['name']+' · encima',
                                     source=dict(feature_id=feature['id'],side='ABOVE')))
    else:
        for body in children:
            require_empty(doc,body)
            doc['bodies'].remove(body)


def require_empty(doc, body):
    identifier=body['id']
    if any(s['body_id']==identifier for s in doc['sketches']) or any(f['body_id']==identifier or f.get('tool_body_id')==identifier for f in doc['features']):
        raise CommandError('La mitad derivada tiene bocetos u operaciones; elimínalos primero',code='cad_dependency')


def validate_sources(doc):
    for body in doc['bodies']:
        source=body.get('source')
        if source is None: continue
        feature=model.find(doc,'features',source.get('feature_id'))
        if feature['type']!='SPLIT' or feature['keep']!='BOTH' or feature['body_id']==body['id'] or source.get('side')!='ABOVE':
            raise BadPayload('Origen del cuerpo derivado inválido')
        if feature.get('derived_body_id')!=body['id']:raise BadPayload('Cuerpo derivado duplicado o inválido')
        if any(n['body_id']==body['id'] and n.get('order',0)<=feature['order'] for n in doc['features']+doc['sketches']):
            raise BadPayload('El cuerpo derivado no puede tener operaciones anteriores al corte')
