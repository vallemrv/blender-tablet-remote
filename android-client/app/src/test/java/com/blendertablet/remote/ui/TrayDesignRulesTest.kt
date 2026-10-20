package com.blendertablet.remote.ui

import java.io.File
import org.junit.Assert.*
import org.junit.Test

/** Reglas comunes de las bandejas inferiores, comprobadas sobre el código que las dibuja. */
class TrayDesignRulesTest {
    private fun source(name: String) = File(System.getProperty("btr.repoRoot"),
        "android-client/app/src/main/java/com/blendertablet/remote/ui/$name.kt").readText()

    private val trays = listOf("TransformBar", "EditToolTray", "TweakHelpersTray", "SchemaToolParameters",
        "ObjectPropertiesTray", "SculptWorkspace", "MaterialWorkspace", "CadWorkspace", "SnapControl",
        "ToolTrayCommon", "Controls")

    private fun body(text: String, signature: String): String {
        val start = text.indexOf(signature).also { assertTrue("Falta $signature", it >= 0) }
        val next = text.indexOf("\n@Composable", start + signature.length)
        return text.substring(start, if (next < 0) text.length else next)
    }

    @Test fun everyTouchControlMeasuresAtLeast48dp() {
        assertTrue(Metrics.Touch.value >= 48f)
        val controls = source("Controls")
        for (name in listOf("fun IconAction(", "fun PillButton(", "fun StepperButton(", "fun RoundAction(",
            "fun CompactNumericField(")) {
            val code = body(controls, name)
            assertTrue("$name no usa el objetivo táctil común", code.contains("Metrics.Touch"))
            // El dibujo interior puede ser menor; el contenedor táctil no.
            val container = code.lines().filterNot { "Icon(" in it }.joinToString("\n")
            Regex("""\.(height|size|width)\((\d+)\.dp\)""").findAll(container).forEach {
                assertTrue("$name: ${it.value} es menor que 48 dp", it.groupValues[2].toInt() >= 48)
            }
        }
    }

    @Test fun traysNeverUseLabelValuePills() {
        val labelValue = Regex("""PillButton\("(\$\{[^}]*\}|[^"$]*\w): """)
        for (name in trays) {
            val hit = labelValue.find(source(name))
            assertNull("$name: pastilla «etiqueta: valor» ${hit?.value}", hit)
        }
        assertFalse(source("SnapControl").contains("\"Snap: "))
    }

    @Test fun sharedTrayIsOneFixedRowWithTheThreeMoreGroups() {
        val tray = body(source("Controls"), "fun SingleLineTray(")
        assertFalse(tray.contains("horizontalScroll"))
        assertTrue(tray.contains("TrayMoreButton"))
        assertEquals(listOf("Precisión", "Referencia", "Forma"),
            TrayMore(precision = {}, reference = {}, shape = {}).groups.map { it.first })
        assertEquals(listOf("Forma"), TrayMore(shape = {}).groups.map { it.first })
        assertTrue(TrayMore().isEmpty)
        for (name in trays) assertFalse("$name usa el menú Más antiguo", source(name).contains("ToolMoreMenu("))
    }
}
