package com.blendertablet.remote.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.text.font.FontWeight
import kotlin.math.roundToInt

/**
 * Menú contextual flotante de la pulsación larga en Object Mode.
 *
 * Lista anclada al punto tocado y no anillo radial: el vacío de Object Mode ofrece
 * "Agregar", cuyo catálogo (Malla, Curva, Luz…) no cabe ni se lee bien repartido en
 * círculo. Los grupos (Agregar, Aplicar, Establecer origen) se recorren sustituyendo
 * el contenido del panel, como los menús de la barra superior, y la cabecera lleva
 * una X que cierra el menú entero desde cualquier nivel.
 *
 * Edit Mode sigue usando el anillo ([QuickMenu]): su contexto siempre es la malla,
 * con pocas acciones frecuentes, y ahí el radial sigue siendo más rápido.
 */
@Composable
fun ContextSheet(
    open: Boolean,
    anchor: Pair<Float, Float>,
    actions: List<QuickAction>,
    contextLabel: String,
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier,
) {
    if (!open || actions.isEmpty()) return
    // Ruta de submenús abierta ("Agregar" > "Malla" > …). Se reinicia con cada
    // apertura porque `anchor` cambia al pulsar en otro punto.
    var path by remember(anchor) { mutableStateOf<List<QuickAction>>(emptyList()) }
    val level = path.lastOrNull()?.children ?: actions
    val title = if (path.isEmpty()) contextLabel else path.joinToString(" · ") { it.label }

    BoxWithConstraints(modifier.fillMaxSize().clickableNoRipple(onDismiss)) {
        val density = LocalDensity.current.density
        // El panel se mide para no salir por abajo: sin esto, un menú abierto cerca
        // del borde inferior dejaría filas inaccesibles fuera de pantalla.
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
                // Cabecera: dónde estamos y salida rápida desde cualquier nivel.
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
                        .weight(1f, fill = false)
                        .verticalScroll(rememberScrollState()),
                ) {
                    if (path.isNotEmpty()) {
                        BackRow(title) { path = path.dropLast(1) }
                    }
                    for (action in level) {
                        SheetRow(
                            action,
                            onClick = {
                                // Normalmente un grupo entra. Extrude conserva tap
                                // en Región y reserva las variantes al long-click.
                                if (action.isGroup && action.opensChildrenOnClick) path = path + action
                                else {
                                    action.onClick()
                                    onDismiss()
                                }
                            },
                            onLongClick = if (action.isGroup && !action.opensChildrenOnClick) {
                                { path = path + action }
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

/** Volver al nivel anterior. El rastro completo ya está en la cabecera. */
@Composable
private fun BackRow(trail: String, onBack: () -> Unit) {
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
