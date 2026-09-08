package com.blendertablet.remote.model

import org.junit.Assert.*
import org.junit.Test

class TapExtrusionGestureTest {
    @Test fun dragEndsAtLastStableSampleAndEachContactCreatesOneTramo() {
        val gesture = TapExtrusionGesture()
        gesture.begin(.2f,.3f)
        gesture.move(.6f,.7f)
        assertEquals(.6f to .7f, gesture.end())
        assertNull(gesture.end())
        gesture.begin(.8f,.9f)
        assertEquals(.8f to .9f, gesture.end())
    }
    @Test fun navigationOrToolChangeCancelsRemainderOfContact() {
        val gesture = TapExtrusionGesture()
        gesture.begin(.2f,.3f)
        gesture.cancel()
        gesture.move(.5f,.6f)
        assertNull(gesture.end())
    }
}
