package com.blendertablet.remote.network

import com.blendertablet.remote.model.*
import org.json.JSONObject

object MaterialParser {
    fun state(json: JSONObject?): MaterialState {
        if (json == null) return MaterialState()
        fun catalog(key: String): List<MaterialPreset> {
            val array = json.optJSONArray(key) ?: return emptyList()
            return (0 until array.length()).mapNotNull { array.optJSONObject(it) }.map {
                MaterialPreset(it.optString("id"), it.optString("label"), it.optString("color", "#B8B8B8"),
                    it.optString("category", "base"), it.optString("hint"))
            }
        }
        val controls = json.optJSONArray("surface_controls")
        val surface = json.optJSONObject("surface")
        val targets = json.optJSONArray("targets")
        return MaterialState(objects = catalog("objects"), interaction = json.optString("interaction", "PAINT"), isolate = json.optBoolean("isolate"),
            scope = json.optString("scope", "ALL"), regions = catalog("regions"), brush = json.optString("brush", "ROUND"), brushes = catalog("brushes"),
            paintBlocked = json.optBoolean("paint_blocked"), paintLimit = json.optInt("paint_limit", 20000),
            erase = json.optBoolean("erase"), finish = json.optString("finish", "natural"), finishes = catalog("finishes"), available = json.optBoolean("available"), active = json.optBoolean("active"),
            targets = if (targets == null) emptyList() else (0 until targets.length()).map { targets.optString(it) },
            presets = catalog("presets"), environments = catalog("environments"), preset = json.optString("preset", "plastic"),
            color = json.optString("color", "#E85D38"), environment = json.optString("environment", "studio"),
            radius = json.optDouble("radius", .06).toFloat(), strength = json.optDouble("strength", 1.0).toFloat(),
            paintReady = json.optBoolean("paint_ready"),
            tinted = json.optBoolean("tinted"), custom = json.optBoolean("custom"),
            surface = surface?.keys()?.asSequence()?.associateWith { surface.optDouble(it).toFloat() }.orEmpty(),
            surfaceControls = if (controls == null) emptyList() else (0 until controls.length())
                .mapNotNull { controls.optJSONObject(it) }.map {
                    SurfaceControl(it.optString("id"), it.optString("label"), it.optString("low"), it.optString("high"),
                        it.optDouble("min", 0.0).toFloat(), it.optDouble("max", 1.0).toFloat())
                },
            grain = json.optString("grain", "none"), grains = catalog("grains"),
            grainScale = json.optDouble("grain_scale", 20.0).toFloat(),
            grainAmount = json.optDouble("grain_amount", .5).toFloat(),
            grainRelief = json.optDouble("grain_relief", .35).toFloat())
    }
}
