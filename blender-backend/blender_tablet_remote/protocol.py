"""Contrato estable compartido con Android (no depende de :mod:`bpy`)."""

PROTOCOL_VERSION = "2.0"

ENUMS = {
    "mode": ["OBJECT", "EDIT"],
    "selection_mode": ["VERTEX", "EDGE", "FACE"],
    "tool": ["SELECT", "MOVE", "ROTATE", "SCALE", "EXTRUDE", "BEVEL", "INSET", "SUBDIVIDE", "LOOP_CUT", "BRIDGE_EDGE_LOOPS", "KNIFE"],
    "modifier_type": ["SUBSURF", "ARRAY", "BEVEL", "SOLIDIFY", "BOOLEAN"],
    "subdivision_type": ["CATMULL_CLARK", "SIMPLE"],
    "boolean_operation": ["DIFFERENCE", "UNION", "INTERSECT"],
    "boolean_solver": ["EXACT", "FAST"],
    "constraint": ["FREE", "X", "Y", "Z", "XY", "XZ", "YZ", "NORMAL", "VIEW"],
    "orientation": ["GLOBAL", "LOCAL", "NORMAL", "VIEW"],
    "pivot": ["MEDIAN", "INDIVIDUAL", "CURSOR", "ACTIVE", "WORLD"],
    "snap_type": ["NONE", "INCREMENT", "GRID", "VERTEX", "EDGE", "FACE", "CURSOR"],
    "session_phase": ["IDLE", "ACTIVE", "CONFIRMED", "CANCELLED", "INVALIDATED"],
    "value_mode": ["RELATIVE", "ABSOLUTE"],
    "shading": ["WIREFRAME", "SOLID"],
    "loop_falloff": ["SMOOTH", "SPHERE", "ROOT", "SHARP", "LINEAR", "INVERSE_SQUARE"],
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

_TOOL_PARAMETERS = {
    "EXTRUDE": [
        {"id": "offset", "label": "Desplazamiento", "type": "float", "default": 0.0},
        {"id": "constraint", "label": "Eje", "type": "enum", "default": "FREE",
         "values": ["FREE", "X", "Y", "Z"], "applies_to": ["REGION"]},
        {"id": "orientation", "label": "Orientación", "type": "enum", "default": "GLOBAL",
         "values": ["GLOBAL", "LOCAL", "VIEW"], "applies_to": ["REGION"]},
    ],
    "BEVEL": [
        {"id": "offset", "label": "Ancho", "type": "float", "default": 0.1, "min": 0.0},
        {"id": "segments", "label": "Segmentos", "type": "int", "default": 1, "min": 1},
    ],
    "INSET": [
        {"id": "thickness", "label": "Grosor", "type": "float", "default": 0.1},
        {"id": "depth", "label": "Profundidad", "type": "float", "default": 0.0},
        {"id": "individual", "label": "Individual", "type": "bool", "default": False},
    ],
    "SUBDIVIDE": [{"id": "cuts", "label": "Cortes", "type": "int", "default": 1, "min": 1}],
    "LOOP_CUT": [
        {"id": "cuts", "label": "Cortes", "type": "int", "default": 1, "min": 1},
        {"id": "smoothness", "label": "Suavidad", "type": "float", "default": 0.0},
        {"id": "factor", "label": "Posición", "type": "float", "default": 0.0, "min": -1.0, "max": 1.0},
    ],
    "BRIDGE_EDGE_LOOPS": [
        {"id": "twist_offset", "label": "Desfase", "type": "int", "default": 0},
        {"id": "merge", "label": "Fusionar", "type": "bool", "default": False},
        {"id": "merge_factor", "label": "Factor de fusión", "type": "float", "default": 0.0,
         "min": 0.0, "max": 1.0},
    ],
    "KNIFE": [
        {"id": "snap", "label": "Snap", "type": "bool", "default": True},
    ],
}


EDIT_CATALOG = {
    "version": 1,
    "groups": {
        "VERTEX": [
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
            _edit_action("DELETE", "Eliminar", command="mesh.delete", payload={"what": "VERTS"}, selection=_selection("VERTEX", verts={"min": 1})),
            _edit_action("HIDE", "Ocultar", command="selection.hide", selection=_selection("VERTEX", verts={"min": 1})),
            _edit_action("REVEAL", "Mostrar oculto", command="selection.reveal", selection=_selection("VERTEX")),
        ],
        "EDGE": [
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
            _edit_action("DISSOLVE", "Disolver", enabled=False, selection=_selection("EDGE", edges={"min": 1})),
            _edit_action("DELETE", "Eliminar", command="mesh.delete", payload={"what": "EDGES"}, selection=_selection("EDGE", edges={"min": 1})),
            _edit_action("HIDE", "Ocultar", command="selection.hide", selection=_selection("EDGE", edges={"min": 1})),
            _edit_action("REVEAL", "Mostrar oculto", command="selection.reveal", selection=_selection("EDGE")),
        ],
        "FACE": [
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
            _edit_action("DISSOLVE", "Disolver", enabled=False, selection=_selection("FACE", faces={"min": 1})),
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
    "selection": {"version": 3, "operations": ["SET", "ADD", "REMOVE", "TOGGLE"],
                  "pick": True, "touch_threshold": True, "grow": True,
                  "shapes": ["BOX", "CIRCLE"], "topology": ["LOOP", "RING"]},
    "view": {"version": 3, "axis_views": ["FRONT", "BACK", "LEFT", "RIGHT", "TOP", "BOTTOM"],
             "projections": ["PERSP", "ORTHO"], "independent_camera": True,
             "shading": ENUMS["shading"], "local_view": True},
    "stream": {"version": 2, "preferred": "H264", "transports": ["H264", "MJPEG"],
               "framing": "btr-h264-v1", "capture_default": "OFFSCREEN"},
    "modifiers": {"version": 1, "types": ENUMS["modifier_type"],
                  "commands": ["modifier.add_options", "modifier.add", "modifier.remove",
                               "modifier.move", "modifier.set", "modifier.toggle", "modifier.apply"]},
    "visibility": {"version": 1, "object_hide": True, "hide_set": True},
    "transform_apply": {"version": 1, "components": ["location", "rotation", "scale"]},
    "edit_tools": {"version": 2,
                   "tools": ["EXTRUDE", "BEVEL", "INSET", "SUBDIVIDE", "LOOP_CUT", "BRIDGE_EDGE_LOOPS", "KNIFE"],
                   "loop_cut": {"pick": True, "probe": True, "falloff": ENUMS["loop_falloff"],
                                "even": True, "flip": True, "clamp": True},
                   "knife": {"snap": True, "close": True, "pop": True, "cut_through": False,
                             "threshold": 0.045}},
    "edit_catalog": EDIT_CATALOG,
    "files": {"version": 1, "browse": True, "default_folder": True,
              "relative_paths": True},
}
