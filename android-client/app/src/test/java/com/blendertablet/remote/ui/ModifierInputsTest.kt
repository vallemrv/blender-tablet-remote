package com.blendertablet.remote.ui

import com.blendertablet.remote.model.*
import com.blendertablet.remote.network.StateParser
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ModifierInputsTest {
    private val width = ModifierParameterDescriptor("width", "float", ModifierDefault.Decimal(.1),
        min = 0.0, max = 1000.0, step = .01, editable = true, unit = "LENGTH")

    @Test fun decimalWidthUsesSceneScaleAndPresetWithoutStepRounding() {
        for ((unit, text) in listOf(LengthUnit.MILLIMETERS to "2,34567", LengthUnit.CENTIMETERS to "0,234567", LengthUnit.METERS to "0,00234567")) {
            for (scale in listOf(1.0, .001)) {
                val state = BlenderState(unitScaleLength = scale, sceneScale = SceneScale(lengthUnit = unit))
                val factor = modifierScalarFactor(width, state)
                val raw = parseModifierScalar(text, width, factor)!!.toDouble()
                assertEquals(.00234567, raw * scale, 1e-12)
            }
        }
        assertEquals(0.0, parseModifierScalar("0", width, 1.0)!!.toDouble(), 0.0)
    }

    @Test fun incompleteInvalidAndOutOfRangeDraftsDoNotBecomeCommands() {
        for (text in listOf("", "-", ",", "NaN", "Infinity", "1e999", "-0.01", "1000.01")) {
            assertNull(text, parseModifierScalar(text, width, 1.0))
        }
        assertNull(parseModifierScalar("1", width, 0.0))
    }

    @Test fun segmentsRequireWholeNumbersAndProfilePreservesWrittenPrecision() {
        val segments = width.copy(type = "int", min = 1.0, unit = null)
        assertEquals(8, parseModifierScalar("8", segments, 1.0))
        assertNull(parseModifierScalar("8.5", segments, 1.0))
        val profile = width.copy(max = 1.0, step = .05, unit = null)
        assertEquals(.537, parseModifierScalar("0.537", profile, 1.0)!!.toDouble(), 0.0)
        assertNull(parseModifierScalar("1.1", profile, 1.0))
    }

    @Test fun editableDisplayDoesNotRoundSmallWidthsToZeroOrToTheStepper() {
        assertEquals("0.000012345", formatEditableModifierValue(.000012345))
        assertEquals("2.34567", formatEditableModifierValue(2.345670022))
        assertEquals("0.1", formatEditableModifierValue(.10000000149))
    }

    @Test fun schemaEnablesExactFieldsWithoutChangingLegacyOrReadOnlyControls() {
        val options = StateParser.modifierOptions(JSONObject("""{"types":{"BEVEL":{"parameters":{
            "width":{"type":"float","default":0.1,"editable":true,"unit":"LENGTH","label":"Ancho"},
            "angle_limit":{"type":"float","default":30,"editable":true,"unit":"ANGLE"}
        }},"MULTIRES":{"parameters":{
            "levels":{"type":"int","default":1,"max_parameter":"total_levels"},
            "total_levels":{"type":"int","default":0,"read_only":true}
        }}}}"""))
        val bevel = options.first { it.type == "BEVEL" }.parameters
        val parsed = bevel.first { it.name == "width" }
        assertTrue(parsed.editable)
        assertEquals("Ancho", parsed.label)
        assertEquals("LENGTH", parsed.unit)
        val angle = bevel.first { it.name == "angle_limit" }
        assertEquals(1.0, modifierScalarFactor(angle, BlenderState(unitScaleLength = .001)), 0.0)
        val multires = options.first { it.type == "MULTIRES" }.parameters
        assertTrue(multires.none { it.editable })
        assertTrue(multires.first { it.name == "total_levels" }.readOnly)
    }
}
