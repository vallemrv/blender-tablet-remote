package com.blendertablet.remote.ui

import com.blendertablet.remote.model.GesturePhase
import org.junit.Assert.*
import org.junit.Test

class F2TouchGestureTest {
    @Test fun armedF2KeepsItsOwnInputAndIconWithoutParametricNudges() {
        val session=com.blendertablet.remote.network.StateParser.toolSession(org.json.JSONObject("""{"tool":"F2","armed":true,"active":false,"input":"F2_DRAW"}"""))
        assertEquals(com.blendertablet.remote.model.EditTool.F2,session.tool)
        assertTrue(session.armed);assertFalse(session.acceptsViewportNudge)
        assertNotEquals(AppIcons.Fallback,AppIcons.toolbarVariant("F2","F2"))
    }

    @Test fun releaseConfirmsOnlyTheLastSentCandidate() {
        val events=mutableListOf<Triple<GesturePhase,Float,Float>>()
        val gesture=F2TouchGesture { phase,u,v -> events.add(Triple(phase,u,v)) }
        gesture.begin(.1f,.2f);gesture.move(.4f,.5f);gesture.end();gesture.end()
        assertEquals(listOf(GesturePhase.BEGIN,GesturePhase.UPDATE,GesturePhase.END),events.map { it.first })
        assertEquals(Triple(GesturePhase.END,.4f,.5f),events.last())
    }
    @Test fun navigationCancellationCannotCreateOnRelease() {
        val phases=mutableListOf<GesturePhase>()
        val gesture=F2TouchGesture { phase,_,_ -> phases.add(phase) }
        gesture.begin(.1f,.2f);gesture.cancel();gesture.move(.8f,.9f);gesture.end()
        assertEquals(listOf(GesturePhase.BEGIN,GesturePhase.CANCEL),phases)
        gesture.begin(.2f,.3f);gesture.end()
        assertEquals(GesturePhase.END,phases.last())
    }
}
