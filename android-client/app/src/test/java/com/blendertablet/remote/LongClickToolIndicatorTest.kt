package com.blendertablet.remote

import com.blendertablet.remote.model.EditToolbarFamily
import com.blendertablet.remote.model.EditToolbarVariant
import com.blendertablet.remote.ui.hasLongClickMenu
import com.blendertablet.remote.ui.displayedVariantOf
import com.blendertablet.remote.ui.hasDuplicateLongClickMenu
import org.junit.Assert.assertEquals
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

    @Test fun `la familia enseña la variante recordada aunque no haya sesión`() {
        val variants = listOf(
            EditToolbarVariant("KNIFE", "Cuchillo"),
            EditToolbarVariant("BISECT", "Bisect"),
        )
        val family = EditToolbarFamily(
            id = "CUT", label = "Cut", defaultVariant = "KNIFE",
            command = "tool.begin", variants = variants,
        )

        assertEquals("BISECT", displayedVariantOf(family, active = null, rememberedId = "BISECT")?.id)
        assertEquals("KNIFE", displayedVariantOf(family, active = null, rememberedId = null)?.id)
    }

    @Test fun `duplicar anuncia long click solo cuando existe la variante enlazada`() {
        assertTrue(hasDuplicateLongClickMenu(inEdit = false))
        assertFalse(hasDuplicateLongClickMenu(inEdit = true))
    }

    private fun family(variants: List<EditToolbarVariant>) = EditToolbarFamily(
        id = "EXTRUDE",
        label = "Extrude",
        defaultVariant = variants.first().id,
        command = "tool.begin",
        variants = variants,
    )
}
