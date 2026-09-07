"""Versioned CAD source model. SI metres; no bpy or mesh indices."""
import copy
import json
import math
import uuid
from ..errors import BadPayload, CommandError

VERSION = 1
KEY = 'btr_cad_document'
PLANES = ('XY', 'XZ', 'YZ')
TYPES = ('LINE', 'RECTANGLE', 'CIRCLE')


def uid(prefix):
    return prefix + '_' + uuid.uuid4().hex


def new_document():
    return dict(version=VERSION, revision=0, id=uid('doc'), sketches=[], features=[])


def loads(raw):
    if not raw:
        return new_document()
    try:
        doc = json.loads(raw)
        if not isinstance(doc, dict) or doc.get('version') != VERSION:
            raise ValueError('unsupported version')
        if not isinstance(doc.get('sketches'), list) or not isinstance(doc.get('features'), list):
            raise ValueError('missing collections')
        if not isinstance(doc.get('id'),str) or not doc['id']:
            raise ValueError('invalid document ID')
        ids = {doc['id']}
        if not isinstance(doc.get('revision', 0), int) or doc.get('revision', 0) < 0:
            raise ValueError('invalid revision')
        def unique(value):
            if not isinstance(value, str) or not value or value in ids:
                raise ValueError('duplicate or missing ID')
            ids.add(value)
        for sketch in doc['sketches']:
            unique(sketch['id'])
            if not isinstance(sketch.get('name'),str):
                raise ValueError('invalid sketch name')
            if sketch['plane'] not in PLANES:
                raise ValueError('invalid plane')
            for e in sketch['entities']:
                unique(e['id'])
                validate_entity(e)
        for feature in doc['features']:
            unique(feature['id'])
            if not isinstance(feature.get('name'),str):
                raise ValueError('invalid feature name')
            sketch, _ = profile(doc, feature['profile_id'])
            if feature['type'] != 'EXTRUDE' or sketch['id'] != feature['sketch_id'] or not isinstance(feature['enabled'], bool):
                raise ValueError('invalid feature')
            number(feature['depth'], positive=True)
        return doc
    except (ValueError, TypeError, KeyError, CommandError) as exc:
        raise CommandError('Documento CAD ilegible o versión no compatible', code='cad_document_invalid') from exc


def dumps(doc):
    return json.dumps(doc, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def number(value, *, positive=False):
    if isinstance(value, bool):
        raise BadPayload('La medida debe ser numérica, no booleana')
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise BadPayload('La medida debe ser un número finito') from exc
    if not math.isfinite(value) or abs(value) > 10000 or (positive and value < 1e-7):
        raise BadPayload('Medida fuera de rango (mínimo 0.0001 mm, máximo 10000 m)')
    return value


def find(doc, collection, identifier):
    for item in doc[collection]:
        if item['id'] == identifier:
            return item
    raise CommandError('Referencia CAD inexistente', code='cad_reference_missing')


def entity(doc, identifier):
    for sketch in doc['sketches']:
        for item in sketch['entities']:
            if item['id'] == identifier:
                return sketch, item
    raise CommandError('Entidad CAD inexistente', code='cad_reference_missing')


def profile(doc, identifier):
    for sketch in doc['sketches']:
        for item in sketch['entities']:
            if item['type'] != 'LINE' and 'profile_' + item['id'] == identifier:
                return sketch, item
    raise CommandError('El perfil está abierto o ya no existe', code='cad_profile_invalid')


def profiles(sketch):
    return [dict(id='profile_' + e['id'], entity_id=e['id'],
                 label='Rectángulo' if e['type'] == 'RECTANGLE' else 'Círculo')
            for e in sketch['entities'] if e['type'] != 'LINE']


def outline(e):
    x, y = e['x'], e['y']
    if e['type'] == 'LINE':
        return [(x, y), (e['x2'], e['y2'])]
    if e['type'] == 'RECTANGLE':
        w, h = e['width'], e['height']
        return [(x, y), (x+w, y), (x+w, y+h), (x, y+h)]
    r = e['diameter'] / 2
    return [(x + r*math.cos(i*math.tau/128), y + r*math.sin(i*math.tau/128)) for i in range(128)]


def contains(ring, point):
    x, y = point
    inside = False
    for a, b in zip(ring, ring[1:] + ring[:1]):
        if (a[1] > y) != (b[1] > y) and x < (b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:
            inside = not inside
    return inside


def validate_entity(e):
    if e.get('type') not in TYPES:
        raise BadPayload('Tipo de entidad CAD no compatible')
    fields = {'LINE': ('x','y','x2','y2'), 'RECTANGLE': ('x','y','width','height'),
              'CIRCLE': ('x','y','diameter')}[e['type']]
    for key in fields:
        e[key] = number(e.get(key), positive=key in ('width','height','diameter'))
    if e['type'] == 'LINE' and math.hypot(e['x2']-e['x'], e['y2']-e['y']) < 1e-7:
        raise BadPayload('La línea necesita dos puntos distintos')
    return e


def public(doc):
    result = copy.deepcopy(doc)
    for sketch in result['sketches']:
        sketch['profiles'] = profiles(sketch)
    return result
