package com.blendertablet.remote.model

import org.junit.Assert.*
import org.junit.Test

class LiveObjectPropertiesTest {
    private fun snapshot(id: String = "image", revision: String = "r1") =
        ObjectProperties(id, "Imagen", revision, emptyList(), emptyMap(), "")

    @Test fun rapidChangesCoalesceAndWaitForTheAcknowledgedRevision() {
        val q = LiveObjectProperties()
        q.offer("image", mapOf("opacity" to .1), "a")
        assertEquals("r1", q.next(snapshot())!!.revision)
        q.offer("image", mapOf("opacity" to .2), "b")
        q.offer("image", mapOf("opacity" to .3, "rotation_x" to 90.0), "c")
        assertNull(q.next(snapshot()))
        q.acknowledge(true)
        val next = q.next(snapshot(revision = "r2"))!!
        assertEquals(mapOf("opacity" to .3, "rotation_x" to 90.0), next.values)
        assertEquals("r2", next.revision)
        assertEquals("c", next.token)
    }

    @Test fun failureDiscardsPendingChangesAndNamesTheLatestLocalValue() {
        val q = LiveObjectProperties()
        q.offer("image", mapOf("location_x" to 1.0), "a")
        q.next(snapshot())
        q.offer("image", mapOf("location_x" to 2.0), "b")
        assertEquals("b", q.acknowledge(false))
        assertNull(q.next(snapshot(revision = "r2")))
        assertFalse(q.inFlight)
    }

    @Test fun changingObjectOrDisconnectingCannotReplayOldUpdates() {
        val q = LiveObjectProperties()
        q.offer("image", mapOf("opacity" to .3), "a")
        assertNull(q.next(snapshot(id = "mesh")))
        assertNull(q.next(snapshot()))
        q.offer("image", mapOf("opacity" to .3), "b")
        q.next(snapshot())
        q.clear()
        assertFalse(q.inFlight)
        assertNull(q.next(snapshot()))
    }

    @Test fun undoDiscardsUnsentValuesWithoutReplayingThemAfterTheCurrentReply() {
        val q = LiveObjectProperties()
        q.offer("image", mapOf("opacity" to .1), "a")
        q.next(snapshot())
        q.offer("image", mapOf("opacity" to .2), "b")
        assertEquals("b", q.discardPending())
        assertTrue(q.inFlight)
        q.acknowledge(true)
        assertNull(q.next(snapshot(revision = "r2")))
    }

    @Test fun incompleteTypingNeverBecomesALiveChangeAndDegreesStayDegrees() {
        val angle = ObjectPropertyField("rotation_x", "X", "Rotación", "number", "angle")
        for (text in listOf("", "-", "+", "1.", "2,", "4*")) {
            assertNull(liveObjectPropertyNumber(text, angle, LengthUnit.MILLIMETERS))
        }
        assertEquals(90.0, liveObjectPropertyNumber("90", angle, LengthUnit.MILLIMETERS)!!, 0.0)
        assertEquals(0.0, liveObjectPropertyNumber("0", angle, LengthUnit.METERS)!!, 0.0)
    }
}
