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


def _selected_faces_for_normals(bm) -> list:
    """Caras afectadas por las acciones de normales.

    Blender permite invocar Alt+N desde cualquiera de los tres submodos.  En
    vértices/aristas la intención sigue siendo las caras incidentes, mientras
    que en caras se respeta exactamente la selección.  Centralizarlo evita que
    los dos comandos discrepen silenciosamente.
    """
    vert_mode, edge_mode, face_mode = _select_mode()
    if face_mode:
        return [face for face in bm.faces if face.select]
    if edge_mode:
        return list({face for edge in bm.edges if edge.select for face in edge.link_faces})
    if vert_mode:
        return list({face for vert in bm.verts if vert.select for face in vert.link_faces})
    return []


def _selected_geometry(bm) -> list:
    """Devuelve geometría efectiva, incluso si el submodo no está actualizado."""
    return [elem for seq in (bm.verts, bm.edges, bm.faces) for elem in seq if elem.select]


def _edge_components(edges: list) -> list[list]:
    """Componentes por conectividad restringida a ``edges``."""
    remaining = set(edges)
    components = []
    while remaining:
        todo = [remaining.pop()]
        component = []
        while todo:
            edge = todo.pop()
            component.append(edge)
            for vert in edge.verts:
                for other in vert.link_edges:
                    if other in remaining:
                        remaining.remove(other)
                        todo.append(other)
        components.append(component)
    return components


def _resolve_extrude_direction(payload: dict, obj) -> Vector | None:
    """Vector unitario LOCAL para la restricción X/Y/Z, o None para FREE.

    - LOCAL: ejes del objeto (en BMesh ya son locales).
    - GLOBAL: eje mundial convertido a local con la 3×3 inversa de `matrix_world`
      (normalizado, para no arrastrar magnitud de una escala no uniforme).
    - VIEW: X = derecha de pantalla, Y = arriba, Z = profundidad de cámara, leídos de
      la cámara de la tablet y convertidos a local. Nunca se toca `rv3d`.
    """
    constraint = str(payload.get("constraint", "FREE")).upper()
    if constraint == "FREE":
        return None
    if constraint not in {"X", "Y", "Z"}:
        raise BadPayload("'constraint' must be FREE, X, Y or Z")
    orientation = str(payload.get("orientation", "GLOBAL")).upper()
    if orientation not in {"GLOBAL", "LOCAL", "VIEW"}:
        raise BadPayload("'orientation' must be GLOBAL, LOCAL or VIEW")

    axis = {"X": Vector((1.0, 0.0, 0.0)), "Y": Vector((0.0, 1.0, 0.0)), "Z": Vector((0.0, 0.0, 1.0))}[constraint]
    if orientation == "LOCAL":
        return axis.copy()
    if orientation == "GLOBAL":
        return (obj.matrix_world.inverted().to_3x3() @ axis).normalized()

    # VIEW
    from ..camera import camera

    found = find_view3d()
    if found is None:
        raise CommandError("VIEW orientation requires a viewport", code="no_viewport")
    camera.sync_from_region(found[3])
    world = camera.rotation @ {"X": Vector((1.0, 0.0, 0.0)),
                               "Y": Vector((0.0, 1.0, 0.0)),
                               "Z": Vector((0.0, 0.0, -1.0))}[constraint]
    return (obj.matrix_world.inverted().to_3x3() @ world).normalized()


