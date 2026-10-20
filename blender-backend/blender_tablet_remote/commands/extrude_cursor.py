"""Extrusión por toque en el plano de la cámara independiente de la tablet."""

import math

import bmesh
import bpy
from mathutils import Quaternion, Vector

from ..bpy_utils import find_view3d, get_float
from ..camera import camera
from ..errors import BadPayload, CommandError
from . import mesh


# Radio de pantalla (fracción del alto del vídeo) para unir el toque a un vértice existente.
CONNECT_RADIUS = .03


def _vertex_under(bm, obj, u, v, rv3d, projection):
    """Vértice visible más cercano al toque dentro de CONNECT_RADIUS, corrigiendo el aspecto."""
    aspect = abs(projection[1][1] / projection[0][0]) if projection[0][0] else 1.0
    best, best_distance = None, CONNECT_RADIUS
    for vert in bm.verts:
        if vert.hide:
            continue
        point = camera.project(obj.matrix_world @ vert.co, rv3d)
        if point is None:
            continue
        distance = math.hypot((point[0] - u) * aspect, point[1] - v)
        if distance < best_distance:
            best, best_distance = vert, distance
    return best


def _connect(bm, obj, tip, target):
    """Une el extremo actual con un vértice existente y continúa desde él."""
    if tip is not None and tip is not target and bm.edges.get((tip, target)) is None:
        bm.edges.new((tip, target))
    for seq in (bm.verts, bm.edges, bm.faces):
        for element in seq:
            element.select = False
    target.select_set(True)
    bm.select_history.clear()
    bm.select_history.add(target)
    bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=True)
    return {"changed": tip is not None and tip is not target, "connected": True,
            "position": list(obj.matrix_world @ target.co)}


def connect_tap(obj, payload):
    """J continuo: marca vértices y, al tener dos, los conecta como J y deselecciona."""
    u, v = get_float(payload, "u", -1), get_float(payload, "v", -1)
    if not all(math.isfinite(n) and 0 <= n <= 1 for n in (u, v)):
        raise BadPayload("'u' and 'v' must be within the viewport")
    found = find_view3d()
    if found is None:
        raise CommandError("No 3D viewport available", code="no_viewport")
    rv3d = found[3]
    camera.sync_from_region(rv3d)
    bm = bmesh.from_edit_mesh(obj.data)
    target = _vertex_under(bm, obj, u, v, rv3d, camera.projection_matrix(rv3d))
    picked = [vert for vert in bm.verts if vert.select and not vert.hide]
    if target is None:
        # Un toque fallido no pierde el primer vértice.
        return {"changed": False, "picked": len(picked)}
    if target in picked:
        picked.remove(target)
    else:
        picked.append(target)
    for seq in (bm.verts, bm.edges, bm.faces):
        for element in seq:
            element.select = False
    bm.select_history.clear()
    for vert in picked:
        vert.select_set(True)
        bm.select_history.add(vert)
    bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
    if len(picked) < 2:
        return {"changed": False, "picked": len(picked)}
    try:
        result = bpy.ops.mesh.vert_connect_path('EXEC_DEFAULT', False)
    except RuntimeError:
        result = set()
    bm = bmesh.from_edit_mesh(obj.data)
    for seq in (bm.verts, bm.edges, bm.faces):
        for element in seq:
            element.select = False
    bm.select_history.clear()
    bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=True)
    if "FINISHED" not in result:
        raise CommandError("No se pueden conectar estos vértices", code="topology_incompatible")
    return {"changed": True, "picked": 0}


