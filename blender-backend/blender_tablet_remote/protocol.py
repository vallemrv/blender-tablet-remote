"""Contrato estable compartido con Android (no depende de :mod:`bpy`)."""

PROTOCOL_VERSION = "2.0"

ENUMS = {
    "mode": ["OBJECT", "EDIT"],
    "selection_mode": ["VERTEX", "EDGE", "FACE"],
    "tool": ["SELECT", "MOVE", "ROTATE", "SCALE", "EXTRUDE", "BEVEL", "INSET", "SUBDIVIDE", "LOOP_CUT", "BRIDGE_EDGE_LOOPS", "KNIFE", "BISECT"],
    "modifier_type": ["SUBSURF", "ARRAY", "BEVEL", "SOLIDIFY", "BOOLEAN", "MIRROR"],
    "subdivision_type": ["CATMULL_CLARK", "SIMPLE"],
    "boolean_operation": ["DIFFERENCE", "UNION", "INTERSECT"],
    "boolean_solver": ["EXACT", "FAST"],
    "constraint": ["FREE", "X", "Y", "Z", "XY", "XZ", "YZ", "NORMAL", "VIEW"],
    "orientation": ["GLOBAL", "LOCAL", "NORMAL", "VIEW"],
    "pivot": ["MEDIAN", "INDIVIDUAL", "CURSOR", "ACTIVE", "WORLD"],
    "snap_type": ["NONE", "INCREMENT", "GRID", "VERTEX", "EDGE", "EDGE_CENTER",
                  "FACE", "FACE_CENTER", "CURSOR"],
    "session_phase": ["IDLE", "ACTIVE", "CONFIRMED", "CANCELLED", "INVALIDATED"],
    "value_mode": ["RELATIVE", "ABSOLUTE"],
    "shading": ["WIREFRAME", "SOLID"],
    "loop_falloff": ["SMOOTH", "SPHERE", "ROOT", "SHARP", "LINEAR", "INVERSE_SQUARE"],
    "proportional_falloff": ["SMOOTH", "SPHERE", "ROOT", "SHARP", "LINEAR", "CONSTANT", "INVERSE_SQUARE"],
}

UNITS = {"distance": "BLENDER_UNIT", "rotation": "DEGREE", "scale": "FACTOR",
         "screen": "NORMALIZED_TOP_LEFT"}


# Catálogo declarativo para la UI contextual de Edit.  No es una lista de comandos:
# ``id`` es la intención estable que usa la tablet y ``command`` sólo se rellena
# cuando esa intención ya tiene una implementación en este servidor.  Las entradas
# congeladas para el siguiente ciclo se anuncian con ``enabled: false``; así un
# cliente nuevo puede enseñar el sitio reservado sin intentar invocar un wire que
# todavía no existe, y un cliente antiguo simplemente ignora toda la feature.
#
# ``requirements`` se evalúa contra el contexto de Edit actual.  Los contadores son
# mínimos, no una promesa de que cualquier topología sea válida: la operación sigue
# validando contornos/bucles en el backend al ejecutarse.
_EDIT = {"mode": "EDIT"}


def _edit_action(action_id, label, *, command=None, execution="DISCRETE", enabled=True,
                 selection=None, variants=None, parameters=None, payload=None):
    item = {
        "id": action_id,
        "label": label,
        "enabled": enabled,
        "execution": execution,
        "requirements": dict(_EDIT, **(selection or {})),
        "variants": variants or [],
        "parameters": parameters or [],
    }
    if command:
        item["command"] = command
    if payload is not None:
        item["payload"] = payload
    return item


def _selection(mode, **minimum):
    return {"selection_modes": [mode], "selection": minimum}


_EXTRUDE_VARIANTS = [
    {"id": "REGION", "label": "Región", "enabled": True},
    {"id": "ALONG_NORMALS", "label": "A lo largo de normales", "enabled": True},
    {"id": "INDIVIDUAL", "label": "Individual", "enabled": True},
]


def _extrude_variants(face_mode=False):
    """Sólo las caras admiten las dos variantes no regionales."""
    return _EXTRUDE_VARIANTS if face_mode else [
        dict(variant, enabled=variant["id"] == "REGION") for variant in _EXTRUDE_VARIANTS
    ]

