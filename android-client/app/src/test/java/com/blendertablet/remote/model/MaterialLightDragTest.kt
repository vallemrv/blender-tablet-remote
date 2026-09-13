package com.blendertablet.remote.model

import org.junit.Assert.*
import org.junit.Test

class MaterialLightDragTest {
    private class Recorder {
        val events = mutableListOf<Triple<GesturePhase, Float, Float>>()
        val drag = MaterialLightDrag().apply { onGesture = { phase, angle, energy -> events += Triple(phase, angle, energy) } }
        /** Casi todas las pruebas miran el giro; el eje vertical se comprueba aparte. */
        fun angles() = events.map { it.first to it.second }
    }

    @Test fun tapDoesNotOpenALightingSession() {
        val r = Recorder()
        r.drag.begin(.25f, .5f)
        r.drag.move(.251f, .5f, crossedSlop = false, dispatch = true)
        r.drag.end()
        assertTrue(r.events.isEmpty())
    }

    @Test fun releaseFlushesTheLastMoveWithoutSamplingTheLift() {
        val r = Recorder()
        r.drag.begin(.25f, .5f)
        r.drag.move(.5f, .5f, crossedSlop = true, dispatch = true)
        r.drag.move(.75f, .5f, crossedSlop = true, dispatch = false)
        r.drag.end()
        assertEquals(listOf(GesturePhase.BEGIN to 0f, GesturePhase.UPDATE to 90f,
            GesturePhase.UPDATE to 180f, GesturePhase.END to 0f), r.angles())
    }

    @Test fun navigationCancelsPendingMotionAndRemainingFingerCannotResumeIt() {
        val r = Recorder()
        r.drag.begin(.25f, .5f)
        r.drag.move(.5f, .5f, crossedSlop = true, dispatch = false)
        r.drag.cancel()
        r.drag.move(.75f, .5f, crossedSlop = true, dispatch = true)
        r.drag.end()
        assertEquals(listOf(GesturePhase.BEGIN to 0f, GesturePhase.CANCEL to 0f), r.angles())
        r.events.clear()
        r.drag.begin(.75f, .5f)
        r.drag.move(.5f, .5f, crossedSlop = true, dispatch = true)
        r.drag.end()
        assertEquals(GesturePhase.UPDATE to -90f, r.angles()[1])
    }

    @Test fun raisingTheFingerRaisesTheLightAndBothAxesTravelTogether() {
        val r = Recorder()
        r.drag.begin(.5f, .8f)
        // Subir el dedo (v menor) tiene que mandar energía positiva.
        r.drag.move(.5f, .3f, crossedSlop = true, dispatch = true)
        assertEquals(Triple(GesturePhase.UPDATE, 0f, .5f), r.events[1])
        r.drag.move(.75f, .9f, crossedSlop = true, dispatch = true)
        assertEquals(GesturePhase.UPDATE, r.events[2].first)
        assertEquals(90f, r.events[2].second, 1e-4f)
        assertEquals(-.1f, r.events[2].third, 1e-4f)
        // Quieto no se repite el mismo par: la luz no parpadea por ritmo de paquetes.
        r.drag.move(.75f, .9f, crossedSlop = true, dispatch = true)
        r.drag.end()
        assertEquals(listOf(GesturePhase.BEGIN, GesturePhase.UPDATE, GesturePhase.UPDATE, GesturePhase.END),
            r.events.map { it.first })
    }
}
