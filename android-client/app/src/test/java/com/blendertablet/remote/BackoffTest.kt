package com.blendertablet.remote

import com.blendertablet.remote.network.Backoff
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class BackoffTest {
    @Test
    fun `crece al doble desde medio segundo`() {
        assertEquals(500L, Backoff.baseDelayMs(1))
        assertEquals(1_000L, Backoff.baseDelayMs(2))
        assertEquals(2_000L, Backoff.baseDelayMs(3))
        assertEquals(4_000L, Backoff.baseDelayMs(4))
    }

    @Test
    fun `se estanca en el tope y no desborda`() {
        assertEquals(Backoff.MAX_DELAY_MS, Backoff.baseDelayMs(10))
        // Una desconexión larga acumula intentos; el desplazamiento no debe
        // volverse negativo ni la espera hacerse infinita.
        assertEquals(Backoff.MAX_DELAY_MS, Backoff.baseDelayMs(1_000))
        assertEquals(Backoff.MAX_DELAY_MS, Backoff.baseDelayMs(Int.MAX_VALUE))
    }

    @Test
    fun `el jitter se queda dentro del veinte por ciento`() {
        for (attempt in 1..12) {
            val base = Backoff.baseDelayMs(attempt)
            val margin = (base * 0.2).toLong()
            repeat(50) {
                val delay = Backoff.delayMs(attempt)
                assertTrue(
                    "intento $attempt dio $delay, fuera de [${base - margin}, ${base + margin}]",
                    delay in (base - margin)..(base + margin),
                )
            }
        }
    }
}
