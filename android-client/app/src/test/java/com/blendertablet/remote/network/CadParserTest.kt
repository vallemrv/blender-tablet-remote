package com.blendertablet.remote.network

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class CadParserTest {
    private val capabilities = """{"version":1,"length_unit":"METERS","planes":["XY","FUTURE"],"entities":["RECTANGLE","CIRCLE","LINE","FUTURE"],"features":["EXTRUDE","FUTURE"]}"""
    @Test fun sharedBackendFixturePreservesFeatureAndDocumentRevision() {
        val fixture = javaClass.classLoader!!.getResourceAsStream("cad_v1.json")!!.bufferedReader().use { JSONObject(it.readText()) }
        assertTrue(CadParser.capabilities(fixture.getJSONObject("capability")).available)
        val state = CadParser.state(fixture.getJSONObject("state"))
        assertEquals("doc_fixture", state.documentId)
        assertEquals(3L, state.revision)
        assertEquals("feature_fixture", state.selectedFeature?.id)
        assertEquals(0.08, state.sketches.single().entities.single().values["width"]!!, 1e-12)
        assertFalse(state.sessionActive)
        assertTrue(state.isolated)
    }
    @Test fun isolationIsExplicitAndDoesNotChangeWorkspaceIdentity() {
        val state = CadParser.state(JSONObject("""{"version":1,"workspace":true,"isolated":true}"""))
        assertTrue(state.workspace)
        assertTrue(state.isolated)
    }
    @Test fun omittedIsolationDefaultsToFalse() {
        val state = CadParser.state(JSONObject("""{"version":1,"workspace":true}"""))
        assertTrue(state.workspace)
        assertFalse(state.isolated)
    }
    @Test fun oldBackendOffersNoCad() {
        assertFalse(CadParser.capabilities(null).available)
        assertFalse(StateParser.features(JSONObject("""{"features":{}}""")).cad.available)
    }
    @Test fun futureProtocolAndUnknownLengthConventionAreNotActivated() {
        assertFalse(CadParser.capabilities(JSONObject(capabilities).put("version", 2)).available)
        assertFalse(CadParser.capabilities(JSONObject(capabilities).put("length_unit", "BLENDER_UNITS")).available)
    }
    @Test fun unsupportedToolsDoNotEnterCatalog() {
        val caps = CadParser.capabilities(JSONObject(capabilities))
        assertTrue(caps.available)
        assertEquals(listOf("XY"), caps.planes)
        assertEquals(listOf("RECTANGLE", "CIRCLE", "LINE"), caps.entities)
        assertEquals(listOf("EXTRUDE"), caps.features)
    }
    @Test fun documentRecoversDimensionsSelectionAndDependencies() {
        val state = CadParser.state(JSONObject("""{
          "version":1,"workspace":true,"active_sketch_id":"s1",
          "document":{"id":"d1","sketches":[{"id":"s1","name":"Boceto 1","plane":"XY",
            "entities":[{"id":"e1","type":"RECTANGLE","x":0,"y":0,"width":0.1,"height":0.045}],
            "profiles":[{"id":"p1","entity_id":"e1","label":"Exterior"}]}],
            "features":[{"id":"f1","name":"Extrusión 1","sketch_id":"s1","profile_id":"p1","depth":0.02,"enabled":true}]},
          "selection":{"kind":"ENTITY","id":"e1"},"session":{"active":false}}
        """))
        assertTrue(state.workspace)
        assertEquals("s1", state.activeSketch?.id)
        assertEquals(0.1, state.selectedEntity!!.values["width"]!!, 1e-12)
        assertEquals("p1", state.features.single().profileId)
        assertEquals(0.02, state.features.single().depth, 1e-12)
        assertFalse(state.sessionActive)
    }
    @Test fun invalidSelectionCannotEditAnotherEntity() {
        val state = CadParser.state(JSONObject("""{"version":1,"workspace":true,"selection":{"kind":"ENTITY","id":"deleted"},"document":{"sketches":[]}}"""))
        assertNull(state.selectedEntity)
        assertNull(state.selectedFeature)
        assertNull(state.selectedSketch)
    }
    @Test fun selectedProfileOrOperationResolvesItsExistingSketchForEditing() {
        val state = CadParser.state(JSONObject("""{
          "version":1,"workspace":true,
          "document":{"sketches":[
            {"id":"other","entities":[],"profiles":[]},
            {"id":"source","entities":[{"id":"line1","type":"LINE"},{"id":"line2","type":"LINE"}],
             "profiles":[{"id":"profile_chain","entity_id":"chain","label":"Contorno"}]}],
            "features":[{"id":"cut","type":"CUT","sketch_id":"source","target_id":"base","profile_id":"profile_chain"}]},
          "selection":{"kind":"PROFILE","id":"profile_chain"}}
        """))
        assertNull(state.activeSketch)
        assertEquals("source", state.selectedSketch?.id)
        assertEquals("source", state.copy(selectionKind = "FEATURE", selectionId = "cut").selectedSketch?.id)
        assertEquals("source", state.copy(selectionKind = "ENTITY", selectionId = "line2").selectedSketch?.id)
        assertNull(state.copy(selectionId = "deleted_profile").selectedSketch)
        assertNull(state.copy(selectionKind = "FEATURE", selectionId = "deleted_feature").selectedSketch)
    }
    @Test fun previewRetainsDepthAndConfirmationAuthority() {
        val state = CadParser.state(JSONObject("""{"version":1,"workspace":true,"session":{"active":true,"operation":"EXTRUDE","depth":0.03,"can_confirm":false}}"""))
        assertTrue(state.sessionActive)
        assertFalse(state.canConfirm)
        assertEquals(0.03, state.depth, 1e-12)
    }
    @Test fun overlayRejectsInvalidCoordinatesButPreservesOffscreenPoints() {
        val state = CadParser.state(JSONObject("""{"version":1,"overlay":[{"id":"e1","selected":true,"closed":true,"points":[[0.2,0.3],[null,0],[1.2,-0.1]]}]}"""))
        val stroke = state.overlay.single()
        assertEquals(2, stroke.points.size)
        assertEquals(1.2f, stroke.points.last().first)
        assertTrue(stroke.closed && stroke.selected)
    }
    @Test fun unsupportedStateNeverClaimsWorkspace() {
        assertFalse(CadParser.state(JSONObject("""{"version":2,"workspace":true}""")).workspace)
    }
    @Test fun sketchEditingPreservesHandlesRulesAndCutPreview() {
        val state = CadParser.state(JSONObject("""{
          "version":1,"workspace":true,"step":0.002,"increment":false,
          "active_sketch_id":"s", "selection":{"kind":"ENTITY","id":"b","items":[{"id":"a","part":"END"},{"id":"b","part":"START"}]},
          "document":{"sketches":[{"id":"s","plane":"XY","entities":[{"id":"a","type":"ARC","radius":0.01,"sweep":90}],
            "constraints":[{"id":"c","type":"COINCIDENT","refs":[{"id":"a"},{"id":"b"}]}]}],
            "features":[{"id":"cut","type":"CUT","target_id":"base","depth":0.005,"enabled":true}]},
          "session":{"id":"preview","active":true,"operation":"CUT","depth":0.005,"transparent":true,"can_confirm":true},
          "overlay":[{"id":"a","points":[[0.1,0.2]],"handles":[{"part":"END","point":[0.2,0.3],"selected":true},{"part":"BAD","point":[null,0]}],"selected_parts":["END"]}]
        }"""))
        assertEquals(listOf("END", "START"), state.selection.map { it.part })
        assertEquals("COINCIDENT", state.activeSketch!!.constraints.single().type)
        assertEquals(90.0, state.activeSketch!!.entities.single().values["sweep"]!!, 0.0)
        assertEquals("base", state.features.single().targetId)
        assertEquals("CUT", state.features.single().type)
        assertEquals("preview", state.sessionId)
        assertTrue(state.transparent && state.canConfirm)
        assertFalse(state.increment)
        assertEquals(.002, state.step, 0.0)
        assertTrue(state.overlay.single().handles.single().selected)
    }
    @Test fun extendedCapabilitiesFilterUnsupportedConstraints() {
        val caps = CadParser.capabilities(JSONObject(capabilities).put("sketch_editing", true)
            .put("entities", org.json.JSONArray(listOf("SQUARE", "ARC")))
            .put("features", org.json.JSONArray(listOf("EXTRUDE", "CUT")))
            .put("constraints", org.json.JSONArray(listOf("TANGENT", "COINCIDENT", "UNSUPPORTED"))))
        assertTrue(caps.sketchEditing)
        assertEquals(listOf("SQUARE", "ARC"), caps.entities)
        assertEquals(listOf("EXTRUDE", "CUT"), caps.features)
        assertEquals(listOf("TANGENT", "COINCIDENT"), caps.constraints)
    }

}
