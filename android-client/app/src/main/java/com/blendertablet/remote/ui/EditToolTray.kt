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
import com.blendertablet.remote.model.NumericExpression
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
        ParamSpec("offset", "Ancho", 0.1, false, TransformMode.MOVE, min = 0.0),
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
        ParamSpec("twist_offset", "Desfase", 1.0, true, TransformMode.SCALE, min = -100000.0),
        ParamSpec("merge_factor", "Posición de fusión", 0.01, false, TransformMode.SCALE, min = 0.0, max = 1.0),
    )
    EditTool.ALIGN -> emptyList()
    EditTool.REVOLVE, EditTool.SWEEP -> emptyList()
    EditTool.KNIFE -> emptyList()
    EditTool.BISECT -> emptyList()
}

private fun defaultValue(spec: ParamSpec): Double =
    if (spec.isInt) maxOf(spec.min ?: 1.0, spec.default) else spec.default

/** One parameter group per slot; the same inventory drives rendering and its limit test. */
@Composable
fun EditToolTray(
    session: ToolSession, selectionMode: SelectionMode, unitScaleLength: Double,
    onParameter: (String, Any?) -> Unit, onConfirm: () -> Unit, onCancel: () -> Unit,
    onLoopPop: () -> Unit, modifier: Modifier = Modifier, awaitingPick: Boolean = false,
    lengthUnit: LengthUnit = LengthUnit.CENTIMETERS, variantLabel: String? = null,
) {
    if (!session.active && !awaitingPick && !session.armed) return
    if (session.tool in setOf(EditTool.KNIFE, EditTool.BISECT)) return
    val instruction = if (session.tool == EditTool.LOOP_CUT)
        "Arrastra para desplazar · toca otra arista para añadir otro corte"
        else session.instruction.ifBlank { if (session.tool == EditTool.EXTRUDE) "Arrastra para extruir · escribe una medida, por ejemplo 5mm"
            else "Arrastra sobre la malla y toca el número para afinar" }
    if (!session.active && session.controls.isEmpty()) {
        SingleLineTray(session.tool.label, onCancel = onCancel, modifier = modifier) {
            Text("Toca una arista para colocar el primer corte", color = Ink.Muted, fontSize = 12.sp, maxLines = 1)
        }
        return
    }
    val contents = com.blendertablet.remote.model.toolTrayContents(session, selectionMode)
    SingleLineTray(trayTitle(session.tool, variantLabel ?: "Región"), onCancel,
        if (session.active) onConfirm else null, session.canConfirm, modifier, help = instruction) {
        key(session.sessionId, session.tool) {
            contents.visible.forEach { id ->
                if (id == "more") ToolMoreMenu(instruction) {
                    contents.advanced.forEach { advanced ->
                        AdvancedToolOption(toolOptionHelp(advanced, session)) {
                            ToolControl(advanced, session, unitScaleLength, lengthUnit, onParameter, onLoopPop)
                        }
                    }
                } else ToolControl(id, session, unitScaleLength, lengthUnit, onParameter, onLoopPop)
            }
        }
    }
}

private fun toolOptionHelp(id: String, session: ToolSession): String = session.controls.firstOrNull { it.id == id }?.help?.takeIf { it.isNotBlank() } ?: when (id) {
    "even" -> "Desplaza el corte siguiendo la distancia de una de sus aristas laterales."
    "flip" -> "Usa el lado opuesto como referencia al seguir la arista."
    "clamp" -> "Impide que el corte sobrepase los extremos de la cara."
    "smoothness" -> "Curva la nueva geometría para suavizar el contorno."
    "falloff" -> "Elige cómo se reparte la suavidad del corte."
    "profile" -> "Cambia la curvatura del bisel entre sus segmentos."
    "miter_outer" -> "Define cómo se unen los biseles en las esquinas exteriores."
    "orientation" -> "Interpreta el eje respecto al mundo, al objeto o a la vista."
    "depth" -> "Eleva o hunde la región interior respecto a su cara original."
    "boundary" -> "Conserva el borde abierto de la malla al crear el inset."
    "merge" -> "Une los dos contornos en uno en lugar de crear caras entre ellos."
    "merge_factor" -> "Sitúa el contorno fusionado entre el primero y el segundo."
    "snap" -> "Ajusta el gesto a incrementos o a la geometría; los números escritos siguen siendo exactos."
    "fill" -> "Cierra con caras los huecos que deja el corte."
    else -> "Ajusta ${session.controls.firstOrNull { it.id == id }?.label?.lowercase() ?: id} de esta operación."
}

