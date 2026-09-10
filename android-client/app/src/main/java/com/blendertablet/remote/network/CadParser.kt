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
        strings(j.optJSONArray("entities")).filter { it in listOf("LINE", "RECTANGLE", "SQUARE", "CIRCLE", "ARC") },
        strings(j.optJSONArray("features")).filter { it in listOf("EXTRUDE", "CUT") },
        strings(j.optJSONArray("constraints")).filter { it in listOf("COINCIDENT", "HORIZONTAL", "VERTICAL", "PARALLEL", "PERPENDICULAR", "TANGENT", "EQUAL", "DISTANCE", "RADIUS", "FIX", "MIDPOINT", "SYMMETRIC") },
        j.optBoolean("sketch_editing"))
    fun state(j: JSONObject?): CadState {
        if (j == null || j.optInt("version") != 1) return CadState()
        val document = j.optJSONObject("document")
        val session = j.optJSONObject("session")
        val selection = j.optJSONObject("selection")
        val surface = j.optJSONObject("surface")
        return CadState(
            history = objects(document?.optJSONArray("history")).map { CadHistoryNode(it.optString("id"),it.optString("kind"),it.optString("name"),it.optString("body_id"),it.id("sketch_id")) },
            surface = CadSurface(surface?.optString("mode", "PROFILE") ?: "PROFILE",
                objects(surface?.optJSONArray("selection")).map { CadSurfaceItem(it.optString("id"),it.optString("kind"),it.optString("object"),it.id("feature_id"),it.optBoolean("planar")) },
                objects(surface?.optJSONArray("measurements")).mapNotNull { m -> m.optDouble("value").takeIf { it.isFinite() }?.let { CadMeasurement(m.optString("label"),it,m.optString("unit")) } },
                surface?.optBoolean("can_sketch") == true),
            workspace = j.optBoolean("workspace"), isolated = j.optBoolean("isolated"),
            revision = document?.optLong("revision", 0) ?: 0, documentId = document?.id("id"),
            sketches = objects(document?.optJSONArray("sketches")).map { sketch ->
                CadSketch(sketch.optString("id"), sketch.optString("name", "Boceto"), sketch.optString("plane", "XY"),
                    objects(sketch.optJSONArray("entities")).map { entity ->
                        CadEntity(entity.optString("id"), entity.optString("type"),
                            listOf("x", "y", "width", "height", "diameter", "x2", "y2", "radius", "start", "sweep", "length").mapNotNull { key ->
                                entity.optDouble(key).takeIf { it.isFinite() }?.let { key to it }
                            }.toMap(), entity.optBoolean("construction"),
                            objects(entity.optJSONArray("dimensions")).map { d -> CadMeasure(d.optString("field"),d.optString("label"),d.optString("constraint_type"),
                                d.optDouble("value_factor",1.0), objects(d.optJSONArray("refs")).map { CadSelection(it.optString("id"),it.optString("part","BODY")) },
                                strings(d.optJSONArray("constraint_ids"))) }, entity.optBoolean("is_fillet"),entity.optBoolean("is_square"),entity.optBoolean("reference"))
                    }, objects(sketch.optJSONArray("profiles")).map { CadProfile(it.optString("id"), it.optString("entity_id"), it.optString("label", "Perfil")) },
                    objects(sketch.optJSONArray("constraints")).map { c -> CadConstraint(c.optString("id"), c.optString("type"),
                        c.optDouble("value").takeIf { it.isFinite() }, objects(c.optJSONArray("refs")).map { it.optString("id") },
                        objects(c.optJSONArray("refs")).map { CadSelection(it.optString("id"),it.optString("part","BODY")) }) },
                    sketch.optBoolean("visible",true),sketch.optString("body_id"),sketch.id("plane_id"),sketch.optString("plane_label",sketch.optString("plane","XY")))
            },
            features = objects(document?.optJSONArray("features")).map { CadFeature(it.optString("id"), it.optString("name", "Extrusión"),
                it.optString("sketch_id"), it.optString("profile_id"), it.optDouble("depth", 0.02), it.optBoolean("enabled", true), it.optString("type", "EXTRUDE"), it.id("target_id"), it.optString("body_id")) },
            activeSketchId = j.id("active_sketch_id"), selectionKind = selection?.id("kind"), selectionId = selection?.id("id"),
            sessionActive = session?.optBoolean("active") == true, sessionId = session?.id("id"), canConfirm = session?.optBoolean("can_confirm", true) == true, operation = session?.optString("operation").orEmpty(),
            depth = session?.optDouble("depth", 0.02) ?: 0.02,
            overlay = objects(j.optJSONArray("overlay")).map { item ->
                val points = item.optJSONArray("points")
                CadOverlay(item.optString("id"), if (points == null) emptyList() else (0 until points.length()).mapNotNull { index ->
                    val p = points.optJSONArray(index)
                    val x = p?.optDouble(0) ?: Double.NaN; val y = p?.optDouble(1) ?: Double.NaN
                    if (x.isFinite() && y.isFinite()) x.toFloat() to y.toFloat() else null
                }, item.optBoolean("closed"), item.optBoolean("selected"),
                    objects(item.optJSONArray("handles")).mapNotNull { h ->
                        val p = h.optJSONArray("point"); val x = p?.optDouble(0) ?: Double.NaN; val y = p?.optDouble(1) ?: Double.NaN
                        if (x.isFinite() && y.isFinite()) CadHandle(h.optString("part"), x.toFloat() to y.toFloat(), h.optBoolean("selected")) else null
                    }, strings(item.optJSONArray("selected_parts")), item.optBoolean("construction"), item.id("label"),
                    item.optJSONArray("label_point")?.let { p ->
                        val x=p.optDouble(0); val y=p.optDouble(1)
                        if (x.isFinite() && y.isFinite()) x.toFloat() to y.toFloat() else null
                    },
                    item.optDouble("label_offset",14.0).toFloat())
            }, error = j.id("error"),
            selection = objects(selection?.optJSONArray("items")).map { CadSelection(it.optString("id"), it.optString("part", "BODY")) },
            step = j.optDouble("step", .001).takeIf { it.isFinite() && it > 0 } ?: .001,
            increment = j.optBoolean("increment", true), transparent = session?.optBoolean("transparent") == true,
            dimensionOptions = listOf("DISTANCE", "RADIUS").mapNotNull { type ->
                j.optJSONObject("dimension_options")?.optJSONObject(type)?.let { option ->
                    option.optDouble("value").takeIf { it.isFinite() && it > 0 }?.let { type to CadDimensionOption(it,option.id("constraint_id")) }
                }
            }.toMap(),
            construction = j.optBoolean("construction"), showScene = j.optBoolean("show_scene"), activeBodyId = j.id("active_body_id"),
            bodies = objects(document?.optJSONArray("bodies")).map { CadBody(it.optString("id"),it.optString("name")) },
            planes = objects(document?.optJSONArray("planes")).map { p -> CadPlane(p.optString("id"),p.optString("name"),
                (0..2).map { p.optJSONArray("translation")?.optDouble(it,0.0) ?: 0.0 },
                (0..2).map { p.optJSONArray("rotation")?.optDouble(it,0.0) ?: 0.0 }) },
        )
    }
}
