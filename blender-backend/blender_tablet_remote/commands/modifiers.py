"""modifier.* — pila no destructiva del objeto activo.

API de datablock (`obj.modifiers.new`), no operadores. El catálogo es deliberadamente
corto: Subsurf, Array, Bevel, Solidify y Boolean. Bevel aquí no es `mesh.bevel`.
"""

from __future__ import annotations

import math

import bpy
from mathutils import Vector

from ..bpy_utils import active_object, get_int, undo_push, view3d_override
from ..errors import BadPayload, CommandError
from . import command

SCHEMA = {
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
    },
    "BEVEL": {
        "width": {"type": "float", "default": 0.1, "min": 0.0, "max": 1000.0, "step": 0.01},
        "segments": {"type": "int", "default": 1, "min": 1, "max": 1000, "step": 1},
        "affect": {"type": "enum", "default": "EDGES", "values": ["EDGES", "VERTICES"]},
        "limit_method": {"type": "enum", "default": "ANGLE", "values": ["NONE", "ANGLE"]},
        "angle_limit": {"type": "float", "default": 30.0, "min": 0.0, "max": 180.0, "step": 1.0},
        "profile": {"type": "float", "default": 0.5, "min": 0.0, "max": 1.0, "step": 0.05},
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
}

CATALOG = {
    "SUBSURF": {"blender": "SUBSURF", "default_name": "Subdivision"},
    "ARRAY": {"blender": "ARRAY", "default_name": "Array"},
    "BEVEL": {"blender": "BEVEL", "default_name": "Bevel"},
    "SOLIDIFY": {"blender": "SOLIDIFY", "default_name": "Solidify"},
    "BOOLEAN": {"blender": "BOOLEAN", "default_name": "Boolean"},
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


def _write(mod, kind: str, params: dict, obj) -> None:
    data = _defaults(kind)
    data.update({key: params[key] for key in _keys(kind) if key in params})
    if kind == "SUBSURF":
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
        mod.use_relative_offset = True
        mod.relative_offset_displace = Vector((float(offset[0]), float(offset[1]), float(offset[2])))
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
    if kind == "SUBSURF":
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
    return {
        "name": mod.name,
        "type": kind or mod.type,
        "show_viewport": bool(mod.show_viewport),
        "show_render": bool(mod.show_render),
        "parameters": params,
    }


def stack(obj=None) -> dict:
    obj = obj or _target()
    return {"object": obj.name, "modifiers": [_read(mod) for mod in obj.modifiers]}


def describe(obj) -> list[dict]:
    return [_read(mod) for mod in obj.modifiers]


@command("modifier.add_options")
def add_options(payload: dict) -> dict:
    return {"types": {
        "SUBSURF": {"parameters": {"levels": _number("int", 1, 0, 6, 1), "render_levels": _number("int", 2, 0, 6, 1), "subdivision_type": _enum("CATMULL_CLARK", ["CATMULL_CLARK", "SIMPLE"])}},
        "ARRAY": {"parameters": {"count": _number("int", 2, 1, 1000, 1), "relative_offset": _number("float3", [1.0, 0.0, 0.0], -1000.0, 1000.0, 0.1), "use_merge": {"type": "bool", "default": False}, "merge_threshold": _number("float", 0.01, 0.0, 1000.0, 0.001)}},
        "BEVEL": {"parameters": {"width": _number("float", 0.1, 0.0, 1000.0, 0.01), "segments": _number("int", 1, 1, 1000, 1), "affect": _enum("EDGES", ["EDGES", "VERTICES"]), "limit_method": _enum("ANGLE", ["NONE", "ANGLE"]), "angle_limit": _number("float", 30.0, 0.0, 180.0, 1.0), "profile": _number("float", 0.5, 0.0, 1.0, 0.05)}},
        "SOLIDIFY": {"parameters": {"thickness": _number("float", 0.1, -1000.0, 1000.0, 0.01), "offset": _number("float", -1.0, -1.0, 1.0, 0.1), "use_even_offset": {"type": "bool", "default": True}, "use_rim": {"type": "bool", "default": True}}},
        "BOOLEAN": {"parameters": {"operation": _enum("DIFFERENCE", ["DIFFERENCE", "UNION", "INTERSECT"]), "object": {"type": "object", "default": None, "object_filter": {"type": "MESH", "exclude_self": True}}, "solver": _enum("EXACT", ["EXACT", "FAST"])}}
    }}


def _number(kind, default, minimum, maximum, step):
    return {"type": kind, "default": default, "min": minimum, "max": maximum, "step": step}


def _enum(default, values):
    return {"type": "enum", "default": default, "values": values}


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
    filtered = {key: params[key] for key in _keys(kind) if key in params}
    _write(mod, kind, filtered, obj)
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
    if "viewport" not in payload and "render" not in payload:
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
