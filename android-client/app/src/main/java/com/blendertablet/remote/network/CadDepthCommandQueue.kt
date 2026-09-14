package com.blendertablet.remote.network

import org.json.JSONObject

internal data class CadQueuedMessage(val name: String, val payload: JSONObject, val raw: String? = null)

/** Depth is an absolute candidate: keep the newest unsent value, before its confirmation. */
internal class CadDepthCommandQueue {
    private val queue = java.util.ArrayDeque<CadQueuedMessage>()
    private var inFlight = false
    val busy: Boolean get() = inFlight || queue.isNotEmpty()

    fun add(message: CadQueuedMessage) {
        if (message.name == "cad.extrude.update" && queue.peekLast()?.name == message.name) queue.removeLast()
        queue.addLast(message)
    }

    fun poll(): CadQueuedMessage? {
        if (inFlight) return null
        return queue.pollFirst()?.also { if (it.name == "cad.extrude.update") inFlight = true }
    }

    fun acknowledge(ok: Boolean) {
        inFlight = false
        // Never confirm an older solid after the requested depth was rejected.
        if (!ok) {
            val pending = queue.iterator()
            while (pending.hasNext()) {
                val name = pending.next().name
                if (name == "cad.extrude.begin") break
                if (name == "cad.extrude.update" || name == "cad.session.confirm") pending.remove()
            }
        }
    }

    fun clear() { queue.clear(); inFlight = false }
}
