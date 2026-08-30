package com.blendertablet.remote

import com.blendertablet.remote.ui.viewportLongPressEnabled
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ViewportLongPressTest {
    @Test fun `el radial se bloquea durante una transformacion`() {
        assertFalse(viewportLongPressEnabled(transformActive = true, toolActive = false))
    }

    @Test fun `el radial se bloquea durante una tool`() {
        assertFalse(viewportLongPressEnabled(transformActive = false, toolActive = true))
    }

    @Test fun `el radial sigue disponible sin sesiones`() {
        assertTrue(viewportLongPressEnabled(transformActive = false, toolActive = false))
    }
}
