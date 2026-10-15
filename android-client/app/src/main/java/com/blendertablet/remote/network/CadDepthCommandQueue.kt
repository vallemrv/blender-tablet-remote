package com.blendertablet.remote.network

import org.json.JSONObject

internal data class CadQueuedMessage(val name: String, val payload: JSONObject)

/** Serialize CAD computations; absolute pointer samples keep only the newest unsent candidate. */
internal class CadDepthCommandQueue {
    companion object {
        val CANDIDATES = setOf("cad.extrude.update", "cad.finish.update", "cad.shell.update", "cad.operation.update", "cad.plane.update", "cad.drag.update", "cad.entity.update", "cad.polygon.update")
        private val BEGINS = setOf("cad.extrude.begin", "cad.finish.begin", "cad.shell.begin", "cad.hole.begin", "cad.pattern.begin", "cad.combine.begin", "cad.plane.begin", "cad.drag.begin", "cad.entity.begin", "cad.polygon.begin")
        fun waitsForResponse(name: String?) = name?.startsWith("cad.") == true && name != "cad.state"
    }
    private val queue = java.util.ArrayDeque<CadQueuedMessage>()
    private var inFlight = false
    val busy: Boolean get() = inFlight || queue.isNotEmpty()

    fun add(message: CadQueuedMessage) {
        val last = queue.peekLast()
        val settle = message.payload.optBoolean("settle")
        // Shell thickness and side edits are independent: never drop one for the other.
        val sameShellFields = message.name !in setOf("cad.shell.update", "cad.operation.update", "cad.plane.update") || last?.payload?.keys()?.asSequence()?.toSet() == message.payload.keys().asSequence().toSet()
        if (!settle && sameShellFields && message.name in CANDIDATES && last?.name == message.name && !last.payload.optBoolean("settle")) queue.removeLast()
        queue.addLast(message)
    }

    fun poll(): CadQueuedMessage? {
        if (inFlight) return null
        return queue.pollFirst()?.also { if (waitsForResponse(it.name)) inFlight = true }
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
