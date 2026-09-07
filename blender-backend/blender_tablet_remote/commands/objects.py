"""object.* — selección y gestión de objetos (API directa, sin operadores)."""

from __future__ import annotations

import bpy

from .. import state
from ..bpy_utils import resolve_objects, undo_push
from ..errors import BadPayload, CommandError
from . import command


def _select(obj, value: bool) -> None:
    try:
        obj.select_set(value)
    except RuntimeError as exc:  # objeto no en el view layer activo
        raise CommandError(f"Cannot select '{obj.name}': {exc}")


@command("object.select")
def select(payload: dict) -> dict:
    """payload: {name | names[], mode: "SET"|"ADD"|"REMOVE"|"TOGGLE", active: bool}"""
    mode = str(payload.get("mode", "SET")).upper()
    if mode not in {"SET", "ADD", "REMOVE", "TOGGLE"}:
        raise BadPayload("'mode' must be SET, ADD, REMOVE or TOGGLE")

    names = payload.get("names")
    if names is None:
        name = payload.get("name")
        names = [name] if name else []
    if not isinstance(names, list):
        raise BadPayload("'names' must be a list")

    view_layer = bpy.context.view_layer
    if mode == "SET":
        for obj in view_layer.objects:
            _select(obj, False)

    last = None
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj is None:
            raise CommandError(f"Object not found: {name}", code="not_found")
        if mode == "REMOVE":
            _select(obj, False)
        elif mode == "TOGGLE":
            _select(obj, not obj.select_get())
        else:
            _select(obj, True)
        last = obj

    if last is not None and payload.get("active", True) and mode != "REMOVE":
        view_layer.objects.active = last

    return {"selected_objects": [o.name for o in view_layer.objects if o.select_get()]}


@command("object.select_all")
def select_all(payload: dict) -> dict:
    value = bool(payload.get("value", True))
    for obj in bpy.context.view_layer.objects:
        _select(obj, value)
    return {"selected_objects": [o.name for o in bpy.context.view_layer.objects if o.select_get()]}


@command("object.shade", mutating=True)
def shade(payload: dict) -> dict:
    """Alterna o fija sombreado plano/suave en las mallas indicadas o seleccionadas."""
    _require_object_mode()
    mode = str(payload.get("mode", "TOGGLE")).upper()
    if mode not in {"TOGGLE", "FLAT", "SMOOTH"}:
        raise BadPayload("'mode' must be TOGGLE, FLAT or SMOOTH")
    meshes = [obj for obj in resolve_objects(payload) if obj.type == "MESH"]
    if not meshes:
        raise CommandError("Object shading requires at least one mesh", code="wrong_type")
    polygons = [polygon for obj in meshes for polygon in obj.data.polygons]
    smooth = (not polygons or not all(polygon.use_smooth for polygon in polygons)) \
        if mode == "TOGGLE" else mode == "SMOOTH"
    for polygon in polygons:
        polygon.use_smooth = smooth
    undo_push("Remote shade smooth" if smooth else "Remote shade flat")
    return dict(state.snapshot(include_view=False), shaded=[obj.name for obj in meshes],
                shade="SMOOTH" if smooth else "FLAT")


@command("object.set_active")
def set_active(payload: dict) -> dict:
    name = payload.get("name")
    obj = bpy.data.objects.get(name) if name else None
    if obj is None:
        raise CommandError(f"Object not found: {name}", code="not_found")
    bpy.context.view_layer.objects.active = obj
    return {"active_object": obj.name}


@command("object.delete", mutating=True)
def delete(payload: dict) -> dict:
    from .sessions import cancel_all
    cancel_all(restore=True)
    objs = resolve_objects(payload)
    removed = [o.name for o in objs]
    for obj in objs:
        bpy.data.objects.remove(obj, do_unlink=True)
    undo_push("Remote delete")
    return {"deleted": removed}


