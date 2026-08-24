package com.blendertablet.remote.ui

import android.content.Context
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import com.blendertablet.remote.model.Gesture
import com.blendertablet.remote.model.GesturePhase
import com.blendertablet.remote.model.InputDebug
import kotlin.math.abs
import kotlin.math.hypot
import kotlin.math.pow

/**
 * Capa de entrada táctil/stylus.
 *
 * Reparto de gestos (§106 del plan):
 *   1 dedo   -> herramienta activa (con Select: orbita, para poder navegar siempre)
 *   2 dedos  -> desplazar y zoom a la vez (no hay que elegir)
 *   toque    -> seleccionar · doble toque -> encuadrar
 *
 * Toda la entrada vive aquí, y no en capas Compose encima, para no tener dos sistemas
 * de entrada disputándose el mismo toque.
 *
 * Emite gestos del protocolo (begin/update/end) con deltas en **fracción de pantalla**,
 * no en píxeles: el servidor no conoce la resolución de esta tablet y trata dx = 1.0
 * como "todo el ancho". Los updates se acumulan y se envían a 30 Hz, así que un
 * arrastre no pierde recorrido aunque se despache menos veces de las que llegan.
 */
@Composable
fun InputSurface(
    modifier: Modifier = Modifier,
    onDebug: (InputDebug) -> Unit,
    onToolGesture: (GesturePhase, Float, Float) -> Unit,
    onViewGesture: (Gesture, GesturePhase, Float, Float, Float) -> Unit,
    onTap: (Float, Float, Boolean) -> Unit,
    onDoubleTap: () -> Unit,
    /** Pulsación larga: abre el menú rápido en píxeles de esta vista. */
    onLongPress: (px: Float, py: Float, u: Float, v: Float) -> Unit = { _, _, _, _ -> },
) {
    AndroidView(
        modifier = modifier,
        factory = { context -> GestureView(context, onDebug, onToolGesture, onViewGesture, onTap, onDoubleTap) },
        update = { view ->
            view.updateCallbacks(onDebug, onToolGesture, onViewGesture, onTap, onDoubleTap)
            view.onLongPress = onLongPress
        },
    )
}

// 30 Hz acompasa la entrada al vídeo sin llenar la cola mientras Blender recalcula
// una malla. Los píxeles recorridos se acumulan, así no se pierde precisión.
private const val DISPATCH_MS = 33L
private const val PINCH_SLOP_PX = 24f
private const val DOUBLE_TAP_MS = 320L
private const val FINGER_LONG_PRESS_MS = 420L
private const val STYLUS_LONG_PRESS_MS = 340L

// Sensibilidad del pellizco. 1.0 seria el ratio crudo entre dedos, que resulta
// demasiado brusco para encuadrar con precision; por debajo de 1 el zoom es mas fino.
private const val ZOOM_GAIN = 0.55f
private const val ZOOM_DEADZONE = 0.004f

