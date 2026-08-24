package com.blendertablet.remote.ui

import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.clickable
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed

/**
 * Pulsación sin el círculo de Material.
 *
 * El ripple queda bien en una app de móvil, pero en una herramienta de diseño sobre
 * un viewport a pantalla completa distrae. El estado seleccionado ya se comunica con
 * color y fondo.
 */
fun Modifier.clickableNoRipple(onClick: () -> Unit): Modifier = composed {
    val interaction = remember { MutableInteractionSource() }
    clickable(interactionSource = interaction, indication = null, onClick = onClick)
}
