package com.blendertablet.remote.model

import org.junit.Assert.*
import org.junit.Test

class EditRadialTest {
    @Test fun editRadialLeavesSelectionToItsBar() {
        for (mode in SelectionMode.entries) for (selected in listOf(false,true)) {
            val context=TouchContext(mode=BlenderMode.EDIT,selectionMode=mode,hasSelection=selected)
            val main=RadialMenu.actionsFor(context)
            assertEquals(ActionId.EDIT_MESH_TOOLS,main.first())
            assertEquals(selected,ActionId.DELETE in main)
            assertTrue(main.intersect(EditSelectionBar.actions.toSet()).isEmpty())
            assertEquals(EditSelectionBar.actions.size,EditSelectionBar.actions.toSet().size)
            assertEquals(selected && mode!=SelectionMode.VERTEX,
                EditSelectionBar.enabled(ActionId.SELECT_RING,mode,selected))
            assertEquals(selected,EditSelectionBar.enabled(ActionId.SELECT_LINKED,mode,selected))
            assertTrue(EditSelectionBar.enabled(ActionId.SELECT_ALL,mode,selected))
        }
    }
}
