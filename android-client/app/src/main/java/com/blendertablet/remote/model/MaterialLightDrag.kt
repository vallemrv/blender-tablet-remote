package com.blendertablet.remote.model

/**
 * Absolute displacement keeps the light stable across packet rates and release jitter.
 *
 * Horizontal gira la luz y vertical cambia cuánta hay: Blender no ofrece elevación
 * para el studio light del viewport, así que el eje que sobra hace lo que se busca
 * al intentar subirla —ver mejor el acabado— en vez de no hacer nada.
 */
internal class MaterialLightDrag {
    var onGesture: (GesturePhase, Float, Float) -> Unit = { _, _, _ -> }
    private var start: Offset2? = null
    private var dragging = false
    private var rotation = 0f
    private var energy = 0f
    private var sentRotation = 0f
    private var sentEnergy = 0f

    private data class Offset2(val u: Float, val v: Float)

    fun begin(u: Float, v: Float) {
        cancel()
        start = Offset2(u, v)
        rotation = 0f
        energy = 0f
        sentRotation = 0f
        sentEnergy = 0f
    }

    fun move(u: Float, v: Float, crossedSlop: Boolean, dispatch: Boolean) {
        val origin = start ?: return
        if (!dragging) {
            if (!crossedSlop) return
            dragging = true
            onGesture(GesturePhase.BEGIN, 0f, 0f)
        }
        rotation = (u - origin.u) * 360f
        // v crece hacia abajo en pantalla; subir el dedo tiene que subir la luz.
        energy = origin.v - v
        if (dispatch) flush()
    }

    private fun flush() {
        if (rotation != sentRotation || energy != sentEnergy) {
            onGesture(GesturePhase.UPDATE, rotation, energy)
            sentRotation = rotation
            sentEnergy = energy
        }
    }

    fun end() {
        if (dragging) {
            flush()
            onGesture(GesturePhase.END, 0f, 0f)
        }
        start = null
        dragging = false
    }

    fun cancel() {
        if (dragging) onGesture(GesturePhase.CANCEL, 0f, 0f)
        start = null
        dragging = false
    }
}
