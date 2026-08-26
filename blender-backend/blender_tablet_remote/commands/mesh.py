"""mesh.* — edición de malla con bmesh (extrude, inset, bevel...).

Todo se hace con `bmesh.ops`, no con operadores modales: así no dependemos del
contexto de la ventana ni de que haya ratón, y el resultado es reproducible.
"""

from __future__ import annotations

import bmesh
import bpy
from mathutils import Vector

from ..bpy_utils import active_object, edit_bmesh, find_view3d, flush_bmesh, get_float, get_int, undo_push
from ..camera import camera
from ..errors import BadPayload, CommandError
from . import command


def _bm_and_obj():
    obj = active_object()
    if obj.mode != "EDIT":
        raise CommandError("mesh.* commands require Edit Mode", code="wrong_mode")
    return obj, edit_bmesh(obj)


def _select_mode() -> tuple[bool, bool, bool]:
    return tuple(bpy.context.scene.tool_settings.mesh_select_mode)


def _deselect_all(bm) -> None:
    for seq in (bm.verts, bm.edges, bm.faces):
        for elem in seq:
            elem.select = False


def _select_geom(bm, geom) -> None:
    for elem in geom:
        if isinstance(elem, (bmesh.types.BMVert, bmesh.types.BMEdge, bmesh.types.BMFace)):
            elem.select = True
    bm.select_flush(True)


@command("mesh.extrude", mutating=True)
def extrude(payload: dict) -> dict:
    """Extruye la selección. `offset` desplaza a lo largo de la normal media.

    Con offset 0 (por defecto) la geometría nueva queda encima de la original y
    queda seleccionada: la tablet puede arrastrarla después con transform.move,
    igual que el flujo E + mover de Blender.
    """
    obj, bm = _bm_and_obj()
    offset = get_float(payload, "offset", 0.0)
    vert_mode, edge_mode, face_mode = _select_mode()

    if face_mode:
        faces = [f for f in bm.faces if f.select]
        if not faces:
            raise CommandError("No faces selected", code="empty_selection")
        normal = Vector((0.0, 0.0, 0.0))
        for f in faces:
            normal += f.normal
        normal = normal.normalized() if normal.length > 0 else Vector((0.0, 0.0, 1.0))

        ret = bmesh.ops.extrude_face_region(bm, geom=faces)
        new_geom = ret["geom"]
        bmesh.ops.delete(bm, geom=faces, context="FACES")
        kind = "faces"
    elif edge_mode:
        edges = [e for e in bm.edges if e.select]
        if not edges:
            raise CommandError("No edges selected", code="empty_selection")
        normal = _average_vert_normal([v for e in edges for v in e.verts])
        ret = bmesh.ops.extrude_edge_only(bm, edges=edges)
        new_geom = ret["geom"]
        kind = "edges"
    else:
        verts = [v for v in bm.verts if v.select]
        if not verts:
            raise CommandError("No vertices selected", code="empty_selection")
        normal = _average_vert_normal(verts)
        ret = bmesh.ops.extrude_vert_indiv(bm, verts=verts)
        new_geom = list(ret["verts"]) + list(ret["edges"])
        kind = "verts"

    new_verts = [g for g in new_geom if isinstance(g, bmesh.types.BMVert)]
    if offset:
        direction = _custom_direction(payload) or normal
        bmesh.ops.translate(bm, verts=new_verts, vec=direction * offset)

    _deselect_all(bm)
    _select_geom(bm, new_geom)
    flush_bmesh(obj, bm)
    _undo(payload, "Remote extrude")
    return {"extruded": kind, "new_verts": len(new_verts), "offset": offset}


@command("mesh.inset", mutating=True)
def inset(payload: dict) -> dict:
    obj, bm = _bm_and_obj()
    faces = [f for f in bm.faces if f.select]
    if not faces:
        raise CommandError("No faces selected", code="empty_selection")

    thickness = get_float(payload, "thickness", 0.1)
    depth = get_float(payload, "depth", 0.0)
    individual = bool(payload.get("individual", False))

    if individual:
        ret = bmesh.ops.inset_individual(bm, faces=faces, thickness=thickness, depth=depth, use_even_offset=True)
    else:
        ret = bmesh.ops.inset_region(
            bm, faces=faces, thickness=thickness, depth=depth, use_even_offset=True, use_boundary=True
        )

    _deselect_all(bm)
    _select_geom(bm, faces)
    flush_bmesh(obj, bm)
    _undo(payload, "Remote inset")
    return {"thickness": thickness, "depth": depth, "new_faces": len(ret.get("faces", []))}


