package com.blendertablet.remote.ui

import com.blendertablet.remote.model.ActiveTool


import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.material.icons.Icons
import androidx.compose.foundation.layout.Box
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Text
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.blendertablet.remote.MainViewModel
import com.blendertablet.remote.model.AppUiState
import com.blendertablet.remote.model.SurfaceCatalog
import com.blendertablet.remote.model.ShapeTool
import com.blendertablet.remote.model.EditSelectionBar
import com.blendertablet.remote.model.ActionId
import com.blendertablet.remote.model.BlenderMode
import com.blendertablet.remote.model.ConnectionStatus
import com.blendertablet.remote.model.SelectionMode
import com.blendertablet.remote.model.Shading

/** Controles generales junto al ojo; al ocultar la interfaz solo permanece el ojo. */
@Composable
fun TopToolbar(
    state: AppUiState,
    vm: MainViewModel,
    chromeVisible: Boolean,
    onToggleChrome: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val blender = state.blender

    Row(modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        // Esta barra vive fuera del chrome porque tiene que sobrevivir al ojo, pero
        // solo el ojo: con la interfaz oculta no queda nada más en pantalla, ni el
        // modo, ni los modificadores de selección, ni los submodos.
        if (chromeVisible) {
            FloatingPanel {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                    IconAction(
                        AppIcons.Wireframe, "Wireframe",
                        selected = blender.view.shading == Shading.WIREFRAME,
                        enabled = blender.features.shading && !blender.material.active,
                    ) { vm.toggleShading() }
                    blender.view.faceOrientation?.let { shown ->
                        IconAction(AppIcons.Normals, "Normales", selected = shown) { vm.toggleFaceOrientation() }
                    }
                    IconAction(AppIcons.Undo, "Deshacer") { vm.undo() }
                    IconAction(AppIcons.Redo, "Rehacer") { vm.redo() }
                }
            }
        }

        FloatingPanel {
            IconAction(
                icon = AppIcons.visibility(!chromeVisible),
                description = if (chromeVisible) "Ocultar controles" else "Mostrar controles",
                onClick = onToggleChrome,
            )
        }
    }
}

/** Modo bajo el ojo; en Edit, los submodos quedan a su izquierda en la misma fila. */
@Composable
fun ModeRail(state: AppUiState, vm: MainViewModel, modifier: Modifier = Modifier) {
    val blender = state.blender
    val editable = blender.activeObject != null
    val inEdit = !blender.cad.workspace && blender.mode == BlenderMode.EDIT
    Row(modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        if (blender.cad.workspace && (blender.cad.activeSketchId == null || blender.cad.surface.mode != "PROFILE")) FloatingPanel {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                listOf("VERTEX" to "Puntos", "EDGE" to "Aristas", "FACE" to "Caras").forEach { (mode, label) ->
                    IconAction(AppIcons.cad(mode), label,
                        selected = blender.cad.surface.mode == mode,
                        enabled = state.connection == ConnectionStatus.CONNECTED && !blender.cad.sessionActive,
                    ) { vm.cadSurfaceMode(mode) }
                }
            }
        }
        if (inEdit) {
            if (blender.activeObjectType == "MESH") FloatingPanel {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                    IconAction(
                        AppIcons.selectionMode(SelectionMode.VERTEX), "Vértices",
                        selected = blender.selectionMode == SelectionMode.VERTEX,
                    ) { vm.setSelectionMode(SelectionMode.VERTEX) }
                    IconAction(
                        AppIcons.selectionMode(SelectionMode.EDGE), "Aristas",
                        selected = blender.selectionMode == SelectionMode.EDGE,
                    ) { vm.setSelectionMode(SelectionMode.EDGE) }
                    IconAction(
                        AppIcons.selectionMode(SelectionMode.FACE), "Caras",
                        selected = blender.selectionMode == SelectionMode.FACE,
                    ) { vm.setSelectionMode(SelectionMode.FACE) }
                }
            }
        }
        FloatingPanel {
            Row(horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                IconAction(AppIcons.ModeObject, "Objeto",
                    selected = blender.mode == BlenderMode.OBJECT && !blender.cad.workspace && !blender.material.active,
                ) { vm.setMode(BlenderMode.OBJECT) }
                IconAction(AppIcons.ModeEdit, "Edición", selected = inEdit,
                    enabled = editable && blender.activeObjectType in setOf("MESH", "CURVE") && !blender.cad.workspace,
                ) { vm.setMode(BlenderMode.EDIT) }
                IconAction(AppIcons.materials, "Materiales", selected = blender.material.active,
                    enabled = blender.material.available && blender.activeObjectType == "MESH" && !blender.cad.workspace,
                ) { vm.enterMaterials() }
                IconAction(AppIcons.sculpt("DRAW"), "Escultura",
                    selected = blender.mode == BlenderMode.SCULPT,
                    enabled = blender.sculpt.available && editable && blender.activeObjectType == "MESH" && !blender.cad.workspace,
                ) { vm.setMode(BlenderMode.SCULPT) }
                if (blender.features.cad.available) IconAction(AppIcons.ModeCad, "CAD", selected = blender.cad.workspace) { vm.enterCad() }
            }
        }
    }
}

