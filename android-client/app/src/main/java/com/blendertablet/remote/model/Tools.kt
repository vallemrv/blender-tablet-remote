package com.blendertablet.remote.model

/**
 * Herramientas paramétricas de Edit Mode (Extrude, Bevel, Inset, Subdivide).
 *
 * El rail elige la herramienta y abre una sesión `tool.*` en el backend; el footer
 * muestra sus parámetros y el preview se reconstruye desde una copia BMesh, así que
 * confirmar deja un único undo y cancelar restaura la topología exacta.
 */
enum class EditTool(val wire: String, val label: String, val requirement: String) {
    EXTRUDE("EXTRUDE", "Extruir", "necesita selección"),
    BEVEL("BEVEL", "Bisel", "necesita selección"),
    INSET("INSET", "Inset", "necesita caras"),
    SUBDIVIDE("SUBDIVIDE", "Subdividir", "necesita aristas"),
    LOOP_CUT("LOOP_CUT", "Loop Cut", "necesita una arista");

    companion object {
        fun fromWire(value: String?): EditTool? = entries.firstOrNull { it.wire == value }
    }
}

/**
 * Sesión de herramienta paramétrica en curso, tal como la cuenta el servidor.
 *
 * [parameters] es lo que se ha fijado; la clave primaria es `offset` (extrude/bevel),
 * `thickness` (inset) o `cuts` (subdivide).
 */
data class ToolSession(
    val active: Boolean = false,
    val tool: EditTool = EditTool.EXTRUDE,
    val parameters: Map<String, Double> = emptyMap(),
) {
    val primaryKey: String
        get() = when (tool) {
            EditTool.EXTRUDE, EditTool.BEVEL -> "offset"
            EditTool.INSET -> "thickness"
            EditTool.SUBDIVIDE -> "cuts"
            EditTool.LOOP_CUT -> "factor"
        }
}