private class GestureView(
    context: Context,
    private var onDebug: (InputDebug) -> Unit,
    private var onToolGesture: (GesturePhase, Float, Float) -> Unit,
    private var onViewGesture: (Gesture, GesturePhase, Float, Float, Float) -> Unit,
    private var onTap: (Float, Float, Boolean) -> Unit,
    private var onDoubleTap: () -> Unit,
) : View(context) {
    private var lastX = 0f
    private var lastY = 0f
    private var lastSpan = 0f
    private var startSpan = 0f
    private var startX = 0f
    private var startY = 0f
    private var lastTapAt = 0L
    private var lastDispatchAt = 0L
    private var moved = false
    private var downToolType = MotionEvent.TOOL_TYPE_FINGER
    private val systemTouchSlop = ViewConfiguration.get(context).scaledTouchSlop.toFloat()
    private val stylusTouchSlop = 12f * resources.displayMetrics.density

    /** Sesión de dos dedos abierta (pan y zoom van juntos). */
    private var pairActive = false
    private var toolActive = false

    /**
     * Pulsación larga. Llegan las dos coordenadas porque hacen falta las dos: los
     * píxeles colocan el menú donde está el dedo y las normalizadas preguntan al
     * servidor qué hay debajo.
     */
    var onLongPress: (px: Float, py: Float, u: Float, v: Float) -> Unit = { _, _, _, _ -> }
    private var longPressFired = false
    private val longPressRunnable = Runnable {
        fireLongPress(startX, startY)
    }

    // Acumuladores: lo que se ha movido el dedo desde el último envío.
    private var pendingDx = 0f
    private var pendingDy = 0f
    private var pendingFactor = 1f

    init { setBackgroundColor(android.graphics.Color.TRANSPARENT) }

    fun updateCallbacks(
        debug: (InputDebug) -> Unit,
        toolGesture: (GesturePhase, Float, Float) -> Unit,
        viewGestureCb: (Gesture, GesturePhase, Float, Float, Float) -> Unit,
        tap: (Float, Float, Boolean) -> Unit,
        doubleTap: () -> Unit,
    ) {
        onDebug = debug; onToolGesture = toolGesture; onViewGesture = viewGestureCb
        onTap = tap; onDoubleTap = doubleTap
    }

    private fun nx(px: Float) = if (width > 0) px / width else 0f
    private fun ny(px: Float) = if (height > 0) px / height else 0f

    override fun onTouchEvent(event: MotionEvent): Boolean {
        val index = event.actionIndex.coerceAtMost(event.pointerCount - 1)
        onDebug(InputDebug(
            pointerCount = event.pointerCount,
            tool = toolName(event.getToolType(index)),
            pressure = event.getPressure(index),
            tilt = event.getAxisValue(MotionEvent.AXIS_TILT, index),
            orientation = event.getOrientation(index),
            buttonState = event.buttonState,
            x = event.getX(index),
            y = event.getY(index),
        ))

        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                parent?.requestDisallowInterceptTouchEvent(true)
                lastX = event.x; lastY = event.y
                startX = event.x; startY = event.y
                downToolType = event.getToolType(0)
                moved = false
                longPressFired = false
                if (isStylus(downToolType) &&
                    event.buttonState and MotionEvent.BUTTON_STYLUS_PRIMARY != 0
                ) {
                    fireLongPress(startX, startY)
                } else {
                    postDelayed(
                        longPressRunnable,
                        if (isStylus(downToolType)) STYLUS_LONG_PRESS_MS else FINGER_LONG_PRESS_MS,
                    )
                }
            }

            MotionEvent.ACTION_POINTER_DOWN -> if (event.pointerCount >= 2) {
                removeCallbacks(longPressRunnable)
                // Un segundo dedo significa navegar: se suelta la herramienta.
                endToolGesture()
                // La sesión de navegación NO se cierra: solo se reancla. Cerrarla
                // cortaría el gesto en seco al apoyar un dedo de más.
                rememberPointers(event)
            }

            // Tres o mas dedos se tratan como dos: Android intercepta el gesto de
            // tres dedos para la captura de pantalla y nunca llega completo.
            MotionEvent.ACTION_MOVE ->
                if (event.pointerCount >= 2) handlePair(event) else handleSingle(event)

            MotionEvent.ACTION_POINTER_UP -> {
                // Si baja de dos dedos se acaba la navegación; si aún quedan dos o
                // más, solo se reancla y el gesto continúa.
                if (event.pointerCount - 1 < 2) endViewGesture()
                rememberPointers(event, skip = event.actionIndex)
            }

            MotionEvent.ACTION_UP -> {
                removeCallbacks(longPressRunnable)
                endToolGesture()
                endViewGesture()
                if (!moved && !longPressFired) handleTap(event)
                parent?.requestDisallowInterceptTouchEvent(false)
            }

            MotionEvent.ACTION_CANCEL -> {
                removeCallbacks(longPressRunnable)
                cancelGestures()
                parent?.requestDisallowInterceptTouchEvent(false)
            }
        }
        return true
    }

    private fun handleSingle(e: MotionEvent) {
        val dx = e.x - lastX
        val dy = e.y - lastY
        lastX = e.x; lastY = e.y

        val slop = if (isStylus(downToolType)) stylusTouchSlop else systemTouchSlop
        if (!moved && hypot(e.x - startX, e.y - startY) <= slop) return
        if (!moved) removeCallbacks(longPressRunnable)
        moved = true

        if (!toolActive) {
            toolActive = true
            onToolGesture(GesturePhase.BEGIN, 0f, 0f)
            lastDispatchAt = e.eventTime
        }

        pendingDx += dx
        pendingDy += dy
        if (e.eventTime - lastDispatchAt >= DISPATCH_MS) {
            onToolGesture(GesturePhase.UPDATE, nx(pendingDx), ny(pendingDy))
            pendingDx = 0f; pendingDy = 0f
            lastDispatchAt = e.eventTime
        }
    }

    /**
     * Ancla el punto medio y la separación de los dos primeros dedos.
     *
     * Se usan siempre los dos mismos punteros que `handlePair`, si no el gesto daría
     * un salto al apoyar o levantar un dedo de más.
     */
    private fun rememberPointers(e: MotionEvent, skip: Int = -1) {
        val idx = (0 until e.pointerCount).filter { it != skip }
        if (idx.isEmpty()) return
        if (idx.size == 1) {
            lastX = e.getX(idx[0]); lastY = e.getY(idx[0])
            lastSpan = 0f
        } else {
            lastX = (e.getX(idx[0]) + e.getX(idx[1])) / 2f
            lastY = (e.getY(idx[0]) + e.getY(idx[1])) / 2f
            lastSpan = hypot(e.getX(idx[1]) - e.getX(idx[0]), e.getY(idx[1]) - e.getY(idx[0]))
        }
        startX = lastX
        startY = lastY
        startSpan = lastSpan
    }

    /**
     * Dos dedos: desplazar y hacer zoom **a la vez**, como en un mapa.
     *
     * Antes se elegía entre pan y zoom con un umbral, y era el origen de dos fallos:
     * al arrastrar dos dedos la separación varía siempre unos píxeles, así que casi
     * todo se clasificaba como zoom y el paneo no llegaba a activarse. Aplicando
     * ambos no hay nada que adivinar y el gesto se siente continuo.
     *
     * No se usan tres dedos: Android se los queda para la captura de pantalla.
     */
    private fun handlePair(e: MotionEvent) {
        val cx = (e.getX(0) + e.getX(1)) / 2f
        val cy = (e.getY(0) + e.getY(1)) / 2f
        val span = hypot(e.getX(1) - e.getX(0), e.getY(1) - e.getY(0))

        val dx = cx - lastX
        val dy = cy - lastY
        val rawRatio = if (lastSpan > 1f) span / lastSpan else 1f
        lastX = cx; lastY = cy; lastSpan = span

        if (!moved && hypot(cx - startX, cy - startY) <= systemTouchSlop &&
            abs(span - startSpan) <= PINCH_SLOP_PX
        ) return
        moved = true

        if (!pairActive) {
            pairActive = true
            onViewGesture(Gesture.PAN, GesturePhase.BEGIN, 0f, 0f, 1f)
            onViewGesture(Gesture.ZOOM, GesturePhase.BEGIN, 0f, 0f, 1f)
            lastDispatchAt = e.eventTime
        }

        pendingDx += dx
        pendingDy += dy
        // Ganancia < 1: el pellizco crudo resultaba demasiado brusco para afinar.
        pendingFactor *= if (rawRatio > 0f) rawRatio.pow(ZOOM_GAIN) else 1f

        if (e.eventTime - lastDispatchAt >= DISPATCH_MS) {
            flushPair()
            lastDispatchAt = e.eventTime
        }
    }

    private fun flushPair() {
        if (pendingDx != 0f || pendingDy != 0f) {
            onViewGesture(Gesture.PAN, GesturePhase.UPDATE, nx(pendingDx), ny(pendingDy), 1f)
        }
        // Zona muerta: sin ella el temblor de la mano produce un zoom nervioso.
        if (abs(pendingFactor - 1f) > ZOOM_DEADZONE) {
            onViewGesture(Gesture.ZOOM, GesturePhase.UPDATE, 0f, 0f, pendingFactor)
        }
        pendingDx = 0f; pendingDy = 0f; pendingFactor = 1f
    }

    private fun endToolGesture() {
        if (!toolActive) return
        if (pendingDx != 0f || pendingDy != 0f) {
            onToolGesture(GesturePhase.UPDATE, nx(pendingDx), ny(pendingDy))
        }
        onToolGesture(GesturePhase.END, 0f, 0f)
        toolActive = false
        resetPending()
    }

    private fun endViewGesture() {
        if (!pairActive) return
        flushPair()
        onViewGesture(Gesture.PAN, GesturePhase.END, 0f, 0f, 1f)
        onViewGesture(Gesture.ZOOM, GesturePhase.END, 0f, 0f, 1f)
        pairActive = false
        resetPending()
    }

    private fun cancelGestures() {
        if (toolActive) onToolGesture(GesturePhase.CANCEL, 0f, 0f)
        if (pairActive) {
            onViewGesture(Gesture.PAN, GesturePhase.CANCEL, 0f, 0f, 1f)
            onViewGesture(Gesture.ZOOM, GesturePhase.CANCEL, 0f, 0f, 1f)
        }
        toolActive = false
        pairActive = false
        resetPending()
    }

    private fun resetPending() {
        pendingDx = 0f; pendingDy = 0f; pendingFactor = 1f
    }

    private fun handleTap(e: MotionEvent) {
        val now = e.eventTime
        if (now - lastTapAt < DOUBLE_TAP_MS) {
            onDoubleTap()
            lastTapAt = 0L
        } else {
            lastTapAt = now
            // u/v normalizados con origen arriba-izquierda: la conversión al eje Y de
            // Blender la hace el servidor.
            // El pequeño deslizamiento al levantar el pen no cambia el objetivo.
            onTap(nx(startX), ny(startY), isStylus(downToolType))
        }
    }

    private fun fireLongPress(x: Float, y: Float) {
        removeCallbacks(longPressRunnable)
        if (longPressFired || moved) return
        longPressFired = true
        performHapticFeedback(android.view.HapticFeedbackConstants.LONG_PRESS)
        onLongPress(x, y, nx(x), ny(y))
    }

    override fun onGenericMotionEvent(event: MotionEvent): Boolean {
        val stylus = event.pointerCount > 0 && isStylus(event.getToolType(0))
        if (stylus && event.actionMasked == MotionEvent.ACTION_BUTTON_PRESS &&
            event.actionButton == MotionEvent.BUTTON_STYLUS_PRIMARY
        ) {
            fireLongPress(event.x, event.y)
            return true
        }
        return super.onGenericMotionEvent(event)
    }

    private fun isStylus(tool: Int) =
        tool == MotionEvent.TOOL_TYPE_STYLUS || tool == MotionEvent.TOOL_TYPE_ERASER

    private fun toolName(tool: Int) = when (tool) {
        MotionEvent.TOOL_TYPE_STYLUS -> "Stylus"
        MotionEvent.TOOL_TYPE_ERASER -> "Eraser"
        MotionEvent.TOOL_TYPE_MOUSE -> "Mouse"
        MotionEvent.TOOL_TYPE_FINGER -> "Finger"
        else -> "Unknown"
    }
}
