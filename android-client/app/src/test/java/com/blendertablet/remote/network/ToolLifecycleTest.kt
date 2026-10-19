package com.blendertablet.remote.network

import com.blendertablet.remote.model.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import okhttp3.Request
import okhttp3.WebSocket
import okio.ByteString
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ToolLifecycleTest {
    private class Wire : WebSocket {
        val sent = mutableListOf<JSONObject>()
        override fun request() = Request.Builder().url("http://localhost").build()
        override fun queueSize() = 0L
        override fun send(text: String): Boolean { sent.add(JSONObject(text)); return true }
        override fun send(bytes: ByteString) = false
        override fun close(code: Int, reason: String?) = true
        override fun cancel() {}
    }

    @Test fun lateToolRepliesCannotReopenOrSendQueuedNudgesIntoAnotherTool() {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined)
        val client = WebSocketRemoteBlenderClient(scope)
        val wire = Wire()
        fun field(name: String) = client.javaClass.getDeclaredField(name).apply { isAccessible = true }
        field("socket").set(client, wire)
        @Suppress("UNCHECKED_CAST")
        (field("_connection").get(client) as MutableStateFlow<ConnectionStatus>).value = ConnectionStatus.CONNECTED
        val handle = client.javaClass.getDeclaredMethod("handle", JSONObject::class.java).apply { isAccessible = true }
        fun reply(request: JSONObject, tool: String, session: String, active: Boolean = true) {
            handle.invoke(client, JSONObject().put("type", "response").put("id", request.getString("id")).put("ok", true)
                .put("result", JSONObject().put("active", active).put("armed", active).put("tool", tool)
                    .put("session_id", session).put("parameters", JSONObject().put("factor", 0.0))))
        }
        try {
            client.toolBegin(EditTool.LOOP_CUT, emptyMap())
            val firstBegin = wire.sent.last()
            reply(firstBegin, "LOOP_CUT", "cut")
            client.toolNudge(.01)
            val oldNudge = wire.sent.last()
            assertEquals("tool.nudge", oldNudge.getString("command"))
            client.toolNudge(.02) // Accumulated while the first update is still in flight.
            client.toolCancel()
            val oldCancel = wire.sent.last()
            client.toolBegin(EditTool.BEVEL, emptyMap())
            val newBegin = wire.sent.last()
            reply(newBegin, "BEVEL", "bevel")
            val count = wire.sent.size
            reply(oldNudge, "LOOP_CUT", "cut")
            reply(oldCancel, "LOOP_CUT", "cut", false)
            assertEquals("bevel", client.toolSession.value.sessionId)
            assertEquals(count, wire.sent.size)
            client.toolCancel()
            val cancelledCount = wire.sent.size
            client.toolParameter(mapOf("offset" to .5))
            client.toolNudge(.02)
            assertEquals(cancelledCount, wire.sent.size)
            assertFalse(client.toolSession.value.active)
            handle.invoke(client, JSONObject("""{"type":"event","event":"tool.session","payload":{"active":true,"tool":"ALIGN","session_id":"old"}}"""))
            assertFalse(client.toolSession.value.active)
        } finally { scope.cancel() }
    }
}
