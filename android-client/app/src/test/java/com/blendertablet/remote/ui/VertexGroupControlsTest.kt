package com.blendertablet.remote.ui

import com.blendertablet.remote.network.StateParser
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class VertexGroupControlsTest {
    @Test fun weightsPreserveZeroAndFractionsAndRejectInvalidDrafts() {
        assertEquals(0.0, vertexGroupWeight("0")!!, 0.0)
        assertEquals(.25, vertexGroupWeight("0,25")!!, 0.0)
        assertEquals(1.0, vertexGroupWeight("1")!!, 0.0)
        for (text in listOf("", "-", "NaN", "Infinity", "-0.1", "1.1")) assertNull(vertexGroupWeight(text))
    }
    @Test fun activeObjectSnapshotRefreshesGroupNamesAndAvailability() {
        val first = StateParser.state(JSONObject("""{"mode":"EDIT","active_object":"Cube","active":{
            "type":"MESH","vertex_groups_available":true,"active_vertex_group":"Zona",
            "vertex_groups":[{"name":"Zona","locked":false},{"name":"Fijo","locked":true}]}}"""))
        assertTrue(first.vertexGroupsAvailable)
        assertEquals("Zona", first.activeVertexGroup)
        assertEquals(listOf("Zona","Fijo"), first.vertexGroups.map { it.name })
        assertTrue(first.vertexGroups.last().locked)
        val other = StateParser.state(JSONObject("""{"mode":"OBJECT","active_object":"Other","active":{"type":"MESH"}}"""))
        assertTrue(other.vertexGroups.isEmpty()); assertFalse(other.vertexGroupsAvailable); assertNull(other.activeVertexGroup)
    }
}
