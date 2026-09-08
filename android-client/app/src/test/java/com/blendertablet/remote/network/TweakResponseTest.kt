package com.blendertablet.remote.network

import com.blendertablet.remote.model.BlenderMode
import com.blendertablet.remote.model.SelectionMode
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class TweakResponseTest {
    private fun scene() = JSONObject("""{
        "mode":"EDIT", "active_object":"Cube", "selection_mode":"EDGE",
        "selected_objects":["Cube"], "objects":[{"name":"Cube","type":"MESH"}]
    }""")

    @Test fun updatesKeepEditModeActiveObjectAndSelectionThroughoutDrag() {
        val begin = scene().put("tweak", true).put("session_id", "tweak-1")
        var current = StateParser.state(tweakSceneSnapshot(begin)!!)
        for (value in listOf(.01, .02, .03)) {
            // El estado modal real también tiene mode y objects, pero no es un snapshot.
            val update = JSONObject("""{
                "active":true, "session_id":"tweak-1", "tweak":true,
                "mode":"MOVE", "tool":"MOVE", "objects":["Cube"],
                "values":[$value,0,0], "motion":"FREE", "snap_type":"NONE"
            }""")
            tweakSceneSnapshot(update)?.let { current = StateParser.state(it) }
            assertEquals(BlenderMode.EDIT, current.mode)
            assertEquals("Cube", current.activeObject)
            assertEquals(SelectionMode.EDGE, current.selectionMode)
        }
        val end = scene().put("active", false).put("tweak_finished", "tweak-1")
        assertSame(end, tweakSceneSnapshot(end))
        assertEquals(BlenderMode.EDIT, StateParser.state(tweakSceneSnapshot(end)!!).mode)
    }

    @Test fun missedAndLateGesturesDoNotReplaceScene() {
        assertNull(tweakSceneSnapshot(null))
        assertNull(tweakSceneSnapshot(JSONObject("""{"hit":false,"tweak":true,"orbit":true}""")))
        assertNull(tweakSceneSnapshot(JSONObject("""{"tweak":true,"moved":false}""")))
    }
}