@command("mesh.extrude", mutating=True)
def extrude(payload: dict) -> dict:
    """Extruye la selección. `offset` desplaza a lo largo de la normal media.

    Con offset 0 (por defecto) la geometría nueva queda encima de la original y
    queda seleccionada: la tablet puede arrastrarla después con transform.move,
    igual que el flujo E + mover de Blender.

    `constraint` (FREE|X|Y|Z) + `orientation` (GLOBAL|LOCAL|VIEW) restringen el
    desplazamiento de la variante REGION a un solo eje, igual que pulsar X/Y/Z tras
    Extrude en Blender. Solo REGION lo admite; FREE conserva el comportamiento anterior.
    """
    obj, bm = _bm_and_obj()
    offset = _apply_scalar_snap(get_float(payload, "offset", 0.0), payload)
    variant = str(payload.get("variant", "REGION")).upper()
    if variant not in {"REGION", "ALONG_NORMALS", "INDIVIDUAL"}:
        raise BadPayload("'variant' must be REGION, ALONG_NORMALS or INDIVIDUAL")
    vert_mode, edge_mode, face_mode = _select_mode()
    if variant != "REGION" and not face_mode:
        raise CommandError(f"{variant} requires face selection", code="incompatible_selection")
    if variant == "ALONG_NORMALS" and _custom_direction(payload) is not None:
        raise BadPayload("'direction' is incompatible with ALONG_NORMALS")

    axis = _resolve_extrude_direction(payload, obj)
    if axis is not None:
        if variant != "REGION":
            raise CommandError("'constraint' only applies to REGION", code="incompatible_parameter")
        if _custom_direction(payload) is not None:
            raise BadPayload("'direction' and 'constraint' are mutually exclusive")

    if face_mode:
        faces = [f for f in bm.faces if f.select]
        if not faces:
            raise CommandError("No faces selected", code="empty_selection")
        normal = Vector((0.0, 0.0, 0.0))
        for f in faces:
            normal += f.normal
        normal = normal.normalized() if normal.length > 0 else Vector((0.0, 0.0, 1.0))

        if variant == "INDIVIDUAL":
            # ``extrude_discrete_faces`` crea una copia independiente de cada cara: no
            # comparte paredes laterales ni vértices entre caras contiguas.
            ret = bmesh.ops.extrude_discrete_faces(bm, faces=faces)
            new_geom = list(ret.get("faces", []))
        else:
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

    new_verts = list({vert for geom in new_geom for vert in (
        [geom] if isinstance(geom, bmesh.types.BMVert) else
        list(geom.verts) if isinstance(geom, (bmesh.types.BMEdge, bmesh.types.BMFace)) else []
    )})
    if offset:
        direction = _custom_direction(payload)
        if variant == "ALONG_NORMALS":
            bm.normal_update()
            for vert in new_verts:
                vert.co += vert.normal * offset
        else:
            bmesh.ops.translate(bm, verts=new_verts, vec=(axis or direction or normal) * offset)

    _deselect_all(bm)
    _select_geom(bm, new_geom)
    flush_bmesh(obj, bm)
    _undo(payload, "Remote extrude")
    return {"extruded": kind, "new_verts": len(new_verts), "offset": offset,
            "variant": variant,
            "constraint": str(payload.get("constraint", "FREE")).upper(),
            "orientation": str(payload.get("orientation", "GLOBAL")).upper()}


@command("mesh.inset", mutating=True)
def inset(payload: dict) -> dict:
    obj, bm = _bm_and_obj()
    faces = [f for f in bm.faces if f.select]
    if not faces:
        raise CommandError("No faces selected", code="empty_selection")

    thickness = _apply_scalar_snap(get_float(payload, "thickness", 0.1), payload)
    depth = get_float(payload, "depth", 0.0)
    variant = str(payload.get("variant", "")).upper()
    if variant and variant not in {"REGION", "INDIVIDUAL"}:
        raise BadPayload("'variant' must be REGION or INDIVIDUAL")
    individual = bool(payload.get("individual", False)) or variant == "INDIVIDUAL"

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
    return {"thickness": thickness, "depth": depth, "new_faces": len(ret.get("faces", [])),
            "variant": "INDIVIDUAL" if individual else "REGION"}


