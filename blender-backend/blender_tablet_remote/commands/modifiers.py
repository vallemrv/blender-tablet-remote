"""modifier.* — pila no destructiva del objeto activo.

API de datablock (`obj.modifiers.new`), no operadores. El catálogo es deliberadamente
corto: Subsurf, Multires, Array, Bevel, Solidify, Boolean, Mirror y Simple Deform. Bevel aquí no es `mesh.bevel`.
"""

from __future__ import annotations

import math

import bpy
from mathutils import Vector

from ..bpy_utils import active_object, get_int, undo_push, view3d_override
from ..errors import BadPayload, CommandError
from . import command

def _rna_schema(rna_type):
    """Generate ordinary controls from native RNA; context rules are adapters."""
    base=set(bpy.types.Modifier.bl_rna.properties.keys())
    result={}
    for prop in rna_type.bl_rna.properties:
        if prop.identifier in base or prop.is_readonly:continue
        key=prop.identifier
        if prop.type=='BOOLEAN':spec=dict(type='bool',default=bool(prop.default))
        elif prop.type=='ENUM':
            spec=dict(type='enum',default=prop.default,values=[i.identifier for i in prop.enum_items],
                      value_labels={i.identifier:i.name for i in prop.enum_items})
        elif prop.type in ('FLOAT','INT') and not prop.is_array:
            angular=prop.subtype=='ANGLE'
            convert=math.degrees if angular else float
            spec=dict(type='int' if prop.type=='INT' else 'float',default=convert(prop.default),
                      min=convert(prop.hard_min),max=convert(prop.hard_max),
                      step=1 if prop.type=='INT' else (1 if angular else max(.01,prop.step/100)),editable=True)
            if angular:spec['unit']='ANGLE'
            elif prop.subtype=='DISTANCE':spec['unit']='LENGTH'
        elif prop.type=='POINTER' and prop.fixed_type.identifier=='Object':
            spec=dict(type='object',default=None,object_filter=dict(exclude_self=True))
        elif prop.type=='STRING' and 'vertex_group' in key:spec=dict(type='vertex_group',default='')
        else:continue
        spec['label']=prop.name
        result[key]=spec
    return result


RNA_TYPES={'LATTICE':bpy.types.LatticeModifier}


