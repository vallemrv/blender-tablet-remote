package com.blendertablet.remote.ui

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.blendertablet.remote.MainViewModel
import com.blendertablet.remote.model.AppUiState
import com.blendertablet.remote.model.SculptState
import com.blendertablet.remote.model.transformStepUnit
import com.blendertablet.remote.model.moveValueForDisplay
import kotlin.math.roundToInt

/** The brush rail stays open; density operations live behind one explicit button. */
@Composable
fun BoxScope.SculptWorkspace(state: AppUiState, vm: MainViewModel) {
    val sculpt = state.blender.sculpt
    var topologyOpen by rememberSaveable { mutableStateOf(false) }
    var maskActionsOpen by remember { mutableStateOf(false) }
    LaunchedEffect(sculpt.active, sculpt.brush) { maskActionsOpen = false }
    val railHeight = (LocalConfiguration.current.screenHeightDp - 220).coerceAtLeast(88).dp
    ToolRail(Modifier.align(Alignment.CenterStart).padding(start = Metrics.EdgeMargin).heightIn(max = railHeight)) {
        RailLabel("PINCEL")
        sculpt.brushes.forEach { brush ->
            val activeMask = sculpt.active && brush.id == "MASK" && sculpt.brush == "MASK"
            Box {
                IconAction(AppIcons.sculpt(brush.icon), brush.label, selected = sculpt.brush == brush.id,
                    enabled = sculpt.active,
                    onLongClick = if (activeMask) ({ maskActionsOpen = true }) else null,
                    onLongClickLabel = "Acciones de máscara",
                ) { vm.sculptSettings(mapOf("brush" to brush.id)) }
                if (activeMask) DropdownMenu(expanded = maskActionsOpen, onDismissRequest = { maskActionsOpen = false }) {
                    DropdownMenuItem(text = { Text("Invertir máscara") }, onClick = {
                        maskActionsOpen = false
                        vm.sculptCommand("sculpt.mask", mapOf("action" to "invert"))
                    })
                    DropdownMenuItem(text = { Text("Borrar toda la máscara") }, onClick = {
                        maskActionsOpen = false
                        vm.sculptCommand("sculpt.mask", mapOf("action" to "clear"))
                    })
                }
            }
        }
    }
    FloatingPanel(Modifier.align(Alignment.BottomCenter).fillMaxWidth().padding(Metrics.EdgeMargin)) {
        Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Row(Modifier.horizontalScroll(rememberScrollState()), verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(sculpt.brushes.firstOrNull { it.id == sculpt.brush }?.label ?: "Escultura", color = Ink.Accent, fontSize = 13.sp)
                SculptSlider("Radio", sculpt.radius, .005f.. .2f, { fraction ->
                    sculpt.radiusMeters?.let { meters ->
                        val unit = state.blender.sceneScale.lengthUnit
                        val value = moveValueForDisplay(meters * fraction / sculpt.radius,
                            unit.transformStepUnit(), 1.0)
                        val decimals = (2 - kotlin.math.floor(kotlin.math.log10(value)).toInt()).coerceIn(2, 12)
                        "≈ ${formatToolDistance(value, decimals)} ${unit.short}"
                    } ?: "${(fraction * 100).roundToInt()} % de pantalla"
                }) {
                    vm.sculptSettings(mapOf("radius" to it))
                }
                SculptSlider("Fuerza", sculpt.strength, 0f..1f, { "${(it * 100).roundToInt()} %" }) {
                    vm.sculptSettings(mapOf("strength" to it))
                }
                PillButton("Suavizar", selected = state.sculptSmooth, onClick = vm::toggleSculptSmooth)
                PillButton("Invertir", selected = state.sculptInvert, onClick = vm::toggleSculptInvert)
                PillButton("Malla", selected = topologyOpen) { topologyOpen = true }
            }
            Row(Modifier.horizontalScroll(rememberScrollState()), verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                Text("Presión", color = Ink.Muted, fontSize = 11.sp)
                PillButton("Fuerza", selected = sculpt.pressureStrength) { vm.sculptSettings(mapOf("pressure_strength" to !sculpt.pressureStrength)) }
                PillButton("Radio", selected = sculpt.pressureSize) { vm.sculptSettings(mapOf("pressure_size" to !sculpt.pressureSize)) }
                Text("Simetría", color = Ink.Muted, fontSize = 11.sp, modifier = Modifier.padding(start = 8.dp))
                listOf("x" to sculpt.symmetryX, "y" to sculpt.symmetryY, "z" to sculpt.symmetryZ).forEach { (axis, enabled) ->
                    PillButton(axis.uppercase(), selected = enabled) {
                        vm.sculptSettings(mapOf("symmetry" to mapOf(axis to !enabled)))
                    }
                }
                PillButton(if (state.sculptStylusOnly) "Solo lápiz" else "Lápiz + dedo", selected = state.sculptStylusOnly,
                    onClick = vm::toggleSculptStylusOnly)
                Text(if (state.sculptStylusOnly) "Dedo: orbitar · 2 dedos: desplazar/zoom · botón lápiz: suavizar" else "2 dedos: desplazar/zoom · órbita: control derecho",
                    color = Ink.Faint, fontSize = 10.sp)
            }
        }
    }
    if (topologyOpen) SculptTopologyDialog(sculpt, vm) { topologyOpen = false }
}

