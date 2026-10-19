"""Resolución de un anillo de malla regular, sin sobrescribir ediciones libres."""
import math

from mathutils import Vector


def describe(obj):
    if obj.type != 'MESH' or obj.mode != 'OBJECT':
        return None
    mesh = obj.data
    count = len(mesh.vertices)
    if not 3 <= count <= 4096 or len(mesh.edges) != count or mesh.polygons:
        return None
    if mesh.shape_keys or obj.vertex_groups:
        return None
    if any(len(attr.data) and not attr.is_internal and attr.name != 'position' for attr in mesh.attributes):
        return None
    if any(v.hide for v in mesh.vertices) or any(e.hide for e in mesh.edges):
        return None
    neighbors = [[] for _ in range(count)]
    for edge in mesh.edges:
        a, b = edge.vertices
        neighbors[a].append(b); neighbors[b].append(a)
    if any(len(n) != 2 for n in neighbors):
        return None
    order, seen, previous, index = [], set(), -1, 0
    while index not in seen:
        order.append(index); seen.add(index)
        following = next(n for n in neighbors[index] if n != previous)
        previous, index = index, following
    if index != 0 or len(order) != count:
        return None
    points = [mesh.vertices[i].co.copy() for i in order]
    center = sum(points, Vector()) / count
    radial = points[0] - center
    radius = radial.length
    if radius <= 1e-12:
        return None
    x = radial.normalized()
    normal = x.cross(points[1] - center)
    if normal.length <= radius * 1e-8:
        return None
    y = normal.normalized().cross(x)
    tolerance = max(radius * 2e-5, 1e-10)
    for i, point in enumerate(points):
        angle = 2 * math.pi * i / count
        if (point - (center + radius * (x * math.cos(angle) + y * math.sin(angle)))).length > tolerance:
            return None
    return dict(count=count, center=center, radius=radius, x=x, y=y)


def resized_mesh(obj, circle, count):
    """Una copia conserva materiales; otras instancias de la malla no se alteran."""
    points = [circle['center'] + circle['radius'] * (
        circle['x'] * math.cos(2 * math.pi * i / count) + circle['y'] * math.sin(2 * math.pi * i / count))
        for i in range(count)]
    mesh = obj.data.copy()
    try:
        mesh.clear_geometry()
        mesh.from_pydata(points, [(i, (i + 1) % count) for i in range(count)], [])
        mesh.update()
    except Exception:
        import bpy
        bpy.data.meshes.remove(mesh)
        raise
    return mesh