SCHEMA = {
    "MULTIRES": {
        key: {"type": "int", "default": 1, "min": 0, "max": 6, "step": 1}
        for key in ("levels", "sculpt_levels", "render_levels")
    },
    "SUBSURF": {
        "levels": {"type": "int", "default": 1, "min": 0, "max": 6, "step": 1},
        "render_levels": {"type": "int", "default": 2, "min": 0, "max": 6, "step": 1},
        "subdivision_type": {"type": "enum", "default": "CATMULL_CLARK", "values": ["CATMULL_CLARK", "SIMPLE"]},
    },
    "ARRAY": {
        "count": {"type": "int", "default": 2, "min": 1, "max": 1000, "step": 1},
        "relative_offset": {"type": "float3", "default": [1.0, 0.0, 0.0], "min": -1000.0, "max": 1000.0, "step": 0.1},
        "use_merge": {"type": "bool", "default": False},
        "merge_threshold": {"type": "float", "default": 0.01, "min": 0.0, "max": 1000.0, "step": 0.001},
        # Matriz circular: el desplazamiento de objeto copia la transformación de un Empty.
        "use_relative_offset": {"type": "bool", "default": True, "label": "Desplazamiento relativo"},
        "use_object_offset": {"type": "bool", "default": False, "label": "Desplazamiento de objeto"},
        "offset_object": {"type": "object", "default": None, "label": "Objeto de desplazamiento",
                          "object_filter": {"exclude_self": True}},
    },
    "BEVEL": {
        "width": {"type": "float", "default": 0.1, "min": 0.0, "max": 1000.0, "step": 0.01},
        "segments": {"type": "int", "default": 1, "min": 1, "max": 1000, "step": 1},
        "affect": {"type": "enum", "default": "EDGES", "values": ["EDGES", "VERTICES"]},
        "limit_method": {"type": "enum", "default": "ANGLE", "values": ["NONE", "ANGLE"]},
        "angle_limit": {"type": "float", "default": 30.0, "min": 0.0, "max": 180.0, "step": 1.0},
        "profile": {"type": "float", "default": 0.5, "min": 0.0, "max": 1.0, "step": 0.05},
    },
    "SIMPLE_DEFORM": {
        "deform_method": {"type":"enum", "default":"TWIST", "values":["TWIST","BEND","TAPER","STRETCH"], "label":"Método",
                          "value_labels":{"TWIST":"Torsión","BEND":"Curvar","TAPER":"Estrechar","STRETCH":"Estirar"}},
        "deform_axis": {"type":"enum", "default":"Z", "values":["X","Y","Z"], "label":"Eje"},
        "angle": {"type":"float", "default":45., "min":-36000., "max":36000., "step":5., "label":"Ángulo", "unit":"ANGLE", "editable":True,
                  "visible_when":{"deform_method":["TWIST","BEND"]}},
        "factor": {"type":"float", "default":.5, "min":-1000., "max":1000., "step":.1, "label":"Factor", "editable":True,
                   "visible_when":{"deform_method":["TAPER","STRETCH"]}},
        "limit_lower": {"type":"float", "default":0., "min":0., "max":1., "step":.05, "label":"Límite inferior (0–1)", "editable":True},
        "limit_upper": {"type":"float", "default":1., "min":0., "max":1., "step":.05, "label":"Límite superior (0–1)", "editable":True},
        **{f"lock_{axis}": {"type":"bool", "default":False, "label":"Bloquear "+axis.upper(),
                            "visible_when":{"deform_method":["TWIST","TAPER","STRETCH"]}} for axis in "xyz"},
        "origin": {"type":"object", "default":None, "label":"Objeto de origen", "object_filter":{"exclude_self":True}},
        "vertex_group": {"type":"vertex_group", "default":"", "label":"Grupo de vértices"},
        "invert_vertex_group": {"type":"bool", "default":False, "label":"Invertir grupo"},
    },
    "SOLIDIFY": {
        "thickness": {"type": "float", "default": 0.1, "min": -1000.0, "max": 1000.0, "step": 0.01},
        "offset": {"type": "float", "default": -1.0, "min": -1.0, "max": 1.0, "step": 0.1},
        "use_even_offset": {"type": "bool", "default": True},
        "use_rim": {"type": "bool", "default": True},
    },
    "BOOLEAN": {
        "operation": {"type": "enum", "default": "DIFFERENCE", "values": ["DIFFERENCE", "UNION", "INTERSECT"]},
        "object": {"type": "object", "default": None, "object_filter": {"type": "MESH", "exclude_self": True}},
        "solver": {"type": "enum", "default": "EXACT", "values": ["EXACT", "FAST"]},
    },
    "MIRROR": {
        "use_axis_x": {"type": "bool", "default": True},
        "use_axis_y": {"type": "bool", "default": False},
        "use_axis_z": {"type": "bool", "default": False},
        "use_bisect_x": {"type": "bool", "default": False},
        "use_bisect_y": {"type": "bool", "default": False},
        "use_bisect_z": {"type": "bool", "default": False},
        "use_bisect_flip_x": {"type": "bool", "default": False},
        "use_bisect_flip_y": {"type": "bool", "default": False},
        "use_bisect_flip_z": {"type": "bool", "default": False},
        "use_clip": {"type": "bool", "default": False, "label": "Clipping"},
        "use_merge": {"type": "bool", "default": True},
        "merge_threshold": {"type": "float", "default": 0.001, "min": 0.0, "max": 1.0, "step": 0.001},
        "mirror_object": {"type": "object", "default": None, "object_filter": {"exclude_self": True}},
    },
}

SCHEMA.update({kind:_rna_schema(cls) for kind,cls in RNA_TYPES.items()})
SCHEMA['LATTICE']['object'].update(label='Jaula Lattice',object_filter=dict(type='LATTICE',exclude_self=True))
SCHEMA['LATTICE']['strength']['label']='Intensidad'
SCHEMA['LATTICE']['vertex_group']['label']='Grupo de vértices'
SCHEMA['LATTICE']['invert_vertex_group']['label']='Invertir grupo'


CATALOG = {
    "SUBSURF": {"blender": "SUBSURF", "default_name": "Subdivision"},
    "MULTIRES": {"blender": "MULTIRES", "default_name": "Multires"},
    "ARRAY": {"blender": "ARRAY", "default_name": "Array"},
    "BEVEL": {"blender": "BEVEL", "default_name": "Bevel"},
    "SIMPLE_DEFORM": {"blender":"SIMPLE_DEFORM", "default_name":"Deformación simple"},
    "SOLIDIFY": {"blender": "SOLIDIFY", "default_name": "Solidify"},
    "BOOLEAN": {"blender": "BOOLEAN", "default_name": "Boolean"},
    "MIRROR": {"blender": "MIRROR", "default_name": "Mirror"},
    "LATTICE": {"blender":"LATTICE", "default_name":"Lattice"},
}


def _defaults(kind: str) -> dict:
    return {key: spec["default"] for key, spec in SCHEMA[kind].items()}


def _keys(kind: str) -> tuple:
    return tuple(SCHEMA[kind])


