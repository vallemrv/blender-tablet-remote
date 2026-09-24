package com.blendertablet.remote.network

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class CadDepthCommandQueueTest {
    private fun message(name: String, depth: Double = .02) = CadQueuedMessage(name, JSONObject().put("depth", depth))

    @Test fun slowServerReceivesOnlyFirstAndLatestDepthBeforeConfirmation() {
        val queue = CadDepthCommandQueue()
        queue.add(message("cad.extrude.update", .01))
        assertEquals(.01, queue.poll()!!.payload.getDouble("depth"), 0.0)
        repeat(100) { queue.add(message("cad.extrude.update", .02 + it * .001)) }
        queue.add(message("cad.session.confirm"))
        assertNull(queue.poll())
        queue.acknowledge(true)
        assertEquals(.119, queue.poll()!!.payload.getDouble("depth"), 1e-12)
        assertNull(queue.poll())
        queue.acknowledge(true)
        assertEquals("cad.session.confirm", queue.poll()!!.name)
        assertFalse(queue.busy)
    }

    @Test fun settleStaysBehindTheLatestGesture() {
        val queue = CadDepthCommandQueue()
        queue.add(message("cad.extrude.update", .01)); queue.poll()
        queue.add(message("cad.extrude.update", .02))
        queue.add(message("cad.extrude.update", .03))
        queue.add(CadQueuedMessage("cad.extrude.update", JSONObject().put("settle", true)))
        queue.acknowledge(true)
        assertEquals(.03, queue.poll()!!.payload.getDouble("depth"), 0.0)
        queue.acknowledge(true)
        assertTrue(queue.poll()!!.payload.optBoolean("settle"))
    }

    @Test fun settingsCancellationAndNextSessionKeepTheirOrder() {
        val queue = CadDepthCommandQueue()
        queue.add(message("cad.extrude.update")); queue.poll()
        queue.add(message("cad.settings"))
        queue.add(message("cad.extrude.update", .03))
        queue.add(CadQueuedMessage("gesture", JSONObject(), "pan"))
        queue.add(message("cad.session.cancel"))
        queue.add(message("cad.extrude.begin"))
        queue.add(message("cad.extrude.update", .04))
        queue.acknowledge(true)
        assertEquals("cad.settings", queue.poll()!!.name)
        assertEquals(.03, queue.poll()!!.payload.getDouble("depth"), 0.0)
        queue.acknowledge(true)
        assertEquals("pan", queue.poll()!!.raw)
        assertEquals("cad.session.cancel", queue.poll()!!.name)
        assertEquals("cad.extrude.begin", queue.poll()!!.name)
        assertEquals(.04, queue.poll()!!.payload.getDouble("depth"), 0.0)
    }

    @Test fun failureCannotConfirmStaleDepthAndDisconnectCannotReplayCandidates() {
        val queue = CadDepthCommandQueue()
        queue.add(message("cad.extrude.update")); queue.poll()
        queue.add(message("cad.extrude.update", 20000.0))
        queue.add(message("cad.session.confirm"))
        queue.add(message("cad.session.cancel"))
        queue.acknowledge(false)
        assertEquals("cad.session.cancel", queue.poll()!!.name)
        assertFalse(queue.busy)
        queue.add(message("cad.extrude.update")); queue.poll()
        queue.add(message("cad.session.confirm"))
        queue.clear()
        assertFalse(queue.busy)
        assertNull(queue.poll())
    }

    @Test fun failedPreviewDoesNotDiscardDepthOrConfirmationOfNextSession() {
        val queue = CadDepthCommandQueue()
        queue.add(message("cad.extrude.update")); queue.poll()
        queue.add(message("cad.session.confirm"))
        queue.add(message("cad.session.cancel"))
        queue.add(message("cad.extrude.begin"))
        queue.add(message("cad.extrude.update", .04))
        queue.add(message("cad.session.confirm"))
        queue.acknowledge(false)
        assertEquals("cad.session.cancel", queue.poll()!!.name)
        assertEquals("cad.extrude.begin", queue.poll()!!.name)
        assertEquals(.04, queue.poll()!!.payload.getDouble("depth"), 0.0)
        queue.acknowledge(true)
        assertEquals("cad.session.confirm", queue.poll()!!.name)
    }
}
