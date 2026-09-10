package com.blendertablet.remote.ui

import com.blendertablet.remote.model.*
import org.junit.Assert.*
import org.junit.Test

class CadFeedbackTest {
    private val sketch = CadSketch("s","Boceto","XY",listOf(CadEntity("line","LINE",emptyMap()),CadEntity("rect","RECTANGLE",emptyMap())),emptyList())
    private fun state(vararg refs: CadSelection) = CadState(activeSketchId="s",sketches=listOf(sketch),selection=refs.toList())
    @Test fun midpointWorksWithOriginAndLineInEitherOrder() {
        val origin=CadSelection("ORIGIN","POINT"); val line=CadSelection("line","BODY")
        assertTrue(cadConstraintEnabled(state(origin,line),"MIDPOINT"))
        assertTrue(cadConstraintEnabled(state(line,origin),"MIDPOINT"))
        assertFalse(cadConstraintEnabled(state(line),"MIDPOINT"))
        assertFalse(cadConstraintEnabled(state(origin),"FIX"))
        assertTrue(cadConstraintEnabled(state(CadSelection("line","START"),CadSelection("rect","P0")),"FIX"))
    }
    @Test fun contextualPanelIncludesOnlyAssociatedPointsOrEdges() {
        assertTrue(cadRefsTouch(CadSelection("rect","P0"),CadSelection("rect","EDGE0")))
        assertTrue(cadRefsTouch(CadSelection("rect","P0"),CadSelection("rect","EDGE3")))
        assertFalse(cadRefsTouch(CadSelection("rect","P0"),CadSelection("rect","EDGE1")))
        assertFalse(cadRefsTouch(CadSelection("rect","P0"),CadSelection("rect","P1")))
        assertFalse(cadRefsTouch(CadSelection("line","START"),CadSelection("rect","BODY")))
        assertTrue(cadRefsTouch(CadSelection("line","START"),CadSelection("line","BODY")))
    }
}
