package com.blendertablet.remote.model

import org.junit.Assert.*
import org.junit.Test

class TransformCenterTest {
    @Test fun cursorAndObjectOriginRememberTheIntentionInsteadOfOldCoordinates() {
        for (preset in listOf("CURSOR", "OBJECT_ORIGIN", "SELECTION", "INDIVIDUAL")) {
            val saved = TransformCenter.from(TransformSession(active = true, mode = TransformMode.ROTATE,
                centerMode = preset, center = listOf(1f,2f,3f)), "scene-a")!!
            assertEquals(preset, saved.mode)
            assertTrue(saved.point.isEmpty())
            assertEquals(saved, saved.forScene("scene-b"))
        }
    }
    @Test fun pickedPointStaysStationaryButNeverLeaksIntoAnotherScene() {
        val saved = TransformCenter.from(TransformSession(active = true, mode = TransformMode.SCALE,
            centerMode = "PICKED", centerLocked = true, center = listOf(1f,2f,3f)), "scene-a")!!
        assertEquals(listOf(1.0,2.0,3.0), saved.forScene("scene-a").point)
        assertEquals("SELECTION", saved.forScene("scene-b").mode)
        assertEquals("SELECTION", saved.forScene("").mode)
    }
    @Test fun movingClosingOrHoveringCannotReplaceTheChosenPivot() {
        assertNull(TransformCenter.from(TransformSession(), "scene"))
        assertNull(TransformCenter.from(TransformSession(active = true, mode = TransformMode.MOVE), "scene"))
        assertNull(TransformCenter.from(TransformSession(active = true, mode = TransformMode.ROTATE,
            centerMode = "PICKED", centerLocked = false, center = listOf(1f,2f,3f)), "scene"))
    }
}
