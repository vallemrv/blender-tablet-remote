package com.blendertablet.remote.network

import com.blendertablet.remote.model.BlenderMode
import com.blendertablet.remote.model.TransformMode
import com.blendertablet.remote.model.TransformSession
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class TransformStepsStateTest {
    @Test fun newStepReplacesSessionButLateUpdatesCannotRestorePreviousStep() {
        for (mode in TransformMode.entries) {
            val previous = TransformSession(active = true, sessionId = "step-1", mode = mode)
            val next = previous.copy(sessionId = "step-2")
            assertTrue(shouldAcceptTransformSession(previous, next, allowReplace = true))
            assertFalse(shouldAcceptTransformSession(next, previous))
            assertTrue(shouldAcceptTransformSession(next, next))
        }
    }

    @Test fun stepResponseKeepsSceneSeparateFromTransformMode() {
        val response = JSONObject("""{
            "active":true, "session_id":"step-2", "mode":"MOVE", "values":[0,0,0],
            "selection_changed":true,
            "state":{"mode":"EDIT","active_object":"Cube","selection_mode":"VERTEX"}
        }""")
        assertEquals(TransformMode.MOVE, StateParser.session(response).mode)
        assertEquals("step-2", StateParser.session(response).sessionId)
        assertEquals(BlenderMode.EDIT, StateParser.state(response.getJSONObject("state")).mode)
        assertTrue(StateParser.features(JSONObject("""{
            "features":{"transform_modal":{"version":4,"edit_step_selection":true}}
        }""")).transformStepSelection)
        assertFalse(StateParser.features(JSONObject("""{"features":{}}""")).transformStepSelection)
    }
}
