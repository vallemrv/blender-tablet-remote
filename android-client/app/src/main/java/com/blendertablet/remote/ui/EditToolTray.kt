package com.blendertablet.remote.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.blendertablet.remote.model.EditTool
import com.blendertablet.remote.model.LoopFalloff
import com.blendertablet.remote.model.ToolSession
import com.blendertablet.remote.model.ValueParser
import com.blendertablet.remote.model.TransformMode
import kotlin.math.roundToInt

/** Descripción de un parámetro editable de una herramienta paramétrica. */
private data class ParamSpec(
    val key: String,
    val label: String,
    val step: Double,
    val isInt: Boolean,
    /** Unidades que entiende el parser del valor exacto. */
    val mode: TransformMode,
)

private fun specsFor(tool: EditTool): List<ParamSpec> = when (tool) {
    EditTool.EXTRUDE -> listOf(ParamSpec("offset", "Distancia", 0.01, false, TransformMode.MOVE))
    EditTool.BEVEL -> listOf(
        ParamSpec("offset", "Ancho", 0.01, false, TransformMode.MOVE),
        ParamSpec("segments", "Segmentos", 1.0, true, TransformMode.SCALE),
    )
    EditTool.INSET -> listOf(
        ParamSpec("thickness", "Grosor", 0.01, false, TransformMode.MOVE),
        ParamSpec("depth", "Profundidad", 0.01, false, TransformMode.MOVE),
    )
    EditTool.SUBDIVIDE -> listOf(ParamSpec("cuts", "Cortes", 1.0, true, TransformMode.SCALE))
    // Loop Cut tiene su propia bandeja (slider de posición, falloff y toggles del
    // modal); aquí solo los steppers que comparte con el resto.
    EditTool.LOOP_CUT -> listOf(
        ParamSpec("cuts", "Cortes", 1.0, true, TransformMode.SCALE),
        ParamSpec("smoothness", "Suavidad", 0.05, false, TransformMode.SCALE),
    )
}

private fun defaultValue(spec: ParamSpec): Double = if (spec.isInt) 1.0 else 0.0

/**
 * Bandeja de la herramienta paramétrica de Edit Mode.
 *
 * El rail eligió la herramienta y abrió la sesión `tool.*`; aquí se ajustan sus
 * parámetros y se confirma o descarta. Cada cambio reconstruye el preview desde la
 * copia BMesh inicial, así que cancelar devuelve la topología exacta.
 *
 * Loop Cut añade el flujo táctil del Ctrl+R: un slider de posición, el perfil
 * (falloff) y los toggles del modal (uniforme/invertir/fijar), todos como botones
 * porque no hay teclado. Con `awaitingPick` (herramienta armada, sin sesión) se
 * muestra el hint de tocar la malla en vez de los parámetros.
 *
 * Sin sesión ni hint no se dibuja nada: comparte el hueco de abajo con [TransformBar]
 * y las dos a la vez se solaparían.
 */
@Composable
fun EditToolTray(
    session: ToolSession,
    onParameter: (String, Any?) -> Unit,
    onConfirm: () -> Unit,
    onCancel: () -> Unit,
    modifier: Modifier = Modifier,
    awaitingPick: Boolean = false,
) {
    if (!session.active && !awaitingPick) return
    FloatingPanel(modifier) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            // Rótulo, no botón: la herramienta ya la eligió el rail y volver a
            // ofrecerla aquí sería la duplicidad que el plan prohíbe.
            Text(
                session.tool.label.uppercase(),
                color = Ink.Accent,
                fontSize = 11.sp,
                fontWeight = FontWeight.SemiBold,
            )
            Spacer(Modifier.height(6.dp))

            if (!session.active) {
                Text(
                    "Toca una arista de la malla para colocar el corte",
                    color = Ink.Muted,
                    fontSize = 12.sp,
                    textAlign = TextAlign.Center,
                    modifier = Modifier.padding(horizontal = 8.dp),
                )
                Spacer(Modifier.height(6.dp))
                RoundAction(Icons.Default.Close, "Cancelar", Ink.Bad, onCancel)
                return@Column
            }

            if (session.tool == EditTool.LOOP_CUT) {
                LoopCutControls(session, onParameter)
            } else {
                for (spec in specsFor(session.tool)) {
                    ParamStepper(
                        spec = spec,
                        value = session.double(spec.key) ?: defaultValue(spec),
                        onCommit = { onParameter(spec.key, it) },
                    )
                    Spacer(Modifier.height(4.dp))
                }
            }
            Spacer(Modifier.height(2.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                RoundAction(Icons.Default.Close, "Descartar", Ink.Bad, onCancel)
                RoundAction(Icons.Default.Check, "Confirmar", Ink.Ok, onConfirm)
            }
        }
    }
}

