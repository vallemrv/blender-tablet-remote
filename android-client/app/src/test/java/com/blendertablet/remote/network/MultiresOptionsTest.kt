package com.blendertablet.remote.network

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class MultiresOptionsTest {
    @Test fun nativeResolutionLimitsAndActionsArePreserved() {
        val json=JSONObject("""{"types":{"MULTIRES":{"parameters":{
            "levels":{"type":"int","default":1,"max":6,"max_parameter":"total_levels","label":"Vista"},
            "total_levels":{"type":"int","default":0,"read_only":true},
            "subdivide":{"type":"action","label":"Subdividir","max":6,"max_parameter":"total_levels"}
        }}}}""")
        val spec=StateParser.modifierOptions(json).single()
        assertEquals("MULTIRES",spec.type)
        assertEquals("Vista",spec.parameters.first{it.name=="levels"}.label)
        assertTrue(spec.parameters.first{it.name=="total_levels"}.readOnly)
        assertEquals("total_levels",spec.parameters.first{it.type=="action"}.maxParameter)
    }
}
