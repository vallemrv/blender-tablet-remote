package com.blendertablet.remote.ui

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
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
    // Loop Cut: la posición es un stepper propio (porcentaje) y añade falloff y
    // toggles del modal; aquí solo los steppers numéricos que comparte con el resto.
    EditTool.LOOP_CUT -> listOf(
        ParamSpec("cuts", "Cortes", 1.0, true, TransformMode.SCALE),
        ParamSpec("smoothness", "Suavidad", 0.05, false, TransformMode.SCALE),
    )
    EditTool.BRIDGE_EDGE_LOOPS -> listOf(
        ParamSpec("twist_offset", "Desfase", 1.0, true, TransformMode.SCALE),
        ParamSpec("merge_factor", "Fusión", 0.05, false, TransformMode.SCALE),
    )
    EditTool.KNIFE -> emptyList()
}

private fun defaultValue(spec: ParamSpec): Double = if (spec.isInt) 1.0 else 0.0

/**
 * Bandeja de la herramienta paramétrica de Edit Mode, en una franja horizontal.
 *
 * Antes era una columna que apilaba los parámetros y tapaba el viewport; ahora es una
 * sola línea: el rótulo a la izquierda, los parámetros en una fila desplazable y las
 * dos salidas (descartar/confirmar) fijas a la derecha. Loop Cut coloca la posición
 * con un stepper numérico (porcentaje) y el lápiz puede seguir deslizándola sobre el
 * viewport, que ya alimenta `tool.nudge`; cortes, suavidad, perfil y toggles viven en
 * la misma línea.
 *
 * Con `awaitingPick` (herramienta armada, sin sesión) se muestra el hint de tocar la
 * malla en vez de los parámetros. Sin sesión ni hint no se dibuja nada: comparte el
 * hueco de abajo con [TransformBar] y las dos a la vez se solaparían.
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
    // El Knife tiene su propia bandeja (puntos, pop, cerrar, snap).
    if (session.tool == EditTool.KNIFE) return
    FloatingPanel(modifier) {
        if (!session.active) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    "Toca una arista de la malla para colocar el corte",
                    color = Ink.Muted,
                    fontSize = 12.sp,
                    modifier = Modifier.padding(horizontal = 8.dp),
                )
                Spacer(Modifier.width(8.dp))
                RoundAction(Icons.Default.Close, "Cancelar", Ink.Bad, onCancel)
            }
            return@FloatingPanel
        }

        Row(verticalAlignment = Alignment.CenterVertically) {
            // Rótulo, no botón: la herramienta ya la eligió el rail y volver a
            // ofrecerla aquí sería la duplicidad que el plan prohíbe.
            Text(
                session.tool.label.uppercase(),
                color = Ink.Accent,
                fontSize = 11.sp,
                fontWeight = FontWeight.SemiBold,
            )
            Spacer(Modifier.width(10.dp))
            Row(
                modifier = Modifier.weight(1f).horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                if (session.tool == EditTool.LOOP_CUT) {
                    LoopCutParams(session, onParameter)
                } else if (session.tool == EditTool.BRIDGE_EDGE_LOOPS) {
                    BridgeParams(session, onParameter)
                } else if (session.tool == EditTool.EXTRUDE) {
                    ExtrudeParams(session, onParameter)
                } else {
                    for (spec in specsFor(session.tool)) {
                        ParamStepper(
                            spec = spec,
                            value = session.double(spec.key) ?: defaultValue(spec),
                            onCommit = { onParameter(spec.key, it) },
                        )
                    }
                }
            }
            Spacer(Modifier.width(10.dp))
            RoundAction(Icons.Default.Close, "Descartar", Ink.Bad, onCancel)
            Spacer(Modifier.width(4.dp))
            RoundAction(Icons.Default.Check, "Confirmar", Ink.Ok, onConfirm)
        }
    }
}

/** Parámetros de Loop Cut en una línea: posición, cortes, suavidad, perfil y toggles. */
@Composable
private fun LoopCutParams(session: ToolSession, onParameter: (String, Any?) -> Unit) {
    PositionStepper(
        factor = session.double("factor") ?: 0.0,
        clamp = session.flag("clamp", true),
        onFactor = { onParameter("factor", it) },
    )
    for (spec in specsFor(EditTool.LOOP_CUT)) {
        ParamStepper(
            spec = spec,
            value = session.double(spec.key) ?: defaultValue(spec),
            onCommit = { onParameter(spec.key, it) },
        )
    }
    val falloff = session.falloff()
    PillButton("Perfil: ${falloff.label}") { onParameter("falloff", falloff.next().wire) }
    PillButton("Uniforme", selected = session.flag("even")) {
        onParameter("even", !session.flag("even"))
    }
    PillButton("Invertir", selected = session.flag("flip")) {
        onParameter("flip", !session.flag("flip"))
    }
    PillButton("Fijar", selected = session.flag("clamp", true)) {
        onParameter("clamp", !session.flag("clamp", true))
    }
}

/**
 * Parámetros de Extrude: distancia + bloqueo de eje (Libre/X/Y/Z) y orientación
 * (Global/Local/Vista) cuando la variante es REGION. Las otras variantes no exponen
 * eje: el backend lo rechaza y aquí se oculta.
 */
