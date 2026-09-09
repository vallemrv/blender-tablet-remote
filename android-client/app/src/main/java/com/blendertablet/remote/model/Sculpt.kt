package com.blendertablet.remote.model

/** Brush radius is a fraction of video height, independent of tablet resolution. */
data class SculptBrush(val id: String, val label: String, val icon: String = id)
data class SculptState(
    val available: Boolean = false,
    val active: Boolean = false,
    val brush: String = "DRAW",
    val radius: Float = .04f,
    val radiusMeters: Double? = null,
    val strength: Float = .5f,
    val pressureStrength: Boolean = true,
    val pressureSize: Boolean = false,
    val symmetryX: Boolean = true,
    val symmetryY: Boolean = false,
    val symmetryZ: Boolean = false,
    val dyntopoEnabled: Boolean = false,
    val dyntopoDetail: Float = 12f,
    val multiresName: String? = null,
    val multiresLevel: Int = 0,
    val multiresTotalLevels: Int = 0,
    val brushes: List<SculptBrush> = emptyList(),
)

data class SculptPoint(val u: Float, val v: Float, val pressure: Float, val time: Double) {
    fun wire(): Map<String, Any> = mapOf("u" to u, "v" to v, "pressure" to pressure, "time" to time)
}

/** Preserves pressure zero and historical path samples; UP never adds a new sample. */
class SculptSamples(private val capacity: Int = 64) {
    private val pending = ArrayList<SculptPoint>()
    private var lastTime = Double.NEGATIVE_INFINITY
    val full: Boolean get() = pending.size >= capacity
    fun add(u: Float, v: Float, pressure: Float, time: Double): Boolean {
        if (!u.isFinite() || !v.isFinite() || !time.isFinite() || time <= lastTime || full) return false
        lastTime = time
        pending += SculptPoint(u.coerceIn(0f, 1f), v.coerceIn(0f, 1f),
            if (pressure.isFinite()) pressure.coerceIn(0f, 1f) else 0f, time)
        return true
    }
    fun drain(): List<SculptPoint> = pending.toList().also { pending.clear() }
    fun clear() { pending.clear(); lastTime = Double.NEGATIVE_INFINITY }
}
