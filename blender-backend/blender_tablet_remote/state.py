"""Snapshot del estado de Blender y detección de cambios para emitir eventos."""

from __future__ import annotations

import bpy
import bmesh
from mathutils import Vector

from .bpy_utils import find_view3d

SELECT_MODE_NAMES = ("VERTEX", "EDGE", "FACE")


def selection_mode() -> str:
    try:
        flags = bpy.context.scene.tool_settings.mesh_select_mode
    except AttributeError:
        return "VERTEX"
    for name, on in zip(SELECT_MODE_NAMES, flags):
        if on:
            return name
    return "VERTEX"


def current_mode() -> str:
    obj = bpy.context.view_layer.objects.active
    return obj.mode if obj is not None else "OBJECT"


def snapshot(include_view: bool = True) -> dict:
    """Estado que consume la tablet. Barato: pensado para llamarse a 10 Hz."""
    view_layer = bpy.context.view_layer
    active = view_layer.objects.active
    selected = [o.name for o in view_layer.objects if o.select_get()]

    state = {
        "mode": current_mode(),
        "active_object": active.name if active else None,
        "selected_objects": selected,
        "selection_mode": selection_mode(),
        "scene": bpy.context.scene.name,
        "frame": bpy.context.scene.frame_current,
        "hidden_objects": hidden_objects(),
    }
    state.update(context_snapshot())

    if active is not None:
        state["active"] = object_info(active)

    if include_view:
        found = find_view3d()
        if found is not None:
            # La vista que se reporta es la de la tablet, no la de la ventana del PC.
            from .camera import camera

            camera.sync_from_region(found[3])
            state["view"] = camera.as_dict()
        # Va con el estado para que la tablet pueda pintar el manipulador en cuanto
        # cambia la selección, sin una segunda petición.
        from .commands.view import gizmo_state

        state["gizmo"] = gizmo_state()

    return state


def context_snapshot() -> dict:
    """Contrato contextual canónico; no obliga a Android a inferir validez."""
    active = bpy.context.view_layer.objects.active
    mode = "EDIT" if active is not None and active.mode == "EDIT" else "OBJECT"
    sel_mode = selection_mode()
    selected_objects = [o for o in bpy.context.view_layer.objects if o.select_get()]
    counts = {"objects": len(selected_objects), "verts": 0, "edges": 0, "faces": 0}
    center = Vector((0.0, 0.0, 0.0))
    normal = Vector((0.0, 0.0, 1.0))
    if mode == "EDIT" and active is not None and active.type == "MESH":
        bm = bmesh.from_edit_mesh(active.data)
        verts = [v for v in bm.verts if v.select and not v.hide]
        edges = [e for e in bm.edges if e.select and not e.hide]
        faces = [f for f in bm.faces if f.select and not f.hide]
        counts.update(verts=len(verts), edges=len(edges), faces=len(faces))
        if verts:
            center = active.matrix_world @ (sum((v.co for v in verts), Vector()) / len(verts))
        if faces:
            local_normal = sum((f.normal for f in faces), Vector())
            if local_normal.length_squared:
                normal = (active.matrix_world.to_3x3() @ local_normal.normalized()).normalized()
    elif selected_objects:
        center = sum((o.matrix_world.translation for o in selected_objects), Vector()) / len(selected_objects)

    edit_tools = ["SELECT", "MOVE", "ROTATE", "SCALE", "EXTRUDE", "BEVEL", "INSET", "SUBDIVIDE", "LOOP_CUT"]
    return {
        "selection_counts": counts,
        "active_tool": "SELECT",
        "orientation": "GLOBAL",
        "pivot": "MEDIAN",
        "available_tools": edit_tools if mode == "EDIT" else ["SELECT", "MOVE", "ROTATE", "SCALE"],
        "available_constraints": ["FREE", "X", "Y", "Z", "XY", "XZ", "YZ"] + (["NORMAL"] if mode == "EDIT" else []) + ["VIEW"],
        "available_orientations": ["GLOBAL", "LOCAL"] + (["NORMAL"] if mode == "EDIT" else []) + ["VIEW"],
        "available_snap_types": ["NONE", "INCREMENT", "GRID", "VERTEX", "EDGE", "FACE", "CURSOR"],
        "selection_center": list(center),
        "selection_normal": list(normal),
        "selection_mode": sel_mode,
    }


