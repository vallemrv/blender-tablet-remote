package com.blendertablet.remote.ui

import com.blendertablet.remote.model.*
import org.junit.Assert.*
import org.junit.Test

class CadFeedbackTest {
    @Test fun planeAxesNameTheBackendFrameInWorldTerms() {
        // base_frame: XY normal +Z, XZ normal −Y, YZ normal +X; local x/y map to these world axes.
        assertEquals(listOf("X", "Y"), cadPlaneAxes("XY").inPlane)
        assertEquals(listOf("X", "Z"), cadPlaneAxes("XZ").inPlane)
        assertTrue(cadPlaneAxes("XZ").positive.contains("−Y"))
        assertEquals(listOf("Y", "Z"), cadPlaneAxes("YZ").inPlane)
        assertTrue(cadPlaneAxes("YZ").positive.contains("+X"))
        assertEquals(listOf("U", "V"), cadPlaneAxes(null).inPlane)
        assertEquals("Frontal (XZ)", cadPlaneLabel("XZ"))
    }

    @Test fun horizontalAndVerticalAcceptSeveralStraightEdges() {
        val lines = (1..6).map { CadEntity("line$it", "LINE", emptyMap()) }
        val rectangle = CadEntity("rect", "RECTANGLE", emptyMap())
        val polygon = CadEntity("ngon", "NGON", mapOf("sides" to 6.0))
        val circle = CadEntity("circle", "CIRCLE", emptyMap())
        val cad = CadState(activeSketchId = "s", sketches = listOf(CadSketch("s", "Boceto", "XY",
            lines + listOf(rectangle, polygon, circle), emptyList())))
        for (type in listOf("HORIZONTAL", "VERTICAL")) {
            for (count in 1..6) assertTrue(cadConstraintEnabled(cad.copy(selection =
                lines.take(count).map { CadSelection(it.id, "BODY") }), type))
            val sides = listOf(CadSelection("rect", "EDGE0"), CadSelection("rect", "EDGE2"),
                CadSelection("ngon", "EDGE0"), CadSelection("ngon", "EDGE3"))
            assertTrue(cadConstraintEnabled(cad.copy(selection = sides), type))
            assertFalse(cadConstraintEnabled(cad, type))
            assertFalse(cadConstraintEnabled(cad.copy(selection = sides + CadSelection("circle", "BODY")), type))
            assertFalse(cadConstraintEnabled(cad.copy(selection = sides + CadSelection("line1", "END")), type))
        }
    }

    @Test fun sketchDimensionsDisappearOnExitAndCannotBelongToAnotherSketch() {
        val circle = CadEntity("circle", "CIRCLE", mapOf("radius" to .015))
        val sketch = CadSketch("s", "Boceto", "XY", listOf(circle), emptyList())
        val other = CadSketch("other", "Otro", "XY", emptyList(), emptyList())
        val editing = CadState(activeSketchId = "s", sketches = listOf(sketch, other),
            selectionKind = "ENTITY", selectionId = "circle")
        assertEquals(circle, editing.selectedEntity)
        assertNull(editing.copy(activeSketchId = null).selectedEntity)
        assertNull(editing.copy(activeSketchId = "other").selectedEntity)
        assertNull(editing.copy(activeSketchId = null, selectionKind = "PROFILE",
            selectionId = "profile_circle").selectedEntity)
        assertEquals(circle, editing.copy(activeSketchId = "s").selectedEntity)
    }

    @Test fun pointOnLineRequiresOnePointAndAnotherStraightReferenceInEitherOrder() {
        val entities = listOf(CadEntity("a", "LINE", emptyMap()), CadEntity("b", "LINE", emptyMap()),
            CadEntity("c", "CIRCLE", emptyMap()), CadEntity("n", "NGON", mapOf("sides" to 8.0)),
            CadEntity("slot", "SLOT", emptyMap()))
        val base = CadState(activeSketchId = "s", sketches = listOf(CadSketch("s", "Boceto", "XY", entities, emptyList())))
        fun enabled(vararg refs: CadSelection) = cadConstraintEnabled(base.copy(selection = refs.toList()), "POINT_ON_LINE")
        val endpoint = CadSelection("a", "END"); val line = CadSelection("b", "BODY")
        assertTrue(enabled(endpoint, line)); assertTrue(enabled(line, endpoint))
        assertTrue(enabled(CadSelection("c", "CENTER"), line))
        assertTrue(enabled(CadSelection("ORIGIN", "POINT"), line))
        assertTrue(enabled(CadSelection("n", "P7"), line))
        assertTrue(enabled(endpoint, CadSelection("n", "EDGE7")))
        assertTrue(enabled(endpoint, CadSelection("slot", "AXIS")))
        assertFalse(enabled(endpoint)); assertFalse(enabled(endpoint, CadSelection("a", "BODY")))
        assertFalse(enabled(endpoint, CadSelection("b", "END")))
        assertFalse(enabled(CadSelection("a", "BODY"), line))
        assertFalse(enabled(endpoint, CadSelection("c", "BODY")))
        assertFalse(enabled(endpoint, CadSelection("n", "EDGE8")))
        assertFalse(enabled(CadSelection("n", "P8"), line))
        assertTrue(cadConstraintGroups(listOf("COINCIDENT", "POINT_ON_LINE", "MIDPOINT")).single().contains("POINT_ON_LINE"))
    }

    @Test fun slotRadiusAndWidthUseTheSameDimension() {
        val measure = CadMeasure("radius", "Radio extremos", "RADIUS", 1.0,
            listOf(CadSelection("slot", "BODY")), listOf("r"))
        val slot = CadEntity("slot", "SLOT", mapOf("radius" to .015, "width" to .030), dimensions = listOf(measure))
        assertEquals("radius", cadDisplayMeasures(slot, false).single().field)
        val width = cadDisplayMeasures(slot, true).single()
        assertEquals("width", width.field)
        assertEquals(.015, slot.values[width.field]!! * width.valueFactor, 1e-12)
        assertEquals(measure.constraintIds, width.constraintIds)
        val cad = CadState(activeSketchId = "s", sketches = listOf(CadSketch("s", "Boceto", "XY", listOf(slot), emptyList())),
            selection = listOf(CadSelection("slot", "BODY")))
        assertTrue(cadConstraintEnabled(cad, "RADIUS"))
    }

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
