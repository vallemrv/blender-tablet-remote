package com.blendertablet.remote.ui

import com.blendertablet.remote.model.CadState

/** Stable entity IDs, including complete figures picked by a center or endpoint.
 * The backend checks that the selected lines/arcs actually close their contours.
 */
internal fun cadCutSelection(cad: CadState): List<String> {
    val sketch = cad.activeSketch ?: return emptyList()
    if (cad.selectionKind != "ENTITY" || cad.surface.mode != "PROFILE") return emptyList()
    val ids = cad.selection.map { it.id }.distinct()
    if (ids.any { id -> sketch.entities.none { it.id == id && !it.construction && it.type != "POINT" } }) return emptyList()
    return ids
}
