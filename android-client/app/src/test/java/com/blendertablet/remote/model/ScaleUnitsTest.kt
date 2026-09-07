package com.blendertablet.remote.model

import org.junit.Assert.*
import org.junit.Test

class ScaleUnitsTest {
    @Test fun oneMillimeterButtonAndTypedDimensionAgreeAtBothSceneScales() {
        for (sceneScale in listOf(1.0, 0.001)) {
            val baseX = 0.020 / sceneScale
            val step = scaleAxisStep(1.0, TransformStepUnit.MM, sceneScale, baseX)
            assertEquals(0.05, step, 1e-9)
            val typed = ValueParser.parseScaleDimension("21", TransformStepUnit.MM, sceneScale, baseX)!!
            assertEquals(typed, 1.0 + step, 1e-9)
            assertEquals(21.0, baseX * (1.0 + step) * sceneScale * 1000.0, 1e-9)
        }
    }

    @Test fun everyLengthUnitUsesTheSamePhysicalStepForWireAndAxisButtons() {
        val oneMillimeter = listOf(TransformStepUnit.MM to 1.0, TransformStepUnit.CM to 0.1, TransformStepUnit.M to 0.001)
        for ((unit, value) in oneMillimeter) {
            assertEquals("LENGTH", unit.scaleStepWireUnit)
            for (sceneScale in listOf(1.0, 0.001, 0.01)) {
                assertEquals(0.001 / sceneScale, scaleStepForWire(value, unit, sceneScale), 1e-9)
                assertEquals(0.05, scaleAxisStep(value, unit, sceneScale, 0.020 / sceneScale), 1e-9)
            }
        }
    }

    @Test fun eachAxisButtonAddsOneMillimeterAndLinkPreservesBaselineProportions() {
        val baseline = listOf(0.020, 0.037, 0.010)
        for (axis in 0..2) {
            val factor = 1.0 + scaleAxisStep(1.0, TransformStepUnit.MM, 1.0, baseline[axis])
            val independent = scaleValuesAfterAxisEdit(listOf(1.0, 1.0, 1.0), axis, factor, false)
            for (i in 0..2) {
                assertEquals(baseline[i] + if (i == axis) 0.001 else 0.0, baseline[i] * independent[i], 1e-9)
            }
            val linked = scaleValuesAfterAxisEdit(listOf(1.0, 1.0, 1.0), axis, factor, true)
            assertEquals((baseline[axis] + 0.001) / baseline[axis], linked[0], 1e-9)
            assertEquals(linked[0], linked[1], 1e-9)
            assertEquals(linked[1], linked[2], 1e-9)
        }
    }

    @Test fun percentStepIsIndependentOfSceneScaleAndDimension() {
        assertEquals("FACTOR", TransformStepUnit.PERCENT.scaleStepWireUnit)
        assertEquals(0.07, scaleStepForWire(7.0, TransformStepUnit.PERCENT, 0.001), 1e-9)
        assertEquals(0.07, scaleAxisStep(7.0, TransformStepUnit.PERCENT, 0.001, 0.0), 1e-9)
        assertEquals(1.07, ValueParser.parseScaleDimension("107 %", TransformStepUnit.PERCENT, 0.001, 0.0)!!, 1e-9)
    }

    @Test fun flatAxisCannotGainThicknessByScaling() {
        assertEquals(0.0, scaleAxisStep(1.0, TransformStepUnit.MM, 1.0, 0.0), 0.0)
        assertNull(ValueParser.parseScaleDimension("1", TransformStepUnit.MM, 1.0, 0.0))
    }
}
