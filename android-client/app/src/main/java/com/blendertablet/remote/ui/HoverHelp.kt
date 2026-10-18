package com.blendertablet.remote.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.PointerEvent
import androidx.compose.ui.input.pointer.PointerEventPass
import androidx.compose.ui.input.pointer.PointerEventType
import androidx.compose.ui.input.pointer.PointerType
import androidx.compose.ui.node.ModifierNodeElement
import androidx.compose.ui.node.PointerInputModifierNode
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntRect
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Popup
import androidx.compose.ui.window.PopupPositionProvider
import androidx.compose.ui.window.PopupProperties
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.delay

/** Observa la proximidad sin consumir gestos, tampoco en los sectores del radial. */
@Composable
internal fun HoverHelp(
    title: String,
    explanation: String = "",
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    contentAlignment: Alignment = Alignment.Center,
    content: @Composable BoxScope.() -> Unit,
) {
    var hovering by remember { mutableStateOf(false) }
    var ready by remember { mutableStateOf(false) }
    LaunchedEffect(hovering, title, explanation, enabled) {
        ready = false
        if (hovering) {
            delay(450)
            ready = true
        }
    }
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    DisposableEffect(lifecycle) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_PAUSE) { hovering = false; ready = false }
        }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer) }
    }
    val observer = remember { HoverObserver { hovering = it; if (!it) ready = false } }
    val gap = with(LocalDensity.current) { 8.dp.roundToPx() }
    Box(modifier.then(observer), contentAlignment = contentAlignment) {
        content()
        if (hovering && ready && title.isNotBlank()) {
            Popup(
                popupPositionProvider = remember(gap) { HelpPosition(gap) },
                properties = PopupProperties(focusable = false, dismissOnBackPress = false, dismissOnClickOutside = false),
            ) {
                Column(Modifier.widthIn(max = 280.dp)
                    .background(Ink.PanelSolid, RoundedCornerShape(10.dp))
                    .border(1.dp, Ink.Accent.copy(alpha = .5f), RoundedCornerShape(10.dp))
                    .padding(12.dp)) {
                    Text(title, color = Ink.OnPanel, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                    if (explanation.isNotBlank() && explanation != title) {
                        Text(explanation, color = Ink.Muted, fontSize = 12.sp, modifier = Modifier.padding(top = 5.dp))
                    }
                    if (!enabled) Text("No disponible en el estado actual.",
                        color = Ink.Muted, fontSize = 12.sp, modifier = Modifier.padding(top = 5.dp))
                }
            }
        }
    }
}

internal fun isHelpHover(type: PointerEventType, pointers: List<Pair<PointerType, Boolean>>): Boolean =
    (type == PointerEventType.Enter || type == PointerEventType.Move) &&
        pointers.isNotEmpty() && pointers.none { it.second } &&
        pointers.any { it.first == PointerType.Stylus || it.first == PointerType.Eraser || it.first == PointerType.Mouse }

private data class HoverObserver(val onHover: (Boolean) -> Unit) : ModifierNodeElement<HoverObserverNode>() {
    override fun create() = HoverObserverNode(onHover)
    override fun update(node: HoverObserverNode) { node.onHover = onHover }
}

internal class HoverObserverNode(var onHover: (Boolean) -> Unit) : Modifier.Node(), PointerInputModifierNode {
    // El radial resuelve los toques en el velo situado detrás de sus iconos.
    // Añadir ayuda a un sector no debe impedir que ese hermano reciba el toque.
    override fun sharePointerInputWithSiblings() = true
    override fun onPointerEvent(pointerEvent: PointerEvent, pass: PointerEventPass, bounds: IntSize) {
        if (pass == PointerEventPass.Main) {
            onHover(isHelpHover(pointerEvent.type, pointerEvent.changes.map { it.type to it.pressed }))
        }
    }
    override fun onCancelPointerInput() { onHover(false) }
}

internal class HelpPosition(private val gap: Int) : PopupPositionProvider {
    override fun calculatePosition(anchorBounds: IntRect, windowSize: IntSize, layoutDirection: LayoutDirection,
                                   popupContentSize: IntSize): IntOffset {
        val x = (anchorBounds.center.x - popupContentSize.width / 2)
            .coerceIn(0, (windowSize.width - popupContentSize.width).coerceAtLeast(0))
        val above = anchorBounds.top - popupContentSize.height - gap
        val y = (if (above >= 0) above else anchorBounds.bottom + gap)
            .coerceIn(0, (windowSize.height - popupContentSize.height).coerceAtLeast(0))
        return IntOffset(x, y)
    }
}
