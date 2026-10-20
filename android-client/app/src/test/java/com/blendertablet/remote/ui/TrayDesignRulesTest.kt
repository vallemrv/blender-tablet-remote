package com.blendertablet.remote.ui

import com.blendertablet.remote.model.Axis
import com.blendertablet.remote.model.Constraint
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
        for (name in listOf("fun IconAction(", "fun PillButton(", "fun RoundAction(",
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

    @Test fun scrubbingCountsWholeStepsAfterTheTouchSlop() {
        assertEquals(0, scrubSteps(5f, 8f, 20f))
        assertEquals(1, scrubSteps(9f, 8f, 20f))
        assertEquals(1, scrubSteps(27f, 8f, 20f))
        assertEquals(2, scrubSteps(29f, 8f, 20f))
        assertEquals(-3, scrubSteps(-50f, 8f, 20f))
        // Un trazo inclinado también desliza; uno claramente vertical no.
        assertTrue(scrubStarts(10f, 15f, 8f, held = false))
        assertFalse(scrubStarts(5f, 30f, 8f, held = false))
        assertFalse(scrubStarts(6f, 0f, 8f, held = false))
        // Tras mantener pulsado basta un movimiento menor y en cualquier dirección.
        assertTrue(scrubStarts(5f, 0f, 8f, held = true))
        assertTrue(scrubStarts(0f, 9f, 8f, held = true))
    }

    @Test fun trayNumbersScrubTypeAndResetWithoutSteppersAndHelpOnlyFirstTimes() {
        val numbers = mapOf("ToolTrayCommon" to "fun ToolNumericInput(", "EditToolTray" to "private fun PositionStepper(",
            "TransformBar" to "internal fun ProportionalRadiusInput(", "CadWorkspace" to "private fun CadDimension(",
            "ObjectPropertiesTray" to "private fun PropertyControl(")
        for ((file, signature) in numbers) {
            val code = body(source(file), signature)
            assertTrue("$signature no desliza", code.contains("ScrubNumber("))
            assertFalse("$signature mantiene −/+ en la fila", code.contains("StepperButton(") || code.contains("PillButton(\"−\""))
        }
        assertTrue(body(source("EditToolTray"), "private fun PositionStepper(").contains("onReset = { send(0.0) }"))
        val tray = body(source("Controls"), "fun SingleLineTray(")
        assertTrue(tray.contains("TrayHints(context).consume(hintKey)"))
        assertTrue(tray.contains("firstTimes && help.isNotBlank()"))
    }

    /** Controles directos de la fila de una bandeja: el bloque de contenido de SingleLineTray. */
    private fun rowControls(code: String, marker: String): List<String> {
        val row = code.substringAfter(marker).substringAfter(") {").substringBefore("\n}\n")
        return Regex("""\b(AxisSelector|IconAction|SnapControl|ChoiceIcon|PillButton|FalloffChoice|TrayNumber)\(""")
            .findAll(row).map { it.groupValues[1] }.toList()
    }

    @Test fun transformShowsAxesSnapAndConstraintWithTheRestUnderMore() {
        val bar = body(source("TransformBar"), "fun TransformBar(")
        val controls = rowControls(bar, "hintKey = \"transform.")
        // Norma: [Mover] [AxisSelector (con la cadena de Escalar dentro)] [Snap] [⋯] [× ✓].
        assertEquals(listOf("AxisSelector", "IconAction", "SnapControl"), controls)
        assertTrue("Rotar no puede mostrar más de cinco controles", controls.size <= 5)
        for (option in listOf("\"Paso\"", "\"Centro\"", "\"Fuente\"", "\"Propio\"", "\"Orientación\"",
            "\"Otra selección\"", "\"Proporcional\"", "\"Perfil\""))
            assertTrue("Falta $option en Más", bar.substringBefore("SingleLineTray(").contains("TrayOption($option"))
        assertFalse(source("TransformBar").contains("IconAction(AppIcons.Reset, \"Restablecer rotación"))
    }

    @Test fun tweakKeepsGgSnapAndExtendInTheRowAndProportionalUnderShape() {
        val tray = source("TweakHelpersTray")
        assertTrue(tray.contains("SingleLineTray(\"Tweak\""))
        assertEquals(listOf("IconAction", "IconAction", "SnapControl"), rowControls(tray, "SingleLineTray(\"Tweak\""))
        assertTrue(tray.contains("TrayOption(if (slide) \"Proporcional (sin GG)\" else \"Proporcional\""))
    }

    @Test fun editToolRowsUseIconsAndNumbersOnly() {
        val control = body(source("EditToolTray"), "private fun ToolControl(")
        assertFalse("Los interruptores de Edit no son pastillas de texto", control.contains("PillButton("))
        for (tray in listOf("fun KnifeTray(", "fun BisectTray(")) assertFalse(body(source("EditToolTray"), tray).contains("PillButton("))
        listOf("even", "flip", "clamp", "remove_loop", "boundary", "merge", "undo_point", "new_cut", "close_cut",
            "clear_inner", "clear_outer", "fill", "merge_loop", "caps", "rotate_source")
            .forEach { assertNotNull("Sin icono: $it", AppIcons.trayToggle(it)) }
    }

    @Test fun noTrayScrollsHorizontally() {
        for (name in trays) assertFalse("$name desplaza su fila", source(name).contains(".horizontalScroll("))
    }

    @Test fun sculptAndMaterialsShowTheirTwoNumbersAndIconsWithDetailUnderMore() {
        val sculpt = source("SculptWorkspace")
        assertEquals(listOf("TrayNumber", "TrayNumber", "IconAction", "IconAction"), rowControls(sculpt, "hintKey = \"sculpt\""))
        for (option in listOf("Simetría", "Presión en la fuerza", "Presión en el radio", "Dyntopo", "Multires"))
            assertTrue(sculpt.contains("TrayOption(\"$option\""))
        // Norma: la presión es un icono por número, no pastillas con su mismo nombre.
        assertFalse(sculpt.contains("PillButton(\"Fuerza\"")); assertFalse(sculpt.contains("PillButton(\"Radio\""))
        assertFalse(sculpt.contains("Slider("))
        val material = source("MaterialWorkspace")
        assertEquals(listOf("ChoiceIcon", "TrayNumber", "TrayNumber"), rowControls(material, "hintKey = \"material.paint\""))
        assertFalse(material.contains("MaterialSlider("))
        // Norma: 48 dp también en fichas, Aplicar y muestras de color.
        for (small in listOf("height(32.dp)", "height(38.dp)", "Modifier.size(36.dp).background(parseColor(swatch), CircleShape).clickableNoRipple"))
            assertFalse("Control pequeño en Materiales: $small", material.contains(small))
    }

    /** Norma: CAD sin pastillas de texto para extensión, historial, planos guardados ni «Ir». */
    @Test fun cadUsesIconsInsteadOfTextPills() {
        val cad = source("CadWorkspace")
        for (pill in listOf("\"Una\"", "\"Todo\"", "\"Atrás\"", "\"Adelante\"", "\"Final\"", "\"Elegir ▾\"", "\"Ir\""))
            assertFalse("Pastilla de texto en CAD: $pill", cad.contains("PillButton($pill"))
        for (name in listOf("EditToolTray", "CadWorkspace")) assertFalse(source(name).contains("import androidx.compose.foundation.horizontalScroll"))
    }

    @Test fun cadAndPropertiesKeepNamedChoicesUnderMore() {
        val cad = source("CadWorkspace")
        val row = cad.substringAfter("hintKey = \"cad.\" + guidance.take(24)").substringBefore("\ninternal fun cadHasProjectedCurves")
        for (word in listOf("\"Una dirección\"", "\"Hasta cara\"", "\"Perforar todo\"", "\"Hacia fuera\"", "\"Planos guardados\"",
            "\"Más opciones", "\"Radio\", selected", "\"Derecha\""))
            assertFalse("$word sigue en la fila CAD", row.contains(word))
        for (option in listOf("Paso", "Extensión", "Hasta cara", "Destino", "Lado", "Planos guardados", "Medida"))
            assertTrue("Falta $option en Más CAD", cad.contains("TrayOption(\"$option\""))
        val props = body(source("ObjectPropertiesTray"), "fun ObjectPropertiesTray(")
        assertEquals(listOf("IconAction"), rowControls(props, "hintKey = \"object.properties\""))
        assertTrue(props.contains("TrayOption(\"Mostrar delante\""))
    }

    @Test fun noNumericInputKeepsMinusPlusButtons() {
        val ui = File(System.getProperty("btr.repoRoot"), "android-client/app/src/main/java/com/blendertablet/remote/ui")
        ui.listFiles()!!.filter { it.extension == "kt" }.forEach { file ->
            val text = file.readText()
            for (pattern in listOf("StepperButton(", "StepperRow(", "PillButton(\"−\"", "PillButton(\"+\"", "repeatOnHold"))
                assertFalse("${file.name} conserva $pattern", text.contains(pattern))
        }
        assertTrue(body(source("ModifierPanel"), "private fun EditableModifierScalar(").contains("ScrubNumber("))
        assertTrue(body(source("SnapControl"), "internal fun DistanceSnapStepInput(").contains("ScrubNumber("))
    }

    @Test fun axisSelectorTapsAnAxisAndThePlaneToggleExcludesIt() {
        assertEquals(Constraint.Z, axisSelectorTap(Constraint.FREE, Axis.Z, planeMode = false))
        assertEquals(Constraint.FREE, axisSelectorTap(Constraint.Z, Axis.Z, planeMode = false))
        assertEquals(Constraint.X, axisSelectorTap(Constraint.XY, Axis.X, planeMode = false))
        // Con Plano activo, tocar un eje lo excluye (como Shift+eje); otra vez vuelve a Libre.
        assertEquals(Constraint.XY, axisSelectorTap(Constraint.FREE, Axis.Z, planeMode = true))
        assertEquals(Constraint.FREE, axisSelectorTap(Constraint.XY, Axis.Z, planeMode = true))
        // El interruptor conserva el eje y cambia su sentido.
        assertEquals(Constraint.YZ, axisSelectorTogglePlane(Constraint.X))
        assertEquals(Constraint.X, axisSelectorTogglePlane(Constraint.YZ))
        // Sin Libre (ejes de un esquema) siempre queda un eje elegido.
        assertEquals(Constraint.Y, axisSelectorTap(Constraint.Y, Axis.Y, planeMode = false, allowFree = false))
        assertTrue(body(source("EditToolTray"), "private fun ToolControl(").contains("AxisSelector("))
    }
}
