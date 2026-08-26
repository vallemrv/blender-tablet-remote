package com.blendertablet.remote.network

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.Log
import java.io.IOException
import java.net.Proxy
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong
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
    /** Tiempo local de BitmapFactory para el último frame publicado. */
    val decodeMs: Long = 0,
    /** Frames leídos que se omitieron porque ya había llegado uno más nuevo. */
    val staleFrames: Long = 0,
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
    private val latestReadSeq = AtomicLong(0)

    fun start(host: String, port: Int, token: String, path: String = "/stream.mjpg") {
        stop()
        minDelta = Long.MAX_VALUE
        latestReadSeq.set(0)
        staleFrames = 0
        val url = buildString {
            append("http://").append(host).append(':').append(port).append(path)
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
                val pool = BitmapPool()
                val decoder = launch(Dispatchers.Default) {
                    var framesInWindow = 0
                    var windowStart = System.currentTimeMillis()
                    var lastPublishedNs = 0L
                    for (part in newest) {
                        val decodeStarted = System.nanoTime()
                        val bitmap = pool.decode(part.body)
                            ?: continue
                        val decodeMs = (System.nanoTime() - decodeStarted) / 1_000_000
                        // CONFLATED elimina lo que aún estaba esperando, pero no puede
                        // cancelar BitmapFactory. Si durante el decode llegó otro frame,
                        // publicar este produciría un salto visible hacia vídeo antiguo.
                        val nowNs = System.nanoTime()
                        val stale = part.seq < latestReadSeq.get()
                        // Si el decoder nunca alcanza al productor, no debemos
                        // quedarnos sin imagen indefinidamente: se admite como
                        // máximo una publicación obsoleta cada 250 ms.
                        if (stale && nowNs - lastPublishedNs < MAX_UI_SILENCE_NS) {
                            pool.recycle(bitmap)
                            staleFrames++
                            if (Log.isLoggable(TAG, Log.DEBUG)) {
                                Log.d(TAG, "drop stale frame=${part.seq} latest=${latestReadSeq.get()} decode=${decodeMs}ms")
                            }
                            continue
                        }
                        val previous = _frame.value?.bitmap
                        _frame.value = ViewportFrame(bitmap, part.seq)
                        // El bitmap sustituido vuelve al pool con dos frames de
                        // margen: Compose puede seguir dibujándolo un instante, y
                        // reutilizarlo antes produciría un frame rasgado.
                        pool.retire(previous)
                        lastPublishedNs = nowNs
                        if (Log.isLoggable(TAG, Log.VERBOSE)) {
                            Log.v(TAG, "publish frame=${part.seq} decode=${decodeMs}ms readToUi=${(System.nanoTime() - part.receivedAtNs) / 1_000_000}ms")
                        }

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
                                decodeMs = decodeMs,
                                staleFrames = staleFrames,
                            )
                            framesInWindow = 0
                            windowStart = now
                        }
                    }
                    pool.close()
                }
                try {
                    while (currentCoroutineContext().isActive) {
                        val part = readPart(source) ?: break
                        latestReadSeq.set(part.seq)
                        newest.trySend(part)
                    }
                } finally {
                    newest.close()
                    decoder.join()
                }
            }
        }
    }

    internal class Part(
        val body: ByteArray,
        val seq: Long,
        val stampMs: Long,
        val receivedAtNs: Long = System.nanoTime(),
    )

    private var staleFrames = 0L

    /**
     * Reúso de bitmaps del decoder. Sin esto, cada frame reservaba un bitmap nuevo
     * ARGB_8888 (~8 MB a 1080p) y a 30 fps eran ~250 MB/s de asignación nativa que
     * mantenían al GC nativo en marcha permanente: era la causa principal de los
     * frames perdidos del viewport.
     *
     * - RGB_565: el JPEG de viewport no tiene alfa y ya viene suavizado en origen;
     *   a mitad de bytes el banding es imperceptible.
     * - inBitmap con pool: los frames descartados por ser stale vuelven
     *   directamente; los publicados se retiran con dos frames de margen porque
     *   Compose puede seguir dibujándolos un instante. Nunca se hace recycle() de
     *   un bitmap publicado: reutilizarlo solo implica que el decoder escriba en él.
     */
    private class BitmapPool {
        private val free = ArrayDeque<Bitmap>(3)
        private val retired = ArrayDeque<Bitmap>(2)

        fun decode(body: ByteArray): Bitmap? {
            val reuse = free.removeFirstOrNull()
            val options = BitmapFactory.Options().apply {
                inPreferredConfig = Bitmap.Config.RGB_565
                inMutable = true
                if (reuse != null) inBitmap = reuse
            }
            val bitmap = try {
                BitmapFactory.decodeByteArray(body, 0, body.size, options)
            } catch (_: IllegalArgumentException) {
                // El tamaño del stream cambió (stream.configure): el pool entero
                // queda desfasado; se suelta y se reserva uno nuevo.
                free.clear()
                retired.clear()
                BitmapFactory.decodeByteArray(body, 0, body.size, options.also { it.inBitmap = null })
            }
            if (bitmap == null && reuse != null && !reuse.isRecycled) free.addLast(reuse)
            return if (bitmap != null && !bitmap.isRecycled) bitmap else null
        }

        /** Un frame decodificado que no se va a publicar: reutilizable ya mismo. */
        fun recycle(bitmap: Bitmap) {
            if (free.size < 3 && !bitmap.isRecycled) free.addLast(bitmap)
        }

        /** El bitmap que deja de estar en pantalla: se reutiliza con margen de seguridad. */
        fun retire(bitmap: Bitmap?) {
            if (bitmap == null || bitmap.isRecycled) return
            retired.addLast(bitmap)
            if (retired.size > 2) {
                val oldest = retired.removeFirst()
                if (free.size < 3) free.addLast(oldest)
            }
        }

        fun close() {
            free.clear()
            retired.clear()
        }
    }

    private companion object {
        const val TAG = "BTR-Viewport"
        const val MAX_UI_SILENCE_NS = 250_000_000L
    }

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
