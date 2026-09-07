package com.blendertablet.remote.ui

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.automirrored.filled.Undo
import androidx.compose.material3.Text
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
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
import com.blendertablet.remote.model.SelectionMode
import com.blendertablet.remote.model.ToolSession
import com.blendertablet.remote.model.SnapType
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
    /** Valor con el que nace el parámetro si la sesión aún no lo trae. */
    val default: Double = 0.0,
    /** Rango cerrado, cuando el backend solo acepta una franja (perfil del bisel). */
    val min: Double? = null,
    val max: Double? = null,
)

private fun specsFor(tool: EditTool): List<ParamSpec> = when (tool) {
    EditTool.EXTRUDE -> listOf(ParamSpec("offset", "Distancia", 0.01, false, TransformMode.MOVE))
    // Los cuatro controles que deciden la forma del bisel. `profile` es un factor
    // 0..1: 0,5 traza el arco circular, por debajo hunde la esquina y 1,0 la remata
    // en pico. El remate exterior va aparte, en su propio botón.
    EditTool.BEVEL -> listOf(
        ParamSpec("offset", "Ancho", 0.1, false, TransformMode.MOVE),
        ParamSpec("segments", "Segmentos", 1.0, true, TransformMode.SCALE, default = 1.0),
        ParamSpec("profile", "Perfil", 0.05, false, TransformMode.SCALE,
                  default = 0.5, min = 0.0, max = 1.0),
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
        ParamSpec("smoothness", "Suavidad", 0.01, false, TransformMode.SCALE),
    )
    EditTool.BRIDGE_EDGE_LOOPS -> listOf(
        ParamSpec("twist_offset", "Desfase", 1.0, true, TransformMode.SCALE),
        ParamSpec("merge_factor", "Fusión", 0.01, false, TransformMode.SCALE),
    )
    EditTool.ALIGN -> emptyList()
    EditTool.KNIFE -> emptyList()
    EditTool.BISECT -> emptyList()
}

private fun defaultValue(spec: ParamSpec): Double =
    if (spec.isInt) maxOf(1.0, spec.default) else spec.default

/** El valor que el backend acepta: entero mínimo 1 y, si lo hay, dentro del rango. */
internal fun clampParam(value: Double, isInt: Boolean, min: Double?, max: Double?): Double {
    var result = if (isInt) maxOf(1.0, value.roundToInt().toDouble()) else value
    min?.let { result = maxOf(it, result) }
    max?.let { result = minOf(it, result) }
    return result
}

