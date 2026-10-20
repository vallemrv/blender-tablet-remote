package com.blendertablet.remote.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.key
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.blendertablet.remote.model.Axis
import com.blendertablet.remote.model.Constraint
import com.blendertablet.remote.model.LengthUnit
import com.blendertablet.remote.model.ProportionalRadius
import com.blendertablet.remote.model.transformStepUnit
import com.blendertablet.remote.model.Orientation
import com.blendertablet.remote.model.SnapType
import com.blendertablet.remote.model.TransformMode
import com.blendertablet.remote.model.TransformSession
import com.blendertablet.remote.model.TransformStepUnit
import com.blendertablet.remote.model.moveValueForDisplay
import com.blendertablet.remote.model.moveValueInBlenderUnits
import com.blendertablet.remote.model.ValueMode
import com.blendertablet.remote.model.NumericExpression
import com.blendertablet.remote.model.ValueParser
import com.blendertablet.remote.model.stepsFor
import com.blendertablet.remote.model.scaleAxisStep
import com.blendertablet.remote.model.scaleValuesAfterAxisEdit
import kotlin.math.abs
import kotlin.math.roundToInt

private val AxisColors = mapOf(Axis.X to Ink.AxisX, Axis.Y to Ink.AxisY, Axis.Z to Ink.AxisZ)

/**
 * Bandeja de la transformación modal (Mover/Rotar/Escalar).
 *
 * Tres niveles: siempre X/Y/Z deslizables; a veces Snap, restricción de eje y, en
 * Escalar, la cadena; casi nunca, en «⋯ Más», paso y unidad (Precisión), centro,
 * fuente, orientación y otra selección (Referencia) y edición proporcional (Forma).
 *
 * La transformación **no termina al soltar el dedo**: se confirma con ✓ o se descarta
 * con ✗, para poder recolocar la mano a mitad de un desplazamiento largo.
 */
