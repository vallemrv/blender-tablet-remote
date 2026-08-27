package com.blendertablet.remote

import com.blendertablet.remote.model.EditTool
import com.blendertablet.remote.model.Gesture
import com.blendertablet.remote.model.TransformMode
import com.blendertablet.remote.model.ToolSession
import kotlin.math.abs
import kotlin.math.pow
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * El reparto de gestos se ha equivocado ya tres veces:
 *
 *  1. La órbita estaba atada a girar dos dedos como un volante: imposible de hacer.
 *  2. Dos dedos orbitaban en vez de desplazar.
 *  3. Se elegía entre pan y zoom con un umbral, y como al arrastrar dos dedos la
 *     separación siempre varía algo, casi todo acababa siendo zoom y el paneo no
 *     llegaba a activarse nunca.
 *
 * Ahora dos dedos hacen las dos cosas a la vez y no hay nada que clasificar. Estas
 * pruebas fijan las decisiones que quedan: la ganancia del pellizco y la zona muerta.
 *
 * Se replica el cálculo en vez de instanciar la View porque `MotionEvent` no existe
 * en la JVM de los tests unitarios.
 */
private const val ZOOM_GAIN = 0.55f
private const val ZOOM_DEADZONE = 0.004f

private fun zoomFactor(spanRatio: Float): Float = spanRatio.pow(ZOOM_GAIN)
private fun zoomApplies(factor: Float): Boolean = abs(factor - 1f) > ZOOM_DEADZONE

class GestureMappingTest {

    @Test
    fun `knife y bisect no convierten el arrastre de un dedo en tool nudge`() {
        assertTrue(!ToolSession(active = true, tool = EditTool.KNIFE).acceptsViewportNudge)
        assertTrue(!ToolSession(active = true, tool = EditTool.BISECT).acceptsViewportNudge)
    }

    @Test
    fun `las previews parametricas conservan el nudge del viewport`() {
        val nudged = listOf(
            EditTool.EXTRUDE,
            EditTool.BEVEL,
            EditTool.INSET,
            EditTool.SUBDIVIDE,
            EditTool.LOOP_CUT,
            EditTool.BRIDGE_EDGE_LOOPS,
        )
        nudged.forEach { tool ->
            assertTrue("$tool debe aceptar nudge", ToolSession(active = true, tool = tool).acceptsViewportNudge)
        }
        assertTrue(!ToolSession(active = false, tool = EditTool.EXTRUDE).acceptsViewportNudge)
    }

    @Test
    fun `el pellizco es mas suave que el movimiento crudo de los dedos`() {
        // Separar los dedos un 50% no debe acercar la camara un 50%.
        val raw = 1.5f
        val applied = zoomFactor(raw)
        assertTrue("$applied deberia quedarse corto respecto a $raw", applied < raw)
        assertTrue("pero debe seguir acercando", applied > 1f)
    }

    @Test
    fun `juntar y separar son simetricos`() {
        // Separar al doble y volver a juntar a la mitad debe dejar la escala igual.
        val ida = zoomFactor(2f)
        val vuelta = zoomFactor(0.5f)
        assertEquals(1f, ida * vuelta, 1e-4f)
    }

    @Test
    fun `el temblor de la mano no dispara zoom`() {
        // Un 0,2% de variacion entre dedos es ruido, no intencion.
        assertTrue(!zoomApplies(zoomFactor(1.002f)))
    }

    @Test
    fun `un pellizco de verdad si dispara zoom`() {
        assertTrue(zoomApplies(zoomFactor(1.05f)))
    }

    @Test
    fun `sin sesion abierta un dedo orbita en vez de quedarse muerto`() {
        assertEquals(Gesture.ORBIT, dragGesture(session = null))
    }

    /**
     * Con una transformación abierta el arrastre la alimenta a ella. El servidor
     * ignora el nombre del gesto y usa el modo que fijó `transform.begin`, pero se
     * manda el que corresponde para que el registro del protocolo se lea claro.
     */
    @Test
    fun `con una sesion abierta el arrastre la alimenta`() {
        assertEquals(Gesture.MOVE, dragGesture(TransformMode.MOVE))
        assertEquals(Gesture.ROTATE, dragGesture(TransformMode.ROTATE))
        assertEquals(Gesture.SCALE, dragGesture(TransformMode.SCALE))
    }

    /**
     * Las herramientas paramétricas no viajan por el canal de gestos: el dedo empuja
     * su parámetro con `tool.nudge`, que es un comando. Si alguien añadiera un gesto
     * `extrude`, el servidor lo rechazaría con "Unknown gesture".
     */
    @Test
    fun `extrude bevel inset y subdivide no son gestos`() {
        val gestures = Gesture.entries.map { it.name }
        for (tool in EditTool.entries) {
            assertNull(
                "${tool.wire} no puede ser un gesto del protocolo",
                gestures.find { it == tool.wire },
            )
        }
    }

    /** Mismo reparto que MainViewModel.toolGesture. */
    private fun dragGesture(session: TransformMode?): Gesture = when (session) {
        null -> Gesture.ORBIT
        TransformMode.MOVE -> Gesture.MOVE
        TransformMode.ROTATE -> Gesture.ROTATE
        TransformMode.SCALE -> Gesture.SCALE
    }
}
