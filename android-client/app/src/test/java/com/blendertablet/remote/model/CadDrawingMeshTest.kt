package com.blendertablet.remote.model

import com.blendertablet.remote.network.CadParser
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class CadDrawingMeshTest {
    private val line=CadEntity("line","LINE",emptyMap())
    private val circle=CadEntity("circle","CIRCLE",emptyMap())
    private val sketch=CadSketch("sketch","Boceto","XY",listOf(line,circle),emptyList())
    private fun state()=CadState(workspace=true,documentId="doc",revision=3,sketches=listOf(sketch),activeSketchId="sketch")
    @Test fun straightSelectionHidesResolutionEvenWithAnUnselectedCircleInTheSketch() {
        val target=cadDrawingMeshTarget(state().copy(selectionKind="ENTITY",selectionId="line",selection=listOf(CadSelection("line","START"))))!!
        assertFalse(target.curved);assertEquals(listOf("line"),target.entityIds);assertEquals(1,target.count)
        assertTrue(cadDrawingMeshTarget(state())!!.curved)
        assertNull(cadDrawingMeshTarget(state().copy(selectionKind="ENTITY",selectionId="ORIGIN")))
        assertNull(cadDrawingMeshTarget(state().copy(sessionActive=true)))
    }
    @Test fun profilesResolveTheirOriginalEntitiesAndCapabilityComesFromTheServer() {
        val parsed=CadParser.state(JSONObject("""{"version":1,"workspace":true,"selection":{"kind":"PROFILE","id":"profile-chain"},
          "document":{"id":"doc","revision":2,"sketches":[{"id":"s","plane":"XY","entities":[{"id":"arc","type":"ARC"},{"id":"line","type":"LINE"}],
          "profiles":[{"id":"profile-chain","entity_id":"chain","entity_ids":["arc","line"]}]}]}}"""))
        val target=cadDrawingMeshTarget(parsed)!!
        assertEquals(listOf("arc","line"),target.entityIds);assertTrue(target.curved)
        val cap=JSONObject("""{"version":2,"length_unit":"METERS","planes":["XY"],"sketch_mesh":true}""")
        assertTrue(CadParser.capabilities(cap).sketchMesh)
        assertFalse(CadParser.capabilities(JSONObject()).sketchMesh)
    }
}
