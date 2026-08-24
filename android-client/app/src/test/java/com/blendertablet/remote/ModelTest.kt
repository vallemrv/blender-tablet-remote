package com.blendertablet.remote

import com.blendertablet.remote.model.BlenderState
import com.blendertablet.remote.model.SelectionMode
import org.junit.Assert.assertEquals
import org.junit.Test

class ModelTest {
    @Test fun defaultStateStartsInVertexSelection() {
        assertEquals(SelectionMode.VERTEX, BlenderState().selectionMode)
    }
}
