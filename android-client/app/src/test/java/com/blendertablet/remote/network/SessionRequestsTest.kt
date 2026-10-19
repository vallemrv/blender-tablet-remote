package com.blendertablet.remote.network

import org.junit.Assert.*
import org.junit.Test

class SessionRequestsTest {
    @Test fun switchingToolsRejectsOldBeginNudgeAndCancelReplies() {
        val requests = SessionRequests()
        requests.sent("begin-cut")
        requests.sent("nudge-cut")
        requests.retire()
        requests.sent("cancel-cut")
        requests.retire()
        requests.sent("begin-bevel")
        assertFalse(requests.accept("begin-cut"))
        assertFalse(requests.accept("nudge-cut"))
        assertTrue(requests.accept("begin-bevel"))
        assertFalse(requests.accept("cancel-cut"))
    }

    @Test fun backgroundAndModeChangesDiscardRepliesEvenBeforeBeginWasAcknowledged() {
        val requests = SessionRequests()
        requests.sent("begin")
        requests.retire()
        assertFalse(requests.accept("begin"))
        requests.sent("cancel")
        assertTrue(requests.accept("cancel"))
        assertFalse(requests.accept("cancel"))
        requests.retire()
        requests.sent("new-tool")
        assertTrue(requests.accept("new-tool"))
    }
}
