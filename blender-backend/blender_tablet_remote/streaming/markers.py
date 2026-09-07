"""Marcadores modales dentro del frame: misma cámara y latencia que la geometría."""

import math

import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector

from ..camera import camera


def transform_markers(status):
    """Centro fijo, fuente transformada, destino y candidato temporal independientes."""
    if not status.get("active"):
        return []
    markers = []
    if status["mode"] in {"ROTATE", "SCALE"}:
        markers.append(("CENTER", status["center"]))
    if status.get("source"):
        markers.append(("SOURCE", status["source"]))
    if status.get("snap") and status.get("target"):
        markers.append(("TARGET", status["target"]))
    candidate = status.get("reference_candidate")
    if candidate and not status.get("reference_locked"):
        markers.append((candidate["snap_type"], candidate["position"]))
    return markers


def marker_segments(kind, x, y, radius):
    """Símbolos huecos de distinto tamaño para que los coincidentes sigan legibles."""
    if kind == "CENTER":
        r = radius * 0.65
        return [(x - r, y), (x + r, y), (x, y - r), (x, y + r)]
    if kind == "SOURCE":
        r = radius
        points = [(x, y + r), (x + r, y), (x, y - r), (x - r, y)]
    elif kind in {"EDGE_CENTER", "FACE_CENTER"}:
        r = radius * (0.7 if kind == "EDGE_CENTER" else 1.0)
        points = [(x-r, y-r), (x+r, y-r), (x+r, y+r), (x-r, y+r)]
    else:
        r = radius * (1.4 if kind == "TARGET" else 0.7)
        points = [(x + r * math.cos(i * math.tau / 24),
                   y + r * math.sin(i * math.tau / 24)) for i in range(24)]
    return [p for i, point in enumerate(points) for p in (point, points[(i + 1) % len(points)])]


def draw_transform_markers(rv3d, width, height):
    from ..commands.modal import session

    markers = transform_markers(session.status())
    from ..commands.tools import tool_session
    paths = []
    if tool_session.alignment is not None and tool_session.status().get("active"):
        for kind, vertices in tool_session.alignment.outlines():
            projected = [camera.project(point, rv3d) for point in vertices]
            if all(point is not None for point in projected):
                points = [(p[0]*width, (1-p[1])*height) for p in projected]
                paths.append((kind, [p for i, point in enumerate(points)
                                    for p in (point, points[(i+1) % len(points)])]))
            markers.append((kind, sum(vertices, Vector()) / len(vertices)))
    for kind, position in markers:
        screen = camera.project(position, rv3d)
        if screen is not None and 0 <= screen[0] <= 1 and 0 <= screen[1] <= 1:
            paths.append((kind, marker_segments(kind, screen[0]*width, (1-screen[1])*height,
                                                max(5.0, width/128.0))))
    if not paths:
        return
    shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
    old_blend = gpu.state.blend_get()
    old_depth = gpu.state.depth_test_get()
    old_mask = gpu.state.depth_mask_get()
    old_viewport = gpu.state.viewport_get()
    try:
        gpu.state.viewport_set(0, 0, width, height)
        gpu.state.blend_set("ALPHA")
        gpu.state.depth_test_set("NONE")
        gpu.state.depth_mask_set(False)
        with gpu.matrix.push_pop(), gpu.matrix.push_pop_projection():
            gpu.matrix.load_identity()
            gpu.matrix.load_projection_matrix(Matrix.Identity(4))
            shader.bind()
            shader.uniform_float("viewportSize", (width, height))
            for kind, points in paths:
                coords = [(x * 2 / width - 1, y * 2 / height - 1, 0) for x, y in points]
                batch = batch_for_shader(shader, "LINES", {"pos": coords})
                # Contorno oscuro: se ve tanto sobre superficies claras como oscuras.
                shader.uniform_float("lineWidth", 4.0)
                shader.uniform_float("color", (0.03, 0.04, 0.05, 0.9))
                batch.draw(shader)
                color = {"CENTER": (1.0, 0.36, 0.41, 1.0),
                         "SOURCE": (1.0, 0.72, 0.30, 1.0),
                         "TARGET": (0.35, 0.8, 1.0, 1.0)}.get(kind, (0.4, 0.89, 0.64, 1.0))
                shader.uniform_float("lineWidth", 2.0)
                shader.uniform_float("color", color)
                batch.draw(shader)
    finally:
        gpu.state.blend_set(old_blend)
        gpu.state.depth_test_set(old_depth)
        gpu.state.depth_mask_set(old_mask)
        gpu.state.viewport_set(*old_viewport)
