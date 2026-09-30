package com.blendertablet.remote.model

/** CAD is a workspace, never a Blender mesh selection mode. Lengths on wire are meters. */
data class CadCapabilities(
    val version: Int = 0,
    val planes: List<String> = emptyList(),
    val entities: List<String> = emptyList(),
    val features: List<String> = emptyList(),
    val constraints: List<String> = emptyList(),
    val sketchEditing: Boolean = false,
    val offsetEntities: List<String> = emptyList(),
    val featureMirror: Boolean = false,
) { val available get() = version == 2 && planes.isNotEmpty() }
data class CadEntity(val id: String, val type: String, val values: Map<String, Double>, val construction: Boolean = false,
    val dimensions: List<CadMeasure> = emptyList(), val isFillet: Boolean = false, val isSquare: Boolean = false, val reference: Boolean = false)
data class CadMeasure(val field: String, val label: String, val constraintType: String,
    val valueFactor: Double, val refs: List<CadSelection>, val constraintIds: List<String>, val lockable: Boolean = true)
data class CadDimensionOption(val value: Double, val constraintId: String?)
data class CadProfile(val id: String, val entityId: String, val label: String)
data class CadSketch(val id: String, val name: String, val plane: String,
    val entities: List<CadEntity>, val profiles: List<CadProfile>,
    val constraints: List<CadConstraint> = emptyList(), val visible: Boolean = true, val bodyId: String = "", val planeId: String? = null, val planeLabel: String = plane)
data class CadConstraint(val id: String, val type: String, val value: Double?, val entityIds: List<String>, val refs: List<CadSelection> = emptyList())
data class CadSelection(val id: String, val part: String = "BODY")
data class CadFeature(val id: String, val name: String, val sketchId: String,
    val profileId: String, val depth: Double, val enabled: Boolean,
    val type: String = "EXTRUDE", val targetId: String? = null, val bodyId: String = "", val extent: String = "ONE",
    /** Redondeo/Chaflán (`FILLET`/`CHAMFER`): ancho, segmentos y aristas elegidas. */
    val width: Double = 0.0, val segments: Int = 1, val edgeCount: Int = 0,
    /** Barrido helicoidal (`HELIX`): paso por vuelta, vueltas, sentido y eje del croquis (X, Y o una línea). */
    val pitch: Double = 0.0, val turns: Double = 0.0, val hand: String = "RIGHT", val axis: String = "Y",
    val mirrorSourceId: String? = null, val mirrorPlane: String = "XZ", val mirrorOffset: Double = 0.0,
    /** Revolución (`REVOLVE`): grados alrededor de su eje (X, Y o una línea del croquis). */
    val angle: Double = 360.0) {
    val isFinish get() = type in listOf("FILLET", "CHAMFER")
    val isMirror get() = mirrorSourceId != null
}
data class CadHandle(val part: String, val point: Pair<Float, Float>, val selected: Boolean, val intent: String = "POINT")
data class CadOverlay(val id: String, val points: List<Pair<Float, Float>>, val closed: Boolean, val selected: Boolean,
    val handles: List<CadHandle> = emptyList(), val selectedParts: List<String> = emptyList(), val construction: Boolean = false,
    val label: String? = null, val labelPoint: Pair<Float, Float>? = null, val labelOffset: Float = 14f,
    val kind: String = "ENTITY", val labelBox: List<Float> = emptyList(),
    val dimensionLines: List<List<Pair<Float, Float>>> = emptyList(), val arrows: List<List<Pair<Float, Float>>> = emptyList())
data class CadBody(val id: String, val name: String)
/** Interactive plane: base XY/XZ/YZ/FACE, separation along its normal (m), tilt (°) and in-plane shift (m). */
data class CadPlaneSession(val base: String, val planeId: String?, val offset: Double, val tilt: List<Double>,
    val shift: List<Double>, val positiveLabel: String, val negativeLabel: String)
/** [derived]: framed by a face, sketch or top-face support, so its axes are local, not world. */
data class CadPlane(val id: String, val name: String, val translation: List<Double>, val rotation: List<Double>,
    val base: String = "XY", val derived: Boolean = false)
data class CadSurfaceItem(val id: String, val kind: String, val objectName: String, val featureId: String?, val planar: Boolean)
data class CadMeasurement(val label: String, val value: Double, val unit: String)
data class CadSurface(val mode: String = "PROFILE", val selection: List<CadSurfaceItem> = emptyList(),
    val measurements: List<CadMeasurement> = emptyList(), val canSketch: Boolean = false)
data class CadHistoryNode(val id: String, val kind: String, val name: String, val bodyId: String, val sketchId: String?)
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
    val canClose: Boolean = false,
    val operation: String = "",
    val depth: Double = 0.02,
    val positiveDirection: String = "",
    val negativeDirection: String = "",
    val extent: String = "ONE",
    val width: Double = 0.0,
    val segments: Int = 1,
    val overlay: List<CadOverlay> = emptyList(),
    val error: String? = null,
    val selection: List<CadSelection> = emptyList(),
    val step: Double = .001,
    val increment: Boolean = true,
    val transparent: Boolean = false,
    /** Plane being placed interactively (`session.operation == "PLANE"`). */
    val plane: CadPlaneSession? = null,
    val construction: Boolean = false, val showScene: Boolean = false,
    val bodies: List<CadBody> = emptyList(), val activeBodyId: String? = null,
    val planes: List<CadPlane> = emptyList(),
    val dimensionOptions: Map<String, CadDimensionOption> = emptyMap(),
    val surface: CadSurface = CadSurface(), val history: List<CadHistoryNode> = emptyList(),
    val rollbackId: String? = null,
) {
    val activeSketch get() = sketches.firstOrNull { it.id == activeSketchId }
    val selectedConstraint get() = activeSketch?.constraints?.firstOrNull { selectionKind == "CONSTRAINT" && it.id == selectionId }
    val selectedEntity get() = activeSketch?.entities?.firstOrNull { selectionKind == "ENTITY" && it.id == selectionId }
    val selectedFeature get() = features.firstOrNull { (selectionKind == "FEATURE" && it.id == selectionId) || (selectionKind == "SURFACE" && it.id == surface.selection.lastOrNull()?.featureId) }
    /** Resolve the source document sketch, including profiles made from several entities. */
    val selectedSketch get() = sketches.firstOrNull { sketch ->
        when (selectionKind) {
            "SKETCH" -> sketch.id == selectionId
            "PROFILE" -> sketch.profiles.any { it.id == selectionId }
            "ENTITY" -> sketch.entities.any { it.id == selectionId }
            "FEATURE" -> sketch.id == selectedFeature?.sketchId
            else -> false
        }
    }
    val selectionSketch get() = activeSketch ?: selectedSketch ?: sketches.singleOrNull {
        (activeBodyId == null || it.bodyId == activeBodyId) && it.profiles.isNotEmpty()
    }
}
