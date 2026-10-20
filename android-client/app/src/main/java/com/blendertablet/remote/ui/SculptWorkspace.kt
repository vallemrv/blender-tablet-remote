package com.blendertablet.remote.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.onSizeChanged
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
fun BoxScope.SculptWorkspace(state: AppUiState, vm: MainViewModel, onTrayHeight: (Int) -> Unit = {}) {
    val sculpt = state.blender.sculpt
    var topologyOpen by rememberSaveable { mutableStateOf(false) }
    val railHeight = (LocalConfiguration.current.screenHeightDp - 220).coerceAtLeast(88).dp
    ToolRail(Modifier.align(Alignment.CenterStart).padding(start = Metrics.EdgeMargin).heightIn(max = railHeight)) {
        RailLabel("PINCEL")
        sculpt.brushes.forEach { brush ->
            IconAction(AppIcons.sculpt(brush.icon), brush.label, selected = sculpt.brush == brush.id,
                enabled = sculpt.active) { vm.sculptSettings(mapOf("brush" to brush.id)) }
        }
    }
    val unit = state.blender.sceneScale.lengthUnit
    // Radio relativo a la altura del vídeo; se lee como medida aproximada si se conoce.
    val metresPerFraction = sculpt.radiusMeters?.takeIf { sculpt.radius > 0f }?.let { it / sculpt.radius }
    fun radiusText(fraction: Double): String = metresPerFraction?.let { perFraction ->
        val value = moveValueForDisplay(perFraction * fraction, unit.transformStepUnit(), 1.0)
        formatToolDistance(value, MaxDecimals)
    } ?: formatToolDistance(fraction * 100, 1)
    fun radiusFromText(text: String, fraction: Double): Double? {
        val number = com.blendertablet.remote.model.NumericExpression.evaluate(text,
            radiusText(fraction).toDoubleOrNull() ?: 0.0) ?: return null
        return metresPerFraction?.let { number * unit.transformStepUnit().meters / it } ?: (number / 100)
    }
    val more = TrayMore(
        precision = {
            TrayOption("Presión", "Qué modula la presión del lápiz: la fuerza, el radio o ambos.") {
                PillButton("Fuerza", selected = sculpt.pressureStrength) { vm.sculptSettings(mapOf("pressure_strength" to !sculpt.pressureStrength)) }
                PillButton("Radio", selected = sculpt.pressureSize) { vm.sculptSettings(mapOf("pressure_size" to !sculpt.pressureSize)) }
            }
            TrayOption("Solo lápiz", "Con Solo lápiz el dedo orbita; si no, el dedo también esculpe.") {
                IconAction(AppIcons.material("STYLUS"), "Solo lápiz", selected = state.sculptStylusOnly,
                    onClick = vm::toggleSculptStylusOnly)
            }
        },
        reference = {
            TrayOption("Simetría", "Repite el trazo al otro lado de cada eje elegido.") {
                listOf("x" to sculpt.symmetryX, "y" to sculpt.symmetryY, "z" to sculpt.symmetryZ).forEach { (axis, enabled) ->
                    PillButton(axis.uppercase(), selected = enabled) {
                        vm.sculptSettings(mapOf("symmetry" to mapOf(axis to !enabled)))
                    }
                }
            }
        },
        shape = {
            if (sculpt.dyntopoEnabled) TrayOption("Dyntopo", "Tamaño de los triángulos que crea el pincel.") { SculptDyntopoDetail(sculpt, vm) }
            else if (sculpt.multiresName != null) TrayOption("Multires", "Nivel de subdivisión en el que se esculpe.") { SculptMultiresLevels(sculpt, vm) }
            TrayOption("Detalle de la malla", "Dyntopo, Multires y máscaras.") {
                IconAction(AppIcons.sculpt("TOPOLOGY"), "Detalle de la malla", selected = topologyOpen) { topologyOpen = true }
            }
        },
    )
    SingleLineTray(sculpt.brushes.firstOrNull { it.id == sculpt.brush }?.label ?: "Escultura", more = more,
        hintKey = "sculpt",
        help = if (state.sculptStylusOnly) "Lápiz esculpe · dedo orbita · dos dedos desplazan y acercan · botón del lápiz suaviza"
            else "Lápiz o dedo esculpen · dos dedos desplazan y acercan · el control derecho orbita",
        modifier = Modifier.align(Alignment.BottomCenter).fillMaxWidth().onSizeChanged { onTrayHeight(it.height) }
            .padding(Metrics.EdgeMargin)) {
        TrayNumber("Radio", sculpt.radius.toDouble(), .005, .005, .2, ::radiusText, ::radiusFromText,
            onValue = { vm.sculptSettings(mapOf("radius" to it.toFloat())) },
            suffix = if (metresPerFraction != null) unit.short else "%", width = 136.dp,
            help = "Radio del pincel · relativo a la altura del vídeo")
        TrayNumber("Fuerza", sculpt.strength.toDouble(), .01, 0.0, 1.0, { formatToolDistance(it * 100, 0) },
            { text, current -> com.blendertablet.remote.model.NumericExpression.evaluate(text, current * 100)?.div(100) },
            onValue = { vm.sculptSettings(mapOf("strength" to it.toFloat())) }, suffix = "%", neutral = .5)
        IconAction(AppIcons.SculptSmooth, "Suavizar", selected = state.sculptSmooth, onClick = vm::toggleSculptSmooth)
        IconAction(AppIcons.SculptInvert, "Invertir", selected = state.sculptInvert, onClick = vm::toggleSculptInvert)
    }
    if (topologyOpen) SculptTopologyDialog(sculpt, vm) { topologyOpen = false }
}

