package com.blendertablet.remote.network

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class LoopCutStateTest {
    @Test fun physicalSlideSurvivesToolStateParsing() {
        val state = StateParser.toolSession(JSONObject("""{
            "active":true,"tool":"LOOP_CUT","parameters":{"factor":0.25,"cuts":3},
            "slide_range":0.02,"slide_distance":0.005
        }"""))
        assertTrue(state.active)
        assertEquals(0.02, state.slideRange, 1e-12)
        assertEquals(0.005, state.slideDistance, 1e-12)
        assertEquals(0.25, state.double("factor")!!, 1e-12)
    }
    @Test fun legacyToolStateDoesNotOfferUncalibratedMetricInput() {
        val state = StateParser.toolSession(JSONObject("""{"active":true,"tool":"LOOP_CUT"}"""))
        assertEquals(0.0, state.slideRange, 0.0)
    }
}
