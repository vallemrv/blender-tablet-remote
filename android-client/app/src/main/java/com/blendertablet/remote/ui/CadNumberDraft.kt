package com.blendertablet.remote.ui

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue

/** Acknowledgments of older values must not reset a held CAD stepper. */
internal class CadNumberDraft {
    var text: String? by mutableStateOf(null)
    var pending: Double? by mutableStateOf(null)

    fun read(remote: Double, factor: Double, minimum: Double, maximum: Double): Double? {
        val value = if (text == null) pending ?: remote else
            text!!.trim().replace(',', '.').toDoubleOrNull()?.div(factor) ?: return null
        return value.takeIf { it.isFinite() && it in minimum..maximum }
    }

    fun nudge(remote: Double, factor: Double, step: Double, direction: Int, minimum: Double, maximum: Double): Double? {
        val current = read(remote, factor, minimum, maximum) ?: return null
        val next = (current.toBigDecimal() + step.toBigDecimal() * direction.toBigDecimal())
            .toDouble().coerceIn(minimum, maximum)
        pending = next
        text = null
        return next
    }

    fun acknowledge(remote: Double) {
        if (pending == remote) pending = null
    }
}
