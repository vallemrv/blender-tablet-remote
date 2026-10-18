package com.blendertablet.remote.ui

import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.input.pointer.PointerEvent
import androidx.compose.ui.input.pointer.PointerEventPass
import androidx.compose.ui.input.pointer.PointerEventType
import androidx.compose.ui.input.pointer.PointerId
import androidx.compose.ui.input.pointer.PointerInputChange
import androidx.compose.ui.input.pointer.PointerType
import androidx.compose.ui.unit.IntRect
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.LayoutDirection
import org.junit.Assert.*
import org.junit.Test

class HoverHelpTest {
    @Test fun hoveringRequiresAProximityDeviceAndNeverContact() {
        for (device in listOf(PointerType.Stylus, PointerType.Eraser, PointerType.Mouse)) {
            assertTrue(isHelpHover(PointerEventType.Enter, listOf(device to false)))
            assertTrue(isHelpHover(PointerEventType.Move, listOf(device to false)))
            assertFalse(isHelpHover(PointerEventType.Move, listOf(device to true)))
            assertFalse(isHelpHover(PointerEventType.Exit, listOf(device to false)))
            assertFalse(isHelpHover(PointerEventType.Press, listOf(device to true)))
            assertFalse(isHelpHover(PointerEventType.Release, listOf(device to false)))
        }
        assertFalse(isHelpHover(PointerEventType.Move, listOf(PointerType.Touch to false)))
        assertFalse(isHelpHover(PointerEventType.Move, listOf(PointerType.Stylus to false, PointerType.Touch to true)))
    }

    @Test fun observerLeavesTapsAndRadialSiblingInputUntouched() {
        val hover = mutableListOf<Boolean>()
        val node = HoverObserverNode { hover += it }
        assertTrue(node.sharePointerInputWithSiblings())
        for (pressed in listOf(false, true)) {
            val change = PointerInputChange(PointerId(1), 100L, Offset(10f, 10f), pressed,
                90L, Offset(9f, 9f), false, isInitiallyConsumed = false, type = PointerType.Stylus)
            val event = PointerEvent(listOf(change))
            node.onPointerEvent(event, PointerEventPass.Main, IntSize(44, 44))
            assertFalse("La ayuda nunca consume el gesto", change.isConsumed)
        }
        assertEquals(listOf(true, false), hover)
        node.onCancelPointerInput()
        assertEquals(false, hover.last())
    }

    @Test fun tooltipFitsAtEachScreenEdgeAndAvoidsItsButton() {
        val position = HelpPosition(8)
        val window = IntSize(800, 600)
        val popup = IntSize(280, 120)
        for (anchor in listOf(IntRect(0, 0, 44, 44), IntRect(756, 0, 800, 44),
            IntRect(0, 556, 44, 600), IntRect(756, 556, 800, 600), IntRect(350, 270, 394, 314))) {
            val offset = position.calculatePosition(anchor, window, LayoutDirection.Ltr, popup)
            assertTrue(offset.x >= 0 && offset.x + popup.width <= window.width)
            assertTrue(offset.y >= 0 && offset.y + popup.height <= window.height)
            assertTrue(offset.y + popup.height <= anchor.top || offset.y >= anchor.bottom)
        }
    }

    @Test fun everyOriginalIconExplainsItsPurposeAndVariantsDiffer() {
        StudioIcons.glyphs.forEach { (id, glyph) ->
            assertTrue("Sin explicación: $id", IconHelp.explanation(StudioIcons[id], glyph.label).isNotBlank())
        }
        assertNotEquals(IconHelp.explanation(AppIcons.toolbarVariant("CUT", "KNIFE"), "Cuchillo"),
            IconHelp.explanation(AppIcons.toolbarVariant("CUT", "BISECT"), "Bisecar"))
        assertEquals("Activa o desactiva esta propiedad.", IconHelp.explanation(AppIcons.Checked, "Vista: activado"))
    }
}