def _target(payload=None):
    name = (payload or {}).get("object")
    obj = bpy.data.objects.get(str(name)) if name else active_object()
    if obj is None:
        raise CommandError(f"Object not found: {name}", code="not_found")
    if obj.type != "MESH":
        raise CommandError(f"Object '{obj.name}' is not a mesh", code="unsupported_type")
    if obj.mode == 'EDIT':
        from .object_properties import _require_idle
        _require_idle()
    return obj


def _require(obj, name: str):
    if not name:
        raise BadPayload("'name' is required")
    mod = obj.modifiers.get(name)
    if mod is None:
        raise CommandError(f"Modifier not found: {name}", code="not_found")
    return mod


def _operand(obj, name):
    if name is None or name == "":
        return None
    other = bpy.data.objects.get(str(name))
    if other is None:
        raise CommandError(f"Object not found: {name}", code="not_found")
    if other == obj:
        raise BadPayload("Boolean operand cannot be the same object")
    if other.type != "MESH":
        raise BadPayload("Boolean operand must be a mesh")
    return other


def _mirror_object(obj, name):
    """Otro objeto de referencia (Espejo, Matriz): nunca el propio objeto."""
    if name is None or name == "":
        return None
    other = bpy.data.objects.get(str(name))
    if other is None:
        raise CommandError(f"Object not found: {name}", code="not_found")
    if other == obj:
        raise BadPayload("El objeto de referencia debe ser otro objeto")
    return other


def _write_rna(mod,kind,data,obj):
    pending={}
    for key,spec in SCHEMA[kind].items():
        value=data[key];typ=spec['type']
        if typ=='bool':
            if not isinstance(value,bool):raise BadPayload(key+' debe ser booleano')
        elif typ in ('float','int'):
            value=(_bounded_int if typ=='int' else _bounded_float)(value,key,spec['min'],spec['max'])
            if spec.get('unit')=='ANGLE':value=math.radians(value)
        elif typ=='enum':
            if value not in spec['values']:raise BadPayload('Valor no válido para '+key)
        elif typ=='vertex_group':
            if not isinstance(value,str) or (value and not obj.vertex_groups.get(value)):raise BadPayload('El grupo no existe en este objeto')
        elif typ=='object':
            target=bpy.data.objects.get(str(value)) if value else None
            filter=spec.get('object_filter',{})
            if value and target is None:raise BadPayload('El objeto no existe')
            if target and ((filter.get('exclude_self') and target==obj) or (filter.get('type') and target.type!=filter['type'])):
                raise BadPayload('Elige un objeto de tipo '+filter.get('type','compatible')+' distinto del objeto deformado')
            value=target
        pending[key]=value
    before={key:getattr(mod,key) for key in pending}
    try:
        for key,value in pending.items():setattr(mod,key,value)
    except Exception:
        for key,value in before.items():setattr(mod,key,value)
        raise


def _read_rna(mod,kind):
    result={}
    for key,spec in SCHEMA[kind].items():
        value=getattr(mod,key)
        if spec['type']=='object':value=value.name if value else None
        elif spec.get('unit')=='ANGLE':value=math.degrees(value)
        result[key]=value
    return result


