package com.blendertablet.remote.network

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class MaterialStateTest {
    @Test fun customCatalogAndWorkspaceSurviveSceneSnapshot() {
        val state = StateParser.state(JSONObject("""{"mode":"MATERIAL","material":{
            "available":true,"active":true,"targets":["Uno","Dos"],"preset":"my-stone","color":"#123456",
            "paint_ready":true,"finish":"worn","erase":true,
            "presets":[{"id":"my-stone","label":"Mi piedra","color":"#123456"}],
            "environments":[{"id":"soft","label":"Luz suave"}]}}"""))
        assertTrue(state.material.active)
        assertEquals(listOf("Uno", "Dos"), state.material.targets)
        assertEquals("Mi piedra", state.material.presets.single().label)
        assertEquals("worn", state.material.finish)
        assertTrue(state.material.erase)
        assertTrue(state.material.paintReady)
        assertFalse(MaterialParser.state(null).available)
    }

    @Test fun detailRecipesAreSeparateFromBaseAndKeepCustomTint() {
        val state=MaterialParser.state(JSONObject("""{"preset":"iron","color":"#DD1122","presets":[
          {"id":"iron","label":"Hierro","category":"base"},{"id":"rust","label":"Óxido","category":"detail"}]}"""))
        assertEquals("#DD1122",state.color)
        assertEquals(listOf("rust"),state.presets.filter { it.category=="detail" }.map { it.id })
    }

    @Test fun materialRecoveryCannotSendASculptCancellation() {
        val queue = SculptCommandQueue()
        fun stroke(phase: String, n: Int) = SculptQueuedMessage("material.stroke", JSONObject()
            .put("phase", phase).put("stroke_id", "paint").put("points", JSONArray((0 until n).toList())))
        queue.add(stroke("update", 64)); queue.add(stroke("update", 64)); queue.add(stroke("end", 0))
        assertEquals(128, queue.poll()!!.payload.getJSONArray("points").length())
        queue.add(SculptQueuedMessage("mode.set", JSONObject().put("mode", "OBJECT")))
        queue.recoverStroke("paint", "material.stroke")
        val cancel = queue.poll()!!
        assertEquals("material.stroke", cancel.name)
        assertEquals("cancel", cancel.payload.getString("phase"))
        assertEquals("mode.set", queue.poll()!!.name)
        assertTrue(queue.isEmpty)
    }

    @Test fun materialAndSculptSamplesNeverMerge() {
        val queue = SculptCommandQueue()
        listOf("material.stroke", "sculpt.stroke").forEach { name ->
            queue.add(SculptQueuedMessage(name, JSONObject().put("phase", "update")
                .put("stroke_id", "same").put("points", JSONArray().put(1))))
        }
        assertEquals("material.stroke", queue.poll()!!.name)
        assertEquals("sculpt.stroke", queue.poll()!!.name)
    }
}
