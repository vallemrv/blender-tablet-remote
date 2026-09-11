"""Tablet Material Recipe v1: bounded, declarative shader recipes; never Python."""
import copy
import json
import math
import re
from ..errors import BadPayload

FORMAT = 'tablet-material'
KEY = 'tablet_material_recipe'
CATALOG_KEY = 'tablet_material_catalog_v1'


def number(value, low, high, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise BadPayload(f'{label}: se requiere un número entre {low} y {high}')
    return float(value)


def color(value):
    if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
        raise BadPayload('Color: usa #RRGGBB')
    return value.upper()


def linear(value):
    rgb = [int(color(value)[i:i+2], 16) / 255 for i in (1, 3, 5)]
    return tuple(v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb) + (1.,)


def validate(raw):
    if not isinstance(raw, dict) or len(json.dumps(raw, allow_nan=True)) > 65536:
        raise BadPayload('Receta: objeto JSON de hasta 64 KiB')
    allowed = {'format', 'version', 'id', 'label', 'color', 'surface', 'patterns'}
    if set(raw) - allowed:
        raise BadPayload('Campos de receta desconocidos: ' + ', '.join(sorted(set(raw)-allowed)))
    if raw.get('format') != FORMAT or isinstance(raw.get('version'),bool) or raw.get('version') != 1:
        raise BadPayload('Formato esperado: tablet-material, versión 1')
    if not isinstance(raw.get('id'), str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,47}', raw['id']):
        raise BadPayload('ID de material inválido')
    if not isinstance(raw.get('label'), str) or not raw['label'].strip() or len(raw['label']) > 48:
        raise BadPayload('Nombre de material: entre 1 y 48 caracteres')
    result = dict(format=FORMAT, version=1, id=raw['id'], label=raw['label'].strip(), color=color(raw.get('color', '#B8B8B8')))
    surface = raw.get('surface', {})
    defaults = {'roughness': .4, 'metallic': 0., 'transmission': 0., 'ior': 1.45, 'coat': 0.}
    if not isinstance(surface, dict) or set(surface)-set(defaults):
        raise BadPayload('Parámetros de superficie desconocidos')
    result['surface'] = {key: number(surface.get(key, default), 1 if key == 'ior' else 0,
                                    3 if key == 'ior' else 1, key) for key, default in defaults.items()}
    patterns = raw.get('patterns', [])
    if not isinstance(patterns, list) or len(patterns) > 8:
        raise BadPayload('Máximo ocho capas de textura')
    result['patterns'] = []
    for p in patterns:
        if not isinstance(p, dict) or set(p)-{'kind','scale','stretch','detail','distortion','color','amount','bump'}:
            raise BadPayload('Capa de textura inválida')
        if p.get('kind') not in {'noise','wood','bands','cells'}:
            raise BadPayload('Textura: noise, wood, bands o cells')
        stretch = p.get('stretch', [1,1,1])
        if not isinstance(stretch, list) or len(stretch) != 3:
            raise BadPayload('stretch requiere tres números')
        result['patterns'].append(dict(kind=p['kind'], scale=number(p.get('scale',5),.01,1000,'scale'),
            stretch=[number(v,.01,100,'stretch') for v in stretch], detail=number(p.get('detail',3),0,8,'detail'),
            distortion=number(p.get('distortion',0),0,20,'distortion'), color=color(p.get('color','#303030')),
            amount=number(p.get('amount',.5),0,1,'amount'), bump=number(p.get('bump',0),0,.1,'bump')))
    return result


def recipe(id, label, c, **surface):
    return dict(format=FORMAT, version=1, id=id, label=label, color=c, surface=surface, patterns=[])


BUILTINS = [recipe('plastic','Plástico','#E85D38',roughness=.3,coat=.2),
    recipe('aluminium','Aluminio','#CCD0D5',metallic=1,roughness=.27),
    recipe('iron','Hierro','#74787E',metallic=1,roughness=.48),
    recipe('glass','Cristal','#DDF5FF',transmission=1,roughness=.06,ior=1.45),
    recipe('rock','Roca','#969084',roughness=.9),
    recipe('wood','Madera','#B87D43',roughness=.48),
    recipe('mercury','Mercurio','#E8EDF4',metallic=1,roughness=.035),
    recipe('rubber','Goma','#24262A',roughness=.85),
    recipe('ceramic','Cerámica','#F5EEE0',roughness=.17,coat=.45),
    recipe('gold','Oro','#EBC16B',metallic=1,roughness=.2)]
BUILTINS[4]['patterns'] = [dict(kind='noise',scale=12,color='#48463E',amount=.65,bump=.018)]
BUILTINS[5]['patterns'] = [dict(kind='wood',scale=7,stretch=[1,1,3],distortion=4,color='#402010',amount=.75,bump=.002)]
DETAIL_IDS = {'rust', 'dirt', 'scratches'}
rust = recipe('rust', 'Óxido', '#A34C24', roughness=.92)
rust['patterns'] = [dict(kind='noise',scale=35,color='#3D2114',amount=.8,bump=.004)]
dirt = recipe('dirt', 'Suciedad', '#62503B', roughness=1.)
dirt['patterns'] = [dict(kind='noise',scale=18,color='#252019',amount=.7,bump=.001)]
scratches = recipe('scratches', 'Arañazos', '#A6ADB5', metallic=.85, roughness=.65)
scratches['patterns'] = [dict(kind='bands',scale=80,stretch=[1,.03,.03],distortion=3,color='#34383D',amount=.9,bump=.0004)]
BUILTINS.extend((rust, dirt, scratches))
BUILTINS = [validate(r) for r in BUILTINS]


def catalog():
    import bpy
    custom = json.loads(bpy.context.scene.get(CATALOG_KEY, '{}'))
    return [copy.deepcopy(r) for r in BUILTINS] + list(custom.values())


SURFACE_LIMITS = {'roughness': (0., 1.), 'metallic': (0., 1.), 'transmission': (0., 1.), 'ior': (1., 3.), 'coat': (0., 1.)}

# Receta neutra para describir un preset que ya no está en el archivo abierto.
FALLBACK = validate(recipe('unknown', 'Material', '#B8B8B8'))

# Cada acabado escribe solo lo que define: un acabado de brillo no debe decidir
# si el material era metal, y el resto de la receta sigue mandando.
FINISHES = [
    dict(id='natural', label='Natural', hint='La superficie original del material.', surface={}),
    dict(id='polished', label='Pulido', hint='Reflejo nítido, como recién bruñido.', surface=dict(roughness=.12)),
    dict(id='satin', label='Satinado', hint='Brillo suave, entre el espejo y el mate.', surface=dict(roughness=.45, coat=.3)),
    dict(id='matte', label='Mate', hint='Sin brillo: la luz se difumina.', surface=dict(roughness=1., coat=0.)),
    dict(id='worn', label='Gastado', hint='Roce y uso: brillo apagado e irregular.', surface=dict(roughness=.8)),
    dict(id='metal', label='Metálico', hint='Reflejo de metal; el color tiñe el reflejo.', surface=dict(metallic=1., roughness=.25, transmission=0.)),
    dict(id='varnish', label='Barnizado', hint='Una laca transparente por encima.', surface=dict(coat=1., roughness=.25)),
    dict(id='translucent', label='Translúcido', hint='Deja pasar la luz, como el cristal.', surface=dict(transmission=1., roughness=.05, metallic=0., ior=1.45)),
]

# Nombres y extremos en lenguaje llano: el usuario no tiene por qué saber qué es
# el IOR para entender que va de aire a diamante.
SURFACE_CONTROLS = [
    dict(id='roughness', label='Pulido', low='Espejo', high='Mate', min=0., max=1.),
    dict(id='metallic', label='Metal', low='No metal', high='Metal puro', min=0., max=1.),
    dict(id='transmission', label='Transparencia', low='Opaco', high='Cristal', min=0., max=1.),
    dict(id='ior', label='Densidad óptica', low='Aire', high='Diamante', min=1., max=3.),
    dict(id='coat', label='Barniz', low='Seco', high='Laca', min=0., max=1.),
]

# El grano se añade encima de la receta: una textura más, con el vocabulario de
# quien mira el objeto («escamas») y no el del nodo de Blender («voronoi»).
GRAINS = [
    dict(id='none', label='Liso', hint='Sin textura añadida.'),
    dict(id='noise', label='Granulado', hint='Grano irregular, como piedra o pintura gruesa.'),
    dict(id='wood', label='Vetas', hint='Anillos alargados, como la madera.'),
    dict(id='bands', label='Cepillado', hint='Rayas finas en una dirección, como metal cepillado.'),
    dict(id='cells', label='Escamas', hint='Celdas irregulares, como cuero o piel.'),
]
GRAIN_STRETCH = {'noise': [1, 1, 1], 'wood': [1, 1, 3], 'bands': [1, .04, .04], 'cells': [1, 1, 1]}
GRAIN_MAX_BUMP = .02


def finish_surface(finish):
    match = next((f for f in FINISHES if f['id'] == finish), None)
    if match is None: raise BadPayload('Acabado desconocido')
    return dict(match['surface'])


def surface_values(values):
    """Ajustes sueltos de superficie; los que no vienen los sigue poniendo el acabado."""
    if not isinstance(values, dict) or set(values) - set(SURFACE_LIMITS):
        raise BadPayload('Ajuste de superficie desconocido')
    return {key: number(value, *SURFACE_LIMITS[key], key) for key, value in values.items()}


def shade(value, factor):
    """Oscurece un color sRGB: el grano se tiñe solo, sin pedir un segundo color."""
    rgb = [int(color(value)[i:i+2], 16) for i in (1, 3, 5)]
    return '#%02X%02X%02X' % tuple(int(round(channel * factor)) for channel in rgb)


def grain_pattern(kind, scale, amount, relief, tint):
    """Una capa de textura descrita con los tres controles que ve el usuario."""
    if kind not in {g['id'] for g in GRAINS}: raise BadPayload('Grano desconocido')
    if kind == 'none': return None
    return dict(kind=kind, scale=number(scale, 1, 200, 'grain_scale'), stretch=list(GRAIN_STRETCH[kind]),
        detail=3., distortion=4. if kind in {'wood', 'bands'} else 0., color=shade(tint, .45),
        amount=number(amount, 0, 1, 'grain_amount'), bump=number(relief, 0, 1, 'grain_relief') * GRAIN_MAX_BUMP)


def unique_id(label, taken):
    """ID legible a partir del nombre escrito; los IDs son del contrato, no del usuario."""
    base = re.sub(r'[^a-z0-9]+', '-', label.lower()).strip('-')[:40]
    if not base or not base[0].isalpha(): base = 'material-' + base.strip('-')
    candidate, index = base[:47], 2
    while candidate in taken:
        candidate = f'{base[:44]}-{index}'
        index += 1
    return candidate


def configure_transmission(material):
    """Trace from the surface, so automatic whole-object thickness cannot skip contents."""
    material.use_raytrace_refraction=True
    material.thickness_mode='SPHERE'
    nodes,links=material.node_tree.nodes,material.node_tree.links
    output=next(n for n in nodes if n.type=='OUTPUT_MATERIAL' and n.is_active_output)
    if not output.inputs['Thickness'].is_linked:
        value=nodes.new('ShaderNodeValue'); value.label='Superficie de cristal · conserva el interior'
        value.outputs[0].default_value=0.
        links.new(value.outputs[0],output.inputs['Thickness'])


def compile_material(raw, tint=None):
    """Create one native shader. Validation completes before Blender data is created."""
    import bpy
    r = validate(raw)
    if tint is not None:
        r['color'] = color(tint)
    encoded = json.dumps(r, sort_keys=True)
    for existing in bpy.data.materials:
        if existing.get(KEY) == encoded and not existing.get('tablet_layers',0):
            transmitting=r['surface']['transmission']>0
            output=next((n for n in existing.node_tree.nodes if n.type=='OUTPUT_MATERIAL' and n.is_active_output),None)
            if existing.use_raytrace_refraction==transmitting and (not transmitting or
                    (output and output.inputs['Thickness'].is_linked)):
                return existing
    material = bpy.data.materials.new(r['label'])
    try:
        material.use_nodes = True
        material.use_raytrace_refraction = r['surface']['transmission'] > 0
        material.thickness_mode = 'SPHERE'
        material.diffuse_color = linear(r['color'])
        material[KEY] = encoded
        nodes, links = material.node_tree.nodes, material.node_tree.links
        nodes.clear()
        out = nodes.new('ShaderNodeOutputMaterial')
        bsdf = nodes.new('ShaderNodeBsdfPrincipled')
        bsdf.inputs['Base Color'].default_value = linear(r['color'])
        for key, socket in {'roughness':'Roughness','metallic':'Metallic','transmission':'Transmission Weight','ior':'IOR','coat':'Coat Weight'}.items():
            bsdf.inputs[socket].default_value = r['surface'][key]
        links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
        if material.use_raytrace_refraction: configure_transmission(material)
        coord = nodes.new('ShaderNodeTexCoord')
        previous_color = None
        previous_normal = None
        for p in r['patterns']:
            mapping = nodes.new('ShaderNodeVectorMath'); mapping.operation = 'MULTIPLY'
            mapping.inputs[1].default_value = p['stretch']
            links.new(coord.outputs['Generated'], mapping.inputs[0])
            node_type = {'noise':'ShaderNodeTexNoise','wood':'ShaderNodeTexWave','bands':'ShaderNodeTexWave','cells':'ShaderNodeTexVoronoi'}[p['kind']]
            tex = nodes.new(node_type)
            tex.inputs['Scale'].default_value = p['scale']
            if p['kind'] in {'wood','bands'}:
                tex.wave_type = 'RINGS' if p['kind'] == 'wood' else 'BANDS'
                tex.inputs['Distortion'].default_value = p['distortion']
            if 'Detail' in tex.inputs: tex.inputs['Detail'].default_value = p['detail']
            links.new(mapping.outputs['Vector'], tex.inputs['Vector'])
            factor = tex.outputs['Distance'] if p['kind'] == 'cells' else tex.outputs['Fac']
            amount = nodes.new('ShaderNodeMath'); amount.operation = 'MULTIPLY'
            amount.inputs[1].default_value = p['amount']; links.new(factor, amount.inputs[0])
            mix = nodes.new('ShaderNodeMixRGB')
            links.new(amount.outputs[0], mix.inputs[0])
            mix.inputs[1].default_value = linear(r['color'])
            mix.inputs[2].default_value = linear(p['color'])
            if previous_color: links.new(previous_color, mix.inputs[1])
            previous_color = mix.outputs[0]
            if p['bump']:
                bump = nodes.new('ShaderNodeBump')
                bump.inputs['Distance'].default_value = p['bump']
                links.new(factor, bump.inputs['Height'])
                if previous_normal: links.new(previous_normal, bump.inputs['Normal'])
                previous_normal = bump.outputs['Normal']
        if previous_color: links.new(previous_color, bsdf.inputs['Base Color'])
        if previous_normal: links.new(previous_normal, bsdf.inputs['Normal'])
        return material
    except Exception:
        bpy.data.materials.remove(material)
        raise
