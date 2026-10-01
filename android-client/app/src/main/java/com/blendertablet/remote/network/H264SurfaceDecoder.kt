package com.blendertablet.remote.network

import android.media.MediaCodec
import android.media.MediaFormat
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.util.Log
import android.view.Surface
import java.util.concurrent.atomic.AtomicBoolean

internal data class H264DecoderConfig(val width: Int, val height: Int)

/** Codec calls stay on one thread; incoming frames occupy a bounded queue, not Handler messages. */
internal class H264SurfaceDecoder {
    private val thread = HandlerThread("btr-h264-decoder").apply { start() }
    private val handler = Handler(thread.looper)
    private val policy = H264DecoderPolicy()
    private val scheduled = AtomicBoolean(false)
    private var codec: MediaCodec? = null
    private var codecGeneration = -1L
    private var inFlight = 0
    private var lastProgressNs = 0L
    private var failure: (String) -> Unit = {}
    private val pumpTask = Runnable {
        scheduled.set(false)
        pump()
    }

    fun start(surface: Surface, config: H264DecoderConfig, onFrame: () -> Unit, onFailure: (String) -> Unit): Long {
        val epoch = policy.restart()
        handler.post {
            if (!policy.isCurrent(epoch)) return@post
            releaseCodec()
            codecGeneration = epoch
            failure = onFailure
            try {
                val format = MediaFormat.createVideoFormat(MediaFormat.MIMETYPE_VIDEO_AVC, config.width, config.height).apply {
                    setInteger(MediaFormat.KEY_PRIORITY, 0)
                    if (Build.VERSION.SDK_INT >= 30) setInteger(MediaFormat.KEY_LOW_LATENCY, 1)
                }
                val active = MediaCodec.createDecoderByType(MediaFormat.MIMETYPE_VIDEO_AVC)
                codec = active
                active.configure(format, surface, null, 0)
                active.setOnFrameRenderedListener({ _, _, _ ->
                    if (policy.isCurrent(epoch)) onFrame()
                }, handler)
                active.start()
                schedule()
            } catch (t: Throwable) { fail(t) }
        }
        return epoch
    }

    fun queue(epoch: Long, unit: H264AccessUnit) {
        synchronized(policy) {
            if (!policy.isCurrent(epoch)) return
            policy.offer(epoch, unit, System.nanoTime())
            schedule()
        }
    }

    fun stop() {
        policy.restart()
        handler.post { releaseCodec() }
    }

    fun close() {
        stop()
        handler.post { thread.quitSafely() }
    }

    private fun schedule(delayMs: Long = 0) {
        if (scheduled.compareAndSet(false, true)) handler.postDelayed(pumpTask, delayMs)
    }

    private fun pump() = synchronized(policy) {
        if (!policy.isCurrent(codecGeneration)) return@synchronized
        val active = codec ?: return@synchronized
        try {
            check(inFlight == 0 || System.nanoTime() - lastProgressNs <= 1_000_000_000L) {
                "El decoder AVC no devuelve fotogramas"
            }
            if (policy.prepare(System.nanoTime())) {
                // Synchronous MediaCodec resumes after flush without another start().
                active.flush()
                inFlight = 0
            }
            drainOutput(active)
            while (policy.peek() != null && inFlight < 6) {
                val index = active.dequeueInputBuffer(0)
                if (index < 0) break
                val unit = policy.remove()
                val buffer = requireNotNull(active.getInputBuffer(index))
                buffer.clear()
                require(buffer.remaining() >= unit.bytes.size) { "Access unit AVC mayor que el buffer del codec" }
                buffer.put(unit.bytes)
                val configOnly = unit.config && !unit.keyframe
                active.queueInputBuffer(index, 0, unit.bytes.size, unit.presentationTimeUs,
                    if (configOnly) MediaCodec.BUFFER_FLAG_CODEC_CONFIG else if (unit.keyframe) MediaCodec.BUFFER_FLAG_KEY_FRAME else 0)
                if (!configOnly) {
                    if (inFlight == 0) lastProgressNs = System.nanoTime()
                    inFlight++
                }
            }
            drainOutput(active)
            // Drain even if no next packet arrives: the last frame must not wait for another capture.
            if (inFlight > 0 || policy.peek() != null) schedule(4)
        } catch (t: Throwable) { fail(t) }
    }

    private fun drainOutput(active: MediaCodec) {
        val info = MediaCodec.BufferInfo()
        var newest = -1
        while (true) {
            val index = active.dequeueOutputBuffer(info, 0)
            if (index == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED || index == MediaCodec.INFO_OUTPUT_BUFFERS_CHANGED) continue
            if (index < 0) break
            inFlight = (inFlight - 1).coerceAtLeast(0)
            lastProgressNs = System.nanoTime()
            if (newest >= 0) active.releaseOutputBuffer(newest, false)
            newest = index
        }
        // Decode every reference, but display only the newest available picture, immediately.
        if (newest >= 0) active.releaseOutputBuffer(newest, System.nanoTime())
    }

    private fun fail(t: Throwable) {
        Log.e("BTR-H264", "Fallo AVC; se requiere una conexión y un decoder nuevos", t)
        releaseCodec()
        if (policy.isCurrent(codecGeneration)) failure(t.message ?: "Fallo del decoder AVC")
    }

    private fun releaseCodec() {
        codec?.let { runCatching { it.stop() }; runCatching { it.release() } }
        codec = null
        inFlight = 0
    }
}
