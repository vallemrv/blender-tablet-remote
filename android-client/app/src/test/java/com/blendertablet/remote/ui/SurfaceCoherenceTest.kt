package com.blendertablet.remote.ui

import com.blendertablet.remote.model.*
import java.io.File
import org.junit.Assert.*
import org.junit.Test

class SurfaceCoherenceTest {
    private fun source(name: String) = File(System.getProperty("btr.repoRoot"),
        "android-client/app/src/main/java/com/blendertablet/remote/ui/$name.kt").readText()

    /** Norma de controles: la pulsación larga solo ofrece «más opciones». */
    @Test fun longPressOnlyLivesInRailVariantsRadialAndMenus() {
        val allowed = setOf("ActiveToolRail.kt", "QuickMenu.kt", "InputSurface.kt", "BlenderTabletApp.kt")
        val dir = File(System.getProperty("btr.repoRoot"), "android-client/app/src/main/java/com/blendertablet/remote")
        val offenders = dir.walkTopDown().filter { it.extension == "kt" && it.name !in allowed }
            .filter { f -> Regex("""combinedClickable|onLongClick|onLongPress""").containsMatchIn(f.readText()) }
            .map { it.name }.toList()
        assertEquals(emptyList<String>(), offenders)
        // El número solo «agarra» al mantener: restablecer es doble toque y nunca al soltar quieto.
        val scrub = source("ScrubNumber")
        assertTrue(scrub.contains("doubleTapTimeoutMillis"))
        assertFalse(scrub.contains("RESET"))
        // Los botones con variantes llevan la marca triangular de «más opciones».
        assertTrue(source("ActiveToolRail").contains("MoreOptionsMark(selected)"))
    }

