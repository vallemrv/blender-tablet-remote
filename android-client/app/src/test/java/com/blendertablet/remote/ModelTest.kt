package com.blendertablet.remote

import com.blendertablet.remote.model.BlenderState
import com.blendertablet.remote.model.LoopFalloff
import com.blendertablet.remote.model.SelectionMode
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ModelTest {
    @Test fun defaultStateStartsInVertexSelection() {
        assertEquals(SelectionMode.VERTEX, BlenderState().selectionMode)
    }

    @Test fun falloffCiclaTodosLosPerfiles() {
        var current = LoopFalloff.SMOOTH
        val seen = mutableSetOf(current)
        repeat(LoopFalloff.entries.size - 1) { current = current.next(); seen.add(current) }
        assertEquals(LoopFalloff.entries.toSet(), seen)
        assertEquals(LoopFalloff.SMOOTH, current.next())
    }

    @Test fun falloffParseEsTolerante() {
        assertEquals(LoopFalloff.SPHERE, LoopFalloff.fromWire("SPHERE"))
        assertEquals(null, LoopFalloff.fromWire("NOPE"))
        assertTrue(LoopFalloff.fromWire("linear") == null)
    }
}
