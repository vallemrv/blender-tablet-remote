package com.blendertablet.remote.network

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class SculptCommandQueueTest {
    private fun stroke(phase: String, count: Int = 0, id: String = "stroke-1") = SculptQueuedMessage("sculpt.stroke",
        JSONObject().put("phase", phase).put("stroke_id", id).put("points", JSONArray((0 until count).map { it })))

    @Test fun pendingSamplesMergeWithinServerBoundAndEndStaysLast() {
        val queue = SculptCommandQueue()
        queue.add(stroke("update", 64)); queue.add(stroke("update", 64)); queue.add(stroke("update", 30))
        queue.add(stroke("end"))
        assertEquals(128, queue.poll()!!.payload.getJSONArray("points").length())
        assertEquals(30, queue.poll()!!.payload.getJSONArray("points").length())
        assertEquals("end", queue.poll()!!.payload.getString("phase"))
        assertTrue(queue.isEmpty)
    }
    @Test fun navigationAndSettingsCannotOvertakeStrokeCompletion() {
        val queue = SculptCommandQueue()
        queue.add(stroke("update", 3)); queue.add(stroke("end"))
        queue.add(SculptQueuedMessage("gesture", JSONObject(), "orbit"))
        queue.add(SculptQueuedMessage("sculpt.settings", JSONObject()))
        queue.add(stroke("begin", 1, "stroke-2"))
        assertEquals("update", queue.poll()!!.payload.getString("phase"))
        assertEquals("end", queue.poll()!!.payload.getString("phase"))
        assertEquals("orbit", queue.poll()!!.raw)
        assertEquals("sculpt.settings", queue.poll()!!.name)
        assertEquals("stroke-2", queue.poll()!!.payload.getString("stroke_id"))
    }
    @Test fun failedUpdateRestoresBeforeNavigationAndDoesNotDiscardNextStroke() {
        val queue = SculptCommandQueue()
        queue.add(stroke("update", 20)); queue.add(stroke("end"))
        queue.add(SculptQueuedMessage("gesture", JSONObject(), "orbit"))
        queue.add(stroke("begin", 1, "stroke-2"))
        queue.recoverStroke("stroke-1")
        val recovery = queue.poll()!!
        assertEquals("cancel", recovery.payload.getString("phase"))
        assertEquals("stroke-1", recovery.payload.getString("stroke_id"))
        assertEquals("orbit", queue.poll()!!.raw)
        assertEquals("stroke-2", queue.poll()!!.payload.getString("stroke_id"))
    }
    @Test fun serverCommittedLongStrokeDropsRemainingPointsWithoutUndoingAcceptedWork() {
        val queue = SculptCommandQueue()
        queue.add(stroke("update", 100)); queue.add(stroke("end"))
        queue.add(SculptQueuedMessage("gesture", JSONObject(), "orbit"))
        queue.add(stroke("begin", 1, "stroke-2"))
        queue.add(stroke("update", 20, "stroke-2"))
        queue.removeStroke("stroke-1")
        assertEquals("orbit", queue.poll()!!.raw)
        assertEquals("begin", queue.poll()!!.payload.getString("phase"))
        assertEquals("stroke-2", queue.poll()!!.payload.getString("stroke_id"))
        assertTrue(queue.isEmpty)
    }
    @Test fun cancellationDropsOnlyItsOwnUnsentStrokeSamples() {
        val queue = SculptCommandQueue()
        queue.add(stroke("update", 20)); queue.add(stroke("end"))
        queue.add(SculptQueuedMessage("scene.get_state", JSONObject()))
        queue.add(stroke("cancel"))
        assertEquals("scene.get_state", queue.poll()!!.name)
        assertEquals("cancel", queue.poll()!!.payload.getString("phase"))
        assertTrue(queue.isEmpty)
    }
}
