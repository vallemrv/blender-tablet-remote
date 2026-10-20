package com.blendertablet.remote.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.width
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.blendertablet.remote.model.EditCatalogParameter
import com.blendertablet.remote.model.Axis
import com.blendertablet.remote.model.Constraint
import com.blendertablet.remote.model.LengthUnit
import com.blendertablet.remote.model.TransformMode
import com.blendertablet.remote.model.NumericExpression
import com.blendertablet.remote.model.ValueParser
import java.util.Locale
import kotlin.math.round

/**
 * Controles descritos por la herramienta: números deslizables, ejes como trípode,
 * enums numéricos con su valor e interruptores con su dibujo. En «⋯ Más»
 * ([labelled] falso) el nombre lo pone la fila de la opción.
 */
@Composable
fun SchemaToolParameters(
    specs: List<EditCatalogParameter>,
    parameters: Map<String, Any?>,
    lengthUnit: LengthUnit,
    unitScaleLength: Double,
    onParameter: (String, Any?) -> Unit,
    modifier: Modifier = Modifier,
    labelled: Boolean = true,
) {
    Row(modifier, horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically) {
        for (spec in specs) key(spec.id) {
            if (spec.type == "bool") {
                val selected = (parameters[spec.id] ?: spec.default) as? Boolean ?: false
                val icon = AppIcons.trayToggle(if (spec.id == "merge") "merge_loop" else spec.id)
                if (icon != null) IconAction(icon, spec.label, selected = selected) { onParameter(spec.id, !selected) }
                else PillButton(if (selected) "Activado" else "Desactivado", selected = selected) { onParameter(spec.id, !selected) }
            } else if (spec.type == "enum") {
                val current = (parameters[spec.id] ?: spec.default)?.toString().orEmpty()
                val label = { value: String -> spec.labels[value] ?: value }
                when {
                    spec.values.isNotEmpty() && spec.values.all { it in setOf("X", "Y", "Z") } ->
                        AxisSelector(Constraint.entries.firstOrNull { it.name == current } ?: Constraint.FREE,
                            onSelect = { onParameter(spec.id, it.name) }, axes = spec.values.map { Axis.valueOf(it) },
                            allowFree = false)
                    spec.values.isNotEmpty() && spec.values.all { AppIcons.trayChoice(spec.id, it) != null } ->
                        ChoiceIcon(spec.values, current, spec.label, { AppIcons.trayChoice(spec.id, it)!! }, label, active = true) {
                            onParameter(spec.id, it)
                        }
                    else -> {
                        var expanded by remember { mutableStateOf(false) }
                        Box {
                            HoverHelp(spec.label, spec.help) { PillButton("${label(current)} ▾") { expanded = true } }
                            DropdownMenu(expanded, onDismissRequest = { expanded = false }) {
                                spec.values.forEach { value ->
                                    DropdownMenuItem(text = { Text(label(value)) },
                                        onClick = { expanded = false; onParameter(spec.id, value) })
                                }
                            }
                        }
                    }
                }
            } else if (spec.type == "float" || spec.type == "int") {
                val value = (parameters[spec.id] as? Number)?.toDouble() ?: (spec.default as? Number)?.toDouble() ?: 0.0
                val length = spec.unit == "length"
                val metres = when(lengthUnit) { LengthUnit.MILLIMETERS -> .001; LengthUnit.CENTIMETERS -> .01; else -> 1.0 }
                ToolNumericInput(if (labelled) spec.label else "", value, if (length) spec.step.takeIf { it > 0 } ?: metres / unitScaleLength else spec.step,
                    if (length) TransformMode.MOVE else if (spec.unit == "angle") TransformMode.ROTATE else TransformMode.SCALE,
                    unitScaleLength, if (length) lengthUnit else null, integer = spec.type == "int", min = spec.min, max = spec.max,
                    onCommit = { onParameter(spec.id, if(spec.type == "int") it.toInt() else it) })
            }
        }
    }
}
