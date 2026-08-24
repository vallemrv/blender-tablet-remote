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
}
