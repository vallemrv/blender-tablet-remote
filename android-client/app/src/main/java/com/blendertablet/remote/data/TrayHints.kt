package com.blendertablet.remote.data

import android.content.Context

/**
 * Cuántas veces se ha enseñado la frase de ayuda de cada bandeja. Las primeras
 * apariciones la muestran bajo la fila; después basta con acercar el lápiz.
 */
class TrayHints(context: Context) {
    private val prefs = context.getSharedPreferences("tray_hints", Context.MODE_PRIVATE)

    /** Cuenta una aparición y dice si todavía corresponde mostrar la ayuda. */
    fun consume(key: String): Boolean {
        val seen = prefs.getInt(key, 0)
        if (seen >= LIMIT) return false
        prefs.edit().putInt(key, seen + 1).apply()
        return true
    }

    companion object { const val LIMIT = 3 }
}