@Composable
private fun ToolControl(id: String, session: ToolSession, scale: Double, unit: LengthUnit,
    change: (String, Any?) -> Unit, pop: () -> Unit) {
    session.controls.firstOrNull { it.id == id }?.let { spec ->
        SchemaToolParameters(listOf(spec), session.parameters, unit, scale, change)
        return
    }
    val spec = specsFor(session.tool).firstOrNull { it.key == id }
    if (spec != null) {
        ParamStepper(spec, session.double(id) ?: defaultValue(spec), scale,
            stepSize = if (spec.mode == TransformMode.MOVE) session.snapStep else null,
            lengthUnit = if (spec.mode == TransformMode.MOVE) unit else null,
            quickValues = when {
                session.tool in setOf(EditTool.LOOP_CUT, EditTool.SUBDIVIDE) && id == "cuts" -> listOf(1,2,3,4)
                session.tool == EditTool.BEVEL && id == "segments" -> listOf(1,2,3)
                else -> emptyList()
            },
            onCommit = { change(id, it) })
        return
    }
    when (id) {
        "position" -> PositionStepper(session, change)
        "remove_loop" -> IconAction(AppIcons.Undo, "Quitar último corte", onClick = pop)
        "even" -> PillButton("Seguir la arista", selected = session.flag(id)) { change(id, !session.flag(id)) }
        "flip" -> PillButton("Invertir", selected = session.flag(id)) { change(id, !session.flag(id)) }
        "clamp" -> PillButton("No salir de la cara", selected = session.flag(id, true)) { change(id, !session.flag(id, true)) }
        "falloff" -> PillButton("Perfil: ${session.falloff().label}") { change(id, session.falloff().next().wire) }
        "miter_outer" -> PillButton("Esquinas: ${session.miterOuter().label}") { change(id, session.miterOuter().next().wire) }
        "constraint" -> Row(horizontalArrangement = Arrangement.spacedBy(3.dp)) {
            listOf("FREE" to "Libre", "X" to "X", "Y" to "Y", "Z" to "Z").forEach { (wire, label) ->
                PillButton(label, selected = (session.parameters[id] ?: "FREE") == wire) { change(id, wire) }
            }
        }
        "orientation" -> Row(horizontalArrangement = Arrangement.spacedBy(3.dp)) {
            listOf("GLOBAL" to "Global", "LOCAL" to "Local", "VIEW" to "Vista").forEach { (wire, label) ->
                PillButton(label, selected = (session.parameters[id] ?: "GLOBAL") == wire) { change(id, wire) }
            }
        }
        "boundary" -> PillButton("Conservar borde abierto", selected = !session.flag(id, true)) { change(id, !session.flag(id, true)) }
        "merge" -> PillButton("Fusionar", selected = session.flag(id)) { change(id, !session.flag(id)) }
        "snap" -> Column {
            SnapControl(session.availableSnapTypes, session.snapType, onSelect = { change("snap_type", it.name) })
            if (session.snapType in setOf(SnapType.INCREMENT, SnapType.GRID)) {
                if (session.tool in setOf(EditTool.EXTRUDE, EditTool.BEVEL, EditTool.INSET))
                    DistanceSnapStepInput(session.snapStep, scale, unit) { change("snap_step", it) }
                else SnapStepControl(session.snapStep, FactorSnapSteps) { change("snap_step", it) }
            }
        }
    }
}

@Composable
fun KnifeTray(session: ToolSession, onKnifePop: () -> Unit, onKnifeNewStroke: () -> Unit,
    onKnifeClose: () -> Unit, onKnifeSnap: (Boolean) -> Unit, onKnifeSnapMode: (String) -> Unit,
    onConfirm: () -> Unit, onCancel: () -> Unit, modifier: Modifier = Modifier) {
    if (!session.active || session.tool != EditTool.KNIFE) return
    val contents = com.blendertablet.remote.model.toolTrayContents(session)
    SingleLineTray("Cuchillo", onCancel, onConfirm, session.points.size >= 2 || session.strokes.isNotEmpty(), modifier,
        help = knifeInstruction(session.points.size)) {
        contents.visible.forEach { id -> when (id) {
            "undo_point" -> PillButton("Deshacer punto", enabled = session.points.isNotEmpty() || session.strokes.isNotEmpty(), onClick = onKnifePop)
            "new_cut" -> PillButton("Nuevo corte", enabled = session.points.size >= 2, onClick = onKnifeNewStroke)
            "close_cut" -> PillButton("Cerrar", selected = session.closed, onClick = onKnifeClose)
            "more" -> ToolMoreMenu(knifeInstruction(session.points.size)) {
                AdvancedToolOption("Atrae el corte a puntos y aristas cercanos al lápiz.") {
                    KnifeSnapControl(session.flag("snap", true), (session.parameters["snap_mode"] as? String ?: "AUTO").uppercase()) { mode ->
                        if (mode == "NONE") onKnifeSnap(false) else { onKnifeSnapMode(mode); if (!session.flag("snap", true)) onKnifeSnap(true) }
                    }
                }
            }
        } }
    }
}

