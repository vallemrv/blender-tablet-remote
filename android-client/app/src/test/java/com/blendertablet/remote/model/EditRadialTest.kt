package com.blendertablet.remote.model

import org.junit.Assert.*
import org.junit.Test

class EditRadialTest {
    @Test fun editSeparatesSelectionMeshAndDestructiveActions() {
        for (mode in SelectionMode.entries) for (selected in listOf(false,true)) {
            val context=TouchContext(mode=BlenderMode.EDIT,selectionMode=mode,hasSelection=selected)
            val main=RadialMenu.actionsFor(context)
            val selection=RadialMenu.selectionActions(context)
            assertEquals(listOf(ActionId.EDIT_SELECTION_TOOLS,ActionId.EDIT_MESH_TOOLS),main.take(2))
            assertEquals(selected,ActionId.DELETE in main)
            assertFalse(selection.contains(ActionId.DELETE))
            assertTrue(main.intersect(selection.toSet()).isEmpty())
            assertTrue(ActionId.SELECT_ALL in selection && ActionId.DESELECT_ALL in selection)
            assertEquals(selected && mode!=SelectionMode.VERTEX,ActionId.SELECT_RING in selection)
            assertEquals(selection.size,selection.toSet().size)
        }
    }
}
