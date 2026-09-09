package com.blendertablet.remote.ui

import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.PressInteraction
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed

/**
 * Pulsación sin el círculo de Material.
 *
 * El ripple queda bien en una app de móvil, pero en una herramienta de diseño sobre
 * un viewport a pantalla completa distrae. El estado seleccionado ya se comunica con
 * color y fondo.
 */
fun Modifier.clickableNoRipple(onClick: () -> Unit): Modifier =
    clickableNoRipple(onClick, null, null)

fun Modifier.clickableNoRipple(onClick: () -> Unit, onLongClick: (() -> Unit)?,
    onLongClickLabel: String?): Modifier = composed {
    val interaction = remember { MutableInteractionSource() }
    if (onLongClick == null) clickable(interactionSource = interaction, indication = null, onClick = onClick)
    else combinedClickable(interactionSource = interaction, indication = null, onClick = onClick,
        onLongClick = onLongClick, onLongClickLabel = onLongClickLabel)
}

/** Uses the normal button gesture policy, including scroll and pointer cancellation. */
fun Modifier.repeatingClick(enabled: Boolean, onClick: () -> Unit): Modifier = composed {
    val interaction = remember { MutableInteractionSource() }
    val latestClick by rememberUpdatedState(onClick)
    val press = remember { RepeatingPress { latestClick() } }
    LaunchedEffect(interaction, enabled) {
        try {
            if (enabled) interaction.interactions.collect { event ->
                when (event) {
                    is PressInteraction.Press -> press.press(this)
                    is PressInteraction.Release -> press.release()
                    is PressInteraction.Cancel -> press.cancel()
                }
            }
        } finally {
            press.cancel()
        }
    }
    clickable(enabled = enabled, interactionSource = interaction, indication = null,
        onClick = press::click)
}