    @Test fun radialCannotRepeatSelectionControlsInObjectOrEdit() {
        val selection = EditSelectionBar.actions.toSet() + setOf(ActionId.SELECT_UNDER, ActionId.SELECT_ADD_UNDER,
            ActionId.SELECT_MORE, ActionId.SELECT_LESS)
        for (mode in listOf(BlenderMode.OBJECT, BlenderMode.EDIT)) for (hit in listOf(false,true))
            for (selected in listOf(false,true)) {
                val actions = RadialMenu.actionsFor(TouchContext(mode=mode, hit=hit, objectSelected=selected, hasSelection=selected))
                assertTrue("$mode: radial duplicates selection", actions.intersect(selection).isEmpty())
                assertEquals(actions.size,actions.toSet().size)
            }
    }
    /** Norma: el pie de Edición usa iconos de 48 dp; la letra de Blender es solo una marca. */
    @Test fun footerEditKeysAreIconsAt48dpWithoutLetterLabels() {
        val footer = source("ViewFooter")
        val numKeys = Regex("""NumKey\("([^"]*)"""").findAll(footer).map { it.groupValues[1] }.toList()
        assertTrue("NumKey solo para el teclado numérico: $numKeys", numKeys.all { it.length == 1 && it[0].isDigit() })
        val edit = footer.substringAfter("private fun EditKeys(").substringBefore("private val KeyGap")
        assertFalse(edit.contains("NumKey("))
        for (abbreviation in listOf("\"Ext\"", "\"Int\"", "\"Vol\"")) assertFalse(footer.contains(abbreviation))
        assertFalse(footer.contains("38.dp"))
        assertTrue(footer.contains("private val KeyGap = 8.dp"))
    }

    @Test fun footerInventoryComesFromRenderedCallbacksAndIsExcludedFromRadial() {
        val footer = source("ViewFooter")
        val rendered = Regex("onAction\\(EditFooterAction\\.(\\w+)\\)").findAll(footer)
            .map { EditFooterAction.valueOf(it.groupValues[1]) }.toSet()
        assertFalse(EditFooterAction.KNIFE in rendered)
        assertEquals(EditFooterCatalog.ids, rendered.mapNotNull(EditFooterCatalog::id).toSet())
        assertTrue(source("BlenderTabletApp").contains("RADIAL_TOP_LEVEL_CATALOG_IDS + EditFooterCatalog.ids"))
        assertFalse(footer.contains("onClick = onMore"));assertFalse(footer.contains("onClick = onLess"))
    }
    @Test fun topToolbarHasOnlyTheGeneralViewControls() {
        val top = source("TopToolbar").substringAfter("fun TopToolbar(").substringBefore("fun ModeRail(")
        val icons = Regex("AppIcons\\.(\\w+)").findAll(top).map { it.groupValues[1] }.toList()
        // Normales se añadió por petición del usuario junto a Wireframe.
        assertEquals(setOf("Wireframe","Normals","Undo","Redo","visibility"),icons.toSet())
        assertEquals(5,icons.size)
        assertFalse(top.contains("CadTopActions"));assertFalse(top.contains("MaterialTopActions"))
    }
    @Test fun cadAndMaterialsDoNotRepeatRadialOrViewActionsInTheirInspectorsAndTrays() {
        val cad = source("CadWorkspace")
        for (command in listOf("cad.feature.delete","cad.entity.delete","cad.sketch.delete","cad.points.weld"))
            assertFalse("$command belongs to radial",cad.contains(command))
        assertFalse(cad.contains("Acciones del nodo"))
        assertEquals(1, Regex("CadAction\\(\"DELETE\"").findAll(cad).count()) // only constraint list
        assertTrue(cad.contains("onClick = delete"))
        assertTrue(cadConstraintGroups(cadDimensionTypes.toList()).isEmpty())
        val material = source("MaterialWorkspace")
        assertFalse(material.contains("AppIcons.material(\"ISOLATE\")"))
        assertFalse(material.contains("AppIcons.material(\"SELECT\")"))
        assertFalse(source("ObjectPropertiesTray").contains("fields.firstOrNull { it.id == \"visible\" }"))
        val app=source("BlenderTabletApp")
        assertTrue(app.contains("cadRadialActions"))
        assertTrue(app.contains("contextKeys = if (state.blender.cad.workspace"))
    }
    @Test fun commonControlsKeepTheirZonesAndCadUsesOneLine() {
        val app = source("BlenderTabletApp")
        val rail = app.substringAfter("private fun RailContent(").substringBefore("private fun deleteWhat")
        assertFalse(rail.contains("AppIcons.SelectTool"))
        assertFalse(rail.contains("AppIcons.Debug"))
        assertTrue(source("MenuBar").contains("AppIcons.Debug"))
        assertFalse(source("MenuBar").contains("onReferences"))
        val board = app.substringAfter("// Última capa del workspace")
        assertTrue(board.contains("ReferencePanel("))
        assertTrue(board.contains("Modifier.zIndex(100f)"))
        assertTrue(app.indexOf("// Última capa del workspace") > app.indexOf("TopToolbar("))
        assertTrue(board.contains("boardId = state.blender.sceneScale.referenceBoardId"))
        val modes = source("TopToolbar").substringAfter("fun ModeRail(").substringBefore("fun SelectionHelperRail(")
        assertFalse(modes.contains("Object Mode")); assertFalse(modes.contains("Edit Mode"))
        assertTrue(modes.contains("AppIcons.ModeCad"))
        assertFalse(modes.contains("PillButton(\"CAD\""))
        val cad = source("CadWorkspace")
        assertTrue(cad.contains("SingleLineTray("))
        // La ayuda CAD vive en el hover del rótulo y en «⋯ Más»; los errores, en el aviso fijo.
        assertTrue(cad.contains("alert = listOfNotNull(cad.error, review)"))
        assertFalse(cad.contains("PillButton(if (cad.error != null) \"Revisar\" else \"Ayuda\")"))
        assertFalse(cad.contains("top = 120.dp, bottom = 160.dp"))
    }

}
