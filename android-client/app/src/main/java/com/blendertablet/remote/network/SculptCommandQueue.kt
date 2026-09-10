package com.blendertablet.remote.network

import org.json.JSONArray
import org.json.JSONObject

/** All mutations/navigation behind a pending stroke retain their original order. */
internal fun isPaintStroke(name: String) = name == "sculpt.stroke" || name == "material.stroke"

internal data class SculptQueuedMessage(val name: String, val payload: JSONObject, val raw: String? = null)
internal class SculptCommandQueue {
    private val queue = java.util.ArrayDeque<SculptQueuedMessage>()
    val isEmpty: Boolean get() = queue.isEmpty()
    fun clear() = queue.clear()
    fun removeStroke(id: String) { queue.removeAll { isPaintStroke(it.name) && it.payload.optString("stroke_id") == id } }
    fun recoverStroke(id: String, name: String = "sculpt.stroke") {
        removeStroke(id)
        queue.addFirst(SculptQueuedMessage(name, JSONObject().put("phase", "cancel")
            .put("stroke_id", id).put("points", JSONArray())))
    }
    fun add(message: SculptQueuedMessage) {
        val incoming = message.payload
        if (isPaintStroke(message.name) && incoming.optString("phase") == "cancel") {
            removeStroke(incoming.optString("stroke_id"))
        }
        val last = queue.peekLast()
        if (isPaintStroke(message.name) && incoming.optString("phase") == "update" &&
            last?.name == message.name && last.payload.optString("phase") == "update" &&
            last.payload.optString("stroke_id") == incoming.optString("stroke_id")) {
            val target = last.payload.optJSONArray("points") ?: JSONArray().also { last.payload.put("points", it) }
            val points = incoming.optJSONArray("points") ?: JSONArray()
            var index = 0
            while (index < points.length() && target.length() < 128) target.put(points.get(index++))
            if (index == points.length()) return
            val rest = JSONArray()
            while (index < points.length()) rest.put(points.get(index++))
            incoming.put("points", rest)
        }
        queue.addLast(message)
    }
    fun poll(): SculptQueuedMessage? = queue.pollFirst()
}
