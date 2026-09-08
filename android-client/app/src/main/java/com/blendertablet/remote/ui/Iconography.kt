package com.blendertablet.remote.ui

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.CallMade
import androidx.compose.material.icons.automirrored.filled.CallSplit
import androidx.compose.material.icons.automirrored.filled.CompareArrows
import androidx.compose.material.icons.automirrored.filled.RotateRight
import androidx.compose.material.icons.automirrored.filled.ShowChart
import androidx.compose.material.icons.filled.AccountTree
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Adjust
import androidx.compose.material.icons.filled.AspectRatio
import androidx.compose.material.icons.filled.AutoFixHigh
import androidx.compose.material.icons.filled.BlurOn
import androidx.compose.material.icons.filled.CenterFocusStrong
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.ContentCut
import androidx.compose.material.icons.filled.CropFree
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
import androidx.compose.material.icons.filled.ZoomOutMap
import androidx.compose.ui.graphics.vector.ImageVector
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
    val Fallback: ImageVector = Icons.Default.Tune
    val Duplicate: ImageVector = Icons.Default.ContentCopy
    val DuplicateLinked: ImageVector = Icons.Default.AccountTree
    val Tweak: ImageVector = Icons.Default.TouchApp
    val SnapAuto: ImageVector = Icons.Default.AutoFixHigh
    val Move: ImageVector = Icons.Default.OpenWith
    val Rotate: ImageVector = Icons.AutoMirrored.Filled.RotateRight
    val Scale: ImageVector = Icons.Default.AspectRatio
    val Reset: ImageVector = Icons.Default.RestartAlt

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
