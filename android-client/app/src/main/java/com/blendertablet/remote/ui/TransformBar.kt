package com.blendertablet.remote.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
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
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Link
import androidx.compose.material.icons.filled.LinkOff
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
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
import com.blendertablet.remote.model.ValueParser
import com.blendertablet.remote.model.stepsFor
import com.blendertablet.remote.model.scaleAxisStep
import com.blendertablet.remote.model.scaleValuesAfterAxisEdit
import kotlin.math.abs
import kotlin.math.roundToInt

private val AxisColors = mapOf(
    Axis.X to Color(0xFFE05B62),
    Axis.Y to Color(0xFF8BC34A),
    Axis.Z to Color(0xFF4A90D9),
)

/**
 * Barra de opciones de la transformación modal.
 *
 * La herramienta (Mover/Rotar/Escalar) la elige el rail; aquí viven sus opciones:
 * restricción (libre, eje o plano), orientación, incremento, valor exacto y las dos
 * salidas (confirmar/descartar). Sustituye al manipulador dibujado sobre el vídeo,
 * que tapaba el objeto y era demasiado fino para un dedo.
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
    onProportionalFalloff: () -> Unit,
    onConfirm: () -> Unit,
    onCancel: () -> Unit,
    modifier: Modifier = Modifier,
) {
    if (!session.active) return
    FloatingPanel(modifier) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            // Rótulo a la izquierda, como EditToolTray: el modo ya lo eligió el rail.
            Text(
                session.mode.label.uppercase(),
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
                if (canChangeSelection) {
                    PillButton(if (selectionPicking) "Toca la selección" else "Otra selección", selected = selectionPicking,
                        onClick = onChooseSelection)
                }
                if (session.proportional) {
                    key(session.sessionId) {
                        ProportionalRadiusInput(session.proportionalRadius, unitScaleLength,
                            proportionalUnit, proportionalRadiusStep, onProportionalRadiusValue)
                    }
                    PillButton("Perfil: ${falloffLabel(session.proportionalFalloff)}") {
                        onProportionalFalloff()
                    }
                }
                SnapCandidateHint(session)
                Divider()
                if (session.mode == TransformMode.MOVE) {
                    MovementControls(
                        session = session,
                        unitScaleLength = unitScaleLength,
                        moveStepValue = moveStepValue,
                        moveStepUnit = moveStepUnit,
                        constraint = constraint,
                        snapType = snapType,
                        orientation = orientation,
                        referencePicking = referencePicking,
                        availableOrientations = availableOrientations,
                        onConstraint = onConstraint,
                        onSnapType = onSnapType,
                        onSnapToSelection = onSnapToSelection,
                        onReference = onReference,
                        onMoveStep = onMoveStep,
                        onValue = onValue,
                        onOrientation = onOrientation,
                    )
                } else {
                    ParametricAxisInputs(
                        session, unitScaleLength, moveStepValue, moveStepUnit,
                        scaleStepValue, stepIndex, constraint, snapType,
                        scaleUnit, onConstraint, onValue, onFlatten,
                    )
                    when (session.mode) {
                        TransformMode.SCALE -> {
                            ScaleUnitPicker(scaleUnit) { onScaleStep(scaleStepValue, it) }
                            IconAction(AppIcons.Reset, "Restablecer escala a 100 %") {
                                onValue(listOf(1.0, 1.0, 1.0), null, null)
                            }
                            if (snapType == SnapType.INCREMENT) {
                                Divider()
                                ScaleStepInput(scaleStepValue, scaleUnit) { onScaleStep(it, scaleUnit) }
                            }
                        }
                        TransformMode.ROTATE -> {
                            IconAction(AppIcons.Reset, "Restablecer rotación a 0°") {
                                onValue(listOf(0.0, 0.0, 0.0), null, null)
                            }
                            if (snapType == SnapType.INCREMENT) {
                                StepPicker(session.mode, stepIndex, onStep)
                            }
                        }
                        TransformMode.MOVE -> Unit
                    }
                    Divider()
                    CenterReferencePicker(
                        session = session,
                        picking = referencePicking && referencePickingRole == "CENTER",
                        onPick = { onReference("CENTER") },
                        onPreset = onCenterPreset,
                    )
                    PillButton(
                        if (referencePicking && referencePickingRole == "SOURCE") "Fuente · señala"
                        else if (session.sourceLocked) "Fuente · fijada" else "Fuente",
                        selected = (referencePicking && referencePickingRole == "SOURCE") || session.sourceLocked,
                    ) { onReference("SOURCE") }
                    SnapPicker(session.mode, snapType, onSnapType)
                    PillButton(
                        "Propio",
                        selected = session.snapToSelection,
                    ) { onSnapToSelection(!session.snapToSelection) }
                    Divider()
                    OrientationPicker(availableOrientations, orientation, onOrientation)
                }
            }
            Spacer(Modifier.width(10.dp))
            // Confirmar y descartar, fijos a la derecha: son las dos únicas salidas
            // y no deben confundirse entre sí ni desplazarse con el scroll.
            RoundAction(Icons.Default.Close, "Descartar", Ink.Bad, onCancel)
            Spacer(Modifier.width(4.dp))
            RoundAction(Icons.Default.Check, "Confirmar", Ink.Ok, onConfirm)
        }
    }
}

/**
 * Sistema único de movimiento para Object y Edit.
 *
 * Todo consumidor de una sesión MOVE pasa por este componente: valores XYZ,
 * incremento, referencia, snap y orientación no se vuelven a implementar por modo.
 */
