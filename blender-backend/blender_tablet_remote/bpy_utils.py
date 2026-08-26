"""Helpers de contexto de Blender. Todo esto corre en el hilo principal."""

from __future__ import annotations

import contextlib

import bmesh
import bpy

from .errors import BadPayload, CommandError


def find_view3d():
    """Devuelve (window, area, region, rv3d) del primer VIEW_3D, o None en background.

    Sin caché a propósito: tras cargar otro .blend los structs de area/region/space se
    liberan y Blender reutiliza sus direcciones, así que validar por `as_pointer()`
    da falsos positivos y devuelve una región caducada (probado en tests: "Region not
    found in area or screen"). Es la trampa que documenta AGENTS.md.
    """
    wm = bpy.context.window_manager
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type != "VIEW_3D":
                continue
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            if region is None:
                continue
            space = area.spaces.active
            return window, area, region, space.region_3d
    return None


@contextlib.contextmanager
def view3d_override():
    """temp_override sobre un VIEW_3D. Sin UI (background) hace un override mínimo."""
    found = find_view3d()
    if found is None:
        with bpy.context.temp_override():
            yield None
        return
    window, area, region, rv3d = found
    with bpy.context.temp_override(window=window, area=area, region=region):
        yield rv3d


def require_rv3d():
    found = find_view3d()
    if found is None:
        raise CommandError("No 3D viewport available (Blender running headless?)", code="no_viewport")
    return found[3]


def active_object():
    obj = bpy.context.view_layer.objects.active
    if obj is None:
        raise CommandError("No active object")
    return obj


def selected_objects() -> list:
    return [o for o in bpy.context.view_layer.objects if o.select_get()]


def resolve_objects(payload: dict) -> list:
    """Objetivos de un comando: payload['objects'] por nombre, o la selección actual."""
    names = payload.get("objects")
    if names:
        if not isinstance(names, list):
            raise BadPayload("'objects' must be a list of names")
        objs = []
        for name in names:
            obj = bpy.data.objects.get(name)
            if obj is None:
                raise CommandError(f"Object not found: {name}", code="not_found")
            objs.append(obj)
        return objs
    objs = selected_objects()
    if not objs:
        obj = bpy.context.view_layer.objects.active
        if obj is not None:
            return [obj]
        raise CommandError("No active object")
    return objs


def edit_bmesh(obj=None):
    """bmesh de la malla en edición. Recuerda llamar a flush_bmesh() después."""
    obj = obj or active_object()
    if obj.type != "MESH":
        raise CommandError(f"Object '{obj.name}' is not a mesh")
    if obj.mode != "EDIT":
        raise CommandError("Not in Edit Mode", code="wrong_mode")
    return bmesh.from_edit_mesh(obj.data)


def flush_bmesh(obj, bm, destructive: bool = True) -> None:
    bmesh.update_edit_mesh(obj.data, loop_triangles=destructive, destructive=destructive)


def get_float3(payload: dict, keys=("x", "y", "z"), default=0.0) -> tuple[float, float, float]:
    """Acepta {"x":..,"y":..,"z":..} o {"vector":[x,y,z]}."""
    vec = payload.get("vector")
    if vec is not None:
        if not isinstance(vec, (list, tuple)) or len(vec) != 3:
            raise BadPayload("'vector' must be [x, y, z]")
        try:
            return float(vec[0]), float(vec[1]), float(vec[2])
        except (TypeError, ValueError):
            raise BadPayload("'vector' must contain numbers")
    out = []
    for key in keys:
        value = payload.get(key, default)
        try:
            out.append(float(value))
        except (TypeError, ValueError):
            raise BadPayload(f"'{key}' must be a number")
    return tuple(out)


def get_float(payload: dict, key: str, default: float) -> float:
    value = payload.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        raise BadPayload(f"'{key}' must be a number")


def get_int(payload: dict, key: str, default: int) -> int:
    value = payload.get(key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        raise BadPayload(f"'{key}' must be an integer")


def undo_push(message: str) -> None:
    """Marca un punto de undo. Sin UI puede fallar; no es motivo para romper el comando."""
    try:
        bpy.ops.ed.undo_push(message=message)
    except RuntimeError:
        pass