@Composable
fun TransformBar(
    session: TransformSession,
    unitScaleLength: Double,
    proportionalUnit: LengthUnit,
    proportionalRadiusStep: Double,
    stepIndex: Int,
    snapType: SnapType,
    constraint: Constraint,
    orientation: Orientation,
    valueMode: ValueMode,
    referencePicking: Boolean,
    referencePickingRole: String,
    canChangeSelection: Boolean,
    selectionPicking: Boolean,
    onChooseSelection: () -> Unit,
    moveStepValue: Double,
    moveStepUnit: TransformStepUnit,
    scaleStepValue: Double,
    scaleUnit: TransformStepUnit,
    availableOrientations: List<Orientation>,
    onConstraint: (Constraint) -> Unit,
    onOrientation: (Orientation) -> Unit,
    onSnapType: (SnapType) -> Unit,
    onSnapToSelection: (Boolean) -> Unit,
    onStep: (Int) -> Unit,
    onValueMode: (ValueMode) -> Unit,
    onReference: (String) -> Unit,
    onCenterPreset: (String) -> Unit,
    onMoveStep: (Double, TransformStepUnit) -> Unit,
    onScaleStep: (Double, TransformStepUnit) -> Unit,
    onFlatten: (String) -> Unit,
    onValue: (List<Double>?, Double?, List<Double>?) -> Unit,
    onProportionalRadiusValue: (Double) -> Unit,
    onProportionalFalloff: (String) -> Unit,
    proportionalAvailable: Boolean,
    onProportional: () -> Unit,
    onConfirm: () -> Unit,
    onCancel: () -> Unit,
    modifier: Modifier = Modifier,
) {
    if (!session.active) return
    var scaleLinked by remember(session.sessionId) { mutableStateOf(true) }
    val individual = session.centerMode == "INDIVIDUAL"
    val snapOptions = if (session.mode != TransformMode.MOVE && individual) listOf(SnapType.NONE, SnapType.INCREMENT)
        else SnapType.forMode(session.mode)
    val picking = when {
        selectionPicking -> "Toca la nueva selección en la vista"
        referencePicking && referencePickingRole == "CENTER" -> "Señala el centro en la vista"
        referencePicking -> "Señala la fuente en la vista"
        else -> null
    }
    val candidate = session.snapCandidate?.let { c -> "⇥ " + (c.objectName?.let { "$it · ${c.type.label}" } ?: c.type.label) }
    val neutral = if (session.mode == TransformMode.SCALE) 1.0 else 0.0
    val more = TrayMore(
        precision = {
            when (session.mode) {
                TransformMode.MOVE -> TrayOption("Paso", "Cuánto avanza cada salto con Incremento y al deslizar los números. " +
                    "La unidad gobierna también X, Y y Z.") {
                    MoveStepInput(moveStepValue, moveStepUnit, session.referenceLocked, onMoveStep)
                }
                TransformMode.ROTATE -> TrayOption("Paso", "Grados de cada salto con Incremento y al deslizar los números.") {
                    StepPicker(session.mode, stepIndex, onStep)
                }
                TransformMode.SCALE -> {
                    TrayOption("Unidad", "Dimensiones en mm, cm o m, o factor en %.") {
                        ScaleUnitPicker(scaleUnit) { onScaleStep(scaleStepValue, it) }
                    }
                    TrayOption("Paso", "Cuánto cambia cada salto con Incremento y al deslizar los números.") {
                        ScaleStepInput(scaleStepValue, scaleUnit) { onScaleStep(it, scaleUnit) }
                    }
                }
            }
            TrayOption("Restablecer", "Devuelve la vista previa a " + when (session.mode) {
                TransformMode.MOVE -> "0"; TransformMode.ROTATE -> "0°"; TransformMode.SCALE -> "100 %" } +
                " sin cerrar la herramienta. Mantener pulsado un número restablece solo ese eje.") {
                IconAction(AppIcons.Reset, "Restablecer") { onValue(List(3) { neutral }, null, null) }
            }
        },
        reference = {
            if (session.mode != TransformMode.MOVE) TrayOption("Centro", "Punto alrededor del que se gira o escala.") {
                CenterReferencePicker(session, referencePicking && referencePickingRole == "CENTER",
                    onPick = { onReference("CENTER") }, onPreset = onCenterPreset)
            }
            if (session.mode == TransformMode.MOVE || !individual) {
                val sourcePicking = referencePicking && referencePickingRole == "SOURCE"
                TrayOption("Fuente", "Punto de la selección que se lleva hasta el destino del snap.") {
                    PillButton(if (sourcePicking) "Señala…" else if (session.sourceLocked) "Fijada" else "Elegir",
                        selected = sourcePicking || session.sourceLocked) { onReference("SOURCE") }
                }
                TrayOption("Propio", "Permite usar la propia selección como destino del snap.") {
                    PillButton(if (session.snapToSelection) "Incluido" else "Excluido", selected = session.snapToSelection) {
                        onSnapToSelection(!session.snapToSelection)
                    }
                }
            }
            TrayOption("Orientación", "Ejes con los que se interpretan X, Y y Z.") {
                OrientationPicker(availableOrientations, orientation, onOrientation)
            }
            if (canChangeSelection) TrayOption("Otra selección", "Confirma este paso y continúa con otra selección.") {
                PillButton(if (selectionPicking) "Toca…" else "Elegir", selected = selectionPicking, onClick = onChooseSelection)
            }
        },
        shape = if (!proportionalAvailable) null else ({
            TrayOption("Proporcional", "Mueve también los vecinos dentro del radio, con el perfil elegido.") {
                IconAction(AppIcons.Proportional, "Edición proporcional", selected = session.proportional, onClick = onProportional)
            }
            if (session.proportional) {
                TrayOption("Radio", "Alcance de la influencia.") {
                    key(session.sessionId) {
                        ProportionalRadiusInput(session.proportionalRadius, unitScaleLength,
                            proportionalUnit, proportionalRadiusStep, onProportionalRadiusValue)
                    }
                }
                TrayOption("Perfil", "Cómo cae la influencia hacia el borde del radio.") {
                    FalloffChoice(session.proportionalFalloff, onProportionalFalloff)
                }
            }
        }),
    )
    SingleLineTray(
        title = session.mode.label, onCancel = onCancel, onConfirm = onConfirm, modifier = modifier,
        help = "Arrastra para ${session.mode.label.lowercase()} · desliza un número para afinarlo, tócalo para escribir " +
            "y mantenlo para restablecer · cambiar de herramienta aplica el resultado",
        hintKey = "transform.${session.mode.name}", status = picking ?: candidate, more = more,
    ) {
        TransformAxisInputs(session, unitScaleLength, moveStepValue, moveStepUnit, scaleStepValue, stepIndex,
            scaleUnit, scaleLinked, onValue, onFlatten)
        if (session.mode == TransformMode.SCALE) IconAction(AppIcons.chain(scaleLinked),
            if (scaleLinked) "Dimensiones vinculadas" else "Dimensiones independientes", selected = scaleLinked) {
            scaleLinked = !scaleLinked
        }
        SnapControl(snapOptions, snapType, onSnapType)
        AxisConstraintButtons(constraint, onSelect = onConstraint)
    }
}

