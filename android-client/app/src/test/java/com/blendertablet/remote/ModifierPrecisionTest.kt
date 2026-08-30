package com.blendertablet.remote

import com.blendertablet.remote.ui.formatModifierValue
import com.blendertablet.remote.ui.stepModifierScalar
import com.blendertablet.remote.model.ModifierDefault
import com.blendertablet.remote.model.ModifierParameterDescriptor
import org.junit.Assert.assertEquals
import org.junit.Test

class ModifierPrecisionTest {
    @Test fun `el umbral de Mirror conserva milesimas visibles`() {
        assertEquals("0.001", formatModifierValue(0.001, isInt = false, step = 0.001))
        assertEquals("0.002", formatModifierValue(0.002, isInt = false, step = 0.001))
        assertEquals("0", formatModifierValue(0.0, isInt = false, step = 0.001))
    }

    @Test fun `cada descriptor conserva la precision de su paso`() {
        assertEquals("0.05", formatModifierValue(0.05, isInt = false, step = 0.05))
        assertEquals("2", formatModifierValue(2.0, isInt = true, step = 1.0))
    }

    @Test fun `el stepper de Mirror avanza una milesima`() {
        val spec = ModifierParameterDescriptor(
            name = "merge_threshold",
            type = "float",
            default = ModifierDefault.Decimal(0.001),
            min = 0.0,
            max = 1.0,
            step = 0.001,
        )
        val next = stepModifierScalar(0.001, isInt = false, delta = spec.step!!, spec = spec)
        assertEquals(0.002, next.toDouble(), 1e-12)
        assertEquals("0.002", formatModifierValue(next.toDouble(), isInt = false, step = spec.step))
    }
}
