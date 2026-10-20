package com.blendertablet.remote.ui

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun QuickToolValues(values: List<Int>, selected: Double, onValue: (Double) -> Unit) {
    values.forEach { value -> PillButton(value.toString(), selected = selected == value.toDouble()) { onValue(value.toDouble()) } }
}

/** Exact numeric editing shared by fixed trays and backend-described tools. */
@Composable
fun ToolNumericInput(
    label: String, value: Double, step: Double, mode: com.blendertablet.remote.model.TransformMode,
    scale: Double, unit: com.blendertablet.remote.model.LengthUnit? = null,
    integer: Boolean = false, min: Double? = null, max: Double? = null,
    quickValues: List<Int> = emptyList(), onCommit: (Double) -> Unit,
) {
    var draft by remember(label, unit, scale) { mutableStateOf<String?>(null) }
    var pending by remember(label, unit, scale) { mutableStateOf<Double?>(null) }
    LaunchedEffect(value) { if (pending?.let { kotlin.math.abs(it-value)<1e-9 } == true) pending = null }
    val shown = pending ?: value
    val metres = when(unit) {
        com.blendertablet.remote.model.LengthUnit.MILLIMETERS -> .001
        com.blendertablet.remote.model.LengthUnit.CENTIMETERS -> .01
        else -> 1.0
    }
    val display = if (unit != null) shown * scale / metres else shown
    val suffix = unit?.let { " ${it.short}" }.orEmpty()
    fun read() = if (draft == null) shown else com.blendertablet.remote.model.parseToolValue(draft!!, shown, mode, unit, scale)
    fun send(raw: Double) {
        if (!raw.isFinite()) return
        val next = (if(integer) kotlin.math.round(raw) else raw).coerceIn(min ?: -Double.MAX_VALUE, max ?: Double.MAX_VALUE)
        pending = next; draft = null; onCommit(next)
    }
    val candidate = read()
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(label, color = Ink.Faint, fontSize = 11.sp, modifier = Modifier.padding(end = 4.dp))
        QuickToolValues(quickValues, shown, ::send)
        StepperButton("−", candidate != null && candidate > (min ?: -Double.MAX_VALUE)) { read()?.let { send(it-step) } }
        CompactNumericField(value = draft ?: (if(integer) kotlin.math.round(display).toLong().toString() else
            formatToolDistance(display, detailDecimalPlaces(display, 3))) + suffix,
            onValueChange = { draft = it }, onDone = { read()?.let(::send) },
            modifier = Modifier.width(78.dp), fontSize = 13.sp, selectAllOnFocus = true)
        StepperButton("+", candidate != null && candidate < (max ?: Double.MAX_VALUE)) { read()?.let { send(it+step) } }
    }
}
