"""Motor geométrico del Knife táctil.

Corta una polilínea sobre la malla con la API de BMesh: no usa
``bpy.ops.mesh.knife_tool`` (operador modal con eventos de ratón) ni
``bmesh.ops.bisect_plane`` (corta un plano infinito, no la polilínea finita).

Cada ancla es un punto en coordenadas LOCALES del objeto; su cara se re-descubre por
búsqueda en el momento de resolver, así que los cortes previos (que parten caras y
crean otras nuevas) no invalidan referencias. El caminado entre anclas parte aristas
cruzadas con ``bmesh.utils.edge_split`` y une los vértices resultantes con
``bmesh.ops.connect_verts``, que parte las caras atravesadas por el segmento.
"""

from __future__ import annotations

import bmesh
from mathutils import Vector

from ..errors import CommandError

_EPS = 1e-6
_EPS2 = _EPS * _EPS


def cut_polyline(bm, anchors, closed: bool) -> dict:
    """Corta la polilínea de anclas en ``bm``. ``anchors``: lista de ``[x, y, z]`` locales.

    Los puntos que caen dentro de una cara no se integran de uno en uno: se acumulan
    hasta que el trazo vuelve a tocar el contorno, y entonces la cara se parte en dos
    n-gons siguiendo la cadena. Integrarlos por separado obligaba a triangular la cara
    en abanico, que es de donde salían las diagonales que nadie había dibujado.
    """
    if len(anchors) < 2:
        return {"segments": 0, "new_verts": 0, "new_edges": 0}
    points = list(anchors)
    if closed and len(anchors) >= 3:
        points.append(anchors[0])
    segments = len(points) - 1

    resolved: dict[int, object] = {}
    new_verts = 0
    new_edges = 0
    # Cadena abierta dentro de una cara: (cara, vértice de entrada, interiores).
    pending_face = None
    pending_entry = None
    pending_inside: list = []
    previous = None

    for raw in points:
        face = _interior_face(bm, raw)
        if face is not None and previous is not None:
            # Punto dentro de una cara: aún no se sabe por dónde saldrá el trazo.
            if pending_face is None:
                pending_face, pending_entry = face, previous
            pending_inside.append(Vector(raw))
            continue

        current = _resolve(bm, raw, resolved)
        if pending_inside:
            nv, ne = _apply_chain(
                bm, pending_face, pending_entry, pending_inside, current, resolved)
            new_verts += nv
            new_edges += ne
            pending_face, pending_entry, pending_inside = None, None, []
        elif previous is not None:
            nv, ne = _cut_segment(bm, previous, current)
            new_verts += nv
            new_edges += ne
        previous = current

    # El trazo se quedó dentro de una cara: un corte que no llega al contorno no la
    # divide, igual que en Blender. Esos puntos no dejan geometría suelta.
    return {"segments": segments, "new_verts": new_verts, "new_edges": new_edges}


def _apply_chain(bm, face, entry, inside, exit_vert, resolved):
    """Parte la cara con la cadena; si no se puede, corta punto a punto como antes.

    La partición en n-gons solo vale cuando entrada y salida están en el contorno de la
    misma cara, que es el caso corriente: se entra por un borde, se marcan puntos dentro
    y se sale por otro. Los trazos que encadenan interiores de caras distintas caen al
    camino antiguo, que trianguliza pero corta.
    """
    try:
        return _split_face_with_chain(bm, face, [entry] + inside + [exit_vert])
    except CommandError:
        new_verts = 0
        new_edges = 0
        previous = entry
        for point in inside:
            current = _resolve(bm, point, resolved)
            nv, ne = _cut_segment(bm, previous, current)
            new_verts += nv
            new_edges += ne
            previous = current
        nv, ne = _cut_segment(bm, previous, exit_vert)
        return new_verts + nv, new_edges + ne


def _interior_face(bm, local):
    """Cara cuyo interior contiene ``local`` sin tocar su contorno, o None."""
    point = Vector(local)
    face = _find_face(bm, point)
    if face is None:
        return None
    for v in face.verts:
        if (v.co - point).length_squared < _EPS2:
            return None
    for edge in face.edges:
        _t, dist = _closest_on_segment(point, edge)
        if dist < _EPS2:
            return None
    return face if _point_in_face(face, point) else None