# Snap por incremento/rejilla de un parámetro escalar de sesión (offset, factor...).
# Igual que en transform_modal, GRID se trata como INCREMENT: no hay una rejilla de
# mundo natural para un desplazamiento relativo de herramienta paramétrica.
def _scalar_snap(applies_to, step):
    return [
        {"id": "snap_type", "label": "Snap", "type": "enum", "default": "NONE",
         "values": ["NONE", "INCREMENT", "GRID"], "applies_to": applies_to},
        {"id": "snap_step", "label": "Paso", "type": "float", "default": step, "min": 0.0001,
         "applies_to": applies_to},
    ]


_TOOL_PARAMETERS = {
    "EXTRUDE": [
        {"id": "offset", "label": "Desplazamiento", "type": "float", "default": 0.0},
        {"id": "constraint", "label": "Eje", "type": "enum", "default": "FREE",
         "values": ["FREE", "X", "Y", "Z"], "applies_to": ["REGION"]},
        {"id": "orientation", "label": "Orientación", "type": "enum", "default": "GLOBAL",
         "values": ["GLOBAL", "LOCAL", "VIEW"], "applies_to": ["REGION"]},
        *_scalar_snap(["offset"], 0.1),
    ],
    "BEVEL": [
        {"id": "offset", "label": "Ancho", "type": "float", "default": 0.1, "min": 0.0},
        {"id": "segments", "label": "Segmentos", "type": "int", "default": 1, "min": 1},
        *_scalar_snap(["offset"], 0.1),
    ],
    "INSET": [
        {"id": "thickness", "label": "Grosor", "type": "float", "default": 0.1},
        {"id": "depth", "label": "Profundidad", "type": "float", "default": 0.0},
        {"id": "individual", "label": "Individual", "type": "bool", "default": False},
        {"id": "boundary", "label": "Incluir borde", "type": "bool", "default": True,
         "applies_to": ["REGION"]},
        *_scalar_snap(["thickness"], 0.1),
    ],
    "SUBDIVIDE": [{"id": "cuts", "label": "Cortes", "type": "int", "default": 1, "min": 1}],
    "LOOP_CUT": [
        {"id": "cuts", "label": "Cortes", "type": "int", "default": 1, "min": 1},
        {"id": "smoothness", "label": "Suavidad", "type": "float", "default": 0.0},
        {"id": "factor", "label": "Posición", "type": "float", "default": 0.0, "min": -1.0, "max": 1.0},
        {"id": "falloff", "label": "Perfil", "type": "enum", "default": "SMOOTH", "values": ENUMS["loop_falloff"]},
        {"id": "even", "label": "Uniforme", "type": "bool", "default": False},
        {"id": "flip", "label": "Invertir", "type": "bool", "default": False},
        {"id": "clamp", "label": "Fijar al borde", "type": "bool", "default": True},
        *_scalar_snap(["factor"], 0.1),
    ],
    "BRIDGE_EDGE_LOOPS": [
        {"id": "twist_offset", "label": "Desfase", "type": "int", "default": 0},
        {"id": "merge", "label": "Fusionar", "type": "bool", "default": False},
        {"id": "merge_factor", "label": "Factor de fusión", "type": "float", "default": 0.0,
         "min": 0.0, "max": 1.0},
        *_scalar_snap(["merge_factor"], 0.1),
    ],
    "KNIFE": [
        {"id": "snap", "label": "Snap", "type": "bool", "default": True},
    ],
    "BISECT": [
        {"id": "clear_inner", "label": "Vaciar interior", "type": "bool", "default": False},
        {"id": "clear_outer", "label": "Vaciar exterior", "type": "bool", "default": False},
        {"id": "fill", "label": "Rellenar corte", "type": "bool", "default": False},
        {"id": "snap", "label": "Snap", "type": "bool", "default": True},
    ],
}


# ---------------------------------------------------------------------------
# `edit_toolbar`: la barra izquierda de herramientas activas de Edit Mode.
#
# A diferencia de `edit_catalog` (agrupado por submodo de selección, una lista
# discreta de acciones), esta feature agrupa por *familia* con la lógica de
# Blender: una familia tiene una o más variantes, se activa/arma con `tap` y
# permanece marcada mientras hay sesión. El orden de `families` es el orden de
# la barra y es contractual. `edit_catalog` no se toca: sigue siendo el único
# catálogo para clientes que no anuncien soporte de `edit_toolbar`.
_INSET_VARIANTS = [
    {"id": "REGION", "label": "Región", "enabled": True},
    {"id": "INDIVIDUAL", "label": "Individual", "enabled": True},
]


