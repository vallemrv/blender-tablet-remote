package com.blendertablet.remote

import com.blendertablet.remote.ui.KNIFE_DISPATCH_MS
import com.blendertablet.remote.ui.knifeInstruction
import com.blendertablet.remote.ui.stableKnifeRelease
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class KnifeInteractionTest {
    @Test fun `Knife explica la colocacion por puntos`() {
        assertEquals("Pulsa, ajusta y suelta el primer punto", knifeInstruction(0))
        assertEquals("Coloca el segundo punto para cortar", knifeInstruction(1))
        assertEquals("Añade puntos o pulsa Nuevo corte", knifeInstruction(2))
    }

    @Test fun `Knife sondea con menos frecuencia que el gesto general`() {
        assertTrue(KNIFE_DISPATCH_MS >= 66L)
    }

    @Test fun `Knife confirma la ultima muestra estable y no el salto al levantar`() {
        assertEquals(120f to 240f, stableKnifeRelease(120f, 240f))
    }
}
