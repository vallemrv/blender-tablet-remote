package com.blendertablet.remote.network

import com.blendertablet.remote.model.EditTool
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ExtrudeCursorStateTest {
    @Test fun extrudeSessionIdentityChangesEvenWhenVariantAndValueMatch() {
        fun session(id: String) = StateParser.toolSession(JSONObject("""{
            "active":true,"armed":true,"tool":"EXTRUDE","session_id":"$id",
            "parameters":{"variant":"REGION","offset":0}
        }"""))
        assertEquals("first",session("first").sessionId)
        assertNotEquals(session("first"),session("second"))
    }

    @Test fun armedCursorToolKeepsItsInputAndControlsWithoutParametricDragging() {
        val state = StateParser.toolSession(JSONObject("""{
            "active":false,"armed":true,"tool":"EXTRUDE","input":"REPEAT_TAP",
            "parameters":{"variant":"CURSOR","rotate_source":false},
            "controls":[{"id":"rotate_source","label":"Girar origen","type":"bool","default":true}],
            "instruction":"Toca para extruir","can_confirm":false
        }"""))
        assertTrue(state.armed)
        assertFalse(state.active)
        assertEquals(EditTool.EXTRUDE, state.tool)
        assertEquals("REPEAT_TAP", state.input)
        assertFalse(state.acceptsViewportNudge)
        assertFalse(state.canConfirm)
        assertFalse(state.flag("rotate_source", true))
        assertEquals("bool", state.controls.single().type)
        assertTrue(state.availableSnapTypes.isEmpty())
    }
}
