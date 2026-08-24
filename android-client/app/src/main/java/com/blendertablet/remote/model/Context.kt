package com.blendertablet.remote.model

/**
 * El contexto que el backend envía para que la UI no tenga que adivinar qué es
 * válido en cada momento (§ modelo de estado requerido del plan).
 *
 * Viene dentro de `scene.get_state` (el servidor lo mezcla en el snapshot) y también
 * como evento `context.changed`.
 */
data class SelectionCounts(
    val objects: Int = 0,
    val verts: Int = 0,
    val edges: Int = 0,
    val faces: Int = 0,
)

/** Proyección de la cámara remota. El servidor puede alternar PERSP/ORTHO. */
enum class Projection { PERSP, ORTHO }

data class ViewState(
    val perspective: Projection = Projection.PERSP,
    val axisView: String? = null,
)

data class SceneContext(
    val selectionCounts: SelectionCounts = SelectionCounts(),
    val availableTools: List<ActiveTool> = emptyList(),
    val availableConstraints: List<Constraint> = emptyList(),
    val availableOrientations: List<Orientation> = emptyList(),
    val availableSnapTypes: List<SnapType> = emptyList(),
    val selectionCenter: List<Float> = emptyList(),
    val selectionNormal: List<Float> = emptyList(),
) {
    /** Hay algo seleccionado en el submodo indicado. */
    fun hasSelection(mode: BlenderMode, selectionMode: SelectionMode): Boolean =
        if (mode == BlenderMode.EDIT) countFor(selectionMode) > 0 else selectionCounts.objects > 0

    /** Cuántos elementos hay seleccionados del submodo indicado. */
    fun countFor(mode: SelectionMode): Int = when (mode) {
        SelectionMode.VERTEX -> selectionCounts.verts
        SelectionMode.EDGE -> selectionCounts.edges
        SelectionMode.FACE -> selectionCounts.faces
    }
}
