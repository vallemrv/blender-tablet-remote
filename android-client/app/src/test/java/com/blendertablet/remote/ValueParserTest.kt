package com.blendertablet.remote

import com.blendertablet.remote.model.TransformMode
import com.blendertablet.remote.model.ValueParser
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ValueParserTest {

    // ------------------------------------------------------------------- mover

    @Test
    fun `mover sin sufijo se asume en metros`() {
        assertEquals(4.0, ValueParser.parseMove("4")!!, 1e-12)
        assertEquals(1.5, ValueParser.parseMove("1.5")!!, 1e-12)
    }

    @Test
    fun `mover acepta metros centimetros y milimetros`() {
        assertEquals(4.0, ValueParser.parseMove("4m")!!, 1e-12)
        assertEquals(0.25, ValueParser.parseMove("25cm")!!, 1e-12)
        assertEquals(0.003, ValueParser.parseMove("3mm")!!, 1e-12)
    }

    @Test
    fun `mover tolera coma decimal y mayusculas`() {
        assertEquals(0.025, ValueParser.parseMove("2,5CM")!!, 1e-12)
    }

    @Test
    fun `mover admite negativos`() {
        assertEquals(-0.03, ValueParser.parseMove("-3cm")!!, 1e-12)
    }

    @Test
    fun `mover rechaza sufijos invalidos`() {
        assertNull(ValueParser.parseMove("4km"))
        assertNull(ValueParser.parseMove("4°"))
    }

    // ------------------------------------------------------------------- rotar

    @Test
    fun `rotar es en grados con o sin simbolo`() {
        assertEquals(45.0, ValueParser.parseRotate("45")!!, 1e-12)
        assertEquals(45.0, ValueParser.parseRotate("45°")!!, 1e-12)
        assertEquals(45.0, ValueParser.parseRotate("45deg")!!, 1e-12)
        assertEquals(-15.0, ValueParser.parseRotate("-15º")!!, 1e-12)
    }

    @Test
    fun `rotar rechaza porcentaje y unidades de longitud`() {
        assertNull(ValueParser.parseRotate("50%"))
        assertNull(ValueParser.parseRotate("2m"))
    }

    // ------------------------------------------------------------------ escalar

    @Test
    fun `escalar sin sufijo es factor`() {
        assertEquals(2.0, ValueParser.parseScale("2")!!, 1e-12)
    }

    @Test
    fun `escalar con porcentaje divide entre cien`() {
        assertEquals(0.5, ValueParser.parseScale("50%")!!, 1e-12)
        assertEquals(1.25, ValueParser.parseScale("125%")!!, 1e-12)
    }

    @Test
    fun `escalar rechaza unidades de longitud`() {
        assertNull(ValueParser.parseScale("2m"))
        assertNull(ValueParser.parseScale("3cm"))
    }

    // --------------------------------------------------------------- entrada

    @Test
    fun `entrada vacia o basura es nula`() {
        assertNull(ValueParser.parseMove(""))
        assertNull(ValueParser.parseMove("  "))
        assertNull(ValueParser.parseMove("abc"))
        assertNull(ValueParser.parseScale("x"))
    }

    @Test
    fun `parse despacha al parser del modo`() {
        assertEquals(0.01, ValueParser.parse("1cm", TransformMode.MOVE)!!, 1e-12)
        assertEquals(90.0, ValueParser.parse("90", TransformMode.ROTATE)!!, 1e-12)
        assertEquals(0.25, ValueParser.parse("25%", TransformMode.SCALE)!!, 1e-12)
    }
}