/** Parámetros propios de Loop Cut: posición, cortes, suavidad, perfil y toggles. */
@Composable
private fun LoopCutControls(session: ToolSession, onParameter: (String, Any?) -> Unit) {
    PositionSlider(session.double("factor") ?: 0.0, onParameter)

    Spacer(Modifier.height(2.dp))
    for (spec in specsFor(EditTool.LOOP_CUT)) {
        ParamStepper(
            spec = spec,
            value = session.double(spec.key) ?: defaultValue(spec),
            onCommit = { onParameter(spec.key, it) },
        )
        Spacer(Modifier.height(4.dp))
    }

    val falloff = session.falloff()
    PillButton(
        label = "Perfil: ${falloff.label}",
        modifier = Modifier.fillMaxWidth(),
        onClick = { onParameter("falloff", falloff.next().wire) },
    )
    Spacer(Modifier.height(4.dp))

    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        PillButton("Uniforme", selected = session.flag("even"), onClick = {
            onParameter("even", !session.flag("even"))
        })
        PillButton("Invertir", selected = session.flag("flip"), onClick = {
            onParameter("flip", !session.flag("flip"))
        })
        PillButton("Fijar", selected = session.flag("clamp", true), onClick = {
            onParameter("clamp", !session.flag("clamp", true))
        })
    }
}

/**
 * Posición del corte a lo largo del anillo (0%..100%), equivalente al factor del
 * modal: 0% = extremo inicial, 50% = centro, 100% = extremo final.
 *
 * El arrastre se manda vivo pero con un ritmo limitado (el servidor reconstruye el
 * preview entero en cada cambio), y al soltar se confirma el valor final.
 */
@Composable
private fun PositionSlider(factor: Double, onParameter: (String, Any?) -> Unit) {
    var dragging by remember { mutableStateOf(false) }
    var local by remember { mutableFloatStateOf(((factor + 1.0) / 2.0).toFloat().coerceIn(0f, 1f)) }
    var lastSent by remember { mutableLongStateOf(0L) }
    val shown = if (dragging) local else ((factor + 1.0) / 2.0).toFloat().coerceIn(0f, 1f)

    Row(verticalAlignment = Alignment.CenterVertically) {
        Text("Posición", color = Ink.Faint, fontSize = 11.sp, modifier = Modifier.padding(end = 6.dp))
        Slider(
            value = shown,
            onValueChange = { value ->
                local = value
                dragging = true
                val now = System.currentTimeMillis()
                if (now - lastSent >= 100L) {
                    lastSent = now
                    onParameter("factor", (value * 2.0 - 1.0).toDouble())
                }
            },
            onValueChangeFinished = {
                onParameter("factor", (local * 2.0 - 1.0).toDouble())
                dragging = false
            },
            colors = SliderDefaults.colors(
                thumbColor = Ink.Accent,
                activeTrackColor = Ink.Accent,
                inactiveTrackColor = Ink.Divider,
            ),
            modifier = Modifier.weight(1f),
        )
        Text(
            "${(shown * 100).roundToInt()}%",
            color = Ink.OnPanel,
            fontSize = 12.sp,
            textAlign = TextAlign.End,
            modifier = Modifier.width(40.dp),
        )
    }
}

/** Un parámetro con steppers (−/+) y valor exacto editable en el centro. */
@Composable
private fun ParamStepper(spec: ParamSpec, value: Double, onCommit: (Double) -> Unit) {
    var text by remember { mutableStateOf("") }
    val formatted = format(value, spec.isInt)

    fun commit() {
        val parsed = ValueParser.parse(text, spec.mode) ?: return
        val next = if (spec.isInt) maxOf(1.0, parsed.roundToInt().toDouble()) else parsed
        onCommit(next)
        text = ""
    }

    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(spec.label, color = Ink.Faint, fontSize = 11.sp, modifier = Modifier.padding(end = 6.dp))
        StepperButton("−") {
            val next = if (spec.isInt) maxOf(1.0, value - spec.step) else value - spec.step
            onCommit(next)
        }
        TextField(
            value = if (text.isEmpty()) formatted else text,
            onValueChange = { text = it },
            singleLine = true,
            textStyle = TextStyle(fontSize = 13.sp, textAlign = TextAlign.Center),
            colors = TextFieldDefaults.colors(
                focusedContainerColor = Color.Transparent,
                unfocusedContainerColor = Color.Transparent,
                focusedTextColor = Ink.OnPanel,
                unfocusedTextColor = Ink.Muted,
            ),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number, imeAction = ImeAction.Done),
            keyboardActions = KeyboardActions(onDone = { commit() }),
            modifier = Modifier.width(72.dp),
        )
        StepperButton("+") {
            val next = if (spec.isInt) maxOf(1.0, value + spec.step) else value + spec.step
            onCommit(next)
        }
    }
}

private fun format(value: Double, isInt: Boolean): String =
    if (isInt) value.roundToInt().toString() else {
        val rounded = (value * 1000).roundToInt() / 1000.0
        if (rounded == 0.0) "0" else rounded.toString()
    }
