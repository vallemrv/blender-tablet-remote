package com.blendertablet.remote

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import com.blendertablet.remote.ui.QuickAction
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class QuickActionBindingTest {

    /** Regresión del fallo real: la trailing lambda es el tap, no el long-click. */
    @Test
    fun `trailing lambda ejecuta onClick`() {
        var calls = 0
        val action = QuickAction("Borrar", Icons.Default.Delete) { calls += 1 }

        action.onClick()

        assertEquals(1, calls)
        assertNull(action.onLongClick)
    }
}
