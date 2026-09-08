package com.blendertablet.remote.model

import org.junit.Assert.*
import org.junit.Test

class ProportionalRadiusTest {
    @Test fun oneInMillimetersMeansOneMillimeterAcrossSceneScales() {
        for (scale in listOf(.001, .01, 1.0)) {
            assertEquals(.001, ProportionalRadius.parse("1", LengthUnit.MILLIMETERS, scale)!! * scale, 1e-12)
            assertEquals(.01, ProportionalRadius.parse("1", LengthUnit.CENTIMETERS, scale)!! * scale, 1e-12)
            assertEquals(.01, ProportionalRadius.parse("10mm", LengthUnit.CENTIMETERS, scale)!! * scale, 1e-12)
        }
    }

    @Test fun presetButtonsAdvanceOnePhysicalStepAndAccumulate() {
        for (scale in listOf(.001, 1.0)) {
            var radius = .01 / scale
            repeat(5) { radius = ProportionalRadius.step(radius, 1, .001, scale) }
            assertEquals(.015, radius * scale, 1e-12)
            repeat(5) { radius = ProportionalRadius.step(radius, -1, .001, scale) }
            assertEquals(.01, radius * scale, 1e-12)
            repeat(20) { radius = ProportionalRadius.step(radius, -1, .001, scale) }
            assertTrue(radius > 0)
        }
    }

    @Test fun invalidDraftsDoNotBecomeRadiusValues() {
        for (input in listOf("", "-1", "0", "NaN", "Infinity", "abc")) {
            assertNull(ProportionalRadius.parse(input, LengthUnit.MILLIMETERS, .001))
        }
    }
}