@command("mesh.bevel", mutating=True)
def bevel(payload: dict) -> dict:
    obj, bm = _bm_and_obj()
    offset = get_float(payload, "offset", 0.1)
    segments = max(1, get_int(payload, "segments", 1))
    profile = get_float(payload, "profile", 0.5)
    vert_mode, _edge_mode, _face_mode = _select_mode()
    affect = str(payload.get("affect", "VERTICES" if vert_mode else "EDGES")).upper()
    if affect not in {"EDGES", "VERTICES"}:
        raise BadPayload("'affect' must be EDGES or VERTICES")

    if affect == "VERTICES":
        geom = [v for v in bm.verts if v.select]
    else:
        geom = [e for e in bm.edges if e.select]
    if not geom:
        raise CommandError(f"No {affect.lower()} selected", code="empty_selection")

    ret = bmesh.ops.bevel(
        bm,
        geom=geom,
        offset=offset,
        offset_type="OFFSET",
        segments=segments,
        profile=profile,
        affect=affect,
        clamp_overlap=bool(payload.get("clamp", True)),
    )

    _deselect_all(bm)
    _select_geom(bm, ret.get("faces", []))
    flush_bmesh(obj, bm)
    _undo(payload, "Remote bevel")
    return {"offset": offset, "segments": segments, "new_faces": len(ret.get("faces", []))}


LOOP_FALLOFFS = {"SMOOTH", "SPHERE", "ROOT", "SHARP", "LINEAR", "INVERSE_SQUARE"}


@command("mesh.loop_cut", mutating=True)
def loop_cut(payload: dict) -> dict:
    from .selection import _edge_ring, _seed_edge

    obj, bm = _bm_and_obj()
    seed = _seed_edge(bm, payload)
    if seed is None:
        raise CommandError("Select an edge or provide 'edge'", code="empty_selection")
    ring = list(_edge_ring(seed))
    cuts = get_int(payload, "cuts", 1)
    if cuts < 1:
        raise BadPayload("'cuts' must be at least 1")
    smoothness = get_float(payload, "smoothness", 0.0)
    if not -1.0 <= smoothness <= 1.0:
        raise BadPayload("'smoothness' must be between -1 and 1")
    falloff = str(payload.get("falloff", "SMOOTH")).upper()
    if falloff not in LOOP_FALLOFFS:
        raise BadPayload(f"'falloff' must be one of {', '.join(sorted(LOOP_FALLOFFS))}")
    even = bool(payload.get("even", False))
    flip = bool(payload.get("flip", False))
    clamp = bool(payload.get("clamp", True))
    factor = get_float(payload, "factor", 0.0)
    limit = 1.0 if clamp else 2.0
    if not -limit <= factor <= limit:
        raise BadPayload(f"'factor' must be between -{limit:g} and {limit:g}" + (" (clamp off allows more)" if clamp else ""))
    segments = _oriented_ring_segments(seed, ring)
    lengths = [(end - start).length for start, end in segments]
    average = sum(lengths) / len(lengths) if lengths else 0.0
    # Lo nuevo queda al final de las secuencias (subdivide no borra elementos), así
    # que basta con el tramo posicional final: construir set(bm.verts)+set(bm.edges)
    # enteros costaba dos hashes de toda la malla por cada corte y por cada preview.
    vert_count = len(bm.verts)
    edge_count = len(bm.edges)
    if len(ring) > 1:
        bmesh.ops.subdivide_edgering(bm, edges=ring, cuts=cuts, smooth=smoothness,
                                     profile_shape=falloff)
    else:
        bmesh.ops.subdivide_edges(bm, edges=ring, cuts=cuts, use_grid_fill=False)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    new_verts = [bm.verts[i] for i in range(vert_count, len(bm.verts))]
    if factor or even or flip:
        for vert in new_verts:
            index, start, end, t = _closest_segment(vert.co, segments)
            if start is None:
                continue
            # t parte de la posición que dejó subdivide (el corte central nace en
            # 0.5 para cualquier número de cortes). El factor empuja hacia los
            # extremos; con `even` se mide en longitud real para que el corte
            # recorra la misma distancia absoluta en cada arista del anillo.
            effective = factor
            if even and average > 1e-12:
                effective = factor * (average / max(lengths[index], 1e-12))
            t = t + effective * (1.0 - t) if effective >= 0.0 else t * (1.0 + effective)
            if flip:
                t = 1.0 - t
            # Clamp: dentro del borde (el classic). Sin él, extrapolar siguiendo la
            # línea, con un borde entero de margen para no disparar la geometría.
            t = min(0.999, max(0.001, t)) if clamp else min(2.0, max(-1.0, t))
            vert.co = start.lerp(end, t)
    new_edges = [bm.edges[i] for i in range(edge_count, len(bm.edges))]
    _deselect_all(bm)
    _select_geom(bm, new_edges or new_verts)
    flush_bmesh(obj, bm)
    _undo(payload, "Remote loop cut")
    return {"cuts": cuts, "factor": factor, "smoothness": smoothness, "falloff": falloff,
            "even": even, "flip": flip, "clamp": clamp, "edges": len(ring),
            "new_verts": len(new_verts)}


