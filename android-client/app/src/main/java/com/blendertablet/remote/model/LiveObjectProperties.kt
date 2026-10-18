package com.blendertablet.remote.model

/** Últimos valores pendientes, con una única petición en vuelo. Sin referencias a UI. */
class LiveObjectProperties {
    data class Request(val objectId: String, val revision: String, val values: Map<String, Any?>, val token: String)
    private var target: String? = null
    private var values = emptyMap<String, Any?>()
    private var token: String? = null
    var inFlight: Boolean = false
        private set

    fun offer(id: String, updates: Map<String, Any?>, nextToken: String) {
        if (target != id) values = emptyMap()
        target = id
        values = values + updates
        token = nextToken
    }
    fun next(current: ObjectProperties?): Request? {
        if (inFlight) return null
        if (current == null || current.id != target) { clear(); return null }
        if (values.isEmpty()) return null
        val next = Request(current.id, current.revision, values, token!!)
        values = emptyMap(); token = null; inFlight = true
        return next
    }
    fun acknowledge(success: Boolean): String? {
        inFlight = false
        if (success) return null
        val last = token
        clear()
        return last
    }
    fun discardPending(): String? {
        val last = token
        values = emptyMap(); token = null
        return last
    }
    fun clear() { target = null; values = emptyMap(); token = null; inFlight = false }
}

fun liveObjectPropertyNumber(text: String, field: ObjectPropertyField, unit: LengthUnit): Double? {
    val value = text.trim()
    if (value.isEmpty() || value.last() in ".,+-*/(") return null
    return objectPropertyNumber(value, field, unit)
}
