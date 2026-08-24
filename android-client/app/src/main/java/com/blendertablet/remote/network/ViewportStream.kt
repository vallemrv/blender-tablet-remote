package com.blendertablet.remote.network

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import java.io.IOException
import java.net.Proxy
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.channels.Channel
import okhttp3.OkHttpClient
import okhttp3.Request
import okio.BufferedSource

/** Un fotograma ya decodificado, listo para pintar. */
data class ViewportFrame(val bitmap: Bitmap, val seq: Long)

data class StreamStats(
    val connected: Boolean = false,
    val fps: Float = 0f,
    /**
     * Retraso **por encima del mejor caso observado**, no latencia absoluta: los
     * relojes de la tablet y del PC no están sincronizados, así que el valor
     * absoluto no significaría nada. Restando el mínimo delta visto queda algo
     * honesto y útil: cuánto se está degradando respecto a la mejor condición.
     */
    val lagMs: Long = 0,
    val kbPerFrame: Int = 0,
    val error: String? = null,
)

/**
 * Cliente del vídeo del viewport (MJPEG sobre HTTP).
 *
 * Va por un canal aparte del WebSocket a propósito: un frame perdido no debe
 * retrasar un comando, y un comando no debe esperar a que termine un frame.
 * El plan (§89) contempla sustituir esto por WebRTC sin tocar el resto.
 */
class ViewportStream(
    private val scope: CoroutineScope,
    private val http: OkHttpClient = OkHttpClient.Builder()
        .proxy(Proxy.NO_PROXY)
        .readTimeout(0, TimeUnit.MILLISECONDS) // un stream no "termina": sin timeout de lectura
        .connectTimeout(5, TimeUnit.SECONDS)
        .build(),
) {
    private val _frame = MutableStateFlow<ViewportFrame?>(null)
    private val _stats = MutableStateFlow(StreamStats())
    val frame: StateFlow<ViewportFrame?> = _frame.asStateFlow()
    val stats: StateFlow<StreamStats> = _stats.asStateFlow()

    private var job: Job? = null
    private var minDelta = Long.MAX_VALUE

    fun start(host: String, port: Int, token: String) {
        stop()
        minDelta = Long.MAX_VALUE
        val url = buildString {
            append("http://").append(host).append(':').append(port).append("/stream.mjpg")
            if (token.isNotBlank()) append("?token=").append(token)
        }
        job = scope.launch(Dispatchers.IO) { runWithRetry(url) }
    }

    fun stop() {
        job?.cancel()
        job = null
        _frame.value = null
        _stats.value = StreamStats()
    }

    /** Reconexión automática con espera creciente: nunca hay que reiniciar la app (§41). */
    private suspend fun runWithRetry(url: String) {
        var backoffMs = 500L
        while (currentCoroutineContext().isActive) {
            try {
                consume(url)
                backoffMs = 500L // una desconexión limpia no debe penalizar el siguiente intento
            } catch (e: IOException) {
                _stats.value = _stats.value.copy(connected = false, fps = 0f, error = e.message)
            }
            delay(backoffMs) // cancelable: al llamar a stop() salimos aquí
            backoffMs = (backoffMs * 2).coerceAtMost(5_000L)
        }
    }

    private suspend fun consume(url: String) {
        val response = http.newCall(Request.Builder().url(url).build()).execute()
        response.use {
            if (!it.isSuccessful) throw IOException("HTTP ${it.code}")
            val source = it.body?.source() ?: throw IOException("Respuesta sin cuerpo")
            _stats.value = StreamStats(connected = true)

            coroutineScope {
                // Lectura y decodificación separadas. CONFLATED conserva solo la
                // parte más reciente: si BitmapFactory tarda, no reproducimos luego
                // una película atrasada de todo lo que ocurrió durante el gesto.
                val newest = Channel<Part>(Channel.CONFLATED)
                val decoder = launch(Dispatchers.Default) {
                    var framesInWindow = 0
                    var windowStart = System.currentTimeMillis()
                    for (part in newest) {
                        val bitmap = BitmapFactory.decodeByteArray(part.body, 0, part.body.size)
                            ?: continue
                        _frame.value = ViewportFrame(bitmap, part.seq)

                        framesInWindow++
                        val now = System.currentTimeMillis()
                        val elapsed = now - windowStart
                        if (elapsed >= 1000) {
                            val delta = now - part.stampMs
                            if (delta < minDelta) minDelta = delta
                            _stats.value = StreamStats(
                                connected = true,
                                fps = framesInWindow * 1000f / elapsed,
                                lagMs = (delta - minDelta).coerceAtLeast(0),
                                kbPerFrame = part.body.size / 1024,
                            )
                            framesInWindow = 0
                            windowStart = now
                        }
                    }
                }
                try {
                    while (currentCoroutineContext().isActive) {
                        val part = readPart(source) ?: break
                        newest.trySend(part)
                    }
                } finally {
                    newest.close()
                    decoder.join()
                }
            }
        }
    }

    internal class Part(val body: ByteArray, val seq: Long, val stampMs: Long)

    /**
     * Lee una parte del multipart. Devuelve null al final del stream.
     *
     * Nos fiamos de Content-Length en vez de buscar el separador dentro del cuerpo:
     * un JPEG puede contener la secuencia del boundary por casualidad.
     */
    internal fun readPart(source: BufferedSource): Part? {
        var length = -1
        var seq = 0L
        var stampMs = 0L
        var sawHeaders = false

        while (true) {
            val line = try {
                source.readUtf8LineStrict()
            } catch (e: java.io.EOFException) {
                return null
            }
            if (line.isEmpty()) {
                if (sawHeaders) break else continue // línea en blanco antes del boundary
            }
            sawHeaders = true
            val colon = line.indexOf(':')
            if (colon <= 0) continue // el "--boundary"
            val name = line.substring(0, colon).trim().lowercase()
            val value = line.substring(colon + 1).trim()
            when (name) {
                "content-length" -> length = value.toIntOrNull() ?: -1
                "x-frame" -> seq = value.toLongOrNull() ?: 0L
                // Segundos con decimales -> milisegundos.
                "x-timestamp" -> stampMs = ((value.toDoubleOrNull() ?: 0.0) * 1000).toLong()
            }
        }

        if (length <= 0) throw IOException("Frame sin Content-Length")
        val body = source.readByteArray(length.toLong())
        return Part(body, seq, stampMs)
    }
}
