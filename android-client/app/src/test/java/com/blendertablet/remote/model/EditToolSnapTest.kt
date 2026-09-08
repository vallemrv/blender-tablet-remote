package com.blendertablet.remote.model

import org.junit.Assert.*
import org.junit.Test

class EditToolSnapTest {
    @Test fun sameFingerDistanceAdvancesOneStepForEveryMetricToolAndSceneScale() {
        for (tool in listOf(EditTool.EXTRUDE, EditTool.INSET, EditTool.BEVEL)) {
            for (step in listOf(.001, .01, 1.0, 10.0)) {
                val session = ToolSession(active = true, tool = tool, snapType = SnapType.INCREMENT, snapStep = step)
                assertEquals(step, session.viewportNudge(-.04), 1e-9)
                assertEquals(-step, session.viewportNudge(.04), 1e-9)
                assertEquals(step, (1..8).sumOf { session.viewportNudge(-.005) }, 1e-9)
            }
        }
    }

    @Test fun freeDragDoesNotDependOnTheSavedSnapStep() {
        for (tool in listOf(EditTool.EXTRUDE, EditTool.INSET, EditTool.BEVEL)) {
            val session = ToolSession(active = true, tool = tool, snapType = SnapType.NONE, snapStep = 10.0)
            assertEquals(.04, session.viewportNudge(-.04), 1e-9)
        }
    }
}
