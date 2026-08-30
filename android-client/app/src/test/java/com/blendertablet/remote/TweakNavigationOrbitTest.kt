package com.blendertablet.remote

import com.blendertablet.remote.model.ActiveTool
import com.blendertablet.remote.ui.navigationOrbitVisible
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class TweakNavigationOrbitTest {
    @Test fun `Tweak no muestra el circulo aunque use una sesion transform interna`() {
        assertFalse(navigationOrbitVisible(true, false, ActiveTool.TWEAK))
    }

    @Test fun `las transformaciones normales conservan el circulo`() {
        assertTrue(navigationOrbitVisible(true, false, ActiveTool.MOVE))
    }

    @Test fun `las tools parametricas conservan el circulo`() {
        assertTrue(navigationOrbitVisible(false, true, ActiveTool.EXTRUDE))
    }

    @Test fun `sin sesion no hay circulo`() {
        assertFalse(navigationOrbitVisible(false, false, ActiveTool.SELECT))
    }
}
