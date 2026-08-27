package com.blendertablet.remote

import com.blendertablet.remote.model.RadialLayout
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * El menú radial debe caber entero en pantalla aunque el long click sea en una
 * esquina: si no, parte del anillo quedaría fuera y sería imposible pulsarlo.
 */
class RadialLayoutTest {

    private val w = 1280f
    private val h = 754f
    private val margin = RadialLayout.RADIUS_DP + RadialLayout.ITEM_HALF_DP

    @Test
    fun `el centro sin peligro queda como esta`() {
        val (x, y) = RadialLayout.clampCenter(640f, 377f, w, h)
        assertEquals(640f, x, 0.01f)
        assertEquals(377f, y, 0.01f)
    }

    @Test
    fun `esquina superior izquierda se aleja del borde`() {
        val (x, y) = RadialLayout.clampCenter(0f, 0f, w, h)
        assertEquals(margin, x, 0.01f)
        assertEquals(margin, y, 0.01f)
    }

    @Test
    fun `esquina inferior derecha se aleja del borde`() {
        val (x, y) = RadialLayout.clampCenter(w, h, w, h)
        assertEquals(w - margin, x, 0.01f)
        assertEquals(h - margin, y, 0.01f)
    }

    @Test
    fun `las cuatro esquinas caben dentro del viewport`() {
        val corners = listOf(0f to 0f, w to 0f, 0f to h, w to h)
        for ((cx, cy) in corners) {
            val (x, y) = RadialLayout.clampCenter(cx, cy, w, h)
            assertTrue("x fuera: $x", x >= margin && x <= w - margin)
            assertTrue("y fuera: $y", y >= margin && y <= h - margin)
        }
    }

    @Test
    fun `un viewport mas pequeno que el anillo degrada al centro`() {
        // Si la pantalla es diminuta, el centro se clava en la mitad y no se sale.
        val (x, y) = RadialLayout.clampCenter(0f, 0f, 50f, 50f)
        assertEquals(25f, x, 0.01f)
        assertEquals(25f, y, 0.01f)
    }

    @Test
    fun `cada icono radial resuelve su indice`() {
        val count = 8
        val cx = 300f
        val cy = 240f
        for (index in 0 until count) {
            val angle = Math.toRadians(-90.0 + index * (360.0 / count))
            val x = cx + kotlin.math.cos(angle).toFloat() * RadialLayout.RADIUS_DP
            val y = cy + kotlin.math.sin(angle).toFloat() * RadialLayout.RADIUS_DP
            assertEquals(index, RadialLayout.hitIndex(x, y, cx, cy, count))
        }
    }

    @Test
    fun `centro y exterior no ejecutan acciones`() {
        assertNull(RadialLayout.hitIndex(300f, 240f, 300f, 240f, 8))
        assertNull(RadialLayout.hitIndex(0f, 0f, 300f, 240f, 8))
    }
}