@command("mesh.loop_probe")
def loop_probe(payload: dict) -> dict:
    """Colocación táctil de un corte: qué arista y en qué punto cae el toque.

    Read-only: no selecciona ni crea undo. La arista es la más cercana al toque
    dentro de la cara impactada (distancia en pantalla, sin umbral — cualquier
    toque sobre la malla elige algo) y `factor` es la proyección del punto sobre
    esa arista, lista para `mesh.loop_cut`/`tool.begin`: -1..1 coloca el corte
    central exactamente donde cayó el dedo.
    """
    from .selection import _edge_ring, _point_segment_distance

    obj, bm = _bm_and_obj()
    found = find_view3d()
    if found is None:
        raise CommandError("No 3D viewport available", code="no_viewport")
    rv3d = found[3]
    camera.sync_from_region(rv3d)

    u = get_float(payload, "u", 0.5)
    v = get_float(payload, "v", 0.5)
    origin, direction = camera.ray(u, v, rv3d)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    hit, _location, _normal, face_index, hit_obj, _matrix = bpy.context.scene.ray_cast(
        depsgraph, origin, direction
    )
    if not hit or hit_obj != obj:
        return {"hit": False}

    bm.faces.ensure_lookup_table()
    face = bm.faces[face_index] if 0 <= face_index < len(bm.faces) else None
    if face is None or face.hide:
        return {"hit": False, "reason": "hidden_or_missing_face"}

    touch = Vector((u, v))
    matrix = obj.matrix_world
    best_edge, best_distance = None, None
    for edge in face.edges:
        if edge.hide:
            continue
        points = [camera.project(matrix @ vert.co, rv3d) for vert in edge.verts]
        if None in points:
            continue
        distance = _point_segment_distance(touch, Vector(points[0]), Vector(points[1]))
        if best_distance is None or distance < best_distance:
            best_edge, best_distance = edge, distance
    if best_edge is None:
        return {"hit": False, "reason": "no_visible_candidate"}

    # Posición del toque proyectada sobre la arista (en pantalla: donde se ve el
    # dedo es donde quiere el corte) y convertida a factor del corte central.
    p0 = Vector(camera.project(matrix @ best_edge.verts[0].co, rv3d))
    p1 = Vector(camera.project(matrix @ best_edge.verts[1].co, rv3d))
    span = p1 - p0
    t = 0.5
    if span.length_squared > 1e-12:
        t = max(0.0, min(1.0, (touch - p0).dot(span) / span.length_squared))
    return {"hit": True, "object": obj.name, "edge": best_edge.index,
            "factor": round(2.0 * t - 1.0, 4), "ring": len(_edge_ring(best_edge))}


