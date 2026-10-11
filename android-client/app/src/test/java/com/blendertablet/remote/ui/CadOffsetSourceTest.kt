package com.blendertablet.remote.ui

import com.blendertablet.remote.model.*
import org.junit.Assert.*
import org.junit.Test

class CadOffsetSourceTest {
    private val types = listOf("SLOT", "CIRCLE", "RECTANGLE")
    private val sketch = CadSketch("s", "Boceto", "XY",
        listOf(CadEntity("c", "CIRCLE", emptyMap()), CadEntity("r", "RECTANGLE", emptyMap()), CadEntity("n", "NGON", emptyMap())), emptyList())

    private fun state(vararg selection: CadSelection) =
        CadState(sketches = listOf(sketch), activeSketchId = "s", selection = selection.toList())

    @Test fun oneSupportedFigureIsTheSourceEvenFromItsParts() {
        assertEquals("c", cadOffsetSource(state(CadSelection("c")), types)?.id)
        assertEquals("r", cadOffsetSource(state(CadSelection("r", "EDGE0"), CadSelection("r", "P1")), types)?.id)
    }

    @Test fun noSelectionSeveralFiguresOrUnsupportedTypeGiveNoSource() {
        assertNull(cadOffsetSource(state(), types))
        assertNull(cadOffsetSource(state(CadSelection("c"), CadSelection("r")), types))
        assertNull(cadOffsetSource(state(CadSelection("n")), types))
    }
}
