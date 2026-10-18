package com.blendertablet.remote.ui

import com.blendertablet.remote.model.*
import com.blendertablet.remote.network.StateParser
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ObjectPropertiesTest {
    private val length = ObjectPropertyField("location_x", "X", "Posición", "number", "length")
    @Test fun metricValuesArePhysicalMetersAndDoNotDependOnBlenderScale() {
        assertEquals(.0125, objectPropertyNumber("12,5", length, LengthUnit.MILLIMETERS)!!, 1e-12)
        assertEquals(.0125, objectPropertyNumber("1.25", length, LengthUnit.CENTIMETERS)!!, 1e-12)
        assertEquals(12.5, objectPropertyDisplay(.0125, length, LengthUnit.MILLIMETERS), 1e-12)
        assertNull(objectPropertyNumber("", length, LengthUnit.MILLIMETERS))
        assertNull(objectPropertyNumber("-", length, LengthUnit.MILLIMETERS))
    }
    @Test fun opacityAllowsExactZeroButRejectsOutOfRange() {
        val opacity = length.copy(id="opacity", unit="percent", min=0.0, max=1.0)
        assertEquals(.35, objectPropertyNumber("35", opacity, LengthUnit.METERS)!!, 1e-12)
        assertEquals(0.0, objectPropertyNumber("0", opacity, LengthUnit.METERS)!!, 0.0)
        assertNull(objectPropertyNumber("101", opacity, LengthUnit.METERS))
        assertNull(objectPropertyNumber("-1", opacity, LengthUnit.METERS))
    }
    @Test fun stateParsesNativeImageSchemaWithoutInferringItFromObjectType() {
        val state=StateParser.state(JSONObject("""{"mode":"OBJECT","active_object":"Plano","active":{
          "type":"EMPTY","properties":{"id":"runtime:scene:object","name":"Plano","revision":"r1",
          "values":{"perspective":false,"opacity":0.35},"fields":[
          {"id":"perspective","label":"En perspectiva","type":"bool","group":"Imagen"},
          {"id":"opacity","label":"Opacidad","type":"number","group":"Imagen","unit":"percent","min":0,"max":1}],
          "note":"Posición en los ejes de la escena."}}}"""))
        val props=state.objectProperties!!
        assertEquals(false, props.values["perspective"])
        assertEquals("percent",props.fields[1].unit)
        assertEquals("r1",props.revision)
        assertNull(StateParser.state(JSONObject("""{"active":{"type":"EMPTY"}}""")).objectProperties)
    }
}
