package com.blendertablet.remote

import com.blendertablet.remote.model.NavigationOrbitLayout
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class NavigationOrbitLayoutTest {
    @Test fun `el centro del circulo captura el gesto`() {
        val circle = NavigationOrbitLayout.circle(1600, 1000)
        assertNotNull(circle)
        assertTrue(NavigationOrbitLayout.contains(1600, 1000, circle!!.x, circle.y))
    }

    @Test fun `un gesto fuera del circulo no se captura aunque este en el lateral`() {
        assertFalse(NavigationOrbitLayout.contains(1600, 1000, 40f, 500f))
        assertFalse(NavigationOrbitLayout.contains(1600, 1000, 1590f, 20f))
    }

    @Test fun `tamanos no medidos no tienen zona activa`() {
        assertFalse(NavigationOrbitLayout.contains(0, 1000, 0f, 0f))
        assertFalse(NavigationOrbitLayout.contains(1000, 0, 0f, 0f))
    }
}
