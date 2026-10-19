"""scene.scale — escala de trabajo de la escena (unidades, clipping y pasos).

Un preset no reescala nada: cambia cómo se mide, hasta dónde se ve y con qué paso se
mueven los controles. La razón de que exista está en `protocol.SCENE_SCALES`; en corto,
el clipping heredado del PC arruinaba la precisión de profundidad del vídeo y con él la
malla se veía rota en cuanto la pieza se salía del rango para el que estaba pensado.
"""

from __future__ import annotations

import bpy
import math
import uuid

from ..camera import camera
from ..errors import BadPayload, CommandError
from ..protocol import DEFAULT_SCENE_SCALE, SCENE_SCALES
from . import command

# El preset pertenece a la escena y se guarda dentro del .blend.
SCENE_SCALE_KEY = 'btr_scene_scale'
REFERENCE_BOARD_KEY = 'btr_reference_board_id'
_EPOCH = uuid.uuid4().hex


def _length_unit() -> str:
    """La unidad real de Blender; `ADAPTIVE` es la de la escena recién creada."""
    return str(bpy.context.scene.unit_settings.length_unit)


def _preset_for_scene() -> str:
    """Preset cuya unidad coincide con la que trae el archivo abierto."""
    saved = bpy.context.scene.get(SCENE_SCALE_KEY)
    if isinstance(saved, str) and saved in SCENE_SCALES:
        return saved
    length_unit = _length_unit()
    return next(
        (name for name, scale in SCENE_SCALES.items() if scale["length_unit"] == length_unit),
        DEFAULT_SCENE_SCALE,
    )


def reference_board_id() -> str:
    """Identidad estable del tablero local, guardada con la escena, sin guardar fotos."""
    scene = bpy.context.scene
    value = scene.get(REFERENCE_BOARD_KEY)
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError):
        value = str(uuid.uuid4())
        scene[REFERENCE_BOARD_KEY] = value
        return value


def current_scale() -> dict:
    """Preset activo, con lo que la tablet necesita para pintar sus controles."""
    current = _preset_for_scene()
    preset = SCENE_SCALES[current]
    return dict(
        preset,
        scene_id=f'{_EPOCH}:{bpy.context.scene.session_uid}',
        reference_board_id=reference_board_id(),
        length_unit=_length_unit(),
        scale_length=float(bpy.context.scene.unit_settings.scale_length),
        unit_system=str(bpy.context.scene.unit_settings.system),
        clip_start=camera.clip_start,
        clip_end=camera.clip_end,
    )


def apply_scale(name: str) -> dict:
    """Aplica el preset a unidades, cámara y rejilla. Nunca toca la geometría."""
    scale = SCENE_SCALES.get(name)
    if scale is None:
        raise BadPayload(f"Unknown scene scale: {name}")
    bpy.context.scene[SCENE_SCALE_KEY] = name

    unit_settings = bpy.context.scene.unit_settings
    # METRIC es condición para que `length_unit` acepte milímetros o metros; con
    # NONE Blender solo entiende unidades sin nombre y rechaza el enum.
    unit_settings.system = "METRIC"
    unit_settings.length_unit = scale["length_unit"]
    # `scale_length` no se toca: multiplica el tamaño del mundo y cambiaría el
    # significado de la geometría existente, que es justo lo que un preset no debe hacer.

    conversion = max(unit_settings.scale_length, 1e-12)
    camera.set_clipping(scale["clip_start"] / conversion, scale["clip_end"] / conversion)
    _apply_grid(scale["grid_scale"])
    bpy.context.scene.tool_settings.proportional_size = (
        scale["proportional_radius"] / max(unit_settings.scale_length, 1e-12))
    from ..cad.runtime import runtime
    runtime.step = scale["snap_step"]
    return current_scale()


def _apply_grid(grid_scale: float) -> None:
    """Paso físico en metros. Blender aplica scale_length al grid métrico nativo."""
    from ..bpy_utils import find_view3d

    found = find_view3d()
    if found is None:
        return
    space = found[1].spaces.active
    conversion = max(bpy.context.scene.unit_settings.scale_length, 1e-12)
    # ED_view3d_grid_scale multiplica por 1/scale_length cuando hay unidades.
    # Dividir aquí otra vez convertiría 1 m en 1000 m en un archivo milimétrico.
    native_factor = space.overlay.grid_scale_unit / space.overlay.grid_scale
    space.overlay.grid_scale = float(grid_scale / conversion / native_factor)


def reset() -> None:
    """Adopta la unidad del archivo nuevo sin modificarla ni tocar su geometría."""
    scale = SCENE_SCALES[_preset_for_scene()]
    conversion = max(bpy.context.scene.unit_settings.scale_length, 1e-12)
    camera.set_clipping(scale["clip_start"] / conversion, scale["clip_end"] / conversion)
    _apply_grid(scale["grid_scale"])
    from ..cad.runtime import runtime
    runtime.step = scale["snap_step"]


def detail_step(obj) -> float:
    """Initial Edit-tool step: 1% of the smallest useful selected dimension.

    Rounded down to 1/2/5, measured in meters, then returned in Blender units.
    This does not change the existing Move, Scale or proportional controls.
    """
    conversion = max(bpy.context.scene.unit_settings.scale_length, 1e-12)
    if obj.mode == 'EDIT':
        import bmesh
        bm = bmesh.from_edit_mesh(obj.data)
        vertices = [v for v in bm.verts if v.select and not v.hide]
        if len(vertices) < 2:
            vertices = [v for v in bm.verts if not v.hide]
        points = [v.co for v in vertices]
    else:
        points = list(obj.bound_box)
    spans = [(max(p[a] for p in points) - min(p[a] for p in points)) *
             obj.matrix_world.to_3x3().col[a].length * conversion
             for a in range(3)] if points else []
    useful = [s for s in spans if s > max(spans, default=0) * 1e-6 and s > 0]
    preset_step = SCENE_SCALES[_preset_for_scene()]['snap_step']
    target = min(min(useful) * .01, preset_step) if useful else preset_step
    target = max(target, 1e-15)
    magnitude = 10 ** math.floor(math.log10(target))
    step = max(v for v in (1, 2, 5, 10) if v <= target / magnitude + 1e-5) * magnitude
    return step / conversion


@command("scene.scale")
def get_scale(payload: dict) -> dict:
    """Preset activo y catálogo completo, para no hardcodearlo en la tablet."""
    return {"scale": current_scale(), "presets": [SCENE_SCALES[key] for key in SCENE_SCALES]}


@command("scene.scale_set")
def set_scale(payload: dict) -> dict:
    """La escala de trabajo se elige al crear la escena, nunca sobre una existente."""
    raise CommandError("La escala pertenece a esta escena. Crea una escena nueva para elegir otra.",
                       code="scene_scale_locked")
