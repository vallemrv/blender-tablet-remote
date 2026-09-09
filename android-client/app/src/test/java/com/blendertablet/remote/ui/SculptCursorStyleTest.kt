package com.blendertablet.remote.ui

import org.junit.Assert.assertEquals
import org.junit.Test

class SculptCursorStyleTest {
    @Test fun smoothWinsEveryCombination() {
        for (invert in listOf(false, true)) for (mask in listOf(false, true)) {
            assertEquals(0xff66b8ff.toInt(), SculptCursorStyle(true, invert, mask).color())
            assertEquals(0xff66b8ff.toInt(), SculptCursorStyle(false, invert, mask).color(penSmooth = true))
        }
    }

    @Test fun normalMaskAndInvertedMaskHaveDistinctColors() {
        assertEquals(0xffffffff.toInt(), SculptCursorStyle().color())
        assertEquals(0xffd49bff.toInt(), SculptCursorStyle(mask = true).color())
        assertEquals(0xffffad55.toInt(), SculptCursorStyle(invert = true, mask = true).color())
        assertEquals(0xffffad55.toInt(), SculptCursorStyle(mask = true).color(penInvert = true))
        assertEquals(0xff66b8ff.toInt(), SculptCursorStyle(smooth = true).color(penInvert = true))
    }
}
