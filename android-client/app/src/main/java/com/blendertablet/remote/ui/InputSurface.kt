package com.blendertablet.remote.ui

import android.content.Context
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.graphics.Canvas
import android.graphics.Paint
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import com.blendertablet.remote.model.Gesture
import com.blendertablet.remote.model.GesturePhase
import com.blendertablet.remote.model.InputDebug
import com.blendertablet.remote.model.NavigationOrbitLayout
import com.blendertablet.remote.model.ProportionalCircle
import com.blendertablet.remote.model.ShapeTool
import com.blendertablet.remote.model.SnapCandidate
import com.blendertablet.remote.model.SnapType
import com.blendertablet.remote.model.TapExtrusionGesture
import kotlin.math.abs
import kotlin.math.atan2
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
    /** Posición absoluta del dedo durante la herramienta, normalizada 0..1. */
    onToolPointer: (Float, Float) -> Unit = { _, _ -> },
    onViewGesture: (Gesture, GesturePhase, Float, Float, Float) -> Unit,
    onTap: (Float, Float, Boolean) -> Unit,
    onDoubleTap: () -> Unit,
    repeatTap: Boolean = false,
    independentTaps: Boolean = false,
    cadDrawingEnabled: Boolean = false,
    onCadGesture: (GesturePhase, Float, Float) -> Unit = { _, _, _ -> },
    cadOverlay: List<com.blendertablet.remote.model.CadOverlay> = emptyList(),
    knifeActive: Boolean = false,
    onKnifeDrag: (GesturePhase, Float, Float) -> Unit = { _, _, _ -> },
    tweakActive: Boolean = false,
    onTweakDrag: (GesturePhase, Float, Float, Float, Float) -> Unit = { _, _, _, _, _ -> },
    /** Una sesión modal/tool captura el dedo y excluye por completo el menú radial. */
    longPressEnabled: Boolean = true,
    /** Pulsación larga: abre el menú rápido en píxeles de esta vista. */
    onLongPress: (px: Float, py: Float, u: Float, v: Float) -> Unit = { _, _, _, _ -> },
    /** Herramienta de forma armada (B/C); NONE = gesto normal de un dedo. */
    shapeTool: ShapeTool = ShapeTool.NONE,
    fixedCircleRadius: Float? = null,
    /** Círculo derecho que navega sin alimentar una sesión modal. */
    navigationOrbitEnabled: Boolean = false,
    /** Forma terminada: esquinas (box) o centro+borde (circle) normalizados. */
    onShape: (ShapeTool, Float, Float, Float, Float) -> Unit = { _, _, _, _, _ -> },
    /** Puntos del Knife en pantalla, para dibujarlos sobre el vídeo. */
    knifePoints: List<List<Pair<Float, Float>>> = emptyList(),
    snapCandidate: SnapCandidate? = null,
    cancelPickOnNavigation: Boolean = false,
    proportionalCircle: ProportionalCircle? = null,
) {
    AndroidView(
        modifier = modifier,
        factory = { context -> GestureView(context, onDebug, onToolGesture, onToolPointer, onViewGesture, onTap, onDoubleTap) },
        update = { view ->
            view.updateCallbacks(onDebug, onToolGesture, onToolPointer, onViewGesture, onTap, onDoubleTap)
            view.onLongPress = onLongPress
            view.repeatTap = repeatTap
            view.independentTaps = independentTaps
            view.shapeTool = shapeTool
            view.fixedCircleRadius = fixedCircleRadius
            view.cadDrawingEnabled = cadDrawingEnabled
            view.onCadGesture = onCadGesture
            view.cadOverlay = cadOverlay
            view.knifeActive = knifeActive
            view.onKnifeDrag = onKnifeDrag
            view.tweakActive = tweakActive
            view.onTweakDrag = onTweakDrag
            view.longPressEnabled = longPressEnabled
            view.navigationOrbitEnabled = navigationOrbitEnabled
            view.onShape = onShape
            view.knifePoints = knifePoints
            view.snapCandidate = snapCandidate
            view.cancelPickOnNavigation = cancelPickOnNavigation
            view.proportionalCircle = proportionalCircle
            view.invalidate()
        },
    )
}

