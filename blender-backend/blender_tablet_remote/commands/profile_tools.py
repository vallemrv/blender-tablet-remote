"""Herramientas de perfiles sobre la sesión reversible de Edit."""

import math

import bmesh
import bpy
from mathutils import Vector

from ..bpy_utils import get_float, get_int
from ..errors import BadPayload, CommandError


REVOLVE_CONTROLS = [
    {"id": "angle", "label": "Ángulo °", "type": "float", "default": 360, "min": -360, "max": 360, "step": 15},
    {"id": "steps", "label": "Segmentos", "type": "int", "default": 32, "min": 1, "max": 256, "step": 1},
    {"id": "axis", "label": "Eje global", "type": "enum", "default": "Z", "values": ["X", "Y", "Z"]},
    *[{"id": f"center_{axis}", "label": f"Centro {axis.upper()}", "type": "float", "unit": "length", "default": 0}
      for axis in "xyz"],
    {"id": "merge", "label": "Cerrar vuelta", "type": "bool", "default": True},
]

SWEEP_CONTROLS = [
    {"id": "width", "label": "Ancho", "type": "float", "unit": "length", "default": .05, "min": 1e-6},
    {"id": "depth", "label": "Fondo", "type": "float", "unit": "length", "default": .1, "min": 1e-6},
    {"id": "caps", "label": "Tapar extremos", "type": "bool", "default": True},
]


def sweep(obj, params):
    width, depth = get_float(params, "width", .05), get_float(params, "depth", .1)
    if not all(math.isfinite(n) and n > 0 for n in (width, depth)):
        raise BadPayload("Ancho y fondo deben ser mayores que cero")
    bm = bmesh.from_edit_mesh(obj.data)
    edges = [e for e in bm.edges if e.select and not e.hide]
    if not edges:
        raise CommandError("Selecciona un contorno de aristas", code="empty_selection")
    if any(e.link_faces for e in edges):
        raise CommandError("Barrido necesita un contorno de aristas sin caras", code="incompatible_selection")
    neighbors = {}
    for edge in edges:
        a, b = edge.verts
        neighbors.setdefault(a, []).append(b)
        neighbors.setdefault(b, []).append(a)
    ends = [v for v, adjacent in neighbors.items() if len(adjacent) == 1]
    if any(len(adjacent) > 2 for adjacent in neighbors.values()) or len(ends) not in (0, 2):
        raise CommandError("El contorno debe ser una cadena o un loop sin ramificaciones", code="topology_incompatible")
    closed = not ends
    start = ends[0] if ends else next(iter(neighbors))
    ordered, previous, current = [], None, start
    while current not in ordered:
        ordered.append(current)
        next_vertices = [v for v in neighbors[current] if v != previous]
        if not next_vertices:
            break
        previous, current = current, next_vertices[0]
    if len(ordered) != len(neighbors):
        raise CommandError("Selecciona un único contorno conectado", code="topology_incompatible")
    points = [obj.matrix_world @ v.co for v in ordered]
    directions = [points[(i+1) % len(points)] - point for i, point in enumerate(points)
                  if closed or i+1 < len(points)]
    if any(direction.length < 1e-9 for direction in directions):
        raise CommandError("El contorno tiene aristas de longitud cero", code="degenerate_reference")
    directions = [direction.normalized() for direction in directions]
    normal = next((directions[0].cross(direction).normalized() for direction in directions[1:]
                   if directions[0].cross(direction).length > 1e-6), None)
    if normal is None:
        reference = min((Vector((1,0,0)), Vector((0,1,0)), Vector((0,0,1))), key=lambda a: abs(a.dot(directions[0])))
        normal = directions[0].cross(reference).normalized()
    tolerance = max((p-points[0]).length for p in points) * 1e-5 + 1e-7
    if any(abs((point-points[0]).dot(normal)) > tolerance for point in points):
        raise CommandError("El contorno del marco debe estar en un plano", code="topology_incompatible")
    try:
        inverse = obj.matrix_world.inverted()
    except ValueError as exc:
        raise CommandError("La escala del objeto no permite barrer", code="degenerate_reference") from exc
    rings = []
    # Cada esquina comparte su sección a inglete: no se superponen tubos separados.
    for i, point in enumerate(points):
        incoming = directions[(i-1) % len(directions)] if closed or i else directions[0]
        outgoing = directions[i % len(directions)] if closed or i < len(points)-1 else directions[-1]
        side_in, side_out = normal.cross(incoming), normal.cross(outgoing)
        miter = side_in + side_out
        if miter.length < 1e-6:
            raise CommandError("El contorno no puede volver sobre sí mismo", code="topology_incompatible")
        miter.normalize()
        denominator = miter.dot(side_out)
        if abs(denominator) < .01:
            raise CommandError("La esquina es demasiado cerrada para el perfil", code="topology_incompatible")
        lateral = miter * (width * .5 / denominator)
        vertical = normal * (depth * .5)
        rings.append([bm.verts.new(inverse @ (point + side*lateral + height*vertical))
                      for side, height in ((-1,-1),(1,-1),(1,1),(-1,1))])
    faces = []
    for i in range(len(rings) if closed else len(rings)-1):
        a, b = rings[i], rings[(i+1) % len(rings)]
        for j in range(4):
            faces.append(bm.faces.new((a[j],a[(j+1)%4],b[(j+1)%4],b[j])))
    if not closed and bool(params.get("caps", True)):
        faces.extend((bm.faces.new(list(reversed(rings[0]))), bm.faces.new(rings[-1])))
    bmesh.ops.delete(bm, geom=edges, context="EDGES")
    for seq in (bm.faces, bm.edges, bm.verts):
        for element in seq:
            element.select = False
    for face in faces:
        face.select_set(True)
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    bm.normal_update()
    bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=True)
    return {"width": width, "depth": depth, "closed": closed}


