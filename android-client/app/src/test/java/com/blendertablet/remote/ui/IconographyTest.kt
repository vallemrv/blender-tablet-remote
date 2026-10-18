package com.blendertablet.remote.ui

import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.VectorPath
import com.blendertablet.remote.model.ActionId
import com.blendertablet.remote.model.AddCategory
import com.blendertablet.remote.model.EditTool
import com.blendertablet.remote.model.SelectionMode
import com.blendertablet.remote.model.SnapType
import org.junit.Assert.*
import org.junit.Test

class IconographyTest {
    private fun drawing(icon: ImageVector) = (icon.root[0] as VectorPath).pathData

    @Test fun originalDrawingsParseAndDifferentIntentionsHaveDifferentGeometry() {
        val drawings = StudioIcons.glyphs.keys.map { id ->
            val vector = StudioIcons[id]
            assertEquals(24f, vector.viewportWidth)
            assertEquals(24f, vector.viewportHeight)
            drawing(vector).also { assertTrue("Dibujo vacío: $id", it.isNotEmpty()) }
        }
        assertEquals("No basta con renombrar el mismo dibujo", drawings.size, drawings.toSet().size)
        AddCategory.entries.forEach { assertNotEquals(AppIcons.Fallback, AppIcons.addCategory(it)) }
        EditTool.entries.forEach { assertNotEquals(AppIcons.Fallback, AppIcons.editTool(it)) }
        SnapType.entries.forEach { assertNotEquals(AppIcons.Fallback, AppIcons.snap(it)) }
    }

    @Test fun formerlyAmbiguousControlsHaveDistinctDrawings() {
        val controls = listOf(
            AppIcons.Move, AppIcons.gizmo, AppIcons.Rotate, AppIcons.Scale, AppIcons.Reset,
            AppIcons.Frame, AppIcons.localView(false), AppIcons.ModeObject, AppIcons.Views,
            AppIcons.Wireframe, AppIcons.Proportional, AppIcons.Modifiers, AppIcons.EditShortcuts,
            AppIcons.editCatalog("KNIFE"), AppIcons.editCatalog("BISECT"),
            AppIcons.editCatalog("CONNECT_VERTICES"), AppIcons.editCatalog("SELECT_SHORTEST_PATH"),
            AppIcons.editCatalog("MAKE_EDGE_FACE"), AppIcons.editCatalog("INSET"),
            AppIcons.action(ActionId.TOOL_CIRCLE), AppIcons.action(ActionId.TOOL_BOX),
        ) + SelectionMode.entries.map(AppIcons::selectionMode) + SnapType.entries.map(AppIcons::snap)
        assertEquals(controls.size, controls.map(::drawing).toSet().size)
    }

    @Test fun menusAndRailsUseTheActualToolAndVariant() {
        assertSame(AppIcons.editTool(EditTool.KNIFE), AppIcons.toolbarVariant("CUT", "KNIFE"))
        assertSame(AppIcons.editTool(EditTool.BISECT), AppIcons.toolbarVariant("CUT", "BISECT"))
        assertNotEquals(drawing(AppIcons.toolbarVariant("CUT", "KNIFE")), drawing(AppIcons.toolbarVariant("CUT", "BISECT")))
        val extrusions = listOf("REGION", "CURSOR", "MANIFOLD", "ALONG_NORMALS", "INDIVIDUAL")
            .map { drawing(AppIcons.toolbarVariant("EXTRUDE", it)) }
        assertEquals(extrusions.size, extrusions.toSet().size)
        assertNotEquals(drawing(AppIcons.toolbarVariant("INSET", "REGION")), drawing(AppIcons.toolbarVariant("INSET", "INDIVIDUAL")))
        for (id in listOf(ActionId.SELECT_LOOP, ActionId.SELECT_RING, ActionId.SELECT_LINKED)) {
            assertSame(AppIcons.action(id), AppIcons.editCatalog(id.name))
        }
        assertSame(AppIcons.editCatalog("BEVEL"), AppIcons.modifier("BEVEL"))
        assertSame(AppIcons.editCatalog("EXTRUDE"), AppIcons.cad("EXTRUDE"))
    }
}
