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
    private val http = OkHttpClient.Builder().proxy(Proxy.NO_PROXY).readTimeout(0, TimeUnit.MILLISECONDS).build()
    private val decoder = H264SurfaceDecoder { handleFailure(it) }
    private var job: Job? = null
    private var call: Call? = null
    private var surface: Surface? = null
    private var desiredEndpoint: StreamEndpoint? = null
    private var dimensions: Pair<Int, Int>? = null
    // Un resize de ventana o el sistema reclamando el codec de hardware invalidan
    // el decoder/la Surface durante un instante: reintentar aquí evita caer a MJPEG
    // por un tropiezo transitorio. Se resetea con cada frame sano y con cada Surface
    // nueva, así que no protege un fallo real y persistente.
    private var retryAttempts = 0
    private val _size = MutableStateFlow<Pair<Int, Int>?>(null)
    val size = _size.asStateFlow()

    fun attachSurface(value: Surface) {
        surface = value
        dimensions = null
        retryAttempts = 0
        desiredEndpoint?.let(::open)
    }

    fun detachSurface() {
        surface = null
        dimensions = null
        cancelTransport()
        decoder.stop()
    }

    fun start(endpoint: StreamEndpoint) {
        stopTransport()
        desiredEndpoint = endpoint
        retryAttempts = 0
        if (surface != null) open(endpoint)
    }

    /**
     * Deja de decodificar pero conserva `desiredEndpoint`: la siguiente
     * [attachSurface] (el próximo resize, o volver a primer plano) reintenta H.264
     * en vez de quedarse en MJPEG hasta que se reinicie la app.
     */
    fun pauseForFallback() {
        cancelTransport()
        decoder.stop()
        dimensions = null
        retryAttempts = 0
    }

    private fun open(endpoint: StreamEndpoint) {
        cancelTransport()
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
                        val target = surface ?: continue
                        val newDimensions = packet.width to packet.height
                        if (dimensions != newDimensions) {
                            dimensions = newDimensions
                            _size.value = newDimensions
                            decoder.start(target, H264DecoderConfig(packet.width, packet.height))
                        }
                        decoder.queue(H264AccessUnit(packet.payload, packet.captureTimeUs, packet.keyframe, packet.config))
                        retryAttempts = 0
                    }
                }
                throw IOException("Stream H.264 finalizado")
            } catch (t: Throwable) {
                if (job?.isActive == true) handleFailure(t.message ?: "Fallo H.264")
            }
        }
    }

    private fun handleFailure(message: String) {
        val endpoint = desiredEndpoint
        if (endpoint != null && surface != null && retryAttempts < MAX_RETRIES) {
            retryAttempts++
            cancelTransport()
            scope.launch {
                delay(RETRY_DELAY_MS)
                if (desiredEndpoint == endpoint && surface != null) open(endpoint)
            }
            return
        }
        onFailure(message)
    }

    /** Cancela de verdad la conexión en vuelo: un `Job.cancel()` no interrumpe un `execute()` bloqueado. */
    private fun cancelTransport() {
        job?.cancel()
        job = null
        call?.cancel()
        call = null
    }

    fun stopTransport() {
        desiredEndpoint = null
        cancelTransport()
        decoder.stop()
        dimensions = null
        _size.value = null
    }

    fun close() { stopTransport(); decoder.close() }

    private companion object {
        const val MAX_RETRIES = 3
        const val RETRY_DELAY_MS = 400L
    }
}