internal fun stepParam(
    value: Double, step: Double, direction: Int, isInt: Boolean, min: Double?, max: Double?,
): Double = clampParam(value + step * direction, isInt, min, max)

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
    selectionMode: SelectionMode,
    unitScaleLength: Double,
    onParameter: (String, Any?) -> Unit,
    onConfirm: () -> Unit,
    onCancel: () -> Unit,
    onLoopPop: () -> Unit,
    modifier: Modifier = Modifier,
    awaitingPick: Boolean = false,
    lengthUnit: com.blendertablet.remote.model.LengthUnit = com.blendertablet.remote.model.LengthUnit.CENTIMETERS,
) {
    if (!session.active && !awaitingPick) return
    // Knife y Bisect tienen su propia bandeja (puntos/pop/cerrar, o el aviso de
    // arrastre y clear inner/outer/fill).
    if (session.tool == EditTool.KNIFE || session.tool == EditTool.BISECT) return
    FloatingPanel(modifier) {
        if (session.controls.isNotEmpty()) {
            Column {
                Text(session.instruction, color = Ink.Muted, fontSize = 12.sp)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    SchemaToolParameters(session.controls, session.parameters, lengthUnit, unitScaleLength,
                        onParameter, Modifier.weight(1f))
                    RoundAction(Icons.Default.Close, "Descartar", Ink.Bad, onCancel)
                    RoundAction(Icons.Default.Check, "Confirmar", if (session.canConfirm) Ink.Ok else Ink.Faint,
                        onClick = { if (session.canConfirm) onConfirm() })
                }
            }
            return@FloatingPanel
        }
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
                    Text(
                        "Loops: ${session.loopCount} · Mayús+toque añade",
                        color = Ink.Muted,
                        fontSize = 11.sp,
                    )
                    LoopCutParams(session, unitScaleLength, onParameter)
                } else if (session.tool == EditTool.BRIDGE_EDGE_LOOPS) {
                    BridgeParams(session, unitScaleLength, onParameter)
                } else if (session.tool == EditTool.EXTRUDE) {
                    ExtrudeParams(session, unitScaleLength, onParameter)
                } else if (session.tool == EditTool.INSET) {
                    InsetParams(session, unitScaleLength, onParameter)
                } else if (session.tool == EditTool.BEVEL) {
                    BevelParams(session, selectionMode, unitScaleLength, onParameter)
                } else {
                    for (spec in specsFor(session.tool)) {
                        ParamStepper(
                            spec = spec,
                            value = session.double(spec.key) ?: defaultValue(spec),
                            unitScaleLength = unitScaleLength,
                            onCommit = { onParameter(spec.key, it) },
                        )
                    }
                }
            }
            Spacer(Modifier.width(10.dp))
            if (session.tool == EditTool.LOOP_CUT && session.loopCount > 1) {
                RoundAction(Icons.AutoMirrored.Filled.Undo, "Deshacer último loop", Ink.Muted, onLoopPop)
                Spacer(Modifier.width(4.dp))
            }
            RoundAction(Icons.Default.Close, "Descartar", Ink.Bad, onCancel)
            Spacer(Modifier.width(4.dp))
            RoundAction(Icons.Default.Check, "Confirmar", Ink.Ok, onConfirm)
        }
    }
}

