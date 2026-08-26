package com.blendertablet.remote

import com.blendertablet.remote.model.Axis
import com.blendertablet.remote.model.BlenderMode
import com.blendertablet.remote.model.Constraint
import com.blendertablet.remote.model.Orientation
import com.blendertablet.remote.model.SelectionMode
import com.blendertablet.remote.model.SnapType
import com.blendertablet.remote.model.TransformMode
import com.blendertablet.remote.model.ValueMode
import com.blendertablet.remote.model.EditTool
import com.blendertablet.remote.model.LoopFalloff
import com.blendertablet.remote.model.RemoteFileType
import com.blendertablet.remote.network.StateParser
import java.io.File
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import com.blendertablet.remote.model.ModifierDefault

/**
 * Contrato con el backend, leyendo **sus** fixtures.
 *
 * `blender-backend/fixtures/` lo publica el add-on con la forma exacta de sus
 * respuestas. Si allí se renombra un campo, aquí se cae un test; sin esto, un
 * `snap_type` que pasara a llamarse de otra forma solo se notaría al tocar el control
 * en la tablet, y encima en silencio, porque el parseo es tolerante a propósito.
 */
class BackendContractTest {

    private fun fixture(name: String): JSONObject {
        // Las pruebas corren con el directorio del módulo como raíz, pero se busca
        // hacia arriba para no atarse a esa profundidad concreta.
        var dir: File? = File("").absoluteFile
        while (dir != null) {
            val candidate = File(dir, "blender-backend/fixtures/v2/$name")
            if (candidate.isFile) return JSONObject(candidate.readText())
            dir = dir.parentFile
        }
        throw AssertionError("No encuentro la fixture $name del backend")
    }

    @Test
    fun `la sesion de transformacion se lee entera`() {
        val session = StateParser.session(fixture("transform.session.json"))

        assertTrue(session.active)
        assertEquals(TransformMode.MOVE, session.mode)
        assertEquals(setOf(Axis.X), session.axes)
        assertEquals(Constraint.X, session.constraint)
        assertEquals(Orientation.GLOBAL, session.orientation)
        assertEquals(ValueMode.RELATIVE, session.valueMode)
        assertEquals(SnapType.INCREMENT, session.snapType)
        assertEquals(0.01, session.step, 1e-9)
        assertEquals(1.25, session.values[0], 1e-9)
        assertEquals(0.0, session.angle, 1e-9)
    }

    /** `snap_candidate: null` es el caso normal: hay snap, pero aún no hay candidato. */
    @Test
    fun `sin candidato de snap no se inventa uno`() {
        assertEquals(null, StateParser.session(fixture("transform.session.json")).snapCandidate)
    }

    @Test
    fun `el contexto de Edit trae conteos y opciones validas`() {
        val json = fixture("context.edit.face.json")
        val context = StateParser.context(json)

        assertEquals(1, context.selectionCounts.faces)
        assertEquals(4, context.selectionCounts.verts)
        assertEquals(1, context.countFor(SelectionMode.FACE))
        assertTrue(context.hasSelection(BlenderMode.EDIT, SelectionMode.FACE))
        // Las cuatro herramientas paramétricas del rail tienen que venir declaradas.
        assertTrue(context.availableTools.map { it.name }.containsAll(
            listOf("EXTRUDE", "BEVEL", "INSET", "SUBDIVIDE"),
        ))
    }

    /**
     * El backend declara restricciones que la app no modela (NORMAL y VIEW no son
     * combinaciones de ejes). Deben descartarse en silencio en vez de tumbar el
     * parseo: el servidor puede ser más nuevo que la tablet.
     */
    @Test
    fun `las opciones desconocidas se descartan sin romper`() {
        val json = fixture("context.edit.face.json")
        val declared = json.getJSONArray("available_constraints").length()
        val parsed = StateParser.context(json).availableConstraints

        assertTrue(parsed.isNotEmpty())
        assertTrue("NORMAL y VIEW no son restricciones de ejes", parsed.size < declared)
        assertTrue(parsed.containsAll(listOf(Constraint.FREE, Constraint.X, Constraint.XY)))
    }

    /** Los tipos de snap del servidor son exactamente los que ofrece la barra. */
    @Test
    fun `los tipos de snap coinciden con los del backend`() {
        val json = fixture("context.edit.face.json")
        val declared = json.getJSONArray("available_snap_types")
        val names = (0 until declared.length()).map { declared.getString(it) }

        assertEquals(names.toSet(), SnapType.entries.map { it.name }.toSet())
        assertEquals(names, StateParser.context(json).availableSnapTypes.map { it.name })
    }

    /**
     * La app declara la versión de protocolo que espera. Si el backend sube de mayor,
     * esta prueba avisa antes que la tablet.
     */
    @Test
    fun `el protocolo sigue siendo la version 2`() {
        val capabilities = fixture("capabilities.json")
        assertTrue(capabilities.getString("protocol_version").startsWith("2."))

        val features = capabilities.getJSONObject("features")
        // Lo que la interfaz da por hecho: contexto con conteos, modal en Edit Mode,
        // snap geométrico y proyección conmutable.
        assertTrue(features.getJSONObject("context").getBoolean("selection_counts"))
        assertTrue(features.getJSONObject("transform_modal").getBoolean("geometric_snap"))
        val modes = features.getJSONObject("transform_modal").getJSONArray("modes")
        assertTrue((0 until modes.length()).map { modes.getString(it) }.contains("EDIT"))
        val projections = features.getJSONObject("view").getJSONArray("projections")
        assertEquals(2, projections.length())
    }

