package com.blendertablet.remote.ui

import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.unit.dp
import com.blendertablet.remote.model.SelectionMode
import com.blendertablet.remote.model.TransformMode
import com.blendertablet.remote.model.ActionId
import com.blendertablet.remote.model.AddCategory
import com.blendertablet.remote.model.EditTool
import com.blendertablet.remote.model.SnapType

/**
 * Vocabulario visual único de la aplicación.
 *
 * Las pantallas piden un icono por intención y nunca eligen un dibujo directamente.
 * Esto evita que una misma herramienta cambie de aspecto entre rail, radial y bandeja,
 * y permite reemplazar un símbolo por uno propio sin perseguir usos por toda la UI.
 */
object AppIcons {
    val gizmo: ImageVector get() = StudioIcons["GIZMO"]
    val Confirm: ImageVector get() = StudioIcons["CONFIRM"]
    val Cancel: ImageVector get() = StudioIcons["CANCEL"]
    val Checked: ImageVector get() = StudioIcons["CONFIRM"]
    val Undo: ImageVector get() = StudioIcons["UNDO"]
    val Redo: ImageVector get() = StudioIcons["REDO"]
    val Back: ImageVector get() = StudioIcons["BACK"]
    val Add: ImageVector get() = StudioIcons["ADD"]
    val Delete: ImageVector get() = StudioIcons["DELETE"]
    val MoveUp: ImageVector get() = StudioIcons["UP"]
    val MoveDown: ImageVector get() = StudioIcons["DOWN"]
    val SubmenuOpen: ImageVector get() = StudioIcons["RIGHT"]
    val SubmenuBack: ImageVector get() = StudioIcons["LEFT"]
    val Dropdown: ImageVector get() = StudioIcons["EXPAND"]
    val Render: ImageVector get() = StudioIcons["CAMERA"]
    val Debug: ImageVector get() = StudioIcons["DEBUG"]
    val Modifiers: ImageVector get() = StudioIcons["MODIFIERS"]
    val EditShortcuts: ImageVector get() = StudioIcons["SHORTCUTS"]
    val Views: ImageVector get() = StudioIcons["VIEWS"]
    val SelectTool: ImageVector get() = StudioIcons["SELECT"]
    val Wireframe: ImageVector get() = StudioIcons["WIREFRAME"]
    val Proportional: ImageVector get() = StudioIcons["PROPORTIONAL"]
    val AutoMerge: ImageVector get() = StudioIcons["AUTO_MERGE"]
    val ModeObject: ImageVector get() = StudioIcons["OBJECT_MODE"]
    val ModeEdit: ImageVector get() = StudioIcons["EDIT_MODE"]
    val materials: ImageVector get() = StudioIcons["MATERIALS"]
    val Fallback: ImageVector get() = StudioIcons["FALLBACK"]
    val Duplicate: ImageVector get() = StudioIcons["DUPLICATE"]
    val DuplicateLinked: ImageVector get() = StudioIcons["DUPLICATE_LINKED"]
    val Tweak: ImageVector get() = StudioIcons["TWEAK"]
    val SnapAuto: ImageVector get() = StudioIcons["SNAP_AUTO"]
    val Move: ImageVector get() = StudioIcons["MOVE"]
    val Rotate: ImageVector get() = StudioIcons["ROTATE"]
    val Scale: ImageVector get() = StudioIcons["SCALE"]
    val Reset: ImageVector get() = StudioIcons["RESET"]
    val Frame: ImageVector get() = StudioIcons["FRAME"]
    val Multires: ImageVector get() = StudioIcons["MULTIRES"]
    val Reference: ImageVector get() = StudioIcons["REFERENCE"]
    val More: ImageVector get() = StudioIcons["MORE"]
    val Collection: ImageVector get() = StudioIcons["COLLECTION"]
    val InFront: ImageVector get() = StudioIcons["IN_FRONT"]

