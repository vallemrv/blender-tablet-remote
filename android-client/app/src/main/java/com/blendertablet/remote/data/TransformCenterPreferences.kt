package com.blendertablet.remote.data

import android.content.Context
import com.blendertablet.remote.model.TransformCenter

class TransformCenterPreferences(context: Context) {
    private val prefs = context.getSharedPreferences("transform_center", Context.MODE_PRIVATE)
    private var current = read()
    private fun read(): TransformCenter {
        val mode = prefs.getString("mode", "SELECTION") ?: "SELECTION"
        if (mode !in setOf("SELECTION", "CURSOR", "OBJECT_ORIGIN", "INDIVIDUAL", "PICKED")) return TransformCenter()
        val point = prefs.getString("point", "")!!.split(',').mapNotNull { it.toDoubleOrNull()?.takeIf(Double::isFinite) }
        if (mode == "PICKED" && point.size != 3) return TransformCenter()
        return TransformCenter(mode, if (mode == "PICKED") point else emptyList(), prefs.getString("scene_id", "") ?: "")
    }
    fun forScene(sceneId: String): TransformCenter = current.forScene(sceneId)
    fun save(center: TransformCenter) {
        if (center == current) return
        current = center
        prefs.edit().putString("mode", center.mode).putString("point", center.point.joinToString(","))
            .putString("scene_id", center.sceneId).apply()
    }
}
