"""reference.* — imágenes de referencia nativas de Blender enviadas desde la tablet.

El tablero de referencias de Android sigue siendo local; esto copia una imagen a la
escena como Añadir → Imagen → Referencia: un Empty de imagen orientado hacia la
cámara de la tablet, en el punto que mira, con la imagen empaquetada en el `.blend`.
"""

from __future__ import annotations

import base64
import binascii
import os
import tempfile

import bpy
from mathutils import Vector

from .. import state
from ..bpy_utils import find_view3d, undo_push
from ..camera import camera
from ..errors import BadPayload, CommandError
from . import command

FORMATS = {"png": ".png", "jpg": ".jpg"}
# Base64 de 8 MB llega a ~6 MB de imagen: el tope del WebSocket de control.
MAX_BYTES = 6 * 1024 * 1024
# La imagen nace ocupando esta fracción de la altura visible.
VIEW_FRACTION = 0.8


def pick_image(origin, direction, rv3d, area, mesh_location=None):
    """Sondea el rectángulo de los Empty IMAGE que el vídeo de la tablet dibuja.

    scene.ray_cast no incluye estos objetos. Tamaño/aspecto/offset y visibilidad
    siguen overlay_empty.hh y BKE_object_empty_image_data_is_visible_in_view3d.
    No se crean mallas auxiliares ni se cambia la vista del PC.
    """
    space = area.spaces.active if area is not None else None
    if space is not None and (not space.overlay.show_overlays or not space.overlay.show_extras
                              or not space.show_object_viewport_empty):
        return None
    perspective = camera.perspective == 'PERSP'
    view_back = camera.rotation @ Vector((0, 0, 1))
    eye = camera.location + view_back * camera.distance
    projection = camera.perspective_matrix(rv3d)
    # FRONT / profundidad normal / BACK, y distancia dentro de cada grupo.
    best = (0, (mesh_location - origin).length) if mesh_location is not None else (2, float('inf'))
    result = None
    for obj in bpy.context.view_layer.objects:
        if (obj.type != 'EMPTY' or obj.empty_display_type != 'IMAGE' or obj.data is None
                or obj.hide_select or not obj.visible_get()):
            continue
        if not (obj.show_empty_image_perspective if perspective else obj.show_empty_image_orthographic):
            continue
        if obj.use_empty_image_alpha and obj.color[3] <= 0:
            continue
        matrix = obj.matrix_world
        normal = matrix.to_3x3().col[2]
        if normal.length_squared == 0:
            continue
        facing = normal.dot(eye - matrix.translation if perspective else view_back)
        epsilon = 0.0 if perspective else 1e-5
        if ((obj.empty_image_side == 'FRONT' and facing < epsilon)
                or (obj.empty_image_side == 'BACK' and facing > -epsilon)):
            continue
        if obj.show_empty_image_only_axis_aligned:
            if normal.normalized().cross(view_back).length_squared > 1e-5:
                continue
        try:
            inverse = matrix.inverted()
        except ValueError:
            continue
        local_origin = inverse @ origin
        local_direction = inverse.to_3x3() @ direction
        if abs(local_direction.z) <= local_direction.length * 1e-8:
            continue
        distance = -local_origin.z / local_direction.z
        if distance < 0:
            continue
        point = local_origin + local_direction * distance
        image = obj.data
        width, height = image.size
        if width <= 0 or height <= 0:
            continue
        aspect_x, aspect_y = image.display_aspect
        width *= aspect_x
        height *= aspect_y
        longest = max(width, height)
        width, height = width / longest * obj.empty_display_size, height / longest * obj.empty_display_size
        offset_x, offset_y = obj.empty_image_offset
        if not (offset_x * width <= point.x <= (offset_x + 1) * width
                and offset_y * height <= point.y <= (offset_y + 1) * height):
            continue
        location = matrix @ point
        clip = projection @ Vector((*location, 1))
        if clip.w <= 0 or not -clip.w <= clip.z <= clip.w:
            continue
        depth = -1 if obj.show_in_front or obj.empty_image_depth == 'FRONT' else (1 if obj.empty_image_depth == 'BACK' else 0)
        candidate = (depth, distance)
        if candidate < best:
            best, result = candidate, (obj, location)
    return result


def _decode(payload: dict) -> tuple[bytes, str]:
    fmt = str(payload.get("format", "")).lower()
    if fmt not in FORMATS:
        raise BadPayload("'format' must be png or jpg")
    try:
        data = base64.b64decode(str(payload.get("data", "")), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise BadPayload("'data' must be base64") from exc
    if not data:
        raise BadPayload("'data' is empty")
    if len(data) > MAX_BYTES:
        raise BadPayload("La imagen es demasiado grande")
    return data, FORMATS[fmt]


def _load_packed(name: str, data: bytes, suffix: str):
    """Blender carga desde disco: fichero temporal, empaquetado y fuera."""
    handle, path = tempfile.mkstemp(prefix="btr-reference-", suffix=suffix)
    try:
        with os.fdopen(handle, "wb") as output:
            output.write(data)
        try:
            image = bpy.data.images.load(path, check_existing=False)
        except RuntimeError as exc:
            raise CommandError("Blender no puede leer la imagen", code="invalid_image") from exc
        image.name = name
        image.pack()
        # Empaquetada, la ruta temporal ya no significa nada y no debe guardarse.
        image.filepath = ""
        return image
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


@command("reference.add", mutating=True)
def add(payload: dict) -> dict:
    """Crea la referencia frente a la cámara de la tablet, con un único undo."""
    data, suffix = _decode(payload)
    name = str(payload.get("name") or "Referencia").strip()[:60] or "Referencia"
    opacity = float(payload.get("opacity", 1.0))
    if not 0.0 < opacity <= 1.0:
        raise BadPayload("'opacity' must be in (0, 1]")
    found = find_view3d()
    if found is None:
        raise CommandError("No 3D viewport available", code="no_viewport")
    rv3d = found[3]
    camera.sync_from_region(rv3d)

    image = _load_packed(name, data, suffix)
    empty = bpy.data.objects.new(name, None)
    empty.empty_display_type = "IMAGE"
    empty.data = image
    _span_x, span_y = camera.screen_span(camera.projection_matrix(rv3d))
    empty.empty_display_size = max(span_y * VIEW_FRACTION, 1e-6)
    empty.location = Vector(camera.location)
    empty.rotation_euler = camera.rotation.to_euler()
    # Igual que la Referencia de Blender: profundidad normal, visible en
    # perspectiva y ortográfica, por delante y por detrás.
    empty.empty_image_depth = "DEFAULT"
    empty.show_empty_image_perspective = True
    empty.show_empty_image_orthographic = True
    empty.use_empty_image_alpha = opacity < 1.0
    empty.color[3] = opacity

    collection = bpy.context.view_layer.active_layer_collection.collection
    collection.objects.link(empty)
    active = bpy.context.view_layer.objects.active
    # En Object queda seleccionada para colocarla con el manipulador; en otro modo
    # no se toca el objeto que se está editando.
    if active is None or active.mode == "OBJECT":
        for obj in bpy.context.view_layer.objects:
            obj.select_set(False)
        empty.select_set(True)
        bpy.context.view_layer.objects.active = empty
    undo_push("Remote reference image")
    return dict(state.snapshot(include_view=False), reference=empty.name, image=image.name)
