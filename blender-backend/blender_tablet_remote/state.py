"""Snapshot del estado de Blender y detección de cambios para emitir eventos."""

from __future__ import annotations

import bpy
import bmesh
from mathutils import Vector

from .bpy_utils import find_view3d

SELECT_MODE_NAMES = ("VERTEX", "EDGE", "FACE")

# Catálogos constantes: se construyen una vez en vez de en cada context_snapshot().
_TOOLS_EDIT = ["SELECT", "MOVE", "ROTATE", "SCALE", "EXTRUDE", "BEVEL", "INSET", "SUBDIVIDE", "LOOP_CUT"]
_TOOLS_OBJECT = ["SELECT", "MOVE", "ROTATE", "SCALE"]
_CONSTRAINTS_OBJECT = ["FREE", "X", "Y", "Z", "XY", "XZ", "YZ", "VIEW"]
_CONSTRAINTS_EDIT = ["FREE", "X", "Y", "Z", "XY", "XZ", "YZ", "NORMAL", "VIEW"]
_ORIENTATIONS_OBJECT = ["GLOBAL", "LOCAL", "VIEW"]
_ORIENTATIONS_EDIT = ["GLOBAL", "LOCAL", "NORMAL", "VIEW"]
_SNAP_TYPES = ["NONE", "INCREMENT", "VERTEX", "EDGE_CENTER", "FACE_CENTER"]


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
    from .cad.runtime import runtime
    if runtime.workspace:
        return "CAD"
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
    from .commands.modal import edit_settings_state
    state["edit_settings"] = edit_settings_state()
    state.update(context_snapshot())
    from .cad.runtime import runtime
    state["cad"] = runtime.status()
    from .commands.sculpt import status as sculpt_status
    state["sculpt"] = sculpt_status()

    if active is not None:
        state["active"] = object_info(active)

    if include_view:
        found = find_view3d()
        if found is not None:
            # La vista que se reporta es la de la tablet, no la de la ventana del PC.
            from .camera import camera

            camera.sync_from_region(found[3])
            state["view"] = camera.as_dict()
        # El toggle de wireframe se pinta según esto; sin viewport se asume SOLID.
        from .commands.view import shading_state

        state["shading"] = shading_state()
        # Los overlays los apaga el ojo de la tablet, pero también pueden cambiar en
        # el PC: viaja en el snapshot para que el botón no mienta tras reconectar.
        from .commands.view import overlays_state

        state["overlays"] = overlays_state()
        # La escala de trabajo decide unidades, clipping y pasos: la tablet la necesita
        # para escribir las medidas y para que sus steppers avancen lo que toca.
        from .commands.units import current_scale

        state["scene_scale"] = current_scale()
    return state


