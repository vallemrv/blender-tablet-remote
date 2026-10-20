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
    /** Valor del doble toque; null si la magnitud no tiene un neutro evidente. */
    neutral: Double? = null, onCommit: (Double) -> Unit,
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
    fun read() = if (draft == null) shown else com.blendertablet.remote.model.parseToolValue(draft!!, shown, mode, unit, scale)
    fun send(raw: Double) {
        if (!raw.isFinite()) return
        val next = (if(integer) kotlin.math.round(raw) else raw).coerceIn(min ?: -Double.MAX_VALUE, max ?: Double.MAX_VALUE)
        pending = next; draft = null; onCommit(next)
    }
    var base by remember { mutableStateOf(shown) }
    val text = if (integer) kotlin.math.round(display).toLong().toString()
        else formatToolDistance(display, 2)
    HoverHelp(label.ifBlank { "Valor" }, numberHelp(neutral != null)) {
        ScrubNumber(
            onScrubStart = { base = read() ?: shown },
            onScrub = { steps -> send(base + steps * step) },
            onReset = neutral?.let { { send(it) } },
        ) { field ->
            CompactNumericField(value = draft ?: text, onValueChange = { draft = it }, onDone = { read()?.let(::send) },
                modifier = field.width(if (label.length > 6) 128.dp else 104.dp), fontSize = 16.sp,
                selectAllOnFocus = true, textAlign = androidx.compose.ui.text.style.TextAlign.End,
                caption = label.takeIf { it.isNotBlank() }, suffix = unit?.short ?: if (mode ==
                    com.blendertablet.remote.model.TransformMode.ROTATE) "°" else null)
        }
    }
}

/** La misma frase para todos los números: así se aprende una vez. */
internal fun numberHelp(resettable: Boolean) =
    "Arrastra a izquierda o derecha para ajustarlo a pasos (también tras mantenerlo pulsado) · toca para escribir un valor exacto" +
        if (resettable) " · doble toque para restablecerlo" else ""
