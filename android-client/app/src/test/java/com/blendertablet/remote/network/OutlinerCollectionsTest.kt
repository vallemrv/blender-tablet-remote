package com.blendertablet.remote.network

import com.blendertablet.remote.model.outlinerTreeRows
import com.blendertablet.remote.model.treeName
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class OutlinerCollectionsTest {
    @Test fun emptyCollectionsAndMultipleParentsAppearInEachTreeBranch() {
        val collections = StateParser.outlinerCollections(JSONArray("""[
            {"id":"root","name":"Escena","root":true,"editable":true},
            {"id":"a","name":"A","parents":["root"],"editable":true,"count":0},
            {"id":"b","name":"B","parents":["root"],"editable":true,"count":0},
            {"id":"child","name":"Compartida","parents":["a","b"],"editable":true,"count":1}
        ]"""))
        assertEquals(4, collections.size)
        assertEquals(0, collections[1].count)
        val rows = outlinerTreeRows(collections)
        assertEquals(listOf("root", "a", "child", "b", "child"), rows.map { it.collection?.id })
        assertEquals(listOf(0, 1, 2, 1, 2), rows.map { it.depth })
        assertEquals("/", rows.first().collection!!.treeName)
        assertEquals(listOf("root", "a", "b", "child"),
            outlinerTreeRows(collections, collapsed = setOf("a")).map { it.collection?.id })
        assertEquals(listOf("root"), outlinerTreeRows(collections, collapsed = setOf("root")).map { it.collection?.id })
        // Al abrir, todo plegado salvo la raíz; abrir «a» muestra solo su rama.
        val closed = com.blendertablet.remote.ui.collapsedExcept(collections, emptySet())
        assertEquals(listOf("root", "a", "b"), outlinerTreeRows(collections, collapsed = closed).map { it.collection?.id })
        assertEquals(listOf("root", "a", "child", "b"), outlinerTreeRows(collections,
            collapsed = com.blendertablet.remote.ui.collapsedExcept(collections, setOf("a"))).map { it.collection?.id })
        assertEquals(listOf("root"), outlinerTreeRows(collections,
            collapsed = com.blendertablet.remote.ui.collapsedExcept(collections, setOf("!root"))).map { it.collection?.id })

    }
    @Test fun searchRevealsObjectsInsideCollapsedBranchesAndKeepsEmptyCollectionMatches() {
        val collections = StateParser.outlinerCollections(JSONArray("""[
            {"id":"root","name":"/","root":true},
            {"id":"a","name":"Piezas","parents":["root"]},
            {"id":"empty","name":"Vacía","parents":["root"]}
        ]"""))
        val objects = StateParser.outlinerObjects(JSONArray("""[
            {"id":"o","name":"Tornillo","collection_ids":["a"]},
            {"id":"r","name":"Cubo","collection_ids":["root"]}
        ]"""))
        val collapsed = setOf("root", "a")
        val found = outlinerTreeRows(collections, objects, collapsed, "Tornillo")
        assertEquals(listOf("root", "a", "o"), found.map { it.collection?.id ?: it.obj?.id })
        assertEquals(listOf(0, 1, 2), found.map { it.depth })
        assertEquals(listOf("root", "empty"), outlinerTreeRows(collections, objects, collapsed, "Vacía").map { it.collection?.id })
        assertEquals(listOf("root", "a", "o"), outlinerTreeRows(collections, objects, collapsed, "Piezas").map { it.collection?.id ?: it.obj?.id })
        assertTrue(outlinerTreeRows(collections, objects, query = "ausente").isEmpty())
        assertEquals(1, outlinerTreeRows(collections, objects, collapsed).size)
        assertEquals("r", outlinerTreeRows(collections, objects).last().obj?.id)
    }

    @Test fun membershipUsesIdentityAndCapabilityIsExplicit() {
        val objects = StateParser.outlinerObjects(JSONArray("""[
            {"id":"object","name":"Referencia","collection_ids":["c1"],"collections":["Imágenes"]}
        ]"""))
        assertEquals(listOf("c1"), objects.single().collectionIds)
        assertTrue(StateParser.features(JSONObject("""{"features":{"outliner":{"version":1,"collections":true}}}""")).outlinerCollections)
        assertFalse(StateParser.features(JSONObject("""{"features":{"outliner":{"version":1}}}""")).outlinerCollections)
    }
}
