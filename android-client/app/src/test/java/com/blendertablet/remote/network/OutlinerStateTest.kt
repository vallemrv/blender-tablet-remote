package com.blendertablet.remote.network

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class OutlinerStateTest {
    @Test fun hiddenLockedAndExcludedRowsRemainListedButCannotBeSelected() {
        val rows=StateParser.outlinerObjects(JSONArray("""[
          {"id":"1","name":"Visible","type":"MESH","visible":true,"in_view_layer":true,"editable":true},
          {"id":"2","name":"Bloqueado","type":"EMPTY","visible":true,"locked":true,"in_view_layer":true,"editable":true},
          {"id":"3","name":"Oculto","type":"MESH","visible":false,"hidden":true,"in_view_layer":true,"editable":true},
          {"id":"4","name":"Excluido","type":"MESH","visible":false,"in_view_layer":false,"editable":true,"collections":["Interior"],"parent":"Grupo"}
        ]"""))
        assertEquals(4,rows.size)
        assertTrue(rows[0].canSelect)
        rows.drop(1).forEach { assertFalse(it.canSelect) }
        assertTrue(rows[1].locked)
        assertTrue(rows[2].hidden)
        assertEquals("Grupo",rows[3].parent)
        assertEquals(listOf("Interior"),rows[3].collections)
        assertNull(rows[0].parent)
    }
    @Test fun capabilityAndRenamingKeepTheOpaqueIdentity() {
        assertTrue(StateParser.features(JSONObject("""{"features":{"outliner":{"version":1}}}""")).outliner)
        assertFalse(StateParser.features(JSONObject("{}")).outliner)
        val before=StateParser.outlinerObjects(JSONArray("""[{"id":"scene:123","name":"Plano"}]""")).single()
        val after=StateParser.outlinerObjects(JSONArray("""[{"id":"scene:123","name":"Referencia frontal"}]""")).single()
        assertEquals(before.id,after.id)
        assertNotEquals(before.name,after.name)
    }
}
