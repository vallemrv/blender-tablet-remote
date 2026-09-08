"""scene.scale — escala de trabajo de la escena (unidades, clipping y pasos).

Un preset no reescala nada: cambia cómo se mide, hasta dónde se ve y con qué paso se
mueven los controles. La razón de que exista está en `protocol.SCENE_SCALES`; en corto,
el clipping heredado del PC arruinaba la precisión de profundidad del vídeo y con él la
malla se veía rota en cuanto la pieza se salía del rango para el que estaba pensado.
"""

from __future__ import annotations

import bpy

from ..camera import camera
from ..errors import BadPayload, CommandError
from ..protocol import DEFAULT_SCENE_SCALE, SCENE_SCALES
from . import command

# `None` significa que todavía no hubo una elección explícita en esta sesión. En ese
# caso la unidad real del .blend decide qué preset se anuncia; así una escena en mm no
# aparece falsamente como "Mediana" solo por ser el valor por defecto del add-on.
_current: str | None = None


def _length_unit() -> str:
    """La unidad real de Blender; `ADAPTIVE` es la de la escena recién creada."""
    return str(bpy.context.scene.unit_settings.length_unit)


def _preset_for_scene() -> str:
    """Preset cuya unidad coincide con la que trae el archivo abierto."""
    length_unit = _length_unit()
    return next(
        (name for name, scale in SCENE_SCALES.items() if scale["length_unit"] == length_unit),
        DEFAULT_SCENE_SCALE,
    )


def current_scale() -> dict:
    """Preset activo, con lo que la tablet necesita para pintar sus controles."""
    current = _current or _preset_for_scene()
    preset = SCENE_SCALES[current]
    return dict(
        preset,
        length_unit=_length_unit(),
        scale_length=float(bpy.context.scene.unit_settings.scale_length),
        unit_system=str(bpy.context.scene.unit_settings.system),
        clip_start=camera.clip_start,
        clip_end=camera.clip_end,
    )


def apply_scale(name: str) -> dict:
    """Aplica el preset a unidades, cámara y rejilla. Nunca toca la geometría."""
    global _current
    scale = SCENE_SCALES.get(name)
    if scale is None:
        raise BadPayload(f"Unknown scene scale: {name}")
    _current = name

    unit_settings = bpy.context.scene.unit_settings
    # METRIC es condición para que `length_unit` acepte milímetros o metros; con
    # NONE Blender solo entiende unidades sin nombre y rechaza el enum.
    unit_settings.system = "METRIC"
    unit_settings.length_unit = scale["length_unit"]
    # `scale_length` no se toca: multiplica el tamaño del mundo y cambiaría el
    # significado de la geometría existente, que es justo lo que un preset no debe hacer.

    camera.set_clipping(scale["clip_start"], scale["clip_end"])
    _apply_grid(scale["grid_scale"])
    bpy.context.scene.tool_settings.proportional_size = (
        scale["proportional_radius"] / max(unit_settings.scale_length, 1e-12))
    return current_scale()


def _apply_grid(grid_scale: float) -> None:
    """Rejilla del viewport capturado, para que el suelo acompañe a la escala."""
    from ..bpy_utils import find_view3d

    found = find_view3d()
    if found is None:
        return
    space = found[1]
    try:
        space.overlay.grid_scale = float(grid_scale)
    except AttributeError:
        pass


def reset() -> None:
    """Adopta la unidad del archivo nuevo sin modificarla ni tocar su geometría."""
    global _current
    _current = _preset_for_scene()
    scale = SCENE_SCALES[_current]
    camera.set_clipping(scale["clip_start"], scale["clip_end"])


@command("scene.scale")
def get_scale(payload: dict) -> dict:
    """Preset activo y catálogo completo, para no hardcodearlo en la tablet."""
    return {"scale": current_scale(), "presets": [SCENE_SCALES[key] for key in SCENE_SCALES]}


@command("scene.scale_set", mutating=True)
def set_scale(payload: dict) -> dict:
    """Cambia de preset, o solo la unidad con la que se escriben las medidas."""
    preset = payload.get("preset")
    length_unit = payload.get("length_unit")
    if preset is None and length_unit is None:
        raise BadPayload("'preset' or 'length_unit' is required")

    result = apply_scale(str(preset).upper()) if preset is not None else current_scale()
    if length_unit is not None:
        unit = str(length_unit).upper()
        if unit not in {"MILLIMETERS", "CENTIMETERS", "METERS"}:
            raise BadPayload("'length_unit' must be MILLIMETERS, CENTIMETERS or METERS")
        try:
            bpy.context.scene.unit_settings.system = "METRIC"
            bpy.context.scene.unit_settings.length_unit = unit
        except TypeError as exc:
            raise CommandError(f"Blender rejected the unit: {exc}", code="invalid_unit") from exc
        result = current_scale()
    return result
