package com.blendertablet.remote.ui

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
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
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.key
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
import com.blendertablet.remote.model.LengthUnit
import com.blendertablet.remote.model.SelectionMode
import com.blendertablet.remote.model.ToolSession
import com.blendertablet.remote.model.SnapType
import com.blendertablet.remote.model.moveValueForDisplay
import com.blendertablet.remote.model.transformStepUnit
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
    EditTool.REVOLVE, EditTool.SWEEP -> emptyList()
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
    variantLabel: String? = null,
) {
    if (!session.active && !awaitingPick && !session.armed) return
    // Knife y Bisect tienen su propia bandeja (puntos/pop/cerrar, o el aviso de
    // arrastre y clear inner/outer/fill).
    if (session.tool == EditTool.KNIFE || session.tool == EditTool.BISECT) return
    FloatingPanel(modifier) {
        if (session.controls.isNotEmpty()) {
            Column {
                if (session.tool == EditTool.EXTRUDE) Text("Extruir · ${variantLabel ?: "A toque"}",
                    color = Ink.Accent, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                Text(session.instruction, color = Ink.Muted, fontSize = 12.sp)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    SchemaToolParameters(session.controls, session.parameters, lengthUnit, unitScaleLength,
                        onParameter, Modifier.weight(1f))
                    RoundAction(Icons.Default.Close, if (session.active) "Descartar" else "Salir", Ink.Bad, onCancel)
                    if (session.active) RoundAction(Icons.Default.Check, "Confirmar", if (session.canConfirm) Ink.Ok else Ink.Faint,
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
                if (session.tool == EditTool.EXTRUDE) "EXTRUIR\n${variantLabel ?: "Región"}" else session.tool.label.uppercase(),
                color = Ink.Accent,
                fontSize = 11.sp,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.widthIn(max = 160.dp),
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
                    key(session.sessionId, session.parameters["variant"]) {
                        ExtrudeParams(session, unitScaleLength, lengthUnit, onParameter)
                    }
                } else if (session.tool == EditTool.INSET) {
                    InsetParams(session, unitScaleLength, lengthUnit, onParameter)
                } else if (session.tool == EditTool.BEVEL) {
                    BevelParams(session, selectionMode, unitScaleLength, lengthUnit, onParameter)
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

/** Selector de snap y control de paso declarado por la bandeja. */
@Composable
private fun SnapToggle(
    session: ToolSession,
    onParameter: (String, Any?) -> Unit,
    unitScaleLength: Double = 1.0,
    lengthUnit: LengthUnit = LengthUnit.METERS,
) {
    val options = session.availableSnapTypes
    if (options.isEmpty()) return
    val selected = session.snapType
    SnapControl(options, selected, onSelect = { onParameter("snap_type", it.name) })
    if (session.tool == EditTool.EXTRUDE || selected == SnapType.INCREMENT || selected == SnapType.GRID) {
        if (session.tool in setOf(EditTool.EXTRUDE, EditTool.INSET, EditTool.BEVEL)) {
            DistanceSnapStepInput(
                session.snapStep, unitScaleLength, lengthUnit,
                showSteppers = session.tool == EditTool.EXTRUDE,
                millimeterDecimals = if (session.tool == EditTool.EXTRUDE) 2 else null,
            ) {
                onParameter("snap_step", it)
            }
        } else {
            SnapStepControl(session.snapStep, FactorSnapSteps) { onParameter("snap_step", it) }
        }
    }
}

/**
 * Parámetros de Extrude: distancia + bloqueo de eje (Libre/X/Y/Z) y orientación
 * (Global/Local/Vista) en Región y Manifold. Las otras variantes no exponen
 * eje: el backend lo rechaza y aquí se oculta.
 */
@Composable
private fun ExtrudeParams(session: ToolSession, unitScaleLength: Double, lengthUnit: LengthUnit, onParameter: (String, Any?) -> Unit) {
    for (spec in specsFor(EditTool.EXTRUDE)) {
        ParamStepper(
            spec = spec,
            value = session.double(spec.key) ?: defaultValue(spec),
            unitScaleLength = unitScaleLength,
            stepSize = session.snapStep,
            lengthUnit = lengthUnit,
            millimeterDecimals = 2,
            showReset = true,
            onCommit = { onParameter(spec.key, it) },
        )
    }
    val variant = (session.parameters["variant"] as? String) ?: "REGION"
    if (variant !in setOf("REGION", "MANIFOLD")) {
        SnapToggle(session, onParameter, unitScaleLength, lengthUnit)
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
    SnapToggle(session, onParameter, unitScaleLength, lengthUnit)
}

/** Parámetros de Inset: grosor, profundidad y snap de incremento real (F2/F5). */
@Composable
private fun InsetParams(
    session: ToolSession,
    unitScaleLength: Double,
    lengthUnit: LengthUnit,
    onParameter: (String, Any?) -> Unit,
) {
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
    SnapToggle(session, onParameter, unitScaleLength, lengthUnit)
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
    lengthUnit: LengthUnit,
    onParameter: (String, Any?) -> Unit,
) {
    for (spec in specsFor(EditTool.BEVEL)) {
        ParamStepper(
            spec = spec,
            value = session.double(spec.key) ?: defaultValue(spec),
            unitScaleLength = unitScaleLength,
            stepSize = if (spec.key == "offset" && session.distanceIncrement) session.snapStep else null,
            lengthUnit = if (spec.key == "offset") lengthUnit else null,
            onCommit = { onParameter(spec.key, it) },
        )
    }
    // Miter Outer solo existe en las terminaciones de un bisel de aristas. Blender
    // lo ignora al biselar vértices y tampoco cambia un loop cerrado completo.
    if (selectionMode == SelectionMode.EDGE) {
        val miter = session.miterOuter()
        PillButton("Final: ${miter.label}") { onParameter("miter_outer", miter.next().wire) }
    }
    SnapToggle(session, onParameter, unitScaleLength, lengthUnit)
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
                KnifeSnapControl(
                    session.flag("snap", true),
                    (session.parameters["snap_mode"] as? String ?: "AUTO").uppercase(),
                ) { mode ->
                    if (mode == "NONE") onKnifeSnap(false) else {
                        onKnifeSnapMode(mode)
                        if (!session.flag("snap", true)) onKnifeSnap(true)
                    }
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
    // null muestra el valor remoto; vacío conserva el borrado mientras se escribe.
    var text by remember(unit) { mutableStateOf<String?>(null) }
    val limit = if (session.flag("clamp", true)) 1.0 else 2.0
    val minimum = if (metric) -limit * session.slideRange / metersPerUnit else (1.0 - limit) * 50.0
    val maximum = if (metric) limit * session.slideRange / metersPerUnit else (1.0 + limit) * 50.0
    fun send(number: Double) {
        if (!number.isFinite()) return
        val bounded = number.coerceIn(minimum, maximum)
        if (metric) onParameter("slide_distance", bounded * metersPerUnit)
        else onParameter("factor", bounded / 50.0 - 1.0)
        text = null
    }
    fun commit() { text?.trim()?.replace(',', '.')?.toDoubleOrNull()?.let(::send) }
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(if (metric) "Desde centro" else "Posición", color = Ink.Faint, fontSize = 11.sp)
        StepperButton("−") { send(value - 1.0) }
        CompactNumericField(
            value = text ?: format(value, false),
            onValueChange = { text = it }, onDone = { commit() },
            modifier = Modifier.width(72.dp),
        )
        Box {
            PillButton(unit) { menu = true }
            DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                val units = if (session.slideRange > 0.0) listOf("%", "mm", "cm", "m") else listOf("%")
                units.forEach { option ->
                    DropdownMenuItem(text = { Text(option) }, onClick = { unit = option; menu = false; text = null })
                }
            }
        }
        StepperButton("+") { send(value + 1.0) }
        PillButton("Aplicar", enabled = !text.isNullOrBlank()) { commit() }
        PillButton("Centro") { onParameter("factor", 0.0); text = null }
    }
}

/** Un parámetro con steppers (−/+) y valor exacto editable en el centro. */
@Composable
private fun ParamStepper(
    spec: ParamSpec,
    value: Double,
    unitScaleLength: Double,
    showSteppers: Boolean = true,
    stepSize: Double? = null,
    lengthUnit: LengthUnit? = null,
    millimeterDecimals: Int? = null,
    showReset: Boolean = false,
    onCommit: (Double) -> Unit,
) {
    // null muestra el valor remoto; "" es un borrado intencional durante la edición.
    var text by remember(spec.key) { mutableStateOf<String?>(null) }
    var pendingValue by remember(spec.key) { mutableStateOf<Double?>(null) }
    LaunchedEffect(value) {
        if (pendingValue?.let { kotlin.math.abs(it - value) < 1e-9 } == true) pendingValue = null
    }
    val shownValue = pendingValue ?: value
    val formatted = if (lengthUnit != null) {
        val display = moveValueForDisplay(shownValue, lengthUnit.transformStepUnit(), unitScaleLength)
        val decimals = if (lengthUnit == LengthUnit.MILLIMETERS) millimeterDecimals else null
        "${formatToolDistance(display, decimals)} ${lengthUnit.short}"
    } else format(shownValue, spec.isInt)

    fun readDraft(): Double? {
        val input = text ?: return shownValue
        val withUnit = if (lengthUnit != null && input.trim().replace(',', '.').toDoubleOrNull() != null)
            "$input ${lengthUnit.short}" else input
        val parsed = ValueParser.parse(withUnit, spec.mode) ?: return null
        val wire = if (spec.mode == TransformMode.MOVE) parsed / unitScaleLength else parsed
        return clampParam(wire, spec.isInt, spec.min, spec.max)
    }
    fun commit() {
        if (text == null) return
        val next = readDraft() ?: return
        if (stepSize != null) pendingValue = next
        onCommit(next)
        text = null
    }
    fun adjust(direction: Int) {
        val current = if (stepSize != null) readDraft() ?: return else value
        val next = stepParam(current, stepSize ?: spec.step, direction, spec.isInt, spec.min, spec.max)
        if (stepSize != null) {
            pendingValue = next
            text = null
        }
        onCommit(next)
    }

    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(spec.label, color = Ink.Faint, fontSize = 11.sp, modifier = Modifier.padding(end = 4.dp))
        if (showSteppers) StepperButton("−") {
            adjust(-1)
        }
        CompactNumericField(
            value = text ?: formatted,
            onValueChange = { text = it },
            onDone = { commit() },
            modifier = Modifier.width(64.dp),
        )
        if (showSteppers) StepperButton("+") {
            adjust(1)
        }
        if (showReset) PillButton("Reset 0") {
            text = null
            pendingValue = if (value == 0.0) null else 0.0
            onCommit(0.0)
        }
    }
}

private fun format(value: Double, isInt: Boolean): String =
    if (isInt) value.roundToInt().toString() else {
        val rounded = (value * 1000).roundToInt() / 1000.0
        if (rounded == 0.0) "0" else rounded.toString()
    }
