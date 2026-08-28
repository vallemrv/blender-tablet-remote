package com.blendertablet.remote

import com.blendertablet.remote.model.ActiveTool
import com.blendertablet.remote.model.BlenderState
import com.blendertablet.remote.model.EditTool
import com.blendertablet.remote.model.LoopFalloff
import com.blendertablet.remote.model.SelectionMode
import com.blendertablet.remote.model.ToolSession
import com.blendertablet.remote.model.SnapType
import com.blendertablet.remote.model.bottomTrayVisible
import com.blendertablet.remote.network.StateParser
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ModelTest {
    @Test fun `knife conserva anclas 3d y lee su proyeccion vigente`() {
        val session = StateParser.toolSession(org.json.JSONObject(
            """{"active":true,"tool":"KNIFE","points":[[1,2,3],[4,5,6]],
                "projected_points":[[0.25,0.4],[0.7,0.8]],"closed":false}"""
        ))
        assertEquals(2, session.points.size)
        assertEquals(listOf(0.25, 0.4), session.projectedPoints.first())
    }

    @Test fun `extrude region ofrece snap geometrico y las demas tools solo escalar`() {
        val extrude = ToolSession(
            active = true, tool = EditTool.EXTRUDE,
            parameters = mapOf("variant" to "REGION", "snap_type" to "NONE"),
        )
        assertTrue(SnapType.VERTEX in extrude.availableSnapTypes)
        val inset = ToolSession(
            active = true, tool = EditTool.INSET,
            parameters = mapOf("snap_type" to "NONE"),
        )
        assertEquals(listOf(SnapType.NONE, SnapType.INCREMENT, SnapType.GRID), inset.availableSnapTypes)
        assertFalse(SnapType.VERTEX in inset.availableSnapTypes)
        val bevel = ToolSession(active = true, tool = EditTool.BEVEL, parameters = mapOf("snap_type" to "NONE"))
        assertEquals(listOf(SnapType.NONE, SnapType.INCREMENT, SnapType.GRID), bevel.availableSnapTypes)
        val bridge = ToolSession(
            active = true, tool = EditTool.BRIDGE_EDGE_LOOPS, parameters = mapOf("snap_type" to "NONE"),
        )
        assertEquals(listOf(SnapType.NONE, SnapType.INCREMENT, SnapType.GRID), bridge.availableSnapTypes)
        val subdivide = ToolSession(active = true, tool = EditTool.SUBDIVIDE, parameters = emptyMap())
        assertTrue(subdivide.availableSnapTypes.isEmpty())
    }

    @Test fun `tool session parsea paso y candidato visual de snap`() {
        val json = org.json.JSONObject(
            """{"active":true,"tool":"EXTRUDE","snap_type":"VERTEX","snap_step":0.01,
              "parameters":{"variant":"REGION","snap_type":"VERTEX","snap_step":0.01},
              "snap_candidate":{"hit":true,"snap_type":"VERTEX","id":"Cube:VERTEX:3",
              "object":"Cube","position":[1,2,3],"screen":[0.25,0.75],"distance":0.004}}""",
        )
        val session = com.blendertablet.remote.network.StateParser.toolSession(json)
        assertEquals(SnapType.VERTEX, session.snapType)
        assertEquals(.01, session.snapStep, 1e-12)
        assertEquals(listOf(.25, .75), session.snapCandidate?.screen)
        assertEquals("Cube:VERTEX:3", session.snapCandidate?.id)
    }
    @Test fun defaultStateStartsInVertexSelection() {
        assertEquals(SelectionMode.VERTEX, BlenderState().selectionMode)
    }

    @Test fun falloffCiclaTodosLosPerfiles() {
        var current = LoopFalloff.SMOOTH
        val seen = mutableSetOf(current)
        repeat(LoopFalloff.entries.size - 1) { current = current.next(); seen.add(current) }
        assertEquals(LoopFalloff.entries.toSet(), seen)
        assertEquals(LoopFalloff.SMOOTH, current.next())
    }

    @Test fun falloffParseEsTolerante() {
        assertEquals(LoopFalloff.SPHERE, LoopFalloff.fromWire("SPHERE"))
        assertEquals(null, LoopFalloff.fromWire("NOPE"))
        assertTrue(LoopFalloff.fromWire("linear") == null)
    }

    /** El teclado de vistas se eleva exactamente cuando una bandeja inferior ocupa su zona. */
    @Test fun `el teclado se eleva solo con una bandeja inferior`() {
        assertFalse(bottomTrayVisible(false, false, ActiveTool.SELECT, false))
        assertTrue(bottomTrayVisible(true, false, ActiveTool.SELECT, false))
        assertTrue(bottomTrayVisible(false, true, ActiveTool.EXTRUDE, false))
        assertTrue(bottomTrayVisible(false, false, ActiveTool.LOOP_CUT, true))
        assertFalse(bottomTrayVisible(false, false, ActiveTool.LOOP_CUT, false))
        assertFalse(bottomTrayVisible(false, false, ActiveTool.MOVE, true))
    }

    /** El puente reconcilia sesión: está en el enum y su nudge es el desfase. */
    @Test fun `bridge edge loops se reconcilia como sesion`() {
        assertEquals(EditTool.BRIDGE_EDGE_LOOPS, EditTool.fromWire("BRIDGE_EDGE_LOOPS"))
        assertEquals("twist_offset", ToolSession(active = true, tool = EditTool.BRIDGE_EDGE_LOOPS).primaryKey)
    }

    /** Knife se reconcilia y su sesión lleva los puntos confirmados por el servidor. */
    @Test fun `knife se reconcilia y parsea puntos y cierre`() {
        assertEquals(EditTool.KNIFE, EditTool.fromWire("KNIFE"))
        assertEquals("", ToolSession(active = true, tool = EditTool.KNIFE).primaryKey)
        val json = org.json.JSONObject(
            """{"active": true, "tool": "KNIFE", "parameters": {"snap": true},
                "points": [[-5.0, 1.0, 0.0], [5.0, 1.0, 0.0]], "closed": true}""",
        )
        val session = com.blendertablet.remote.network.StateParser.toolSession(json)
        assertTrue(session.active)
        assertEquals(EditTool.KNIFE, session.tool)
        assertEquals(2, session.points.size)
        assertEquals(3, session.points[0].size)
        assertTrue(session.closed)
    }

    /** B1: una tool armada (Loop Cut/Bisect sin geometría todavía) no es IDLE. */
    @Test fun `tool armada se distingue de inactiva y de activa`() {
        val armed = org.json.JSONObject(
            """{"active": false, "armed": true, "phase": "ARMED", "tool": "LOOP_CUT", "parameters": {}}""",
        )
        val session = com.blendertablet.remote.network.StateParser.toolSession(armed)
        assertFalse(session.active)
        assertTrue(session.armed)
        assertEquals(EditTool.LOOP_CUT, session.tool)

        val idle = com.blendertablet.remote.network.StateParser.toolSession(
            org.json.JSONObject("""{"active": false, "armed": false, "phase": "IDLE"}"""),
        )
        assertFalse(idle.armed)
        assertEquals(ToolSession(), idle)
    }

    /** B4: Bisect se reconcilia y su sesión lleva la línea que fijó el servidor. */
    @Test fun `bisect se reconcilia y parsea la linea de arrastre`() {
        assertEquals(EditTool.BISECT, EditTool.fromWire("BISECT"))
        val json = org.json.JSONObject(
            """{"active": true, "armed": true, "tool": "BISECT",
                "parameters": {"clear_inner": false, "fill": true},
                "line": {"start": [0.1, 0.5], "end": [0.9, 0.5]}}""",
        )
        val session = com.blendertablet.remote.network.StateParser.toolSession(json)
        assertTrue(session.active)
        assertEquals(EditTool.BISECT, session.tool)
        assertTrue(session.flag("fill"))
        assertEquals(listOf(0.1, 0.5), session.line?.start)
        assertEquals(listOf(0.9, 0.5), session.line?.end)
    }

    /** F1: el teclado de vistas también se eleva con Bisect armado esperando el arrastre. */
    @Test fun `el teclado se eleva con bisect armado`() {
        assertTrue(bottomTrayVisible(false, false, ActiveTool.BISECT, false, toolSessionArmed = true))
        assertFalse(bottomTrayVisible(false, false, ActiveTool.BISECT, false, toolSessionArmed = false))
    }
}