@Composable
fun MovementControls(
    session: TransformSession,
    unitScaleLength: Double,
    moveStepValue: Double,
    moveStepUnit: TransformStepUnit,
    constraint: Constraint,
    snapType: SnapType,
    orientation: Orientation,
    referencePicking: Boolean,
    availableOrientations: List<Orientation>,
    onConstraint: (Constraint) -> Unit,
    onSnapType: (SnapType) -> Unit,
    onSnapToSelection: (Boolean) -> Unit,
    onReference: (String) -> Unit,
    onMoveStep: (Double, TransformStepUnit) -> Unit,
    onValue: (List<Double>?, Double?, List<Double>?) -> Unit,
    onOrientation: (Orientation) -> Unit,
) {
    ParametricAxisInputs(
        session = session,
        unitScaleLength = unitScaleLength,
        stepValue = moveStepValue,
        stepUnit = moveStepUnit,
        scaleStepValue = 0.0,
        stepIndex = 0,
        constraint = constraint,
        snapType = snapType,
        scaleUnit = moveStepUnit,
        onConstraint = onConstraint,
        onValue = onValue,
    )
    IconAction(AppIcons.Reset, "Restablecer movimiento a 0") {
        onValue(listOf(0.0, 0.0, 0.0), null, null)
    }
    if (snapType == SnapType.INCREMENT) {
        MoveStepInput(moveStepValue, moveStepUnit, session.referenceLocked, onMoveStep)
    }
    Divider()
    PillButton(
        if (referencePicking) "REL · señala" else if (session.sourceLocked) "REL · fijada" else "REL",
        selected = referencePicking || session.sourceLocked,
    ) { onReference("SOURCE") }
    SnapControl(SnapType.forMode(TransformMode.MOVE), snapType, onSnapType)
    PillButton(
        "Propio",
        selected = session.snapToSelection,
    ) { onSnapToSelection(!session.snapToSelection) }
    Divider()
    OrientationPicker(availableOrientations, orientation, onOrientation)
}

@Composable
private fun MoveStepInput(
    value: Double,
    unit: TransformStepUnit,
    hasReference: Boolean,
    onChange: (Double, TransformStepUnit) -> Unit,
) {
    var text by remember(value) { mutableStateOf(format(value, 3)) }
    var expanded by remember { mutableStateOf(false) }
    fun commit(raw: String = text) {
        raw.replace(',', '.').toDoubleOrNull()?.takeIf { it > 0.0 }?.let { onChange(it, unit) }
    }
    PillButton("−", repeatOnHold = true) { onChange((value - 1.0).coerceAtLeast(0.001), unit) }
    CompactNumericField(
        value = text, onValueChange = { text = it }, modifier = Modifier.width(58.dp),
        textAlign = TextAlign.End, placeholder = "Paso", onDone = { commit() },
    )
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
    PillButton("+", repeatOnHold = true) { onChange(value + 1.0, unit) }
}

