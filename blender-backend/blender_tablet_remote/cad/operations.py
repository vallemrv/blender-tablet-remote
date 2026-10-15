"""Parameters and tray descriptors for new CAD features, independent of Compose."""
from . import document as model, holes
from ..errors import BadPayload

TYPES=('HOLE',)
LABELS={'HOLE':'Taladro'}


def validate(doc, feature):
    if feature['type']=='HOLE': return holes.validate(doc,feature)
    raise ValueError('Unsupported feature')


def update(doc, feature, payload):
    if 'enabled' in payload:
        if not isinstance(payload['enabled'],bool): raise BadPayload('enabled debe ser booleano')
        feature['enabled']=payload['enabled']
    fields=holes.FIELDS if feature['type']=='HOLE' else ()
    for key in fields:
        if key in payload: feature[key]=payload[key]
    return validate(doc,feature)


def number(feature, key, label, step, minimum=1e-7, unit='LENGTH', maximum=10000):
    return dict(key=key,label=label,type='NUMBER',value=feature.get(key,0),step=step,min=minimum,max=maximum,unit=unit)


def select(feature, key, label, options):
    return dict(key=key,label=label,type='ENUM',value=feature.get(key),options=[dict(id=k,label=v) for k,v in options.items()])


def controls(doc, feature, step):
    fields=[]; typ=feature['type']
    if typ=='HOLE':
        fields=[select(feature,'size','Métrica',{s:s.replace('.',',') for s in holes.TABLE}),select(feature,'kind','Tipo',holes.KINDS)]
        if feature['kind']!='INSERT':
            fields.append(select(feature,'extent','Alcance',{'THROUGH_ALL':'Perforar todo','ONE':'Profundidad'}))
            if feature['extent']=='ONE':fields.append(number(dict(feature,depth=feature.get('depth') or .01),'depth','Profundidad',step))
        fields.append(number(feature,'tolerance','Holgura diametral',.00005,0))
        if feature['kind']=='INSERT':
            measures=holes.measures(feature)
            values=dict(feature,insert_diameter=measures['insert_diameter']-feature['tolerance'],insert_depth=measures['insert_depth'])
            fields.extend(number(values,k,label,step) for k,label in (('insert_diameter','Ø inserto'),('insert_depth','Prof. inserto')))
        sketch=model.find(doc,'sketches',feature['sketch_id'])
        fields.append(dict(key='point_ids',label='Puntos',type='MULTI',value=feature.get('point_ids'),
                           options=[dict(id=e['id'],label=f'Punto {i+1}') for i,e in enumerate(sketch['entities']) if e['type'] in ('POINT','CIRCLE')]))
    return dict(id=feature['id'],type=typ,label=LABELS[typ],fields=fields)