// 30 Hz acompasa la entrada al vídeo sin llenar la cola mientras Blender recalcula
// una malla. Los píxeles recorridos se acumulan, así no se pierde precisión.
private const val DISPATCH_MS = 33L
// Knife solo sondea el candidato durante UPDATE; 15 Hz basta visualmente y evita
// reconstrucciones/estado innecesarios mientras Blender también codifica el viewport.
internal const val KNIFE_DISPATCH_MS = 66L

/** Knife ignora el jitter de ACTION_UP y confirma la última muestra DOWN/MOVE. */
internal fun stableKnifeRelease(lastStableX: Float, lastStableY: Float) =
    lastStableX to lastStableY
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
    private var onToolPointer: (Float, Float) -> Unit,
    private var onViewGesture: (Gesture, GesturePhase, Float, Float, Float) -> Unit,
    private var onTap: (Float, Float, Boolean) -> Unit,
    private var onDoubleTap: () -> Unit,
) : View(context) {
    private val tapPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = android.graphics.Color.WHITE
        style = Paint.Style.STROKE
        strokeWidth = 2f * resources.displayMetrics.density
    }
    private val shapePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = android.graphics.Color.parseColor("#4C8DFF")
        style = Paint.Style.STROKE
        strokeWidth = 2f * resources.displayMetrics.density
    }
    private var tapFeedbackX = -1f
    private var tapFeedbackY = -1f
    private var tapFeedbackUntil = 0L
    private var lastX = 0f
    private var lastY = 0f
    private var lastSpan = 0f
    private var startSpan = 0f
    private var lastAngle = 0f
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
    /** Un DOWN dentro del círculo queda capturado hasta UP/CANCEL. */
    private var navigationOrbitActive = false
    private var navigationOrbitBegan = false

    /**
     * Pulsación larga. Llegan las dos coordenadas porque hacen falta las dos: los
     * píxeles colocan el menú donde está el dedo y las normalizadas preguntan al
     * servidor qué hay debajo.
     */
    var onLongPress: (px: Float, py: Float, u: Float, v: Float) -> Unit = { _, _, _, _ -> }
    private val tapExtrusion = TapExtrusionGesture()
    var independentTaps: Boolean = false
    var repeatTap: Boolean = false
        set(value) {
            if (!value) tapExtrusion.cancel()
            field = value
        }
    var longPressEnabled: Boolean = true
        set(value) {
            field = value
            if (!value) removeCallbacks(longPressRunnable)
        }
    private var longPressFired = false
    private val longPressRunnable = Runnable {
        fireLongPress(startX, startY)
    }

    /** Herramienta de forma (B/C). Con una armada, el dedo dibuja en vez de orbitar. */
    var shapeTool: ShapeTool = ShapeTool.NONE
    var fixedCircleRadius: Float? = null
    var knifeActive: Boolean = false
    var onKnifeDrag: (GesturePhase, Float, Float) -> Unit = { _, _, _ -> }
    var tweakActive: Boolean = false
        set(value) {
            if (!value) cancelTweak()
            field = value
        }
    var onTweakDrag: (GesturePhase, Float, Float, Float, Float) -> Unit = { _, _, _, _, _ -> }
    private var tweakDrawing = false
    private var suppressSingleAfterTweak = false
    var navigationOrbitEnabled: Boolean = false
    var onShape: (ShapeTool, Float, Float, Float, Float) -> Unit = { _, _, _, _, _ -> }
    /** Puntos del Knife (normalizados) para el overlay. */
    var cadDrawingEnabled = false
        set(value) {
            if (field && !value && cadDrawing) {
                onCadGesture(GesturePhase.CANCEL, nx(shapeCurrentX), ny(shapeCurrentY))
                cadDrawing = false
                suppressSingleAfterTweak = true
            }
            field = value
        }
    var onCadGesture: (GesturePhase, Float, Float) -> Unit = { _, _, _ -> }
    var cadOverlay: List<com.blendertablet.remote.model.CadOverlay> = emptyList()
    private var cadDrawing = false
    private val cadPaint = android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG).apply {
        style = android.graphics.Paint.Style.STROKE
        strokeWidth = 2.5f * resources.displayMetrics.density
    }
    var knifePoints: List<List<Pair<Float, Float>>> = emptyList()
    var snapCandidate: SnapCandidate? = null
    var cancelPickOnNavigation: Boolean = false
    var proportionalCircle: ProportionalCircle? = null
    private val proportionalPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = android.graphics.Color.parseColor("#B3FFFFFF")
        style = Paint.Style.STROKE
        strokeWidth = 1.5f * resources.displayMetrics.density
    }
    private val candidatePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = android.graphics.Color.parseColor("#66E3A4")
        style = Paint.Style.STROKE
        strokeWidth = 2.5f * resources.displayMetrics.density
    }
    private val knifePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = android.graphics.Color.parseColor("#FFB84C")
        style = Paint.Style.STROKE
        strokeWidth = 2.5f * resources.displayMetrics.density
    }
    private var shapeDrawing = false
    private var knifeDrawing = false
    private var shapeStartX = 0f
    private var shapeStartY = 0f
    private var shapeCurrentX = 0f
    private var shapeCurrentY = 0f

    // Acumuladores: lo que se ha movido el dedo desde el último envío.
    private var pendingDx = 0f
    private var pendingDy = 0f
    private var pendingFactor = 1f
    private var pendingRoll = 0f

    init { setBackgroundColor(android.graphics.Color.TRANSPARENT) }

    fun updateCallbacks(
        debug: (InputDebug) -> Unit,
        toolGesture: (GesturePhase, Float, Float) -> Unit,
        toolPointer: (Float, Float) -> Unit,
        viewGestureCb: (Gesture, GesturePhase, Float, Float, Float) -> Unit,
        tap: (Float, Float, Boolean) -> Unit,
        doubleTap: () -> Unit,
    ) {
        onDebug = debug; onToolGesture = toolGesture; onToolPointer = toolPointer; onViewGesture = viewGestureCb
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
                suppressSingleAfterTweak = false
                parent?.requestDisallowInterceptTouchEvent(true)
                lastX = event.x; lastY = event.y
                startX = event.x; startY = event.y
                downToolType = event.getToolType(0)
                moved = false
                longPressFired = false
                // El hit-test se hace solo al bajar: si el dedo entra después en el
                // círculo continúa el nudge que ya había empezado fuera.
                if (navigationOrbitEnabled && NavigationOrbitLayout.contains(width, height, event.x, event.y)) {
                    navigationOrbitActive = true
                    navigationOrbitBegan = false
                    invalidate()
                    return true
                }
                if (repeatTap) {
                    tapExtrusion.begin(nx(event.x), ny(event.y))
                    return true
                }
                if (cadDrawingEnabled) {
                    cadDrawing = true
                    shapeCurrentX = event.x; shapeCurrentY = event.y
                    lastDispatchAt = event.eventTime
                    onCadGesture(GesturePhase.BEGIN, nx(event.x), ny(event.y))
                    return true
                }
                if (knifeActive) {
                    knifeDrawing = true
                    shapeStartX = event.x; shapeStartY = event.y
                    shapeCurrentX = event.x; shapeCurrentY = event.y
                    lastDispatchAt = event.eventTime
                    onKnifeDrag(GesturePhase.BEGIN, nx(event.x), ny(event.y))
                    invalidate()
                    return true
                }
                if (tweakActive) {
                    tweakDrawing = true
                    lastDispatchAt = event.eventTime
                    pendingDx = 0f; pendingDy = 0f
                    onTweakDrag(GesturePhase.BEGIN, nx(event.x), ny(event.y), 0f, 0f)
                    invalidate()
                    return true
                }
                // Con B/C armada, un dedo dibuja la forma: no orbita, no selecciona
                // y no abre el menú. El tap simple no hace nada (se resuelve al soltar).
                if (shapeTool != ShapeTool.NONE) {
                    shapeDrawing = true
                    shapeStartX = event.x; shapeStartY = event.y
                    shapeCurrentX = event.x; shapeCurrentY = event.y
                    moved = false
                    longPressFired = false
                    invalidate()
                    return true
                }
                if (!longPressEnabled) {
                    removeCallbacks(longPressRunnable)
                } else if (isStylus(downToolType) &&
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
                if (repeatTap) {
                    tapExtrusion.cancel()
                    suppressSingleAfterTweak = true
                }
                // Un segundo dedo significa navegar: se suelta la herramienta y la forma.
                if (cadDrawing) {
                    onCadGesture(GesturePhase.CANCEL, nx(shapeCurrentX), ny(shapeCurrentY))
                    cadDrawing = false
                    suppressSingleAfterTweak = true
                }
                if (shapeDrawing) {
                    shapeDrawing = false
                    invalidate()
                }
                if (knifeDrawing) {
                    onKnifeDrag(GesturePhase.CANCEL, nx(shapeCurrentX), ny(shapeCurrentY))
                    knifeDrawing = false
                    invalidate()
                }
                if (tweakDrawing) {
                    cancelTweak()
                }
                if (cancelPickOnNavigation && toolActive) {
                    onToolGesture(GesturePhase.CANCEL, 0f, 0f)
                    toolActive = false
                    resetPending()
                } else endToolGesture()
                endNavigationOrbit()
                // La sesión de navegación NO se cierra: solo se reancla. Cerrarla
                // cortaría el gesto en seco al apoyar un dedo de más.
                rememberPointers(event)
            }

            // Tres o mas dedos se tratan como dos: Android intercepta el gesto de
            // tres dedos para la captura de pantalla y nunca llega completo.
            MotionEvent.ACTION_MOVE ->
                if (event.pointerCount >= 2) handlePair(event)
                else if (tapExtrusion.active) {
                    tapExtrusion.move(nx(event.x), ny(event.y))
                }
                else if (cadDrawing) {
                    shapeCurrentX = event.x; shapeCurrentY = event.y
                    if (event.eventTime - lastDispatchAt >= KNIFE_DISPATCH_MS) {
                        onCadGesture(GesturePhase.UPDATE, nx(shapeCurrentX), ny(shapeCurrentY))
                        lastDispatchAt = event.eventTime
                    }
                } else if (knifeDrawing) {
                    shapeCurrentX = event.x; shapeCurrentY = event.y
                    if (event.eventTime - lastDispatchAt >= KNIFE_DISPATCH_MS) {
                        onKnifeDrag(GesturePhase.UPDATE, nx(event.x), ny(event.y))
                        lastDispatchAt = event.eventTime
                    }
                    invalidate()
                } else if (tweakDrawing) {
                    handleTweak(event)
                } else if (suppressSingleAfterTweak) {
                    // Tras cancelar Tweak, el dedo restante no inicia otra edición.
                } else if (shapeDrawing) {
                    shapeCurrentX = event.x; shapeCurrentY = event.y
                    invalidate()
                } else if (navigationOrbitActive) handleNavigationOrbit(event) else handleSingle(event)

            MotionEvent.ACTION_POINTER_UP -> {
                // Si baja de dos dedos se acaba la navegación; si aún quedan dos o
                // más, solo se reancla y el gesto continúa.
                if (event.pointerCount - 1 < 2) endViewGesture()
                rememberPointers(event, skip = event.actionIndex)
            }

            MotionEvent.ACTION_UP -> {
                removeCallbacks(longPressRunnable)
                if (tapExtrusion.active) {
                    tapExtrusion.end()?.let { (u, v) -> onTap(u, v, isStylus(downToolType)) }
                    parent?.requestDisallowInterceptTouchEvent(false)
                    return true
                }
                if (cadDrawing) {
                    // END consumes the last stable MOVE candidate without another raycast.
                    onCadGesture(GesturePhase.END, nx(shapeCurrentX), ny(shapeCurrentY))
                    cadDrawing = false
                    parent?.requestDisallowInterceptTouchEvent(false)
                    return true
                }
                if (shapeDrawing) {
                    shapeDrawing = false
                    finishShape()
                    parent?.requestDisallowInterceptTouchEvent(false)
                    return true
                }
                if (knifeDrawing) {
                    // Al perder presión, ACTION_UP suele saltar unos píxeles. Se fija
                    // la última posición estable que el usuario estaba viendo.
                    val (releaseX, releaseY) = stableKnifeRelease(shapeCurrentX, shapeCurrentY)
                    onKnifeDrag(GesturePhase.END, nx(releaseX), ny(releaseY))
                    knifeDrawing = false
                    invalidate()
                    parent?.requestDisallowInterceptTouchEvent(false)
                    return true
                }
                if (tweakDrawing) {
                    flushTweak(event)
                    onTweakDrag(GesturePhase.END, nx(lastX), ny(lastY), 0f, 0f)
                    tweakDrawing = false
                    parent?.requestDisallowInterceptTouchEvent(false)
                    return true
                }
                val wasNavigationOrbit = navigationOrbitActive
                endToolGesture()
                endNavigationOrbit()
                endViewGesture()
                if (!suppressSingleAfterTweak && !wasNavigationOrbit && !moved && !longPressFired) handleTap(event)
                parent?.requestDisallowInterceptTouchEvent(false)
            }

            MotionEvent.ACTION_CANCEL -> {
                removeCallbacks(longPressRunnable)
                tapExtrusion.cancel()
                if (cadDrawing) onCadGesture(GesturePhase.CANCEL, nx(shapeCurrentX), ny(shapeCurrentY))
                cadDrawing = false
                shapeDrawing = false
                if (knifeDrawing) onKnifeDrag(GesturePhase.CANCEL, nx(shapeCurrentX), ny(shapeCurrentY))
                knifeDrawing = false
                cancelTweak()
                invalidate()
                cancelGestures()
                parent?.requestDisallowInterceptTouchEvent(false)
            }
        }
        return true
    }

    private fun handleTweak(e: MotionEvent) {
        pendingDx += e.x - lastX
        pendingDy += e.y - lastY
        lastX = e.x; lastY = e.y
        val slop = if (isStylus(downToolType)) stylusTouchSlop else systemTouchSlop
        moved = moved || hypot(e.x - startX, e.y - startY) > slop
        if (e.eventTime - lastDispatchAt >= DISPATCH_MS) flushTweak(e)
    }

    private fun flushTweak(e: MotionEvent) {
        if (moved && (pendingDx != 0f || pendingDy != 0f)) {
            onTweakDrag(
                GesturePhase.UPDATE, nx(lastX), ny(lastY),
                nx(pendingDx), ny(pendingDy),
            )
            pendingDx = 0f; pendingDy = 0f
            lastDispatchAt = e.eventTime
        }
    }

    private fun cancelTweak() {
        if (!tweakDrawing) return
        tweakDrawing = false
        suppressSingleAfterTweak = true
        resetPending()
        onTweakDrag(GesturePhase.CANCEL, nx(lastX), ny(lastY), 0f, 0f)
    }

    override fun onDetachedFromWindow() {
        tapExtrusion.cancel()
        cancelTweak()
        super.onDetachedFromWindow()
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
            onToolPointer(nx(e.x), ny(e.y))
            pendingDx = 0f; pendingDy = 0f
            lastDispatchAt = e.eventTime
        }
    }

    /** Arrastre reservado al círculo: siempre envía ORBIT, nunca un nudge. */
    private fun handleNavigationOrbit(e: MotionEvent) {
        val dx = e.x - lastX
        val dy = e.y - lastY
        lastX = e.x; lastY = e.y
        val slop = if (isStylus(downToolType)) stylusTouchSlop else systemTouchSlop
        if (!moved && hypot(e.x - startX, e.y - startY) <= slop) return
        moved = true
        if (!navigationOrbitBegan) {
            onViewGesture(Gesture.ORBIT, GesturePhase.BEGIN, 0f, 0f, 1f)
            navigationOrbitBegan = true
            lastDispatchAt = e.eventTime
        }
        pendingDx += dx
        pendingDy += dy
        if (e.eventTime - lastDispatchAt >= DISPATCH_MS) {
            onViewGesture(Gesture.ORBIT, GesturePhase.UPDATE, nx(pendingDx), ny(pendingDy), 1f)
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
            lastAngle = atan2(e.getY(idx[1]) - e.getY(idx[0]), e.getX(idx[1]) - e.getX(idx[0]))
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
        val angle = atan2(e.getY(1) - e.getY(0), e.getX(1) - e.getX(0))

        val dx = cx - lastX
        val dy = cy - lastY
        val rawRatio = if (lastSpan > 1f) span / lastSpan else 1f
        // Giro de la cuerda entre los dos dedos (rueda). Normalizado a [-π, π].
        var deltaAngle = angle - lastAngle
        while (deltaAngle > Math.PI) deltaAngle -= (2 * Math.PI).toFloat()
        while (deltaAngle < -Math.PI) deltaAngle += (2 * Math.PI).toFloat()
        lastX = cx; lastY = cy; lastSpan = span; lastAngle = angle

        if (!moved && hypot(cx - startX, cy - startY) <= systemTouchSlop &&
            abs(span - startSpan) <= PINCH_SLOP_PX
        ) return
        moved = true

        if (!pairActive) {
            pairActive = true
            onViewGesture(Gesture.PAN, GesturePhase.BEGIN, 0f, 0f, 1f)
            onViewGesture(Gesture.ZOOM, GesturePhase.BEGIN, 0f, 0f, 1f)
            onViewGesture(Gesture.ROLL, GesturePhase.BEGIN, 0f, 0f, 1f)
            lastDispatchAt = e.eventTime
        }

        pendingDx += dx
        pendingDy += dy
        // Ganancia < 1: el pellizco crudo resultaba demasiado brusco para afinar.
        pendingFactor *= if (rawRatio > 0f) rawRatio.pow(ZOOM_GAIN) else 1f
        pendingRoll += deltaAngle

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
        if (pendingRoll != 0f) {
            onViewGesture(Gesture.ROLL, GesturePhase.UPDATE, pendingRoll, 0f, 1f)
        }
        pendingDx = 0f; pendingDy = 0f; pendingFactor = 1f; pendingRoll = 0f
    }

    private fun endToolGesture() {
        if (!toolActive) return
        if (pendingDx != 0f || pendingDy != 0f) {
            onToolGesture(GesturePhase.UPDATE, nx(pendingDx), ny(pendingDy))
        }
        // Entrega la última muestra MOVE estable antes de END. REL la usa para
        // bloquear exactamente el marcador visto, sin confiar en el jitter de UP.
        onToolPointer(nx(lastX), ny(lastY))
        onToolGesture(GesturePhase.END, 0f, 0f)
        toolActive = false
        resetPending()
    }

    private fun endViewGesture() {
        if (!pairActive) return
        flushPair()
        onViewGesture(Gesture.PAN, GesturePhase.END, 0f, 0f, 1f)
        onViewGesture(Gesture.ZOOM, GesturePhase.END, 0f, 0f, 1f)
        onViewGesture(Gesture.ROLL, GesturePhase.END, 0f, 0f, 1f)
        pairActive = false
        resetPending()
    }

    private fun endNavigationOrbit() {
        if (!navigationOrbitActive) return
        if (pendingDx != 0f || pendingDy != 0f) {
            onViewGesture(Gesture.ORBIT, GesturePhase.UPDATE, nx(pendingDx), ny(pendingDy), 1f)
        }
        if (navigationOrbitBegan) onViewGesture(Gesture.ORBIT, GesturePhase.END, 0f, 0f, 1f)
        navigationOrbitActive = false
        navigationOrbitBegan = false
        resetPending()
        invalidate()
    }

    private fun cancelGestures() {
        if (toolActive) onToolGesture(GesturePhase.CANCEL, 0f, 0f)
        if (pairActive) {
            onViewGesture(Gesture.PAN, GesturePhase.CANCEL, 0f, 0f, 1f)
            onViewGesture(Gesture.ZOOM, GesturePhase.CANCEL, 0f, 0f, 1f)
            onViewGesture(Gesture.ROLL, GesturePhase.CANCEL, 0f, 0f, 1f)
        }
        if (navigationOrbitBegan) {
            onViewGesture(Gesture.ORBIT, GesturePhase.CANCEL, 0f, 0f, 1f)
        }
        toolActive = false
        pairActive = false
        navigationOrbitActive = false
        navigationOrbitBegan = false
        resetPending()
    }

    private fun resetPending() {
        pendingDx = 0f; pendingDy = 0f; pendingFactor = 1f; pendingRoll = 0f
    }

    private fun handleTap(e: MotionEvent) {
        val now = e.eventTime
        if (!repeatTap && !independentTaps && now - lastTapAt < DOUBLE_TAP_MS) {
            onDoubleTap()
            lastTapAt = 0L
        } else {
            lastTapAt = if (repeatTap || independentTaps) 0L else now
            // Confirma localmente que el toque sí se registró. No representa el
            // resultado remoto: solo elimina la incertidumbre durante el viaje de
            // picking y el siguiente frame MJPEG.
            tapFeedbackX = startX
            tapFeedbackY = startY
            tapFeedbackUntil = android.os.SystemClock.uptimeMillis() + 220L
            performHapticFeedback(android.view.HapticFeedbackConstants.KEYBOARD_TAP)
            invalidate()
            // u/v normalizados con origen arriba-izquierda: la conversión al eje Y de
            // Blender la hace el servidor.
            // El pequeño deslizamiento al levantar el pen no cambia el objetivo.
            onTap(nx(startX), ny(startY), isStylus(downToolType))
        }
    }

    /**
     * Cierra la forma dibujada y la entrega. Un recorrido por debajo del umbral de
     * deslizamiento es un tap simple con la herramienta armada: no hace nada.
     */
    private fun finishShape() {
        invalidate()
        if (shapeTool == ShapeTool.CIRCLE && fixedCircleRadius != null) {
            val radius = fixedCircleRadius!!.coerceIn(0.01f, 0.5f)
            onShape(shapeTool, nx(shapeStartX), ny(shapeStartY), nx(shapeStartX) + radius, ny(shapeStartY))
            return
        }
        if (hypot(shapeCurrentX - shapeStartX, shapeCurrentY - shapeStartY) <= systemTouchSlop) return
        onShape(shapeTool, nx(shapeStartX), ny(shapeStartY), nx(shapeCurrentX), ny(shapeCurrentY))
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        cadOverlay.forEach { stroke ->
            cadPaint.color = if (stroke.selected && (stroke.selectedParts.isEmpty() || "BODY" in stroke.selectedParts)) 0xffffb347.toInt() else 0xff57dfe6.toInt()
            val path = android.graphics.Path()
            stroke.points.forEachIndexed { index, (u, v) ->
                if (index == 0) path.moveTo(u * width, v * height) else path.lineTo(u * width, v * height)
            }
            if (stroke.closed) path.close()
            canvas.drawPath(path, cadPaint)
            stroke.selectedParts.filter { it.startsWith("EDGE") }.forEach { part ->
                val index = part.removePrefix("EDGE").toIntOrNull()
                if (index != null && index in stroke.points.indices) {
                    val a = stroke.points[index]; val b = stroke.points[(index + 1) % stroke.points.size]
                    cadPaint.color = 0xffffb347.toInt()
                    canvas.drawLine(a.first * width, a.second * height, b.first * width, b.second * height, cadPaint)
                }
            }
            stroke.handles.forEach { handle ->
                cadPaint.style = android.graphics.Paint.Style.FILL
                cadPaint.color = if (handle.selected) 0xffffb347.toInt() else 0xffe0fafc.toInt()
                canvas.drawCircle(handle.point.first * width, handle.point.second * height,
                    (if (handle.selected) 5f else 3.5f) * resources.displayMetrics.density, cadPaint)
            }
            cadPaint.style = android.graphics.Paint.Style.STROKE
        }
        if (navigationOrbitEnabled) drawNavigationOrbit(canvas)
        if (shapeDrawing) {
            if (shapeTool == ShapeTool.BOX) {
                canvas.drawRect(
                    minOf(shapeStartX, shapeCurrentX), minOf(shapeStartY, shapeCurrentY),
                    maxOf(shapeStartX, shapeCurrentX), maxOf(shapeStartY, shapeCurrentY),
                    shapePaint,
                )
            } else if (shapeTool == ShapeTool.CIRCLE) {
                canvas.drawCircle(
                    shapeStartX, shapeStartY,
                    hypot(shapeCurrentX - shapeStartX, shapeCurrentY - shapeStartY),
                    shapePaint,
                )
            } else if (shapeTool == ShapeTool.LINE) {
                // Bisect: la línea completa, no un segmento acotado a la pantalla — es
                // justo lo que verá el usuario cuando confirme (un plano que la cruza
                // entera), y confirma visualmente que no es una selección por caja.
                canvas.drawLine(shapeStartX, shapeStartY, shapeCurrentX, shapeCurrentY, shapePaint)
            }
        }
        if (knifePoints.any { it.isNotEmpty() }) {
            val radius = 7f * resources.displayMetrics.density
            knifePoints.forEach { stroke ->
                stroke.forEach { (u, v) -> canvas.drawCircle(u * width, v * height, radius, knifePaint) }
                for (index in 1 until stroke.size) {
                    val (u0, v0) = stroke[index - 1]
                    val (u1, v1) = stroke[index]
                    canvas.drawLine(u0 * width, v0 * height, u1 * width, v1 * height, knifePaint)
                }
            }
        }
        if (knifeDrawing) {
            val start = knifePoints.lastOrNull()?.lastOrNull()?.let { (u, v) -> u * width to v * height }
                ?: (shapeStartX to shapeStartY)
            canvas.drawLine(start.first, start.second, shapeCurrentX, shapeCurrentY, candidatePaint)
        }
        drawSnapCandidate(canvas)
        proportionalCircle?.takeIf { it.center.size >= 2 && it.radius > 0f }?.let {
            val radiusPixels = it.radius * width
            canvas.drawCircle(it.center[0] * width, it.center[1] * height,
                radiusPixels, proportionalPaint)
        }
        val remaining = tapFeedbackUntil - android.os.SystemClock.uptimeMillis()
        if (remaining <= 0L || tapFeedbackX < 0f) return
        tapPaint.alpha = (255f * remaining / 220f).toInt().coerceIn(0, 255)
        val progress = 1f - remaining / 220f
        val radius = (10f + 9f * progress) * resources.displayMetrics.density
        canvas.drawCircle(tapFeedbackX, tapFeedbackY, radius, tapPaint)
        postInvalidateOnAnimation()
    }

    private fun drawSnapCandidate(canvas: Canvas) {
        snapCandidate?.let { drawCandidate(canvas, it, candidatePaint) }
    }

    private fun drawCandidate(canvas: Canvas, candidate: SnapCandidate, paint: Paint) {
        if (candidate.screen.size < 2) return
        val x = candidate.screen[0].toFloat() * width
        val y = candidate.screen[1].toFloat() * height
        val r = 9f * resources.displayMetrics.density
        when (candidate.type) {
            SnapType.VERTEX -> canvas.drawCircle(x, y, r, paint)
            SnapType.EDGE -> {
                canvas.drawLine(x - r, y, x + r, y, paint)
                canvas.drawCircle(x, y, r * .45f, paint)
            }
            SnapType.EDGE_CENTER, SnapType.FACE_CENTER ->
                canvas.drawRect(x - r * .65f, y - r * .65f, x + r * .65f, y + r * .65f, paint)
            SnapType.FACE -> canvas.drawRect(x - r, y - r, x + r, y + r, paint)
            else -> {
                canvas.drawLine(x - r, y, x + r, y, paint)
                canvas.drawLine(x, y - r, x, y + r, paint)
            }
        }
    }

    private fun drawNavigationOrbit(canvas: Canvas) {
        val circle = NavigationOrbitLayout.circle(width, height) ?: return
        val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = android.graphics.Color.parseColor(if (navigationOrbitActive) "#6B4C8DFF" else "#384C8DFF")
            style = Paint.Style.FILL
        }
        val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = android.graphics.Color.parseColor("#B3B9D2FF")
            style = Paint.Style.STROKE
            strokeWidth = 2f * resources.displayMetrics.density
        }
        canvas.drawCircle(circle.x, circle.y, circle.radius, fill)
        canvas.drawCircle(circle.x, circle.y, circle.radius, stroke)
        val arm = circle.radius * .38f
        canvas.drawLine(circle.x - arm, circle.y, circle.x + arm, circle.y, stroke)
        canvas.drawLine(circle.x, circle.y - arm, circle.x, circle.y + arm, stroke)
    }

    private fun fireLongPress(x: Float, y: Float) {
        removeCallbacks(longPressRunnable)
        if (!longPressEnabled || longPressFired || moved) return
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
