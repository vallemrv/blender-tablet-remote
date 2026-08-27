package com.blendertablet.remote

import com.blendertablet.remote.model.ActionId
import com.blendertablet.remote.model.ActionSurface
import com.blendertablet.remote.model.BlenderMode
import com.blendertablet.remote.model.RadialMenu
import com.blendertablet.remote.model.SelectionMode
import com.blendertablet.remote.model.SurfaceCatalog
import com.blendertablet.remote.model.TouchContext
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Fija el invariante "cero duplicidades": ninguna acción vive en más de una
 * superficie visible.
 *
 * La parte que de verdad protege es `el menú radial no invade otras superficies`: no
 * comprueba la tabla contra sí misma, sino contra el constructor que usa la interfaz.
 * El long click es donde más tienta duplicar, porque es cómodo "dejarlo también ahí".
 */
class SurfaceCatalogTest {

    /** Todos los contextos posibles bajo el dedo, para no probar solo el fácil. */
    private fun everyContext(): List<TouchContext> = buildList {
        for (mode in BlenderMode.entries) {
            for (selection in SelectionMode.entries) {
                for (hit in listOf(true, false)) {
                    for (selected in listOf(true, false)) {
                        for (hasSelection in listOf(true, false)) {
                            add(
                                TouchContext(
                                    mode = mode,
                                    selectionMode = selection,
                                    hit = hit,
                                    objectName = if (hit) "Cube" else null,
                                    objectSelected = hit && selected,
                                    hasSelection = hasSelection,
                                ),
                            )
                        }
                    }
                }
            }
        }
    }

    @Test
    fun `ninguna accion vive en dos superficies`() {
        assertEquals(
            "Acciones duplicadas: ${SurfaceCatalog.duplicates()}",
            emptyMap<ActionId, List<ActionSurface>>(),
            SurfaceCatalog.duplicates(),
        )
    }

    @Test
    fun `todas las acciones del catalogo tienen una superficie`() {
        val covered = SurfaceCatalog.entries.map { it.id }.toSet()
        for (id in ActionId.entries) {
            assertTrue("$id no está en el catálogo", id in covered)
        }
    }

    @Test
    fun `cada accion aparece una sola vez en el catalogo`() {
        val ids = SurfaceCatalog.entries.map { it.id }
        assertEquals(ids.distinct().size, ids.size)
    }

    @Test
    fun `el menu radial no invade otras superficies`() {
        for (context in everyContext()) {
            for (id in RadialMenu.actionsFor(context)) {
                assertEquals(
                    "$id salió en el menú radial y su sitio es ${SurfaceCatalog.surfaceOf(id)} ($context)",
                    ActionSurface.RADIAL,
                    SurfaceCatalog.surfaceOf(id),
                )
            }
        }
    }

    /** El anillo se vuelve inpulsable pasadas ~8 entradas y nunca debe salir vacío. */
    @Test
    fun `el menu radial siempre cabe en el anillo`() {
        for (context in everyContext()) {
            val actions = RadialMenu.actionsFor(context)
            assertTrue("Menú vacío en $context", actions.isNotEmpty())
            assertTrue("Menú de ${actions.size} entradas en $context", actions.size <= RadialMenu.MAX_ACTIONS)
            assertEquals("Entradas repetidas en $context", actions.distinct().size, actions.size)
        }
    }

    /**
     * Ni Loop ni Ring sin una arista de partida: el servidor respondería
     * `empty_selection`, y el plan prohíbe ofrecer lo que no se puede ejecutar.
     */
    @Test
    fun `loop y ring solo con aristas seleccionadas`() {
        for (context in everyContext()) {
            val actions = RadialMenu.actionsFor(context)
            val topology = actions.any { it == ActionId.SELECT_LOOP || it == ActionId.SELECT_RING }
            if (topology) {
                assertEquals(BlenderMode.EDIT, context.mode)
                assertEquals(SelectionMode.EDGE, context.selectionMode)
                assertTrue(context.hasSelection)
            }
        }
    }

