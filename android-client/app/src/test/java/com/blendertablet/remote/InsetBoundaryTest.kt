package com.blendertablet.remote

import com.blendertablet.remote.ui.toggledInsetBoundary
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class InsetBoundaryTest {
    @Test fun `costura fija desactiva Boundary y puede volver a activarlo`() {
        assertFalse(toggledInsetBoundary(boundary = true))
        assertTrue(toggledInsetBoundary(boundary = false))
    }
}
