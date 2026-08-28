package com.blendertablet.remote.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.ExperimentalFoundationApi
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
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material.icons.filled.GridOn
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
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
import com.blendertablet.remote.model.EditSettings
import com.blendertablet.remote.model.Orientation
import com.blendertablet.remote.model.SnapType
import com.blendertablet.remote.model.TransformMode
import com.blendertablet.remote.model.TransformSession
import com.blendertablet.remote.model.ValueMode
import com.blendertablet.remote.model.ValueParser
import com.blendertablet.remote.model.stepsFor
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
    editSettings: EditSettings,
    stepIndex: Int,
    snapType: SnapType,
    constraint: Constraint,
    orientation: Orientation,
    valueMode: ValueMode,
    availableOrientations: List<Orientation>,
    onConstraint: (Constraint) -> Unit,
    onOrientation: (Orientation) -> Unit,
    onSnapType: (SnapType) -> Unit,
    onStep: (Int) -> Unit,
    onValueMode: (ValueMode) -> Unit,
    onValue: (List<Double>?, Double?) -> Unit,
    onProportionalRadius: (Double) -> Unit,
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
                Readout(session)
                if (session.proportional) {
                    PillButton("Radio −") { onProportionalRadius(0.5) }
                    ProportionalRadiusInput(editSettings.radius, onProportionalRadiusValue)
                    PillButton("Radio +") { onProportionalRadius(2.0) }
                    PillButton("Perfil: ${falloffLabel(editSettings.falloff)}") {
                        onProportionalFalloff()
                    }
                }
                SnapCandidateHint(session)
                Divider()
                // Restricción: libre, eje o plano. En ROTATE solo ejes simples.
                ConstraintPicker(
                    mode = session.mode,
                    selected = constraint,
                    onSelect = onConstraint,
                )
                Divider()
                OrientationPicker(availableOrientations, orientation, onOrientation)
                Divider()
                SnapPicker(session.mode, snapType, onSnapType)
                // El paso solo significa algo si el snap cuadra a un incremento; en
                // un snap a vértice manda la geometría, no una cifra.
                if (snapType == SnapType.INCREMENT || snapType == SnapType.GRID) {
                    StepPicker(session.mode, stepIndex, onStep)
                }
                Divider()
                ValueModePicker(valueMode, onValueMode)
                ValueInput(session, onValue)
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

@Composable
private fun ProportionalRadiusInput(radius: Double, onRadius: (Double) -> Unit) {
    var text by remember(radius) { mutableStateOf(format(radius, 3)) }
    fun commit() {
        val parsed = ValueParser.parse(text, TransformMode.MOVE)
        if (parsed != null && parsed > 0.0) onRadius(parsed)
        else text = format(radius, 3)
    }
    CompactNumericField(
        value = text,
        onValueChange = { text = it },
        placeholder = "25cm",
        textAlign = TextAlign.End,
        onDone = ::commit,
        modifier = Modifier.width(64.dp),
    )
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

/** Cuánto se lleva movido/girado/escalado. Es la razón de ser de la barra. */
@Composable
private fun Readout(session: TransformSession) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        if (session.mode == TransformMode.ROTATE) {
            Text(
                "${format(session.angle, 1)}°",
                color = Ink.Accent,
                fontSize = 20.sp,
                fontWeight = FontWeight.SemiBold,
            )
        } else {
            for (axis in Axis.entries) {
                val value = session.values.getOrElse(axis.ordinal) { 0.0 }
                // Un eje descartado por la restricción se apaga en vez de desaparecer:
                // así la fila no cambia de ancho al tocar los botones de restricción.
                val muted = session.axes.isNotEmpty() && axis !in session.axes
                Text(
                    "${axis.name} ${format(value, 3)}",
                    color = if (muted) Ink.Faint else AxisColors.getValue(axis),
                    fontSize = 17.sp,
                    fontWeight = if (muted) FontWeight.Normal else FontWeight.SemiBold,
                    modifier = Modifier.padding(horizontal = 7.dp),
                )
            }
        }
    }
}

/**
 * Selector mínimo: solo X/Y/Z. Un toque elige un único eje (o lo libera si ya estaba
 * elegido); una pulsación larga añade/quita ejes para formar planos sin seis botones
 * extra. Rotar conserva por definición un único eje.
 */
