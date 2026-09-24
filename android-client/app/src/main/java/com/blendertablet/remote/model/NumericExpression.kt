package com.blendertablet.remote.model

/**
 * Cuentas de los campos numéricos, al estilo de Blender y FreeCAD.
 *
 * `10-3`, `(2+1)*4` y `2x3` son valores absolutos. Si empieza por `+`, `*` o `/`,
 * la operación usa el valor actual: `+5` suma, `*2` duplica, `/2` divide.
 * Un `-` seguido solo de un número sigue siendo negativo, para poder escribir cotas.
 */
object NumericExpression {
    fun evaluate(input: String, current: Double? = null): Double? {
        var text = input.trim().replace(',', '.')
        if (text.isEmpty()) return null
        if (text[0] in "+*/" && current != null && current.isFinite()) text = "($current)$text"
        val parser = Parser(text)
        val value = parser.expression() ?: return null
        parser.skip()
        return value.takeIf { parser.done() && it.isFinite() }
    }

    private class Parser(private val source: String) {
        private var index = 0

        fun done() = index >= source.length

        fun expression(): Double? {
            var value = term() ?: return null
            while (true) {
                skip()
                when (peek()) {
                    '+' -> { index++; value += term() ?: return null }
                    '-' -> { index++; value -= term() ?: return null }
                    else -> return value
                }
            }
        }

        private fun term(): Double? {
            var value = unary() ?: return null
            while (true) {
                skip()
                val op = peek()
                if (op != '*' && op != '/' && op != 'x' && op != 'X' && op != '×') return value
                index++
                val right = unary() ?: return null
                if (op == '/') {
                    if (right == 0.0) return null
                    value /= right
                } else value *= right
            }
        }

        private fun unary(): Double? {
            skip()
            return when (peek()) {
                '+' -> { index++; unary() }
                '-' -> { index++; unary()?.unaryMinus() }
                else -> primary()
            }
        }

        private fun primary(): Double? {
            skip()
            if (peek() == '(') {
                index++
                val value = expression() ?: return null
                skip()
                if (peek() != ')') return null
                index++
                return value
            }
            val start = index
            if (peek() == '.') index++
            while (index < source.length && source[index].isDigit()) index++
            if (index < source.length && source[index] == '.' && start != index) {
                index++
                while (index < source.length && source[index].isDigit()) index++
            }
            if (index == start) return null
            return source.substring(start, index).toDoubleOrNull()
        }

        fun skip() {
            while (index < source.length && source[index].isWhitespace()) index++
        }

        private fun peek() = if (index < source.length) source[index] else '\u0000'
    }
}