@command("mesh.bevel", mutating=True)
def bevel(payload: dict) -> dict:
    obj, bm = _bm_and_obj()
    offset = _apply_scalar_snap(get_float(payload, "offset", 0.1), payload)
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
    factor = _apply_scalar_snap(get_float(payload, "factor", 0.0), payload)
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
    # Cada vértice nuevo nace sobre una arista del ring original. Guardar esa
    # procedencia antes de desplazar el corte permite distinguir las aristas de
    # los loops transversales de los tramos adyacentes creados al partir el ring.
    source_segment = {
        vert: _closest_segment(vert.co, segments)[0]
        for vert in new_verts
    }
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
    cut_edges = [
        edge for edge in new_edges
        if edge.verts[0] in source_segment
        and edge.verts[1] in source_segment
        and source_segment[edge.verts[0]] != source_segment[edge.verts[1]]
    ] if len(ring) > 1 else new_edges
    _deselect_all(bm)
    if cut_edges:
        # No usar select_flush(True): cuando todos los bordes de una cara quedan
        # marcados, BMesh selecciona también la cara y vuelve a incorporar sus
        # aristas longitudinales. Loop Cut debe dejar solo los loops nuevos.
        for edge in cut_edges:
            edge.select = True
            for vert in edge.verts:
                vert.select = True
    else:
        _select_geom(bm, new_verts)
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
    from .sessions import cancel_all
    cancel_all(restore=True)
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


@command("mesh.dissolve", mutating=True)
def dissolve(payload: dict) -> dict:
    """Disuelve la selección conservando la superficie circundante."""
    from .sessions import cancel_all
    cancel_all(restore=True)
    obj, bm = _bm_and_obj()
    what = str(payload.get("what", "VERTS")).upper()
    if what == "VERTS":
        geom = [v for v in bm.verts if v.select and not v.hide]
        if not geom:
            raise CommandError("No vertices selected", code="empty_selection")
        bmesh.ops.dissolve_verts(bm, verts=geom,
            use_face_split=bool(payload.get("use_face_split", False)),
            use_boundary_tear=bool(payload.get("use_boundary_tear", False)))
    elif what == "EDGES":
        geom = [e for e in bm.edges if e.select and not e.hide]
        if not geom:
            raise CommandError("No edges selected", code="empty_selection")
        bmesh.ops.dissolve_edges(bm, edges=geom,
            use_verts=bool(payload.get("use_verts", True)),
            use_face_split=bool(payload.get("use_face_split", False)))
    elif what == "FACES":
        geom = [f for f in bm.faces if f.select and not f.hide]
        if not geom:
            raise CommandError("No faces selected", code="empty_selection")
        bmesh.ops.dissolve_faces(bm, faces=geom,
            use_verts=bool(payload.get("use_verts", False)))
    else:
        raise BadPayload("'what' must be VERTS, EDGES or FACES")
    count = len(geom)
    flush_bmesh(obj, bm)
    _undo(payload, "Remote mesh dissolve")
    return {"dissolved": what, "count": count}


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


def _apply_scalar_snap(value: float, payload: dict) -> float:
    """Cuadra `value` a incrementos de `snap_step` si `snap_type` lo pide.

    GRID se trata como INCREMENT: estos parámetros son relativos a la sesión
    (desplazamiento, grosor, posición del corte), no una coordenada de mundo con una
    rejilla propia, igual que ya hace transform_modal para ROTATE/SCALE.
    """
    snap_type = str(payload.get("snap_type", "NONE")).upper()
    if snap_type == "NONE":
        return value
    if snap_type not in {"INCREMENT", "GRID"}:
        raise BadPayload("'snap_type' must be NONE, INCREMENT or GRID")
    step = get_float(payload, "snap_step", 0.1)
    if step <= 0:
        raise BadPayload("'snap_step' must be greater than zero")
    return round(value / step) * step


def _custom_direction(payload: dict) -> Vector | None:
    direction = payload.get("direction")
    if direction is None:
        return None
    if not isinstance(direction, (list, tuple)) or len(direction) != 3:
        raise BadPayload("'direction' must be [x, y, z]")
    vec = Vector((float(direction[0]), float(direction[1]), float(direction[2])))
    return vec.normalized() if vec.length > 0 else None


