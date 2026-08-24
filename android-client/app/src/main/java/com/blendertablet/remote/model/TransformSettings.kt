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
 * y el backend **solo los admite en MOVE**: girar o escalar "hacia un vértice" no
 * significa nada. [forMode] es quien impone esa regla, para no ofrecer un control que
 * el servidor rechazaría con `wrong_tool`.
 */
enum class SnapType(val label: String, val geometric: Boolean = false) {
    NONE("Sin snap"),
    INCREMENT("Incremento"),
    GRID("Rejilla"),
    VERTEX("Vértice", geometric = true),
    EDGE("Arista", geometric = true),
    FACE("Cara", geometric = true),
    CURSOR("Cursor", geometric = true);

    companion object {
        fun forMode(mode: TransformMode): List<SnapType> =
            if (mode == TransformMode.MOVE) entries else listOf(NONE, INCREMENT, GRID)
    }
}

/**
 * El candidato geométrico que el servidor encontró bajo el dedo, para poder decir a
 * qué se está pegando el movimiento sin tapar la selección.
 */
data class SnapCandidate(
    val type: SnapType,
    val id: String,
    val objectName: String?,
)

/** Relativo = delta desde el snapshot de inicio; absoluto = valor objetivo. */
enum class ValueMode(val label: String) {
    RELATIVE("Relativo"),
    ABSOLUTE("Absoluto"),
}
