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
    @Test fun shownProfilesStayOutsideSketchEditingAndExcludeUnselectedCircles() {
        val shown = sketch.copy(profiles = (1..4).map { CadProfile("profile_hole$it", "hole$it", "Círculo") } +
            listOf(CadProfile("profile_center", "center", "Círculo"), CadProfile("profile_inner", "inner", "Círculo")))
        val ids = (1..4).map { "profile_hole$it" }
        val state = CadState(sketches = listOf(shown), selectionKind = "PROFILE", selectionId = ids.last(),
            selection = ids.map { CadSelection(it) })
        assertNull(state.activeSketchId)
        assertEquals(ids, cadShownProfiles(state))
        assertTrue(cadShownProfiles(state.copy(activeSketchId = "s")).isEmpty())
        assertTrue(cadShownProfiles(state.copy(selection = state.selection + CadSelection("profile_other"))).isEmpty())
        assertTrue(cadShownProfiles(state.copy(selectionKind = "SKETCH")).isEmpty())
    }
    @Test fun olderServersDoNotOfferSubsetCuts() {
        val flags = JSONObject().put("version", 2).put("length_unit", "METERS").put("planes", org.json.JSONArray(listOf("XY")))
        assertFalse(CadParser.capabilities(flags).selectedCut)
        assertFalse(CadParser.capabilities(flags).profileMultiselect)
        flags.put("selected_cut", true)
        assertTrue(CadParser.capabilities(flags).selectedCut)
        flags.put("profile_multiselect", true)
        assertTrue(CadParser.capabilities(flags).profileMultiselect)
    }
}
