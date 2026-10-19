package com.blendertablet.remote.ui

import com.blendertablet.remote.model.*
import org.junit.Assert.*
import org.junit.Test

class PaintNavigationTest {
    @Test fun paintSelectionKeepsOrbitAvailableWithoutTransformOrToolSession() {
        assertTrue(navigationOrbitVisible(false,false,ActiveTool.SELECT,ShapeTool.PAINT))
        assertFalse(navigationOrbitVisible(false,false,ActiveTool.SELECT,ShapeTool.NONE))
        assertFalse(navigationOrbitVisible(false,false,ActiveTool.SELECT,ShapeTool.BOX))
        assertTrue(navigationOrbitVisible(true,false,ActiveTool.MOVE))
        assertFalse(navigationOrbitVisible(true,false,ActiveTool.TWEAK))
    }
}
