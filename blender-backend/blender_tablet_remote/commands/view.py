"""view.* — navegación de la cámara de la tablet.

La tablet tiene su **propia** cámara (ver camera.py): no se toca el RegionView3D de
la ventana del PC. El motivo es de rendimiento y está medido: escribir en `rv3d`
desde el timer hunde el bucle de eventos de Blender a 1 Hz y no se recupera.

De la región solo se hereda la matriz de proyección, para que la imagen capturada y
el rayo de selección usen exactamente la misma.

Los deltas llegan normalizados (fracción de pantalla), así la tablet no necesita
saber la resolución del viewport remoto.
"""

from __future__ import annotations

import math

import bpy
from mathutils import Vector

from ..bpy_utils import get_float, require_rv3d
from ..camera import camera
from ..errors import BadPayload, CommandError
from . import command

ORBIT_SENSITIVITY = math.pi  # arrastrar toda la pantalla = 180 grados
# El paneo no tiene sensibilidad: se deduce de la proyección para que la escena siga
# exactamente al dedo. Ver RemoteCamera.screen_span().


def _region_view():
    """rv3d de la ventana. Solo se lee (proyección y sincronización inicial)."""
    rv3d = require_rv3d()
    camera.sync_from_region(rv3d)
    return rv3d


def orbit_delta(dx: float, dy: float) -> None:
    _region_view()
    camera.orbit(dx, dy, ORBIT_SENSITIVITY)


def pan_delta(dx: float, dy: float) -> None:
    rv3d = _region_view()
    camera.pan(dx, dy, camera.projection_matrix(rv3d))


def zoom_factor(factor: float) -> None:
    if factor <= 0:
        raise BadPayload("'factor' must be > 0")
    _region_view()
    camera.zoom(factor)


def _view_state() -> dict:
    _region_view()
    return camera.as_dict()


@command("view.orbit")
def orbit(payload: dict) -> dict:
    orbit_delta(get_float(payload, "dx", 0.0), get_float(payload, "dy", 0.0))
    return _view_state()


@command("view.pan")
def pan(payload: dict) -> dict:
    pan_delta(get_float(payload, "dx", 0.0), get_float(payload, "dy", 0.0))
    return _view_state()


@command("view.zoom")
def zoom(payload: dict) -> dict:
    """`factor` > 1 acerca. Alternativamente `delta` (fracción de pantalla)."""
    if "factor" in payload:
        zoom_factor(get_float(payload, "factor", 1.0))
    else:
        zoom_factor(math.exp(get_float(payload, "delta", 0.0)))
    return _view_state()


def _bounds(objects):
    """Centro y radio que engloban a los objetos, en coordenadas de mundo."""
    corners = []
    for obj in objects:
        if obj.bound_box and obj.type != "EMPTY":
            corners.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
        else:
            corners.append(obj.matrix_world.translation.copy())
    if not corners:
        return Vector((0.0, 0.0, 0.0)), 1.0

    lo = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
    hi = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
    center = (lo + hi) * 0.5
    radius = max((hi - lo).length * 0.5, 0.25)
    return center, radius


@command("view.frame_selected")
def frame_selected(payload: dict) -> dict:
    """Encuadra la selección; si no hay nada seleccionado, encuadra la escena.

    Ojo: el cubo por defecto de Blender es el objeto *activo* pero NO está
    seleccionado. Sin este respaldo, un doble toque nada más abrir no haría nada y
    parecería que la app se ha colgado.
    """
    _region_view()
    view_layer = bpy.context.view_layer
    selected = [o for o in view_layer.objects if o.select_get()]
    targets = selected or [o for o in view_layer.objects if o.visible_get()]
    if not targets:
        raise CommandError("Nothing to frame", code="empty_scene")

    center, radius = _bounds(targets)
    camera.look_at(center, radius)
    return dict(camera.as_dict(), framed="selected" if selected else "all")


@command("view.frame_all")
def frame_all(payload: dict) -> dict:
    _region_view()
    targets = [o for o in bpy.context.view_layer.objects if o.visible_get()]
    if not targets:
        raise CommandError("Nothing to frame", code="empty_scene")
    center, radius = _bounds(targets)
    camera.look_at(center, radius)
    return camera.as_dict()