@command("object.duplicate", mutating=True)
def duplicate(payload: dict) -> dict:
    """linked=True comparte los datos de malla (como Alt+D)."""
    objs = resolve_objects(payload)
    linked = bool(payload.get("linked", False))
    view_layer = bpy.context.view_layer
    collection = bpy.context.collection

    for obj in view_layer.objects:
        _select(obj, False)

    created = []
    for obj in objs:
        copy = obj.copy()
        if not linked and copy.data is not None:
            copy.data = obj.data.copy()
        collection.objects.link(copy)
        _select(copy, True)
        created.append(copy.name)

    if created:
        view_layer.objects.active = bpy.data.objects[created[-1]]
    undo_push("Remote duplicate")
    return {"created": created}


# Catálogo del menú Add de Blender. Nombre plano -> (categoría, cómo se crea).
#
# Se usa un nombre plano en vez de (tipo + primitiva) para que el cliente mande un
# único valor y el enum de Kotlin sea un espejo directo de estas claves.
#
# El valor es (categoría, callable, kwargs): los metaballs, vacíos y luces comparten
# operador y se distinguen por `type`, así que no basta con guardar la función.
#
# Se construye una vez y se cachea: 36 entradas por cada object.add/add_options era
# asignación gratuita en el camino de creación de primitivas.
_ADD_CATALOG: dict[str, tuple[str, object, dict]] | None = None


def _add_catalog() -> dict[str, tuple[str, object, dict]]:
    global _ADD_CATALOG
    if _ADD_CATALOG is not None:
        return _ADD_CATALOG
    mesh = bpy.ops.mesh
    obj = bpy.ops.object
    curve = bpy.ops.curve
    surface = bpy.ops.surface
    _ADD_CATALOG = {
        # Malla
        "PLANE": ("MESH", mesh.primitive_plane_add, {}),
        "CUBE": ("MESH", mesh.primitive_cube_add, {}),
        "CIRCLE": ("MESH", mesh.primitive_circle_add, {}),
        "SPHERE": ("MESH", mesh.primitive_uv_sphere_add, {}),
        "ICO_SPHERE": ("MESH", mesh.primitive_ico_sphere_add, {}),
        "CYLINDER": ("MESH", mesh.primitive_cylinder_add, {}),
        "CONE": ("MESH", mesh.primitive_cone_add, {}),
        "TORUS": ("MESH", mesh.primitive_torus_add, {}),
        "GRID": ("MESH", mesh.primitive_grid_add, {}),
        "MONKEY": ("MESH", mesh.primitive_monkey_add, {}),
        # Curva
        "BEZIER_CURVE": ("CURVE", curve.primitive_bezier_curve_add, {}),
        "BEZIER_CIRCLE": ("CURVE", curve.primitive_bezier_circle_add, {}),
        "NURBS_CURVE": ("CURVE", curve.primitive_nurbs_curve_add, {}),
        "NURBS_CIRCLE": ("CURVE", curve.primitive_nurbs_circle_add, {}),
        "PATH": ("CURVE", curve.primitive_nurbs_path_add, {}),
        # Superficie
        "SURFACE_CURVE": ("SURFACE", surface.primitive_nurbs_surface_curve_add, {}),
        "SURFACE_CIRCLE": ("SURFACE", surface.primitive_nurbs_surface_circle_add, {}),
        "SURFACE_PATCH": ("SURFACE", surface.primitive_nurbs_surface_surface_add, {}),
        "SURFACE_CYLINDER": ("SURFACE", surface.primitive_nurbs_surface_cylinder_add, {}),
        "SURFACE_SPHERE": ("SURFACE", surface.primitive_nurbs_surface_sphere_add, {}),
        "SURFACE_TORUS": ("SURFACE", surface.primitive_nurbs_surface_torus_add, {}),
        # Metaball
        "META_BALL": ("METABALL", obj.metaball_add, {"type": "BALL"}),
        "META_CAPSULE": ("METABALL", obj.metaball_add, {"type": "CAPSULE"}),
        "META_PLANE": ("METABALL", obj.metaball_add, {"type": "PLANE"}),
        "META_ELLIPSOID": ("METABALL", obj.metaball_add, {"type": "ELLIPSOID"}),
        "META_CUBE": ("METABALL", obj.metaball_add, {"type": "CUBE"}),
        # Otros
        "TEXT": ("TEXT", obj.text_add, {}),
        "EMPTY_PLAIN_AXES": ("EMPTY", obj.empty_add, {"type": "PLAIN_AXES"}),
        "EMPTY_ARROWS": ("EMPTY", obj.empty_add, {"type": "ARROWS"}),
        "EMPTY_SINGLE_ARROW": ("EMPTY", obj.empty_add, {"type": "SINGLE_ARROW"}),
        "EMPTY_CIRCLE": ("EMPTY", obj.empty_add, {"type": "CIRCLE"}),
        "EMPTY_CUBE": ("EMPTY", obj.empty_add, {"type": "CUBE"}),
        "EMPTY_SPHERE": ("EMPTY", obj.empty_add, {"type": "SPHERE"}),
        "EMPTY_CONE": ("EMPTY", obj.empty_add, {"type": "CONE"}),
        "LIGHT_POINT": ("LIGHT", obj.light_add, {"type": "POINT"}),
        "LIGHT_SUN": ("LIGHT", obj.light_add, {"type": "SUN"}),
        "LIGHT_SPOT": ("LIGHT", obj.light_add, {"type": "SPOT"}),
        "LIGHT_AREA": ("LIGHT", obj.light_add, {"type": "AREA"}),
        "CAMERA": ("CAMERA", obj.camera_add, {}),
    }
    return _ADD_CATALOG


