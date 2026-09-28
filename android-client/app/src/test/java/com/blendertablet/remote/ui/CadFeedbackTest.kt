package com.blendertablet.remote.ui

import com.blendertablet.remote.model.*
import org.junit.Assert.*
import org.junit.Test

class CadFeedbackTest {
    @Test fun equalityAcceptsSeveralDifferentCirclesAndDistanceAxesUsePoints() {
        val circles = (1..3).map { CadEntity("c$it", "CIRCLE", emptyMap()) }
        val cad = CadState(activeSketchId = "s", sketches = listOf(CadSketch("s", "Boceto", "XY", circles, emptyList())),
            selection = circles.map { CadSelection(it.id, "CENTER") })
        assertTrue(cadConstraintEnabled(cad, "EQUAL"))
        assertFalse(cadConstraintEnabled(cad.copy(selection = listOf(CadSelection("c1", "CENTER"), CadSelection("c1", "RIM"))), "EQUAL"))
        val points = cad.copy(selection = listOf(CadSelection("ORIGIN", "POINT"), CadSelection("c1", "CENTER")))
        assertTrue(cadConstraintEnabled(points, "DISTANCE_X"))
        assertTrue(cadConstraintEnabled(points, "DISTANCE_Y"))
        assertFalse(cadConstraintEnabled(cad, "DISTANCE_X"))
    }
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
    @Test fun collinearRequiresTwoDifferentLinesOrSides() {
        val line = CadSelection("line", "BODY")
        val side = CadSelection("rect", "EDGE0")
        assertTrue(cadConstraintEnabled(state(line, side), "COLLINEAR"))
        assertTrue(cadConstraintEnabled(state(side, line), "COLLINEAR"))
        assertFalse(cadConstraintEnabled(state(line), "COLLINEAR"))
        assertFalse(cadConstraintEnabled(state(line, line), "COLLINEAR"))
        assertFalse(cadConstraintEnabled(state(line, CadSelection("rect", "P0")), "COLLINEAR"))
        assertFalse(cadConstraintEnabled(state(line, CadSelection("rect", "BODY")), "COLLINEAR"))
    }
    @Test fun polygonSidesAllowHorizontalAndVerticalButWholePolygonDoesNot() {
        val polygon = CadEntity("polygon", "NGON", mapOf("sides" to 6.0))
        val cad = CadState(activeSketchId = "s", sketches = listOf(
            CadSketch("s", "Boceto", "XY", sketch.entities + polygon, emptyList())))
        for (type in listOf("HORIZONTAL", "VERTICAL")) {
            assertTrue(cadConstraintEnabled(cad.copy(selection = listOf(CadSelection("line", "BODY"))), type))
            assertTrue(cadConstraintEnabled(cad.copy(selection = listOf(CadSelection("polygon", "EDGE4"))), type))
            assertFalse(cadConstraintEnabled(cad.copy(selection = listOf(CadSelection("polygon", "P4"))), type))
            assertFalse(cadConstraintEnabled(cad.copy(selection = listOf(CadSelection("polygon", "BODY"))), type))
        }
    }
    @Test fun contextualPanelIncludesOnlyAssociatedPointsOrEdges() {
        assertTrue(cadRefsTouch(CadSelection("rect","P0"),CadSelection("rect","EDGE0")))
        assertTrue(cadRefsTouch(CadSelection("rect","P0"),CadSelection("rect","EDGE3")))
        assertFalse(cadRefsTouch(CadSelection("rect","P0"),CadSelection("rect","EDGE1")))
        assertFalse(cadRefsTouch(CadSelection("rect","P0"),CadSelection("rect","P1")))
        assertFalse(cadRefsTouch(CadSelection("line","START"),CadSelection("rect","BODY")))
        assertTrue(cadRefsTouch(CadSelection("line","START"),CadSelection("line","BODY")))
    }
    @Test fun weldRequiresDistinctEndpointsRatherThanWholeEntities() {
        assertTrue(cadWeldEnabled(state(CadSelection("line","END"),CadSelection("rect","P0"))))
        assertTrue(cadWeldEnabled(state(CadSelection("ORIGIN","POINT"),CadSelection("line","START"))))
        assertFalse(cadWeldEnabled(state(CadSelection("line","BODY"),CadSelection("rect","BODY"))))
        assertFalse(cadWeldEnabled(state(CadSelection("line","START"),CadSelection("line","START"))))
    }
}
