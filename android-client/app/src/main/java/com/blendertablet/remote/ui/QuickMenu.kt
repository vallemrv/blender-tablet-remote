package com.blendertablet.remote.ui

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronLeft
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.Icon
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.blendertablet.remote.model.RadialLayout
import kotlin.math.cos
import kotlin.math.roundToInt
import kotlin.math.sin

/**
 * Una entrada del menú rápido.
 *
 * Con [children] deja de ser una acción y pasa a ser un grupo. [tint] permite marcar
 * una acción como destructiva (roja) para que no se confunda con las frecuentes.
 */
data class QuickAction(
    val label: String,
    val icon: ImageVector,
    val enabled: Boolean = true,
    val tint: Color? = null,
    val children: List<QuickAction> = emptyList(),
    /** Extrude: tap ejecuta la variante por defecto; long-click abre variantes. */
    val opensChildrenOnClick: Boolean = true,
    val onLongClick: (() -> Unit)? = null,
    /**
     * Debe ser el último parámetro funcional: Kotlin asigna aquí la trailing lambda
     * de `QuickAction(...) { acción() }`. Cuando onLongClick estaba después, todos
     * esos taps quedaban con un onClick vacío y la acción terminaba conectada a una
     * pulsación larga que el usuario nunca había pedido.
     */
    val onClick: () -> Unit = {},
) {
    val isGroup: Boolean get() = children.isNotEmpty()
}

/**
 * Menú de la pulsación larga (§16, plan 001).
 *
 * El primer nivel es siempre el anillo radial: la mano ya está ahí, y para un puñado
 * curado de acciones (≤8) el recorrido hasta cualquiera es el mismo. A partir del
 * segundo nivel (Agregar > Malla, un submenú de variantes, el catálogo de tools de
 * malla…) se pasa a un panel vertical flotante con cabecera y X: una lista ya no
 * gana nada por ser circular, y cabe más contenido sin paginar en sub-anillos.
 */
@Composable
fun QuickMenu(
    open: Boolean,
    center: Pair<Float, Float>,
    actions: List<QuickAction>,
    contextLabel: String,
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier,
) {
    if (!open || actions.isEmpty()) return
    // Ruta de submenús abiertos. Se reinicia con cada apertura porque `center`
    // cambia al pulsar en otro punto.
    var path by remember(center) { mutableStateOf<List<QuickAction>>(emptyList()) }

    if (path.isEmpty()) {
        RadialRing(
            actions = actions,
            center = center,
            contextLabel = contextLabel,
            onEnter = { path = path + it },
            onDismiss = onDismiss,
            modifier = modifier,
        )
    } else {
        VerticalMenuPanel(
            path = path,
            anchor = center,
            onEnter = { path = path + it },
            onBack = { path = path.dropLast(1) },
            onDismiss = onDismiss,
            modifier = modifier,
        )
    }
}