@Composable
private fun SculptSlider(label: String, remote: Float, range: ClosedFloatingPointRange<Float>, format: (Float) -> String,
    onValue: (Float) -> Unit) {
    var value by remember { mutableFloatStateOf(remote.coerceIn(range)) }
    var dragging by remember { mutableStateOf(false) }
    LaunchedEffect(remote) { if (!dragging) value = remote.coerceIn(range) }
    Column(Modifier.width(160.dp)) {
        Text("$label · ${format(value)}", color = Ink.Muted, fontSize = 11.sp)
        Slider(value, onValueChange = { dragging = true; value = it }, valueRange = range,
            onValueChangeFinished = { dragging = false; onValue(value) }, modifier = Modifier.height(32.dp))
    }
}

@Composable
private fun SculptTopologyDialog(sculpt: SculptState, vm: MainViewModel, onDismiss: () -> Unit) {
    AlertDialog(onDismissRequest = onDismiss,
        title = { Text("Detalle de la malla") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Text("Dyntopo añade geometría mientras esculpes. Un detalle menor crea triángulos más pequeños. Puede perder UVs y otros atributos de la malla.", fontSize = 13.sp)
                PillButton(if (sculpt.dyntopoEnabled) "Desactivar Dyntopo" else "Activar Dyntopo",
                    selected = sculpt.dyntopoEnabled, enabled = sculpt.multiresName == null) {
                    vm.sculptCommand("sculpt.dyntopo", mapOf("enabled" to !sculpt.dyntopoEnabled, "detail" to sculpt.dyntopoDetail))
                }
                SculptSlider("Detalle", sculpt.dyntopoDetail, 1f..40f, { "${it.roundToInt()} px" }) {
                    vm.sculptCommand("sculpt.dyntopo", mapOf("detail" to it))
                }
                Text("Multires conserva niveles de subdivisión para trabajar desde la forma general hasta el detalle.", fontSize = 13.sp)
                if (sculpt.multiresName == null) {
                    PillButton("Añadir Multires", enabled = !sculpt.dyntopoEnabled) {
                        vm.sculptCommand("sculpt.multires", mapOf("action" to "add"))
                    }
                } else {
                    Text("Nivel ${sculpt.multiresLevel} de ${sculpt.multiresTotalLevels}", color = Ink.Accent)
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        PillButton("−", repeatOnHold = true, enabled = sculpt.multiresLevel > 0) {
                            vm.sculptCommand("sculpt.multires", mapOf("action" to "level", "level" to sculpt.multiresLevel - 1))
                        }
                        PillButton("+", repeatOnHold = true, enabled = sculpt.multiresLevel < sculpt.multiresTotalLevels) {
                            vm.sculptCommand("sculpt.multires", mapOf("action" to "level", "level" to sculpt.multiresLevel + 1))
                        }
                        PillButton("Subdividir", enabled = !sculpt.dyntopoEnabled) {
                            vm.sculptCommand("sculpt.multires", mapOf("action" to "subdivide"))
                        }
                    }
                }
                if (sculpt.dyntopoEnabled || sculpt.multiresName != null)
                    Text("Dyntopo y Multires se usan por separado. Para quitar Multires, vuelve a Object → Modificadores.", color = Ink.Muted, fontSize = 11.sp)
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("Listo") } },
    )
}
