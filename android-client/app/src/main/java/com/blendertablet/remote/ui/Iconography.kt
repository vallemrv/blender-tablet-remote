package com.blendertablet.remote.ui

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.CallMade
import androidx.compose.material.icons.automirrored.filled.CallSplit
import androidx.compose.material.icons.automirrored.filled.CompareArrows
import androidx.compose.material.icons.automirrored.filled.RotateRight
import androidx.compose.material.icons.automirrored.filled.ShowChart
import androidx.compose.material.icons.filled.Palette
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Brush
import androidx.compose.material.icons.filled.Image
import androidx.compose.material.icons.filled.AccountTree
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Adjust
import androidx.compose.material.icons.filled.AspectRatio
import androidx.compose.material.icons.filled.AutoFixHigh
import androidx.compose.material.icons.filled.BlurOn
import androidx.compose.material.icons.filled.BookmarkAdd
import androidx.compose.material.icons.filled.CenterFocusStrong
import androidx.compose.material.icons.filled.Draw
import androidx.compose.material.icons.filled.FormatColorReset
import androidx.compose.material.icons.filled.Grain
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.ContentCut
import androidx.compose.material.icons.filled.CropFree
import androidx.compose.material.icons.filled.CropSquare
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.DeleteSweep
import androidx.compose.material.icons.filled.Deselect
import androidx.compose.material.icons.filled.DoNotDisturb
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.FiberManualRecord
import androidx.compose.material.icons.filled.Flip
import androidx.compose.material.icons.filled.Grid4x4
import androidx.compose.material.icons.filled.GridOn
import androidx.compose.material.icons.filled.Hexagon
import androidx.compose.material.icons.filled.Hub
import androidx.compose.material.icons.filled.JoinFull
import androidx.compose.material.icons.filled.Layers
import androidx.compose.material.icons.filled.LibraryAdd
import androidx.compose.material.icons.filled.Lightbulb
import androidx.compose.material.icons.filled.LinearScale
import androidx.compose.material.icons.filled.Lens
import androidx.compose.material.icons.filled.Mouse
import androidx.compose.material.icons.filled.MyLocation
import androidx.compose.material.icons.filled.OpenWith
import androidx.compose.material.icons.filled.PhotoCamera
import androidx.compose.material.icons.filled.RoundedCorner
import androidx.compose.material.icons.filled.RestartAlt
import androidx.compose.material.icons.filled.Rowing
import androidx.compose.material.icons.filled.SelectAll
import androidx.compose.material.icons.filled.ScatterPlot
import androidx.compose.material.icons.filled.Straighten
import androidx.compose.material.icons.filled.TextFields
import androidx.compose.material.icons.filled.Timeline
import androidx.compose.material.icons.filled.TouchApp
import androidx.compose.material.icons.filled.Transform
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material.icons.filled.ViewInAr
import androidx.compose.material.icons.filled.ViewWeek
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material.icons.filled.Waves
import androidx.compose.material.icons.filled.WbSunny
import androidx.compose.material.icons.filled.ZoomOutMap
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.unit.dp
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
    val materials: ImageVector get() = Icons.Default.Palette
    val Fallback: ImageVector = Icons.Default.Tune
    val Duplicate: ImageVector = Icons.Default.ContentCopy
    val DuplicateLinked: ImageVector = Icons.Default.AccountTree
    val Tweak: ImageVector = Icons.Default.TouchApp
    val SnapAuto: ImageVector = Icons.Default.AutoFixHigh
    val Move: ImageVector = Icons.Default.OpenWith
    val Rotate: ImageVector = Icons.AutoMirrored.Filled.RotateRight
    val Scale: ImageVector = Icons.Default.AspectRatio
    val Reset: ImageVector = Icons.Default.RestartAlt
    val Frame: ImageVector = Icons.Default.CenterFocusStrong
    val Multires: ImageVector = Icons.Default.Layers

    val Reference: ImageVector = Icons.Default.Image

    /** Modos, trazos y ayudas del taller de materiales; el rail solo pide intención. */
    fun material(intent: String): ImageVector = when (intent.uppercase()) {
        "SELECT" -> Icons.Default.TouchApp
        "PAINT" -> Icons.Default.Brush
        "ERASE" -> Icons.Default.FormatColorReset
        "LIGHTS" -> Icons.Default.Lightbulb
        "ROUND" -> Icons.Default.Lens
        "AIRBRUSH" -> Icons.Default.BlurOn
        "SPRAY" -> Icons.Default.Grain
        "STYLUS" -> Icons.Default.Draw
        "ISOLATE" -> Icons.Default.CenterFocusStrong
        "SAVE_ZONE" -> Icons.Default.BookmarkAdd
        "OBJECTS" -> Icons.Default.ViewInAr
        "ZONE_ALL" -> Icons.Default.SelectAll
        "ZONE" -> Icons.Default.CropFree
        "LIGHT" -> Icons.Default.WbSunny
        else -> Fallback
    }

    fun sculpt(intent: String): ImageVector = when (intent.uppercase()) {
        "DRAW" -> Icons.Default.Brush
        "CLAY" -> Icons.Default.Layers
        "INFLATE" -> Icons.Default.Lens
        "CREASE" -> Icons.Default.Timeline
        "FLATTEN" -> Icons.Default.LinearScale
        "GRAB" -> Icons.Default.TouchApp
        "SMOOTH" -> Icons.Default.Waves
        "MASK" -> Icons.Default.Flip
        "PINCH" -> Icons.Default.CenterFocusStrong
        "TOPOLOGY" -> Icons.Default.Grid4x4
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
        "RADIUS" to "M3,20 A17,17 0,0 1,20,3 M4,20 L16,8 M11,8 L16,8 L16,13",
        "MIDPOINT" to "M3,12 L21,12 M3,8 L3,16 M21,8 L21,16 M12,7 L17,17 L7,17 Z",
        "SYMMETRIC" to "M12,2 L12,6 M12,9 L12,15 M12,18 L12,22 M3,8 L8,12 L3,16 Z M21,8 L16,12 L21,16 Z",
        "SYMMETRIC_LINE" to "M2,22 L6,18 M10,14 L14,10 M18,6 L22,2 M4,12 L12,20 M5.8,12 A1.8,1.8 0,1,1 2.2,12 A1.8,1.8 0,1,1 5.8,12 M13.8,20 A1.8,1.8 0,1,1 10.2,20 A1.8,1.8 0,1,1 13.8,20",
        "MIRROR" to "M12,2 L12,6 M12,9 L12,15 M12,18 L12,22 M2,18 L9,18 L9,5 Z M22,18 L15,18 L15,5 Z",
        "OFFSET" to "M6,7 L18,7 A5,5 0,0,1 18,17 L6,17 A5,5 0,0,1 6,7 Z M6,10 L18,10 A2,2 0,0,1 18,14 L6,14 A2,2 0,0,1 6,10 Z",
        "ORIGIN" to "M12,2 L12,22 M2,12 L22,12 M16,12 A4,4 0,1 1,8,12 A4,4 0,1 1,16,12",
        "CONSTRUCTION" to "M2,18 L6,15 M9,12 L13,9 M16,6 L21,2 M2,2 L5,5 M8,8 L11,11 M14,14 L17,17 M20,20 L22,22",
        "WELD" to "M2,5 L9,10 M22,5 L15,10 M2,19 L9,14 M22,19 L15,14 M12,8 L16,12 L12,16 L8,12 Z",
        "FIX" to "M5,10 L19,10 L19,21 L5,21 Z M8,10 L8,6 A4,4 0,0 1,16,6 L16,10 M12,14 L12,17",
        "EXTRUDE" to "M3,11 L12,15 L21,11 L12,7 Z M3,11 L3,19 L12,23 L21,19 L21,11 M12,15 L12,23 M12,11 L12,1 M8,5 L12,1 L16,5",
        "LOFT" to "M4,20 L20,20 L20,16 L4,16 Z M9,4 A3,3 0,1 1,15,4 A3,3 0,1 1,9,4 M4,16 L9,4 M20,16 L15,4",
        "HELIX" to "M12,2 L12,22 M6,5 L18,8 M6,10 L18,13 M6,15 L18,18 M6,5 L6,10 M18,8 L18,13 M6,10 L6,15 M18,13 L18,18",
        "CUT" to "M3,9 L3,20 L21,20 L21,9 M3,9 L8,9 L8,16 L16,16 L16,9 L21,9 M12,2 L12,12 M9,9 L12,12 L15,9",
        "SKETCH" to "M3,5 L14,5 M3,5 L3,21 L19,21 L19,12 M8,16 L9,12 L19,2 L22,5 L12,15 Z",
        "SKETCH_FACE" to "M2,10 L11,5 L21,10 L12,16 Z M2,10 L2,18 L12,23 L21,18 L21,10 M12,16 L12,23 M10,12 L11,8 L18,1 L21,4 L14,11 Z",
        "PROJECT" to "M4,5 L14,9 M14,9 L11,7 M14,9 L12,12 M3,18 L21,18 M8,14 L8,18 M16,14 L16,18",
        "POLYGON" to "M3,17 L8,4 L15,7 L21,12 L13,20 Z M8,4 L8.7,6 M15,7 L14,9 M20,12 L18,13.5",
        "PLANE_XY" to "M2,17 L9,8 L22,8 L15,17 Z M7,13 L17,13 M9,4 L9,7",
        "PLANE_XZ" to "M3,20 L3,5 L20,5 L20,20 Z M3,20 L9,14 M9,14 L17,14 M9,14 L9,8",
        "PLANE_YZ" to "M7,3 L19,8 L19,22 L7,17 Z M10,16 L16,18 M10,16 L10,8",
        "SELECT" to "M5,3 L5,20 L10,15 L14,22 L17,20 L13,13 L21,13 Z",
    )
    private val cadVectors by lazy {
        cadPaths.mapValues { (name, data) ->
            ImageVector.Builder("CAD $name", 24.dp, 24.dp, 24f, 24f).addPath(
                pathData = PathParser().parsePathString(data).toNodes(),
                stroke = SolidColor(Color.White), strokeLineWidth = 1.7f,
                strokeLineCap = StrokeCap.Round, strokeLineJoin = StrokeJoin.Round,
            ).build()
        }
    }
    fun cad(intent: String): ImageVector = when (intent) {
        "VERTEX" -> Icons.Default.ScatterPlot
        "EDGE" -> Icons.Default.LinearScale
        "FACE" -> Icons.Default.CropSquare
        "SELECT_ALL" -> Icons.Default.SelectAll
        "DESELECT_ALL" -> Icons.Default.Deselect
        "FINISH" -> Icons.Default.Check
        "CANCEL" -> Icons.Default.Close
        "MODEL" -> Icons.Default.AccountTree
        "DELETE" -> Icons.Default.Delete
        "CONVERT" -> Icons.Default.ViewInAr
        "VISIBLE" -> Icons.Default.Visibility
        else -> cadVectors[intent] ?: Fallback
    }

    /** Angular sketch handles use a diamond; ordinary point handles remain round. */
    fun cadHandlePath(intent: String, x: Float, y: Float, size: Float): android.graphics.Path? =
        if (intent == "ANGLE") android.graphics.Path().apply {
            moveTo(x, y - size); lineTo(x + size, y); lineTo(x, y + size); lineTo(x - size, y); close()
        } else null

    fun action(id: ActionId): ImageVector = when (id) {
        ActionId.PLACE_OBJECT -> Icons.AutoMirrored.Filled.CompareArrows
        ActionId.ADD_OBJECT -> Icons.Default.Add
        ActionId.TOOL_BOX, ActionId.SELECT_ALL -> Icons.Default.SelectAll
        ActionId.TOOL_CIRCLE -> Icons.Default.BlurOn
        ActionId.DESELECT_ALL -> Icons.Default.Deselect
        ActionId.SELECT_INVERT -> Icons.Default.Flip
        ActionId.SELECT_UNDER -> Icons.Default.Mouse
        ActionId.SELECT_ADD_UNDER -> Icons.Default.LibraryAdd
        ActionId.SELECT_LOOP -> Icons.Default.Timeline
        ActionId.SELECT_RING -> Icons.Default.Rowing
        ActionId.SELECT_LINKED -> Icons.Default.Hub
        ActionId.HIDE_OBJECT, ActionId.HIDE_GEOMETRY -> Icons.Default.VisibilityOff
        ActionId.SHADE_OBJECT -> Icons.Default.Lens
        ActionId.VIEW_LOCAL -> Icons.Default.CenterFocusStrong
        ActionId.DUPLICATE -> Duplicate
        ActionId.RENAME -> Icons.Default.Edit
        ActionId.DELETE -> Icons.Default.Delete
        ActionId.DISSOLVE -> Icons.Default.DeleteSweep
        ActionId.APPLY_TRANSFORMS -> Icons.Default.Transform
        ActionId.EDIT_MESH_TOOLS -> Icons.Default.GridOn
        ActionId.EDIT_SELECTION_TOOLS -> Icons.Default.SelectAll
        else -> Fallback
    }

    fun editCatalog(id: String): ImageVector = when (id) {
        "MAKE_EDGE_FACE" -> Icons.Default.CropFree
        "CONNECT_VERTICES" -> Icons.Default.LinearScale
        "SELECT_SHORTEST_PATH" -> Icons.Default.LinearScale
        "SELECT_LOOP" -> Icons.Default.Timeline
        "SELECT_RING" -> Icons.Default.Rowing
        "BRIDGE_EDGE_LOOPS" -> Icons.AutoMirrored.Filled.CompareArrows
        "EXTRUDE" -> Icons.AutoMirrored.Filled.CallMade
        "BEVEL" -> Icons.Default.RoundedCorner
        "INSET" -> Icons.Default.CropFree
        "SUBDIVIDE" -> Icons.Default.Grid4x4
        "REVOLVE" -> Icons.AutoMirrored.Filled.RotateRight
        "SWEEP" -> Icons.Default.Timeline
        "LOOP_CUT" -> Icons.Default.ViewWeek
        "KNIFE", "BISECT" -> Icons.Default.ContentCut
        "SEPARATE" -> Icons.Default.AccountTree
        "SPLIT" -> Icons.AutoMirrored.Filled.CallSplit
        "DISSOLVE" -> Icons.Default.DeleteSweep
        "DELETE" -> Icons.Default.Delete
        "HIDE" -> Icons.Default.VisibilityOff
        "REVEAL" -> Icons.Default.Visibility
        "NORMALS" -> Icons.Default.Layers
        else -> Fallback
    }

    fun editTool(tool: EditTool): ImageVector = when (tool) {
        EditTool.EXTRUDE -> editCatalog("EXTRUDE")
        EditTool.BEVEL -> editCatalog("BEVEL")
        EditTool.INSET -> editCatalog("INSET")
        EditTool.SUBDIVIDE -> editCatalog("SUBDIVIDE")
        EditTool.REVOLVE -> editCatalog("REVOLVE")
        EditTool.SWEEP -> editCatalog("SWEEP")
        EditTool.LOOP_CUT -> editCatalog("LOOP_CUT")
        EditTool.BISECT -> editCatalog("BISECT")
        EditTool.BRIDGE_EDGE_LOOPS -> editCatalog("BRIDGE_EDGE_LOOPS")
        EditTool.KNIFE -> editCatalog("KNIFE")
        EditTool.ALIGN -> action(ActionId.PLACE_OBJECT)
    }

    fun toolbarFamily(id: String): ImageVector = editCatalog(id)

    fun toolbarVariant(familyId: String, variantId: String?): ImageVector =
        if (familyId == "EXTRUDE") when (variantId) {
            "CURSOR" -> Icons.Default.TouchApp
            "MANIFOLD" -> Icons.Default.JoinFull
            "ALONG_NORMALS" -> Icons.Default.ZoomOutMap
            "INDIVIDUAL" -> Icons.AutoMirrored.Filled.CallSplit
            else -> editCatalog(familyId)
        } else toolbarFamily(familyId)

    /** Un símbolo reconocible por destino; SnapControl solo decide estado y color. */
    fun snap(type: SnapType): ImageVector = when (type) {
        SnapType.NONE -> Icons.Default.DoNotDisturb
        SnapType.INCREMENT -> Icons.Default.Straighten
        SnapType.GRID -> Icons.Default.GridOn
        SnapType.VERTEX -> Icons.Default.FiberManualRecord
        SnapType.EDGE -> Icons.Default.LinearScale
        SnapType.EDGE_CENTER -> Icons.Default.Adjust
        SnapType.FACE -> Icons.Default.CropFree
        SnapType.FACE_CENTER -> Icons.Default.CenterFocusStrong
        SnapType.CURSOR -> Icons.Default.MyLocation
    }

    fun addCategory(category: AddCategory): ImageVector = when (category) {
        AddCategory.MESH -> Icons.Default.ViewInAr
        AddCategory.CURVE -> Icons.AutoMirrored.Filled.ShowChart
        AddCategory.SURFACE -> Icons.Default.Waves
        AddCategory.METABALL -> Icons.Default.BlurOn
        AddCategory.TEXT -> Icons.Default.TextFields
        AddCategory.EMPTY -> Icons.Default.CropFree
        AddCategory.LIGHT -> Icons.Default.Lightbulb
        AddCategory.CAMERA -> Icons.Default.PhotoCamera
    }

    fun shading(smooth: Boolean): ImageVector =
        if (smooth) Icons.Default.Hexagon else Icons.Default.Lens

    fun localView(active: Boolean): ImageVector =
        if (active) Icons.Default.ZoomOutMap else Icons.Default.CenterFocusStrong
}
