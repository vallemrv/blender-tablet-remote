"""Knife sobre la superficie: cadenas finitas, sin triangulación ni corte pasante."""
from __future__ import annotations

import bmesh
from mathutils import Vector

from ..errors import CommandError

_EPS = 1e-6
_EPS2 = _EPS * _EPS


def cut_polyline(bm, anchors, closed: bool) -> dict:
    """Recorta cada segmento a las caras y las divide por cadenas entre sus bordes.

    Los interiores se acumulan sin crear vértices hasta alcanzar otro borde. La
    cadena se integra en una sola división de la cara, conservando sus n-gons.
    """
    points = [Vector(p) for p in anchors]
    if closed and len(points) >= 3:
        points.append(points[0])
    bm.normal_update()
    chains = []
    for a, b in zip(points, points[1:]):
        if (b - a).length_squared < _EPS2:
            continue
        for face, start, end in _surface_spans(bm, a, b):
            if (chains and chains[-1][0] == face and not _on_boundary(face, start)
                    and (chains[-1][1][-1] - start).length_squared < _EPS2):
                chains[-1][1].append(end)
            else:
                chains.append((face, [start, end]))
    if (closed and len(chains) > 1 and chains[0][0] == chains[-1][0]
            and not _on_boundary(chains[0][0], chains[0][1][0])):
        face, tail = chains.pop()
        chains[0] = (face, tail + chains[0][1][1:])

    before_verts, before_edges = len(bm.verts), len(bm.edges)
    for original_face, chain in chains:
        # Una misma cara puede recibir varios pasos de una polilínea. Tras el
        # primero, localizar el fragmento que contiene toda la cadena siguiente.
        candidates = [original_face] if original_face.is_valid else []
        candidates += [f for f in bm.faces if f not in candidates and not f.hide]
        face = next((f for f in candidates if all(
            _on_face(f, a.lerp(b, .5)) for a, b in zip(chain, chain[1:]))
            and _on_boundary(f, chain[0]) and _on_boundary(f, chain[-1])), None)
        if face is None:
            # Un trazo que termina en el interior sigue siendo overlay, sin abanicos
            # ni geometría suelta. El usuario puede continuarlo hasta el contorno.
            continue
        entry = _resolve_boundary(face, chain[0])
        exit_vert = _resolve_boundary(face, chain[-1])
        if entry == exit_vert:
            continue
        if len(chain) == 2 and bm.edges.get((entry, exit_vert)) is not None:
            continue
        new_face, _ = bmesh.utils.face_split(face, entry, exit_vert, coords=chain[1:-1])
        if new_face is None:
            raise CommandError("Cannot split this face", code="topology_incompatible")
        bm.normal_update()
    for seq in (bm.verts, bm.edges, bm.faces):
        seq.index_update()
    return dict(segments=max(0, len(points) - 1), new_verts=len(bm.verts) - before_verts,
                new_edges=len(bm.edges) - before_edges)


def _surface_spans(bm, a, b):
    """Tramos ordenados y cubiertos por la superficie, nunca por el volumen."""
    spans = []
    for face in bm.faces:
        if face.hide or not _in_plane(face, a) or not _in_plane(face, b):
            continue
        factors = [0.0, 1.0]
        for edge in face.edges:
            cross = _segment_edge_cross(a, b, edge)
            if cross is not None:
                factors.append(cross[0])
            # También vértices colineales con el segmento.
            for vert in edge.verts:
                t, distance = _closest_on_line(vert.co, a, b)
                if distance < _EPS2:
                    factors.append(t)
        factors = sorted(set(factors))
        for start, end in zip(factors, factors[1:]):
            if end - start > _EPS and _point_in_face(face, a.lerp(b, (start + end) * .5)):
                spans.append((start, end, face))
    covered = 0.0
    result = []
    for start, end, face in sorted(spans, key=lambda item: (item[0], -item[1])):
        if end <= covered + _EPS:
            continue
        if start > covered + _EPS:
            break
        result.append((face, a.lerp(b, covered), a.lerp(b, end)))
        covered = end
    if covered < 1.0 - _EPS:
        raise CommandError("El trazo sale de la superficie; marca un punto en el borde antes de continuar",
                           code="disconnected_surface")
    return result


def _in_plane(face, point):
    return abs((point - face.verts[0].co).dot(face.normal)) <= _EPS


def _on_face(face, point):
    return _in_plane(face, point) and _point_in_face(face, point)


def _on_boundary(face, point):
    return any(_closest_on_segment(point, edge)[1] < _EPS2 for edge in face.edges)


def _resolve_boundary(face, point):
    for vert in face.verts:
        if (vert.co - point).length_squared < _EPS2:
            return vert
    for edge in face.edges:
        t, distance = _closest_on_segment(point, edge)
        if distance < _EPS2 and _EPS < t < 1 - _EPS:
            return bmesh.utils.edge_split(edge, edge.verts[0], t)[1]
    raise CommandError("Cut endpoint is not on the face boundary", code="disconnected_surface")


def _point_in_face(face, point):
    """Paridad en el plano dominante: admite n-gons cóncavos de cortes anteriores."""
    if _on_boundary(face, point):
        return True
    drop = max(range(3), key=lambda i: abs(face.normal[i]))
    x, y = [i for i in range(3) if i != drop]
    inside = False
    vertices = list(face.verts)
    for va, vb in zip(vertices, vertices[1:] + vertices[:1]):
        a, b = va.co, vb.co
        if (a[y] > point[y]) != (b[y] > point[y]):
            crossing = a[x] + (point[y] - a[y]) * (b[x] - a[x]) / (b[y] - a[y])
            if point[x] < crossing:
                inside = not inside
    return inside


def _closest_on_line(point, a, b):
    span = b - a
    t = max(0.0, min(1.0, (point - a).dot(span) / span.length_squared)) if span.length_squared > _EPS2 else 0.0
    return t, (point - (a + span * t)).length_squared


def _closest_on_segment(point, edge):
    return _closest_on_line(point, edge.verts[0].co, edge.verts[1].co)


def _segment_edge_cross(a, b, edge):
    p0, p1 = (v.co for v in edge.verts)
    d1, d2 = b - a, p1 - p0
    n = d1.cross(d2)
    if n.length_squared <= 1e-24:
        return None
    s = (p0 - a).cross(d2).dot(n) / n.length_squared
    t = (p0 - a).cross(d1).dot(n) / n.length_squared
    if not (-_EPS <= s <= 1 + _EPS and -_EPS <= t <= 1 + _EPS):
        return None
    s, t = max(0.0, min(1.0, s)), max(0.0, min(1.0, t))
    if (a + d1 * s - p0 - d2 * t).length_squared > _EPS2:
        return None
    return s, t