@command("object.add_options")
def add_options(payload: dict) -> dict:
    """Qué se puede añadir, agrupado por categoría. Para que el cliente no adivine."""
    grouped: dict[str, list[str]] = {}
    for name, (category, _op, _kwargs) in _add_catalog().items():
        grouped.setdefault(category, []).append(name)
    return {"categories": grouped}


def _sized_kwargs(op, kwargs: dict) -> dict:
    """El tamaño con el que nace la primitiva, según la escala de trabajo.

    El cubo de 2 unidades de Blender es enorme para una pieza de milímetros y diminuto
    para un edificio, y quien elige un preset no quiere escalar a mano cada objeto que
    añade. Cada operador nombra su tamaño de forma distinta —`size`, `radius`, los dos
    radios del toro—, así que se pregunta al RNA en vez de mantener aquí una tabla que
    se desincronizaría con Blender. Un tamaño explícito del cliente siempre gana.
    """
    from .units import current_scale

    scale = current_scale()
    # El preset expresa metros físicos; los operadores reciben unidades Blender.
    # En un archivo con 1 BU = 1 mm, 10 mm son 10 BU, no 0.01 BU.
    size = float(scale.get("primitive_size") or 0.0) / scale["scale_length"]
    if size <= 0.0:
        return kwargs
    try:
        properties = op.get_rna_type().properties
    except (AttributeError, RuntimeError):
        return kwargs

    sized = dict(kwargs)
    if "size" in properties:
        sized.setdefault("size", size)
    if "radius" in properties:
        sized.setdefault("radius", size / 2.0)
    if "radius1" in properties:  # cono: base y punta
        sized.setdefault("radius1", size / 2.0)
    if "depth" in properties:
        sized.setdefault("depth", size)
    if "major_radius" in properties:
        sized.setdefault("major_radius", size / 2.0)
        sized.setdefault("minor_radius", size / 8.0)
    return sized


