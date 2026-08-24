"""transform.* — mover / rotar / escalar, en Object y en Edit Mode.

Se usa la API de datos directamente (matrices y bmesh) en vez de bpy.ops.transform.*:
los operadores dependen del contexto de la ventana y son modales, lo que los hace
frágiles para un servidor remoto. Con matrices el comportamiento es determinista y
funciona igual en background.

Convenios del protocolo:
  - move   : delta en unidades de Blender. `absolute: true` fija la posición.
  - rotate : delta en GRADOS. `radians: true` para radianes. `absolute` fija el euler.
  - scale  : factor multiplicativo. `absolute: true` fija la escala.
  - space  : "GLOBAL" (por defecto) o "LOCAL".
  - pivot  : "INDIVIDUAL" (por defecto en objeto), "MEDIAN", "CURSOR", "WORLD".
"""

from __future__ import annotations

import math

import bpy
from mathutils import Euler, Matrix, Vector

from .. import state
from ..bpy_utils import (
    active_object,
    edit_bmesh,
    flush_bmesh,
    get_float3,
    resolve_objects,
    undo_push,
)
from ..errors import BadPayload, CommandError
from . import command


# ------------------------------------------------------------------ helpers


def _angles(payload: dict) -> Vector:
    x, y, z = get_float3(payload, default=0.0)
    if payload.get("radians"):
        return Vector((x, y, z))
    return Vector((math.radians(x), math.radians(y), math.radians(z)))


def _rotation_matrix(payload: dict) -> Matrix:
    """Rotación por eje/ángulo si viene 'axis'+'angle', si no euler XYZ."""
    axis = payload.get("axis")
    if axis is not None:
        if not isinstance(axis, (list, tuple)) or len(axis) != 3:
            raise BadPayload("'axis' must be [x, y, z]")
        vec = Vector((float(axis[0]), float(axis[1]), float(axis[2])))
        if vec.length == 0:
            raise BadPayload("'axis' cannot be a zero vector")
        angle = float(payload.get("angle", 0.0))
        if not payload.get("radians"):
            angle = math.radians(angle)
        return Matrix.Rotation(angle, 3, vec.normalized())
    return Euler(_angles(payload), "XYZ").to_matrix()


def _scale_matrix(payload: dict) -> Matrix:
    if "factor" in payload:
        f = float(payload["factor"])
        vec = Vector((f, f, f))
    else:
        vec = Vector(get_float3(payload, default=1.0))
    if vec.x == 0 or vec.y == 0 or vec.z == 0:
        raise BadPayload("scale factors cannot be zero")
    m = Matrix.Identity(3)
    m[0][0], m[1][1], m[2][2] = vec.x, vec.y, vec.z
    return m


def _pivot_point(payload: dict, objs, default: str = "INDIVIDUAL") -> tuple[str, Vector | None]:
    kind = str(payload.get("pivot", default)).upper()
    if kind == "INDIVIDUAL":
        return kind, None
    if kind == "CURSOR":
        return kind, Vector(bpy.context.scene.cursor.location)
    if kind == "WORLD":
        return kind, Vector((0.0, 0.0, 0.0))
    if kind == "MEDIAN":
        if not objs:
            return kind, Vector((0.0, 0.0, 0.0))
        total = Vector((0.0, 0.0, 0.0))
        for obj in objs:
            total += obj.matrix_world.translation
        return kind, total / len(objs)
    raise BadPayload("'pivot' must be INDIVIDUAL, MEDIAN, CURSOR or WORLD")


def _apply_around(obj, mat3: Matrix, pivot: Vector | None) -> None:
    """Aplica una transformación lineal global alrededor de un pivote del mundo."""
    world = obj.matrix_world
    center = pivot if pivot is not None else world.translation.copy()
    m4 = mat3.to_4x4()
    obj.matrix_world = Matrix.Translation(center) @ m4 @ Matrix.Translation(-center) @ world


def _in_edit_mode() -> bool:
    obj = bpy.context.view_layer.objects.active
    return obj is not None and obj.mode == "EDIT"


