package com.blendertablet.remote.network

import com.blendertablet.remote.model.TransformMode
import java.util.IdentityHashMap

/** La intención viaja con la petición, incluso si espera en la cola de transporte. */
internal class DuplicateRequests {
    data class Placement(val mode: TransformMode, val generation: Long)
    private var generation = 0L
    private val queued = IdentityHashMap<Any, Placement>()
    private val sent = mutableMapOf<String, Placement>()

    @Synchronized fun register(payload: Any, mode: TransformMode) {
        queued[payload] = Placement(mode, generation)
    }
    @Synchronized fun sent(payload: Any, id: String) {
        queued.remove(payload)?.let { sent[id] = it }
    }
    @Synchronized fun finish(id: String, created: Boolean): Placement? =
        sent.remove(id)?.takeIf { created && it.generation == generation }
    @Synchronized fun consume(placement: Placement): TransformMode? =
        placement.mode.takeIf { placement.generation == generation }
    @Synchronized fun retire() {
        generation++
        queued.clear()
        sent.clear()
    }
}
