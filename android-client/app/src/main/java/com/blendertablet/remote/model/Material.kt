package com.blendertablet.remote.model

data class MaterialPreset(val id: String, val label: String, val color: String = "#B8B8B8", val category: String = "base")
data class MaterialState(
    val erase: Boolean = false, val finish: String = "natural", val finishes: List<MaterialPreset> = emptyList(),
    val available: Boolean = false, val active: Boolean = false,
    val targets: List<String> = emptyList(), val presets: List<MaterialPreset> = emptyList(),
    val environments: List<MaterialPreset> = emptyList(), val preset: String = "plastic",
    val color: String = "#E85D38", val environment: String = "studio",
    val radius: Float = .06f, val strength: Float = 1f, val paintReady: Boolean = false,
)