def _toolbar_variant(variant_id, label, *, enabled=True, requirements=None, input=None,
                      payload=None, parameters=None):
    item = {"id": variant_id, "label": label, "enabled": enabled}
    if requirements is not None:
        item["requirements"] = dict(_EDIT, **requirements)
    if input is not None:
        item["input"] = input
    if payload is not None:
        item["payload"] = payload
    if parameters is not None:
        item["parameters"] = parameters
    return item


def _toolbar_family(family_id, label, default_variant, *, input="PARAMETRIC",
                     command="tool.begin", payload=None, requirements=None,
                     variants, parameters=None):
    return {
        "id": family_id,
        "label": label,
        "default_variant": default_variant,
        "execution": "SESSION",
        "command": command,
        "payload": payload if payload is not None else {"tool": family_id},
        "input": input,
        "requirements": dict(_EDIT, **(requirements or {})),
        "variants": variants,
        "parameters": parameters or [],
    }


EDIT_TOOLBAR = {
    "version": 2,
    "families": [
        _toolbar_family(
            "EXTRUDE", "Extrude", "REGION",
            variants=[
                _toolbar_variant("REGION", "Región", requirements=_selection("VERTEX", verts={"min": 1})),
                _toolbar_variant("ALONG_NORMALS", "A lo largo de normales",
                                 requirements=_selection("FACE", faces={"min": 1})),
                _toolbar_variant("INDIVIDUAL", "Individual", requirements=_selection("FACE", faces={"min": 1})),
            ],
            parameters=_TOOL_PARAMETERS["EXTRUDE"],
        ),
        _toolbar_family(
            "BEVEL", "Bevel", "BEVEL",
            variants=[_toolbar_variant("BEVEL", "Bisel")],
            parameters=_TOOL_PARAMETERS["BEVEL"],
        ),
        _toolbar_family(
            "INSET", "Inset", "REGION",
            requirements={"selection_modes": ["FACE"], "selection": {"faces": {"min": 1}}},
            variants=[_toolbar_variant(v["id"], v["label"]) for v in _INSET_VARIANTS],
            parameters=_TOOL_PARAMETERS["INSET"],
        ),
        _toolbar_family(
            "LOOP_CUT", "Loop Cut", "LOOP_CUT", input="VIEWPORT_TAP",
            variants=[_toolbar_variant("LOOP_CUT", "Loop Cut", input="VIEWPORT_TAP")],
            parameters=_TOOL_PARAMETERS["LOOP_CUT"],
        ),
        _toolbar_family(
            "BRIDGE_EDGE_LOOPS", "Bridge", "BRIDGE_EDGE_LOOPS",
            requirements={"selection_modes": ["EDGE"], "selection": {"edges": {"min": 6}}},
            variants=[_toolbar_variant("BRIDGE_EDGE_LOOPS", "Puente entre loops")],
            parameters=_TOOL_PARAMETERS["BRIDGE_EDGE_LOOPS"],
        ),
        _toolbar_family(
            "CUT", "Cut", "KNIFE", command="tool.begin", payload={},
            variants=[
                _toolbar_variant("KNIFE", "Cuchillo", input="VIEWPORT_DRAG_SEGMENTS",
                                 payload={"tool": "KNIFE"}, parameters=_TOOL_PARAMETERS["KNIFE"]),
                _toolbar_variant("BISECT", "Bisect", input="VIEWPORT_DRAG_LINE",
                                 payload={"tool": "BISECT"}, parameters=_TOOL_PARAMETERS["BISECT"]),
            ],
        ),
    ],
}


LOOPTOOLS_CIRCLE_ACTION = {
    "id": "LOOPTOOLS_CIRCLE",
    "label": "Hacer círculo",
    "enabled": True,
    "execution": "DISCRETE",
    "command": "mesh.looptools_circle",
    "requirements": {
        "mode": "EDIT",
        "selection_modes": ["VERTEX", "EDGE"],
        "selection": {"verts": {"min": 3}},
    },
    "variants": [],
    "parameters": [],
}


