package com.blendertablet.remote.network

/**
 * Estado puro que protege al decoder frente a vídeo atrasado.
 *
 * Un H.264 inter-frame no permite descartar P-frames arbitrariamente como MJPEG.
 * Cuando la cola se satura o el codec falla, se abandona el GOP completo y no se
 * vuelve a aceptar vídeo hasta el siguiente IDR anunciado por el parser.
 */
internal class H264DecoderPolicy(private val capacity: Int = 6) {
    init { require(capacity > 0) }

    private var waitingForKeyframe = true
    private var queued = 0

    fun accept(keyframe: Boolean): Boolean {
        if (waitingForKeyframe && !keyframe) return false
        if (keyframe) waitingForKeyframe = false
        if (queued >= capacity) {
            reset()
            return false
        }
        queued++
        return true
    }

    fun consumed() {
        if (queued > 0) queued--
    }

    fun reset() {
        queued = 0
        waitingForKeyframe = true
    }

    val needsKeyframe: Boolean get() = waitingForKeyframe
}
