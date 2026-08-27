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
    KNIFE("KNIFE", "Cuchillo", "necesita una malla"),
    BISECT("BISECT", "Bisect", "necesita una malla");

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

/** Línea de arrastre de una sesión Bisect, en coordenadas de pantalla normalizadas. */
data class DragLine(val start: List<Double>, val end: List<Double>)

/**
 * Sesión de herramienta paramétrica en curso, tal como la cuenta el servidor.
 *
 * [parameters] es lo que se ha fijado; la clave primaria es `offset` (extrude/bevel),
 * `thickness` (inset), `cuts` (subdivide) o `factor` (loop cut). Los valores llegan
 * tipados: números como Double, opciones del modal (even/flip/clamp) como Boolean y
 * `falloff` como String.
 *
 * [armed] es la familia elegida (B1) esperando el primer toque/arrastre del viewport
 * (Loop Cut, Bisect): sin backup ni preview todavía, `active` sigue en `false`. Puede
 * estar armada sin estar activa, o activa (lo que implica armada). [tool]/[parameters]
 * ya vienen rellenos en ese estado, para que la barra muestre el icono marcado.
 */
data class ToolSession(
    val active: Boolean = false,
    val armed: Boolean = false,
    val tool: EditTool = EditTool.EXTRUDE,
    val parameters: Map<String, Any?> = emptyMap(),
    /** Knife: puntos confirmados por el servidor, en coordenadas locales. */
    val points: List<List<Double>> = emptyList(),
    /** Knife: la polilínea está cerrada. */
    val closed: Boolean = false,
    /** Bisect: última línea de arrastre resuelta por el servidor. */
    val line: DragLine? = null,
) {
    val primaryKey: String
        get() = when (tool) {
            EditTool.EXTRUDE, EditTool.BEVEL -> "offset"
            EditTool.INSET -> "thickness"
            EditTool.SUBDIVIDE -> "cuts"
            EditTool.LOOP_CUT -> "factor"
            EditTool.BRIDGE_EDGE_LOOPS -> "twist_offset"
            EditTool.KNIFE, EditTool.BISECT -> ""
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

/**
 * Barra izquierda de tools activas de Edit Mode (`edit_toolbar`).
 *
 * A diferencia de [EditCatalog] (agrupado por submodo, acciones discretas), esto
 * agrupa por familia con la lógica de Blender: una familia arma una variante y
 * permanece marcada mientras hay sesión armada o activa. Convive con [EditCatalog]:
 * un servidor sin esta feature sigue sirviendo solo el catálogo legacy.
 */
data class EditToolbar(
    val families: List<EditToolbarFamily> = emptyList(),
) {
    val available: Boolean get() = families.isNotEmpty()
}

data class EditToolbarFamily(
    val id: String,
    val label: String,
    val defaultVariant: String,
    /** Comando fijo (normalmente `tool.begin`) y su payload base (p. ej. `tool`). */
    val command: String?,
    val payload: Map<String, Any?> = emptyMap(),
    /** `PARAMETRIC`, `VIEWPORT_TAP`, `VIEWPORT_POLYLINE` o `VIEWPORT_DRAG_LINE`. */
    val input: String = "PARAMETRIC",
    val requirements: Map<String, Any?> = emptyMap(),
    val variants: List<EditToolbarVariant> = emptyList(),
    /** Parámetros compartidos por todas las variantes; cada variante puede sumar los suyos. */
    val parameters: List<EditCatalogParameter> = emptyList(),
)

data class EditToolbarVariant(
    val id: String,
    val label: String,
    val enabled: Boolean = true,
    val input: String? = null,
    /** Payload propio, fundido sobre el de la familia (p. ej. distinto `tool`). */
    val payload: Map<String, Any?> = emptyMap(),
    val requirements: Map<String, Any?> = emptyMap(),
    val parameters: List<EditCatalogParameter> = emptyList(),
)