@Composable
private fun ParametricAxisInputs(
    session: TransformSession,
    unitScaleLength: Double,
    stepValue: Double,
    stepUnit: TransformStepUnit,
    scaleStepValue: Double,
    stepIndex: Int,
    constraint: Constraint,
    snapType: SnapType,
    scaleUnit: TransformStepUnit,
    onConstraint: (Constraint) -> Unit,
    onValue: (List<Double>?, Double?, List<Double>?) -> Unit,
    onFlatten: ((String) -> Unit)? = null,
) {
    var scaleLinked by remember(session.sessionId) { mutableStateOf(true) }
    if (session.mode == TransformMode.SCALE) {
        IconAction(
            icon = if (scaleLinked) Icons.Default.Link else Icons.Default.LinkOff,
            description = if (scaleLinked) "Dimensiones vinculadas" else "Dimensiones independientes",
            selected = scaleLinked,
        ) { scaleLinked = !scaleLinked }
        Axis.entries.forEach { axis ->
            PillButton("${axis.name}=0") { onFlatten?.invoke(axis.name) }
        }
    }
    val referenceDistance = session.referenceDistance ?: 0.0
    val step = when (session.mode) {
        TransformMode.MOVE -> {
            moveValueInBlenderUnits(stepValue, stepUnit, unitScaleLength, referenceDistance)
        }
        TransformMode.ROTATE -> stepsFor(session.mode)[stepIndex.coerceIn(0, stepsFor(session.mode).lastIndex)].step
        TransformMode.SCALE -> 0.0 // depende de la dimensión base de cada eje
    }
    Axis.entries.forEach { axis ->
        val index = axis.ordinal
        val current = session.values.getOrElse(index) {
            if (session.mode == TransformMode.SCALE) 1.0 else 0.0
        }
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
            mutableStateOf(format(displayed, 4))
        }
        LaunchedEffect(displayed, editing) {
            if (!editing) text = format(displayed, 4)
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
        Row(verticalAlignment = Alignment.CenterVertically) {
            val active = axis in constraint.axes
            Box(
                Modifier
                    .size(34.dp)
                    .clip(RoundedCornerShape(17.dp))
                    .background(if (active) AxisColors.getValue(axis).copy(alpha = .28f) else Color.Transparent)
                    .combinedClickable(
                        interactionSource = remember { MutableInteractionSource() },
                        indication = null,
                        onClick = {
                            onConstraint(if (active && constraint.axes.size == 1) Constraint.FREE
                            else Constraint.ofAxes(setOf(axis)))
                        },
                        onLongClick = {
                            val next = if (active) constraint.axes - axis else constraint.axes + axis
                            onConstraint(Constraint.ofAxes(next))
                        },
                    ),
                contentAlignment = Alignment.Center,
            ) {
                Text(axis.name, color = AxisColors.getValue(axis), fontSize = 13.sp,
                    fontWeight = FontWeight.Bold)
            }
            if (snapType == SnapType.INCREMENT) {
                PillButton("−", repeatOnHold = true) {
                    val next = current - axisStep
                    send(if (session.mode == TransformMode.SCALE && next < 0.0) current else next)
                }
            }
            CompactNumericField(
                value = text, onValueChange = { text = it }, modifier = Modifier.width(72.dp),
                textAlign = TextAlign.End, placeholder = axis.name,
                textColor = AxisColors.getValue(axis),
                onFocusChange = { editing = it },
                onDone = {
                    val parsed = when {
                        session.mode == TransformMode.SCALE -> ValueParser.parseScaleDimension(
                            text, scaleUnit, unitScaleLength,
                            session.baseDimensions.getOrElse(index) { 0.0 },
                        )
                        else -> ValueParser.parse(text, session.mode)
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
            if (snapType == SnapType.INCREMENT) {
                PillButton("+", repeatOnHold = true) { send(current + axisStep) }
            }
        }
    }
}

@Composable
private fun ProportionalRadiusInput(
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
    fun readDraft(): Double? = if (text == null) shown else ProportionalRadius.parse(text!!, unit, unitScaleLength)
    fun send(value: Double) {
        pending = if (abs(value-radius) <= tolerance) null else value
        text = null
        onRadius(value)
    }
    fun commit() {
        if (text != null) ProportionalRadius.parse(text!!, unit, unitScaleLength)?.let(::send)
    }
    fun adjust(direction: Int) {
        val current = readDraft() ?: return
        send(ProportionalRadius.step(current, direction, stepMeters, unitScaleLength))
    }
    Text("Radio", color = Ink.Muted, fontSize = 11.sp)
    PillButton("−", repeatOnHold = true) { adjust(-1) }
    CompactNumericField(
        value = text ?: formatToolDistance(displayed, 3),
        onValueChange = { text = it },
        placeholder = unit.short,
        textAlign = TextAlign.End,
        onDone = ::commit,
        modifier = Modifier.width(64.dp),
    )
    Text(unit.short, color = Ink.Muted, fontSize = 11.sp)
    PillButton("+", repeatOnHold = true) { adjust(1) }
}

private fun falloffLabel(value: String) = when (value) {
    "SPHERE" -> "Esfera"
    "ROOT" -> "Raíz"
    "SHARP" -> "Agudo"
    "LINEAR" -> "Lineal"
    "CONSTANT" -> "Constante"
    "INVERSE_SQUARE" -> "Inv. cuadrado"
    else -> "Suave"
}

/**
 * A qué se está pegando el movimiento ahora mismo.
 *
 * Va en una línea propia bajo el marcador y no encima del vídeo: el plan pide ver el
 * candidato **sin tapar la selección**.
 */
@Composable
private fun SnapCandidateHint(session: TransformSession) {
    val candidate = session.snapCandidate ?: return
    val target = candidate.objectName?.let { "$it · ${candidate.type.label}" } ?: candidate.type.label
    Text("⇥ $target", color = Ink.Ok, fontSize = 11.sp)
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
        picking -> "REL · señala"
        session.centerMode == "OBJECT_ORIGIN" -> "REL · origen"
        session.centerMode == "CURSOR" -> "REL · cursor"
        session.centerMode == "PICKED" -> "REL · punto"
        else -> "REL · selección"
    }
    Box {
        PillButton(label, selected = picking || session.centerLocked) { expanded = true }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            DropdownMenuItem(
                text = { Text("Centro de selección") },
                onClick = { expanded = false; onPreset("SELECTION") },
            )
            DropdownMenuItem(
                text = { Text("Señalar punto") },
                onClick = { expanded = false; onPick() },
            )
            DropdownMenuItem(
                text = { Text("Origen del objeto") },
                onClick = { expanded = false; onPreset("OBJECT_ORIGIN") },
            )
            DropdownMenuItem(
                text = { Text("Cursor 3D") },
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

/**
 * Tipo de snap. El desplegable solo contiene los válidos para el modo: los
 * geométricos forman fuente→destino en MOVE y centro→fuente→destino en ROTATE/SCALE.
 */
@Composable
private fun SnapPicker(mode: TransformMode, selected: SnapType, onSelect: (SnapType) -> Unit) {
    SnapControl(SnapType.forMode(mode), selected, onSelect)
}

/** Cuánto avanza cada incremento: milímetros, centímetros, metros, grados o factor. */
@Composable
private fun StepPicker(mode: TransformMode, index: Int, onStep: (Int) -> Unit) {
    val steps = stepsFor(mode)
    val safe = index.coerceIn(0, steps.lastIndex)
    Box(
        Modifier
            .height(34.dp)
            .clip(RoundedCornerShape(9.dp))
            .background(Color.White.copy(alpha = .05f))
            // Cicla en vez de desplegar: son cuatro valores y un menú por cada
            // cambio de incremento sería un estorbo a mitad de transformación.
            .clickableNoRipple { onStep((safe + 1) % steps.size) }
            .padding(horizontal = 10.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(steps[safe].label, color = Ink.Muted, fontSize = 13.sp)
    }
}

@Composable
private fun Divider() {
    Box(
        Modifier
            .padding(horizontal = 3.dp)
            .width(1.dp)
            .height(24.dp)
            .background(Ink.Divider),
    )
}

private fun format(value: Double, decimals: Int): String {
    val factor = if (decimals == 1) 10.0 else 1000.0
    val rounded = (value * factor).roundToInt() / factor
    if (abs(rounded) < 1e-9) return "0"
    return if (decimals == 1) "%.1f".format(rounded) else rounded.toString()
}
