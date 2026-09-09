package com.blendertablet.remote.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Redo
import androidx.compose.material.icons.automirrored.filled.Undo
import androidx.compose.material.icons.automirrored.filled.CallMerge
import androidx.compose.material.icons.filled.CropSquare
import androidx.compose.material.icons.filled.BlurOn
import androidx.compose.material.icons.filled.Brush
import androidx.compose.material.icons.filled.Grid4x4
import androidx.compose.material.icons.filled.LinearScale
import androidx.compose.material.icons.filled.ScatterPlot
import androidx.compose.material.icons.filled.Straighten
import androidx.compose.material.icons.filled.ViewInAr
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.blendertablet.remote.MainViewModel
import com.blendertablet.remote.model.AppUiState
import com.blendertablet.remote.model.BlenderMode
import com.blendertablet.remote.model.SelectionMode
import com.blendertablet.remote.model.SelectionOp
import com.blendertablet.remote.model.Shading

/**
 * Barra horizontal de tools, al lado del ojo (arriba a la derecha).
 *
 * Agrupa lo que se usa a cada toque sin abrir el rail: wireframe (toggle), los
 * modificadores Mayús/Ctrl/Alt (alternar/añadir/quitar de la selección) y undo/redo,
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
                    if (blender.features.shading) {
                        IconAction(
                            Icons.Default.Grid4x4, "Wireframe",
                            selected = blender.view.shading == Shading.WIREFRAME,
                        ) { vm.toggleShading() }
                    }
                    if (inEdit && blender.features.editSettings) {
                        IconAction(
                            Icons.Default.BlurOn, "Edición proporcional",
                            selected = blender.editSettings.proportional,
                        ) {
                            vm.toggleProportional()
                        }
                        IconAction(
                            Icons.AutoMirrored.Filled.CallMerge, "Auto Merge",
                            selected = blender.editSettings.autoMerge,
                        ) {
                            vm.toggleAutoMerge()
                        }
                    }
                    if (!blender.cad.workspace && blender.mode != BlenderMode.SCULPT) {
                    PillButton("Mayús", selected = state.selectionOp == SelectionOp.TOGGLE && !state.shortestPathActive) { vm.toggleSelectionOp(SelectionOp.TOGGLE) }
                    if (inEdit && blender.features.selectionShortestPath) {
                        PillButton("Ctrl", selected = state.shortestPathActive) { vm.toggleShortestPath() }
                    }
                    PillButton("Alt", selected = state.selectionOp == SelectionOp.REMOVE) { vm.toggleSelectionOp(SelectionOp.REMOVE) }
                    }
                    IconAction(Icons.AutoMirrored.Filled.Undo, "Deshacer") { vm.undo() }
                    IconAction(Icons.AutoMirrored.Filled.Redo, "Rehacer") { vm.redo() }
                    if (!blender.cad.workspace && blender.mode != BlenderMode.SCULPT && blender.features.repeatLast) {
                        PillButton("⇧R") { vm.repeatLast() }
                    }
                }
            }
        }

        FloatingPanel {
            IconAction(
                icon = if (chromeVisible) Icons.Default.VisibilityOff else Icons.Default.Visibility,
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
        if (inEdit) {
            FloatingPanel {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                    IconAction(
                        Icons.Default.ScatterPlot, "Vértices",
                        selected = blender.selectionMode == SelectionMode.VERTEX,
                    ) { vm.setSelectionMode(SelectionMode.VERTEX) }
                    IconAction(
                        Icons.Default.LinearScale, "Aristas",
                        selected = blender.selectionMode == SelectionMode.EDGE,
                    ) { vm.setSelectionMode(SelectionMode.EDGE) }
                    IconAction(
                        Icons.Default.CropSquare, "Caras",
                        selected = blender.selectionMode == SelectionMode.FACE,
                    ) { vm.setSelectionMode(SelectionMode.FACE) }
                }
            }
        }
        FloatingPanel {
            Row(horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                IconAction(
                    Icons.Default.ViewInAr, "Object Mode",
                    selected = blender.mode == BlenderMode.OBJECT && !blender.cad.workspace,
                ) { vm.setMode(BlenderMode.OBJECT) }
                IconAction(
                    Icons.Default.Straighten, "Edit Mode",
                    selected = inEdit,
                    enabled = editable,
                ) { vm.setMode(BlenderMode.EDIT) }
                if (blender.features.cad.available) PillButton("CAD", selected = blender.cad.workspace) { vm.enterCad() }
                IconAction(
                    AppIcons.sculpt("DRAW"), "Escultura",
                    selected = blender.mode == BlenderMode.SCULPT,
                    enabled = blender.sculpt.available && editable && blender.activeObjectType == "MESH",
                    onClick = { vm.setMode(BlenderMode.SCULPT) },
                )
            }
        }
    }
}
