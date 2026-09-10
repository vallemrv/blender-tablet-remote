package com.blendertablet.remote.ui

import org.junit.Assert.*
import org.junit.Test

class CadNumberDraftTest {
    @Test fun rapidStepsRetainTheLatestValueWhileOldResponsesArrive() {
        val draft = CadNumberDraft()
        assertEquals(.021, draft.nudge(.02, 1000.0, .001, 1, 1e-7, 10000.0)!!, 0.0)
        assertEquals(.022, draft.nudge(.02, 1000.0, .001, 1, 1e-7, 10000.0)!!, 0.0)
        draft.acknowledge(.021)
        assertEquals(.023, draft.nudge(.021, 1000.0, .001, 1, 1e-7, 10000.0)!!, 0.0)
        draft.acknowledge(.023)
        assertNull(draft.pending)
        assertEquals(.018, draft.read(.018, 1000.0, 1e-7, 10000.0)!!, 0.0)
    }

    @Test fun millimeterDraftAndHeldStepsRemainExactInMeters() {
        val draft = CadNumberDraft()
        draft.text = "0,01"
        assertEquals(.00001, draft.read(.02, 1000.0, 1e-7, 10000.0)!!, 1e-20)
        repeat(100) { draft.nudge(.02, 1000.0, .00001, 1, 1e-7, 10000.0) }
        assertEquals(.00101, draft.pending!!, 1e-18)
        assertNull(draft.text)
    }

    @Test fun emptyOrInvalidDraftCannotSendANudge() {
        val draft = CadNumberDraft()
        for (text in listOf("", "-", "NaN", "Infinity", "0", "-2")) {
            draft.text = text
            assertNull(draft.read(.02, 1000.0, 1e-7, 10000.0))
            assertNull(draft.nudge(.02, 1000.0, .001, 1, 1e-7, 10000.0))
        }
    }

    @Test fun coordinatesAllowZeroAndNegativeValuesWhileLengthsStayPositive() {
        val position = CadNumberDraft()
        position.text = "0"
        assertEquals(-.001, position.nudge(1.0, 1000.0, .001, -1, -10000.0, 10000.0)!!, 0.0)
        val length = CadNumberDraft()
        assertEquals(1e-7, length.nudge(.0001, 1000.0, .001, -1, 1e-7, 10000.0)!!, 0.0)
    }

    @Test fun anglesUseDegreesAndUnitChangesDoNotRescaleThePendingWireValue() {
        val draft = CadNumberDraft()
        assertEquals(91.0, draft.nudge(90.0, 1.0, 1.0, 1, -359.99, 359.99)!!, 0.0)
        val distance = CadNumberDraft()
        distance.nudge(.02, 1000.0, .001, 1, 1e-7, 10000.0)
        assertEquals(.021, distance.read(.02, 100.0, 1e-7, 10000.0)!!, 0.0)
    }
}
