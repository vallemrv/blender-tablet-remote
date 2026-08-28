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

    @Test fun `edit_toolbar agrupa por familia y respeta el orden del servidor`() {
        val toolbar = StateParser.editToolbar(JSONObject("""
            {"families":[
              {"id":"EXTRUDE","label":"Extrude","default_variant":"REGION","command":"tool.begin",
               "payload":{"tool":"EXTRUDE"},"input":"PARAMETRIC",
               "variants":[{"id":"REGION","label":"Región"},{"id":"INDIVIDUAL","label":"Individual","enabled":false}],
               "parameters":[{"id":"offset","label":"Desplazamiento","type":"float","default":0.0}]},
              {"id":"CUT","label":"Cut","default_variant":"KNIFE","command":"tool.begin","payload":{},
               "variants":[
                 {"id":"KNIFE","label":"Cuchillo","input":"VIEWPORT_DRAG_SEGMENTS","payload":{"tool":"KNIFE"}},
                 {"id":"BISECT","label":"Bisect","input":"VIEWPORT_DRAG_LINE","payload":{"tool":"BISECT"},
                  "parameters":[{"id":"fill","label":"Rellenar","type":"bool","default":false}]}
               ]}
            ]}
        """))
        assertTrue(toolbar.available)
        assertEquals(listOf("EXTRUDE", "CUT"), toolbar.families.map { it.id })
        val extrude = toolbar.families.first { it.id == "EXTRUDE" }
        assertEquals("REGION", extrude.defaultVariant)
        assertEquals(listOf("REGION" to true, "INDIVIDUAL" to false), extrude.variants.map { it.id to it.enabled })
        assertEquals("offset", extrude.parameters.single().id)
        val cut = toolbar.families.first { it.id == "CUT" }
        assertEquals("tool.begin", cut.command)
        assertTrue(cut.payload.isEmpty())
        assertEquals("VIEWPORT_DRAG_SEGMENTS", cut.variants.first { it.id == "KNIFE" }.input)
        val bisect = cut.variants.first { it.id == "BISECT" }
        assertEquals("VIEWPORT_DRAG_LINE", bisect.input)
        assertEquals("BISECT", bisect.payload["tool"])
        assertEquals("fill", bisect.parameters.single().id)
    }

    @Test fun `edit_toolbar vacio y campos desconocidos son tolerantes`() {
        assertFalse(StateParser.editToolbar(null).available)
        val toolbar = StateParser.editToolbar(JSONObject("""
            {"families":[{"id":"LOOP_CUT","unknown_field":42,"variants":[{"no_id":true}]},{"label":"sin id"}]}
        """))
        assertEquals(listOf("LOOP_CUT"), toolbar.families.map { it.id })
        assertTrue(toolbar.families.single().variants.isEmpty())
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
