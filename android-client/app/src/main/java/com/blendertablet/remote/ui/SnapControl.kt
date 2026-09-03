package com.blendertablet.remote.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
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
import androidx.compose.ui.unit.dp
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
    if (options.isEmpty()) return
    var expanded by remember(options) { mutableStateOf(false) }
    Box(modifier) {
        PillButton("Snap: ${selected.label}", selected = selected != SnapType.NONE) {
            expanded = true
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            options.forEach { option ->
                DropdownMenuItem(
                    text = { Text(option.label) },
                    leadingIcon = {
                        Icon(
                            AppIcons.snap(option),
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

/** Opciones de Tweak derivadas por el mismo módulo que representa el snap. */
internal fun tweakSnapOptions(announced: List<SnapType>, motion: TweakMotion): List<SnapType> {
    val exact = SnapType.forMode(TransformMode.MOVE)
    val usable = if (motion == TweakMotion.SLIDE) exact.filterNot { it.geometric } else exact
    return usable.filter { it == SnapType.NONE || it in announced }
}

internal fun tweakSnapSteps(motion: TweakMotion): List<Pair<String, Double>> =
    if (motion == TweakMotion.SLIDE) {
        listOf("5%" to .05, "10%" to .1, "25%" to .25, "50%" to .5)
    } else {
        DistanceSnapSteps
    }
