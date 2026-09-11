package com.blendertablet.remote.model

data class MaterialPreset(val id: String, val label: String, val color: String = "#B8B8B8", val category: String = "base",
    val hint: String = "")

/** Un parámetro de superficie con sus dos extremos dichos en castellano llano. */
data class SurfaceControl(val id: String, val label: String, val low: String, val high: String,
    val min: Float = 0f, val max: Float = 1f)

data class MaterialState(
    val objects: List<MaterialPreset> = emptyList(), val interaction: String = "PAINT", val isolate: Boolean = false,
    val scope: String = "ALL", val regions: List<MaterialPreset> = emptyList(),
    val brush: String = "ROUND", val brushes: List<MaterialPreset> = emptyList(),
    val paintBlocked: Boolean = false, val paintLimit: Int = 20000,
    val erase: Boolean = false, val finish: String = "natural", val finishes: List<MaterialPreset> = emptyList(),
    val available: Boolean = false, val active: Boolean = false,
    val targets: List<String> = emptyList(), val presets: List<MaterialPreset> = emptyList(),
    val environments: List<MaterialPreset> = emptyList(), val preset: String = "plastic",
    val color: String = "#E85D38", val environment: String = "studio",
    val radius: Float = .06f, val strength: Float = 1f, val paintReady: Boolean = false,
    /** Sin tinte el material se ve con su propio color; el tinte es una decisión explícita. */
    val tinted: Boolean = false,
    /** Hay ajustes sueltos encima del acabado: ningún acabado describe ya la superficie. */
    val custom: Boolean = false,
    val surface: Map<String, Float> = emptyMap(), val surfaceControls: List<SurfaceControl> = emptyList(),
    val grain: String = "none", val grains: List<MaterialPreset> = emptyList(),
    val grainScale: Float = 20f, val grainAmount: Float = .5f, val grainRelief: Float = .35f,
)
