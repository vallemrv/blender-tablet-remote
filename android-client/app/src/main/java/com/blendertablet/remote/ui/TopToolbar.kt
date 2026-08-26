package com.blendertablet.remote.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Redo
import androidx.compose.material.icons.automirrored.filled.Undo
import androidx.compose.material.icons.filled.CropSquare
import androidx.compose.material.icons.filled.Grid4x4
import androidx.compose.material.icons.filled.LinearScale
import androidx.compose.material.icons.filled.ScatterPlot
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
 * que salen del rail para quedarse aquí con iconos. En Edit Mode, en el
 * lado derecho de la misma barra, se muestran los submodos vértice/arista/cara
 * para cambiar de selección sin abrir nada. La selección por caja B y círculo C
 * vive en el long-click (RADIAL); armada, un chip sobre el viewport la señala y
 * la desarma.
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
    val inEdit = blender.mode == BlenderMode.EDIT

    Row(modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        FloatingPanel {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                if (blender.features.shading) {
                    IconAction(
                        Icons.Default.Grid4x4, "Wireframe",
                        selected = blender.view.shading == Shading.WIREFRAME,
                    ) { vm.toggleShading() }
                }
                PillButton("Mayús", selected = state.selectionOp == SelectionOp.TOGGLE) { vm.toggleSelectionOp(SelectionOp.TOGGLE) }
                PillButton("Ctrl", selected = state.selectionOp == SelectionOp.ADD) { vm.toggleSelectionOp(SelectionOp.ADD) }
                PillButton("Alt", selected = state.selectionOp == SelectionOp.REMOVE) { vm.toggleSelectionOp(SelectionOp.REMOVE) }
                IconAction(Icons.AutoMirrored.Filled.Undo, "Deshacer") { vm.undo() }
                IconAction(Icons.AutoMirrored.Filled.Redo, "Rehacer") { vm.redo() }
            }
        }

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
            IconAction(
                icon = if (chromeVisible) Icons.Default.VisibilityOff else Icons.Default.Visibility,
                description = if (chromeVisible) "Ocultar controles" else "Mostrar controles",
                onClick = onToggleChrome,
            )
        }
    }
}
