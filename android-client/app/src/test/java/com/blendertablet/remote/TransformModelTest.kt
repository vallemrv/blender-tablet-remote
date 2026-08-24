package com.blendertablet.remote

import com.blendertablet.remote.model.AddObject
import com.blendertablet.remote.model.MoveSteps
import com.blendertablet.remote.model.RotateSteps
import com.blendertablet.remote.model.SnapAction
import com.blendertablet.remote.model.SnapGroup
import com.blendertablet.remote.model.TransformMode
import com.blendertablet.remote.model.stepsFor
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Guarda el contrato con el backend que no se puede comprobar compilando: los
 * nombres de estos enums viajan tal cual por el protocolo.
 */
class TransformModelTest {
    @Test
    fun `todos los modos tienen incrementos`() {
        for (mode in TransformMode.entries) {
            assertTrue("$mode sin incrementos", stepsFor(mode).isNotEmpty())
            assertTrue("$mode con incremento no positivo", stepsFor(mode).all { it.step > 0 })
        }
    }

    @Test
    fun `los incrementos de mover están en metros`() {
        // La etiqueta se lee en mm/cm/m pero por el cable van metros, que es la
        // unidad de Blender. Confundirlos movería mil veces de más.
        assertEquals(0.001, MoveSteps.first { it.label == "1 mm" }.step, 1e-12)
        assertEquals(1.0, MoveSteps.first { it.label == "1 m" }.step, 1e-12)
    }

    @Test
    fun `los incrementos de rotar están en radianes`() {
        assertEquals(Math.toRadians(45.0), RotateSteps.first { it.label == "45°" }.step, 1e-12)
    }

    @Test
    fun `los incrementos van de menor a mayor`() {
        for (mode in TransformMode.entries) {
            val steps = stepsFor(mode).map { it.step }
            assertEquals("$mode desordenado", steps.sorted(), steps)
        }
    }

    @Test
    fun `cada grupo de snap tiene entradas y comandos únicos`() {
        for (group in SnapGroup.entries) {
            assertTrue("$group vacío", SnapAction.of(group).isNotEmpty())
        }
        val commands = SnapAction.entries.map { it.command }
        assertEquals("hay comandos de snap repetidos", commands.distinct(), commands)
        assertTrue(SnapAction.entries.all { it.command.startsWith("snap.") })
    }

    @Test
    fun `no hay dos objetos con el mismo nombre en una categoría`() {
        // El nombre del enum viaja como `primitive`; dos etiquetas iguales dentro de
        // la misma categoría harían el menú ambiguo.
        for (category in AddObject.entries.groupBy { it.category }) {
            val labels = category.value.map { it.label }
            assertEquals("etiquetas repetidas en ${category.key}", labels.distinct(), labels)
        }
    }
}
