package com.blendertablet.remote.network

import com.blendertablet.remote.model.SculptBrush
import com.blendertablet.remote.model.SculptState
import org.json.JSONObject

object SculptParser {
    fun state(json: JSONObject?): SculptState {
        if (json == null) return SculptState()
        val symmetry = json.optJSONObject("symmetry")
        val dyntopo = json.optJSONObject("dyntopo")
        val multires = json.optJSONObject("multires")
        val brushes = json.optJSONArray("brushes")
        return SculptState(
            available = json.optBoolean("available"), active = json.optBoolean("active"),
            brush = json.optString("brush", "DRAW"),
            radius = number(json, "radius", .04f, .002f, .3f),
            radiusMeters = json.optDouble("radius_meters").takeIf { it.isFinite() && it > 0 },
            strength = number(json, "strength", .5f, 0f, 1f),
            pressureStrength = json.optBoolean("pressure_strength", true),
            pressureSize = json.optBoolean("pressure_size", false),
            symmetryX = symmetry?.optBoolean("x", true) ?: true,
            symmetryY = symmetry?.optBoolean("y", false) ?: false,
            symmetryZ = symmetry?.optBoolean("z", false) ?: false,
            dyntopoEnabled = dyntopo?.optBoolean("enabled") ?: false,
            dyntopoDetail = number(dyntopo, "detail", 12f, 1f, 40f),
            multiresName = multires?.optString("name")?.takeIf { it.isNotBlank() && it != "null" },
            multiresLevel = multires?.optInt("level", 0)?.coerceAtLeast(0) ?: 0,
            multiresTotalLevels = multires?.optInt("total_levels", 0)?.coerceAtLeast(0) ?: 0,
            brushes = (0 until (brushes?.length() ?: 0)).mapNotNull { index ->
                brushes?.optJSONObject(index)?.let {
                    val id = it.optString("id")
                    if (id.isBlank()) null else SculptBrush(id, it.optString("label", id), it.optString("icon", id))
                }
            },
        )
    }
    private fun number(json: JSONObject?, key: String, fallback: Float, min: Float, max: Float): Float =
        json?.optDouble(key, fallback.toDouble())?.toFloat()?.takeIf { it.isFinite() }?.coerceIn(min, max) ?: fallback
}
