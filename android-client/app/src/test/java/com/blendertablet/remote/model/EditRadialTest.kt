package com.blendertablet.remote.model

import org.junit.Assert.*
import org.junit.Test

class EditRadialTest {
    @Test fun selectedWireObjectKeepsPlacementAndApplyWhenLongPressMissesItsContour() {
        val selected = TouchContext(mode=BlenderMode.OBJECT,hasSelection=true)
        val centre = RadialMenu.actionsFor(selected.copy(hit=false))
        val contour = RadialMenu.actionsFor(selected.copy(hit=true,objectSelected=true))
        assertTrue(ActionId.PLACE_OBJECT in centre)
        assertTrue(ActionId.PLACE_OBJECT in contour)
        assertTrue(ActionId.APPLY_TRANSFORMS in centre)
        assertTrue(ActionId.APPLY_TRANSFORMS in contour)
        assertTrue(centre.size <= RadialMenu.MAX_ACTIONS)
        assertEquals(ActionId.DELETE,centre.last())
        assertFalse(ActionId.PLACE_OBJECT in RadialMenu.actionsFor(selected.copy(hasSelection=false)))
        assertFalse(ActionId.APPLY_TRANSFORMS in RadialMenu.actionsFor(selected.copy(hasSelection=false)))
        assertFalse(ActionId.APPLY_TRANSFORMS in RadialMenu.actionsFor(selected.copy(hit=true,objectSelected=false)))
        assertTrue(centre.intersect(EditSelectionBar.actions.toSet()).isEmpty())
    }

    @Test fun editMeshRadialOffersAddingAnotherMesh() {
        val mesh = RadialMenu.actionsFor(TouchContext(mode = BlenderMode.EDIT, activeObjectType = "MESH"))
        assertEquals(ActionId.EDIT_MESH_TOOLS, mesh.first())
        assertTrue(ActionId.ADD_OBJECT in mesh)
        assertFalse(ActionId.ADD_OBJECT in RadialMenu.actionsFor(TouchContext(mode = BlenderMode.EDIT, activeObjectType = "CURVE")))
        assertTrue(RadialMenu.actionsFor(TouchContext(mode = BlenderMode.EDIT, activeObjectType = "MESH", hasSelection = true)).size <= RadialMenu.MAX_ACTIONS)
    }

    @Test fun ringAndSimilarAreAvailableFromTheSelectionRail() {
        assertTrue(ActionId.SELECT_RING in EditSelectionBar.actions)
        assertTrue(ActionId.SELECT_SIMILAR in EditSelectionBar.actions)
        assertFalse(EditSelectionBar.enabled(ActionId.SELECT_RING, SelectionMode.VERTEX, true))
        assertTrue(EditSelectionBar.enabled(ActionId.SELECT_RING, SelectionMode.FACE, true))
        assertFalse(EditSelectionBar.enabled(ActionId.SELECT_SIMILAR, SelectionMode.FACE, false))
    }

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