@command("view.axis")
def axis(payload: dict) -> dict:
    """Vistas estándar: FRONT, BACK, LEFT, RIGHT, TOP, BOTTOM."""
    name = str(payload.get("axis", "FRONT")).upper()
    valid = {"FRONT", "BACK", "LEFT", "RIGHT", "TOP", "BOTTOM"}
    if name not in valid:
        raise BadPayload(f"'axis' must be one of {', '.join(sorted(valid))}")
    _region_view()
    camera.set_axis_view(name)
    return camera.as_dict()


@command("view.perspective")
def perspective(payload: dict) -> dict:
    """Cambia realmente la proyección usada por captura, picking y gizmos."""
    _region_view()
    mode = str(payload.get("mode", "TOGGLE")).upper()
    if mode == "TOGGLE":
        mode = "ORTHO" if camera.perspective == "PERSP" else "PERSP"
    if mode not in ("PERSP", "ORTHO"):
        raise BadPayload("'mode' must be PERSP, ORTHO or TOGGLE")
    changed = camera.perspective != mode
    camera.perspective = mode
    return dict(camera.as_dict(), changed=changed)


@command("view.get")
def get_view(payload: dict) -> dict:
    return _view_state()


@command("view.set")
def set_view(payload: dict) -> dict:
    """Restaura una vista completa (la que devuelve view.get)."""
    _region_view()
    rotation = payload.get("rotation")
    if rotation is not None and (not isinstance(rotation, (list, tuple)) or len(rotation) != 4):
        raise BadPayload("'rotation' must be a quaternion [w, x, y, z]")
    projection = payload.get("perspective")
    if projection is not None and str(projection).upper() not in ("PERSP", "ORTHO"):
        raise BadPayload("'perspective' must be PERSP or ORTHO")
    camera.apply(
        location=payload.get("location"),
        rotation=rotation,
        distance=get_float(payload, "distance", camera.distance) if "distance" in payload else None,
        perspective=str(projection).upper() if projection is not None else None,
    )
    return camera.as_dict()


# Longitud de los ejes del manipulador, en fracción de la distancia de la vista. Así
# el gizmo conserva más o menos el mismo tamaño en pantalla al acercarse o alejarse.
GIZMO_AXIS_SCALE = 0.22


@command("view.gizmo")
def gizmo(payload: dict) -> dict:
    """Dónde pintar el manipulador de la tablet, en coordenadas de pantalla.

    Los gizmos nativos de Blender no aparecen en la captura: `draw_view3d` dibuja la
    escena, no los overlays de la región (comprobado). Y aunque aparecieran serían
    demasiado finos para un dedo. Así que el servidor solo proyecta los puntos y es
    Android quien los dibuja al tamaño adecuado y decide qué eje se ha tocado (§18).

    u/v normalizados 0..1 con origen arriba-izquierda, la misma convención que
    `selection.pick`. Un eje puede venir a null si cae detrás de la cámara.
    """
    return gizmo_state()


def gizmo_state() -> dict:
    from ..bpy_utils import find_view3d

    found = find_view3d()
    if found is None:
        return {"visible": False, "reason": "no_viewport"}
    rv3d = found[3]
    camera.sync_from_region(rv3d)

    obj = bpy.context.view_layer.objects.active
    if obj is None or not obj.select_get():
        # Sin selección no hay nada que manipular: la tablet oculta el gizmo.
        return {"visible": False, "reason": "no_selection"}

    origin = obj.matrix_world.translation
    length = max(1e-4, camera.distance * GIZMO_AXIS_SCALE)

    axes = {}
    for name, direction in (("X", Vector((1, 0, 0))), ("Y", Vector((0, 1, 0))), ("Z", Vector((0, 0, 1)))):
        axes[name] = camera.project(origin + direction * length, rv3d)

    return {
        "visible": True,
        "object": obj.name,
        "origin": camera.project(origin, rv3d),
        "axes": axes,
        "mode": obj.mode,
    }
