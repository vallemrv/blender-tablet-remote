"""Linked parallel contours of analytic sketch primitives, in metres."""
from . import document as model
from ..errors import BadPayload

TYPES = ('SLOT', 'CIRCLE', 'RECTANGLE')


def rule_for(sketch, identifier):
    return next((c for c in sketch.get('constraints', [])
                 if c['type'] == 'OFFSET' and c['refs'][1]['id'] == identifier), None)


def shape(source, distance):
    result = dict(source)
    typ = source['type']
    if typ == 'SLOT':
        result['width'] += 2 * distance
    elif typ == 'CIRCLE':
        result['diameter'] += 2 * distance
    elif typ == 'RECTANGLE':
        result.update(x=source['x']-distance, y=source['y']-distance,
                      width=source['width']+2*distance, height=source['height']+2*distance)
    else:
        raise BadPayload('Desfase admite ranuras, círculos y rectángulos')
    return result


def distance(rule):
    amount = model.number(rule.get('value'), positive=True)
    if rule.get('side') not in ('INWARD', 'OUTWARD'):
        raise BadPayload('Elige desfase hacia dentro o hacia fuera')
    return amount if rule['side'] == 'OUTWARD' else -amount


def validate(sketch):
    parents = {}
    for rule in sketch.get('constraints', []):
        if rule['type'] != 'OFFSET':
            continue
        refs = rule['refs']
        if len(refs) != 2 or any(r.get('part') != 'BODY' for r in refs):
            raise BadPayload('Desfase requiere dos figuras completas')
        source, target = (model.find(sketch, 'entities', r['id']) for r in refs)
        if source['type'] not in TYPES or target['type'] != source['type']:
            raise BadPayload('Los contornos de desfase deben tener el mismo tipo')
        distance(rule)
        if target['id'] in parents:
            raise BadPayload('Un contorno solo puede tener un desfase de origen')
        parents[target['id']] = source['id']
    for target in parents:
        seen = set()
        while target in parents:
            if target in seen:
                raise BadPayload('Dependencia circular entre contornos')
            seen.add(target)
            target = parents[target]


def set_value(sketch, rule, value):
    from . import sketch as geometry
    rule['value'] = model.number(value, positive=True)
    source = model.find(sketch, 'entities', rule['refs'][0]['id'])
    # Changing thickness moves only the derived contour, not its mother.
    goals = [dict(id=source['id'], field=k, value=source[k]) for k in model.FIELDS[source['type']]]
    geometry.solve(sketch, goals)
