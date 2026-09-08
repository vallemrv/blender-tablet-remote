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


def roll_delta(angle: float) -> None:
    """Gira la cámara sobre su eje de visión (roll), en radianes.

    ``angle`` es el giro de la rueda de dos dedos en pantalla (positivo = horario). Se
    invierte para que la escena acompañe al dedo: rueda horaria -> cámara antihoraria
    -> escena horaria.
    """
    _region_view()
    camera.roll(-angle)


def _view_state() -> dict:
    _region_view()
    return camera.as_dict()


@command("view.orbit")
def orbit(payload: dict) -> dict:
    orbit_delta(get_float(payload, "dx", 0.0), get_float(payload, "dy", 0.0))
    return _view_state()


@command("view.roll")
def roll(payload: dict) -> dict:
    roll_delta(get_float(payload, "angle", 0.0))
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
    """Centro y esquinas que engloban a los objetos, en coordenadas de mundo."""
    corners = []
    for obj in objects:
        if obj.bound_box and obj.type != "EMPTY":
            corners.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
        else:
            corners.append(obj.matrix_world.translation.copy())
    if not corners:
        return Vector((0.0, 0.0, 0.0)), [Vector((0.0, 0.0, 0.0))]

    lo = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
    hi = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
    center = (lo + hi) * 0.5
    return center, corners


@command("view.frame_selected")
def frame_selected(payload: dict) -> dict:
    """Encuadra la selección; si no hay nada seleccionado, encuadra la escena.

    Ojo: el cubo por defecto de Blender es el objeto *activo* pero NO está
    seleccionado. Sin este respaldo, un doble toque nada más abrir no haría nada y
    parecería que la app se ha colgado.
    """
    rv3d = _region_view()
    view_layer = bpy.context.view_layer
    selected = [o for o in view_layer.objects if o.select_get()]
    targets = selected or [o for o in view_layer.objects if o.visible_get()]
    if not targets:
        raise CommandError("Nothing to frame", code="empty_scene")

    center, corners = _bounds(targets)
    camera.look_at(center, corners, rv3d)
    return dict(camera.as_dict(), framed="selected" if selected else "all")


@command("view.frame_all")
def frame_all(payload: dict) -> dict:
    rv3d = _region_view()
    targets = [o for o in bpy.context.view_layer.objects if o.visible_get()]
    if not targets:
        raise CommandError("Nothing to frame", code="empty_scene")
    center, corners = _bounds(targets)
    camera.look_at(center, corners, rv3d)
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
    """Cambia realmente la proyección usada por captura y picking."""
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


# ------------------------------------------------------------------- shading

VALID_SHADING = {"WIREFRAME", "SOLID"}


def _shading_space():
    """(area, space) del primer VIEW_3D, o None. El shading vive en el espacio."""
    from ..bpy_utils import find_view3d

    found = find_view3d()
    if found is None:
        return None
    _window, area, _region, _rv3d = found
    return area, area.spaces.active


def shading_state() -> str:
    """Shading actual del viewport capturado, normalizado a WIREFRAME/SOLID.

    MATERIAL y RENDERED se reportan como SOLID: la tablet solo alterna entre esos
    dos, y no hay botón que se pueda pintar "a medias".
    """
    found = _shading_space()
    if found is None:
        return "SOLID"
    return "WIREFRAME" if found[1].shading.type == "WIREFRAME" else "SOLID"


def is_xray_wireframe() -> bool:
    """El picking puede ciclar hacia detrás: wireframe con xray activado."""
    found = _shading_space()
    if found is None:
        return False
    shading = found[1].shading
    return shading.type == "WIREFRAME" and bool(shading.show_xray_wireframe)


