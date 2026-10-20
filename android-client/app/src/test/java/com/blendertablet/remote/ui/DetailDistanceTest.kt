package com.blendertablet.remote.ui

import org.junit.Assert.assertEquals
import org.junit.Test

class DetailDistanceTest {
    @Test fun everyShownNumberIsRoundedToTwoDecimalsAtMost() {
        for ((value, expected) in listOf(.02 to "0.02", .0012 to "0", -.00001 to "0", 0.0 to "0",
            1.23456 to "1.23", 2.005 to "2.01", -3.14159 to "-3.14", 10.0 to "10", 0.1 + 0.2 to "0.3")) {
            assertEquals(expected, formatToolDistance(value, null))
            assertEquals(expected, formatToolDistance(value, 6))
        }
        assertEquals("1.2", formatToolDistance(1.23, 1))
    }
}
