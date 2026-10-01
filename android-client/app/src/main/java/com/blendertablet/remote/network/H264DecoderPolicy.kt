package com.blendertablet.remote.network

import java.util.ArrayDeque

internal data class H264AccessUnit(
    val bytes: ByteArray,
    val presentationTimeUs: Long,
    val keyframe: Boolean,
    val config: Boolean = false,
    val sequence: Long,
)

/** Bounded before posting to the codec thread; a lost reference abandons the whole GOP. */
internal class H264DecoderPolicy(private val capacity: Int = 6, private val maxAgeNs: Long = 150_000_000L) {
    private data class Pending(val unit: H264AccessUnit, val receivedNs: Long)
    private val pending = ArrayDeque<Pending>()
    var generation = 0L
        private set
    private var waitingForKeyframe = true
    private var lastSequence: Long? = null
    private var resetRequired = false

    init { require(capacity > 0 && maxAgeNs > 0) }

    @Synchronized fun restart(): Long {
        generation++
        pending.clear()
        waitingForKeyframe = true
        lastSequence = null
        resetRequired = false
        return generation
    }

    @Synchronized fun offer(epoch: Long, unit: H264AccessUnit, nowNs: Long): Boolean {
        if (epoch != generation) return false
        if (lastSequence?.let { unit.sequence != ((it + 1) and 0xffffffffL) } == true ||
            pending.size >= capacity || expired(nowNs)) abandonGop()
        lastSequence = unit.sequence
        if (waitingForKeyframe && !unit.keyframe && !unit.config) return false
        if (unit.keyframe) waitingForKeyframe = false
        pending.addLast(Pending(unit, nowNs))
        return true
    }

    @Synchronized fun abandonGop() {
        pending.clear()
        waitingForKeyframe = true
        resetRequired = true
    }

    @Synchronized fun prepare(nowNs: Long): Boolean {
        if (expired(nowNs)) abandonGop()
        val reset = resetRequired
        resetRequired = false
        return reset
    }

    @Synchronized fun peek(): H264AccessUnit? = pending.peekFirst()?.unit
    @Synchronized fun remove(): H264AccessUnit = pending.removeFirst().unit
    @Synchronized fun isCurrent(epoch: Long): Boolean = epoch == generation
    private fun expired(nowNs: Long) = pending.peekFirst()?.let { nowNs - it.receivedNs > maxAgeNs } == true
}
