package com.blendertablet.remote.network

import org.json.JSONObject

internal data class CadQueuedMessage(val name: String, val payload: JSONObject, val raw: String? = null)

/** Depth (and a fillet width) is an absolute candidate: keep the newest unsent value, before its confirmation. */
internal class CadDepthCommandQueue {
    companion object {
        val CANDIDATES = setOf("cad.extrude.update", "cad.finish.update")
        private val BEGINS = setOf("cad.extrude.begin", "cad.finish.begin")
    }
    private val queue = java.util.ArrayDeque<CadQueuedMessage>()
    private var inFlight = false
    val busy: Boolean get() = inFlight || queue.isNotEmpty()

    fun add(message: CadQueuedMessage) {
        val last = queue.peekLast()
        val settle = message.payload.optBoolean("settle")
        if (!settle && message.name in CANDIDATES && last?.name == message.name && !last.payload.optBoolean("settle")) queue.removeLast()
        queue.addLast(message)
    }

    fun poll(): CadQueuedMessage? {
        if (inFlight) return null
        return queue.pollFirst()?.also { if (it.name in CANDIDATES) inFlight = true }
    }

    fun acknowledge(ok: Boolean) {
        inFlight = false
        // Never confirm an older solid after the requested depth was rejected.
        if (!ok) {
            val pending = queue.iterator()
            while (pending.hasNext()) {
                val name = pending.next().name
                if (name in BEGINS) break
                if (name in CANDIDATES || name == "cad.session.confirm") pending.remove()
            }
        }
    }

    fun clear() { queue.clear(); inFlight = false }
}