    fun disclosure(open: Boolean): ImageVector = StudioIcons[if (open) "EXPAND" else "RIGHT"]
    fun drawer(open: Boolean): ImageVector = StudioIcons[if (open) "EXPAND" else "COLLAPSE"]
    fun visibility(visible: Boolean): ImageVector = StudioIcons[if (visible) "VISIBLE" else "HIDDEN"]
    fun selectionLock(locked: Boolean): ImageVector = StudioIcons[if (locked) "LOCK" else "UNLOCK"]
    fun chain(linked: Boolean): ImageVector = StudioIcons[if (linked) "CHAIN" else "UNCHAIN"]
    fun selectionMode(mode: SelectionMode): ImageVector = StudioIcons[mode.name]
    fun transform(mode: TransformMode): ImageVector = StudioIcons[mode.name]
    fun origin(intent: String): ImageVector = StudioIcons[when (intent) {
        "CURSOR" -> "ORIGIN_CURSOR"
        "GEOMETRY" -> "ORIGIN_GEOMETRY"
        else -> "ORIGIN_MASS"
    }]
    fun modifier(type: String): ImageVector = when (type) {
        "MULTIRES", "SUBSURF", "ARRAY", "BEVEL", "SOLIDIFY", "BOOLEAN", "MIRROR", "LATTICE" -> StudioIcons[type]
        "SIMPLE_DEFORM" -> StudioIcons["DEFORM"]
        else -> Fallback
    }
    fun material(intent: String): ImageVector = when (intent.uppercase()) {
        "SELECT" -> SelectTool
        "PAINT", "ERASE", "AIRBRUSH", "SPRAY", "STYLUS", "ISOLATE", "SAVE_ZONE", "ZONE" -> StudioIcons[intent.uppercase()]
        "LIGHTS" -> StudioIcons["LIGHT_MOVE"]
        "ROUND" -> StudioIcons["BRUSH_ROUND"]
        "OBJECTS" -> StudioIcons["OBJECT_LIST"]
        "ZONE_ALL" -> StudioIcons["SELECT_ALL"]
        "LIGHT" -> StudioIcons["ENVIRONMENT"]
        else -> Fallback
    }
    fun sculpt(intent: String): ImageVector = when (intent.uppercase()) {
        "DRAW" -> StudioIcons["SCULPT_DRAW"]
        "CLAY", "INFLATE", "CREASE", "FLATTEN", "GRAB", "SMOOTH", "MASK", "PINCH", "TOPOLOGY" -> StudioIcons[intent.uppercase()]
        else -> Fallback
    }