def revolve(obj, params):
    angle = get_float(params, "angle", 360)
    steps = get_int(params, "steps", 32)
    axis_name = str(params.get("axis", "Z"))
    center = Vector([get_float(params, f"center_{axis}", 0) for axis in "xyz"])
    if not math.isfinite(angle) or not -360 <= angle <= 360 or not 1 <= steps <= 256:
        raise BadPayload("Revolución necesita un ángulo entre −360° y 360° y entre 1 y 256 segmentos")
    if axis_name not in "XYZ" or len(axis_name) != 1 or not all(math.isfinite(n) for n in center):
        raise BadPayload("Eje o centro de revolución no válido")
    if abs(angle) == 360 and steps < 3:
        raise BadPayload("Una vuelta completa necesita al menos tres segmentos")
    bm = bmesh.from_edit_mesh(obj.data)
    verts = [v for v in bm.verts if v.select and not v.hide]
    if not verts:
        raise CommandError("Selecciona un perfil para revolucionar", code="empty_selection")
    selected = set(verts)
    geom = verts + [e for e in bm.edges if not e.hide and all(v in selected for v in e.verts)]
    geom += [f for f in bm.faces if f.select and not f.hide]
    if abs(angle) < 1e-9:
        return {"angle": angle, "steps": steps}
    axis = Vector(tuple(int(axis_name == name) for name in "XYZ"))
    world = obj.matrix_world
    try:
        inverse = world.inverted()
    except ValueError as exc:
        raise CommandError("La escala del objeto no permite revolucionar", code="degenerate_reference") from exc
    originals = set(bm.verts)
    positions = {v: v.co.copy() for v in verts}
    for vert in verts:
        vert.co = world @ vert.co
    result = bmesh.ops.spin(bm, geom=geom, cent=center, axis=axis, angle=math.radians(angle),
                            steps=steps, use_merge=bool(params.get("merge", True)) and abs(angle) == 360)
    tolerance = 1e-7 / max(bpy.context.scene.unit_settings.scale_length, 1e-12)
    poles = [v for v in bm.verts if (v not in originals or v in selected)
             and (v.co-center).cross(axis).length < tolerance]
    if len(poles) > 1:
        bmesh.ops.remove_doubles(bm, verts=poles, dist=tolerance)
    for vert in bm.verts:
        if vert not in originals:
            vert.co = inverse @ vert.co
    for vert, position in positions.items():
        if vert.is_valid:
            vert.co = position
    for seq in (bm.faces, bm.edges, bm.verts):
        for element in seq:
            element.select = False
    for element in result['geom_last']:
        if element.is_valid:
            element.select_set(True)
    bm.normal_update()
    bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=True)
    return {"angle": angle, "steps": steps}
