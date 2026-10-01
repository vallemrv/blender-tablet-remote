"""Mirror extrusion/cut operands by stable feature ID, without copying sketches."""
from . import document as model
from ..errors import BadPayload

AXIS = {'YZ': 0, 'XZ': 1, 'XY': 2}


def resolve(doc):
    sequence={node['id']:i for i,node in enumerate(model.history(doc))}
    for feature in doc['features']:
        spec=feature.get('mirror')
        if spec is None:
            if feature['type']=='MIRROR': raise BadPayload('Falta la referencia de la simetría')
            continue
        if feature['type']!='MIRROR': raise BadPayload('La referencia de simetría requiere una operación MIRROR')
        if not isinstance(spec,dict) or spec.get('plane') not in AXIS:
            raise BadPayload('Plano de simetría no válido')
        spec['offset']=model.number(spec.get('offset',0.))
        source=model.find(doc,'features',spec.get('source_id'))
        if (source.get('mirror') or source['type'] not in ('EXTRUDE','CUT')
                or sequence[source['id']]>=sequence[feature['id']]
                or source['body_id']!=feature['body_id']):
            raise BadPayload('La simetría requiere una extrusión o vaciado anterior del mismo cuerpo')
        feature['operation']=source['type']
        for key in ('sketch_id','profile_id','depth','extent'):
            feature[key]=source.get(key,'ONE') if key=='extent' else source[key]
        if source.get('to_face'): feature['to_face']=source['to_face']
        else: feature.pop('to_face',None)
        if source['type']=='CUT': feature['target_id']=source['target_id']


def active(doc, feature):
    return feature['enabled'] and (not feature.get('mirror') or
            model.find(doc,'features',feature['mirror']['source_id'])['enabled'])


def point(value, spec, *, direction=False, scale=1.):
    result=list(value);axis=AXIS[spec['plane']]
    result[axis]=(0. if direction else 2*spec['offset']/scale)-result[axis]
    return tuple(result)


def solid(mesh, spec):
    vertices,faces=mesh
    return [point(v,spec) for v in vertices],[tuple(reversed(f)) for f in faces]
