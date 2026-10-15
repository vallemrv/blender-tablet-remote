"""Metric hole presets and sketch anchors. All persisted lengths are metres."""
from . import document as model
from ..errors import BadPayload, CommandError

# Supplied design presets in mm: clearance, counterbore D/depth, countersink D,
# nut across-flats/height, insert D/depth. Inserts vary by manufacturer.
TABLE = dict(zip(('M2','M2.5','M3','M4','M5','M6'), (
    (2.4,4.4,2.2,4.4,4.,1.6,3.2,4.), (2.9,5.,2.7,5.5,5.,2.,3.6,5.),
    (3.4,6.,3.2,6.9,5.5,2.4,4.,5.7), (4.5,8.,4.4,9.2,7.,3.2,5.6,8.1),
    (5.5,10.,5.4,11.5,8.,4.7,6.4,9.5), (6.6,11.,6.4,13.7,10.,5.2,8.,12.7))))
KINDS = {'THROUGH':'Pasante', 'COUNTERBORE':'Cajeado', 'COUNTERSINK':'Avellanado', 'NUT':'Tuerca hexagonal', 'INSERT':'Inserto'}
FIELDS = ('size','kind','depth','extent','tolerance','point_ids','insert_diameter','insert_depth')


def points(sketch, feature):
    available={e['id']:e for e in sketch['entities'] if e['type'] in ('POINT','CIRCLE')}
    ids=feature.get('point_ids')
    if ids is None: ids=list(available)
    if not isinstance(ids,list) or not ids or len(ids)>100 or not all(isinstance(i,str) for i in ids) or len(set(ids))!=len(ids):
        raise BadPayload('Taladro requiere entre 1 y 100 puntos o centros distintos')
    if any(i not in available for i in ids):
        raise CommandError('No se encuentra un punto utilizado por Taladro',code='cad_dependency')
    return [available[i] for i in ids]


def measures(feature):
    d,cb,h,cs,nut,nh,insert,ih=[v/1000 for v in TABLE[feature['size']]]
    tol=feature['tolerance']
    return dict(diameter=d+tol,head_diameter=cb+tol,head_depth=h,sink_diameter=cs+tol,
                nut_flats=nut+tol,nut_depth=nh,insert_diameter=feature.get('insert_diameter',insert)+tol,
                insert_depth=feature.get('insert_depth',ih))


def validate(doc, feature):
    if feature.get('size') not in TABLE or feature.get('kind') not in KINDS:
        raise BadPayload('Selecciona una métrica y un tipo de taladro válidos')
    if feature.get('extent') not in ('ONE','THROUGH_ALL'): raise BadPayload('Profundidad o Perforar todo')
    feature['tolerance']=model.number(feature.get('tolerance',.0002))
    if feature['tolerance']<0: raise BadPayload('La holgura no puede ser negativa')
    if feature.get('depth') is not None: feature['depth']=model.number(feature['depth'],positive=True)
    if feature['extent']=='ONE' and feature.get('depth') is None: raise BadPayload('Escribe la profundidad del taladro')
    for key in ('insert_diameter','insert_depth'):
        if key in feature: feature[key]=model.number(feature[key],positive=True)
    if feature['kind']=='INSERT': feature['extent']='ONE'
    sketch=model.find(doc,'sketches',feature.get('sketch_id'))
    points(sketch,feature)
    if feature['body_id']!=sketch['body_id']: raise BadPayload('El croquis y el taladro deben pertenecer al mismo cuerpo')
    return feature
