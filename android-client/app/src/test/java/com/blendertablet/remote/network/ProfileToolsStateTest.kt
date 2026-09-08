package com.blendertablet.remote.network

import com.blendertablet.remote.model.EditTool
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ProfileToolsStateTest {
    @Test fun profileSessionsKeepSchemaUnitsAndDoNotSendViewportNudges() {
        for (tool in listOf(EditTool.REVOLVE, EditTool.SWEEP)) {
            val state = StateParser.toolSession(JSONObject("""{
                "tool":"${tool.wire}","active":true,"input":"PARAMETERS",
                "parameters":{"steps":32,"width":50},
                "controls":[
                    {"id":"steps","label":"Segmentos","type":"int","min":1,"max":256,"step":1},
                    {"id":"width","label":"Ancho","type":"float","unit":"length"}
                ]
            }"""))
            assertEquals(tool, state.tool)
            assertFalse(state.acceptsViewportNudge)
            assertEquals("int", state.controls[0].type)
            assertEquals(256.0, state.controls[0].max!!, 0.0)
            assertEquals("length", state.controls[1].unit)
            assertEquals(50.0, state.double("width")!!, 0.0)
        }
    }
}