def _split_face_with_chain(bm, face, chain):
    """Parte ``face`` en dos n-gons siguiendo ``chain``.

    ``chain`` empieza y acaba en vértices del contorno de la cara; los de en medio son
    puntos interiores todavía sin crear. Es lo que hace el Knife de Blender: la cara
    atravesada queda en dos trozos y el trazo es su frontera común, sin triangular.
    """
    entry, exit_vert = chain[0], chain[-1]
    loop = list(face.verts)
    if entry not in loop or exit_vert not in loop or entry == exit_vert:
        raise CommandError("Cut does not cross the face", code="disconnected_surface")
    inside = [bm.verts.new(co) for co in chain[1:-1]]
    start, end = loop.index(entry), loop.index(exit_vert)
    forward = _loop_slice(loop, start, end)
    backward = _loop_slice(loop, end, start)
    try:
        bm.faces.new(forward + list(reversed(inside)), face)
        bm.faces.new(backward + inside, face)
    except ValueError as exc:
        for vert in inside:
            bm.verts.remove(vert)
        raise CommandError("Cannot split this face", code="topology_incompatible") from exc
    bm.faces.remove(face)
    return len(inside), len(inside) + 1


def _loop_slice(loop, start, end):
    """Vértices del contorno de ``start`` a ``end``, siguiendo el orden del bucle."""
    out = [loop[start]]
    index = start
    while index != end:
        index = (index + 1) % len(loop)
        out.append(loop[index])
    return out


def _split_edge_vert(edge, t):
    """Parte la arista en ``t`` y devuelve el vértice nuevo (5.2 devuelve tupla)."""
    out = bmesh.utils.edge_split(edge, edge.verts[0], t)
    return out[1] if isinstance(out, tuple) else out


def _resolve(bm, local, resolved):
    """Devuelve un BMVert en ``local``, reutilizando o creando. Cachea por id."""
    key = id(local)
    if key in resolved:
        return resolved[key]
    point = Vector(local)
    face = _find_face(bm, point)
    if face is None:
        raise CommandError("Anchor not on mesh surface", code="disconnected_surface")
    # Snap a un vértice existente de la cara.
    for v in face.verts:
        if (v.co - point).length_squared < _EPS2:
            resolved[key] = v
            return v
    # Snap a una arista de la cara.
    for edge in face.edges:
        t, dist = _closest_on_segment(point, edge)
        if dist < _EPS2 and _EPS < t < 1.0 - _EPS:
            v = _split_edge_vert(edge, t)
            resolved[key] = v
            return v
    # Último recurso para un punto interior que no forma cadena dentro de una sola cara
    # (trazos que encadenan interiores de caras distintas). Trianguliza en abanico, que
    # es justo lo que `_split_face_with_chain` evita: ver la limitación en el plan 005.
    v = _poke(bm, face, point)
    resolved[key] = v
    return v


def _poke(bm, face, point):
    """Integra un punto interior partiendo la cara en un abanico de triángulos."""
    v = bm.verts.new(point)
    corners = [c for c in face.verts]
    bm.faces.remove(face)
    for i in range(len(corners)):
        bm.faces.new((corners[i], corners[(i + 1) % len(corners)], v))
    return v


def _find_face(bm, point):
    """Cara de la malla cuya superficie contiene (o queda más cerca de) ``point``."""
    best_face = None
    best_dist = None
    for face in bm.faces:
        if face.hide:
            continue
        dist = _point_face_distance(face, point)
        if best_dist is None or dist < best_dist:
            best_face, best_dist = face, dist
    if best_face is None or best_dist > 1e-3:
        return None
    return best_face


def _point_face_distance(face, point):
    """Distancia de un punto a la superficie de una cara (plano + bordes)."""
    normal = face.normal
    center = face.calc_center_median()
    plane_dist = abs((point - center).dot(normal))
    # Si la proyección cae dentro, la distancia es la del plano.
    if _point_in_face(face, point):
        return plane_dist
    # Si no, la distancia al borde más cercano.
    best = float("inf")
    for edge in face.edges:
        _t, d = _closest_on_segment(point, edge)
        best = min(best, d)
    return best ** 0.5


def _point_in_face(face, point):
    """Test de interior (convexo) proyectando al plano de la cara."""
    normal = face.normal
    verts = list(face.verts)
    n = len(verts)
    for i in range(n):
        a = verts[i].co
        b = verts[(i + 1) % n].co
        edge = b - a
        cross = edge.cross(normal)
        if (point - a).dot(cross) > _EPS:
            return False
    return True


