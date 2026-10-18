package com.blendertablet.remote.network

import com.blendertablet.remote.model.outlinerCollectionScope
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class OutlinerCollectionsTest {
    @Test fun emptyCollectionsAndMultipleParentsRemainAvailableForFiltering() {
        val collections = StateParser.outlinerCollections(JSONArray("""[
            {"id":"root","name":"Escena","root":true,"editable":true},
            {"id":"a","name":"A","parents":["root"],"editable":true,"count":0},
            {"id":"b","name":"B","parents":["root"],"editable":true,"count":0},
            {"id":"child","name":"Compartida","parents":["a","b"],"editable":true,"count":1}
        ]"""))
        assertEquals(4, collections.size)
        assertEquals(0, collections[1].count)
        assertEquals(setOf("a", "child"), outlinerCollectionScope(collections, "a"))
        assertEquals(setOf("b", "child"), outlinerCollectionScope(collections, "b"))
        assertEquals(setOf("root", "a", "b", "child"), outlinerCollectionScope(collections, "root"))
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
