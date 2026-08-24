package com.blendertablet.remote.network

import kotlin.math.min
import kotlin.random.Random

/**
 * Espera entre reintentos de conexión: exponencial con tope y jitter.
 *
 * El jitter no es cosmético. La app reintenta el control y el vídeo por canales
 * distintos; sin desfase ambos caerían sobre el servidor en el mismo instante una
 * y otra vez, justo cuando Blender está recuperándose.
 */
object Backoff {
    const val FIRST_DELAY_MS = 500L
    const val MAX_DELAY_MS = 30_000L

    /** [attempt] empieza en 1 para el primer reintento. */
    fun delayMs(attempt: Int, random: Random = Random.Default): Long {
        val base = baseDelayMs(attempt)
        // ±20%: suficiente para desincronizar sin que la espera se note errática.
        val jitter = (base * 0.2).toLong()
        return base - jitter + random.nextLong(2 * jitter + 1)
    }

    /** La progresión sin jitter, que es lo que se puede afirmar en un test. */
    fun baseDelayMs(attempt: Int): Long {
        if (attempt <= 1) return FIRST_DELAY_MS
        // shl en Long y con el exponente acotado: 1 shl 63 se volvería negativo.
        val factor = 1L shl min(attempt - 1, 16)
        return min(FIRST_DELAY_MS * factor, MAX_DELAY_MS)
    }
}
