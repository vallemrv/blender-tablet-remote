package com.blendertablet.remote.ui

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.blendertablet.remote.model.EditCatalogParameter
import com.blendertablet.remote.model.LengthUnit
import com.blendertablet.remote.model.TransformMode
import com.blendertablet.remote.model.NumericExpression
import com.blendertablet.remote.model.ValueParser
import java.util.Locale
import kotlin.math.round

/** Controles descritos por la herramienta: la bandeja comparte unidades y edición. */
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
                PillButton(if (labelled) spec.label else if (selected) "Activado" else "Desactivado", selected = selected) {
                    onParameter(spec.id, !selected)
                }
            } else if (spec.type == "enum") {
                var expanded by remember { mutableStateOf(false) }
                val current = (parameters[spec.id] ?: spec.default)?.toString().orEmpty()
                Box {
                    PillButton("${spec.labels[current] ?: current} ▾") { expanded = true }
                    DropdownMenu(expanded, onDismissRequest = { expanded = false }) {
                        spec.values.forEach { value ->
                            DropdownMenuItem(text = { Text(spec.labels[value] ?: value) },
                                onClick = { expanded = false; onParameter(spec.id, value) })
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
                    quickValues = if (spec.type == "int" && spec.id == "steps") listOf(8,16,32) else emptyList(),
                    onCommit = { onParameter(spec.id, if(spec.type == "int") it.toInt() else it) })
            }
        }
    }
}