/** Rail helper contextual: selección a un toque en el borde derecho. */
@Composable
fun SelectionHelperRail(state: AppUiState, vm: MainViewModel, modifier: Modifier = Modifier) {
    val blender = state.blender
    val hasSelection = when {
        blender.material.active -> blender.material.targets.isNotEmpty()
        blender.cad.workspace -> blender.cad.selectionId != null || blender.cad.surface.selection.isNotEmpty()
        else -> blender.context.hasSelection(blender.mode, blender.selectionMode)
    }
    ToolRail(modifier) {
        RailLabel("SELECCIÓN")
        SelectionIntentControls(state, vm)
        if (!blender.cad.workspace && !blender.material.active && blender.features.gizmo && blender.activeObjectType != "CURVE")
            IconAction(AppIcons.gizmo, "Manipulador", selected = state.gizmoEnabled, onClick = vm::toggleGizmo)
        if (blender.mode == BlenderMode.EDIT && blender.activeObjectType == "MESH")
            IconAction(AppIcons.AutoMerge, "Auto Merge", selected = blender.editSettings.autoMerge, onClick = vm::toggleAutoMerge)
        if (blender.mode == BlenderMode.EDIT && blender.activeObjectType == "MESH")
            IconAction(AppIcons.editCatalog("SELECT_SHORTEST_PATH"), "Camino más corto",
                selected = state.shortestPathActive, onClick = vm::toggleShortestPath)
        if (blender.mode == BlenderMode.EDIT && blender.activeObjectType == "MESH" && blender.features.selectionGrow) {
            IconAction(AppIcons.action(ActionId.SELECT_MORE), "Crecer selección", enabled = hasSelection, onClick = vm::selectMore)
            IconAction(AppIcons.action(ActionId.SELECT_LESS), "Decrecer selección", enabled = hasSelection, onClick = vm::selectLess)
        }
        androidx.compose.foundation.layout.Column(horizontalAlignment = Alignment.CenterHorizontally) {
            EditSelectionBar.actions.filter {
                when {
                    blender.cad.workspace -> it in setOf(ActionId.SELECT_ALL, ActionId.SELECT_INVERT, ActionId.TOOL_BOX, ActionId.TOOL_CIRCLE, ActionId.TOOL_PAINT_SELECT) &&
                        ((blender.cad.surface.mode == "PROFILE" && blender.cad.selectionSketch != null) || (it == ActionId.SELECT_ALL && hasSelection) ||
                         (it in setOf(ActionId.TOOL_BOX, ActionId.TOOL_CIRCLE, ActionId.TOOL_PAINT_SELECT) && blender.cad.surface.mode != "PROFILE"))
                    blender.mode == BlenderMode.OBJECT -> it in setOf(ActionId.SELECT_ALL, ActionId.SELECT_INVERT, ActionId.TOOL_BOX, ActionId.TOOL_CIRCLE, ActionId.TOOL_PAINT_SELECT)
                    blender.activeObjectType == "CURVE" -> it in setOf(ActionId.SELECT_ALL, ActionId.SELECT_INVERT, ActionId.TOOL_PAINT_SELECT)
                    else -> when (it) {
                        ActionId.SELECT_LOOP, ActionId.SELECT_RING -> blender.selectionMode != SelectionMode.VERTEX
                        ActionId.SELECT_SIMILAR -> blender.features.editCatalog.actionsFor(blender.selectionMode).any { action -> action.id == "SELECT_SIMILAR" }
                        else -> true
                    }
                }
            }.forEach { id ->
                // Un único botón alterna Seleccionar todo / Deseleccionar.
                val shown = if (id == ActionId.SELECT_ALL && hasSelection) ActionId.DESELECT_ALL else id
                if (shown == ActionId.SELECT_SIMILAR) SimilarSelectionButton(state, vm, hasSelection)
                else IconAction(
                    AppIcons.action(shown), SurfaceCatalog.labelOf(shown),
                    selected = (shown == ActionId.TOOL_BOX && state.shapeTool == ShapeTool.BOX) ||
                        (shown == ActionId.TOOL_CIRCLE && state.shapeTool == ShapeTool.CIRCLE) ||
                        (shown == ActionId.TOOL_PAINT_SELECT && state.shapeTool == ShapeTool.PAINT),
                    enabled = EditSelectionBar.enabled(shown, blender.selectionMode, hasSelection),
                ) {
                    when (shown) {
                        ActionId.SELECT_ALL -> vm.selectAll()
                        ActionId.DESELECT_ALL -> vm.deselectAll()
                        ActionId.SELECT_INVERT -> vm.invertSelection()
                        ActionId.SELECT_LOOP -> vm.selectLoop()
                        ActionId.SELECT_RING -> vm.selectRing()
                        ActionId.SELECT_LINKED -> vm.selectLinked()
                        ActionId.TOOL_BOX -> vm.toggleShapeTool(ShapeTool.BOX)
                        ActionId.TOOL_CIRCLE -> vm.toggleShapeTool(ShapeTool.CIRCLE)
                        ActionId.TOOL_PAINT_SELECT -> vm.toggleShapeTool(ShapeTool.PAINT)
                        else -> Unit
                    }
                }
            }
        }
    }
}


