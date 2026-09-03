package com.blendertablet.remote.model

/**
 * Restricción de la transformación: qué ejes participan en el movimiento.
 *
 * En MOVE/SCALE se combinan ejes para formar planos (XY, XZ, YZ). En ROTATE no hay
 * planos: un giro es siempre alrededor de UN eje, así que ahí la restricción solo
 * puede ser libre o de un eje. Lo impone [forMode].
 */
enum class Constraint(val label: String) {
    FREE("Libre"),
    X("X"), Y("Y"), Z("Z"),
    XY("XY"), XZ("XZ"), YZ("YZ");

    val axes: Set<Axis>
        get() = when (this) {
            FREE -> emptySet()
            X -> setOf(Axis.X)
            Y -> setOf(Axis.Y)
            Z -> setOf(Axis.Z)
            XY -> setOf(Axis.X, Axis.Y)
            XZ -> setOf(Axis.X, Axis.Z)
            YZ -> setOf(Axis.Y, Axis.Z)
        }

    companion object {
        /** Restricción correspondiente a un conjunto de ejes; por contrato es única. */
        fun ofAxes(axes: Set<Axis>): Constraint {
            val sorted = axes.sortedBy { it.ordinal }
            return when (sorted) {
                emptyList<Axis>() -> FREE
                listOf(Axis.X) -> X
                listOf(Axis.Y) -> Y
                listOf(Axis.Z) -> Z
                listOf(Axis.X, Axis.Y) -> XY
                listOf(Axis.X, Axis.Z) -> XZ
                listOf(Axis.Y, Axis.Z) -> YZ
                // Un conjunto de tres ejes equivale a libre.
                else -> FREE
            }
        }

        /** Las restricciones válidas para un modo. ROTATE solo admite un eje. */
        fun forMode(mode: TransformMode): List<Constraint> =
            if (mode == TransformMode.ROTATE) listOf(FREE, X, Y, Z) else entries
    }
}

/** Orientación de los ejes de la transformación. */
enum class Orientation(val label: String) {
    GLOBAL("Global"),
    LOCAL("Local"),
    VIEW("Vista"),
    NORMAL("Normal"),
}

/**
 * Tipo de snap. El nombre viaja tal cual como `snap_type`.
 *
 * Los geométricos se resuelven con un rayo desde el dedo (`transform.snap_candidate`),
 * En MOVE alinean source→target; ROTATE alinea direcciones desde center y SCALE
 * resuelve su cociente. Todos conservan solo destinos exactos.
 */
enum class SnapType(val label: String, val geometric: Boolean = false) {
    NONE("Sin snap"),
    INCREMENT("Incremento"),
    GRID("Rejilla"),
    VERTEX("Vértice", geometric = true),
    EDGE("Arista", geometric = true),
    EDGE_CENTER("Centro arista", geometric = true),
    FACE("Cara", geometric = true),
    FACE_CENTER("Centro cara", geometric = true),
    CURSOR("Cursor", geometric = true);

    companion object {
        fun forMode(mode: TransformMode): List<SnapType> =
            listOf(NONE, INCREMENT, VERTEX, EDGE_CENTER, FACE_CENTER)
    }
}

enum class TransformStepUnit(val label: String) {
    MM("mm"), CM("cm"), M("m"), PERCENT("%")
}

/** Cómo se mueve el elemento arrastrado con Tweak. Viaja como `motion`. */
enum class TweakMotion(val label: String) {
    FREE("Libre"),
    /** El `GG` de Blender: el vértice no sale de una de sus aristas. */
    SLIDE("Solo aristas"),
}

/**
 * Ajustes del gesto de Tweak. Viven fuera de la sesión porque el gesto es tan corto
 * que no da tiempo a configurarlo mientras dura: se eligen antes, en el rail, y el
 * BEGIN los manda enteros.
 */
data class TweakSettings(
    val motion: TweakMotion = TweakMotion.FREE,
    val snapType: SnapType = SnapType.NONE,
    /** Fracción del riel con SLIDE; unidades de escena con FREE. */
    val snapStep: Double = 0.1,
    /** Con SLIDE, impide que el vértice se salga del segmento. */
    val clamp: Boolean = true,
) {
    /**
     * Deslizar por una arista ya decide el destino, así que el backend degrada ahí los
     * destinos geométricos a NONE. Se refleja aquí para no prometer en la UI un snap
     * que el gesto no va a aplicar.
     */
    val effectiveSnapType: SnapType
        get() = if (motion == TweakMotion.SLIDE && snapType.geometric) SnapType.NONE else snapType
}

/**
 * El candidato geométrico que el servidor encontró bajo el dedo, para poder decir a
 * qué se está pegando el movimiento sin tapar la selección.
 */
data class SnapCandidate(
    val type: SnapType,
    val id: String,
    val objectName: String?,
    /** Posición mundial/local informativa, si el servidor la publica. */
    val position: List<Double> = emptyList(),
    /** Centro del marcador en coordenadas normalizadas del viewport. */
    val screen: List<Double> = emptyList(),
    val distance: Double? = null,
)

/** Relativo = delta desde el snapshot de inicio; absoluto = valor objetivo. */
enum class ValueMode(val label: String) {
    RELATIVE("Relativo"),
    ABSOLUTE("Absoluto"),
}
