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
import com.blendertablet.remote.model.ValueParser
import java.util.Locale

/** Controles descritos por la herramienta: la bandeja comparte unidades y edición. */
@Composable
fun SchemaToolParameters(
    specs: List<EditCatalogParameter>,
    parameters: Map<String, Any?>,
    lengthUnit: LengthUnit,
    unitScaleLength: Double,
    onParameter: (String, Any?) -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically) {
        for (spec in specs) key(spec.id) {
            if (spec.type == "bool") {
                val selected = (parameters[spec.id] ?: spec.default) as? Boolean ?: false
                PillButton(spec.label, selected = selected) { onParameter(spec.id, !selected) }
            } else if (spec.type == "enum") {
                var expanded by remember { mutableStateOf(false) }
                val current = (parameters[spec.id] ?: spec.default)?.toString().orEmpty()
                Box {
                    PillButton("${spec.label}: ${spec.labels[current] ?: current}") { expanded = true }
                    DropdownMenu(expanded, onDismissRequest = { expanded = false }) {
                        spec.values.forEach { value ->
                            DropdownMenuItem(text = { Text(spec.labels[value] ?: value) },
                                onClick = { expanded = false; onParameter(spec.id, value) })
                        }
                    }
                }
            } else if (spec.type == "float") {
                val value = (parameters[spec.id] as? Number)?.toDouble() ?: 0.0
                val length = spec.unit == "length"
                val metresPerUnit = when (lengthUnit) {
                    LengthUnit.MILLIMETERS -> 0.001
                    LengthUnit.CENTIMETERS -> 0.01
                    LengthUnit.METERS -> 1.0
                }
                val conversion = if (length) unitScaleLength / metresPerUnit else 1.0
                var draft by remember(value, conversion) { mutableStateOf<String?>(null) }
                fun set(wire: Double) {
                    if (!wire.isFinite()) return
                    onParameter(spec.id, wire.coerceIn(spec.min ?: -Double.MAX_VALUE, spec.max ?: Double.MAX_VALUE))
                    draft = null
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(spec.label, color = Ink.Muted, fontSize = 11.sp)
                    // En longitudes, cada botón recorre una unidad visible del preset.
                    val step = if (length) 1.0 / conversion else spec.step
                    StepperButton("−") { set(value - step) }
                    CompactNumericField(
                        value = draft ?: String.format(Locale.ROOT, "%.3f", value * conversion).trimEnd('0').trimEnd('.'),
                        onValueChange = { draft = it },
                        onDone = {
                            val text = draft.orEmpty().trim().replace(',', '.')
                            val scalar = text.toDoubleOrNull()
                            val parsed = if (scalar != null) scalar / conversion else if (length)
                                ValueParser.parse(text, TransformMode.MOVE)?.div(unitScaleLength) else null
                            parsed?.let(::set)
                        },
                        modifier = Modifier.width(64.dp),
                    )
                    StepperButton("+") { set(value + step) }
                    if (length) Text(lengthUnit.short, color = Ink.Muted, fontSize = 11.sp)
                }
            }
        }
    }
}