def apply(obj, payload, rotate_source=True, connect=False):
    u, v = get_float(payload, "u", -1), get_float(payload, "v", -1)
    if not all(math.isfinite(n) and 0 <= n <= 1 for n in (u, v)):
        raise BadPayload("'u' and 'v' must be within the viewport")
    found = find_view3d()
    if found is None:
        raise CommandError("No 3D viewport available", code="no_viewport")
    rv3d = found[3]
    camera.sync_from_region(rv3d)
    bm = bmesh.from_edit_mesh(obj.data)
    selected = [vert for vert in bm.verts if vert.select and not vert.hide]
    if connect:
        # Dibujar: tocar un vértice existente lo une con el extremo (cierra formas)
        # o, sin línea en curso, empieza a dibujar desde él.
        target = _vertex_under(bm, obj, u, v, rv3d, camera.projection_matrix(rv3d))
        if target is not None:
            return _connect(bm, obj, selected[-1] if len(selected) == 1 else None, target)
        if len(selected) > 1:
            selected = [selected[-1]]
            for vert in bm.verts:
                vert.select = vert is selected[0]
            bm.select_flush_mode()
    world = obj.matrix_world
    try:
        inverse = world.inverted()
    except ValueError as exc:
        raise CommandError("La escala del objeto no permite extruir", code="degenerate_reference") from exc
    center = (sum((world @ vert.co for vert in selected), Vector()) / len(selected)
              if selected else bpy.context.scene.cursor.location.copy())
    view = camera.view_matrix()
    projection = camera.projection_matrix(rv3d)
    view_center = view @ center
    clip = projection @ view_center.to_4d()
    if clip.w <= 1e-9:
        raise CommandError("La selección queda detrás de la vista", code="degenerate_reference")
    clip.x, clip.y = (2 * u - 1) * clip.w, (1 - 2 * v) * clip.w
    # Resolver x/y a z fija evita perder precisión al invertir near/far.
    px = clip.x - projection[0][2] * view_center.z - projection[0][3]
    py = clip.y - projection[1][2] * view_center.z - projection[1][3]
    determinant = projection[0][0] * projection[1][1] - projection[0][1] * projection[1][0]
    target = view.inverted() @ Vector(((px * projection[1][1] - py * projection[0][1]) / determinant,
                                      (py * projection[0][0] - px * projection[1][0]) / determinant,
                                      view_center.z))
    view_normal = camera.rotation @ Vector((0, 0, 1))
    local_center = inverse @ center
    delta = inverse.to_3x3() @ (target - center)
    if selected and delta.length < 1e-9:
        return {"changed": False}

    rotation = Quaternion()
    if selected:
        # Normal de las aristas en pantalla orientada hacia el toque, como Ctrl+RMB.
        aspect = abs(projection[1][1] / projection[0][0])
        normal = Vector()
        pointer = Vector((u * aspect, -v, 0))
        for edge in bm.edges:
            if not edge.select or edge.hide:
                continue
            points = [camera.project(world @ vert.co, rv3d) for vert in edge.verts]
            if any(point is None for point in points):
                continue
            a, b = [Vector((point[0] * aspect, -point[1], 0)) for point in points]
            segment = b - a
            perpendicular = Vector((segment.y, -segment.x, 0))
            normal += perpendicular if perpendicular.dot(pointer - a) >= 0 else -perpendicular
        local_view = inverse.to_3x3() @ view_normal
        normal = inverse.to_3x3() @ (camera.rotation @ normal)
        normal = local_view.cross(normal.cross(local_view))
        if normal.length > 1e-9:
            rotation = normal.normalized().rotation_difference(delta.normalized())
            if rotate_source:
                rotation = Quaternion().slerp(rotation, .5)

    # Cada toque es atómico y confirmado; un fallo restaura solo ese tramo.
    backup = bpy.data.meshes.new(".remote_cursor_backup")
    bm.to_mesh(backup)
    try:
        if selected:
            if rotate_source:
                bmesh.ops.rotate(bm, verts=selected, cent=local_center, matrix=rotation.to_matrix())
            mesh.extrude({"offset": 0, "variant": "REGION", "_no_undo": True})
            tip = [vert for vert in bm.verts if vert.select and not vert.hide]
            bmesh.ops.rotate(bm, verts=tip, cent=local_center, matrix=rotation.to_matrix())
            bmesh.ops.translate(bm, verts=tip, vec=delta)
        else:
            bm.verts.new(inverse @ target).select_set(True)
        bm.normal_update()
        bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=True)
    except Exception:
        bm.clear()
        bm.from_mesh(backup)
        bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=True)
        raise
    finally:
        bpy.data.meshes.remove(backup)
    return {"changed": True, "position": list(target)}