@command("mesh.make_edge_face", mutating=True)
def make_edge_face(payload: dict) -> dict:
    """Equivalente discreto de ``F`` para los submodos Vértice y Arista.

    No depende del orden en que llegaron los índices desde la tablet: BMesh
    decide el contorno contextual.  Antes comprobamos los casos que Blender
    aceptaría como no-op para convertirlos en errores útiles y estables.
    """
    obj, bm = _bm_and_obj()
    vert_mode, edge_mode, face_mode = _select_mode()
    if face_mode:
        raise CommandError("Make Edge/Face is unavailable in face select mode", code="incompatible_selection")

    if vert_mode:
        verts = [vert for vert in bm.verts if vert.select]
        if len(verts) < 2:
            raise CommandError("Select at least two vertices", code="insufficient_selection")
        if len(verts) == 2:
            if bm.edges.get((verts[0], verts[1])) is not None:
                raise CommandError("The edge already exists", code="geometry_exists")
            try:
                edge = bm.edges.new((verts[0], verts[1]))
            except ValueError as exc:
                raise CommandError("Cannot create an edge from this selection", code="topology_incompatible") from exc
            _deselect_all(bm)
            _select_geom(bm, [edge])
            flush_bmesh(obj, bm)
            _undo(payload, "Remote make edge")
            return {"created": "EDGE", "count": 1}

        selected = set(verts)
        if any(set(face.verts) == selected for face in bm.faces):
            raise CommandError("The face already exists", code="geometry_exists")
        try:
            result = bmesh.ops.contextual_create(bm, geom=verts)
        except (ValueError, RuntimeError) as exc:
            raise CommandError("Selected vertices do not form a valid contour", code="topology_incompatible") from exc
        created = result.get("faces", [])
        if not created:
            raise CommandError("Selected vertices do not form a valid contour", code="topology_incompatible")
        _deselect_all(bm)
        _select_geom(bm, created)
        flush_bmesh(obj, bm)
        _undo(payload, "Remote make face")
        return {"created": "FACE", "count": len(created)}

    if not edge_mode:
        raise CommandError("Select vertices or edges", code="incompatible_selection")
    edges = [edge for edge in bm.edges if edge.select]
    if len(edges) < 3:
        raise CommandError("Select a closed edge boundary", code="insufficient_selection")
    vertices = {vert for edge in edges for vert in edge.verts}
    # Un ciclo simple es el único caso que este primer contrato promete.  Es
    # preferible rechazar un ocho/ramificación que adivinar una cara distinta.
    if any(sum(1 for edge in vert.link_edges if edge in edges) != 2 for vert in vertices):
        raise CommandError("Selected edges do not form one closed contour", code="open_contour")
    pending = {edges[0]}
    seen = set()
    while pending:
        edge = pending.pop()
        if edge in seen:
            continue
        seen.add(edge)
        pending.update(other for vert in edge.verts for other in vert.link_edges if other in edges and other not in seen)
    if len(seen) != len(edges):
        raise CommandError("Selected edges form multiple contours", code="topology_incompatible")
    if any(set(face.edges) == set(edges) for face in bm.faces):
        raise CommandError("The face already exists", code="geometry_exists")
    try:
        result = bmesh.ops.edgeloop_fill(bm, edges=edges)
    except (ValueError, RuntimeError) as exc:
        raise CommandError("Selected edges do not form a fillable contour", code="topology_incompatible") from exc
    created = result.get("faces", [])
    if not created:
        raise CommandError("Selected edges do not form a fillable contour", code="topology_incompatible")
    _deselect_all(bm)
    _select_geom(bm, created)
    flush_bmesh(obj, bm)
    _undo(payload, "Remote fill")
    return {"created": "FACE", "count": len(created)}


@command("mesh.normals_recalculate", mutating=True)
def normals_recalculate(payload: dict) -> dict:
    """Recalcula normales hacia fuera (por defecto) o hacia dentro."""
    obj, bm = _bm_and_obj()
    faces = _selected_faces_for_normals(bm)
    if not faces:
        raise CommandError("Select geometry with faces", code="empty_selection")
    inside = bool(payload.get("inside", False))
    try:
        bmesh.ops.recalc_face_normals(bm, faces=faces)
        if inside:
            bmesh.ops.reverse_faces(bm, faces=faces, flip_multires=False)
    except (ValueError, RuntimeError) as exc:
        raise CommandError("Cannot recalculate normals for this topology", code="topology_incompatible") from exc
    flush_bmesh(obj, bm)
    _undo(payload, "Remote recalculate normals inside" if inside else "Remote recalculate normals outside")
    return {"inside": inside, "faces": len(faces)}


