package com.blendertablet.remote.model

/** Un punto señalado pertenece a una escena; los presets se resuelven al comenzar. */
data class TransformCenter(
    val mode: String = "SELECTION",
    val point: List<Double> = emptyList(),
    val sceneId: String = "",
) {
    fun forScene(id: String): TransformCenter =
        if (mode == "PICKED" && (id.isEmpty() || sceneId != id)) TransformCenter() else this

    companion object {
        fun from(session: TransformSession, sceneId: String): TransformCenter? {
            if (!session.active || session.mode == TransformMode.MOVE) return null
            if (session.centerMode == "PICKED") {
                if (!session.centerLocked || session.center.size != 3 || sceneId.isEmpty()) return null
                return TransformCenter("PICKED", session.center.map { it.toDouble() }, sceneId)
            }
            return session.centerMode.takeIf { it in setOf("SELECTION", "CURSOR", "OBJECT_ORIGIN", "INDIVIDUAL") }
                ?.let { TransformCenter(it) }
        }
    }
}
