package com.blendertablet.remote.network

import com.blendertablet.remote.model.*
import org.json.JSONObject

object MaterialParser {
    fun state(json: JSONObject?): MaterialState {
        if (json == null) return MaterialState()
        fun catalog(key: String): List<MaterialPreset> {
            val array = json.optJSONArray(key) ?: return emptyList()
            return (0 until array.length()).mapNotNull { array.optJSONObject(it) }.map {
                MaterialPreset(it.optString("id"), it.optString("label"), it.optString("color", "#B8B8B8"), it.optString("category", "base"))
            }
        }
        val targets = json.optJSONArray("targets")
        return MaterialState(erase = json.optBoolean("erase"), finish = json.optString("finish", "natural"), finishes = catalog("finishes"), available = json.optBoolean("available"), active = json.optBoolean("active"),
            targets = if (targets == null) emptyList() else (0 until targets.length()).map { targets.optString(it) },
            presets = catalog("presets"), environments = catalog("environments"), preset = json.optString("preset", "plastic"),
            color = json.optString("color", "#E85D38"), environment = json.optString("environment", "studio"),
            radius = json.optDouble("radius", .06).toFloat(), strength = json.optDouble("strength", 1.0).toFloat(),
            paintReady = json.optBoolean("paint_ready"))
    }
}