def _selected_verts(bm):
    verts = [v for v in bm.verts if v.select]
    if not verts:
        raise CommandError("No selected vertices", code="empty_selection")
    return verts


def _edit_pivot(payload: dict, obj, verts) -> Vector:
    kind = str(payload.get("pivot", "MEDIAN")).upper()
    if kind == "CURSOR":
        return obj.matrix_world.inverted() @ Vector(bpy.context.scene.cursor.location)
    if kind == "WORLD":
        return obj.matrix_world.inverted() @ Vector((0.0, 0.0, 0.0))
    total = Vector((0.0, 0.0, 0.0))
    for v in verts:
        total += v.co
    return total / len(verts)


def _to_local_linear(obj, mat3: Matrix, space: str) -> Matrix:
    if space == "LOCAL":
        return mat3
    w3 = obj.matrix_world.to_3x3()
    return w3.inverted() @ mat3 @ w3


def _space(payload: dict) -> str:
    space = str(payload.get("space", "GLOBAL")).upper()
    if space not in {"GLOBAL", "LOCAL"}:
        raise BadPayload("'space' must be GLOBAL or LOCAL")
    return space


def _result(objs) -> dict:
    return {
        "mode": state.current_mode(),
        "objects": [state.object_info(o) for o in objs if o.name in bpy.data.objects],
    }


# ----------------------------------------------------------------- comandos


@command("transform.move", mutating=True)
def move(payload: dict) -> dict:
    delta = Vector(get_float3(payload, default=0.0))
    space = _space(payload)

    if _in_edit_mode():
        obj = active_object()
        bm = edit_bmesh(obj)
        verts = _selected_verts(bm)
        local = delta if space == "LOCAL" else obj.matrix_world.to_3x3().inverted() @ delta
        if payload.get("absolute"):
            raise BadPayload("'absolute' is not supported in Edit Mode")
        for v in verts:
            v.co += local
        flush_bmesh(obj, bm, destructive=False)
        _push(payload, "Remote move")
        return {"mode": "EDIT", "verts": len(verts)}

    objs = resolve_objects(payload)
    for obj in objs:
        if payload.get("absolute"):
            obj.location = delta
        elif space == "LOCAL":
            world = obj.matrix_world.copy()
            world.translation += obj.matrix_world.to_3x3() @ delta
            obj.matrix_world = world
        else:
            world = obj.matrix_world.copy()
            world.translation += delta
            obj.matrix_world = world
    _push(payload, "Remote move")
    return _result(objs)


@command("transform.rotate", mutating=True)
def rotate(payload: dict) -> dict:
    space = _space(payload)

    if _in_edit_mode():
        obj = active_object()
        bm = edit_bmesh(obj)
        verts = _selected_verts(bm)
        mat = _to_local_linear(obj, _rotation_matrix(payload), space)
        pivot = _edit_pivot(payload, obj, verts)
        for v in verts:
            v.co = pivot + mat @ (v.co - pivot)
        flush_bmesh(obj, bm, destructive=False)
        _push(payload, "Remote rotate")
        return {"mode": "EDIT", "verts": len(verts)}

    objs = resolve_objects(payload)
    if payload.get("absolute"):
        angles = _angles(payload)
        for obj in objs:
            obj.rotation_mode = "XYZ"
            obj.rotation_euler = angles
        _push(payload, "Remote rotate")
        return _result(objs)

    mat = _rotation_matrix(payload)
    _kind, pivot = _pivot_point(payload, objs)
    for obj in objs:
        local_mat = mat if space == "GLOBAL" else obj.matrix_world.to_3x3() @ mat @ obj.matrix_world.to_3x3().inverted()
        _apply_around(obj, local_mat, pivot)
    _push(payload, "Remote rotate")
    return _result(objs)


