package com.blendertablet.remote.model

/** CAD is a workspace, never a Blender mesh selection mode. Lengths on wire are meters. */
data class CadCapabilities(
    val version: Int = 0,
    val planes: List<String> = emptyList(),
    val entities: List<String> = emptyList(),
    val features: List<String> = emptyList(),
) { val available get() = version == 1 && planes.isNotEmpty() }
data class CadEntity(val id: String, val type: String, val values: Map<String, Double>)
data class CadProfile(val id: String, val entityId: String, val label: String)
data class CadSketch(val id: String, val name: String, val plane: String,
    val entities: List<CadEntity>, val profiles: List<CadProfile>)
data class CadFeature(val id: String, val name: String, val sketchId: String,
    val profileId: String, val depth: Double, val enabled: Boolean)
data class CadOverlay(val id: String, val points: List<Pair<Float, Float>>, val closed: Boolean, val selected: Boolean)
data class CadState(
    val workspace: Boolean = false,
    val isolated: Boolean = false,
    val revision: Long = 0,
    val documentId: String? = null,
    val sketches: List<CadSketch> = emptyList(),
    val features: List<CadFeature> = emptyList(),
    val activeSketchId: String? = null,
    val selectionKind: String? = null,
    val selectionId: String? = null,
    val sessionActive: Boolean = false,
    val canConfirm: Boolean = false,
    val operation: String = "",
    val depth: Double = 0.02,
    val overlay: List<CadOverlay> = emptyList(),
    val error: String? = null,
) {
    val activeSketch get() = sketches.firstOrNull { it.id == activeSketchId }
    val selectedEntity get() = sketches.flatMap { it.entities }.firstOrNull { selectionKind == "ENTITY" && it.id == selectionId }
    val selectedFeature get() = features.firstOrNull { selectionKind == "FEATURE" && it.id == selectionId }
}
