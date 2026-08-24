package com.blendertablet.remote

import com.blendertablet.remote.model.Axis
import com.blendertablet.remote.model.Constraint
import com.blendertablet.remote.model.SnapType
import com.blendertablet.remote.model.TransformMode
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Las restricciones son el corazón de la transformación táctil: un eje se combina
 * con otro para formar un plano, y la rotación solo admite un eje a la vez. Aquí se
 * fija que la conversión ejes ↔ restricción es biunívoca y sin trampas.
 */
class TransformSettingsTest {

    @Test
    fun `la restriccion libre no tiene ejes`() {
        assertTrue(Constraint.FREE.axes.isEmpty())
    }

    @Test
    fun `cada eje simple corresponde a si mismo`() {
        assertEquals(setOf(Axis.X), Constraint.X.axes)
        assertEquals(setOf(Axis.Y), Constraint.Y.axes)
        assertEquals(setOf(Axis.Z), Constraint.Z.axes)
    }

    @Test
    fun `los planos combinan los dos ejes`() {
        assertEquals(setOf(Axis.X, Axis.Y), Constraint.XY.axes)
        assertEquals(setOf(Axis.X, Axis.Z), Constraint.XZ.axes)
        assertEquals(setOf(Axis.Y, Axis.Z), Constraint.YZ.axes)
    }

    @Test
    fun `ofAxes es la inversa de axes`() {
        for (constraint in Constraint.entries) {
            assertEquals("$constraint no es biunívoca", constraint, Constraint.ofAxes(constraint.axes))
        }
    }

    @Test
    fun `los tres ejes a la vez equivalen a libre`() {
        assertEquals(Constraint.FREE, Constraint.ofAxes(setOf(Axis.X, Axis.Y, Axis.Z)))
    }

    @Test
    fun `el orden de los ejes no importa`() {
        assertEquals(Constraint.XY, Constraint.ofAxes(setOf(Axis.Y, Axis.X)))
    }

    @Test
    fun `move y scale ofrecen los planos, rotate solo ejes simples`() {
        assertTrue(Constraint.forMode(TransformMode.MOVE).contains(Constraint.XY))
        assertTrue(Constraint.forMode(TransformMode.SCALE).contains(Constraint.XZ))
        assertFalse(Constraint.forMode(TransformMode.ROTATE).contains(Constraint.XY))
        assertFalse(Constraint.forMode(TransformMode.ROTATE).contains(Constraint.YZ))
    }

    @Test
    fun `rotar solo ofrece restricciones de cero o un eje`() {
        for (constraint in Constraint.forMode(TransformMode.ROTATE)) {
            assertTrue("$constraint no es válido para rotar", constraint.axes.size <= 1)
        }
    }

    /**
     * El snap geométrico se resuelve con un rayo hacia un vértice, arista o cara, y
     * eso solo tiene sentido desplazando: el backend responde `wrong_tool` si se pide
     * girando o escalando. La barra no debe llegar a ofrecerlo.
     */
    @Test
    fun `el snap geometrico solo existe al mover`() {
        assertTrue(SnapType.forMode(TransformMode.MOVE).contains(SnapType.VERTEX))
        for (mode in listOf(TransformMode.ROTATE, TransformMode.SCALE)) {
            for (type in SnapType.forMode(mode)) {
                assertFalse("$type no vale para $mode", type.geometric)
            }
        }
    }

    @Test
    fun `todos los modos permiten quitar el snap y cuadrar al incremento`() {
        for (mode in TransformMode.entries) {
            val options = SnapType.forMode(mode)
            assertTrue(options.contains(SnapType.NONE))
            assertTrue(options.contains(SnapType.INCREMENT))
            assertEquals("Con opciones repetidas el botón cíclico se atasca",
                options.distinct().size, options.size)
        }
    }
}
