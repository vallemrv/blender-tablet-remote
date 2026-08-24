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
