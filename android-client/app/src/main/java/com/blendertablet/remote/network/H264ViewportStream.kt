package com.blendertablet.remote.network

import android.view.Surface
import java.io.IOException
import java.net.Proxy
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request

internal class H264ViewportStream(private val scope: CoroutineScope, private val onFailure: (String) -> Unit) {
    private val http = OkHttpClient.Builder().proxy(Proxy.NO_PROXY).readTimeout(0, TimeUnit.MILLISECONDS).build()
    private val decoder = H264SurfaceDecoder(onFailure)
    private var job: Job? = null
    private var surface: Surface? = null
    private var desiredEndpoint: StreamEndpoint? = null
    private var dimensions: Pair<Int, Int>? = null
    private val _size = MutableStateFlow<Pair<Int, Int>?>(null)
    val size = _size.asStateFlow()

    fun attachSurface(value: Surface) { surface = value; dimensions = null; desiredEndpoint?.let(::open) }
    fun detachSurface() { surface = null; dimensions = null; job?.cancel(); job = null; decoder.stop() }

    fun start(endpoint: StreamEndpoint) {
        stopTransport()
        desiredEndpoint = endpoint
        if (surface != null) open(endpoint)
    }

    private fun open(endpoint: StreamEndpoint) {
        job?.cancel()
        val url = buildString {
            append("http://").append(endpoint.host).append(':').append(endpoint.port).append(endpoint.path)
            if (endpoint.token.isNotBlank()) append("?token=").append(endpoint.token)
        }
        job = scope.launch(Dispatchers.IO) {
            try {
                http.newCall(Request.Builder().url(url).build()).execute().use { response ->
                    if (!response.isSuccessful) throw IOException("HTTP ${response.code}")
                    val source = response.body?.source() ?: throw IOException("Respuesta H.264 vacía")
                    while (true) {
                        val packet = H264Framing.read(source) ?: break
                        val target = surface ?: continue
                        val newDimensions = packet.width to packet.height
                        if (dimensions != newDimensions) {
                            dimensions = newDimensions
                            _size.value = newDimensions
                            decoder.start(target, H264DecoderConfig(packet.width, packet.height))
                        }
                        decoder.queue(H264AccessUnit(packet.payload, packet.captureTimeUs, packet.keyframe, packet.config))
                    }
                }
                throw IOException("Stream H.264 finalizado")
            } catch (t: Throwable) {
                if (job?.isActive == true) onFailure(t.message ?: "Fallo H.264")
            }
        }
    }

    fun stopTransport() { desiredEndpoint = null; job?.cancel(); job = null; decoder.stop(); dimensions = null; _size.value = null }
    fun close() { stopTransport(); decoder.close() }
}
