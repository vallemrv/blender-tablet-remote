package com.blendertablet.remote.ui

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

/**
 * Paleta y medidas de la interfaz.
 *
 * Oscura, poco saturada y con mucha transparencia: todo lo que no sea el viewport
 * debe pesar lo menos posible visualmente (§51, §52). Los paneles flotan sobre la
 * imagen en vez de robarle sitio.
 */
object Ink {
    val Background = Color(0xFF0E1013)
    val Panel = Color(0xE61A1D22)          // 90% opaco: deja intuir el viewport debajo
    val PanelSolid = Color(0xFF1A1D22)
    val Elevated = Color(0xF223262C)
    val Divider = Color(0x1AFFFFFF)
    val Accent = Color(0xFF4C8DFF)
    val OnPanel = Color(0xFFE6E8EB)
    val Muted = Color(0x99E6E8EB)
    val Faint = Color(0x59E6E8EB)

    val Ok = Color(0xFF57C98A)
    val Warn = Color(0xFFE8B454)
    val Bad = Color(0xFFE8685D)

    val AxisX = Color(0xFFE05B62)
    val AxisY = Color(0xFF8BC34A)
    val AxisZ = Color(0xFF4A90D9)
}

object Metrics {
    /** Objetivo táctil mínimo (§83). El icono se dibuja más pequeño dentro. */
    val Touch = 44.dp
    val IconSize = 20.dp
    val Radius = 14.dp
    val PanelPadding = 8.dp
    val EdgeMargin = 10.dp

    /**
     * Hueco que reserva una bandeja horizontal inferior (una línea de controles
     * ~44 dp + el padding del panel). Con una bandeja presente, el teclado de
     * vistas se eleva esta altura para no quedar tapado ni taparla.
     */
    val TrayInset = 64.dp
}
