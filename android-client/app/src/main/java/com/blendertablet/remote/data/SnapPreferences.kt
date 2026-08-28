package com.blendertablet.remote.data

import android.content.Context
import com.blendertablet.remote.model.SnapType

/** Preferencia global de snap: permanece hasta que el usuario la cambie. */
data class SnapSettings(
    val type: SnapType = SnapType.NONE,
    val step: Double = 0.1,
)

class SnapPreferences(context: Context) {
    private val prefs = context.getSharedPreferences(NAME, Context.MODE_PRIVATE)

    val current: SnapSettings
        get() = SnapSettings(
            type = runCatching {
                SnapType.valueOf(prefs.getString(KEY_TYPE, SnapType.NONE.name)!!)
            }.getOrDefault(SnapType.NONE),
            step = prefs.getString(KEY_STEP, null)?.toDoubleOrNull() ?: 0.1,
        )

    fun save(settings: SnapSettings) {
        prefs.edit()
            .putString(KEY_TYPE, settings.type.name)
            .putString(KEY_STEP, settings.step.toString())
            .apply()
    }

    private companion object {
        const val NAME = "snap"
        const val KEY_TYPE = "type"
        const val KEY_STEP = "step"
    }
}