/** Parámetros de Loop Cut en una línea: posición, cortes, suavidad, perfil y toggles. */
@Composable
private fun LoopCutParams(
    session: ToolSession,
    unitScaleLength: Double,
    onParameter: (String, Any?) -> Unit,
) {
    PositionStepper(
        session = session,
        onParameter = onParameter,
    )
    for (spec in specsFor(EditTool.LOOP_CUT)) {
        ParamStepper(
            spec = spec,
            value = session.double(spec.key) ?: defaultValue(spec),
            unitScaleLength = unitScaleLength,
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
    SnapToggle(session, onParameter)
}

/**
 * Snap de incremento real (B5/F5): NONE <-> INCREMENT con el paso por defecto del
 * servidor (`snap_step`, 0.1). Cuadra el valor antes de aplicar la operación, así
 * que cambia el resultado geométrico, no solo lo que se enseña.
 */
@Composable
private fun SnapToggle(session: ToolSession, onParameter: (String, Any?) -> Unit) {
    val options = session.availableSnapTypes
    if (options.isEmpty()) return
    val selected = session.snapType
    SnapControl(options, selected, onSelect = { onParameter("snap_type", it.name) })
    if (selected == SnapType.INCREMENT || selected == SnapType.GRID) {
        val distance = session.tool in setOf(EditTool.EXTRUDE, EditTool.INSET, EditTool.BEVEL)
        SnapStepControl(
            selected = session.snapStep,
            presets = if (distance) DistanceSnapSteps else FactorSnapSteps,
            onSelect = { onParameter("snap_step", it) },
        )
    }
}

/**
 * Parámetros de Extrude: distancia + bloqueo de eje (Libre/X/Y/Z) y orientación
 * (Global/Local/Vista) cuando la variante es REGION. Las otras variantes no exponen
 * eje: el backend lo rechaza y aquí se oculta.
 */
@Composable
private fun ExtrudeParams(session: ToolSession, unitScaleLength: Double, onParameter: (String, Any?) -> Unit) {
    for (spec in specsFor(EditTool.EXTRUDE)) {
        ParamStepper(
            spec = spec,
            value = session.double(spec.key) ?: defaultValue(spec),
            unitScaleLength = unitScaleLength,
            onCommit = { onParameter(spec.key, it) },
        )
    }
    val variant = (session.parameters["variant"] as? String) ?: "REGION"
    if (variant != "REGION") {
        SnapToggle(session, onParameter)
        return
    }
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
    SnapToggle(session, onParameter)
}

/** Parámetros de Inset: grosor, profundidad y snap de incremento real (F2/F5). */
@Composable
private fun InsetParams(session: ToolSession, unitScaleLength: Double, onParameter: (String, Any?) -> Unit) {
    for (spec in specsFor(EditTool.INSET)) {
        ParamStepper(
            spec = spec,
            value = session.double(spec.key) ?: defaultValue(spec),
            unitScaleLength = unitScaleLength,
            onCommit = { onParameter(spec.key, it) },
        )
    }
    val boundary = session.flag("boundary", true)
    PillButton("Costura fija", selected = !boundary) {
        onParameter("boundary", toggledInsetBoundary(boundary))
    }
    SnapToggle(session, onParameter)
}

internal fun toggledInsetBoundary(boundary: Boolean): Boolean = !boundary

/**
 * Parámetros de Bevel: ancho, segmentos, perfil, remate de la esquina y snap.
 *
 * El perfil y el remate son los dos que deciden la forma, así que van en la bandeja y
 * no escondidos: con un solo segmento el perfil apenas se nota, pero con varios manda
 * sobre el resultado. El remate cicla porque son tres valores y un desplegable para
 * tres opciones cortas cuesta más toques que el propio ciclo.
 */
@Composable
private fun BevelParams(
    session: ToolSession,
    selectionMode: SelectionMode,
    unitScaleLength: Double,
    onParameter: (String, Any?) -> Unit,
) {
    for (spec in specsFor(EditTool.BEVEL)) {
        ParamStepper(
            spec = spec,
            value = session.double(spec.key) ?: defaultValue(spec),
            unitScaleLength = unitScaleLength,
            onCommit = { onParameter(spec.key, it) },
        )
    }
    // Miter Outer solo existe en las terminaciones de un bisel de aristas. Blender
    // lo ignora al biselar vértices y tampoco cambia un loop cerrado completo.
    if (selectionMode == SelectionMode.EDGE) {
        val miter = session.miterOuter()
        PillButton("Final: ${miter.label}") { onParameter("miter_outer", miter.next().wire) }
    }
    SnapToggle(session, onParameter)
}

/** Parámetros de Bridge Edge Loops: desfase, fusión, su toggle de fundir y snap del factor. */
@Composable
private fun BridgeParams(session: ToolSession, unitScaleLength: Double, onParameter: (String, Any?) -> Unit) {
    for (spec in specsFor(EditTool.BRIDGE_EDGE_LOOPS)) {
        ParamStepper(
            spec = spec,
            value = session.double(spec.key) ?: defaultValue(spec),
            unitScaleLength = unitScaleLength,
            onCommit = { onParameter(spec.key, it) },
        )
    }
    PillButton("Fusionar", selected = session.flag("merge")) {
        onParameter("merge", !session.flag("merge"))
    }
    SnapToggle(session, onParameter)
}

/**
 * Bandeja del Knife: contador de puntos, deshacer punto, cerrar, snap y las dos
 * salidas. Confirmar solo se habilita con al menos dos puntos (un segmento).
 */
@Composable
fun KnifeTray(
    session: ToolSession,
    onKnifePop: () -> Unit,
    onKnifeNewStroke: () -> Unit,
    onKnifeClose: () -> Unit,
    onKnifeSnap: (Boolean) -> Unit,
    onKnifeSnapMode: (String) -> Unit,
    onConfirm: () -> Unit,
    onCancel: () -> Unit,
    modifier: Modifier = Modifier,
) {
    if (!session.active || session.tool != EditTool.KNIFE) return
    FloatingPanel(modifier) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                "${session.tool.label.uppercase()} · ${session.strokes.size + 1} cortes · ${session.points.size} puntos",
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
                Text(
                    knifeInstruction(session.points.size),
                    color = Ink.Muted,
                    fontSize = 11.sp,
                )
                PillButton(
                    "Deshacer punto",
                    enabled = session.points.isNotEmpty() || session.strokes.isNotEmpty(),
                    onClick = onKnifePop,
                )
                PillButton("Nuevo corte", enabled = session.points.size >= 2, onClick = onKnifeNewStroke)
                PillButton("Cerrar", selected = session.closed, onClick = onKnifeClose)
                PillButton("Snap", selected = session.flag("snap", true)) {
                    onKnifeSnap(!session.flag("snap", true))
                }
                val snapModes = listOf("AUTO", "VERTEX", "EDGE_CENTER", "EDGE")
                val snapMode = (session.parameters["snap_mode"] as? String ?: "AUTO").uppercase()
                val snapLabel = when (snapMode) {
                    "VERTEX" -> "Vértice"
                    "EDGE_CENTER" -> "Medio"
                    "EDGE" -> "Arista"
                    else -> "Auto"
                }
                PillButton("Destino: $snapLabel", enabled = session.flag("snap", true)) {
                    onKnifeSnapMode(snapModes[(snapModes.indexOf(snapMode).coerceAtLeast(0) + 1) % snapModes.size])
                }
            }
            Spacer(Modifier.width(10.dp))
            RoundAction(Icons.Default.Close, "Descartar", Ink.Bad, onCancel)
            Spacer(Modifier.width(4.dp))
            // Confirmar solo actúa con un segmento válido (el backend lo exige).
            RoundAction(
                Icons.Default.Check, "Confirmar",
                if (session.points.size >= 2 || session.strokes.isNotEmpty()) Ink.Ok else Ink.Faint,
                onClick = { if (session.points.size >= 2 || session.strokes.isNotEmpty()) onConfirm() },
            )
        }
    }
}