@command("mesh.normals_flip", mutating=True)
def normals_flip(payload: dict) -> dict:
    """Voltea las normales de las caras que toca la selección actual."""
    obj, bm = _bm_and_obj()
    faces = _selected_faces_for_normals(bm)
    if not faces:
        raise CommandError("Select geometry with faces", code="empty_selection")
    try:
        bmesh.ops.reverse_faces(bm, faces=faces, flip_multires=False)
    except (ValueError, RuntimeError) as exc:
        raise CommandError("Cannot flip normals for this topology", code="topology_incompatible") from exc
    flush_bmesh(obj, bm)
    _undo(payload, "Remote flip normals")
    return {"faces": len(faces)}


@command("mesh.split", mutating=True)
def split(payload: dict) -> dict:
    """Equivalente de Y: desconecta la selección sin crear otro objeto.

    La operación de Blender conoce las sutilezas de los tres submodos y de la
    selección implícita de caras. Aquí un operador está justificado: no existe
    una primitiva BMesh equivalente que conserve esa semántica contextual.
    """
    obj, bm = _bm_and_obj()
    if not _selected_geometry(bm):
        raise CommandError("Nothing selected to split", code="empty_selection")
    try:
        bpy.ops.mesh.split()
    except RuntimeError as exc:
        raise CommandError("Cannot split this selection", code="topology_incompatible") from exc
    # El operador actualiza la malla de edición y crea su propio undo: no añadir
    # otro undo_push aquí, para que Y siga siendo una sola acción reversible.
    return {"object": obj.name, "created_objects": []}


@command("mesh.separate", mutating=True)
def separate(payload: dict) -> dict:
    """Equivalente estricto de P > Selection; no implementa otros modos aún."""
    obj, bm = _bm_and_obj()
    if not _selected_geometry(bm):
        raise CommandError("Nothing selected to separate", code="empty_selection")
    before = set(bpy.data.objects.keys())
    try:
        bpy.ops.mesh.separate(type="SELECTED")
    except RuntimeError as exc:
        raise CommandError("Cannot separate this selection", code="topology_incompatible") from exc
    created = sorted(set(bpy.data.objects.keys()) - before)
    if not created:
        raise CommandError("Selection did not create a separate object", code="topology_incompatible")
    # Igual que split, mesh.separate ya crea el único paso de undo requerido.
    return {"separated": "SELECTION", "created_objects": created}


def bridge_edge_loops(payload: dict) -> dict:
    """Une dos anillos de aristas seleccionados mediante ``bridge_loops``.

    Esta función se usa exclusivamente desde la sesión paramétrica ``tool.*``:
    su llamador restaura el BMesh original antes de cada preview y añade el undo
    sólo al confirmar.  Por eso respeta ``_no_undo`` igual que el resto de
    herramientas de ``mesh``.
    """
    obj, bm = _bm_and_obj()
    _vert_mode, edge_mode, _face_mode = _select_mode()
    if not edge_mode:
        raise CommandError("Bridge Edge Loops requires edge select mode", code="incompatible_selection")
    edges = [edge for edge in bm.edges if edge.select and not edge.hide]
    if len(edges) < 6:
        raise CommandError("Select two edge loops with at least three edges each", code="empty_selection")
    components = _edge_components(edges)
    if len(components) != 2:
        raise CommandError("Select exactly two edge loops", code="ambiguous_loops")
    if len(components[0]) != len(components[1]):
        raise CommandError("Edge loops must have matching edge counts", code="topology_incompatible")
    for loop in components:
        vertices = {vert for edge in loop for vert in edge.verts}
        if len(loop) < 3 or any(
            sum(1 for edge in vert.link_edges if edge in loop) != 2 for vert in vertices
        ):
            raise CommandError("Selected edges must form closed loops", code="topology_incompatible")
        # Un borde puede ser un wire ring (0 caras) o el borde de un agujero (1
        # cara); una arista interior no identifica de forma no ambigua qué lado
        # se debe puentear.
        if any(len(edge.link_faces) > 1 for edge in loop):
            raise CommandError("Selected loops must be boundary loops", code="topology_incompatible")

    twist_offset = get_int(payload, "twist_offset", 0)
    merge = bool(payload.get("merge", False))
    merge_factor = _apply_scalar_snap(get_float(payload, "merge_factor", 0.0), payload)
    if not 0.0 <= merge_factor <= 1.0:
        raise BadPayload("'merge_factor' must be between 0 and 1")
    try:
        result = bmesh.ops.bridge_loops(
            bm,
            edges=edges,
            use_pairs=False,
            use_cyclic=True,
            use_merge=merge,
            merge_factor=merge_factor,
            twist_offset=twist_offset,
        )
    except (ValueError, RuntimeError) as exc:
        raise CommandError("Selected loops cannot be bridged", code="topology_incompatible") from exc
    faces = result.get("faces", [])
    if not faces:
        raise CommandError("Selected loops cannot be bridged", code="topology_incompatible")
    _deselect_all(bm)
    _select_geom(bm, faces)
    flush_bmesh(obj, bm)
    _undo(payload, "Remote bridge edge loops")
    return {"loops": [len(loop) for loop in components], "faces": len(faces),
            "twist_offset": twist_offset, "merge": merge, "merge_factor": merge_factor}