    /** Borrar no puede salir si no hay nada que borrar. */
    @Test
    fun `borrar solo aparece con algo seleccionado`() {
        for (context in everyContext()) {
            if (ActionId.DELETE in RadialMenu.actionsFor(context)) {
                assertTrue("Borrar sin selección en $context", context.hasSelection || context.objectSelected)
            }
        }
    }

    @Test
    fun `edit ofrece borrar directamente segun el submodo activo`() {
        for (mode in SelectionMode.entries) {
            val actions = RadialMenu.actionsFor(
                TouchContext(mode = BlenderMode.EDIT, selectionMode = mode, hit = true, hasSelection = true),
            )
            assertTrue("Falta Borrar para $mode: $actions", ActionId.DELETE in actions)
            assertTrue("Falta Caja para $mode: $actions", ActionId.TOOL_BOX in actions)
            assertTrue("Falta Círculo para $mode: $actions", ActionId.TOOL_CIRCLE in actions)
            assertTrue("Menú de ${actions.size} entradas para $mode", actions.size <= RadialMenu.MAX_ACTIONS)
        }
    }

    /** Tocar un objeto ajeno a la selección ofrece engancharlo, no operarlo. */
    @Test
    fun `un objeto no seleccionado ofrece seleccionarlo`() {
        val context = TouchContext(
            mode = BlenderMode.OBJECT,
            hit = true,
            objectName = "Mesa",
            objectSelected = false,
            hasSelection = true,
        )
        val actions = RadialMenu.actionsFor(context)

        assertTrue(ActionId.SELECT_UNDER in actions)
        assertTrue(ActionId.SELECT_ADD_UNDER in actions)
        assertFalse("Borrar operaría sobre otra cosa que la tocada", ActionId.DELETE in actions)
    }

    /**
     * Agregar objetos vive solo en el vacío de Object Mode: es donde se colocan
     * cosas nuevas. En Edit Mode añadir un objeto no procede y sobre un objeto
     * ya hay qué operar.
     */
    @Test
    fun `agregar solo en object mode y en el vacio`() {
        for (context in everyContext()) {
            val hasAdd = ActionId.ADD_OBJECT in RadialMenu.actionsFor(context)
            assertEquals(
                "Agregar apareció en $context",
                BlenderMode.OBJECT == context.mode && !context.hit,
                hasAdd,
            )
        }
    }

    /**
     * La barra superior de tools (junto al ojo) es la única dueña de undo/redo y del
     * submodo de selección: salieron del rail para no duplicarse. B/C viven en el
     * long-click (RADIAL), no en la barra.
     */
    @Test
    fun `la barra superior de tools es duena de undo redo y submodo`() {
        for (id in listOf(
            ActionId.UNDO, ActionId.REDO,
            ActionId.SEL_VERTEX, ActionId.SEL_EDGE, ActionId.SEL_FACE,
            ActionId.VIEW_SHADING,
        )) {
            assertEquals("$id debería estar en TOP_TOOLS", ActionSurface.TOP_TOOLS, SurfaceCatalog.surfaceOf(id))
        }
        assertEquals(ActionSurface.RADIAL, SurfaceCatalog.surfaceOf(ActionId.TOOL_BOX))
        assertEquals(ActionSurface.RADIAL, SurfaceCatalog.surfaceOf(ActionId.TOOL_CIRCLE))
    }

    /** Object/Edit salieron del rail: viven en su propia barra de modo, junto al ojo. */
    @Test
    fun `object y edit viven en la barra de modo y no en el rail`() {
        assertEquals(ActionSurface.TOP_MODE, SurfaceCatalog.surfaceOf(ActionId.MODE_OBJECT))
        assertEquals(ActionSurface.TOP_MODE, SurfaceCatalog.surfaceOf(ActionId.MODE_EDIT))
        // Y ninguna acción de modo queda colgando en el rail.
        val rail = SurfaceCatalog.idsOf(ActionSurface.RAIL)
        assertFalse(ActionId.MODE_OBJECT in rail)
        assertFalse(ActionId.MODE_EDIT in rail)
    }
}
