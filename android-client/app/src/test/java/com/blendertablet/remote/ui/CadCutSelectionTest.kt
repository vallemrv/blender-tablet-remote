package com.blendertablet.remote.ui

import com.blendertablet.remote.model.*
import com.blendertablet.remote.network.CadParser
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class CadCutSelectionTest {
    private val sketch = CadSketch("s", "Boceto", "XY",
        (1..4).map { CadEntity("hole$it", "CIRCLE", emptyMap()) } + listOf(
            CadEntity("center", "CIRCLE", emptyMap()), CadEntity("inner", "CIRCLE", emptyMap()),
            CadEntity("construction", "LINE", emptyMap(), construction = true), CadEntity("p", "POINT", emptyMap())), emptyList())
    private fun state(vararg selection: CadSelection) = CadState(sketches = listOf(sketch), activeSketchId = "s",
        selectionKind = "ENTITY", selection = selection.toList())

    @Test fun fourSelectedHolesExcludeTheTwoCenterCircles() {
        val ids = (1..4).map { "hole$it" }
        assertEquals(ids, cadCutSelection(state(*ids.map { CadSelection(it) }.toTypedArray())))
    }
    @Test fun centerAndRimOfOneCircleSelectOneFullFigure() {
        assertEquals(listOf("hole1"), cadCutSelection(state(CadSelection("hole1", "CENTER"), CadSelection("hole1", "RIM"))))
    }
    @Test fun emptyOrInvalidSelectionNeverMeansTheWholeSketch() {
        for (ids in listOf(emptyList(), listOf("ORIGIN"), listOf("hole1", "missing"), listOf("construction"), listOf("p"))) {
            assertTrue(cadCutSelection(state(*ids.map { CadSelection(it) }.toTypedArray())).isEmpty())
        }
        assertTrue(cadCutSelection(state(CadSelection("hole1")).copy(activeSketchId = null)).isEmpty())
        assertTrue(cadCutSelection(state(CadSelection("hole1")).copy(surface = CadSurface(mode = "EDGE"))).isEmpty())
    }
    @Test fun olderServersDoNotOfferSubsetCuts() {
        val flags = JSONObject().put("version", 2).put("length_unit", "METERS").put("planes", org.json.JSONArray(listOf("XY")))
        assertFalse(CadParser.capabilities(flags).selectedCut)
        flags.put("selected_cut", true)
        assertTrue(CadParser.capabilities(flags).selectedCut)
    }
}
