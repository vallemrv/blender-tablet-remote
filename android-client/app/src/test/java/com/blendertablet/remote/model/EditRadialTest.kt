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
            val bar=SelectionBar.actionsFor(BlenderMode.EDIT)
            assertTrue(main.intersect(bar.toSet()).isEmpty())
            assertEquals(bar.size,bar.toSet().size)
            assertEquals(selected && mode!=SelectionMode.VERTEX,
                SelectionBar.enabled(ActionId.SELECT_RING,mode,selected))
            assertEquals(selected,SelectionBar.enabled(ActionId.SELECT_LINKED,mode,selected))
            assertTrue(SelectionBar.enabled(ActionId.SELECT_ALL,mode,selected))
        }
    }

    @Test fun objectBarLeavesTheRadialWithoutShapes() {
        for (hit in listOf(false,true)) for (selected in listOf(false,true)) {
            val context=TouchContext(mode=BlenderMode.OBJECT,hit=hit,objectSelected=hit,hasSelection=selected)
            val main=RadialMenu.actionsFor(context)
            assertTrue(main.intersect(SelectionBar.actionsFor(BlenderMode.OBJECT).toSet()).isEmpty())
        }
        assertEquals(listOf(ActionId.SELECT_ALL,ActionId.SELECT_INVERT,ActionId.TOOL_BOX,ActionId.TOOL_CIRCLE),
            SelectionBar.actionsFor(BlenderMode.OBJECT))
    }
}