def _write(mod, kind: str, params: dict, obj, preserve_current: bool = False) -> None:
    current = _read(mod)["parameters"] if preserve_current else {}
    data = _defaults(kind)
    data.update(current)
    data.update({key: params[key] for key in _keys(kind) if key in params})
    if kind in RNA_TYPES:
        _write_rna(mod,kind,data,obj)
    elif kind == "MULTIRES":
        values = {key: _bounded_int(data[key], key, 0, mod.total_levels) for key in _keys(kind)}
        with view3d_override(), bpy.context.temp_override(object=obj, active_object=obj):
            previous_mode = obj.mode
            if previous_mode == 'SCULPT': bpy.ops.object.mode_set(mode='OBJECT')
            try:
                for key, value in values.items(): setattr(mod, key, value)
            finally:
                if previous_mode == 'SCULPT': bpy.ops.object.mode_set(mode='SCULPT')
    elif kind == "SUBSURF":
        mod.levels = _bounded_int(data["levels"], "levels", 0, 6)
        mod.render_levels = _bounded_int(data["render_levels"], "render_levels", 0, 6)
        subdiv = str(data["subdivision_type"]).upper()
        if subdiv not in {"CATMULL_CLARK", "SIMPLE"}:
            raise BadPayload("'subdivision_type' must be CATMULL_CLARK or SIMPLE")
        mod.subdivision_type = subdiv
    elif kind == "ARRAY":
        mod.count = _bounded_int(data["count"], "count", 1, 1000)
        offset = data["relative_offset"]
        if not isinstance(offset, (list, tuple)) or len(offset) != 3:
            raise BadPayload("'relative_offset' must be [x, y, z]")
        for key in ("use_relative_offset", "use_object_offset"):
            if not isinstance(data[key], bool):
                raise BadPayload(f"'{key}' must be a boolean")
        offset_object = _mirror_object(obj, data["offset_object"])
        if offset_object is not None and "offset_object" in params:
            # Elegir el objeto es pedir la matriz circular: sin estos interruptores el
            # Empty no hace nada y el desplazamiento relativo deforma el círculo.
            if "use_object_offset" not in params:
                data["use_object_offset"] = True
            if "use_relative_offset" not in params:
                data["use_relative_offset"] = False
        mod.use_relative_offset = data["use_relative_offset"]
        mod.relative_offset_displace = Vector((float(offset[0]), float(offset[1]), float(offset[2])))
        mod.use_object_offset = data["use_object_offset"]
        mod.offset_object = offset_object
        mod.use_merge_vertices = bool(data["use_merge"])
        mod.merge_threshold = _bounded_float(data["merge_threshold"], "merge_threshold", 0.0, 1000.0)
    elif kind == "BEVEL":
        mod.width = _bounded_float(data["width"], "width", 0.0, 1000.0)
        mod.segments = _bounded_int(data["segments"], "segments", 1, 1000)
        affect = str(data["affect"]).upper()
        if affect not in {"EDGES", "VERTICES"}:
            raise BadPayload("'affect' must be EDGES or VERTICES")
        mod.affect = affect
        limit = str(data["limit_method"]).upper()
        if limit not in {"NONE", "ANGLE"}:
            raise BadPayload("'limit_method' must be NONE or ANGLE")
        mod.limit_method = limit
        mod.angle_limit = math.radians(_bounded_float(data["angle_limit"], "angle_limit", 0.0, 180.0))
        mod.profile = _bounded_float(data["profile"], "profile", 0.0, 1.0)
    elif kind == "SIMPLE_DEFORM":
        method, axis = str(data['deform_method']).upper(), str(data['deform_axis']).upper()
        if method not in SCHEMA[kind]['deform_method']['values'] or axis not in ('X','Y','Z'):
            raise BadPayload('Método o eje de deformación no válido')
        angle = _bounded_float(data['angle'],'angle',-36000.,36000.) if method in ('TWIST','BEND') else None
        factor = _bounded_float(data['factor'],'factor',-1000.,1000.) if method in ('TAPER','STRETCH') else None
        lower = _bounded_float(data['limit_lower'],'limit_lower',0.,1.)
        upper = _bounded_float(data['limit_upper'],'limit_upper',0.,1.)
        if lower > upper: raise BadPayload('El límite inferior no puede superar al superior')
        for key in ('lock_x','lock_y','lock_z'):
            if not isinstance(data[key],bool): raise BadPayload(key+' debe ser booleano')
        origin = bpy.data.objects.get(str(data['origin'])) if data['origin'] else None
        if data['origin'] and origin is None: raise BadPayload('El objeto de origen no existe')
        if origin == obj: raise BadPayload('El origen debe ser otro objeto')
        group = data['vertex_group']
        if not isinstance(group,str) or (group and not obj.vertex_groups.get(group)):
            raise BadPayload('El grupo no existe en este objeto')
        if not isinstance(data['invert_vertex_group'],bool):raise BadPayload('Invertir grupo debe ser booleano')
        mod.deform_method, mod.deform_axis = method, axis
        # Blender shares storage for angle/factor: write only the active quantity.
        if method in ('TWIST','BEND'): mod.angle = math.radians(angle)
        else: mod.factor = factor
        mod.limits = (lower,upper)
        for key in ('lock_x','lock_y','lock_z'):setattr(mod,key,data[key])
        mod.origin = origin
        mod.vertex_group = group
        mod.invert_vertex_group = data['invert_vertex_group']
    elif kind == "SOLIDIFY":
        mod.thickness = float(data["thickness"])
        mod.offset = _bounded_float(data["offset"], "offset", -1.0, 1.0)
        mod.use_even_offset = bool(data["use_even_offset"])
        mod.use_rim = bool(data["use_rim"])
    elif kind == "BOOLEAN":
        operation = str(data["operation"]).upper()
        if operation not in {"DIFFERENCE", "UNION", "INTERSECT"}:
            raise BadPayload("'operation' must be DIFFERENCE, UNION or INTERSECT")
        solver = str(data["solver"]).upper()
        if solver not in {"EXACT", "FAST"}:
            raise BadPayload("'solver' must be EXACT or FAST")
        mod.operation = operation
        mod.solver = solver
        if "object" in params or data["object"] is not None:
            mod.object = _operand(obj, data["object"])
    elif kind == "MIRROR":
        mod.use_axis = tuple(bool(data[f"use_axis_{axis}"]) for axis in "xyz")
        mod.use_bisect_axis = tuple(bool(data[f"use_bisect_{axis}"]) for axis in "xyz")
        mod.use_bisect_flip_axis = tuple(bool(data[f"use_bisect_flip_{axis}"]) for axis in "xyz")
        mod.use_clip = bool(data["use_clip"])
        mod.use_mirror_merge = bool(data["use_merge"])
        mod.merge_threshold = _bounded_float(data["merge_threshold"], "merge_threshold", 0.0, 1.0)
        if "mirror_object" in params or data["mirror_object"] is not None:
            mod.mirror_object = _mirror_object(obj, data["mirror_object"])


