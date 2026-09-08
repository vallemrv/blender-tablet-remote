package com.blendertablet.remote.model

/** El radio viaja en unidades Blender; los controles muestran la unidad del preset. */
object ProportionalRadius {
    fun parse(text: String, unit: LengthUnit, scaleLength: Double): Double? {
        if (scaleLength <= 0.0 || !scaleLength.isFinite()) return null
        val input = text.trim().replace(',', '.')
        val withUnit = if (input.toDoubleOrNull() != null) "$input ${unit.short}" else input
        return ValueParser.parseMove(withUnit)?.div(scaleLength)?.takeIf { it.isFinite() && it > 0.0 }
    }

    fun step(radius: Double, direction: Int, stepMeters: Double, scaleLength: Double): Double =
        (radius + direction * stepMeters / scaleLength).coerceAtLeast(0.000001 / scaleLength)
}
