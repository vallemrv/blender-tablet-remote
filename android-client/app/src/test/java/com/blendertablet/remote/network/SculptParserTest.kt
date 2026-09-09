package com.blendertablet.remote.network

import com.blendertablet.remote.model.BlenderMode
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class SculptParserTest {
    @Test fun nativeSculptSnapshotKeepsItsModeAndPressureSettings() {
        val state = StateParser.state(JSONObject("""{
            "mode":"SCULPT", "active_object":"Head",
            "sculpt":{"available":true,"active":true,"brush":"CLAY","radius":0.08,
              "strength":0.65,"pressure_strength":true,"pressure_size":true,
              "symmetry":{"x":false,"y":true,"z":false},
              "dyntopo":{"enabled":false,"detail":8},
              "multires":{"name":"Multires","level":2,"total_levels":3},
              "brushes":[{"id":"CLAY","label":"Arcilla","icon":"CLAY"}]}
        }"""))
        assertEquals(BlenderMode.SCULPT, state.mode)
        assertTrue(state.sculpt.available)
        assertTrue(state.sculpt.pressureSize)
        assertFalse(state.sculpt.symmetryX)
        assertTrue(state.sculpt.symmetryY)
        assertEquals(2, state.sculpt.multiresLevel)
        assertEquals(3, state.sculpt.multiresTotalLevels)
        assertEquals("Arcilla", state.sculpt.brushes.single().label)
    }
    @Test fun oldBackendDoesNotAdvertiseSculptAndUnknownModeStaysSafe() {
        val state = StateParser.state(JSONObject("""{"mode":"OBJECT"}"""))
        assertFalse(state.sculpt.available)
        assertTrue(state.sculpt.brushes.isEmpty())
        assertEquals(BlenderMode.EDIT, StateParser.state(JSONObject("""{"mode":"EDIT_MESH"}""")).mode)
    }
    @Test fun nullMultiresNameIsAbsentAndZeroStrengthIsExact() {
        val sculpt = SculptParser.state(JSONObject("""{"strength":0,"multires":{"name":null}}"""))
        assertNull(sculpt.multiresName)
        assertEquals(0f, sculpt.strength)
    }
}