@Composable
private fun RadialRing(
    actions: List<QuickAction>,
    center: Pair<Float, Float>,
    contextLabel: String,
    onEnter: (QuickAction) -> Unit,
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val progress by animateFloatAsState(1f, tween(150), label = "quickmenu")

    BoxWithConstraints(modifier.fillMaxSize()) {
        val density = LocalDensity.current.density
        // El centro llega en píxeles; el ajuste a bordes se hace en dp.
        val (cxDp, cyDp) = RadialLayout.clampCenter(
            center.first / density, center.second / density,
            maxWidth.value, maxHeight.value,
        )
        val cx = cxDp * density
        val cy = cyDp * density

        fun activate(action: QuickAction, longPress: Boolean = false) {
            when {
                longPress && action.isGroup && !action.opensChildrenOnClick -> onEnter(action)
                longPress && action.onLongClick != null -> action.onLongClick.invoke()
                action.isGroup && action.opensChildrenOnClick -> onEnter(action)
                else -> {
                    action.onClick()
                    onDismiss()
                }
            }
        }

        // Velo suave: indica que el menú captura el siguiente toque.
        Box(
            Modifier
                .fillMaxSize()
                .background(Color.Black.copy(alpha = .35f * progress))
                .pointerInput(actions, cxDp, cyDp) {
                    detectTapGestures(
                        onTap = { point ->
                            val index = RadialLayout.hitIndex(
                                point.x / density, point.y / density, cxDp, cyDp, actions.size,
                            )
                            if (index == null) onDismiss() else if (actions[index].enabled) activate(actions[index])
                        },
                        onLongPress = { point ->
                            val index = RadialLayout.hitIndex(
                                point.x / density, point.y / density, cxDp, cyDp, actions.size,
                            )
                            if (index != null && actions[index].enabled) activate(actions[index], longPress = true)
                        },
                    )
                },
        )

        // Etiqueta central: qué hay bajo el dedo.
        Box(
            Modifier
                .offset { IntOffset(cx.roundToInt(), cy.roundToInt()) }
                .offset((-40).dp, (-12).dp)
                .size(80.dp),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                contextLabel,
                color = Ink.Muted,
                fontSize = 10.sp,
                maxLines = 2,
                modifier = Modifier.padding(horizontal = 6.dp),
            )
        }

        actions.forEachIndexed { index, action ->
            // Arranca arriba y reparte en círculo.
            val angle = (-90.0 + index * (360.0 / actions.size)) * Math.PI / 180.0
            val distance = RadialLayout.RADIUS_DP * progress
            RadialItem(
                action = action,
                x = cx,
                y = cy,
                dx = (cos(angle) * distance).toFloat().dp,
                dy = (sin(angle) * distance).toFloat().dp,
                progress = progress,
            )
        }
    }
}

/**
 * Un sector del anillo. Tap normalmente ejecuta o entra en el grupo; con
 * `opensChildrenOnClick = false` (Extrude en el catálogo legacy: variante por
 * defecto en tap, selector en long-click) tap ejecuta y long-click entra.
 */
@Composable
private fun RadialItem(
    action: QuickAction,
    x: Float,
    y: Float,
    dx: Dp,
    dy: Dp,
    progress: Float,
) {
    Column(
        Modifier
            .offset { IntOffset(x.roundToInt(), y.roundToInt()) }
            .offset(dx - 30.dp, dy - 30.dp)
            .size(60.dp)
            .scale(0.85f + 0.15f * progress)
            .alpha(progress)
            .clip(RoundedCornerShape(14.dp))
            .background(if (action.enabled) Ink.Elevated else Ink.Elevated.copy(alpha = .5f))
            .padding(4.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Box(Modifier.size(28.dp).clip(CircleShape), contentAlignment = Alignment.Center) {
            Icon(
                action.icon,
                action.label,
                Modifier.size(20.dp),
                tint = when {
                    !action.enabled -> Ink.Faint
                    action.tint != null -> action.tint
                    else -> Ink.OnPanel
                },
            )
        }
        Text(
            action.label,
            color = if (action.enabled) Ink.Muted else Ink.Faint,
            fontSize = 9.sp,
            maxLines = 1,
        )
    }
}

/**
 * Panel vertical flotante para el segundo nivel y siguientes (plan 001 F1): una
 * lista no gana nada por repartirse en círculo, y así el catálogo de tools de malla
 * o un Agregar con muchas primitivas no necesitan paginarse en sub-anillos.
 *
 * Ancla cerca del punto que abrió el menú, igual que hacía el `ContextSheet`
 * original, con la misma cabecera (ruta + X) y fila "Atrás".
 */
@Composable
private fun VerticalMenuPanel(
    path: List<QuickAction>,
    anchor: Pair<Float, Float>,
    onEnter: (QuickAction) -> Unit,
    onBack: () -> Unit,
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val level = path.last().children
    val title = path.joinToString(" · ") { it.label }

    BoxWithConstraints(modifier.fillMaxSize().clickableNoRipple(onDismiss)) {
        val density = LocalDensity.current.density
        var panelSize by remember { mutableStateOf<IntSize?>(null) }
        val panelWidth = 288.dp
        val pad = 8.dp

        val maxX = (maxWidth.value - panelWidth.value - pad.value).coerceAtLeast(pad.value)
        val x = (anchor.first / density + pad.value).coerceIn(pad.value, maxX)
        val measuredH = (panelSize?.height ?: 0) / density
        val maxY = (maxHeight.value - measuredH - pad.value).coerceAtLeast(pad.value)
        val y = (anchor.second / density + pad.value).coerceIn(pad.value, maxY)

        // Velo suave: indica que el menú captura el siguiente toque.
        Box(Modifier.fillMaxSize().background(Color.Black.copy(alpha = .35f)))

        Surface(
            color = Ink.Panel,
            shape = RoundedCornerShape(16.dp),
            tonalElevation = 0.dp,
            modifier = Modifier
                .offset { IntOffset(x.dp.roundToPx(), y.dp.roundToPx()) }
                .width(panelWidth)
                .heightIn(max = maxHeight - pad * 2)
                .onGloballyPositioned { panelSize = it.size },
        ) {
            Column(Modifier.padding(Metrics.PanelPadding)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        title,
                        color = Ink.Muted,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.SemiBold,
                        maxLines = 1,
                        modifier = Modifier.weight(1f).padding(start = 8.dp),
                    )
                    IconAction(Icons.Default.Close, "Cerrar menú", onClick = onDismiss)
                }
                Box(
                    Modifier
                        .padding(horizontal = 8.dp)
                        .fillMaxWidth()
                        .height(1.dp)
                        .background(Ink.Divider),
                )

                Column(
                    Modifier
                        .padding(horizontal = 4.dp)
                        .heightIn(max = 420.dp)
                        .verticalScroll(rememberScrollState()),
                ) {
                    BackRow(onBack)
                    for (action in level) {
                        SheetRow(
                            action,
                            onClick = {
                                if (action.isGroup && action.opensChildrenOnClick) onEnter(action)
                                else {
                                    action.onClick()
                                    onDismiss()
                                }
                            },
                            onLongClick = if (action.isGroup && !action.opensChildrenOnClick) {
                                { onEnter(action) }
                            } else {
                                action.onLongClick
                            },
                        )
                    }
                }
            }
        }
    }
}

