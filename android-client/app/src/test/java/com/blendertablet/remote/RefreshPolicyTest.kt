package com.blendertablet.remote

import com.blendertablet.remote.network.shouldRequestSceneSnapshot
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RefreshPolicyTest {
    @Test fun idleEventRefreshesScene() {
        assertTrue(shouldRequestSceneSnapshot(false, false, false))
    }

    @Test fun modalEventsDoNotCompeteWithLiveFeedback() {
        assertFalse(shouldRequestSceneSnapshot(true, false, false))
        assertFalse(shouldRequestSceneSnapshot(false, true, false))
    }

    @Test fun pickResponseOwnsItsSnapshot() {
        assertFalse(shouldRequestSceneSnapshot(false, false, true))
    }
}
