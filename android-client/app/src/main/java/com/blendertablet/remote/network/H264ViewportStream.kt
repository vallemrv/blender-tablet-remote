package com.blendertablet.remote.network

import android.view.Surface
import java.io.IOException
import java.net.Proxy
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import okhttp3.Call
import okhttp3.OkHttpClient
import okhttp3.Request

internal class H264ViewportStream(private val scope: CoroutineScope, private val onFailure: (String) -> Unit) {
    private val http = OkHttpClient.Builder().proxy(Proxy.NO_PROXY)
        .connectTimeout(5, TimeUnit.SECONDS).readTimeout(5, TimeUnit.SECONDS).build()
    private val decoder = H264SurfaceDecoder()
    private var job: Job? = null
    private var retryJob: Job? = null
    private var call: Call? = null
    private var surface: Surface? = null
    private var desiredEndpoint: StreamEndpoint? = null
    private var dimensions: Pair<Int, Int>? = null
    private var surfaceSize: Pair<Int, Int>? = null
    private var foreground = true
    private var transportGeneration = 0L
    private var decoderGeneration = -1L
    private var retryAttempts = 0
    private val _size = MutableStateFlow<Pair<Int, Int>?>(null)
    val size = _size.asStateFlow()

    @Synchronized fun attachSurface(value: Surface) {
        surface = value
        surfaceSize = null
        retryAttempts = 0
        if (foreground) desiredEndpoint?.let(::open)
    }

    @Synchronized fun surfaceChanged(value: Surface, width: Int, height: Int) {
        if (surface !== value || width <= 0 || height <= 0 || surfaceSize == width to height) return
        surfaceSize = width to height
        retryAttempts = 0
        if (foreground) desiredEndpoint?.let(::open)
    }

    @Synchronized fun detachSurface(value: Surface) {
        if (surface !== value) return
        surface = null
        surfaceSize = null
        cancelTransport()
    }

    @Synchronized fun pause() {
        foreground = false
        cancelTransport()
    }

    @Synchronized fun resume() {
        if (foreground) return
        foreground = true
        retryAttempts = 0
        if (surface?.isValid == true) desiredEndpoint?.let(::open)
    }

    @Synchronized fun start(endpoint: StreamEndpoint) {
        stopTransport()
        desiredEndpoint = endpoint
        retryAttempts = 0
        if (foreground && surface?.isValid == true) open(endpoint)
    }

    @Synchronized fun pauseForFallback() {
        cancelTransport()
    }

    private fun open(endpoint: StreamEndpoint) {
        // Every HTTP connection gets a fresh codec, even when its dimensions are unchanged.
        cancelTransport()
        val epoch = transportGeneration
        val url = buildString {
            append("http://").append(endpoint.host).append(':').append(endpoint.port).append(endpoint.path)
            if (endpoint.token.isNotBlank()) append("?token=").append(endpoint.token)
        }
        val request = http.newCall(Request.Builder().url(url).build())
        call = request
        job = scope.launch(Dispatchers.IO) {
            try {
                request.execute().use { response ->
                    if (!response.isSuccessful) throw IOException("HTTP ${response.code}")
                    val source = response.body?.source() ?: throw IOException("Respuesta H.264 vacía")
                    while (true) {
                        val packet = H264Framing.read(source) ?: break
                        if (!receive(epoch, packet)) return@launch
                    }
                }
                throw IOException("Stream H.264 finalizado")
            } catch (t: Exception) {
                reportFailure(epoch, t.message ?: "Fallo H.264")
            }
        }
    }

    @Synchronized private fun receive(epoch: Long, packet: H264Packet): Boolean {
        if (epoch != transportGeneration || !foreground) return false
        val target = surface?.takeIf { it.isValid } ?: return false
        val newDimensions = packet.width to packet.height
        if (dimensions != newDimensions) {
            // SPS/PPS travel with each IDR. Never configure from a dependent picture.
            if (!packet.keyframe || !packet.config) return true
            dimensions = newDimensions
            _size.value = newDimensions
            decoderGeneration = decoder.start(target, H264DecoderConfig(packet.width, packet.height),
                onFrame = { scope.launch { frameRendered(epoch) } },
                onFailure = { reportFailure(epoch, it) })
        }
        decoder.queue(decoderGeneration,
            H264AccessUnit(packet.payload, packet.captureTimeUs, packet.keyframe, packet.config, packet.sequence))
        return true
    }

    @Synchronized private fun frameRendered(epoch: Long) {
        if (epoch == transportGeneration) retryAttempts = 0
    }

    private fun reportFailure(epoch: Long, message: String) {
        // Codec callbacks and HTTP errors cannot race the UI lifecycle or recover an old connection.
        scope.launch { handleFailure(epoch, message) }
    }

    @Synchronized private fun handleFailure(epoch: Long, message: String) {
        if (epoch != transportGeneration) return
        val endpoint = desiredEndpoint
        cancelTransport()
        if (endpoint == null || !foreground || surface?.isValid != true) return
        if (retryAttempts >= MAX_RETRIES) {
            onFailure(message)
            return
        }
        retryAttempts++
        val retryEpoch = transportGeneration
        retryJob = scope.launch {
            delay(RETRY_DELAY_MS)
            synchronized(this@H264ViewportStream) {
                if (retryEpoch == transportGeneration && desiredEndpoint == endpoint && foreground && surface?.isValid == true) {
                    retryJob = null
                    open(endpoint)
                }
            }
        }
    }

    private fun cancelTransport() {
        transportGeneration++
        retryJob?.cancel()
        retryJob = null
        job?.cancel()
        job = null
        call?.cancel()
        call = null
        decoder.stop()
        decoderGeneration = -1
        dimensions = null
    }

    @Synchronized fun stopTransport() {
        desiredEndpoint = null
        cancelTransport()
        _size.value = null
    }

    @Synchronized fun close() { stopTransport(); decoder.close() }

    private companion object {
        const val MAX_RETRIES = 3
        const val RETRY_DELAY_MS = 400L
    }
}
