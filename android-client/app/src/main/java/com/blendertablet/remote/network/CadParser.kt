package com.blendertablet.remote.network

import com.blendertablet.remote.model.*
import org.json.JSONArray
import org.json.JSONObject

object CadParser {
    private fun objects(a: JSONArray?) = if (a == null) emptyList() else
        (0 until a.length()).mapNotNull { a.optJSONObject(it) }
    private fun strings(a: JSONArray?) = if (a == null) emptyList() else
        (0 until a.length()).map { a.optString(it) }
    private fun JSONObject.id(key: String) = optString(key).takeIf { it.isNotBlank() && it != "null" }
    fun capabilities(j: JSONObject?): CadCapabilities = if (j == null || j.optInt("version") != 1 ||
        j.optString("length_unit") != "METERS") CadCapabilities() else CadCapabilities(1,
        strings(j.optJSONArray("planes")).filter { it in listOf("XY", "XZ", "YZ") },
        strings(j.optJSONArray("entities")).filter { it in listOf("LINE", "RECTANGLE", "CIRCLE") },
        strings(j.optJSONArray("features")).filter { it == "EXTRUDE" })
    fun state(j: JSONObject?): CadState {
        if (j == null || j.optInt("version") != 1) return CadState()
        val document = j.optJSONObject("document")
        val session = j.optJSONObject("session")
        val selection = j.optJSONObject("selection")
        return CadState(
            workspace = j.optBoolean("workspace"), isolated = j.optBoolean("isolated"),
            revision = document?.optLong("revision", 0) ?: 0, documentId = document?.id("id"),
            sketches = objects(document?.optJSONArray("sketches")).map { sketch ->
                CadSketch(sketch.optString("id"), sketch.optString("name", "Boceto"), sketch.optString("plane", "XY"),
                    objects(sketch.optJSONArray("entities")).map { entity ->
                        CadEntity(entity.optString("id"), entity.optString("type"),
                            listOf("x", "y", "width", "height", "diameter", "x2", "y2").mapNotNull { key ->
                                entity.optDouble(key).takeIf { it.isFinite() }?.let { key to it }
                            }.toMap())
                    }, objects(sketch.optJSONArray("profiles")).map { CadProfile(it.optString("id"), it.optString("entity_id"), it.optString("label", "Perfil")) })
            },
            features = objects(document?.optJSONArray("features")).map { CadFeature(it.optString("id"), it.optString("name", "Extrusión"),
                it.optString("sketch_id"), it.optString("profile_id"), it.optDouble("depth", 0.02), it.optBoolean("enabled", true)) },
            activeSketchId = j.id("active_sketch_id"), selectionKind = selection?.id("kind"), selectionId = selection?.id("id"),
            sessionActive = session?.optBoolean("active") == true, canConfirm = session?.optBoolean("can_confirm", true) == true, operation = session?.optString("operation").orEmpty(),
            depth = session?.optDouble("depth", 0.02) ?: 0.02,
            overlay = objects(j.optJSONArray("overlay")).map { item ->
                val points = item.optJSONArray("points")
                CadOverlay(item.optString("id"), if (points == null) emptyList() else (0 until points.length()).mapNotNull { index ->
                    val p = points.optJSONArray(index)
                    val x = p?.optDouble(0) ?: Double.NaN; val y = p?.optDouble(1) ?: Double.NaN
                    if (x.isFinite() && y.isFinite()) x.toFloat() to y.toFloat() else null
                }, item.optBoolean("closed"), item.optBoolean("selected"))
            }, error = j.id("error"),
        )
    }
}
