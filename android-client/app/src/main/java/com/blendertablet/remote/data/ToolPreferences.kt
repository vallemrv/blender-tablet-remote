package com.blendertablet.remote.data

import android.content.Context
import com.blendertablet.remote.model.EditTool
import org.json.JSONObject

/** Only successful, reusable settings; never IDs, selections, picked points or loop position. */
class ToolPreferences(context: Context) {
    private val prefs = context.getSharedPreferences("edit_tool_values", Context.MODE_PRIVATE)
    private fun key(tool: EditTool, parameters: Map<String, Any?>) = tool.name + ":" + (parameters["variant"] ?: "DEFAULT")
    fun save(tool: EditTool, parameters: Map<String, Any?>, scale: Double) {
        val safe = reusableToolValues(tool, parameters, scale, true)
        prefs.edit().putString(key(tool, parameters), JSONObject(safe).toString()).apply()
    }
    fun restore(tool: EditTool, defaults: Map<String, Any?>, scale: Double): Map<String, Any?> {
        val saved = runCatching { JSONObject(prefs.getString(key(tool, defaults), "{}")!!) }.getOrDefault(JSONObject())
        val values = saved.keys().asSequence().associateWith { saved.get(it) }
        val restored = reusableToolValues(tool, values, scale, false)
        return (defaults + restored).let { if (restored.keys.any { key -> key in setOf("offset", "thickness") }) it - "auto_size" else it }
    }
}

internal fun reusableToolValues(tool: EditTool, source: Map<String, Any?>, scale: Double, store: Boolean): Map<String, Any?> {
    val keys = when (tool) {
        EditTool.LOOP_CUT -> setOf("cuts", "smoothness", "falloff", "even", "flip", "clamp")
        EditTool.BEVEL -> setOf("offset", "segments", "profile", "miter_outer")
        EditTool.EXTRUDE -> setOf("offset", "constraint", "orientation", "rotate_source")
        EditTool.INSET -> setOf("thickness", "depth", "boundary")
        EditTool.BRIDGE_EDGE_LOOPS -> setOf("twist_offset", "merge", "merge_factor")
        EditTool.SUBDIVIDE -> setOf("cuts", "smoothness")
        EditTool.F2, EditTool.DRAW, EditTool.CONNECT -> emptySet()
        EditTool.KNIFE -> setOf("snap", "snap_mode")
        EditTool.BISECT -> setOf("fill", "clear_inner", "clear_outer", "snap")
        EditTool.REVOLVE -> setOf("angle", "steps", "axis", "merge")
        EditTool.SWEEP -> setOf("width", "depth", "caps")
        EditTool.ALIGN -> setOf("mode", "twist", "gap")
    } + setOf("snap_type", "snap_step")
    val lengths = when (tool) {
        EditTool.EXTRUDE, EditTool.BEVEL -> setOf("offset", "snap_step")
        EditTool.INSET -> setOf("thickness", "depth", "snap_step")
        EditTool.SWEEP -> setOf("width", "depth")
        EditTool.ALIGN -> setOf("gap")
        else -> emptySet()
    }
    return source.filter { (key, value) -> key in keys &&
        (value is String || value is Boolean || value is Number && value.toDouble().isFinite()) }.mapValues { (key,value) ->
        if (key in lengths && value is Number) value.toDouble() * if (store) scale else 1.0 / scale.coerceAtLeast(1e-12) else value
    }
}
