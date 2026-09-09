package com.blendertablet.remote.ui

import org.junit.Assert.assertEquals
import org.junit.Test

class DetailDistanceTest {
    @Test fun submillimeterStepsNeverDisappearAsZero() {
        for ((value, expected) in listOf(.02 to "0.02", .0012 to "0.0012", -.00001 to "-0.00001", 0.0 to "0")) {
            assertEquals(expected, formatToolDistance(value, detailDecimalPlaces(value, 2)))
        }
    }
}