@Composable
private fun MoveStepInput(
    value: Double,
    unit: TransformStepUnit,
    hasReference: Boolean,
    onChange: (Double, TransformStepUnit) -> Unit,
) {
    var text by remember(value) { mutableStateOf(format(value)) }
    var expanded by remember { mutableStateOf(false) }
    fun commit(raw: String = text) {
        NumericExpression.evaluate(raw, value)?.takeIf { it > 0.0 }?.let { onChange(it, unit) }
    }
    var base by remember { mutableStateOf(value) }
    HoverHelp("Paso", numberHelp(false)) {
        ScrubNumber(onScrubStart = { base = value },
            onScrub = { steps -> onChange((base + steps).coerceAtLeast(0.001), unit) }) { field ->
            CompactNumericField(
                value = text, onValueChange = { text = it }, modifier = field.width(104.dp), fontSize = 16.sp,
                textAlign = TextAlign.End, placeholder = "Paso", caption = "Paso", selectAllOnFocus = true,
                onDone = { commit() },
            )
        }
    }
    Box {
        PillButton(unit.label) { expanded = true }
        DropdownMenu(expanded, { expanded = false }) {
            TransformStepUnit.entries.forEach { option ->
                val enabled = option != TransformStepUnit.PERCENT || hasReference
                DropdownMenuItem(
                    text = { Text(option.label) }, enabled = enabled,
                    onClick = { expanded = false; onChange(value, option) },
                )
            }
        }
    }
}

/**
 * X, Y y Z de cualquier transformación: deslizar avanza por el paso de la sesión,
 * tocar escribe el valor exacto y mantener restablece ese eje.
 */
