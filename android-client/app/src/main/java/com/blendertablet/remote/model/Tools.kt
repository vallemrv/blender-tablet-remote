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
    LOOP_CUT("LOOP_CUT", "Loop Cut", "necesita una arista"),
    BRIDGE_EDGE_LOOPS("BRIDGE_EDGE_LOOPS", "Bridge Edge Loops", "necesita dos loops de aristas"),
    KNIFE("KNIFE", "Cuchillo", "necesita una malla");

    companion object {
        fun fromWire(value: String?): EditTool? = entries.firstOrNull { it.wire == value }
    }
}

/**
 * Perfil del corte (`falloff` del Ctrl+R): la forma con la que el corte interpola
 * la malla. Los nombres viajan tal cual al servidor.
 */
enum class LoopFalloff(val wire: String, val label: String) {
    SMOOTH("SMOOTH", "Suave"),
    SPHERE("SPHERE", "Esfera"),
    ROOT("ROOT", "Raíz"),
    SHARP("SHARP", "Afilado"),
    LINEAR("LINEAR", "Lineal"),
    INVERSE_SQUARE("INVERSE_SQUARE", "Inv.²");

    companion object {
        fun fromWire(value: String?): LoopFalloff? = entries.firstOrNull { it.wire == value }
    }

    /** Siguiente del ciclo, para el botón que recorre los perfiles sin teclado. */
    fun next(): LoopFalloff = entries[(ordinal + 1) % entries.size]
}

/**
 * Sesión de herramienta paramétrica en curso, tal como la cuenta el servidor.
 *
 * [parameters] es lo que se ha fijado; la clave primaria es `offset` (extrude/bevel),
 * `thickness` (inset), `cuts` (subdivide) o `factor` (loop cut). Los valores llegan
 * tipados: números como Double, opciones del modal (even/flip/clamp) como Boolean y
 * `falloff` como String.
 */
data class ToolSession(
    val active: Boolean = false,
    val tool: EditTool = EditTool.EXTRUDE,
    val parameters: Map<String, Any?> = emptyMap(),
    /** Knife: puntos confirmados por el servidor, en coordenadas locales. */
    val points: List<List<Double>> = emptyList(),
    /** Knife: la polilínea está cerrada. */
    val closed: Boolean = false,
) {
    val primaryKey: String
        get() = when (tool) {
            EditTool.EXTRUDE, EditTool.BEVEL -> "offset"
            EditTool.INSET -> "thickness"
            EditTool.SUBDIVIDE -> "cuts"
            EditTool.LOOP_CUT -> "factor"
            EditTool.BRIDGE_EDGE_LOOPS -> "twist_offset"
            EditTool.KNIFE -> ""
        }

    fun double(key: String): Double? = (parameters[key] as? Number)?.toDouble()
    fun flag(key: String, default: Boolean = false): Boolean = (parameters[key] as? Boolean) ?: default
    fun falloff(default: LoopFalloff = LoopFalloff.SMOOTH): LoopFalloff =
        (parameters["falloff"] as? String)?.let(LoopFalloff::fromWire) ?: default
}

/** Resultado de `mesh.loop_probe`: la arista y el punto donde cae el toque. */
data class LoopProbe(
    val hit: Boolean = false,
    val edge: Int = -1,
    /** −1..1: coloca el corte del medio exactamente donde se tocó. */
    val factor: Double = 0.0,
    val ring: Int = 0,
)
