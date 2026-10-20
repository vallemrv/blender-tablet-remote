package com.blendertablet.remote.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.input.pointer.AwaitPointerEventScope
import androidx.compose.ui.input.pointer.PointerId
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.abs

/** Recorrido del lápiz por cada paso al deslizar sobre un número. */
internal val ScrubStep = 14.dp

/**
 * Número de bandeja pensado para lápiz y dedo.
 *
 * - Deslizar en horizontal lo ajusta a pasos enteros ([onScrub] recibe los pasos
 *   acumulados desde que empezó el gesto; quien llama suma su paso o snap activo).
 * - Tocar abre la edición exacta del campo que se dibuja en [field].
 * - Doble toque lo restablece con [onReset], si existe un valor neutro (norma de
 *   controles: la pulsación larga solo ofrece «más opciones»).
 * - Mantener pulsado lo «agarra» (se resalta) para deslizar después; soltarlo quieto
 *   no cambia nada.
 * - Dos flechitas en los bordes indican que se arrastra; cada paso da un toque háptico.
 *
 * Mientras no se edita, una capa encima del campo recibe el gesto: el campo de
 * texto nunca empieza a seleccionar ni a desplazar su texto por un arrastre.
 */
@Composable
fun ScrubNumber(
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    onScrubStart: () -> Unit = {},
    onScrub: ((Int) -> Unit)? = null,
    onScrubEnd: () -> Unit = {},
    onReset: (() -> Unit)? = null,
    field: @Composable (Modifier) -> Unit,
) {
    val focus = remember { FocusRequester() }
    val keyboard = LocalSoftwareKeyboardController.current
    var editing by remember { mutableStateOf(false) }
    var scrubbing by remember { mutableStateOf(false) }
    var grabbed by remember { mutableStateOf(false) }
    val haptics = LocalHapticFeedback.current
    val start by rememberUpdatedState(onScrubStart)
    val scrub by rememberUpdatedState(onScrub)
    val end by rememberUpdatedState(onScrubEnd)
    val reset by rememberUpdatedState(onReset)
    val shape = RoundedCornerShape(7.dp)
    Box(modifier) {
        field(Modifier.focusRequester(focus).onFocusChanged { editing = it.isFocused })
        if (!editing) Box(
            Modifier.matchParentSize()
                .then(if (scrubbing || grabbed) Modifier.background(Ink.Accent.copy(alpha = .12f), shape)
                    .border(1.dp, Ink.Accent.copy(alpha = .6f), shape) else Modifier)
                .then(if (scrubbing || !enabled) Modifier else Modifier.drawBehind { drawScrubHint() })
                .pointerInput(enabled) {
                    val stepPx = ScrubStep.toPx()
                    awaitEachGesture {
                        val down = awaitFirstDown(requireUnconsumed = false)
                        down.consume()
                        if (!enabled) { consumeUntilUp(down.id); return@awaitEachGesture }
                        val slop = viewConfiguration.touchSlop
                        val holdMs = viewConfiguration.longPressTimeoutMillis
                        // Mantener pulsado solo «agarra» el número para deslizarlo después;
                        // soltarlo quieto no hace nada. Restablecer es un doble toque.
                        var held = false
                        var outcome = ScrubOutcome.TAP
                        while (true) {
                            val event = if (held) awaitPointerEvent()
                                else withTimeoutOrNull(holdMs) { awaitPointerEvent() }
                            if (event == null) { held = true; grabbed = true; continue }
                            val change = event.changes.firstOrNull { it.id == down.id }
                            if (change == null) { outcome = ScrubOutcome.IGNORE; break }
                            if (!change.pressed) {
                                change.consume()
                                outcome = if (held) ScrubOutcome.IGNORE else ScrubOutcome.TAP
                                break
                            }
                            val d = change.position - down.position
                            if (scrub != null && scrubStarts(d.x, d.y, slop, held)) { outcome = ScrubOutcome.SCRUB; break }
                            if (!held && abs(d.y) > slop && abs(d.y) > 2 * abs(d.x)) { outcome = ScrubOutcome.IGNORE; break }
                            change.consume()
                        }
                        grabbed = false
                        when (outcome) {
                            ScrubOutcome.TAP -> {
                                // Con valor neutro, un segundo toque cercano restablece; si no
                                // llega a tiempo, el toque abre la escritura exacta.
                                val second = if (reset == null) null else withTimeoutOrNull(viewConfiguration.doubleTapTimeoutMillis) {
                                    awaitFirstDown(requireUnconsumed = false)
                                }?.takeIf { (it.position - down.position).getDistance() < slop * 4 }
                                if (second != null) {
                                    second.consume(); consumeUntilUp(second.id)
                                    reset?.invoke(); haptics.performHapticFeedback(HapticFeedbackType.LongPress)
                                } else { focus.requestFocus(); keyboard?.show() }
                            }
                            ScrubOutcome.IGNORE -> if (!held) consumeUntilUp(down.id)
                            ScrubOutcome.SCRUB -> {
                                scrubbing = true
                                start()
                                var steps = 0
                                while (true) {
                                    val change = awaitPointerEvent().changes.firstOrNull { it.id == down.id } ?: break
                                    if (!change.pressed) { change.consume(); break }
                                    val next = scrubSteps(change.position.x - down.position.x, slop, stepPx)
                                    if (next != steps) {
                                        steps = next; scrub?.invoke(steps)
                                        haptics.performHapticFeedback(HapticFeedbackType.TextHandleMove)
                                    }
                                    change.consume()
                                }
                                scrubbing = false
                                end()
                            }
                        }
                    }
                },
        )
    }
}

