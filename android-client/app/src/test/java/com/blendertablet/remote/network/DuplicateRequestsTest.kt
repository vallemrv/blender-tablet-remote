package com.blendertablet.remote.network

import com.blendertablet.remote.model.TransformMode
import org.junit.Assert.*
import org.junit.Test

class DuplicateRequestsTest {
    @Test fun eachReplyUsesItsOwnChoiceEvenWhenRepliesArriveOutOfOrder() {
        val requests = DuplicateRequests()
        val move = Any(); val rotate = Any()
        requests.register(move, TransformMode.MOVE)
        requests.register(rotate, TransformMode.ROTATE)
        requests.sent(move, "move"); requests.sent(rotate, "rotate")
        assertEquals(TransformMode.ROTATE, requests.consume(requests.finish("rotate", true)!!))
        assertEquals(TransformMode.MOVE, requests.consume(requests.finish("move", true)!!))
        assertNull(requests.finish("rotate", true))
    }

    @Test fun failuresAndEmptyDuplicatesNeverTransformTheOriginal() {
        val requests = DuplicateRequests(); val payload = Any()
        requests.register(payload, TransformMode.ROTATE); requests.sent(payload, "failed")
        assertNull(requests.finish("failed", false))
        assertNull(requests.finish("failed", true))
        assertNull(requests.finish("unrelated", true))
    }

    @Test fun changingInteractionRetiresQueuedSentAndAlreadyEmittedPlacement() {
        val requests = DuplicateRequests()
        val queued = Any(); val sent = Any(); val emitted = Any()
        for (payload in listOf(queued, sent, emitted)) requests.register(payload, TransformMode.ROTATE)
        requests.sent(sent, "sent"); requests.sent(emitted, "emitted")
        val event = requests.finish("emitted", true)!!
        requests.retire()
        requests.sent(queued, "late")
        assertNull(requests.finish("late", true))
        assertNull(requests.finish("sent", true))
        assertNull(requests.consume(event))
    }
}