@Composable
private fun ExtrudeParams(session: ToolSession, onParameter: (String, Any?) -> Unit) {
    for (spec in specsFor(EditTool.EXTRUDE)) {
        ParamStepper(
            spec = spec,
            value = session.double(spec.key) ?: defaultValue(spec),
            onCommit = { onParameter(spec.key, it) },
        )
    }
    val variant = (session.parameters["variant"] as? String) ?: "REGION"
    if (variant != "REGION") return
    val constraint = (session.parameters["constraint"] as? String) ?: "FREE"
    PillButton("Libre", selected = constraint == "FREE") { onParameter("constraint", "FREE") }
    for (axis in listOf("X", "Y", "Z")) {
        PillButton(axis, selected = constraint == axis) { onParameter("constraint", axis) }
    }
    if (constraint != "FREE") {
        val orientation = (session.parameters["orientation"] as? String) ?: "GLOBAL"
        for ((wire, label) in listOf("GLOBAL" to "Global", "LOCAL" to "Local", "VIEW" to "Vista")) {
            PillButton(label, selected = orientation == wire) { onParameter("orientation", wire) }
        }
    }
}

/** Parámetros de Bridge Edge Loops: desfase, fusión y su toggle de fundir. */
@Composable
private fun BridgeParams(session: ToolSession, onParameter: (String, Any?) -> Unit) {    for (spec in specsFor(EditTool.BRIDGE_EDGE_LOOPS)) {
        ParamStepper(
            spec = spec,
            value = session.double(spec.key) ?: defaultValue(spec),
            onCommit = { onParameter(spec.key, it) },
        )
    }
    PillButton("Fusionar", selected = session.flag("merge")) {
        onParameter("merge", !session.flag("merge"))
    }
}

/**
 * Bandeja del Knife: contador de puntos, deshacer punto, cerrar, snap y las dos
 * salidas. Confirmar solo se habilita con al menos dos puntos (un segmento).
 */
@Composable
fun KnifeTray(
    session: ToolSession,
    onKnifePop: () -> Unit,
    onKnifeClose: () -> Unit,
    onKnifeSnap: (Boolean) -> Unit,
    onConfirm: () -> Unit,
    onCancel: () -> Unit,
    modifier: Modifier = Modifier,
) {
    if (!session.active || session.tool != EditTool.KNIFE) return
    FloatingPanel(modifier) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                "${session.tool.label.uppercase()} · ${session.points.size}",
                color = Ink.Accent,
                fontSize = 11.sp,
                fontWeight = FontWeight.SemiBold,
            )
            Spacer(Modifier.width(10.dp))
            Row(
                modifier = Modifier.weight(1f).horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                PillButton("Deshacer punto", enabled = session.points.isNotEmpty(), onClick = onKnifePop)
                PillButton("Cerrar", selected = session.closed, onClick = onKnifeClose)
                PillButton("Snap", selected = session.flag("snap", true)) {
                    onKnifeSnap(!session.flag("snap", true))
                }
            }
            Spacer(Modifier.width(10.dp))
            RoundAction(Icons.Default.Close, "Descartar", Ink.Bad, onCancel)
            Spacer(Modifier.width(4.dp))
            // Confirmar solo actúa con un segmento válido (el backend lo exige).
            RoundAction(
                Icons.Default.Check, "Confirmar",
                if (session.points.size >= 2) Ink.Ok else Ink.Faint,
                onClick = { if (session.points.size >= 2) onConfirm() },
            )
        }
    }
}

/** factor (−1..1, o ±2 sin fijar) <-> posición 0..100%. */
private fun factorToPercent(factor: Double): Int = (((factor + 1.0) / 2.0) * 100.0).roundToInt()
private fun percentToFactor(percent: Double): Double = (percent / 100.0) * 2.0 - 1.0

/**
 * Posición del corte como porcentaje (0 = extremo, 50 = centro, 100 = el otro
 * extremo), con steppers numéricos y valor editable. Es el equivalente del slider
 * anterior, pero numérico; el arrastre fino sigue siendo deslizar el lápiz por el
 * viewport (`tool.nudge`). Con "Fijar" desactivado el corte puede salirse del borde y
 * el rango se ensancha a −50%..150%.
 */
@Composable
private fun PositionStepper(factor: Double, clamp: Boolean, onFactor: (Double) -> Unit) {
    var text by remember { mutableStateOf("") }
    val percent = factorToPercent(factor)
    val min = if (clamp) 0 else -50
    val max = if (clamp) 100 else 150
    val shown = if (text.isEmpty()) "$percent" else text

    fun commit() {
        val parsed = text.trim().replace(',', '.').removeSuffix("%").toDoubleOrNull() ?: return
        onFactor(percentToFactor(parsed.coerceIn(min.toDouble(), max.toDouble())))
        text = ""
    }

    Row(verticalAlignment = Alignment.CenterVertically) {
        Text("Posición", color = Ink.Faint, fontSize = 11.sp, modifier = Modifier.padding(end = 4.dp))
        StepperButton("−") { onFactor(percentToFactor((percent - 5).coerceAtLeast(min).toDouble())) }
        TextField(
            value = shown,
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
            modifier = Modifier.width(44.dp),
        )
        StepperButton("+") { onFactor(percentToFactor((percent + 5).coerceAtMost(max).toDouble())) }
        Text("%", color = Ink.Faint, fontSize = 11.sp, modifier = Modifier.padding(start = 2.dp))
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
        Text(spec.label, color = Ink.Faint, fontSize = 11.sp, modifier = Modifier.padding(end = 4.dp))
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
            modifier = Modifier.width(64.dp),
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