    // Original 24 × 24 stroke icons: each CAD intent has its own silhouette.
    private val cadPaths = mapOf(
        "LINE" to "M4,20 L20,4 M3,18 L6,21 M18,3 L21,6",
        "RECTANGLE" to "M3,6 L21,6 L21,18 L3,18 Z M3,3 L3,4 M21,3 L21,4",
        "CIRCLE" to "M21,12 A9,9 0,1 1,3,12 A9,9 0,1 1,21,12 M10,12 L14,12 M12,10 L12,14",
        "NGON" to "M7.5,4.2 L16.5,4.2 L21,12 L16.5,19.8 L7.5,19.8 L3,12 Z M12,10 L12,14",
        "SLOT" to "M8,7 L16,7 A5,5 0,0 1,16,17 L8,17 A5,5 0,0 1,8,7 Z M8,12 L16,12",
        "GEAR" to "M17,12 A5,5 0,1 1,7,12 A5,5 0,1 1,17,12 M12,2 L12,7 M12,17 L12,22 M2,12 L7,12 M17,12 L22,12 M4.9,4.9 L8.5,8.5 M15.5,15.5 L19.1,19.1 M4.9,19.1 L8.5,15.5 M15.5,8.5 L19.1,4.9 M13.5,12 A1.5,1.5 0,1 1,10.5,12 A1.5,1.5 0,1 1,13.5,12",
        "ARC" to "M3,18 A15,15 0,0 1,18,3 M2,16 L4,20 M16,2 L20,4 M17,18 L21,18 M19,16 L19,20",
        "FILLET" to "M3,3 L3,11 Q3,21 13,21 L21,21 M8,3 L8,9 M15,16 L21,16 M13,9 L8,14 M10,9 L13,9 L13,12",
        "TRIM" to "M3,4 L21,20 M3,20 L21,4 M4,3 A3,3 0,1 1,4,9 A3,3 0,1 1,4,3 M4,15 A3,3 0,1 1,4,21 A3,3 0,1 1,4,15 M15,3 L15,8 M15,16 L15,21",
        "SPLIT" to "M3,5 L10,5 L10,19 L3,19 Z M14,5 L21,5 L21,19 L14,19 Z M12,2 L12,22 M7,2 L5,2 L5,4 M17,20 L17,22 L19,22",
        "COMBINE" to "M3,4 L14,4 L14,15 L3,15 Z M10,9 L21,9 L21,20 L10,20 Z M10,4 L10,9 M14,15 L21,15",
        "PATTERN" to "M3,3 L8,3 L8,8 L3,8 Z M16,3 L21,3 L21,8 L16,8 Z M3,16 L8,16 L8,21 L3,21 Z M16,16 L21,16 L21,21 L16,21 Z M10,5 L14,5 M12,3 L14,5 L12,7 M5,10 L5,14 M3,12 L5,14 L7,12",
        "HOLE" to "M3,5 L21,5 L21,20 L3,20 Z M8,5 L8,10 L10,10 L10,20 M16,5 L16,10 L14,10 L14,20 M12,2 L12,8 M10,6 L12,8 L14,6",
        "SHELL" to "M3,5 L7,3 L21,5 L21,19 L17,22 L3,19 Z M3,5 L3,19 L17,22 L17,8 Z M6,7 L6,17 L14,19 L14,10 Z M7,3 L7,5 M17,8 L21,5",
        "CHAMFER" to "M3,3 L3,13 L11,21 L21,21 M7,3 L7,11 M13,17 L21,17",
        "COINCIDENT" to "M3,6 L10,11 M21,18 L14,13 M15,12 A3,3 0,1 1,9,12 A3,3 0,1 1,15,12",
        "POINT_ON_LINE" to "M3,18 L9,14 M15,10 L21,6 M15,12 A3,3 0,1,1 9,12 A3,3 0,1,1 15,12",
        "HORIZONTAL" to "M3,12 L21,12 M3,8 L3,16 M21,8 L21,16",
        "VERTICAL" to "M12,3 L12,21 M8,3 L16,3 M8,21 L16,21",
        "PARALLEL" to "M4,19 L12,3 M12,21 L20,5",
        "COLLINEAR" to "M3,21 L10,14 M14,10 L21,3 M3,17 L7,21 M17,3 L21,7 M10,10 L14,14 M12,12 L12.1,11.9",
        "PERPENDICULAR" to "M3,20 L21,20 M8,20 L8,3 M8,15 L13,15 L13,20",
        "TANGENT" to "M3,20 L21,20 M19,12 A7,7 0,1 1,5,12 A7,7 0,1 1,19,12 M12,19 L12,22",
        "EQUAL" to "M4,8 L20,8 M4,16 L20,16",
        "DISTANCE" to "M2,15 L9,22 M15,2 L22,9 M5,19 L19,5 M5,14 L5,19 L10,19 M14,5 L19,5 L19,10",
        "DISTANCE_X" to "M3,6 L3,21 M21,6 L21,21 M3,16 L21,16 M7,12 L3,16 L7,20 M17,12 L21,16 L17,20 M8,3 L16,3",
        "DISTANCE_Y" to "M3,3 L18,3 M3,21 L18,21 M13,3 L13,21 M9,7 L13,3 L17,7 M9,17 L13,21 L17,17 M3,8 L3,16",
        "ANGLE" to "M3,20 L21,20 M3,20 L15,6.5 M12,20 A9,9 0,0 0,9,13.3 M9,13.3 L8.8,16 M9,13.3 L11.5,14.4",
        "RADIUS" to "M3,20 A17,17 0,0 1,20,3 M4,20 L16,8 M11,8 L16,8 L16,13",
        "MIDPOINT" to "M3,12 L21,12 M3,8 L3,16 M21,8 L21,16 M12,7 L17,17 L7,17 Z",
        "POINT" to "M15,12 A3,3 0,1,1 9,12 A3,3 0,1,1 15,12 M12,3 L12,7 M12,17 L12,21 M3,12 L7,12 M17,12 L21,12",
        "CLOSE_REFERENCE" to "M3,8 L3,18 L21,18 L21,8 M3,5 L8,5 M16,5 L21,5 M8,2 L11,5 L8,8 M16,2 L13,5 L16,8",
        "SUBDIVIDE" to "M3,12 L21,12 M3,8 L3,16 M21,8 L21,16 M12,9 L12,15 M12,4 L12,6 M12,18 L12,20",
        "SYMMETRIC" to "M12,2 L12,6 M12,9 L12,15 M12,18 L12,22 M3,8 L8,12 L3,16 Z M21,8 L16,12 L21,16 Z",
        "SYMMETRIC_LINE" to "M2,22 L6,18 M10,14 L14,10 M18,6 L22,2 M4,12 L12,20 M5.8,12 A1.8,1.8 0,1,1 2.2,12 A1.8,1.8 0,1,1 5.8,12 M13.8,20 A1.8,1.8 0,1,1 10.2,20 A1.8,1.8 0,1,1 13.8,20",
        "OFFSET" to "M6,7 L18,7 A5,5 0,0,1 18,17 L6,17 A5,5 0,0,1 6,7 Z M6,10 L18,10 A2,2 0,0,1 18,14 L6,14 A2,2 0,0,1 6,10 Z",
        "ORIGIN" to "M12,2 L12,22 M2,12 L22,12 M16,12 A4,4 0,1 1,8,12 A4,4 0,1 1,16,12",
        "CONSTRUCTION" to "M2,18 L6,15 M9,12 L13,9 M16,6 L21,2 M2,2 L5,5 M8,8 L11,11 M14,14 L17,17 M20,20 L22,22",
        "WELD" to "M2,5 L9,10 M22,5 L15,10 M2,19 L9,14 M22,19 L15,14 M12,8 L16,12 L12,16 L8,12 Z",
        "FIX" to "M5,10 L19,10 L19,21 L5,21 Z M8,10 L8,6 A4,4 0,0 1,16,6 L16,10 M12,14 L12,17",
        "LOFT" to "M4,20 L20,20 L20,16 L4,16 Z M9,4 A3,3 0,1 1,15,4 A3,3 0,1 1,9,4 M4,16 L9,4 M20,16 L15,4",
        "HELIX" to "M12,2 L12,22 M6,5 L18,8 M6,10 L18,13 M6,15 L18,18 M6,5 L6,10 M18,8 L18,13 M6,10 L6,15 M18,13 L18,18",
        "CUT" to "M3,9 L3,20 L21,20 L21,9 M3,9 L8,9 L8,16 L16,16 L16,9 L21,9 M12,2 L12,12 M9,9 L12,12 L15,9",
        "SKETCH" to "M3,5 L14,5 M3,5 L3,21 L19,21 L19,12 M8,16 L9,12 L19,2 L22,5 L12,15 Z",
        "SKETCH_FACE" to "M2,10 L11,5 L21,10 L12,16 Z M2,10 L2,18 L12,23 L21,18 L21,10 M12,16 L12,23 M10,12 L11,8 L18,1 L21,4 L14,11 Z",
        "PLANE_EDGE" to "M2,19 L22,19 M6,19 L11,8 L22,8 L18,19 M3,14 A7,7 0,0,1 8,8 M8,8 L5,7.5 M8,8 L7,11",
        "PERSPECTIVE" to "M2,21 L22,21 L16,5 L8,5 Z M12,5 L12,21 M5,13 L19,13 M8.5,5 L7,21 M15.5,5 L17,21",
        "SECTION" to "M3,9 L12,4 L21,9 L21,17 L12,22 L3,17 Z M12,4 L12,22 M1,13 L23,13",
        "PROJECT" to "M4,5 L14,9 M14,9 L11,7 M14,9 L12,12 M3,18 L21,18 M8,14 L8,18 M16,14 L16,18",
        "POLYGON" to "M3,17 L8,4 L15,7 L21,12 L13,20 Z M8,4 L8.7,6 M15,7 L14,9 M20,12 L18,13.5",
    )
    private val cadVectors by lazy {
        cadPaths.mapValues { (name, data) -> StudioIcons.vector("CAD $name", data) }
    }
    /**
     * Sketch planes share one Blender-coloured axis triad (X red, Y green, Z blue,
     * same orientation as Blender's default view); only the filled square changes,
     * so each icon names its two axes by colour instead of an abstract parallelogram.
     */
    private val planeFaces = mapOf(
        "PLANE_XY" to "M4,14 L11,18 L18,14 L11,10 Z",
        "PLANE_XZ" to "M4,14 L11,18 L11,10 L4,6 Z",
        "PLANE_YZ" to "M4,14 L11,10 L11,2 L4,6 Z",
    )
    private val planeNormals = mapOf("PLANE_XY" to 'Z', "PLANE_XZ" to 'Y', "PLANE_YZ" to 'X')
    private val planeVectors by lazy {
        val axes = mapOf('X' to ("M4,14 L15.3,20.5" to Ink.AxisX), 'Y' to ("M4,14 L15.3,7.5" to Ink.AxisY),
            'Z' to ("M4,14 L4,1" to Ink.AxisZ))
        planeFaces.mapValues { (name, face) ->
            ImageVector.Builder("CAD $name", 24.dp, 24.dp, 24f, 24f).apply {
                fun axis(key: Char) = axes.getValue(key).let { (data, color) ->
                    addPath(PathParser().parsePathString(data).toNodes(), stroke = SolidColor(color),
                        strokeLineWidth = 1.9f, strokeLineCap = StrokeCap.Round)
                }
                // Normal axis behind the square (it may pass behind it), in-plane axes on top.
                val normal = planeNormals.getValue(name)
                axis(normal)
                addPath(PathParser().parsePathString(face).toNodes(), fill = SolidColor(Color(0xFFC9CCD2)), fillAlpha = .6f,
                    stroke = SolidColor(Color.White), strokeLineWidth = 1.2f, strokeLineJoin = StrokeJoin.Round)
                "XYZ".filter { it != normal }.forEach(::axis)
            }.build()
        }
    }
    /** Icons whose colours carry meaning and must not be tinted. */
    fun cadMulticolor(intent: String) = intent in planeFaces
    fun cad(intent: String): ImageVector = when (intent) {
        "VERTEX", "EDGE", "FACE", "SELECT_ALL", "DESELECT_ALL", "SELECT", "DELETE", "VISIBLE",
        "EXTRUDE", "REVOLVE", "SWEEP", "MIRROR", "SCENE" -> StudioIcons[intent]
        "FINISH" -> Confirm
        "CANCEL" -> Cancel
        "MODEL" -> StudioIcons["STACK"]
        "CONVERT" -> StudioIcons["CONVERT_MESH"]
        "NEW_PLANE", "VIEW_ROLL", "VIEW_ALIGN" -> StudioIcons[intent]
        else -> planeVectors[intent] ?: cadVectors[intent] ?: Fallback
    }