def _oriented_ring_segments(seed, ring):
    """Segmentos del anillo orientados todos en la misma dirección visual.

    `edge.verts[0]→verts[1]` es arbitrario y distinto por arista: sin esto, un
    factor positivo sube el corte en una columna y lo baja en la vecina. La
    orientación coherente se deduce caminando las caras cuadradas del anillo: el
    extremo de cada arista opuesta que conecta con el inicio de la anterior (por
    la perpendicular de la cara) es el nuevo inicio.
    """
    ring_set = set(ring)
    oriented = {seed: (seed.verts[0], seed.verts[1])}
    pending = [seed]
    while pending:
        edge = pending.pop()
        start0 = oriented[edge][0]
        for face in edge.link_faces:
            if len(face.edges) != 4:
                continue
            opposite = next((c for c in face.edges if c is not edge and c in ring_set), None)
            if opposite is None or opposite in oriented:
                continue
            start = next(
                (w for w in opposite.verts
                 if any({p.verts[0].index, p.verts[1].index} == {start0.index, w.index}
                        for p in face.edges if p is not edge and p is not opposite)),
                opposite.verts[0],
            )
            oriented[opposite] = (start, opposite.other_vert(start))
            pending.append(opposite)
    return [
        (oriented.get(edge, edge.verts)[0].co.copy(), oriented.get(edge, edge.verts)[1].co.copy())
        for edge in ring
    ]


def _closest_segment(point, segments):
    best = (-1, None, None, 0.5)
    best_dist = None
    for index, (start, end) in enumerate(segments):
        span = end - start
        length = span.length_squared
        if length < 1e-16:
            continue
        t = max(0.0, min(1.0, (point - start).dot(span) / length))
        dist = (point - (start + span * t)).length_squared
        if best_dist is None or dist < best_dist:
            best = (index, start, end, t)
            best_dist = dist
    return best


@command("mesh.subdivide", mutating=True)
def subdivide(payload: dict) -> dict:
    obj, bm = _bm_and_obj()
    edges = [e for e in bm.edges if e.select]
    if not edges:
        raise CommandError("No edges selected", code="empty_selection")
    cuts = max(1, get_int(payload, "cuts", 1))
    ret = bmesh.ops.subdivide_edges(bm, edges=edges, cuts=cuts, use_grid_fill=True)
    _deselect_all(bm)
    _select_geom(bm, ret.get("geom_inner", []))
    flush_bmesh(obj, bm)
    _undo(payload, "Remote subdivide")
    return {"cuts": cuts}


@command("mesh.delete", mutating=True)
def delete(payload: dict) -> dict:
    obj, bm = _bm_and_obj()
    what = str(payload.get("what", "VERTS")).upper()
    contexts = {"VERTS": "VERTS", "EDGES": "EDGES", "FACES": "FACES", "ONLY_FACES": "FACES_ONLY"}
    if what not in contexts:
        raise BadPayload(f"'what' must be one of {', '.join(contexts)}")

    if what == "FACES" or what == "ONLY_FACES":
        geom = [f for f in bm.faces if f.select]
    elif what == "EDGES":
        geom = [e for e in bm.edges if e.select]
    else:
        geom = [v for v in bm.verts if v.select]
    if not geom:
        raise CommandError("Nothing selected to delete", code="empty_selection")

    bmesh.ops.delete(bm, geom=geom, context=contexts[what])
    flush_bmesh(obj, bm)
    _undo(payload, "Remote mesh delete")
    return {"deleted": what, "count": len(geom)}


@command("mesh.info")
def info(payload: dict) -> dict:
    obj, bm = _bm_and_obj()
    return {
        "object": obj.name,
        "verts": len(bm.verts),
        "edges": len(bm.edges),
        "faces": len(bm.faces),
        "selected_verts": sum(1 for v in bm.verts if v.select),
        "selected_edges": sum(1 for e in bm.edges if e.select),
        "selected_faces": sum(1 for f in bm.faces if f.select),
    }


def _undo(payload: dict, message: str) -> None:
    if not payload.get("_no_undo"):
        undo_push(message)


def _average_vert_normal(verts) -> Vector:
    normal = Vector((0.0, 0.0, 0.0))
    for v in verts:
        normal += v.normal
    return normal.normalized() if normal.length > 0 else Vector((0.0, 0.0, 1.0))


def _custom_direction(payload: dict) -> Vector | None:
    direction = payload.get("direction")
    if direction is None:
        return None
    if not isinstance(direction, (list, tuple)) or len(direction) != 3:
        raise BadPayload("'direction' must be [x, y, z]")
    vec = Vector((float(direction[0]), float(direction[1]), float(direction[2])))
    return vec.normalized() if vec.length > 0 else None