def context_snapshot() -> dict:
    """Contrato contextual canónico; no obliga a Android a inferir validez.

    Los conteos de Edit se leen de ``Mesh.total_vert_sel/edge_sel/face_sel``, que
    Blender mantiene en O(1) y con la misma semántica que el código original
    (seleccionado y no oculto). Recorrer las tres secuencias del bmesh aquí costaba
    ~50 ms en una malla de 90 k vértices, y como esta función se llama a 10 Hz y en
    cada comando de selección, ese coste dominaba el hilo principal y convertía la
    selección, el escalado y el vídeo en una sucesión de tirones.
    """
    active = bpy.context.view_layer.objects.active
    mode = "EDIT" if active is not None and active.mode == "EDIT" else "OBJECT"
    sel_mode = selection_mode()
    selected_objects = [o for o in bpy.context.view_layer.objects if o.select_get()]
    counts = {"objects": len(selected_objects), "verts": 0, "edges": 0, "faces": 0}
    center = Vector((0.0, 0.0, 0.0))
    normal = Vector((0.0, 0.0, 1.0))
    if mode == "EDIT" and active is not None and active.type == "MESH":
        mesh = active.data
        counts["verts"] = mesh.total_vert_sel
        counts["edges"] = mesh.total_edge_sel
        counts["faces"] = mesh.total_face_sel
        # Centro y normal solo tienen sentido con algo seleccionado; además recorrer
        # la selección es O(seleccionados), así que se evita por completo si no hay.
        if counts["verts"] or counts["edges"] or counts["faces"]:
            bm = bmesh.from_edit_mesh(active.data)
            if counts["verts"]:
                bm.verts.ensure_lookup_table()
                total = Vector((0.0, 0.0, 0.0))
                n = 0
                for v in bm.verts:
                    if v.select and not v.hide:
                        total += v.co
                        n += 1
                if n:
                    center = active.matrix_world @ (total / n)
            if counts["faces"]:
                bm.faces.ensure_lookup_table()
                local_normal = Vector((0.0, 0.0, 0.0))
                for f in bm.faces:
                    if f.select and not f.hide:
                        local_normal += f.normal
                if local_normal.length_squared:
                    normal = (active.matrix_world.to_3x3() @ local_normal.normalized()).normalized()
    elif selected_objects:
        center = sum((o.matrix_world.translation for o in selected_objects), Vector()) / len(selected_objects)

    edit_tools = _TOOLS_EDIT if mode == "EDIT" else _TOOLS_OBJECT
    return {
        "selection_counts": counts,
        "active_tool": "SELECT",
        "orientation": "GLOBAL",
        "pivot": "MEDIAN",
        "available_tools": edit_tools,
        "available_constraints": _CONSTRAINTS_EDIT if mode == "EDIT" else _CONSTRAINTS_OBJECT,
        "available_orientations": _ORIENTATIONS_EDIT if mode == "EDIT" else _ORIENTATIONS_OBJECT,
        "available_snap_types": _SNAP_TYPES,
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
            # Solo el primer polígono: este snapshot se pide a 10 Hz y preguntar
            # `all(p.use_smooth ...)` recorrería la malla entera en cada uno. Sirve
            # para rotular el interruptor de la tablet; en una malla con sombreado
            # mixto es el estado de referencia, no un censo.
            "shade_smooth": bool(mesh.polygons[0].use_smooth) if mesh.polygons else False,
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
        # `context_snapshot()` calcula centro y normal recorriendo la selección, que
        # es O(seleccionados). En el poll de 10 Hz solo se recalcula cuando la firma
        # barata indica que algo cambió; el resto del tiempo se reutiliza la caché.
        self._context_cache: dict | None = None
        self._context_sig: tuple | None = None

    def reset(self) -> None:
        self._prev = None
        self._context_cache = None
        self._context_sig = None

    @staticmethod
    def _context_signature(selected_names: list[str]) -> tuple:
        """Firma O(1) de las partes dinámicas del contexto.

        Cubre todo lo que `context_snapshot()` emite salvo `selection_center` y
        `selection_normal`, que no tienen consumidor visual en la app y solo se
        recomputan cuando la firma cambia (un tap, un box, un cambio de selección).
        """
        active = bpy.context.view_layer.objects.active
        if active is not None and active.mode == "EDIT" and active.type == "MESH":
            counts = (active.data.total_vert_sel, active.data.total_edge_sel, active.data.total_face_sel)
        else:
            counts = (0, 0, 0)
        return (current_mode(), selection_mode(), counts, tuple(selected_names))

    def _context(self, selected_names: list[str]) -> dict:
        sig = self._context_signature(selected_names)
        if self._context_cache is None or sig != self._context_sig:
            self._context_cache = context_snapshot()
            self._context_sig = sig
        return self._context_cache

    def _light_snapshot(self) -> dict:
        view_layer = bpy.context.view_layer
        active = view_layer.objects.active
        selected_names = sorted(o.name for o in view_layer.objects if o.select_get())
        return {
            "mode": current_mode(),
            "active_object": active.name if active else None,
            "selected_objects": selected_names,
            "selection_mode": selection_mode(),
            "object_count": len(view_layer.objects),
            "context": self._context(selected_names),
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