def _bounded_float(value, key, minimum, maximum):
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise BadPayload(f"'{key}' must be a number")
    if not minimum <= result <= maximum:
        raise BadPayload(f"'{key}' must be between {minimum} and {maximum}")
    return result


def _bounded_int(value, key, minimum, maximum):
    if isinstance(value, bool):
        raise BadPayload(f"'{key}' must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise BadPayload(f"'{key}' must be an integer")
    if result != float(value) or not minimum <= result <= maximum:
        raise BadPayload(f"'{key}' must be an integer between {minimum} and {maximum}")
    return result


def _read(mod) -> dict:
    kind = next((key for key, spec in CATALOG.items() if spec["blender"] == mod.type), None)
    params: dict = {}
    if kind in RNA_TYPES:
        params = _read_rna(mod,kind)
        if kind=='LATTICE':params['cage_count']=int(mod.object is not None)
    elif kind == "MULTIRES":
        params = {key: int(getattr(mod, key)) for key in _keys(kind)}
        params['total_levels'] = int(mod.total_levels)
    elif kind == "SUBSURF":
        params = {
            "levels": int(mod.levels),
            "render_levels": int(mod.render_levels),
            "subdivision_type": str(mod.subdivision_type),
        }
    elif kind == "ARRAY":
        params = {
            "count": int(mod.count),
            "relative_offset": list(mod.relative_offset_displace),
            "use_merge": bool(mod.use_merge_vertices),
            "merge_threshold": float(mod.merge_threshold),
            "use_relative_offset": bool(mod.use_relative_offset),
            "use_object_offset": bool(mod.use_object_offset),
            "offset_object": mod.offset_object.name if mod.offset_object else None,
        }
    elif kind == "BEVEL":
        params = {
            "width": float(mod.width),
            "segments": int(mod.segments),
            "affect": str(mod.affect),
            "limit_method": str(mod.limit_method),
            "angle_limit": math.degrees(float(mod.angle_limit)),
            "profile": float(mod.profile),
        }
    elif kind == "SIMPLE_DEFORM":
        params = dict(deform_method=mod.deform_method, deform_axis=mod.deform_axis,
                      angle=math.degrees(mod.angle), factor=mod.factor,
                      limit_lower=float(mod.limits[0]), limit_upper=float(mod.limits[1]),
                      lock_x=mod.lock_x, lock_y=mod.lock_y, lock_z=mod.lock_z,
                      origin=mod.origin.name if mod.origin else None,
                      vertex_group=mod.vertex_group, invert_vertex_group=mod.invert_vertex_group)
    elif kind == "SOLIDIFY":
        params = {
            "thickness": float(mod.thickness),
            "offset": float(mod.offset),
            "use_even_offset": bool(mod.use_even_offset),
            "use_rim": bool(mod.use_rim),
        }
    elif kind == "BOOLEAN":
        params = {
            "operation": str(mod.operation),
            "object": mod.object.name if mod.object else None,
            "solver": str(mod.solver),
        }
    elif kind == "MIRROR":
        params = {
            **{f"use_axis_{axis}": bool(mod.use_axis[index]) for index, axis in enumerate("xyz")},
            **{f"use_bisect_{axis}": bool(mod.use_bisect_axis[index]) for index, axis in enumerate("xyz")},
            **{f"use_bisect_flip_{axis}": bool(mod.use_bisect_flip_axis[index]) for index, axis in enumerate("xyz")},
            "use_clip": bool(mod.use_clip),
            "use_merge": bool(mod.use_mirror_merge),
            "merge_threshold": float(mod.merge_threshold),
            "mirror_object": mod.mirror_object.name if mod.mirror_object else None,
        }
    return {
        "name": mod.name,
        "type": kind or mod.type,
        "show_viewport": bool(mod.show_viewport),
        "show_render": bool(mod.show_render),
        "show_in_editmode": bool(mod.show_in_editmode),
        "parameters": params,
    }


def stack(obj=None) -> dict:
    obj = obj or _target()
    return {"object": obj.name, "modifiers": [_read(mod) for mod in obj.modifiers]}


def describe(obj) -> list[dict]:
    return [_read(mod) for mod in obj.modifiers]


@command("modifier.add_options")
def add_options(payload: dict) -> dict:
    types = {
        "MULTIRES": {"parameters": {
            **{key: dict(_number('int', 1, 0, 6, 1), label=label, max_parameter='total_levels')
               for key, label in [('levels','Vista'), ('sculpt_levels','Escultura'), ('render_levels','Render')]},
            'total_levels': dict(_number('int', 0, 0, 6, 1), label='Niveles creados', read_only=True),
            'subdivide': {'type':'action', 'label':'Subdividir (+1 nivel)', 'max':6, 'max_parameter':'total_levels'},
        }},
        "SUBSURF": {"parameters": {"levels": _number("int", 1, 0, 6, 1), "render_levels": _number("int", 2, 0, 6, 1), "subdivision_type": _enum("CATMULL_CLARK", ["CATMULL_CLARK", "SIMPLE"])}},
        "ARRAY": {"parameters": {"count": _number("int", 2, 1, 1000, 1), "relative_offset": _number("float3", [1.0, 0.0, 0.0], -1000.0, 1000.0, 0.1), "use_merge": {"type": "bool", "default": False}, "merge_threshold": _number("float", 0.01, 0.0, 1000.0, 0.001),
            "use_relative_offset": SCHEMA["ARRAY"]["use_relative_offset"], "use_object_offset": SCHEMA["ARRAY"]["use_object_offset"],
            "offset_object": SCHEMA["ARRAY"]["offset_object"]}},
        "BEVEL": {"parameters": {
            "width": dict(_number("float", 0.1, 0.0, 1000.0, 0.01), label="Ancho", editable=True, unit="LENGTH"),
            "segments": dict(_number("int", 1, 1, 1000, 1), label="Segmentos", editable=True),
            "affect": _enum("EDGES", ["EDGES", "VERTICES"]), "limit_method": _enum("ANGLE", ["NONE", "ANGLE"]),
            "angle_limit": dict(_number("float", 30.0, 0.0, 180.0, 1.0), label="Ángulo", editable=True, unit="ANGLE"),
            "profile": dict(_number("float", 0.5, 0.0, 1.0, 0.05), label="Perfil", editable=True),
        }},
        "SIMPLE_DEFORM": {"parameters": SCHEMA["SIMPLE_DEFORM"]},
        **{kind:{"parameters":dict(SCHEMA[kind], create_cage=dict(type='action',label='Crear jaula ajustada',max=1,max_parameter='cage_count')),
                 "source":"RNA"} for kind in RNA_TYPES},
        "SOLIDIFY": {"parameters": {"thickness": _number("float", 0.1, -1000.0, 1000.0, 0.01), "offset": _number("float", -1.0, -1.0, 1.0, 0.1), "use_even_offset": {"type": "bool", "default": True}, "use_rim": {"type": "bool", "default": True}}},
        "BOOLEAN": {"parameters": {"operation": _enum("DIFFERENCE", ["DIFFERENCE", "UNION", "INTERSECT"]), "object": {"type": "object", "default": None, "object_filter": {"type": "MESH", "exclude_self": True}}, "solver": _enum("EXACT", ["EXACT", "FAST"])}},
        "MIRROR": {"parameters": {
            "use_axis_x": {"type": "bool", "default": True}, "use_axis_y": {"type": "bool", "default": False}, "use_axis_z": {"type": "bool", "default": False},
            "use_bisect_x": {"type": "bool", "default": False}, "use_bisect_y": {"type": "bool", "default": False}, "use_bisect_z": {"type": "bool", "default": False},
            "use_bisect_flip_x": {"type": "bool", "default": False}, "use_bisect_flip_y": {"type": "bool", "default": False}, "use_bisect_flip_z": {"type": "bool", "default": False},
            "use_clip": {"type": "bool", "default": False, "label": "Clipping"}, "use_merge": {"type": "bool", "default": True},
            "merge_threshold": _number("float", 0.001, 0.0, 1.0, 0.001),
            "mirror_object": {"type": "object", "default": None, "object_filter": {"exclude_self": True}}
        }}
    }
    native={item.identifier:item.name for item in bpy.types.Modifier.bl_rna.properties['type'].enum_items}
    labels=dict(SUBSURF='Subdivisión',MULTIRES='Multiresolución',ARRAY='Matriz',BEVEL='Bisel',
                SOLIDIFY='Solidificar',BOOLEAN='Booleano',MIRROR='Espejo',SIMPLE_DEFORM='Deformación simple',LATTICE='Lattice · Jaula')
    for kind,spec in types.items():spec['label']=labels.get(kind,native.get(kind,kind))
    return dict(types=types)



def _number(kind, default, minimum, maximum, step):
    return {"type": kind, "default": default, "min": minimum, "max": maximum, "step": step}


def _enum(default, values):
    return {"type": "enum", "default": default, "values": values}


def multires_change(obj, action, *, level=None, name=None):
    """One native implementation shared by Object's modifier panel and Sculpt."""
    if obj.mode not in {'OBJECT', 'SCULPT'}:
        raise CommandError('Multires requiere Object o Sculpt', code='wrong_mode')
    if obj.use_dynamic_topology_sculpting:
        raise CommandError('Desactiva Dyntopo antes de usar Multires', code='incompatible_modifier')
    mod = _require(obj, name) if name else next((m for m in obj.modifiers if m.type == 'MULTIRES'), None)
    if mod and mod.type != 'MULTIRES': raise BadPayload('El modificador no es Multires')
    if action not in {'add', 'subdivide', 'level'}: raise BadPayload('Acción Multires desconocida')
    if action == 'add' and mod: return mod, False
    if mod is None and action != 'add': raise CommandError('Añade Multires primero', code='not_found')
    if action == 'level':
        level = _bounded_int(level, 'level', 0, mod.total_levels)
    elif mod and mod.total_levels >= 6:
        raise CommandError('Máximo de 6 niveles Multires desde la tablet', code='resolution_limit')
    created = mod is None
    previous_mode = obj.mode
    with view3d_override(), bpy.context.temp_override(object=obj, active_object=obj):
        if previous_mode == 'SCULPT': bpy.ops.object.mode_set(mode='OBJECT')
        try:
            if created: mod = obj.modifiers.new('Multires', 'MULTIRES')
            if action != 'level':
                result = bpy.ops.object.multires_subdivide(modifier=mod.name, mode='CATMULL_CLARK')
                if 'FINISHED' not in result: raise CommandError('No se pudo subdividir Multires', code='subdivide_failed')
                level = mod.total_levels
                mod.render_levels = max(mod.render_levels, level)
            mod.levels = level
            mod.sculpt_levels = level
        except Exception:
            if created and mod: obj.modifiers.remove(mod)
            raise
        finally:
            if previous_mode == 'SCULPT': bpy.ops.object.mode_set(mode='SCULPT')
    return mod, True


@command("modifier.add", mutating=True)
def add(payload: dict) -> dict:
    obj = _target(payload)
    kind = str(payload.get("type", "")).upper()
    spec = CATALOG.get(kind)
    if spec is None:
        raise BadPayload(f"'type' must be one of {', '.join(CATALOG)}")
    params = payload.get("parameters", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise BadPayload("'parameters' must be an object")
    name = str(payload["name"]) if payload.get("name") else spec["default_name"]
    if kind == 'MULTIRES':
        from .sessions import cancel_all
        cancel_all()
        obj = _target(payload)
        mod, changed = multires_change(obj, 'add')
        if not changed: return dict(stack(obj), modifier=mod.name)
        mod.name = name
    else:
        mod = obj.modifiers.new(name, spec["blender"])
    try:
        _write(mod, kind, params, obj)
    except Exception:
        obj.modifiers.remove(mod)
        raise
    undo_push(f"Remote add {kind}")
    result = stack(obj)
    result["modifier"] = mod.name
    return result


@command("modifier.remove", mutating=True)
def remove(payload: dict) -> dict:
    obj = _target(payload)
    mod = _require(obj, payload.get("name"))
    obj.modifiers.remove(mod)
    undo_push("Remote remove modifier")
    return stack(obj)


@command("modifier.move", mutating=True)
def move(payload: dict) -> dict:
    obj = _target(payload)
    mod = _require(obj, payload.get("name"))
    index = get_int(payload, "index", -1)
    if index < 0:
        raise BadPayload("'index' must be a non-negative integer")
    index = min(index, len(obj.modifiers) - 1)
    current = list(obj.modifiers).index(mod)
    while current < index:
        obj.modifiers.move(current, current + 1)
        current += 1
    while current > index:
        obj.modifiers.move(current, current - 1)
        current -= 1
    undo_push("Remote move modifier")
    return stack(obj)


def _create_lattice_cage(obj,mod):
    if mod.object is not None:raise BadPayload('El modificador ya tiene una jaula')
    if not obj.data.vertices:raise BadPayload('La malla está vacía')
    from mathutils import Matrix
    evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    corners=[Vector(p) for p in evaluated.bound_box]
    low=Vector(tuple(min(p[i] for p in corners) for i in range(3)))
    high=Vector(tuple(max(p[i] for p in corners) for i in range(3)))
    size=high-low;minimum=max(max(size)*.01,1e-6)
    size=Vector(tuple(max(v,minimum) for v in size))
    data=bpy.data.lattices.new('Jaula de '+obj.name)
    cage=None
    try:
        data.points_u=data.points_v=data.points_w=4
        cage=bpy.data.objects.new(data.name,data)
        bpy.context.scene.collection.objects.link(cage)
        rest_low=Vector(tuple(min(p.co[i] for p in data.points) for i in range(3)))
        rest_high=Vector(tuple(max(p.co[i] for p in data.points) for i in range(3)))
        cage_scale=tuple(size[i]/max(rest_high[i]-rest_low[i],1e-9) for i in range(3))
        cage.matrix_world=(obj.matrix_world@Matrix.Translation((low+high)*.5)
                           @Matrix.Diagonal((*cage_scale,1.))@Matrix.Translation(-(rest_low+rest_high)*.5))
        cage.show_in_front=True;mod.object=cage
    except Exception:
        mod.object=None
        if cage:bpy.data.objects.remove(cage,do_unlink=True)
        if data.users==0:bpy.data.lattices.remove(data)
        raise


@command("modifier.set", mutating=True)
def set_params(payload: dict) -> dict:
    obj = _target(payload)
    mod = _require(obj, payload.get("name"))
    kind = next((key for key, spec in CATALOG.items() if spec["blender"] == mod.type), None)
    if kind is None:
        raise BadPayload(f"Modifier '{mod.name}' is not a supported type")
    params = payload.get("parameters", payload)
    if not isinstance(params, dict):
        raise BadPayload("'parameters' must be an object")
    if kind=='LATTICE' and params.get('create_cage') is True:
        if any(key in params for key in _keys(kind)):raise BadPayload('Crea la jaula antes de cambiar sus parámetros')
        _create_lattice_cage(obj,mod)
        undo_push('Remote crear jaula Lattice')
        return stack(obj)
    if kind == 'MULTIRES':
        from .sessions import cancel_all
        cancel_all()
        obj = _target(payload)
        mod = _require(obj, payload.get('name'))
        if params.get('subdivide') is True:
            for key in _keys(kind):
                if key in params: _bounded_int(params[key], key, 0, min(mod.total_levels + 1, 6))
            multires_change(obj, 'subdivide', name=mod.name)
    filtered = {key: params[key] for key in _keys(kind) if key in params}
    _write(mod, kind, filtered, obj, preserve_current=True)
    undo_push("Remote set modifier")
    return stack(obj)


@command("modifier.toggle", mutating=True)
def toggle(payload: dict) -> dict:
    obj = _target(payload)
    mod = _require(obj, payload.get("name"))
    if "viewport" in payload:
        mod.show_viewport = bool(payload["viewport"])
    if "render" in payload:
        mod.show_render = bool(payload["render"])
    if "editmode" in payload:
        mod.show_in_editmode = bool(payload["editmode"])
    if "viewport" not in payload and "render" not in payload and "editmode" not in payload:
        mod.show_viewport = not mod.show_viewport
    undo_push("Remote toggle modifier")
    return stack(obj)


@command("modifier.apply", mutating=True)
def apply(payload: dict) -> dict:
    obj = _target(payload)
    if obj.mode != "OBJECT":
        raise CommandError("Applying a modifier requires Object Mode", code="wrong_mode")
    if obj.data is not None and getattr(obj.data, "users", 1) > 1:
        raise CommandError(f"Object '{obj.name}' shares its data", code="shared_data")
    mod = _require(obj, payload.get("name"))
    name = mod.name
    view_layer = bpy.context.view_layer
    old_active = view_layer.objects.active
    old_selected = [item for item in view_layer.objects if item.select_get()]
    old_hidden = obj.hide_get()
    for item in old_selected:
        item.select_set(False)
    obj.hide_set(False)
    obj.select_set(True)
    view_layer.objects.active = obj
    try:
        with view3d_override():
            result = bpy.ops.object.modifier_apply(modifier=name)
    except RuntimeError as exc:
        raise CommandError(f"Cannot apply modifier '{name}': {exc}")
    finally:
        obj.select_set(False)
        obj.hide_set(old_hidden)
        for item in old_selected:
            if item.name in bpy.data.objects:
                item.select_set(True)
        if old_active is not None and old_active.name in bpy.data.objects:
            view_layer.objects.active = old_active
    if result and "FINISHED" not in result:
        raise CommandError(f"Cannot apply modifier '{name}'")
    undo_push("Remote apply modifier")
    return stack(obj)
