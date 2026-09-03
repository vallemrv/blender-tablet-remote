package com.blendertablet.remote.model

/**
 * Parser de la entrada numérica de la barra de transformación.
 *
 * Acepta lo que un modelador escribe a mano, con la unidad pegada al número:
 *
 *   - Mover:  `4m`, `25cm`, `3mm`, `1.5` (sin sufijo se asume metros, la unidad de Blender).
 *   - Rotar:  `45`, `45°`, `45º`, `45deg` (grados).
 *   - Escalar: `2`, `50%` (sin sufijo es factor; con `%` es porcentaje).
 *
 * Devuelve siempre el valor en la unidad que espera el protocolo: metros, grados o
 * factor. `null` significa "no se puede interpretar", y la UI no envía nada.
 */
object ValueParser {

    fun parse(input: String, mode: TransformMode): Double? = when (mode) {
        TransformMode.MOVE -> parseMove(input)
        TransformMode.ROTATE -> parseRotate(input)
        TransformMode.SCALE -> parseScale(input)
    }

    /** Metros. Sufijos: `m`, `cm`, `mm`. Sin sufijo, metros. */
    fun parseMove(input: String): Double? {
        val (number, unit) = split(input) ?: return null
        return when (unit) {
            "" -> number
            "m" -> number
            "cm" -> number * 0.01
            "mm" -> number * 0.001
            else -> null
        }
    }

    /** Grados. Sufijos opcionales: `°`, `º`, `deg`. */
    fun parseRotate(input: String): Double? {
        val (number, unit) = split(input) ?: return null
        return when (unit) {
            "", "°", "º", "deg" -> number
            else -> null
        }
    }

    /** Factor. Sufijo `%` divide entre 100; sin sufijo es el factor tal cual. */
    fun parseScale(input: String): Double? {
        val (number, unit) = split(input) ?: return null
        return when (unit) {
            "" -> number
            "%" -> number / 100.0
            else -> null
        }
    }

    /** Factor necesario para alcanzar una dimensión final o un porcentaje. */
    fun parseScaleDimension(
        input: String,
        unit: TransformStepUnit,
        unitScaleLength: Double,
        baseDimension: Double,
    ): Double? {
        if (baseDimension <= 1e-12 || unitScaleLength <= 1e-12) return null
        if (unit == TransformStepUnit.PERCENT) {
            val number = input.trim().replace(',', '.').removeSuffix("%").toDoubleOrNull() ?: return null
            return (number / 100.0).takeIf { it > 0.0 }
        }
        val explicit = split(input)?.second?.isNotEmpty() == true
        val physicalMeters = (if (explicit) parseMove(input) else {
            val number = input.trim().replace(',', '.').toDoubleOrNull() ?: return null
            when (unit) {
                TransformStepUnit.MM -> number / 1000.0
                TransformStepUnit.CM -> number / 100.0
                TransformStepUnit.M -> number
                TransformStepUnit.PERCENT -> return null
            }
        }) ?: return null
        return (physicalMeters / unitScaleLength / baseDimension).takeIf { it > 0.0 }
    }

    /** Separa el número de su sufijo: `"25cm"` -> `(25.0, "cm")`. */
    private fun split(input: String): Pair<Double, String>? {
        val text = input.trim().replace(',', '.').lowercase()
        if (text.isEmpty()) return null
        // El sufijo son letras o símbolos de unidad al final; el número es el resto.
        var i = text.length
        while (i > 0 && (text[i - 1].isLetter() || text[i - 1] in "°º%")) i--
        val number = text.substring(0, i).toDoubleOrNull() ?: return null
        return number to text.substring(i)
    }
}

/**
 * Aplica la edición de un campo de escala. Con la cadena activa replica el factor
 * relativo y conserva las proporciones; abierta cambia únicamente el eje editado.
 */
fun scaleValuesAfterAxisEdit(
    current: List<Double>,
    axisIndex: Int,
    factor: Double,
    linked: Boolean,
): List<Double> {
    require(axisIndex in 0..2) { "axisIndex must be 0, 1 or 2" }
    val values = MutableList(3) { current.getOrElse(it) { 1.0 } }
    if (linked) values.indices.forEach { values[it] = factor }
    else values[axisIndex] = factor
    return values
}