internal fun knifeInstruction(pointCount: Int): String =
    if (pointCount == 0) "Pulsa, ajusta y suelta el primer punto"
    else if (pointCount == 1) "Coloca el segundo punto para cortar"
    else "Añade puntos o pulsa Nuevo corte"

/**
 * Bandeja de Bisect (F4). Armada (sin arrastre todavía) solo enseña el aviso de
 * dibujar la línea; activa, muestra clear inner/outer, fill, snap y las dos salidas.
 * Redibujar la línea no la cierra: el usuario puede ajustar el corte varias veces
 * antes de confirmar.
 */
@Composable
fun BisectTray(
    session: ToolSession,
    onParameter: (String, Any?) -> Unit,
    onConfirm: () -> Unit,
    onCancel: () -> Unit,
    modifier: Modifier = Modifier,
) {
    if (session.tool != EditTool.BISECT || (!session.active && !session.armed)) return
    FloatingPanel(modifier) {
        if (!session.active) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    "Arrastra una línea sobre la malla para cortar",
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
                PillButton("Vaciar interior", selected = session.flag("clear_inner")) {
                    onParameter("clear_inner", !session.flag("clear_inner"))
                }
                PillButton("Vaciar exterior", selected = session.flag("clear_outer")) {
                    onParameter("clear_outer", !session.flag("clear_outer"))
                }
                PillButton("Rellenar", selected = session.flag("fill")) {
                    onParameter("fill", !session.flag("fill"))
                }
                PillButton("Snap", selected = session.flag("snap", true)) {
                    onParameter("snap", !session.flag("snap", true))
                }
            }
            Spacer(Modifier.width(10.dp))
            RoundAction(Icons.Default.Close, "Descartar", Ink.Bad, onCancel)
            Spacer(Modifier.width(4.dp))
            RoundAction(Icons.Default.Check, "Confirmar", Ink.Ok, onConfirm)
        }
    }
}