private enum class ScrubOutcome { TAP, SCRUB, IGNORE }

/**
 * ¿Empieza el deslizamiento? Basta con superar el umbral en horizontal aunque el
 * trazo vaya algo inclinado (hasta ~63°); tras mantener pulsado, cualquier dirección.
 * Solo un trazo claramente vertical se deja pasar al panel que lo contiene.
 */
internal fun scrubStarts(dx: Float, dy: Float, slop: Float, held: Boolean): Boolean =
    if (held) abs(dx) > slop / 2 || abs(dy) > slop
    else abs(dx) > slop && abs(dx) * 2 >= abs(dy)

/** Dos flechitas tenues en los bordes: el número se arrastra a izquierda/derecha. */
private fun DrawScope.drawScrubHint() {
    val h = 3.5.dp.toPx(); val inset = 3.dp.toPx(); val cy = size.height / 2
    val color = Ink.Faint.copy(alpha = .55f)
    fun arrow(tipX: Float, baseX: Float) = Path().apply {
        moveTo(tipX, cy); lineTo(baseX, cy - h); lineTo(baseX, cy + h); close()
    }
    drawPath(arrow(inset, inset + h), color)
    drawPath(arrow(size.width - inset, size.width - inset - h), color)
}

/** Pasos enteros recorridos, contando desde que el gesto superó el umbral táctil. */
internal fun scrubSteps(dx: Float, slop: Float, stepPx: Float): Int {
    val travelled = abs(dx) - slop
    if (travelled <= 0f || stepPx <= 0f) return 0
    val steps = (travelled / stepPx).toInt() + 1
    return if (dx < 0) -steps else steps
}

private suspend fun AwaitPointerEventScope.consumeUntilUp(id: PointerId) {
    while (true) {
        val change = awaitPointerEvent().changes.firstOrNull { it.id == id } ?: return
        change.consume()
        if (!change.pressed) return
    }
}

/**
 * Número sencillo de bandeja (radio, fuerza, tamaño…): muestra su valor, desliza a
 * pasos dentro de [min]..[max], se escribe con cuentas y, si hay neutro, se restablece.
 * [toText]/[fromText] convierten entre el valor real y lo que se lee (p. ej. %).
 */
@Composable
fun TrayNumber(
    caption: String,
    value: Double,
    step: Double,
    min: Double,
    max: Double,
    toText: (Double) -> String,
    fromText: (String, Double) -> Double?,
    onValue: (Double) -> Unit,
    suffix: String = "",
    help: String = caption,
    neutral: Double? = null,
    enabled: Boolean = true,
    width: androidx.compose.ui.unit.Dp = 120.dp,
) {
    var pending by remember { mutableStateOf<Double?>(null) }
    androidx.compose.runtime.LaunchedEffect(value) { pending = null }
    val shown = pending ?: value
    var draft by remember { mutableStateOf<String?>(null) }
    var base by remember { mutableStateOf(shown) }
    fun send(raw: Double) {
        if (!raw.isFinite()) return
        val next = raw.coerceIn(min, max)
        pending = next; draft = null
        onValue(next)
    }
    HoverHelp(help, numberHelp(neutral != null), enabled = enabled) {
        ScrubNumber(enabled = enabled, onScrubStart = { base = shown },
            onScrub = { steps -> send(base + steps * step) },
            onReset = neutral?.let { { send(it) } }) { field ->
            CompactNumericField(draft ?: toText(shown), { draft = it }, modifier = field.width(width),
                fontSize = 16.sp, textAlign = androidx.compose.ui.text.style.TextAlign.End, selectAllOnFocus = true,
                caption = caption, suffix = suffix,
                textColor = if (enabled) Ink.OnPanel else Ink.Faint,
                onDone = { draft?.let { fromText(it, shown) }?.let(::send); draft = null })
        }
    }
}
