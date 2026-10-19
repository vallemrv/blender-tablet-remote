package com.blendertablet.remote.ui

import org.junit.Assert.*
import org.junit.Test

class ReferencePanelPositionTest {
    @Test fun boardCanReachAllFourCornersWithoutRailMargins() {
        assertEquals(0f to 0f, referencePanelPosition(-500f,-500f,1200f,800f,310f,400f))
        assertEquals(890f to 400f, referencePanelPosition(2000f,2000f,1200f,800f,310f,400f))
        assertEquals(890f to 0f, referencePanelPosition(890f,0f,1200f,800f,310f,400f))
        assertEquals(0f to 400f, referencePanelPosition(0f,400f,1200f,800f,310f,400f))
    }
    @Test fun enlargingOrRotatingScreenKeepsHeaderReachable() {
        assertEquals(340f to 140f, referencePanelPosition(890f,400f,800f,700f,460f,560f))
        assertEquals(0f to 0f, referencePanelPosition(500f,400f,300f,200f,460f,560f))
    }
}
