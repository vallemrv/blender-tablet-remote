package com.blendertablet.remote.ui

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.Icon
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
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.blendertablet.remote.model.RadialLayout
import kotlin.math.cos
import kotlin.math.roundToInt
import kotlin.math.sin

/**
 * Una entrada del menú rápido.
 *
 * Con [children] deja de ser una acción y pasa a ser un grupo: al tocarlo, el anillo
 * se sustituye por el de sus hijos. [tint] permite marcar una acción como destructiva
 * (roja) para que no se confunda con las frecuentes.
 */
data class QuickAction(
    val label: String,
    val icon: ImageVector,
    val enabled: Boolean = true,
    val tint: Color? = null,
    val children: List<QuickAction> = emptyList(),
    /** Extrude: tap ejecuta la variante por defecto; long-click abre variantes. */
    val opensChildrenOnClick: Boolean = true,
    val onClick: () -> Unit = {},
    val onLongClick: (() -> Unit)? = null,
) {
    val isGroup: Boolean get() = children.isNotEmpty()
}

/**
 * Menú radial que se abre con pulsación larga en el punto tocado (§16).
 *
 * Radial y no lista porque la mano ya está ahí: el recorrido hasta cualquier opción
 * es el mismo y no hay que apuntar a una fila concreta. El centro se ajusta a los
 * bordes para que ningún sector quede fuera de pantalla, y una etiqueta en el centro
 * recuerda qué hay bajo el dedo.
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
    val progress by animateFloatAsState(if (open) 1f else 0f, tween(150), label = "quickmenu")
    // El submenú abierto, o null en el primer nivel. Se reinicia con cada apertura
    // porque `center` cambia al pulsar en otro punto.
    var group by remember(center) { mutableStateOf<QuickAction?>(null) }
    val level = group?.children ?: actions

    BoxWithConstraints(modifier.fillMaxSize().clickableNoRipple(onDismiss)) {
        val density = androidx.compose.ui.platform.LocalDensity.current.density
        // El centro llega en píxeles; el ajuste a bordes se hace en dp.
        val (cxDp, cyDp) = RadialLayout.clampCenter(
            center.first / density, center.second / density,
            maxWidth.value, maxHeight.value,
        )
        val cx = cxDp * density
        val cy = cyDp * density

        // Velo suave: indica que el menú captura el siguiente toque.
        Box(Modifier.fillMaxSize().background(Color.Black.copy(alpha = .35f * progress)))

        // Etiqueta central: qué hay bajo el dedo.
        Box(
            Modifier
                .offset { androidx.compose.ui.unit.IntOffset(cx.roundToInt(), cy.roundToInt()) }
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

        level.forEachIndexed { index, action ->
            // Arranca arriba y reparte en círculo.
            val angle = (-90.0 + index * (360.0 / level.size)) * Math.PI / 180.0
            val distance = RadialLayout.RADIUS_DP * progress
            RadialItem(
                action = action,
                x = cx,
                y = cy,
                dx = (cos(angle) * distance).toFloat().dp,
                dy = (sin(angle) * distance).toFloat().dp,
                progress = progress,
                // Entrar en un grupo no cierra el menú; ejecutar una acción sí.
                onActivate = { if (action.isGroup) group = action else action.onClick() },
                onDismiss = onDismiss,
            )
        }

        // En un submenú, el centro vuelve atrás. Sin esto la única salida sería
        // cerrar el menú entero y volver a mantener pulsado.
        group?.let {
            RadialItem(
                action = QuickAction("Atrás", Icons.Default.Close, onClick = {}),
                x = cx,
                y = cy,
                dx = 0.dp,
                dy = 0.dp,
                progress = progress,
                onActivate = { group = null },
                onDismiss = onDismiss,
                closeOnActivate = false,
            )
        }
    }
}

@Composable
private fun RadialItem(
    action: QuickAction,
    x: Float,
    y: Float,
    dx: Dp,
    dy: Dp,
    progress: Float,
    onActivate: () -> Unit,
    onDismiss: () -> Unit,
    closeOnActivate: Boolean = !action.isGroup,
) {
    Column(
        Modifier
            .offset { androidx.compose.ui.unit.IntOffset(x.roundToInt(), y.roundToInt()) }
            .offset(dx - 30.dp, dy - 30.dp)
            .size(60.dp)
            .scale(0.85f + 0.15f * progress)
            .alpha(progress)
            .clip(RoundedCornerShape(14.dp))
            .background(if (action.enabled) Ink.Elevated else Ink.Elevated.copy(alpha = .5f))
            .then(
                if (action.enabled) {
                    Modifier.clickableNoRipple { onActivate(); if (closeOnActivate) onDismiss() }
                } else {
                    Modifier
                }
            )
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