@Composable
private fun TransformAxisInputs(
    session: TransformSession,
    unitScaleLength: Double,
    stepValue: Double,
    stepUnit: TransformStepUnit,
    scaleStepValue: Double,
    stepIndex: Int,
    scaleUnit: TransformStepUnit,
    scaleLinked: Boolean,
    onValue: (List<Double>?, Double?, List<Double>?) -> Unit,
    onFlatten: ((String) -> Unit)? = null,
) {
    val referenceDistance = session.referenceDistance ?: 0.0
    val step = when (session.mode) {
        TransformMode.MOVE -> {
            moveValueInBlenderUnits(stepValue, stepUnit, unitScaleLength, referenceDistance)
        }
        TransformMode.ROTATE -> stepsFor(session.mode)[stepIndex.coerceIn(0, stepsFor(session.mode).lastIndex)].step
        TransformMode.SCALE -> 0.0 // depende de la dimensión base de cada eje
    }
    val neutral = if (session.mode == TransformMode.SCALE) 1.0 else 0.0
    val suffix = when (session.mode) {
        TransformMode.MOVE -> stepUnit.label
        TransformMode.ROTATE -> "°"
        TransformMode.SCALE -> scaleUnit.label
    }
    Axis.entries.forEach { axis ->
        val index = axis.ordinal
        val current = session.values.getOrElse(index) { neutral }
        val displayed = when (session.mode) {
            TransformMode.MOVE ->
                moveValueForDisplay(current, stepUnit, unitScaleLength, referenceDistance)
            TransformMode.ROTATE -> Math.toDegrees(current)
            TransformMode.SCALE -> if (scaleUnit == TransformStepUnit.PERCENT) current * 100.0 else {
                val physical = session.dimensions.getOrElse(index) { 0.0 } * unitScaleLength
                when (scaleUnit) {
                    TransformStepUnit.MM -> physical * 1000.0
                    TransformStepUnit.CM -> physical * 100.0
                    TransformStepUnit.M -> physical
                    TransformStepUnit.PERCENT -> current * 100.0
                }
            }
        }
        var editing by remember(session.sessionId, axis) { mutableStateOf(false) }
        var text by remember(session.sessionId, axis, if (session.mode == TransformMode.SCALE) scaleUnit else null) {
            mutableStateOf(format(displayed))
        }
        LaunchedEffect(displayed, editing) {
            if (!editing) text = format(displayed)
        }
        fun send(value: Double) {
            if (session.mode == TransformMode.SCALE && value == 0.0 && onFlatten != null) {
                onFlatten(axis.name)
                return
            }
            val next = if (session.mode == TransformMode.SCALE) {
                scaleValuesAfterAxisEdit(session.values, index, value, scaleLinked)
            } else session.values.toMutableList().also { it[index] = value }
            onValue(next, null, null)
        }
        val axisStep = if (session.mode == TransformMode.SCALE) scaleAxisStep(
            scaleStepValue, scaleUnit, unitScaleLength,
            session.baseDimensions.getOrElse(index) { 0.0 },
        ) else step
        var base by remember(session.sessionId, axis) { mutableStateOf(current) }
        HoverHelp("${session.mode.label} en ${axis.name}", numberHelp(true)) {
            ScrubNumber(
                onScrubStart = { base = session.values.getOrElse(index) { neutral } },
                onScrub = { steps ->
                    val next = base + steps * axisStep
                    // Deslizar no aplana: el cero exacto de Escalar se escribe a propósito.
                    if (session.mode != TransformMode.SCALE || next > 0.0) send(next)
                },
                onReset = {
                    if (session.mode == TransformMode.SCALE && scaleLinked) onValue(listOf(1.0, 1.0, 1.0), null, null)
                    else send(neutral)
                },
            ) { field ->
                CompactNumericField(
                    value = text, onValueChange = { text = it }, modifier = field.width(112.dp),
                    textAlign = TextAlign.End, placeholder = axis.name, fontSize = 16.sp,
                    caption = axis.name, captionColor = AxisColors.getValue(axis), suffix = suffix,
                    selectAllOnFocus = true,
                    onFocusChange = { editing = it },
                    onDone = {
                        val parsed = when {
                            session.mode == TransformMode.SCALE -> ValueParser.parseScaleDimension(
                                text, scaleUnit, unitScaleLength,
                                session.baseDimensions.getOrElse(index) { 0.0 },
                                displayed,
                            )
                            else -> ValueParser.parse(text, session.mode, displayed)
                        }
                        parsed?.let {
                            send(when (session.mode) {
                                TransformMode.MOVE -> moveValueInBlenderUnits(
                                    it, stepUnit, unitScaleLength, referenceDistance,
                                )
                                TransformMode.ROTATE -> Math.toRadians(it)
                                TransformMode.SCALE -> it
                            })
                        }
                    },
                )
            }
        }
    }
}

@Composable
internal fun ProportionalRadiusInput(
    radius: Double,
    unitScaleLength: Double,
    unit: LengthUnit,
    stepMeters: Double,
    onRadius: (Double) -> Unit,
) {
    var text by remember(unit, unitScaleLength) { mutableStateOf<String?>(null) }
    var pending by remember(unitScaleLength) { mutableStateOf<Double?>(null) }
    val tolerance = maxOf(1e-7, abs(radius) * 1e-6)
    LaunchedEffect(radius) {
        if (pending?.let { abs(it-radius) <= tolerance } == true) pending = null
    }
    val shown = pending ?: radius
    val displayed = moveValueForDisplay(shown, unit.transformStepUnit(), unitScaleLength)
    fun readDraft(): Double? = if (text == null) shown else ProportionalRadius.parse(text!!, unit, unitScaleLength, shown)
    fun send(value: Double) {
        pending = if (abs(value-radius) <= tolerance) null else value
        text = null
        onRadius(value)
    }
    fun commit() {
        if (text != null) ProportionalRadius.parse(text!!, unit, unitScaleLength, shown)?.let(::send)
    }
    var base by remember { mutableStateOf(shown) }
    HoverHelp("Radio proporcional", numberHelp(false)) {
        ScrubNumber(onScrubStart = { base = readDraft() ?: shown }, onScrub = { steps ->
            var next = base
            repeat(abs(steps)) { next = ProportionalRadius.step(next, if (steps < 0) -1 else 1, stepMeters, unitScaleLength) }
            send(next)
        }) { field ->
            CompactNumericField(
                value = text ?: formatToolDistance(displayed, MaxDecimals),
                onValueChange = { text = it },
                placeholder = unit.short,
                textAlign = TextAlign.End,
                onDone = ::commit,
                fontSize = 16.sp, selectAllOnFocus = true, caption = "Radio", suffix = unit.short,
                modifier = field.width(120.dp),
            )
        }
    }
}


