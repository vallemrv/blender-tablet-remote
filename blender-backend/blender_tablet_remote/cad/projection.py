"""Explicit conversion of fixed projected curves into closed sketch profiles."""
import math

import numpy as np

from . import document as model, sketch as geometry
from ..errors import BadPayload


def _junction(first, second, p, q, tolerance):
    a, b = first['type'], second['type']
    if a == b == 'LINE':
        return (p+q)*.5
    if a == 'LINE':
        first, second, p, q = second, first, q, p
        a, b = b, a
    center = np.array((first['x'], first['y']))
    radius = first['radius']
    if b == 'LINE':
        start = np.array((second['x'], second['y']))
        direction = np.array((second['x2'], second['y2']))-start
        direction /= np.linalg.norm(direction)
        foot = start+np.dot(center-start, direction)*direction
        distance = np.linalg.norm(foot-center)
        height = radius*radius-distance*distance
        if distance > 0. and abs(distance-radius) <= tolerance:
            return center+(foot-center)*radius/distance
        if height < 0:
            if distance-radius > tolerance:
                raise BadPayload('La línea no alcanza el arco; dibuja un tramo de unión')
            return center+(foot-center)*radius/distance
        candidates = [foot+sign*math.sqrt(height)*direction for sign in (-1,1)]
    else:
        other = np.array((second['x'], second['y']))
        distance = np.linalg.norm(other-center)
        if distance < tolerance:
            if abs(radius-second['radius']) > tolerance:
                raise BadPayload('Los arcos no se encuentran; dibuja un tramo de unión')
            target = (p+q)*.5-center
            if np.linalg.norm(target) <= tolerance:
                raise BadPayload('Los extremos no definen una unión próxima entre los arcos')
            return center+target*radius/np.linalg.norm(target)
        direction = (other-center)/distance
        along = (radius*radius-second['radius']**2+distance*distance)/(2*distance)
        height = radius*radius-along*along
        if height < -tolerance*max(radius, second['radius']):
            raise BadPayload('Los arcos no se encuentran; dibuja un tramo de unión')
        foot = center+along*direction
        normal = np.array((-direction[1], direction[0]))
        candidates = [foot+sign*math.sqrt(max(0.,height))*normal for sign in (-1,1)]
    return min(candidates, key=lambda target: np.linalg.norm(target-p)+np.linalg.norm(target-q))


def _endpoint(entity, role, target):
    if entity['type'] == 'LINE':
        x, y = ('x','y') if role == 'START' else ('x2','y2')
        entity[x], entity[y] = map(float, target)
        return
    angle = math.degrees(math.atan2(target[1]-entity['y'], target[0]-entity['x']))
    old = entity['start']+(entity['sweep'] if role == 'END' else 0)
    delta = (angle-old+180.)%360.-180.
    previous = entity['sweep']
    if role == 'START':
        entity['start'] += delta
        entity['sweep'] -= delta
    else:
        entity['sweep'] += delta
    if previous*entity['sweep'] <= 0:
        raise BadPayload('Cerrar ese hueco invertiría el arco; dibuja un tramo de unión')
    model.validate_entity(entity)


def close_profile(sketch, identifiers, max_gap):
    entities = [e for e in sketch['entities'] if e['id'] in identifiers]
    if not entities or any(not e.get('reference') or e['type']=='POINT' for e in entities):
        raise BadPayload('Selecciona las aristas proyectadas del contorno que quieres cerrar')
    ends = [(e, role, np.array(geometry.handles(e)[role])) for e in entities
            if e['type'] in ('LINE','ARC') for role in ('START','END')]
    positions = [p for e in entities for p in model.outline(e)]
    size = math.dist((min(p[0] for p in positions),min(p[1] for p in positions)),
                     (max(p[0] for p in positions),max(p[1] for p in positions)))
    tolerance = max(size*1e-6, 1e-9)
    nearest = {}
    for i, (entity, role, point) in enumerate(ends):
        candidates = sorted((math.dist(point, other), j) for j, (e,r,other) in enumerate(ends)
                            if e['id'] != entity['id'] and math.dist(point,other) <= max_gap)
        if not candidates:
            raise BadPayload('Hay extremos separados más que el Paso; dibuja la unión o aumenta Paso')
        if len(candidates)>1 and candidates[1][0]-candidates[0][0] <= tolerance:
            raise BadPayload('Hay varios extremos cercanos; selecciona solo un contorno sin ramas')
        nearest[i] = candidates[0][1]
    pairs = []
    for i,j in nearest.items():
        if nearest.get(j) != i:
            raise BadPayload('El contorno tiene extremos ambiguos; selecciona sus aristas por separado')
        if i < j:
            e,role,p = ends[i]; other,other_role,q = ends[j]
            target = _junction(e,other,p,q,tolerance)
            if max(math.dist(target,p),math.dist(target,q)) > max_gap+tolerance:
                raise BadPayload('La unión queda más lejos que el Paso; dibuja un tramo de unión')
            pairs.append((e,role,other,other_role,target))
    for e,role,other,other_role,target in pairs:
        _endpoint(e,role,target); _endpoint(other,other_role,target)
        refs = [dict(id=e['id'],part=role), dict(id=other['id'],part=other_role)]
        if not any(c['type']=='COINCIDENT' and c['refs'] in (refs,refs[::-1]) for c in sketch['constraints']):
            sketch['constraints'].append(dict(id=model.uid('constraint'),type='COINCIDENT',refs=refs))
    for e in entities:
        e['construction'] = False
        for rule in sketch['constraints']:
            if rule['type']=='FIX' and rule['refs']==[dict(id=e['id'],part='BODY')] and 'values' in rule:
                rule['values'] = {k:e[k] for k in model.FIELDS[e['type']]}
    geometry.solve(sketch)
    closed = model.closed_entities(sketch)
    covered = {identifier for profile in closed for identifier in profile.get('members',[profile['id']])}
    if not identifiers <= covered:
        raise BadPayload('El contorno sigue abierto o tiene ramas; selecciona solo las aristas de una figura')
    from .kernel import region
    for profile in closed:
        if identifiers.intersection(profile.get('members',[profile['id']])):
            region(sketch,profile)
