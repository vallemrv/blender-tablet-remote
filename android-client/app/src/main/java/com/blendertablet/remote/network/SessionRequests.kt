package com.blendertablet.remote.network

/** Replies from a retired interaction must not reopen it or flush its queued input. */
internal class SessionRequests {
    private var generation = 0L
    private val requests = mutableMapOf<String, Long>()

    @Synchronized fun retire() { generation++; requests.clear() }
    @Synchronized fun sent(id: String) { requests[id] = generation }
    @Synchronized fun accept(id: String): Boolean = requests.remove(id) == generation
}