/**
 * Restricción con los botones Libre · X · Y · Z siempre a la vista. Tocar un eje lo
 * deja solo (otra vez, vuelve a Libre); mantenerlo pulsado bloquea los otros dos,
 * como Shift+Z en Blender: mantener Z deja el plano XY. [planes] falso solo admite ejes.
 */
@Composable
internal fun AxisConstraintButtons(selected: Constraint, enabled: Boolean = true, planes: Boolean = true,
                                   onSelect: (Constraint) -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(2.dp), verticalAlignment = Alignment.CenterVertically) {
        val free = selected == Constraint.FREE
        HoverHelp("Libre", "Sin restricción: sigue al dedo.", enabled = enabled) {
            Box(Modifier.height(Metrics.Touch).clip(RoundedCornerShape(10.dp))
                .background(if (free) Ink.Accent.copy(alpha = .22f) else Color.Transparent)
                .then(if (enabled) Modifier.clickableNoRipple { onSelect(Constraint.FREE) } else Modifier)
                .padding(horizontal = 10.dp), contentAlignment = Alignment.Center) {
                Text("Libre", color = if (!enabled) Ink.Faint else if (free) Ink.Accent else Ink.Muted,
                    fontSize = 13.sp, fontWeight = if (free) FontWeight.SemiBold else FontWeight.Normal)
            }
        }
        Axis.entries.forEach { axis ->
            val active = axis in selected.axes
            val color = AxisColors.getValue(axis)
            HoverHelp("Eje ${axis.name}", "Toca para mover solo en ${axis.name}" +
                if (planes) "; mantén pulsado para bloquear los otros dos ejes (como Shift+${axis.name})." else ".",
                enabled = enabled) {
                Box(Modifier.size(Metrics.Touch).clip(RoundedCornerShape(10.dp))
                    .background(if (active) color.copy(alpha = .28f) else Color.Transparent)
                    .then(if (!enabled) Modifier else Modifier.combinedClickable(
                        interactionSource = remember { MutableInteractionSource() }, indication = null,
                        onClick = { onSelect(constraintAfterTap(selected, axis)) },
                        onLongClick = if (planes) ({ onSelect(constraintAfterHold(selected, axis)) }) else null)),
                    contentAlignment = Alignment.Center) {
                    Text(axis.name, color = if (enabled) color else Ink.Faint, fontSize = 15.sp,
                        fontWeight = if (active) FontWeight.Bold else FontWeight.Normal)
                }
            }
        }
    }
}

/** Tocar un eje lo deja solo; tocar el eje que ya está solo vuelve a Libre. */
internal fun constraintAfterTap(current: Constraint, axis: Axis): Constraint {
    val only = Constraint.ofAxes(setOf(axis))
    return if (current == only) Constraint.FREE else only
}

/** Mantener un eje bloquea los otros dos (Shift+eje); repetirlo vuelve a Libre. */
internal fun constraintAfterHold(current: Constraint, axis: Axis): Constraint {
    val plane = Constraint.ofAxes(Axis.entries.toSet() - axis)
    return if (current == plane) Constraint.FREE else plane
}

internal fun constraintLabel(value: Constraint) = when (value) {
    Constraint.FREE -> "Libre"
    Constraint.X, Constraint.Y, Constraint.Z -> "Solo eje ${value.name}"
    else -> "Plano ${value.name}"
}