    /** El estado completo: lo que llega en cada `scene.get_state`. */
    @Test
    fun `el estado mezcla escena y contexto`() {
        val json = JSONObject(
            """
            {"mode": "EDIT_MESH", "active_object": "Mesa", "selected_objects": ["Mesa"],
             "selection_mode": "FACE", "selection_counts": {"objects": 1, "faces": 2},
             "active": {"location": [1, 2, 3], "rotation_euler": [0, 0, 0], "scale": [1, 1, 1]},
             "view": {"perspective": "ORTHO"}}
            """.trimIndent(),
        )
        val state = StateParser.state(json)

        // "EDIT_MESH" es lo que manda Blender: la app lo colapsa a EDIT.
        assertEquals(BlenderMode.EDIT, state.mode)
        assertEquals("Mesa", state.activeObject)
        assertEquals(SelectionMode.FACE, state.selectionMode)
        assertEquals(2, state.context.selectionCounts.faces)
        assertEquals("ORTHO", state.view.perspective.name)
        assertNotNull(state.transform)
        assertEquals(listOf(1f, 2f, 3f), state.transform?.location)
    }

    @Test fun `descriptores cubren cinco modifiers y boolean null`() {
        val options = StateParser.modifierOptions(fixture("modifier.add_options.json"))
        assertEquals(setOf("SUBSURF", "ARRAY", "BEVEL", "SOLIDIFY", "BOOLEAN"), options.map { it.type }.toSet())
        val operand = options.first { it.type == "BOOLEAN" }.parameters.first { it.name == "object" }
        assertEquals(ModifierDefault.Null, operand.default)
        assertEquals("MESH", operand.objectFilter?.type)
        assertTrue(operand.objectFilter?.excludeSelf == true)
    }

    @Test fun `visibility vacia y no vacia se parsea sin inventar objetos`() {
        assertTrue(StateParser.hiddenObjects(JSONObject("{}" ).optJSONArray("hidden_objects")).isEmpty())
        val list = StateParser.hiddenObjects(JSONObject("""{"hidden_objects":[{"name":"Cube","type":"MESH"}]}""").getJSONArray("hidden_objects"))
        assertEquals("Cube", list.single().name)
        assertEquals("MESH", list.single().type)
    }

    @Test fun `capability gating viene del servidor`() {
        val features = StateParser.features(fixture("capabilities.json"))
        assertTrue(features.modifiers)
        assertTrue(features.visibility)
        assertTrue(features.transformApply)
        assertTrue(features.loopCutPick)
        assertTrue(features.fileBrowse)
    }

    @Test fun `la sesion de loop cut conserva tipos de los parametros`() {
        val session = StateParser.toolSession(fixture("tool.session.json"))

        assertTrue(session.active)
        assertEquals(EditTool.LOOP_CUT, session.tool)
        // Números, bools del modal y el perfil llegan con su tipo original.
        assertEquals(3.0, session.double("edge")!!, 1e-9)
        assertEquals(0.35, session.double("factor")!!, 1e-9)
        assertEquals(2.0, session.double("cuts")!!, 1e-9)
        assertEquals(true, session.flag("even"))
        assertEquals(false, session.flag("flip"))
        assertEquals(true, session.flag("clamp", true))
        assertEquals(LoopFalloff.SPHERE, session.falloff())
    }

    @Test fun `el sondeo de loop cut devuelve arista y factor`() {
        val probe = StateParser.loopProbe(fixture("mesh.loop_probe.json"))
        assertTrue(probe.hit)
        assertEquals(3, probe.edge)
        assertEquals(0.42, probe.factor, 1e-9)
        assertEquals(4, probe.ring)
    }

    @Test fun `el explorador de archivos devuelve listado opaco`() {
        val browse = StateParser.fileBrowse(fixture("file.browse.json"))
        assertEquals("/home/valle/proyectos", browse.path)
        assertEquals("/home/valle", browse.parent)
        assertEquals(4, browse.breadcrumbs.size)
        assertEquals(2, browse.entries.size)
        assertEquals(RemoteFileType.DIRECTORY, browse.entries[0].type)
        assertEquals(RemoteFileType.BLEND, browse.entries[1].type)
    }

    @Test fun `los lugares de archivo traen alias estables`() {
        val locations = StateParser.fileLocations(fixture("file.locations.json"))
        assertEquals("/home/valle/proyectos", locations.defaultFolder)
        assertEquals(listOf("DEFAULT", "HOME", "ROOT"), locations.locations.map { it.id })
    }

    @Test fun `un tipo de entrada desconocido se descarta`() {
        val json = JSONObject(
            """{"entries": [{"name": "a", "path": "/a", "type": "BLEND"},
                            {"name": "b", "path": "/b", "type": "FUTURO"}]}""",
        )
        val entries = StateParser.fileEntries(json.optJSONArray("entries"))
        assertEquals(1, entries.size)
        assertEquals("a", entries.single().name)
    }
}
