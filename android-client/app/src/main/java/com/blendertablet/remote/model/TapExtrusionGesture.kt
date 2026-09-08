package com.blendertablet.remote.model

/** Un tramo por contacto; soltar confirma la última posición DOWN/MOVE. */
class TapExtrusionGesture {
    private var point: Pair<Float, Float>? = null
    val active: Boolean get() = point != null
    fun begin(u: Float, v: Float) { point = u to v }
    fun move(u: Float, v: Float) { if (active) point = u to v }
    fun end(): Pair<Float, Float>? = point.also { point = null }
    fun cancel() { point = null }
}
