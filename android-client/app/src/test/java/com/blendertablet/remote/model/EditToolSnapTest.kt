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

    @Test fun freeDragKeepsSubstepPrecisionAtOneMillimeterScale() {
        for (tool in listOf(EditTool.EXTRUDE, EditTool.INSET, EditTool.BEVEL)) {
            for (scale in listOf(.001,1.0,10.0)) {
                val session = ToolSession(active = true, tool = tool, snapType = SnapType.NONE, snapStep = .00001 / scale)
                assertEquals(.000005, session.viewportNudge(-.02)*scale, 1e-12)
                assertEquals(.00001, (1..8).sumOf {session.viewportNudge(-.005)}*scale, 1e-12)
            }
        }
    }
}