def bisect(payload: dict) -> dict:
    """Corta con un plano infinito `plane_co`/`plane_no` (locales, ya resueltos).

    Como Knife, opera sobre toda la malla visible, no solo la selección: es una
    herramienta de Cut, no una operación sobre lo seleccionado. La sesión que la
    llama (``tool.*``) es quien calcula el plano a partir del arrastre de pantalla;
    aquí solo se aplica el corte, igual que ``bridge_edge_loops`` se limita al bmesh.
    """
    obj, bm = _bm_and_obj()
    plane_co = payload.get("plane_co")
    plane_no = payload.get("plane_no")
    if not isinstance(plane_co, (list, tuple)) or len(plane_co) != 3:
        raise BadPayload("'plane_co' must be [x, y, z]")
    if not isinstance(plane_no, (list, tuple)) or len(plane_no) != 3:
        raise BadPayload("'plane_no' must be [x, y, z]")
    normal = Vector((float(plane_no[0]), float(plane_no[1]), float(plane_no[2])))
    if normal.length < 1e-9:
        raise BadPayload("'plane_no' cannot be a zero vector")
    geom = [elem for elem in list(bm.verts) + list(bm.edges) + list(bm.faces) if not elem.hide]
    if not geom:
        raise CommandError("No geometry to bisect", code="empty_selection")
    clear_inner = bool(payload.get("clear_inner", False))
    clear_outer = bool(payload.get("clear_outer", False))
    fill = bool(payload.get("fill", False))
    try:
        ret = bmesh.ops.bisect_plane(
            bm, geom=geom, dist=1e-4,
            plane_co=Vector((float(plane_co[0]), float(plane_co[1]), float(plane_co[2]))),
            plane_no=normal.normalized(),
            clear_inner=clear_inner, clear_outer=clear_outer,
        )
    except (ValueError, RuntimeError) as exc:
        raise CommandError("Cannot bisect this geometry", code="topology_incompatible") from exc
    cut_geom = ret.get("geom_cut", [])
    cut_edges = [e for e in cut_geom if isinstance(e, bmesh.types.BMEdge)]
    new_faces = []
    if fill and cut_edges:
        try:
            fill_ret = bmesh.ops.edgenet_fill(bm, edges=cut_edges)
            new_faces = fill_ret.get("faces", [])
        except (ValueError, RuntimeError):
            new_faces = []
    if not cut_edges:
        raise CommandError("The plane does not cross any geometry", code="topology_incompatible")
    _deselect_all(bm)
    _select_geom(bm, cut_geom + new_faces)
    flush_bmesh(obj, bm)
    _undo(payload, "Remote bisect")
    return {"cut_edges": len(cut_edges), "clear_inner": clear_inner, "clear_outer": clear_outer,
            "fill": fill, "new_faces": len(new_faces)}
