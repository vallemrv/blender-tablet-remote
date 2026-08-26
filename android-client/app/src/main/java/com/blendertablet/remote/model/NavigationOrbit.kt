package com.blendertablet.remote.model

import kotlin.math.hypot
import kotlin.math.min

/**
 * Geometría del círculo de órbita disponible durante una sesión modal.
 *
 * Se expresa a partir del tamaño real de la superficie de vídeo, en vez de una
 * coordenada Compose: así lo que se dibuja y lo que captura [InputSurface] son
 * exactamente el mismo objetivo. Se sitúa en el lateral derecho y a media altura,
 * fuera de la barra superior y de los paneles inferiores (incluido su desplazamiento
 * cuando aparece una bandeja).
 */
object NavigationOrbitLayout {
    private const val RADIUS_FRACTION = .13f
    private const val RIGHT_MARGIN_FRACTION = .045f
    private const val CENTER_Y_FRACTION = .55f

    data class Circle(val x: Float, val y: Float, val radius: Float)

    fun circle(width: Int, height: Int): Circle? {
        if (width <= 0 || height <= 0) return null
        val base = min(width, height).toFloat()
        val radius = base * RADIUS_FRACTION
        return Circle(
            x = width - radius - base * RIGHT_MARGIN_FRACTION,
            y = height * CENTER_Y_FRACTION,
            radius = radius,
        )
    }

    fun contains(width: Int, height: Int, x: Float, y: Float): Boolean {
        val circle = circle(width, height) ?: return false
        return hypot(x - circle.x, y - circle.y) <= circle.radius
    }
}