internal fun knifeInstruction(pointCount: Int): String = if (pointCount == 0) "Pulsa, ajusta y suelta el primer punto"
    else if (pointCount == 1) "Coloca el segundo punto para cortar" else "Añade puntos o pulsa Nuevo corte"

@Composable
fun BisectTray(session: ToolSession, onParameter: (String, Any?) -> Unit, onConfirm: () -> Unit,
    onCancel: () -> Unit, modifier: Modifier = Modifier) {
    if (session.tool != EditTool.BISECT || (!session.active && !session.armed)) return
    val help = "Arrastra una línea sobre la malla para cortar"
    val contents = com.blendertablet.remote.model.toolTrayContents(session)
    SingleLineTray(session.tool.label, onCancel, if (session.active) onConfirm else null, modifier = modifier, help = help) {
        if (!session.active) Text(help, color = Ink.Muted, fontSize = 12.sp, maxLines = 1)
        else contents.visible.forEach { id -> when (id) {
            "clear_inner", "clear_outer" -> PillButton(if (id == "clear_inner") "Vaciar interior" else "Vaciar exterior", selected = session.flag(id)) { onParameter(id, !session.flag(id)) }
            "more" -> ToolMoreMenu(help) {
                AdvancedToolOption("Cierra los huecos del corte con caras nuevas.") {
                    PillButton("Rellenar", selected = session.flag("fill")) { onParameter("fill", !session.flag("fill")) }
                }
                AdvancedToolOption("Atrae los extremos de la línea a la geometría cercana.") {
                    PillButton("Snap", selected = session.flag("snap", true)) { onParameter("snap", !session.flag("snap", true)) }
                }
            }
        } }
    }
}

/** Offset from the centre, accepting percentages or physical lengths in the same field. */
@Composable
private fun PositionStepper(session: ToolSession, onParameter: (String, Any?) -> Unit) {
    val factor = session.double("factor") ?: 0.0
    var draft by remember(session.sessionId, session.loopCount) { mutableStateOf<String?>(null) }
    var pending by remember(session.sessionId, session.loopCount) { mutableStateOf<Double?>(null) }
    LaunchedEffect(factor) { if (pending?.let { kotlin.math.abs(it - factor) < 1e-9 } == true) pending = null }
    val shown = pending ?: factor
    val limit = if (session.flag("clamp", true)) 1.0 else 2.0
    fun read() = draft?.let { com.blendertablet.remote.model.parseLoopPosition(it, shown, session.slideRange) } ?: shown.takeIf { draft == null }
    fun send(value: Double) {
        if (!value.isFinite()) return
        val bounded = value.coerceIn(-limit, limit)
        pending = bounded; draft = null
        onParameter("factor", bounded)
    }
    Row(verticalAlignment = Alignment.CenterVertically) {
        HoverHelp("Posición desde el centro", "0 % es el centro. Escribe un porcentaje o una distancia, por ejemplo 5mm.") {
            Text("Posición", color = Ink.Faint, fontSize = 11.sp)
        }
        StepperButton("−") { read()?.let { send(it - .01) } }
        CompactNumericField(value = draft ?: "${formatToolDistance(shown * 100, 3)} %",
            onValueChange = { draft = it }, onDone = { read()?.let(::send) },
            modifier = Modifier.width(90.dp), fontSize = 16.sp, selectAllOnFocus = true)
        StepperButton("+") { read()?.let { send(it + .01) } }
        PillButton("Centro") { send(0.0) }
    }
}

/** Un parámetro con steppers (−/+) y valor exacto editable en el centro. */
@Composable
private fun ParamStepper(
    spec: ParamSpec,
    value: Double,
    unitScaleLength: Double,
    stepSize: Double? = null,
    lengthUnit: LengthUnit? = null,
    quickValues: List<Int> = emptyList(),
    onCommit: (Double) -> Unit,
) {
    ToolNumericInput(spec.label, value, stepSize ?: spec.step, spec.mode, unitScaleLength, lengthUnit,
        integer = spec.isInt, min = spec.min ?: if (spec.isInt) 1.0 else null, max = spec.max,
        quickValues = quickValues, onCommit = onCommit)
}

/** Extruir lleva su variante en el rótulo; el resto, el nombre de la herramienta. */
internal fun trayTitle(tool: EditTool, variantLabel: String): String =
    if (tool == EditTool.EXTRUDE) "Extruir · $variantLabel" else tool.label
