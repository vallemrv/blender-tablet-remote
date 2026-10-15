"""Parameters and tray descriptors for new CAD features, independent of Compose."""
from . import document as model, holes, pattern
from ..errors import BadPayload

TYPES=('HOLE','PATTERN')
LABELS={'HOLE':'Taladro','PATTERN':'Patrón'}


def validate(doc, feature):
    if feature['type']=='HOLE': return holes.validate(doc,feature)
    if feature['type']=='PATTERN': return pattern.validate(doc,feature)
    raise ValueError('Unsupported feature')


def update(doc, feature, payload):
    if 'enabled' in payload:
        if not isinstance(payload['enabled'],bool): raise BadPayload('enabled debe ser booleano')
        feature['enabled']=payload['enabled']
    fields={'HOLE':holes.FIELDS,'PATTERN':pattern.FIELDS}.get(feature['type'],())
    for key in fields:
        if key in payload: feature[key]=payload[key]
    if feature['type']=='PATTERN' and any('axis_'+k in payload for k in ('x','y','z')):
        origin=list(feature.get('axis_origin',[0.,0.,0.]))
        for i,k in enumerate(('x','y','z')):
            if 'axis_'+k in payload:origin[i]=model.number(payload['axis_'+k])
        feature['axis_origin']=origin
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
    if typ=='PATTERN':
        fields=[select(feature,'kind','Patrón',{'LINEAR':'Lineal','CIRCULAR':'Circular'}),number(feature,'count','Número',1,2,'SCALAR',100)]
        if feature['kind']=='LINEAR':
            for key,label in (('direction','Dirección'),('direction2','Segunda dirección')):
                value=feature.get(key); options={'NONE':'Sin rejilla'} if key=='direction2' else {}
                options.update({k:'Eje '+k for k in pattern.AXES})
                if isinstance(value,list): options['CAPTURED']='Arista elegida'
                fields.append(select(dict(feature,**{key:'CAPTURED' if isinstance(value,list) else value or 'NONE'}),key,label,options))
                fields.append(dict(key='pick_'+key,label='Tocar arista'+(' 2' if key=='direction2' else ''),type='ACTION'))
            fields.append(number(feature,'spacing','Separación',step))
            fields.append(dict(key='symmetric',label='Ambos lados',type='BOOL',value=feature.get('symmetric',False)))
            if feature.get('direction2'):
                fields.extend([number(feature,'count2','Número 2',1,2,'SCALAR',100),number(feature,'spacing2','Separación 2',step)])
        else:
            fields.append(number(feature,'angle','Ángulo',15,1e-7,'ANGLE',360))
            options={k:'Eje '+k for k in pattern.AXES}
            if isinstance(feature.get('axis'),dict):options['CAPTURED']='Eje elegido'
            fields.append(select(dict(feature,axis='CAPTURED' if isinstance(feature.get('axis'),dict) else feature['axis']),'axis','Eje',options))
            fields.extend([dict(key='pick_axis',label='Tocar arista del eje',type='ACTION'),dict(key='pick_cylinder',label='Tocar cara cilíndrica',type='ACTION')])
            if isinstance(feature.get('axis'),str):
                values={f'axis_{k}':v for k,v in zip(('x','y','z'),feature.get('axis_origin',[0.,0.,0.]))}
                fields.extend(number(values,'axis_'+k,'Centro '+k.upper(),step,-10000) for k in ('x','y','z'))
        allowed=[f for f in doc['features'] if f['body_id']==feature['body_id'] and f['type'] in ('EXTRUDE','CUT','HOLE') and f.get('order',0)<feature['order']]
        fields.append(dict(key='source_ids',label='Operaciones',type='MULTI',all_null=False,value=feature['source_ids'],options=[dict(id=f['id'],label=f['name']) for f in allowed]))
    return dict(id=feature['id'],type=typ,label=LABELS[typ],fields=fields)
