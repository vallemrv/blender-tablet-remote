package com.blendertablet.remote.data

import android.content.Context
import com.blendertablet.remote.model.TransformMode

class DuplicatePreferences(context: Context) {
    private val prefs = context.getSharedPreferences("duplicate", Context.MODE_PRIVATE)
    val mode: TransformMode get() = if (prefs.getString("mode", null) == TransformMode.ROTATE.name)
        TransformMode.ROTATE else TransformMode.MOVE
    val linked: Boolean get() = prefs.getBoolean("linked", false)
    fun save(mode: TransformMode, linked: Boolean) {
        prefs.edit().putString("mode", mode.name).putBoolean("linked", linked).apply()
    }
}