def _closest_on_segment(point, edge):
    """(t, dist²) del punto más cercano del segmento de la arista al ``point``."""
    a = edge.verts[0].co
    b = edge.verts[1].co
    span = b - a
    length2 = span.length_squared
    if length2 < _EPS2:
        return 0.5, (point - a).length_squared
    t = max(0.0, min(1.0, (point - a).dot(span) / length2))
    closest = a + span * t
    return t, (point - closest).length_squared


def _cut_segment(bm, va, vb):
    """Corta la malla a lo largo del segmento ``va`` -> ``vb``. Devuelve (verts, edges)."""
    if va == vb:
        return 0, 0
    a = va.co.copy()
    b = vb.co.copy()
    if (b - a).length_squared < _EPS2:
        return 0, 0

    # Misma cara: solo unir si aún no hay arista directa.
    if set(va.link_faces) & set(vb.link_faces):
        if not any({va, vb} == set(e.verts) for e in va.link_edges):
            bmesh.ops.connect_verts(bm, verts=[va, vb], check_degenerate=True)
            return 0, 1
        return 0, 0

    current_vert = va
    current_face = _exit_face(va, a, b)
    if current_face is None:
        raise CommandError("Cut leaves the mesh surface", code="disconnected_surface")
    path = []
    guard = 0
    while True:
        guard += 1
        if guard > 100000:
            raise CommandError("Cut did not converge", code="topology_incompatible")
        exit_edge, t_edge = _find_exit(current_face, a, b, current_vert)
        if exit_edge is None:
            break
        v = _split_edge_vert(exit_edge, t_edge)
        path.append(v)
        neighbor = next((f for f in exit_edge.link_faces if f != current_face), None)
        if neighbor is None:
            raise CommandError("Cut leaves the mesh surface", code="disconnected_surface")
        if vb in neighbor.verts or _point_in_face(neighbor, b):
            current_face = neighbor
            break
        current_vert = v
        current_face = neighbor

    chain = [va] + path + [vb]
    deduped = []
    for v in chain:
        if not deduped or deduped[-1] != v:
            deduped.append(v)
    if len(deduped) >= 2:
        bmesh.ops.connect_verts(bm, verts=deduped, check_degenerate=True)
    return len(path), len(path) + 1


def _exit_face(va, a, b):
    """Cara de ``va`` por la que el segmento ``a->b`` sale hacia el objetivo."""
    direction = (b - a).normalized()
    best_face = None
    best_dot = -2.0
    for face in va.link_faces:
        center = face.calc_center_median()
        to_center = center - a
        if to_center.length_squared < _EPS2:
            continue
        dot = direction.dot(to_center.normalized())
        if dot > best_dot:
            best_face, best_dot = face, dot
    return best_face


def _find_exit(face, a, b, current_vert):
    """Arista de ``face`` que cruza el segmento ``a->b`` saliendo de ``current_vert``."""
    best_s = None
    best_edge = None
    best_t = None
    for edge in face.edges:
        if current_vert in edge.verts:
            continue
        cross = _segment_edge_cross(a, b, edge)
        if cross is None:
            continue
        s, t_edge = cross
        if s <= _EPS:
            continue
        if best_s is None or s < best_s:
            best_s, best_edge, best_t = s, edge, t_edge
    return best_edge, best_t


def _segment_edge_cross(a, b, edge):
    """(s, t) donde el segmento ``a->b`` (s) cruza la arista (t), o None.

    Puntos más cercanos entre dos rectas (triple producto) y chequeo de coincidencia
    dentro del umbral, porque el segmento y la arista viven sobre la superficie.
    """
    p0 = edge.verts[0].co
    p1 = edge.verts[1].co
    d1 = b - a
    d2 = p1 - p0
    n = d1.cross(d2)
    if n.length_squared < _EPS2:
        return None
    n1 = d1.cross(n)
    n2 = d2.cross(n)
    denom1 = d1.dot(n2)
    denom2 = d2.dot(n1)
    if abs(denom1) < _EPS2 or abs(denom2) < _EPS2:
        return None
    s = (p0 - a).dot(n2) / denom1
    t = (a - p0).dot(n1) / denom2
    if not (0.0 <= s <= 1.0) or not (0.0 <= t <= 1.0):
        return None
    pa = a + d1 * s
    pb = p0 + d2 * t
    if (pa - pb).length_squared > _EPS2 * 100.0:
        return None
    return s, t
