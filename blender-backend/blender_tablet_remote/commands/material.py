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
    runtime.preset=recipe['id']; runtime.tint=None; runtime.finish='natural'
    runtime.surface={}; runtime.grain='none'
    undo_push('Importar material')
    return {'material':runtime.status()}


@command('material.settings')
def settings(payload):
    runtime.require(payload.get('_client_id'),targets=False)
    preset=payload.get('preset',runtime.preset)
    match=next((r for r in recipes.catalog() if r['id']==preset),None)
    if match is None: raise BadPayload('Material desconocido')
    # `color: null` devuelve el material a su propio color; omitirlo conserva el tinte.
    raw_tint=payload.get('color',runtime.tint)
    tint=None if raw_tint is None else recipes.color(raw_tint)
    radius=recipes.number(payload.get('radius',runtime.radius),.005,.25,'radius')
    strength=recipes.number(payload.get('strength',runtime.strength),0,1,'strength')
    env=payload.get('environment',runtime.environment)
    if env not in {e['id'] for e in ENVIRONMENTS}: raise BadPayload('Ambiente desconocido')
    finish=payload.get('finish', runtime.finish)
    recipes.finish_surface(finish)
    # Elegir un acabado es empezar de cero desde él; los ajustes sueltos van encima.
    overrides={} if 'finish' in payload else dict(runtime.surface)
    if 'surface' in payload: overrides.update(recipes.surface_values(payload['surface']))
    grain=payload.get('grain',runtime.grain)
    grain_scale=recipes.number(payload.get('grain_scale',runtime.grain_scale),1,200,'grain_scale')
    grain_amount=recipes.number(payload.get('grain_amount',runtime.grain_amount),0,1,'grain_amount')
    grain_relief=recipes.number(payload.get('grain_relief',runtime.grain_relief),0,1,'grain_relief')
    recipes.grain_pattern(grain,grain_scale,grain_amount,grain_relief,tint or '#B8B8B8')
    erase=payload.get('erase',runtime.erase)
    if not isinstance(erase,bool): raise BadPayload('erase requiere true o false')
    interaction=payload.get('interaction',runtime.interaction)
    brush=payload.get('brush',runtime.brush)
    scope=payload.get('scope',runtime.scope)
    isolate=payload.get('isolate',runtime.isolate)
    if not isinstance(interaction,str) or interaction not in {'SELECT','PAINT'}: raise BadPayload('Elige Seleccionar o Pintar')
    if not isinstance(brush,str) or brush not in {'ROUND','AIRBRUSH','SPRAY'}: raise BadPayload('Pincel desconocido')
    if not isinstance(scope,str) or scope not in {r['id'] for r in runtime.status()['regions']}: raise BadPayload('Zona desconocida')
    if not isinstance(isolate,bool): raise BadPayload('isolate requiere true o false')
    runtime.cancel()
    if isolate!=runtime.isolate: runtime.frame=None
    runtime.interaction=interaction; runtime.brush=brush; runtime.scope=scope; runtime.isolate=isolate
    runtime.finish=finish; runtime.erase=erase; runtime.surface=overrides
    runtime.grain=grain; runtime.grain_scale=grain_scale; runtime.grain_amount=grain_amount; runtime.grain_relief=grain_relief
    runtime.preset=preset; runtime.tint=tint; runtime.radius=radius; runtime.strength=strength; runtime.environment=env
    return {'material':runtime.status()}


@command('material.save')
def save_recipe(payload):
    """Guarda lo que se ve —receta, tinte, acabado, ajustes y grano— como preset propio."""
    runtime.require(payload.get('_client_id'),targets=False)
    label=payload.get('label')
    if not isinstance(label,str) or not label.strip() or len(label.strip())>48:
        raise BadPayload('Nombre de material: entre 1 y 48 caracteres')
    runtime.cancel()
    custom=json.loads(bpy.context.scene.get(recipes.CATALOG_KEY,'{}'))
    if len(custom)>=64: raise BadPayload('Máximo 64 presets guardados por escena')
    saved=runtime.selected_recipe()
    saved.update(label=label.strip(), color=runtime.effective_color(),
                 id=recipes.unique_id(label.strip(), {r['id'] for r in recipes.BUILTINS}|set(custom)))
    saved=recipes.validate(saved)
    custom[saved['id']]=saved
    bpy.context.scene[recipes.CATALOG_KEY]=json.dumps(custom)
    # El material guardado ya incluye acabado, ajustes y grano: se vuelve al punto
    # de partida para que seguir tocando no acumule dos veces lo mismo.
    runtime.preset=saved['id']; runtime.tint=None; runtime.finish='natural'
    runtime.surface={}; runtime.grain='none'
    undo_push('Guardar material')
    return {'material':runtime.status()}


@command('material.select', mutating=False)
def select(payload):
    runtime.require(payload.get('_client_id'),targets=False)
    if 'objects' in payload:
        runtime.select(payload['objects'])
    else:
        from .snap import query_candidate
        runtime.cancel()
        # Use the same visibility and acquisition policy as all surface tools.
        from ..bpy_utils import find_view3d
        found=find_view3d()
        if found is None: raise CommandError('Se necesita un viewport',code='no_viewport')
        with runtime.presentation(found[1].spaces.active):
            hit=query_candidate(dict(payload,snap_type='FACE'))
        if hit.get('hit'):
            name=hit['object']
            additive=payload.get('additive',False)
            if not isinstance(additive,bool): raise BadPayload('additive requiere true o false')
            names=list(runtime.targets) if additive else []
            if name in names: names.remove(name)
            else: names.append(name)
            runtime.select(names)
    return {'material':runtime.status()}


@command('material.group')
def group(payload):
    runtime.require(payload.get('_client_id'))
    name=payload.get('name','Zona de pintura')
    if not isinstance(name,str) or not name.strip() or len(name.encode('utf-8'))>63: raise BadPayload('Nombre de grupo inválido o demasiado largo')
    selections=[(o,[v.index for v in o.data.vertices if v.select]) for o in runtime.objects()]
    if any(not ids for _,ids in selections): raise BadPayload('Selecciona vértices o caras en Edit antes de guardar la zona')
    if any(o.vertex_groups.get(name) for o,_ in selections): raise BadPayload('Ya existe un grupo con ese nombre; elige otro')
    runtime.cancel()
    created=[]
    try:
        for obj,ids in selections:
            old=obj.data; obj.data=old.copy()
            created.append((obj,old,None))
            group=obj.vertex_groups.new(name=name); created[-1]=(obj,old,group)
            group.add(ids,1.,'REPLACE')
        undo_push('Guardar zona de pintura')
    except Exception:
        for obj,old,group in created:
            if group: obj.vertex_groups.remove(group)
            new=obj.data; obj.data=old
            if new.users==0: bpy.data.meshes.remove(new)
        raise
    runtime.scope='GROUP:'+name
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
