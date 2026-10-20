package com.blendertablet.remote.ui

import java.io.File
import org.junit.Assert.*
import org.junit.Test

/**
 * Hace cumplir la «Norma de controles y gestos» de AGENTS.md sobre todo el código
 * Android, no solo sobre las bandejas que ya existían: lo nuevo tampoco puede saltársela.
 */
class ControlNormTest {
    private val root = File(System.getProperty("btr.repoRoot"), "android-client/app/src/main/java/com/blendertablet/remote")
    private val sources = root.walkTopDown().filter { it.extension == "kt" }.associate { it.name to it.readText() }

    @Test fun axisSelectorIsTheOnlyAxisControl() {
        val definitions = sources.filterValues { Regex("""fun AxisSelector\(""").containsMatchIn(it) }.keys
        assertEquals(setOf("AxisSelector.kt"), definitions)
        for ((name, code) in sources) {
            assertFalse("$name conserva el control de ejes antiguo", code.contains("AxisConstraintButtons"))
            assertFalse("$name bloquea un plano con pulsación larga", code.contains("constraintAfterHold"))
        }
        // Transformar ya no dibuja una segunda fila de letras X/Y/Z encima de los valores.
        val transform = sources.getValue("TransformBar.kt")
        assertFalse(transform.contains("caption = axis.name"))
        assertTrue(transform.contains("AxisSelector(constraint, onConstraint"))
        // Extruir y los ejes por esquema usan el mismo componente.
        assertTrue(sources.getValue("EditToolTray.kt").contains("AxisSelector("))
        assertTrue(sources.getValue("SchemaToolParameters.kt").contains("AxisSelector("))
    }

    @Test fun planeIsAVisibleToggleAndTheSelectorHasNoLongPress() {
        val selector = sources.getValue("AxisSelector.kt")
        assertTrue(selector.contains("AppIcons.AxisPlane"))
        assertFalse(selector.contains("onLongClick"))
        assertFalse(selector.contains("combinedClickable"))
    }

    @Test fun numbersResetWithDoubleTapEverywhere() {
        val scrub = sources.getValue("ScrubNumber.kt")
        assertTrue(scrub.contains("doubleTapTimeoutMillis"))
        assertTrue(sources.getValue("ToolTrayCommon.kt").contains("doble toque para restablecerlo"))
        for ((name, code) in sources) assertFalse("$name sigue explicando restablecer al mantener",
            code.contains("mantén pulsado para restablecer") || code.contains("y mantenlo para restablecer"))
    }

    @Test fun touchTargetsInFooterAndMaterialsAreAtLeast48dp() {
        val small = Regex("""\.(size|height)\((2\d|3\d|4[0-7])\.dp\)\s*\n?\s*\.clip\(RoundedCornerShape""")
        for (name in listOf("ViewFooter.kt", "MaterialWorkspace.kt"))
            assertFalse("$name tiene un control táctil menor de 48 dp", small.containsMatchIn(sources.getValue(name)))
    }
}