@command("object.add", mutating=True)
def add_primitive(payload: dict) -> dict:
    """Equivalente al menú Add de Blender: mallas, curvas, superficies, texto…

    Sin `x/y/z` explícitos se añade **en el cursor 3D**, como Blender. Antes se
    añadía siempre en el origen del mundo, que hacía inútil todo el menú de cursor.
    """
    kind = str(payload.get("primitive", "CUBE")).upper()
    catalog = _add_catalog()
    entry = catalog.get(kind)
    if entry is None:
        raise BadPayload(f"Unknown primitive '{kind}'. Options: {', '.join(sorted(catalog))}")
    category, op, kwargs = entry

    from ..bpy_utils import get_float3, view3d_override

    if any(axis in payload or "vector" in payload for axis in ("x", "y", "z")):
        location = get_float3(payload, default=0.0)
    else:
        location = tuple(bpy.context.scene.cursor.location)

    # En Edit Mode, Blender solo deja añadir mallas (se fusionan con la que se edita).
    # El resto crea un objeto nuevo y necesita Object Mode.
    active = bpy.context.view_layer.objects.active
    if category != "MESH" and active is not None and active.mode != "OBJECT":
        raise CommandError(f"Adding a {category.lower()} requires Object Mode", code="wrong_mode")

    try:
        with view3d_override():
            op(location=location, **_sized_kwargs(op, kwargs))
    except RuntimeError as exc:
        raise CommandError(f"Cannot add {kind}: {exc}")

    undo_push(f"Remote add {kind}")
    return state.snapshot(include_view=False)


@command("object.rename", mutating=True)
def rename(payload: dict) -> dict:
    name = payload.get("name")
    new_name = payload.get("new_name")
    if not new_name:
        raise BadPayload("'new_name' is required")
    obj = bpy.data.objects.get(name) if name else bpy.context.view_layer.objects.active
    if obj is None:
        raise CommandError(f"Object not found: {name}", code="not_found")
    obj.name = str(new_name)
    return {"name": obj.name}


def _hide_set(obj, value: bool) -> None:
    try:
        obj.hide_set(value)
    except RuntimeError as exc:
        raise CommandError(f"Cannot hide '{obj.name}': {exc}")


def _visibility_result(**extra) -> dict:
    view_layer = bpy.context.view_layer
    result = {
        "hidden_objects": state.hidden_objects(),
        "selected_objects": [obj.name for obj in view_layer.objects if obj.select_get()],
        "active_object": view_layer.objects.active.name if view_layer.objects.active else None,
    }
    result.update(extra)
    return result


def _require_object_mode() -> None:
    active = bpy.context.view_layer.objects.active
    if active is not None and active.mode != "OBJECT":
        raise CommandError("Object visibility requires Object Mode", code="wrong_mode")


@command("object.hide", mutating=True)
def hide(payload: dict) -> dict:
    _require_object_mode()
    view_layer = bpy.context.view_layer
    unselected = bool(payload.get("unselected", False))
    if unselected:
        kept = {obj.name for obj in resolve_objects(payload)}
        targets = [obj for obj in view_layer.objects if obj.name not in kept]
    else:
        targets = resolve_objects(payload)
    hidden = []
    for obj in targets:
        _hide_set(obj, True)
        hidden.append(obj.name)
    if hidden:
        # Lo ocultado a mano durante un aislamiento no se revela al desaislar.
        from .view import forget_local_hidden

        forget_local_hidden(hidden)
    active = view_layer.objects.active
    if active is not None and active.hide_get():
        view_layer.objects.active = next((obj for obj in view_layer.objects if obj.select_get() and not obj.hide_get()), None)
    undo_push("Remote hide")
    return _visibility_result(hidden=hidden)


@command("object.reveal", mutating=True)
def reveal(payload: dict) -> dict:
    _require_object_mode()
    select = bool(payload.get("select", True))
    names = payload.get("objects")
    view_layer = bpy.context.view_layer
    if names:
        if not isinstance(names, list):
            raise BadPayload("'objects' must be a list of names")
        targets = []
        for name in names:
            obj = bpy.data.objects.get(name)
            if obj is None:
                raise CommandError(f"Object not found: {name}", code="not_found")
            targets.append(obj)
    else:
        targets = [obj for obj in view_layer.objects if obj.hide_get()]
    revealed = []
    for obj in targets:
        _hide_set(obj, False)
        if select:
            try:
                obj.select_set(True)
            except RuntimeError:
                pass
        revealed.append(obj.name)
    undo_push("Remote reveal")
    if select and revealed and view_layer.objects.active is None:
        view_layer.objects.active = targets[-1]
    return _visibility_result(revealed=revealed)