    /** Angular sketch handles use a diamond; ordinary point handles remain round. */
    fun cadHandlePath(intent: String, x: Float, y: Float, size: Float): android.graphics.Path? =
        if (intent == "ANGLE") android.graphics.Path().apply {
            moveTo(x, y - size); lineTo(x + size, y); lineTo(x, y + size); lineTo(x - size, y); close()
        } else null

    fun action(id: ActionId): ImageVector = when (id) {
        ActionId.PLACE_OBJECT -> StudioIcons["PLACE"]
        ActionId.ADD_OBJECT -> Add
        ActionId.SELECT_ALL -> StudioIcons["SELECT_ALL"]
        ActionId.TOOL_BOX -> StudioIcons["BOX_SELECT"]
        ActionId.TOOL_CIRCLE -> StudioIcons["CIRCLE_SELECT"]
        ActionId.TOOL_PAINT_SELECT -> StudioIcons["PAINT_SELECT"]
        ActionId.DESELECT_ALL -> StudioIcons["DESELECT_ALL"]
        ActionId.SELECT_INVERT -> StudioIcons["INVERT"]
        ActionId.SELECT_UNDER -> StudioIcons["SELECT_UNDER"]
        ActionId.SELECT_ADD_UNDER -> StudioIcons["SELECT_ADD_UNDER"]
        ActionId.SELECT_LOOP -> StudioIcons["LOOP_SELECT"]
        ActionId.SELECT_RING -> StudioIcons["RING_SELECT"]
        ActionId.SELECT_LINKED -> StudioIcons["LINKED_SELECT"]
        ActionId.HIDE_OBJECT, ActionId.HIDE_GEOMETRY -> visibility(false)
        ActionId.SHADE_OBJECT -> StudioIcons["SHADE_SMOOTH"]
        ActionId.VIEW_LOCAL -> StudioIcons["ISOLATE"]
        ActionId.DUPLICATE -> Duplicate
        ActionId.RENAME -> StudioIcons["RENAME"]
        ActionId.DELETE -> Delete
        ActionId.DISSOLVE -> StudioIcons["DISSOLVE"]
        ActionId.APPLY_TRANSFORMS -> StudioIcons["APPLY"]
        ActionId.EDIT_MESH_TOOLS -> StudioIcons["MESH_TOOLS"]
        else -> Fallback
    }

