package com.blendertablet.remote.network

import com.blendertablet.remote.model.SurfaceControl
import com.blendertablet.remote.ui.surfaceSummary
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class MaterialStateTest {
    @Test fun objectSelectionRegionsAndBrushesSurviveParsing() {
        val state = MaterialParser.state(JSONObject("""{
            "objects":[{"id":"Interior","label":"Interior"}],"targets":[],"interaction":"SELECT","isolate":true,
            "brush":"SPRAY","brushes":[{"id":"SPRAY","label":"Salpicado"}],
            "scope":"GROUP:Mitad","regions":[{"id":"GROUP:Mitad","label":"Mitad"}],
            "paint_blocked":true,"paint_limit":20000} """))
        assertEquals("Interior", state.objects.single().id)
        assertTrue(state.targets.isEmpty())
        assertEquals("SELECT", state.interaction)
        assertTrue(state.isolate)
        assertEquals("SPRAY", state.brush)
        assertEquals("GROUP:Mitad", state.scope)
        assertTrue(state.paintBlocked)
        assertEquals(20000, state.paintLimit)
    }
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

    @Test fun surfaceFinishAndGrainArriveWithTheirOwnExplanations() {
        val state = MaterialParser.state(JSONObject("""{"preset":"gold","color":"#EBC16B","tinted":false,"custom":true,
            "finish":"metal","finishes":[{"id":"metal","label":"Metálico","hint":"Reflejo de metal."}],
            "surface":{"roughness":0.12,"metallic":1.0,"transmission":0.0,"ior":1.45,"coat":0.0},
            "surface_controls":[{"id":"ior","label":"Densidad óptica","low":"Aire","high":"Diamante","min":1.0,"max":3.0}],
            "grain":"bands","grain_scale":60.0,"grain_amount":0.8,"grain_relief":1.0,
            "grains":[{"id":"bands","label":"Cepillado","hint":"Rayas finas."}]}"""))
        assertFalse(state.tinted)
        assertTrue(state.custom)
        assertEquals("Reflejo de metal.", state.finishes.single().hint)
        assertEquals(1.0f, state.surface["metallic"])
        assertEquals(SurfaceControl("ior", "Densidad óptica", "Aire", "Diamante", 1f, 3f), state.surfaceControls.single())
        assertEquals("bands", state.grain)
        assertEquals(60f, state.grainScale)
        assertEquals(0.8f, state.grainAmount)
        assertEquals(1f, state.grainRelief)
        assertEquals("Cepillado", state.grains.single().label)
    }

    @Test fun aSurfaceIsDescribedInPlainWordsAndAnEmptyOneStaysSilent() {
        assertEquals("Metal · espejo", surfaceSummary(mapOf("metallic" to 1f, "roughness" to .1f)))
        assertEquals("Transparente · brillante", surfaceSummary(mapOf("transmission" to 1f, "roughness" to .2f)))
        assertEquals("No metálico · mate", surfaceSummary(mapOf("roughness" to .95f)))
        assertEquals("No metálico · satinado · barnizado", surfaceSummary(mapOf("roughness" to .5f, "coat" to 1f)))
        assertEquals("", surfaceSummary(emptyMap()))
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
