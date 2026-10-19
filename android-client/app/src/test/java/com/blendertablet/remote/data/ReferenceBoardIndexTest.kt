package com.blendertablet.remote.data

import org.junit.Assert.*
import org.junit.Test
import com.blendertablet.remote.network.StateParser
import org.json.JSONObject

class ReferenceBoardIndexTest {
    private val a = ReferenceRecord("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "Nave")
    private val b = ReferenceRecord("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "Dibujo")
    @Test fun newSceneIsEmptyAndReturningToSavedSceneRestoresItsBoard() {
        val index = ReferenceBoardIndex()
        index.add("nave", a)
        assertTrue(index.list("nueva").isEmpty())
        assertTrue(index.list("").isEmpty())
        index.add("nueva", b)
        val reopened = ReferenceBoardIndex(index.boardsJson(), index.legacyJson())
        assertEquals(listOf(a), reopened.list("nave"))
        assertEquals(listOf(b), reopened.list("nueva"))
    }
    @Test fun legacyImagesRequireExplicitRecoveryAndAreNotDeleted() {
        val index = ReferenceBoardIndex(legacyJson = """[{"id":"${a.id}","name":"Nave"}]""")
        assertTrue(index.list("nueva").isEmpty())
        assertEquals(listOf(a), index.previous())
        index.recover("nave", a.id)
        assertEquals(listOf(a), index.list("nave"))
        assertTrue(index.previous().isEmpty())
        assertTrue(index.list("nueva").isEmpty())
    }
    @Test fun removingFromOneBoardKeepsAnyOtherOwnerAndOriginalImportTarget() {
        val index = ReferenceBoardIndex()
        val pickerTarget = "nave"
        index.add("nueva", b)
        index.add(pickerTarget, a) // el selector de Android termina después de cambiar escena
        assertEquals(listOf(b), index.list("nueva"))
        index.add("copia", a)
        index.remove("nave", a.id)
        assertTrue(index.contains(a.id))
        assertTrue(index.list("nave").isEmpty())
        index.remove("copia", a.id)
        assertFalse(index.contains(a.id))
    }
    @Test fun backendIdentityIsParsedWithoutLeakingThePreviousSceneIdentity() {
        val before = StateParser.sceneScale(JSONObject("""{"reference_board_id":"board-a"}"""))
        assertEquals("board-a", before.referenceBoardId)
        assertEquals("", StateParser.sceneScale(JSONObject("""{"scene_id":"new"}"""), before).referenceBoardId)
    }
}
