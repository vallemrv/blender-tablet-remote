package com.blendertablet.remote

import com.blendertablet.remote.model.SelectionMode
import com.blendertablet.remote.network.StateParser
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class EditCatalogParserTest {
    @Test fun `catalogo agrupa por selector y conserva variantes`() {
        val catalog = StateParser.editCatalog(JSONObject("""
            {"groups":{"EDGE":[{"id":"BRIDGE_EDGE_LOOPS","label":"Bridge Edge Loops",
            "execution":"SESSION","command":"tool.begin","payload":{"tool":"BRIDGE_EDGE_LOOPS"},
            "requirements":{"mode":"EDIT"},"variants":[{"id":"DEFAULT","label":"Normal"}],
            "parameters":[{"id":"segments","label":"Segmentos","type":"int"}]}]}}
        """))
        val bridge = catalog.actionsFor(SelectionMode.EDGE).single()
        assertTrue(catalog.available)
        assertTrue(catalog.actionsFor(SelectionMode.VERTEX).isEmpty())
        assertEquals("BRIDGE_EDGE_LOOPS", bridge.id)
        assertEquals("DEFAULT", bridge.variants.single().id)
        assertEquals("segments", bridge.parameters.single().id)
        assertEquals("tool.begin", bridge.command)
        assertEquals("BRIDGE_EDGE_LOOPS", bridge.payload["tool"])
        assertEquals("EDIT", bridge.requirements["mode"])
    }

    @Test fun `catalogo vacio y campos desconocidos son tolerantes`() {
        assertFalse(StateParser.editCatalog(null).available)
        val catalog = StateParser.editCatalog(JSONObject("""
            {"groups":{"FACE":[{"id":"FLIP_NORMALS","unknown":42},{"label":"sin id"}]}}
        """))
        assertEquals(listOf("FLIP_NORMALS"), catalog.actionsFor(SelectionMode.FACE).map { it.id })
    }

    @Test fun `extrude anuncia eje y orientacion con applies_to`() {
        val catalog = StateParser.editCatalog(JSONObject("""
            {"groups":{"FACE":[{"id":"EXTRUDE","label":"Extruir","execution":"SESSION",
            "command":"tool.begin","payload":{"tool":"EXTRUDE"},
            "parameters":[
              {"id":"offset","label":"Desplazamiento","type":"float","default":0.0},
              {"id":"constraint","label":"Eje","type":"enum","default":"FREE",
               "values":["FREE","X","Y","Z"],"applies_to":["REGION"]},
              {"id":"orientation","label":"Orientación","type":"enum","default":"GLOBAL",
               "values":["GLOBAL","LOCAL","VIEW"],"applies_to":["REGION"]}
            ]}]}}
        """))
        val extrude = catalog.actionsFor(SelectionMode.FACE).single()
        val constraint = extrude.parameters.first { it.id == "constraint" }
        assertEquals(listOf("FREE", "X", "Y", "Z"), constraint.values)
        assertEquals(listOf("REGION"), constraint.appliesTo)
        assertEquals(listOf("GLOBAL", "LOCAL", "VIEW"),
            extrude.parameters.first { it.id == "orientation" }.values)
    }
}