    fun editCatalog(id: String): ImageVector = when (id) {
        "MAKE_EDGE_FACE" -> StudioIcons["FILL"]
        "CONNECT_VERTICES" -> StudioIcons["CONNECT"]
        "SELECT_SHORTEST_PATH" -> StudioIcons["SHORTEST_PATH"]
        "SELECT_LOOP" -> action(ActionId.SELECT_LOOP)
        "SELECT_RING" -> action(ActionId.SELECT_RING)
        "SELECT_LINKED" -> action(ActionId.SELECT_LINKED)
        "BRIDGE_EDGE_LOOPS" -> StudioIcons["BRIDGE"]
        "EXTRUDE", "BEVEL", "INSET", "SUBDIVIDE", "REVOLVE", "SWEEP", "LOOP_CUT",
        "KNIFE", "BISECT", "SEPARATE", "SPLIT", "DISSOLVE", "DELETE", "NORMALS" -> StudioIcons[id]
        "CUT" -> StudioIcons["KNIFE"]
        "HIDE" -> visibility(false)
        "REVEAL" -> visibility(true)
        "RECALCULATE_NORMALS_OUTSIDE" -> StudioIcons["NORMALS"]
        "RECALCULATE_NORMALS_INSIDE" -> StudioIcons["NORMALS_INSIDE"]
        "FLIP_NORMALS" -> StudioIcons["NORMALS_FLIP"]
        "LOOPTOOLS_CIRCLE" -> StudioIcons["MAKE_CIRCLE"]
        else -> Fallback
    }