def object_info(obj) -> dict:
    info = {
        "name": obj.name,
        "type": obj.type,
        "location": list(obj.location),
        "rotation_euler": list(obj.rotation_euler),
        "scale": list(obj.scale),
        "dimensions": list(obj.dimensions),
        "visible": not obj.hide_get(),
        "modifiers": _modifier_info(obj),
    }
    if obj.type == "MESH":
        mesh = obj.data
        info["mesh"] = {
            "vertices": len(mesh.vertices),
            "edges": len(mesh.edges),
            "polygons": len(mesh.polygons),
        }
    return info


def _modifier_info(obj) -> list[dict]:
    from .commands import modifiers as modifier_commands

    return modifier_commands.describe(obj)


def scene_objects() -> list[dict]:
    return [
        {"name": o.name, "type": o.type, "selected": o.select_get(), "visible": not o.hide_get()}
        for o in bpy.context.view_layer.objects
    ]


def hidden_objects() -> list[dict]:
    return [{"name": obj.name, "type": obj.type}
            for obj in bpy.context.view_layer.objects if obj.hide_get()]


class StateWatcher:
    """Compara snapshots ligeros y produce eventos solo cuando algo cambia de verdad."""

    def __init__(self):
        self._prev: dict | None = None

    def reset(self) -> None:
        self._prev = None

    def _light_snapshot(self) -> dict:
        view_layer = bpy.context.view_layer
        active = view_layer.objects.active
        context = context_snapshot()
        return {
            "mode": current_mode(),
            "active_object": active.name if active else None,
            "selected_objects": sorted(o.name for o in view_layer.objects if o.select_get()),
            "selection_mode": selection_mode(),
            "object_count": len(view_layer.objects),
            "context": context,
            "modifiers": {obj.name: _modifiers_sig(obj) for obj in view_layer.objects if obj.modifiers},
            "hidden": tuple(sorted(o.name for o in view_layer.objects if o.hide_get())),
        }

    def poll(self) -> list[dict]:
        """Devuelve la lista de eventos a difundir desde el último poll()."""
        try:
            current = self._light_snapshot()
        except (AttributeError, ReferenceError):
            return []

        prev, self._prev = self._prev, current
        if prev is None:
            return []

        events = []
        if prev["mode"] != current["mode"]:
            events.append(_event("mode.changed", {"mode": current["mode"]}))
        if prev["active_object"] != current["active_object"]:
            events.append(_event("active_object.changed", {"object": current["active_object"]}))
        if prev["selected_objects"] != current["selected_objects"]:
            events.append(
                _event(
                    "selection.changed",
                    {
                        "objects": current["selected_objects"],
                        "object": current["active_object"],
                    },
                )
            )
        if prev["selection_mode"] != current["selection_mode"]:
            events.append(_event("selection_mode.changed", {"selection_mode": current["selection_mode"]}))
        if prev["object_count"] != current["object_count"]:
            events.append(_event("scene.changed", {"object_count": current["object_count"]}))
        if prev["context"] != current["context"]:
            events.append(_event("context.changed", current["context"]))
        if prev["modifiers"] != current["modifiers"]:
            changed = next((name for name in set(prev["modifiers"]) | set(current["modifiers"])
                            if prev["modifiers"].get(name) != current["modifiers"].get(name)),
                           current["active_object"])
            active_now = bpy.data.objects.get(changed) if changed else None
            events.append(_event("modifiers.changed", {
                "object": changed,
                "modifiers": _modifier_info(active_now) if active_now else [],
            }))
        if prev["hidden"] != current["hidden"]:
            events.append(_event("visibility.changed", {"hidden_objects": hidden_objects()}))
        return events


def _modifiers_sig(obj) -> tuple:
    if obj is None:
        return ()
    bits = []
    for mod in obj.modifiers:
        entry = [mod.name, mod.type, bool(mod.show_viewport), bool(mod.show_render)]
        for attr in ("levels", "render_levels", "count", "width", "segments", "thickness",
                     "offset", "operation", "solver", "affect", "limit_method", "profile"):
            if hasattr(mod, attr):
                value = getattr(mod, attr)
                entry.append(tuple(value) if hasattr(value, "__iter__") and not isinstance(value, str) else value)
        if getattr(mod, "object", None) is not None:
            entry.append(mod.object.name)
        if hasattr(mod, "relative_offset_displace"):
            entry.append(tuple(mod.relative_offset_displace))
        bits.append(tuple(entry))
    return tuple(bits)


def _event(name: str, payload: dict) -> dict:
    return {"type": "event", "event": name, "payload": payload}
