package com.blendertablet.remote.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
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
    EditTool.LOOP_CUT -> listOf(
        ParamSpec("cuts", "Cortes", 1.0, true, TransformMode.SCALE),
        ParamSpec("smoothness", "Suavidad", 0.05, false, TransformMode.SCALE),
        ParamSpec("factor", "Factor", 0.05, false, TransformMode.SCALE),
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
 * Sin sesión no se dibuja nada: comparte el hueco de abajo con [TransformBar] y las
 * dos a la vez se solaparían.
 */
@Composable
fun EditToolTray(
    session: ToolSession,
    onParameter: (String, Double) -> Unit,
    onConfirm: () -> Unit,
    onCancel: () -> Unit,
    modifier: Modifier = Modifier,
) {
    if (!session.active) return
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
            for (spec in specsFor(session.tool)) {
                ParamStepper(
                    spec = spec,
                    value = session.parameters[spec.key] ?: defaultValue(spec),
                    onCommit = { onParameter(spec.key, it) },
                )
                Spacer(Modifier.height(4.dp))
            }
            Spacer(Modifier.height(2.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                RoundAction(Icons.Default.Close, "Descartar", Ink.Bad, onCancel)
                RoundAction(Icons.Default.Check, "Confirmar", Ink.Ok, onConfirm)
            }
        }
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
