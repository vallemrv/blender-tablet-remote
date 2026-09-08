package com.blendertablet.remote.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.Row
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.sp
import androidx.compose.ui.unit.dp
import com.blendertablet.remote.model.TransformStepUnit
import com.blendertablet.remote.model.LengthUnit
import com.blendertablet.remote.model.transformStepUnit
import com.blendertablet.remote.model.moveValueForDisplay
import com.blendertablet.remote.model.moveValueInBlenderUnits
import com.blendertablet.remote.model.SnapType
import com.blendertablet.remote.model.TransformMode
import com.blendertablet.remote.model.TweakMotion
import kotlin.math.abs

/**
 * Selector único de snap para cualquier bandeja.
 *
 * El consumidor solo declara qué tipos admite y recibe la elección. La apariencia,
 * el estado abierto y la lectura del valor seleccionado pertenecen a este componente.
 */
@Composable
fun SnapControl(
    options: List<SnapType>,
    selected: SnapType,
    onSelect: (SnapType) -> Unit,
    modifier: Modifier = Modifier,
) {
    SnapOptions(options, selected, selected != SnapType.NONE, { it.label }, AppIcons::snap, onSelect, modifier)
}

@Composable
internal fun KnifeSnapControl(enabled: Boolean, mode: String, onSelect: (String) -> Unit) {
    val options = listOf("NONE", "AUTO", "VERTEX", "EDGE_CENTER", "EDGE")
    SnapOptions(options, if (enabled) mode else "NONE", enabled,
        { if (it == "AUTO") "Auto" else SnapType.valueOf(it).label },
        { if (it == "AUTO") AppIcons.SnapAuto else AppIcons.snap(SnapType.valueOf(it)) }, onSelect)
}

@Composable
private fun <T> SnapOptions(
    options: List<T>, selected: T, active: Boolean,
    label: (T) -> String, icon: (T) -> ImageVector, onSelect: (T) -> Unit,
    modifier: Modifier = Modifier,
) {
    if (options.isEmpty()) return
    var expanded by remember(options) { mutableStateOf(false) }
    Box(modifier) {
        PillButton("Snap: ${label(selected)}", selected = active) {
            expanded = true
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            options.forEach { option ->
                DropdownMenuItem(
                    text = { Text(label(option)) },
                    leadingIcon = {
                        Icon(
                            icon(option),
                            null,
                            tint = if (option == selected) Ink.Accent else Ink.Muted,
                        )
                    },
                    trailingIcon = {
                        if (option == selected) Icon(Icons.Default.Check, null, tint = Ink.Accent)
                    },
                    onClick = {
                        expanded = false
                        onSelect(option)
                    },
                )
            }
        }
    }
}

/** Pasos del mismo sistema de snap; distancia y factor solo cambian sus presets. */
@Composable
fun SnapStepControl(
    selected: Double,
    presets: List<Pair<String, Double>>,
    onSelect: (Double) -> Unit,
) {
    Row(horizontalArrangement = Arrangement.spacedBy(3.dp)) {
        presets.forEach { (label, step) ->
            PillButton(label, selected = abs(selected - step) < 1e-9) { onSelect(step) }
        }
    }
}

val DistanceSnapSteps = listOf("1mm" to .001, "1cm" to .01, "10cm" to .1, "1m" to 1.0)
val FactorSnapSteps = listOf("1%" to .01, "5%" to .05, "10%" to .1, "25%" to .25)

/** Cantidad libre y unidad métrica; el consumidor recibe el paso en unidades Blender. */
@Composable
internal fun DistanceSnapStepInput(
    step: Double,
    unitScaleLength: Double,
    defaultUnit: LengthUnit,
    onNudge: ((Double) -> Unit)? = null,
    onChange: (Double) -> Unit,
) {
    var unit by remember(defaultUnit) { mutableStateOf(defaultUnit.transformStepUnit()) }
    var expanded by remember { mutableStateOf(false) }
    var text by remember(unit, unitScaleLength) { mutableStateOf<String?>(null) }
    val displayed = moveValueForDisplay(step, unit, unitScaleLength)
    fun commit(): Double? {
        if (text == null) return step
        val number = text?.trim()?.replace(',', '.')?.toDoubleOrNull()
            ?.takeIf { it.isFinite() && it > 0.0 } ?: return null
        val wire = moveValueInBlenderUnits(number, unit, unitScaleLength)
        onChange(wire)
        text = null
        return wire
    }
    Text("Paso", color = Ink.Faint, fontSize = 11.sp)
    if (onNudge != null) PillButton("−") { commit()?.let { onNudge(-it) } }
    CompactNumericField(
        value = text ?: displayed.toBigDecimal().stripTrailingZeros().toPlainString(),
        onValueChange = { text = it }, modifier = Modifier.width(84.dp),
        textAlign = TextAlign.End, placeholder = "Cantidad", onDone = { commit() },
    )
    Box {
        PillButton(unit.label) { expanded = true }
        DropdownMenu(expanded, { expanded = false }) {
            listOf(TransformStepUnit.MM, TransformStepUnit.CM, TransformStepUnit.M).forEach { option ->
                DropdownMenuItem(
                    text = { Text(option.label) },
                    onClick = { commit(); unit = option; expanded = false },
                )
            }
        }
    }
    if (onNudge != null) PillButton("+") { commit()?.let(onNudge) }
}

/** Opciones de Tweak derivadas por el mismo módulo que representa el snap. */
internal fun tweakSnapOptions(announced: List<SnapType>, motion: TweakMotion): List<SnapType> {
    val exact = SnapType.forMode(TransformMode.MOVE)
    val usable = if (motion == TweakMotion.SLIDE) exact.filterNot { it.geometric } else exact
    return usable.filter { it == SnapType.NONE || it in announced }
}

/** El paso comparte la unidad seleccionada para las dimensiones de Escalar. */
@Composable
internal fun ScaleStepInput(value: Double, unit: TransformStepUnit, onChange: (Double) -> Unit) {
    var text by remember(value, unit) { mutableStateOf("${formatScaleStep(value)} ${unit.label}") }
    fun commit() {
        text.replace(',', '.').trim().removeSuffix(unit.label).trim().toDoubleOrNull()
            ?.takeIf { it.isFinite() && it > 0.0 }?.let {
                text = "${formatScaleStep(it)} ${unit.label}"
                onChange(it)
            }
    }
    Text("Paso", color = Ink.Faint, fontSize = 11.sp)
    PillButton("−") { onChange((value - 1.0).coerceAtLeast(0.001)) }
    CompactNumericField(
        value = text, onValueChange = { text = it }, modifier = Modifier.width(84.dp),
        textAlign = TextAlign.End, placeholder = "Paso", onDone = { commit() },
    )
    PillButton("+") { onChange(value + 1.0) }
}

@Composable
internal fun ScaleUnitPicker(unit: TransformStepUnit, onSelect: (TransformStepUnit) -> Unit) {
    Box {
        var expanded by remember { mutableStateOf(false) }
        PillButton(unit.label) { expanded = true }
        DropdownMenu(expanded, { expanded = false }) {
            TransformStepUnit.entries.forEach { option ->
                DropdownMenuItem(
                    text = { Text(option.label) },
                    onClick = { onSelect(option); expanded = false },
                )
            }
        }
    }
}

private fun formatScaleStep(value: Double): String =
    value.toBigDecimal().stripTrailingZeros().toPlainString()
