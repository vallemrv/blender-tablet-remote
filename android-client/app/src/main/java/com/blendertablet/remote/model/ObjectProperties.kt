package com.blendertablet.remote.model

data class ObjectPropertyField(
    val id: String, val label: String, val group: String, val type: String,
    val unit: String = "", val readOnly: Boolean = false,
    val min: Double? = null, val max: Double? = null,
    val choices: Map<String, String> = emptyMap(),
)
data class ObjectProperties(
    val id: String, val name: String, val revision: String,
    val fields: List<ObjectPropertyField>, val values: Map<String, Any?>, val note: String,
)
data class ObjectPropertiesResult(val token: String, val success: Boolean)

/** Solo los campos modificados viajan; un borrador vacío nunca se convierte en cero. */
fun objectPropertyNumber(text: String, field: ObjectPropertyField, unit: LengthUnit): Double? {
    val value = NumericExpression.evaluate(text) ?: return null
    val factor = when (field.unit) {
        "length" -> unit.transformStepUnit().meters
        "percent" -> .01
        else -> 1.0
    }
    return (value * factor).takeIf { it.isFinite() && it >= (field.min ?: -Double.MAX_VALUE) && it <= (field.max ?: Double.MAX_VALUE) }
}

fun objectPropertyDisplay(value: Number, field: ObjectPropertyField, unit: LengthUnit): Double =
    value.toDouble() / when (field.unit) {
        "length" -> unit.transformStepUnit().meters
        "percent" -> .01
        else -> 1.0
    }
