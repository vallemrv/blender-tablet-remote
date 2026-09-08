package com.blendertablet.remote.model

import org.junit.Assert.*
import org.junit.Test

class ExtrudeVariantsTest {
    @Test fun faceVariantsAreUnavailableAfterSwitchingToEdgesOrVertices() {
        val individual = EditToolbarVariant("INDIVIDUAL", "Individual",
            requirements = mapOf("selection_modes" to listOf("FACE")))
        assertTrue(individual.availableIn(SelectionMode.FACE))
        assertFalse(individual.availableIn(SelectionMode.EDGE))
        assertFalse(individual.availableIn(SelectionMode.VERTEX))
        assertFalse(individual.copy(enabled = false).availableIn(SelectionMode.FACE))
    }

    @Test fun regionAndCursorAreAvailableInAllSelectionModes() {
        val region = EditToolbarVariant("REGION", "Región", requirements =
            mapOf("selection_modes" to listOf("VERTEX", "EDGE", "FACE")))
        val cursor = EditToolbarVariant("CURSOR", "A toque")
        for (mode in SelectionMode.entries) {
            assertTrue(region.availableIn(mode))
            assertTrue(cursor.availableIn(mode))
        }
    }
}