/** 50 % es el centro; las unidades métricas expresan desplazamiento desde él. */
@Composable
private fun PositionStepper(session: ToolSession, onParameter: (String, Any?) -> Unit) {
    var unit by remember { mutableStateOf("%") }
    var menu by remember { mutableStateOf(false) }
    val factor = session.double("factor") ?: 0.0
    val metric = unit != "%" && session.slideRange > 0.0
    val metersPerUnit = when (unit) { "mm" -> 0.001; "cm" -> 0.01; else -> 1.0 }
    val value = if (metric) session.slideDistance / metersPerUnit else (factor + 1.0) * 50.0
    var text by remember(value, unit) { mutableStateOf("") }
    val limit = if (session.flag("clamp", true)) 1.0 else 2.0
    val minimum = if (metric) -limit * session.slideRange / metersPerUnit else (1.0 - limit) * 50.0
    val maximum = if (metric) limit * session.slideRange / metersPerUnit else (1.0 + limit) * 50.0
    fun send(number: Double) {
        if (!number.isFinite()) return
        val bounded = number.coerceIn(minimum, maximum)
        if (metric) onParameter("slide_distance", bounded * metersPerUnit)
        else onParameter("factor", bounded / 50.0 - 1.0)
        text = ""
    }
    fun commit() { text.trim().replace(',', '.').toDoubleOrNull()?.let(::send) }
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(if (metric) "Desde centro" else "Posición", color = Ink.Faint, fontSize = 11.sp)
        StepperButton("−") { send(value - 1.0) }
        CompactNumericField(
            value = text.ifEmpty { format(value, false) },
            onValueChange = { text = it }, onDone = { commit() },
            modifier = Modifier.width(72.dp),
        )
        Box {
            PillButton(unit) { menu = true }
            DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                val units = if (session.slideRange > 0.0) listOf("%", "mm", "cm", "m") else listOf("%")
                units.forEach { option ->
                    DropdownMenuItem(text = { Text(option) }, onClick = { unit = option; menu = false; text = "" })
                }
            }
        }
        StepperButton("+") { send(value + 1.0) }
        PillButton("Aplicar", enabled = text.isNotBlank()) { commit() }
        PillButton("Centro") { onParameter("factor", 0.0); text = "" }
    }
}

/** Un parámetro con steppers (−/+) y valor exacto editable en el centro. */
@Composable
private fun ParamStepper(
    spec: ParamSpec,
    value: Double,
    unitScaleLength: Double,
    onCommit: (Double) -> Unit,
) {
    var text by remember { mutableStateOf("") }
    val formatted = format(value, spec.isInt)

    fun commit() {
        val parsed = ValueParser.parse(text, spec.mode) ?: return
        val wire = if (spec.mode == TransformMode.MOVE) parsed / unitScaleLength else parsed
        onCommit(clampParam(wire, spec.isInt, spec.min, spec.max))
        text = ""
    }

    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(spec.label, color = Ink.Faint, fontSize = 11.sp, modifier = Modifier.padding(end = 4.dp))
        StepperButton("−") {
            onCommit(stepParam(value, spec.step, -1, spec.isInt, spec.min, spec.max))
        }
        CompactNumericField(
            value = if (text.isEmpty()) formatted else text,
            onValueChange = { text = it },
            onDone = { commit() },
            modifier = Modifier.width(64.dp),
        )
        StepperButton("+") {
            onCommit(stepParam(value, spec.step, 1, spec.isInt, spec.min, spec.max))
        }
    }
}

private fun format(value: Double, isInt: Boolean): String =
    if (isInt) value.roundToInt().toString() else {
        val rounded = (value * 1000).roundToInt() / 1000.0
        if (rounded == 0.0) "0" else rounded.toString()
    }