internal fun orientationLabel(wire: String) = when (wire) {
    "LOCAL" -> "Local"; "VIEW" -> "Vista"; "NORMAL" -> "Normal"; else -> "Global"
}

/** Perfil de la edición proporcional: el icono es su curva; al tocarlo se elige otro. */
@Composable
internal fun FalloffChoice(selected: String, onSelect: (String) -> Unit, enabled: Boolean = true) {
    ChoiceIcon(com.blendertablet.remote.model.ProportionalFalloffs, selected, "Perfil", AppIcons::falloff,
        ::falloffLabel, enabled = enabled, onSelect = onSelect)
}

internal fun falloffLabel(value: String) = when (value) {
    "SPHERE" -> "Esfera"
    "ROOT" -> "Raíz"
    "SHARP" -> "Agudo"
    "LINEAR" -> "Lineal"
    "CONSTANT" -> "Constante"
    "INVERSE_SQUARE" -> "Inv. cuadrado"
    else -> "Suave"
}

@Composable
private fun CenterReferencePicker(
    session: TransformSession,
    picking: Boolean,
    onPick: () -> Unit,
    onPreset: (String) -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }
    val label = when {
        picking -> "Señala…"
        session.centerMode == "OBJECT_ORIGIN" -> "Origen del objeto"
        session.centerMode == "CURSOR" -> "Cursor 3D"
        session.centerMode == "PICKED" -> "Punto señalado"
        session.centerMode == "INDIVIDUAL" -> "Orígenes individuales"
        else -> "Punto medio"
    } + " ▾"
    Box {
        PillButton(label, selected = picking || session.centerMode != "SELECTION") { expanded = true }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            DropdownMenuItem(
                text = { Text("Punto medio de la selección") },
                trailingIcon = { if (session.centerMode == "SELECTION") Icon(AppIcons.Confirm, "Seleccionado", tint = Ink.Accent) },
                onClick = { expanded = false; onPreset("SELECTION") },
            )
            DropdownMenuItem(
                text = { Text("Orígenes individuales") },
                trailingIcon = { if (session.centerMode == "INDIVIDUAL") Icon(AppIcons.Confirm, "Seleccionado", tint = Ink.Accent) },
                onClick = { expanded = false; onPreset("INDIVIDUAL") },
            )
            DropdownMenuItem(
                text = { Text("Señalar punto") },
                trailingIcon = { if (session.centerMode == "PICKED") Icon(AppIcons.Confirm, "Seleccionado", tint = Ink.Accent) },
                onClick = { expanded = false; onPick() },
            )
            DropdownMenuItem(
                text = { Text("Origen del objeto") },
                trailingIcon = { if (session.centerMode == "OBJECT_ORIGIN") Icon(AppIcons.Confirm, "Seleccionado", tint = Ink.Accent) },
                onClick = { expanded = false; onPreset("OBJECT_ORIGIN") },
            )
            DropdownMenuItem(
                text = { Text("Cursor 3D") },
                trailingIcon = { if (session.centerMode == "CURSOR") Icon(AppIcons.Confirm, "Seleccionado", tint = Ink.Accent) },
                onClick = { expanded = false; onPreset("CURSOR") },
            )
        }
    }
}

/** Orientación de los ejes. Solo se ofrecen las que el contexto declara válidas. */
@Composable
private fun OrientationPicker(
    available: List<Orientation>,
    selected: Orientation,
    onSelect: (Orientation) -> Unit,
) {
    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        for (orientation in available) {
            PillButton(orientation.label, selected = orientation == selected) { onSelect(orientation) }
        }
    }
}

/** Cuánto avanza cada incremento: los pasos del modo, visibles a la vez en «⋯ Más». */
@Composable
private fun StepPicker(mode: TransformMode, index: Int, onStep: (Int) -> Unit) {
    val steps = stepsFor(mode)
    val safe = index.coerceIn(0, steps.lastIndex)
    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        steps.forEachIndexed { i, step -> PillButton(step.label, selected = i == safe) { onStep(i) } }
    }
}

private fun format(value: Double): String = formatToolDistance(value, MaxDecimals)