EDIT_CATALOG = {
    "version": 1,
    "conditional_actions": [
        {
            "id": LOOPTOOLS_CIRCLE_ACTION["id"],
            "label": LOOPTOOLS_CIRCLE_ACTION["label"],
            "command": LOOPTOOLS_CIRCLE_ACTION["command"],
            "execution": LOOPTOOLS_CIRCLE_ACTION["execution"],
            "selection_modes": ["VERTEX", "EDGE"],
            "availability": "OPERATOR_REGISTERED",
            "operator": "mesh.looptools_circle",
        },
    ],
    "groups": {
        "VERTEX": [
            _edit_action("SELECT_LINKED", "Seleccionar enlazado", command="selection.linked",
                         selection=_selection("VERTEX", verts={"min": 1})),
            _edit_action("MAKE_EDGE_FACE", "Crear arista/cara", command="mesh.make_edge_face",
                         selection=_selection("VERTEX", verts={"min": 2})),
            _edit_action("EXTRUDE", "Extruir", command="tool.begin", execution="SESSION", payload={"tool": "EXTRUDE"},
                         selection=_selection("VERTEX", verts={"min": 1}), variants=_extrude_variants(),
                         parameters=_TOOL_PARAMETERS["EXTRUDE"]),
            _edit_action("BEVEL", "Biselar", command="tool.begin", execution="SESSION", payload={"tool": "BEVEL"},
                         selection=_selection("VERTEX", verts={"min": 1}), parameters=_TOOL_PARAMETERS["BEVEL"]),
            _edit_action("SUBDIVIDE", "Subdividir", command="tool.begin", execution="SESSION", payload={"tool": "SUBDIVIDE"},
                         selection=_selection("VERTEX", verts={"min": 1}), parameters=_TOOL_PARAMETERS["SUBDIVIDE"]),
            _edit_action("KNIFE", "Cuchillo", command="tool.begin", execution="SESSION",
                         payload={"tool": "KNIFE"}, selection=_selection("VERTEX"),
                         parameters=_TOOL_PARAMETERS["KNIFE"]),
            _edit_action("SEPARATE", "Separar a objeto", command="mesh.separate",
                         selection=_selection("VERTEX", verts={"min": 1})),
            _edit_action("SPLIT", "Split", command="mesh.split", selection=_selection("VERTEX", verts={"min": 1})),
            _edit_action("DISSOLVE", "Disolver", command="mesh.dissolve", payload={"what": "VERTS"}, selection=_selection("VERTEX", verts={"min": 1})),
            _edit_action("DELETE", "Eliminar", command="mesh.delete", payload={"what": "VERTS"}, selection=_selection("VERTEX", verts={"min": 1})),
            _edit_action("HIDE", "Ocultar", command="selection.hide", selection=_selection("VERTEX", verts={"min": 1})),
            _edit_action("REVEAL", "Mostrar oculto", command="selection.reveal", selection=_selection("VERTEX")),
        ],
        "EDGE": [
            _edit_action("SELECT_LINKED", "Seleccionar enlazado", command="selection.linked",
                         selection=_selection("EDGE", edges={"min": 1})),
            _edit_action("SELECT_LOOP", "Seleccionar loop", command="selection.loop", selection=_selection("EDGE", edges={"min": 1})),
            _edit_action("SELECT_RING", "Seleccionar anillo", command="selection.ring", selection=_selection("EDGE", edges={"min": 1})),
            _edit_action("BRIDGE_EDGE_LOOPS", "Puente entre loops", command="tool.begin", execution="SESSION",
                         payload={"tool": "BRIDGE_EDGE_LOOPS"}, selection=_selection("EDGE", edges={"min": 6}),
                         parameters=_TOOL_PARAMETERS["BRIDGE_EDGE_LOOPS"]),
            _edit_action("MAKE_EDGE_FACE", "Rellenar", command="mesh.make_edge_face", selection=_selection("EDGE", edges={"min": 3})),
            _edit_action("EXTRUDE", "Extruir", command="tool.begin", execution="SESSION", payload={"tool": "EXTRUDE"},
                         selection=_selection("EDGE", edges={"min": 1}), variants=_extrude_variants(),
                         parameters=_TOOL_PARAMETERS["EXTRUDE"]),
            _edit_action("BEVEL", "Biselar", command="tool.begin", execution="SESSION", payload={"tool": "BEVEL"},
                         selection=_selection("EDGE", edges={"min": 1}), parameters=_TOOL_PARAMETERS["BEVEL"]),
            _edit_action("SUBDIVIDE", "Subdividir", command="tool.begin", execution="SESSION", payload={"tool": "SUBDIVIDE"},
                         selection=_selection("EDGE", edges={"min": 1}), parameters=_TOOL_PARAMETERS["SUBDIVIDE"]),
            _edit_action("LOOP_CUT", "Corte de loop", command="tool.begin", execution="SESSION", payload={"tool": "LOOP_CUT"},
                         selection=_selection("EDGE", edges={"min": 1}), parameters=_TOOL_PARAMETERS["LOOP_CUT"]),
            _edit_action("KNIFE", "Cuchillo", command="tool.begin", execution="SESSION",
                         payload={"tool": "KNIFE"}, selection=_selection("EDGE"),
                         parameters=_TOOL_PARAMETERS["KNIFE"]),
            _edit_action("SEPARATE", "Separar a objeto", command="mesh.separate", selection=_selection("EDGE", edges={"min": 1})),
            _edit_action("SPLIT", "Split", command="mesh.split", selection=_selection("EDGE", edges={"min": 1})),
            _edit_action("DISSOLVE", "Disolver", command="mesh.dissolve", payload={"what": "EDGES"}, selection=_selection("EDGE", edges={"min": 1})),
            _edit_action("DELETE", "Eliminar", command="mesh.delete", payload={"what": "EDGES"}, selection=_selection("EDGE", edges={"min": 1})),
            _edit_action("HIDE", "Ocultar", command="selection.hide", selection=_selection("EDGE", edges={"min": 1})),
            _edit_action("REVEAL", "Mostrar oculto", command="selection.reveal", selection=_selection("EDGE")),
        ],
        "FACE": [
            _edit_action("SELECT_LINKED", "Seleccionar enlazado", command="selection.linked",
                         selection=_selection("FACE", faces={"min": 1})),
            _edit_action("EXTRUDE", "Extruir", command="tool.begin", execution="SESSION", payload={"tool": "EXTRUDE"},
                         selection=_selection("FACE", faces={"min": 1}), variants=_extrude_variants(face_mode=True),
                         parameters=_TOOL_PARAMETERS["EXTRUDE"]),
            _edit_action("INSET", "Inset", command="tool.begin", execution="SESSION", payload={"tool": "INSET"},
                         selection=_selection("FACE", faces={"min": 1}), parameters=_TOOL_PARAMETERS["INSET"]),
            _edit_action("BEVEL", "Biselar", command="tool.begin", execution="SESSION", payload={"tool": "BEVEL"},
                         selection=_selection("FACE", faces={"min": 1}), parameters=_TOOL_PARAMETERS["BEVEL"]),
            _edit_action("SUBDIVIDE", "Subdividir", command="tool.begin", execution="SESSION", payload={"tool": "SUBDIVIDE"},
                         selection=_selection("FACE", faces={"min": 1}), parameters=_TOOL_PARAMETERS["SUBDIVIDE"]),
            _edit_action("KNIFE", "Cuchillo", command="tool.begin", execution="SESSION",
                         payload={"tool": "KNIFE"}, selection=_selection("FACE"),
                         parameters=_TOOL_PARAMETERS["KNIFE"]),
            _edit_action("SEPARATE", "Separar a objeto", command="mesh.separate", selection=_selection("FACE", faces={"min": 1})),
            _edit_action("SPLIT", "Split", command="mesh.split", selection=_selection("FACE", faces={"min": 1})),
            _edit_action("RECALCULATE_NORMALS_OUTSIDE", "Recalcular exterior", command="mesh.normals_recalculate", payload={"inside": False}, selection=_selection("FACE", faces={"min": 1})),
            _edit_action("RECALCULATE_NORMALS_INSIDE", "Recalcular interior", command="mesh.normals_recalculate", payload={"inside": True}, selection=_selection("FACE", faces={"min": 1})),
            _edit_action("FLIP_NORMALS", "Voltear normales", command="mesh.normals_flip", selection=_selection("FACE", faces={"min": 1})),
            _edit_action("DISSOLVE", "Disolver", command="mesh.dissolve", payload={"what": "FACES"}, selection=_selection("FACE", faces={"min": 1})),
            _edit_action("DELETE", "Eliminar", command="mesh.delete", payload={"what": "FACES"}, selection=_selection("FACE", faces={"min": 1})),
            _edit_action("HIDE", "Ocultar", command="selection.hide", selection=_selection("FACE", faces={"min": 1})),
            _edit_action("REVEAL", "Mostrar oculto", command="selection.reveal", selection=_selection("FACE")),
        ],
    },
}

