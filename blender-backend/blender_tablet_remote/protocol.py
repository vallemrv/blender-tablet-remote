"""Contrato estable compartido con Android (no depende de :mod:`bpy`)."""

PROTOCOL_VERSION = "2.0"

ENUMS = {
    "mode": ["OBJECT", "EDIT"],
    "selection_mode": ["VERTEX", "EDGE", "FACE"],
    "tool": ["SELECT", "MOVE", "ROTATE", "SCALE", "EXTRUDE", "BEVEL", "INSET", "SUBDIVIDE", "LOOP_CUT"],
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
    "edit_tools": {"version": 1,
                   "tools": ["EXTRUDE", "BEVEL", "INSET", "SUBDIVIDE", "LOOP_CUT"],
                   "loop_cut": {"pick": True, "probe": True, "falloff": ENUMS["loop_falloff"],
                                "even": True, "flip": True, "clamp": True}},
    "files": {"version": 1, "browse": True, "default_folder": True,
              "relative_paths": True},
}
