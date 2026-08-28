package com.blendertablet.remote

import com.blendertablet.remote.model.EditToolbarFamily
import com.blendertablet.remote.model.EditToolbarVariant
import com.blendertablet.remote.ui.hasLongClickMenu
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LongClickToolIndicatorTest {
    @Test fun `solo hay señal con varias variantes habilitadas`() {
        val single = family(listOf(EditToolbarVariant("REGION", "Región")))
        val multiple = family(listOf(
            EditToolbarVariant("REGION", "Región"),
            EditToolbarVariant("INDIVIDUAL", "Individual"),
        ))
        val disabledSecond = family(listOf(
            EditToolbarVariant("REGION", "Región"),
            EditToolbarVariant("INDIVIDUAL", "Individual", enabled = false),
        ))

        assertFalse(hasLongClickMenu(single))
        assertTrue(hasLongClickMenu(multiple))
        assertFalse(hasLongClickMenu(disabledSecond))
    }

    private fun family(variants: List<EditToolbarVariant>) = EditToolbarFamily(
        id = "EXTRUDE",
        label = "Extrude",
        defaultVariant = variants.first().id,
        command = "tool.begin",
        variants = variants,
    )
}