@Composable
fun SelectionIntentControls(state: AppUiState, vm: MainViewModel) {
    val selectSelected = state.shapeTool == ShapeTool.NONE &&
        (!state.blender.material.active || state.blender.material.interaction == "SELECT") && state.activeTool == ActiveTool.SELECT
    val blender = state.blender
    // En Edición de mallas Tweak comparte botón con Seleccionar (mantener elige la variante).
    if (!blender.cad.workspace && !blender.material.active && blender.mode == BlenderMode.EDIT &&
        blender.activeObjectType == "MESH" && blender.features.selectionTweak) {
        SelectTweakButton(state.activeTool, selectSelected, vm)
    } else IconAction(AppIcons.SelectTool, "Seleccionar", selected = selectSelected, onClick = vm::activateSelection)
}

@Composable
private fun SimilarSelectionButton(state: AppUiState, vm: MainViewModel, hasSelection: Boolean) {
    val blender = state.blender
    val action = blender.features.editCatalog.actionsFor(blender.selectionMode).firstOrNull { it.id == "SELECT_SIMILAR" } ?: return
    var open by remember(blender.selectionMode, blender.activeObject) { mutableStateOf(false) }
    Box {
        IconAction(AppIcons.action(ActionId.SELECT_SIMILAR), "Seleccionar similares",
            enabled = hasSelection && action.enabled) { open = true }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            action.variants.forEach { variant ->
                DropdownMenuItem(text = { Text(variant.label) }, enabled = hasSelection && action.enabled && variant.enabled,
                    onClick = { open = false; vm.selectSimilar(action, variant.id) })
            }
        }
    }
}
