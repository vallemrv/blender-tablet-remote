package com.blendertablet.remote.model

import org.junit.Assert.*
import org.junit.Test

class TweakControlsTest {
    @Test fun tweakHelpersStayVisibleBeforeDuringAndAfterDragWithoutSelectingMove() {
        for (dragActive in listOf(false, true, false)) {
            val session = TransformSession(active = dragActive, mode = TransformMode.MOVE)
            assertTrue(bottomTrayVisible(dragActive, false, ActiveTool.TWEAK, false))
            for (mode in TransformMode.entries) {
                assertFalse(isTransformToolSelected(ActiveTool.TWEAK, session, mode))
            }
        }
    }

    @Test fun leavingTweakRestoresOrdinarySelectionAndTransformRailStates() {
        assertFalse(bottomTrayVisible(false, false, ActiveTool.SELECT, false))
        for (mode in TransformMode.entries) {
            val session = TransformSession(active = true, mode = mode)
            assertTrue(bottomTrayVisible(true, false, ActiveTool.SELECT, false))
            for (button in TransformMode.entries) {
                assertEquals(button == mode, isTransformToolSelected(ActiveTool.SELECT, session, button))
            }
        }
    }

}