@command("view.shading")
def shading(payload: dict) -> dict:
    """Wireframe/sólido del viewport capturado. Wireframe y xray van siempre juntos.

    El offscreen dibuja con el shading del espacio que se le pasa, así que cambiar
    `space.shading` cambia el vídeo sin tocar la cámara. El xray del wireframe
    hace que se vea (y se pueda picar) a través: ver `selection.pick`.

    El paquete es inseparable también en TOGGLE: un WIREFRAME sin xray (dejado por
    Shift+Z en el PC o por un .blend guardado) no cuenta como "wireframe", así que
    el toggle lo re-arma completo en vez de bajar a SOLID.
    """
    found = _shading_space()
    mode = str(payload.get("mode", "TOGGLE")).upper()
    if mode == "TOGGLE":
        if found is None:
            raise CommandError("No 3D viewport available", code="no_viewport")
        mode = "SOLID" if is_xray_wireframe() else "WIREFRAME"
    if mode not in VALID_SHADING:
        raise BadPayload("'mode' must be WIREFRAME, SOLID or TOGGLE")
    if found is None:
        raise CommandError("No 3D viewport available", code="no_viewport")
    _area, space = found

    space.shading.type = mode
    if mode == "WIREFRAME":
        # Con 1.0 el xray es opaco y vuelve a ocultar lo que hay dentro. Un valor
        # moderado conserva legibles frente e interior, como el xray de Blender.
        space.shading.show_xray_wireframe = True
        space.shading.xray_alpha_wireframe = 0.65
    return {"shading": shading_state()}


def overlays_state() -> bool:
    """¿Se están dibujando los overlays (rejilla, ejes, cage de Edit)?"""
    found = _shading_space()
    if found is None:
        return True
    return bool(found[1].overlay.show_overlays)


@command("view.overlays")
def overlays(payload: dict) -> dict:
    """Enciende o apaga los overlays del viewport capturado.

    `draw_view3d` sí pinta el motor de overlays (la rejilla del suelo, los ejes y el
    cage de Edit Mode), pero no la interfaz nativa de la región. Así que apagar
    `space.overlay.show_overlays` deja el vídeo limpio, solo la
    escena. Es lo que pide el ojo de la tablet al ocultar la interfaz: sin controles
    encima y sin rejilla debajo.

    Sin `show` alterna. Cambia el espacio VIEW_3D real, igual que `view.shading`.
    """
    show = payload.get("show")
    if show is not None and not isinstance(show, bool):
        raise BadPayload("'show' must be a boolean")
    found = _shading_space()
    if found is None:
        raise CommandError("No 3D viewport available", code="no_viewport")
    _area, space = found
    space.overlay.show_overlays = (not space.overlay.show_overlays) if show is None else show
    return {"overlays": bool(space.overlay.show_overlays)}


# ---------------------------------------------------------------- aislamiento

# Objetos ocultados por `view.local`. Solo estos se restauran al salir: lo que ya
# estaba oculto antes de aislar no se toca, y el aislamiento nunca lo revela.
_local_hidden: list[str] = []


@command("view.local", mutating=True)
def local(payload: dict) -> dict:
    """Aísla la selección ocultando el resto (el `/` de Blender).

    La cámara de la tablet dibuja el view_layer entero, así que el local view
    nativo de Blender (que opera sobre el rv3d del PC) no nos sirve: el equivalente
    fiable es ocultar los no seleccionados y recordar exactamente qué se ocultó.
    """
    global _local_hidden
    from .. import state

    enabled = payload.get("enabled")
    if enabled is None:
        enabled = not _local_hidden
    enabled = bool(enabled)

    if enabled and not _local_hidden:
        view_layer = bpy.context.view_layer
        selected = {o.name for o in view_layer.objects if o.select_get()}
        newly = [o for o in view_layer.objects if o.name not in selected and not o.hide_get()]
        for obj in newly:
            obj.hide_set(True)
        _local_hidden = [o.name for o in newly]
    elif not enabled and _local_hidden:
        for name in _local_hidden:
            obj = bpy.data.objects.get(name)
            if obj is not None:
                try:
                    if obj.hide_get():
                        obj.hide_set(False)
                except RuntimeError:
                    pass  # objeto en otra escena/archivo: no se puede restaurar
        _local_hidden = []

    return dict(state.snapshot(include_view=False), local=bool(_local_hidden),
                hidden=list(_local_hidden))


def reset_local_view() -> None:
    """Tras cargar otro .blend los nombres guardados apuntan a otra cosa."""
    global _local_hidden
    _local_hidden = []


def forget_local_hidden(names) -> None:
    """`object.hide` explícito: ese objeto ya no es cosa del aislamiento.

    Ocultar algo a mano mientras se aísla es una decisión del usuario que debe
    sobrevivir a la salida del local view, igual que en Blender.
    """
    global _local_hidden
    if _local_hidden:
        hidden_set = {str(name) for name in names}
        _local_hidden = [name for name in _local_hidden if name not in hidden_set]


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