    fun editTool(tool: EditTool): ImageVector =
        if (tool == EditTool.ALIGN) StudioIcons["ALIGN"] else editCatalog(tool.name)

    fun toolbarFamily(id: String): ImageVector = editCatalog(id)

    /** Variantes del rail y del menú comparten el dibujo de la operación efectiva. */
    fun toolbarVariant(familyId: String, variantId: String?): ImageVector = when (familyId) {
        "EXTRUDE" -> when (variantId) {
            "CURSOR" -> StudioIcons["EXTRUDE_CURSOR"]
            "MANIFOLD" -> StudioIcons["EXTRUDE_MANIFOLD"]
            "ALONG_NORMALS" -> StudioIcons["EXTRUDE_NORMALS"]
            "INDIVIDUAL" -> StudioIcons["EXTRUDE_INDIVIDUAL"]
            else -> editCatalog(familyId)
        }
        "CUT" -> editCatalog(if (variantId == "BISECT") "BISECT" else "KNIFE")
        "INSET" -> if (variantId == "INDIVIDUAL") StudioIcons["INSET_INDIVIDUAL"] else editCatalog(familyId)
        else -> toolbarFamily(familyId)
    }

    /** La flecha hacia geometría distingue el destino de snap del modo de selección. */
    fun snap(type: SnapType): ImageVector = StudioIcons["SNAP_${type.name}"]
    fun addCategory(category: AddCategory): ImageVector = StudioIcons[category.name]

    // El parámetro describe el estado actual: se dibuja la acción ofrecida al tocar.
    fun shading(smooth: Boolean): ImageVector = StudioIcons[if (smooth) "SHADE_FLAT" else "SHADE_SMOOTH"]
    fun localView(active: Boolean): ImageVector = StudioIcons[if (active) "ISOLATE_EXIT" else "ISOLATE"]
}
