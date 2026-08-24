package com.blendertablet.remote.model

/**
 * Geometría del menú radial, separada de Compose para poder probarla en la JVM.
 *
 * El menú pinta sus entradas sobre un círculo alrededor del punto tocado. Si ese
 * punto está cerca de un borde o de una esquina, las entradas se saldrían de la
 * pantalla; [clampCenter] desplaza el centro para que todas quepan dentro.
 */
object RadialLayout {

    /** Radio del círculo donde se reparten las entradas, en dp. */
    const val RADIUS_DP = 92f

    /** La mitad del tamaño de una entrada (60 dp de ancho), en dp. */
    const val ITEM_HALF_DP = 30f

    /**
     * Devuelve el centro ajustado para que las entradas (a [RADIUS_DP] del centro y
     * de ancho [ITEM_HALF_DP]) queden enteras dentro del viewport de [width]×[height].
     */
    fun clampCenter(x: Float, y: Float, width: Float, height: Float): Pair<Float, Float> {
        val margin = RADIUS_DP + ITEM_HALF_DP
        // Si el viewport es menor que el anillo (pantalla diminuta), se degrada al centro.
        val loX = margin.coerceAtMost(width / 2f)
        val hiX = (width - margin).coerceAtLeast(width / 2f)
        val loY = margin.coerceAtMost(height / 2f)
        val hiY = (height - margin).coerceAtLeast(height / 2f)
        return x.coerceIn(loX, hiX) to y.coerceIn(loY, hiY)
    }
}
