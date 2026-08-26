package com.blendertablet.remote.network

import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaFormat
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.util.Log
import android.view.Surface
import java.nio.ByteBuffer
import java.util.ArrayDeque

/** Configuración local del codec; no representa ningún campo del protocolo. */
internal data class H264DecoderConfig(
    val width: Int,
    val height: Int,
    val csd0: ByteArray? = null,
    val csd1: ByteArray? = null,
)

/** Unidad ya delimitada por el futuro parser del transporte. */
internal data class H264AccessUnit(
    val bytes: ByteArray,
    val presentationTimeUs: Long,
    val keyframe: Boolean,
    val config: Boolean = false,
)

/**
 * Decoder H.264 directo a Surface: no crea Bitmap, StateFlow ni recomposición.
 * Todas las llamadas a MediaCodec quedan confinadas a un HandlerThread.
 */
internal class H264SurfaceDecoder(private val onFailure: (String) -> Unit = {}) {
    private val thread = HandlerThread("btr-h264-decoder").apply { start() }
    private val handler = Handler(thread.looper)
    private val pending = ArrayDeque<H264AccessUnit>()
    private val policy = H264DecoderPolicy()
    private var codec: MediaCodec? = null
    private var generation = 0

    fun start(surface: Surface, config: H264DecoderConfig) {
        val requestedGeneration = ++generation
        handler.post {
            if (requestedGeneration != generation) return@post
            releaseCodec()
            policy.reset()
            pending.clear()
            try {
                val format = MediaFormat.createVideoFormat(MediaFormat.MIMETYPE_VIDEO_AVC, config.width, config.height).apply {
                    config.csd0?.let { setByteBuffer("csd-0", ByteBuffer.wrap(it)) }
                    config.csd1?.let { setByteBuffer("csd-1", ByteBuffer.wrap(it)) }
                    setInteger(MediaFormat.KEY_PRIORITY, 0)
                    if (Build.VERSION.SDK_INT >= 30) setInteger(MediaFormat.KEY_LOW_LATENCY, 1)
                }
                codec = MediaCodec.createDecoderByType(MediaFormat.MIMETYPE_VIDEO_AVC).also {
                    it.configure(format, surface, null, 0)
                    it.start()
                }
                pump()
            } catch (t: Throwable) {
                Log.e(TAG, "No se pudo iniciar AVC", t)
                releaseCodec()
                onFailure(t.message ?: "No se pudo iniciar AVC")
            }
        }
    }

    fun queue(unit: H264AccessUnit) {
        handler.post {
            // CONFIG (SPS/PPS) precede al primer IDR y deben llegar al codec aunque
            // la política todavía esté esperando ese keyframe.
            if (!(unit.config && !unit.keyframe) && !policy.accept(unit.keyframe)) {
                if (policy.needsKeyframe) pending.clear()
                return@post
            }
            pending.addLast(unit)
            pump()
        }
    }

    /** Invalida referencias tras pérdida de transporte; el siguiente AU debe ser IDR. */
    fun awaitKeyframe() = handler.post {
        pending.clear()
        policy.reset()
        codec?.flush()
        codec?.start()
    }

    fun stop() {
        generation++
        handler.post {
            pending.clear()
            policy.reset()
            releaseCodec()
        }
    }

    fun close() {
        stop()
        handler.post { thread.quitSafely() }
    }

    private fun pump() {
        val active = codec ?: return
        try {
            while (pending.isNotEmpty()) {
                val index = active.dequeueInputBuffer(0)
                if (index < 0) break
                val unit = pending.removeFirst()
                val buffer = active.getInputBuffer(index) ?: continue
                buffer.clear()
                if (buffer.remaining() < unit.bytes.size) {
                    policy.consumed()
                    throw IllegalArgumentException("Access unit AVC mayor que el buffer del codec")
                }
                buffer.put(unit.bytes)
                active.queueInputBuffer(
                    index,
                    0,
                    unit.bytes.size,
                    unit.presentationTimeUs,
                    if (unit.keyframe) MediaCodec.BUFFER_FLAG_KEY_FRAME else 0,
                )
                if (!(unit.config && !unit.keyframe)) policy.consumed()
            }
            val info = MediaCodec.BufferInfo()
            while (true) {
                val index = active.dequeueOutputBuffer(info, 0)
                if (index < 0) break
                // true programa el buffer directamente sobre la Surface.
                active.releaseOutputBuffer(index, true)
            }
        } catch (t: Throwable) {
            Log.e(TAG, "Fallo AVC; esperando una nueva inicialización/keyframe", t)
            pending.clear()
            policy.reset()
            releaseCodec()
            onFailure(t.message ?: "Fallo del decoder AVC")
        }
    }

    private fun releaseCodec() {
        codec?.let {
            runCatching { it.stop() }
            runCatching { it.release() }
        }
        codec = null
    }

    private companion object {
        const val TAG = "BTR-H264"
    }
}
