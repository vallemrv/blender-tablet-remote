"""material.* — catalog, appearance and reversible painting, main thread only."""
import json
import bpy
from . import command
from ..errors import BadPayload, CommandError
from ..bpy_utils import undo_push
from ..materials.runtime import runtime, ENVIRONMENTS
from ..materials import recipes


@command('material.state')
def state(payload): return {'material':runtime.status()}


@command('material.catalog')
def catalog(payload): return {'format':'tablet-material','version':1,'presets':recipes.catalog()}


@command('material.import')
def import_recipe(payload):
    runtime.require(payload.get('_client_id'))
    runtime.cancel()
    recipe=recipes.validate(payload.get('recipe'))
    if recipe['id'] in {r['id'] for r in recipes.BUILTINS}:
        raise BadPayload('Usa un ID propio; los materiales incluidos no se sustituyen')
    custom=json.loads(bpy.context.scene.get(recipes.CATALOG_KEY,'{}'))
    if recipe['id'] not in custom and len(custom)>=64: raise BadPayload('Máximo 64 presets importados por escena')
    custom[recipe['id']]=recipe
    bpy.context.scene[recipes.CATALOG_KEY]=json.dumps(custom)
    runtime.preset=recipe['id']; runtime.tint=recipe['color']; runtime.finish='natural'
    undo_push('Importar material')
    return {'material':runtime.status()}


@command('material.settings')
def settings(payload):
    runtime.require(payload.get('_client_id'))
    preset=payload.get('preset',runtime.preset)
    match=next((r for r in recipes.catalog() if r['id']==preset),None)
    if match is None: raise BadPayload('Material desconocido')
    tint=recipes.color(payload.get('color',runtime.tint))
    radius=recipes.number(payload.get('radius',runtime.radius),.005,.25,'radius')
    strength=recipes.number(payload.get('strength',runtime.strength),0,1,'strength')
    env=payload.get('environment',runtime.environment)
    if env not in {e['id'] for e in ENVIRONMENTS}: raise BadPayload('Ambiente desconocido')
    finish=payload.get('finish', runtime.finish)
    if finish not in {'natural','polished','worn'}: raise BadPayload('Acabado desconocido')
    erase=payload.get('erase',runtime.erase)
    if not isinstance(erase,bool): raise BadPayload('erase requiere true o false')
    runtime.cancel()
    runtime.finish=finish; runtime.erase=erase
    runtime.preset=preset; runtime.tint=tint; runtime.radius=radius; runtime.strength=strength; runtime.environment=env
    return {'material':runtime.status()}


@command('material.apply')
def apply(payload):
    runtime.require(payload.get('_client_id'))
    runtime.apply()
    return {'material':runtime.status()}


@command('material.stroke')
def stroke(payload):
    runtime.require(payload.get('_client_id'))
    phase=payload.get('phase')
    ident=payload.get('stroke_id')
    if phase not in {'begin','update','end','cancel'} or not isinstance(ident,str) or not 1<=len(ident)<=80:
        raise BadPayload('Trazo: phase y stroke_id requeridos')
    points=payload.get('points',[])
    if not isinstance(points,list) or len(points)>128: raise BadPayload('Máximo 128 muestras por mensaje')
    samples=[]
    for p in points:
        if not isinstance(p,dict): raise BadPayload('Muestra de pintura inválida')
        samples.append({k:recipes.number(p.get(k,1 if k=='pressure' else None),0,1,k) for k in ('u','v','pressure')})
    if phase=='begin': runtime.begin(payload)
    if not runtime.stroke or runtime.stroke['id']!=ident:
        return {'finished':True}
    try:
        if phase in {'begin','update'}: runtime.update(samples)
        elif phase=='end': runtime.end()
        elif phase=='cancel': runtime.cancel()
    except Exception:
        runtime.cancel(); raise
    return {'finished':runtime.stroke is None}