FEATURES = {
    "context": {"version": 1, "events": ["context.changed"], "selection_counts": True},
    "transform_modal": {"version": 3, "modes": ["OBJECT", "EDIT"],
                        "tools": ["MOVE", "ROTATE", "SCALE"],
                        "constraints": ENUMS["constraint"], "orientations": ENUMS["orientation"],
                        "owned_sessions": True, "manual_confirm": True,
                        "geometric_snap": True, "locked_candidate": True},
    "edit_settings": {"version": 1, "proportional": True,
                      "falloffs": ENUMS["proportional_falloff"],
                      "radius": True, "auto_merge": True, "merge_threshold": True},
    "selection": {"version": 7, "operations": ["SET", "ADD", "REMOVE", "TOGGLE"],
                  "pick": True, "touch_threshold": True, "grow": True,
                  "shapes": ["BOX", "CIRCLE"], "topology": ["LOOP", "RING"],
                  "linked": True, "shortest_path": True,
                  "tweak": {"phases": ["BEGIN", "UPDATE", "END", "CANCEL"],
                            "selection_modes": ["VERTEX", "EDGE"],
                            "miss_behavior": "ORBIT"}},
    "view": {"version": 4, "axis_views": ["FRONT", "BACK", "LEFT", "RIGHT", "TOP", "BOTTOM"],
             "projections": ["PERSP", "ORTHO"], "independent_camera": True,
             "shading": ENUMS["shading"], "local_view": True, "overlays": True},
    "stream": {"version": 2, "preferred": "H264", "transports": ["H264", "MJPEG"],
               "framing": "btr-h264-v1", "capture_default": "OFFSCREEN"},
    "modifiers": {"version": 2, "types": ENUMS["modifier_type"],
                  "commands": ["modifier.add_options", "modifier.add", "modifier.remove",
                               "modifier.move", "modifier.set", "modifier.toggle", "modifier.apply"]},
    "visibility": {"version": 1, "object_hide": True, "hide_set": True},
    "transform_apply": {"version": 1, "components": ["location", "rotation", "scale"]},
    "object_shading": {"version": 1, "modes": ["TOGGLE", "FLAT", "SMOOTH"]},
    "edit_tools": {"version": 7,
                   "tools": ["EXTRUDE", "BEVEL", "INSET", "SUBDIVIDE", "LOOP_CUT", "BRIDGE_EDGE_LOOPS",
                             "KNIFE", "BISECT"],
                   "loop_cut": {"pick": True, "probe": True, "falloff": ENUMS["loop_falloff"],
                                "even": True, "flip": True, "clamp": True,
                                "multiple": True, "pop": True},
                   "knife": {"snap": True, "close": True, "pop": True, "cut_through": False,
                             "threshold": 0.045, "drag": True, "first_point_drag": True,
                             "projection": True,
                             "snap_types": ["VERTEX", "EDGE_CENTER", "EDGE", "FACE"]},
                   "bisect": {"drag_line": True, "snap": True, "clear_inner": True,
                              "clear_outer": True, "fill": True},
                   "snap": {"scalar": ["INCREMENT", "GRID"],
                            "geometric": ["VERTEX", "EDGE", "EDGE_CENTER", "FACE", "FACE_CENTER", "CURSOR"],
                            "candidate_command": "tool.snap_candidate",
                            "geometric_tools": ["EXTRUDE"], "locked_candidate": True}},
    "edit_catalog": EDIT_CATALOG,
    "edit_toolbar": EDIT_TOOLBAR,
    "files": {"version": 1, "browse": True, "default_folder": True,
              "relative_paths": True},
}