@command("transform.scale", mutating=True)
def scale(payload: dict) -> dict:
    space = _space(payload)

    if _in_edit_mode():
        obj = active_object()
        bm = edit_bmesh(obj)
        verts = _selected_verts(bm)
        mat = _to_local_linear(obj, _scale_matrix(payload), space)
        pivot = _edit_pivot(payload, obj, verts)
        for v in verts:
            v.co = pivot + mat @ (v.co - pivot)
        flush_bmesh(obj, bm, destructive=False)
        _push(payload, "Remote scale")
        return {"mode": "EDIT", "verts": len(verts)}

    objs = resolve_objects(payload)
    if payload.get("absolute"):
        vec = Vector(get_float3(payload, default=1.0))
        for obj in objs:
            obj.scale = vec
        _push(payload, "Remote scale")
        return _result(objs)

    mat = _scale_matrix(payload)
    _kind, pivot = _pivot_point(payload, objs)
    for obj in objs:
        local_mat = mat if space == "GLOBAL" else obj.matrix_world.to_3x3() @ mat @ obj.matrix_world.to_3x3().inverted()
        _apply_around(obj, local_mat, pivot)
    _push(payload, "Remote scale")
    return _result(objs)


@command("transform.reset", mutating=True)
def reset(payload: dict) -> dict:
    """Pone loc/rot/escala a identidad. No hornea: la malla no cambia."""
    objs = resolve_objects(payload)
    what = {str(w).upper() for w in payload.get("what", ["LOCATION", "ROTATION", "SCALE"])}
    for obj in objs:
        if "LOCATION" in what:
            obj.location = (0.0, 0.0, 0.0)
        if "ROTATION" in what:
            obj.rotation_euler = (0.0, 0.0, 0.0)
        if "SCALE" in what:
            obj.scale = (1.0, 1.0, 1.0)
    undo_push("Remote reset transform")
    return _result(objs)


@command("transform.apply", mutating=True)
def apply(payload: dict) -> dict:
    """Hornea loc/rot/escala en la malla y deja el transform en identidad (Ctrl+A)."""
    if _in_edit_mode():
        raise CommandError("Applying transforms requires Object Mode", code="wrong_mode")
    use_loc = bool(payload.get("location", False))
    use_rot = bool(payload.get("rotation", False))
    use_scl = bool(payload.get("scale", False))
    if not (use_loc or use_rot or use_scl):
        raise BadPayload("transform.apply needs location, rotation or scale set to true")
    objs = resolve_objects(payload)
    for obj in objs:
        if obj.data is None or not hasattr(obj.data, "transform"):
            raise CommandError(f"Object type '{obj.type}' cannot apply transforms", code="unsupported_type")
        if obj.data is not None and getattr(obj.data, "users", 1) > 1:
            raise CommandError(f"Object '{obj.name}' shares its data", code="shared_data")
    for obj in objs:
        _bake_transform(obj, use_loc, use_rot, use_scl)
    undo_push("Remote apply transform")
    return _result(objs)


def _bake_transform(obj, use_loc: bool, use_rot: bool, use_scl: bool) -> None:
    loc, rot, scale = obj.matrix_basis.decompose()
    ident = Matrix.Identity(4)
    parts = [Matrix.Translation(loc), rot.to_matrix().to_4x4(), Matrix.Diagonal(scale.to_4d())]
    baked = [ident.copy(), ident.copy(), ident.copy()]
    leftover = list(parts)
    if use_loc:
        baked[0], leftover[0] = leftover[0], baked[0]
    if use_rot:
        baked[1], leftover[1] = leftover[1], baked[1]
    if use_scl:
        baked[2], leftover[2] = leftover[2], baked[2]
    bake = baked[0] @ baked[1] @ baked[2]
    if hasattr(obj.data, "transform"):
        obj.data.transform(bake)
        if hasattr(obj.data, "update"):
            obj.data.update()
    for child in obj.children:
        child.matrix_local = bake.inverted() @ child.matrix_local
    obj.matrix_basis = leftover[0] @ leftover[1] @ leftover[2]


def _push(payload: dict, label: str) -> None:
    """Durante un gesto el undo_push lo hace el gestor al soltar el dedo."""
    if not payload.get("_no_undo"):
        undo_push(label)