@Composable
private fun SculptDyntopoDetail(sculpt: SculptState, vm: MainViewModel) {
    TrayNumber("Detalle", sculpt.dyntopoDetail.toDouble(), 1.0, 1.0, 40.0, { formatToolDistance(it, 0) },
        { text, current -> com.blendertablet.remote.model.NumericExpression.evaluate(text, current) },
        onValue = { vm.sculptCommand("sculpt.dyntopo", mapOf("detail" to it.toFloat())) }, suffix = "px")
}

@Composable
private fun SculptMultiresLevels(sculpt: SculptState, vm: MainViewModel) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        TrayNumber("Nivel", sculpt.multiresLevel.toDouble(), 1.0, 0.0, sculpt.multiresTotalLevels.coerceAtLeast(0).toDouble(),
            { kotlin.math.round(it).toInt().toString() },
            { text, current -> com.blendertablet.remote.model.NumericExpression.evaluate(text, current)?.let { kotlin.math.round(it) } },
            onValue = { vm.sculptCommand("sculpt.multires", mapOf("action" to "level", "level" to kotlin.math.round(it).toInt())) },
            suffix = "/ ${sculpt.multiresTotalLevels}", enabled = sculpt.active && sculpt.multiresTotalLevels > 0)
        PillButton("Subdividir", enabled = sculpt.active && !sculpt.dyntopoEnabled && sculpt.multiresTotalLevels < 6) {
            vm.sculptCommand("sculpt.multires", mapOf("action" to "subdivide"))
        }
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
                SculptDyntopoDetail(sculpt, vm)
                Text("Multires conserva niveles de subdivisión para trabajar desde la forma general hasta el detalle.", fontSize = 13.sp)
                if (sculpt.multiresName == null) {
                    PillButton("Añadir Multires", enabled = !sculpt.dyntopoEnabled) {
                        vm.sculptCommand("sculpt.multires", mapOf("action" to "add"))
                    }
                } else {
                    SculptMultiresLevels(sculpt, vm)
                }
                if (sculpt.dyntopoEnabled || sculpt.multiresName != null)
                    Text("Dyntopo y Multires se usan por separado. Para quitar Multires, vuelve a Object → Modificadores.", color = Ink.Muted, fontSize = 11.sp)
                Text("Máscara · protege las zonas pintadas", fontSize = 13.sp)
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    PillButton("Invertir máscara") { vm.sculptCommand("sculpt.mask", mapOf("action" to "invert")) }
                    PillButton("Borrar máscara") { vm.sculptCommand("sculpt.mask", mapOf("action" to "clear")) }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("Listo") } },
    )
}
