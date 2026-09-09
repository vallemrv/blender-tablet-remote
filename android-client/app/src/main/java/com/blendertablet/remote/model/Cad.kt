package com.blendertablet.remote.model

/** CAD is a workspace, never a Blender mesh selection mode. Lengths on wire are meters. */
data class CadCapabilities(
    val version: Int = 0,
    val planes: List<String> = emptyList(),
    val entities: List<String> = emptyList(),
    val features: List<String> = emptyList(),
    val constraints: List<String> = emptyList(),
    val sketchEditing: Boolean = false,
) { val available get() = version == 1 && planes.isNotEmpty() }
data class CadEntity(val id: String, val type: String, val values: Map<String, Double>)
data class CadProfile(val id: String, val entityId: String, val label: String)
data class CadSketch(val id: String, val name: String, val plane: String,
    val entities: List<CadEntity>, val profiles: List<CadProfile>,
    val constraints: List<CadConstraint> = emptyList())
data class CadConstraint(val id: String, val type: String, val value: Double?, val entityIds: List<String>)
data class CadSelection(val id: String, val part: String = "BODY")
data class CadFeature(val id: String, val name: String, val sketchId: String,
    val profileId: String, val depth: Double, val enabled: Boolean,
    val type: String = "EXTRUDE", val targetId: String? = null)
data class CadHandle(val part: String, val point: Pair<Float, Float>, val selected: Boolean)
data class CadOverlay(val id: String, val points: List<Pair<Float, Float>>, val closed: Boolean, val selected: Boolean,
    val handles: List<CadHandle> = emptyList(), val selectedParts: List<String> = emptyList())
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
    val sessionId: String? = null,
    val canConfirm: Boolean = false,
    val operation: String = "",
    val depth: Double = 0.02,
    val overlay: List<CadOverlay> = emptyList(),
    val error: String? = null,
    val selection: List<CadSelection> = emptyList(),
    val step: Double = .001,
    val increment: Boolean = true,
    val transparent: Boolean = false,
) {
    val activeSketch get() = sketches.firstOrNull { it.id == activeSketchId }
    val selectedEntity get() = sketches.flatMap { it.entities }.firstOrNull { selectionKind == "ENTITY" && it.id == selectionId }
    val selectedFeature get() = features.firstOrNull { selectionKind == "FEATURE" && it.id == selectionId }
    /** Resolve the source document sketch, including profiles made from several entities. */
    val selectedSketch get() = sketches.firstOrNull { sketch ->
        when (selectionKind) {
            "PROFILE" -> sketch.profiles.any { it.id == selectionId }
            "ENTITY" -> sketch.entities.any { it.id == selectionId }
            "FEATURE" -> sketch.id == selectedFeature?.sketchId
            else -> false
        }
    }
}
