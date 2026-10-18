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
