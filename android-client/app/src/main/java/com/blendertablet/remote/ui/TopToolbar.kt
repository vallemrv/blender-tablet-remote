package com.blendertablet.remote.ui

import com.blendertablet.remote.model.ActiveTool

import com.blendertablet.remote.model.SelectionOp

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.material.icons.Icons
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

/**
 * Barra horizontal de tools, al lado del ojo (arriba a la derecha).
 *
 * Agrupa lo que se usa a cada toque sin abrir el rail: wireframe (toggle), los
 * el control Ctrl de camino más corto y undo/redo,
 * que salen del rail para quedarse aquí con iconos. La selección por caja B y círculo C
 * vive en el long-click (RADIAL); armada, un chip sobre el viewport la señala y
 * la desarma.
 *
 * La barra entera está fuera del chrome para que el ojo siga siendo alcanzable con
 * la interfaz oculta, pero con `chromeVisible == false` solo queda el ojo: si algo
 * de aquí sobreviviera, "ocultar controles" no ocultaría los controles.
 */
@Composable
fun TopToolbar(
    state: AppUiState,
    vm: MainViewModel,
    chromeVisible: Boolean,
    onToggleChrome: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val blender = state.blender
    val inEdit = !blender.cad.workspace && blender.mode == BlenderMode.EDIT

    Row(modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        // Esta barra vive fuera del chrome porque tiene que sobrevivir al ojo, pero
        // solo el ojo: con la interfaz oculta no queda nada más en pantalla, ni el
        // modo, ni los modificadores de selección, ni los submodos.
        if (chromeVisible) {
            FloatingPanel {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                    if (blender.features.shading && !blender.material.active) {
                        IconAction(
                            AppIcons.Wireframe, "Wireframe",
                            selected = blender.view.shading == Shading.WIREFRAME,
                        ) { vm.toggleShading() }
                    }
                    if (inEdit && blender.activeObjectType == "MESH" && blender.features.editSettings) {
                        IconAction(
                            AppIcons.Proportional, "Edición proporcional",
                            selected = blender.editSettings.proportional,
                        ) {
                            vm.toggleProportional()
                        }
                        IconAction(
                            AppIcons.AutoMerge, "Auto Merge",
                            selected = blender.editSettings.autoMerge,
                        ) {
                            vm.toggleAutoMerge()
                        }
                    }
                    if (!blender.cad.workspace && blender.mode != BlenderMode.SCULPT && !blender.material.active) {
                    if (blender.features.gizmo && !(inEdit && blender.activeObjectType == "CURVE")) IconAction(AppIcons.gizmo, "Manipulador", selected = state.gizmoEnabled) { vm.toggleGizmo() }

                    }
                    // Materiales y CAD no abren una franja propia: su contexto son
                    // iconos en esta misma fila, delante de Deshacer.
                    if (blender.material.active) MaterialTopActions(state, vm)
                    if (blender.cad.workspace) CadTopActions(state, vm)
                    IconAction(AppIcons.Undo, "Deshacer") { vm.undo() }
                    IconAction(AppIcons.Redo, "Rehacer") { vm.redo() }
                    if (blender.cad.workspace) CadSelectionActions(state, vm)
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
                // CAD permanece al final; dentro de ese workspace Object permite salir.
                if (!blender.cad.workspace) {
                    IconAction(
                        AppIcons.ModeObject, "Object Mode",
                        selected = blender.mode == BlenderMode.OBJECT && !blender.cad.workspace && !blender.material.active,
                    ) { vm.setMode(BlenderMode.OBJECT) }
                    IconAction(
                        AppIcons.ModeEdit, "Edit Mode",
                        selected = inEdit,
                        enabled = editable,
                    ) { vm.setMode(BlenderMode.EDIT) }
                    if (blender.material.available) IconAction(AppIcons.materials, "Materiales",
                        selected = blender.material.active, enabled = blender.activeObjectType == "MESH") { vm.enterMaterials() }
                }
                if (blender.cad.workspace) {
                    IconAction(
                        AppIcons.ModeObject, "Salir de CAD a Object Mode",
                    ) { vm.setMode(BlenderMode.OBJECT) }
                } else {
                    IconAction(
                        AppIcons.sculpt("DRAW"), "Escultura",
                        selected = blender.mode == BlenderMode.SCULPT,
                        enabled = blender.sculpt.available && editable && blender.activeObjectType == "MESH",
                        onClick = { vm.setMode(BlenderMode.SCULPT) },
                    )
                }
                if (blender.features.cad.available) PillButton("CAD", selected = blender.cad.workspace) { vm.enterCad() }
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
        if (blender.mode == BlenderMode.EDIT && blender.activeObjectType == "MESH")
            PillButton("Camino", selected = state.shortestPathActive, onClick = vm::toggleShortestPath)
        androidx.compose.foundation.layout.Column(horizontalAlignment = Alignment.CenterHorizontally) {
            EditSelectionBar.actions.filter {
                when {
                    blender.cad.workspace -> it in setOf(ActionId.SELECT_ALL, ActionId.SELECT_INVERT, ActionId.TOOL_BOX, ActionId.TOOL_CIRCLE, ActionId.TOOL_PAINT_SELECT) &&
                        ((blender.cad.surface.mode == "PROFILE" && blender.cad.selectionSketch != null) || (it == ActionId.SELECT_ALL && hasSelection) ||
                         (it in setOf(ActionId.TOOL_BOX, ActionId.TOOL_CIRCLE, ActionId.TOOL_PAINT_SELECT) && blender.cad.surface.mode != "PROFILE"))
                    blender.mode == BlenderMode.OBJECT -> it in setOf(ActionId.SELECT_ALL, ActionId.SELECT_INVERT, ActionId.TOOL_BOX, ActionId.TOOL_CIRCLE, ActionId.TOOL_PAINT_SELECT)
                    blender.activeObjectType == "CURVE" -> it in setOf(ActionId.SELECT_ALL, ActionId.SELECT_INVERT, ActionId.TOOL_PAINT_SELECT)
                    else -> EditSelectionBar.enabled(it, blender.selectionMode, hasSelection)
                }
            }.forEach { id ->
                // Un único botón alterna Seleccionar todo / Deseleccionar.
                val shown = if (id == ActionId.SELECT_ALL && hasSelection) ActionId.DESELECT_ALL else id
                IconAction(
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
    IconAction(AppIcons.SelectTool, "Seleccionar", selected = state.shapeTool == ShapeTool.NONE &&
        (!state.blender.material.active || state.blender.material.interaction == "SELECT") && state.activeTool == ActiveTool.SELECT,
        onClick = vm::activateSelection)
    PillButton("＋ Añadir", selected = state.selectionOp == SelectionOp.TOGGLE, onClick = vm::toggleSelectionAdd)
}
