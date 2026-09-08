"""Extrusión por toque en el plano de la cámara independiente de la tablet."""

import math

import bmesh
import bpy
from mathutils import Quaternion, Vector

from ..bpy_utils import find_view3d, get_float
from ..camera import camera
from ..errors import BadPayload, CommandError
from . import mesh


def apply(obj, payload, rotate_source=True):
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
    # Ctrl+RMB extruye la geometría efectiva, también si el usuario está en
    # Vértices pero ha seleccionado los extremos de una arista o una cara.
    faces_selected = any(f.select and not f.hide for f in bm.faces)
    edges_selected = any(e.select and not e.hide for e in bm.edges)
    selection_mode = (not faces_selected and not edges_selected, not faces_selected and edges_selected, faces_selected)
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
            mesh.extrude({"offset": 0, "variant": "REGION", "_no_undo": True, "_selection_mode": selection_mode})
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