/** Fila del menú: icono, etiqueta y galón si abre subnivel. Objetivo táctil generoso. */
@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun SheetRow(action: QuickAction, onClick: () -> Unit, onLongClick: (() -> Unit)?) {
    Row(
        Modifier
            .fillMaxWidth()
            .heightIn(min = 44.dp)
            .clip(RoundedCornerShape(10.dp))
            .then(if (action.enabled) Modifier.combinedClickable(onClick = onClick, onLongClick = onLongClick) else Modifier)
            .padding(horizontal = 10.dp, vertical = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            action.icon,
            action.label,
            Modifier.size(20.dp),
            tint = when {
                !action.enabled -> Ink.Faint
                action.tint != null -> action.tint
                else -> Ink.Muted
            },
        )
        Spacer(Modifier.width(12.dp))
        Text(
            action.label,
            color = if (action.enabled) Ink.OnPanel else Ink.Faint,
            fontSize = 13.sp,
            modifier = Modifier.weight(1f),
        )
        if (action.isGroup) {
            Icon(Icons.Default.ChevronRight, null, Modifier.size(16.dp), tint = Ink.Faint)
        }
    }
}

/** Volver al nivel anterior (el anillo, si solo había uno de profundidad). */
@Composable
private fun BackRow(onBack: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .heightIn(min = 44.dp)
            .clip(RoundedCornerShape(10.dp))
            .clickableNoRipple(onBack)
            .padding(horizontal = 10.dp, vertical = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(Icons.Default.ChevronLeft, null, Modifier.size(18.dp), tint = Ink.Accent)
        Spacer(Modifier.width(12.dp))
        Text("Atrás", color = Ink.Accent, fontSize = 13.sp, modifier = Modifier.weight(1f))
    }
    Box(
        Modifier
            .padding(horizontal = 10.dp)
            .fillMaxWidth()
            .height(1.dp)
            .background(Ink.Divider),
    )
}