@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun ConstraintPicker(mode: TransformMode, selected: Constraint, onSelect: (Constraint) -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        for (axis in Axis.entries) {
            val active = axis in selected.axes
            Box(
                Modifier
                    .size(38.dp)
                    .clip(RoundedCornerShape(19.dp))
                    .background(if (active) AxisColors.getValue(axis).copy(alpha = .28f) else Color.White.copy(alpha = .05f))
                    .combinedClickable(
                        interactionSource = remember { MutableInteractionSource() },
                        indication = null,
                        onClick = {
                            onSelect(if (active && selected.axes.size == 1) Constraint.FREE else Constraint.ofAxes(setOf(axis)))
                        },
                        onLongClick = {
                            if (mode == TransformMode.ROTATE) onSelect(Constraint.ofAxes(setOf(axis)))
                            else {
                                val next = if (active) selected.axes - axis else selected.axes + axis
                                onSelect(Constraint.ofAxes(next))
                            }
                        },
                    ),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    axis.name,
                    color = if (active) AxisColors.getValue(axis) else Ink.Muted,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Bold,
                )
            }
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
 * geométricos existen únicamente en MOVE, así que al rotar y escalar solo ofrece
 * libre, incremento y rejilla. Enseñar más sería enseñar algo que el servidor
 * rechaza.
 */
@Composable
private fun SnapPicker(mode: TransformMode, selected: SnapType, onSelect: (SnapType) -> Unit) {
    val options = SnapType.forMode(mode)
    val active = selected != SnapType.NONE
    var expanded by remember(mode) { mutableStateOf(false) }

    Box {
        Row(
            Modifier
                .height(Metrics.Touch)
                .clip(RoundedCornerShape(10.dp))
                .background(if (active) Ink.Accent.copy(alpha = .22f) else Color.White.copy(alpha = .05f))
                .clickableNoRipple { expanded = true }
                .padding(start = 10.dp, end = 5.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                Icons.Default.GridOn,
                if (active) "Snap: ${selected.label}" else "Snap desactivado",
                Modifier.size(16.dp),
                tint = if (active) Ink.Accent else Ink.Muted,
            )
            Spacer(Modifier.width(5.dp))
            Text(selected.label, color = if (active) Ink.Accent else Ink.Muted, fontSize = 12.sp)
            Icon(
                Icons.Default.ArrowDropDown,
                "Abrir tipos de snap",
                Modifier.size(18.dp),
                tint = if (active) Ink.Accent else Ink.Muted,
            )
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            for (option in options) {
                DropdownMenuItem(
                    text = { Text(option.label) },
                    leadingIcon = {
                        if (option == selected) {
                            Icon(Icons.Default.Check, null, tint = Ink.Accent)
                        }
                    },
                    onClick = {
                        expanded = false
                        onSelect(option)
                    },
                )
            }
        }
    }
}

/** Relativo (cuánto se mueve) o absoluto (a dónde va). Cambia qué significa el valor. */
@Composable
private fun ValueModePicker(selected: ValueMode, onSelect: (ValueMode) -> Unit) {
    val next = if (selected == ValueMode.RELATIVE) ValueMode.ABSOLUTE else ValueMode.RELATIVE
    PillButton(
        if (selected == ValueMode.RELATIVE) "Δ rel" else "= abs",
        selected = selected == ValueMode.ABSOLUTE,
    ) { onSelect(next) }
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

/**
 * Valor exacto. Acepta unidades (`4m`, `25cm`, `3mm`), grados (`45°`) y porcentajes
 * (`50%`): el parser devuelve metros, grados o factor según el modo. Sin restricción
 * el número se aplica a los tres ejes; con un eje o plano, solo a los elegidos.
 */
@Composable
private fun ValueInput(session: TransformSession, onValue: (List<Double>?, Double?) -> Unit) {
    var text by remember(session.mode) { mutableStateOf("") }
    // Al cerrar y reabrir la sesión el campo debe quedar limpio, no con lo anterior.
    LaunchedEffect(session.active) { if (!session.active) text = "" }

    fun commit() {
        val parsed = ValueParser.parse(text, session.mode) ?: return
        if (session.mode == TransformMode.ROTATE) {
            onValue(null, parsed)
        } else {
            // El número se aplica a los ejes activos; sin restricción, a los tres.
            val neutral = if (session.mode == TransformMode.SCALE) 1.0 else 0.0
            val values = Axis.entries.map { axis ->
                if (session.axes.isEmpty() || axis in session.axes) parsed else neutral
            }
            onValue(values, null)
        }
        text = ""
    }

    CompactNumericField(
        value = text,
        onValueChange = { text = it },
        placeholder = "4m · 25cm · 45° · 50%",
        textAlign = TextAlign.End,
        onDone = { commit() },
        modifier = Modifier.width(118.dp),
    )
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
