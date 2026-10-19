package com.blendertablet.remote.model

/** The renderer and its tests consume the same parameter groups, including More. */
data class ToolTrayContents(val visible: List<String>, val advanced: List<String>) {
    init { require(visible.size <= 5); require(visible.toSet().size == visible.size) }
}

fun toolTrayContents(session: ToolSession, selection: SelectionMode = SelectionMode.EDGE): ToolTrayContents {
    if (session.controls.isNotEmpty()) {
        val primary = session.controls.filter { it.primary }.ifEmpty { session.controls.take(1) }.take(3).map { it.id }
        return ToolTrayContents(primary + "more", session.controls.map { it.id }.filterNot { it in primary })
    }
    return when (session.tool) {
        EditTool.LOOP_CUT -> ToolTrayContents(listOf("cuts", "position") + (if (session.loopCount > 1) listOf("remove_loop") else emptyList()) + "more",
            listOf("even") + (if (session.flag("even")) listOf("flip") else emptyList()) + listOf("clamp", "smoothness") +
                (if ((session.double("smoothness") ?: 0.0) != 0.0) listOf("falloff") else emptyList()) + "snap")
        EditTool.BEVEL -> ToolTrayContents(listOf("offset", "segments", "more"),
            (if ((session.double("segments") ?: 1.0) > 1) listOf("profile") else emptyList()) +
                (if (selection == SelectionMode.EDGE) listOf("miter_outer") else emptyList()) + "snap")
        EditTool.EXTRUDE -> {
            val directed = (session.parameters["variant"] ?: "REGION") in setOf("REGION", "MANIFOLD")
            ToolTrayContents(listOf("offset") + (if (directed) listOf("constraint") else emptyList()) + "more",
                (if (directed && (session.parameters["constraint"] ?: "FREE") != "FREE") listOf("orientation") else emptyList()) + "snap")
        }
        EditTool.INSET -> ToolTrayContents(listOf("thickness", "more"), listOf("depth", "boundary", "snap"))
        EditTool.BRIDGE_EDGE_LOOPS -> ToolTrayContents(listOf("twist_offset", "more"), listOf("merge") +
            (if (session.flag("merge")) listOf("merge_factor") else emptyList()) + "snap")
        EditTool.SUBDIVIDE -> ToolTrayContents(listOf("cuts", "more"), listOf("snap"))
        EditTool.KNIFE -> ToolTrayContents(listOf("undo_point", "new_cut", "close_cut", "more"), listOf("snap"))
        EditTool.BISECT -> ToolTrayContents(listOf("clear_inner", "clear_outer", "more"), listOf("fill", "snap"))
        else -> ToolTrayContents(listOf("more"), emptyList())
    }
}

/** Position percentages are offsets from the centre: 0% is centred, 100% reaches one side. */
fun parseLoopPosition(text: String, currentFactor: Double, rangeMeters: Double): Double? {
    val input = text.trim().lowercase()
    val result = if (input.endsWith("m")) {
        if (rangeMeters <= 0) return null
        val unit = if (input.endsWith("mm")) .001 else if (input.endsWith("cm")) .01 else 1.0
        ValueParser.parseMove(input, currentFactor * rangeMeters / unit)?.div(rangeMeters)
    } else NumericExpression.evaluate(input.removeSuffix("%"), currentFactor * 100)?.div(100)
    return result?.takeIf { it.isFinite() }
}

/** Relative expressions use the unit typed, even when it differs from the displayed preset. */
fun parseToolValue(input: String, current: Double, mode: TransformMode, lengthUnit: LengthUnit?, scale: Double): Double? {
    val text = input.trim().lowercase()
    if (text.isBlank()) return null
    if (mode == TransformMode.MOVE) {
        val explicit = text.endsWith("m")
        val unit = if (explicit) when { text.endsWith("mm") -> "mm"; text.endsWith("cm") -> "cm"; else -> "m" }
            else lengthUnit?.short ?: "m"
        val meters = when (unit) { "mm" -> .001; "cm" -> .01; else -> 1.0 }
        return ValueParser.parseMove(if (explicit) text else text + unit, current * scale / meters)?.div(scale.coerceAtLeast(1e-12))
    }
    return ValueParser.parse(text, mode, if (text.endsWith("%")) current * 100 else current)
}
