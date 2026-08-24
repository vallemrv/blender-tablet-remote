package com.blendertablet.remote

import com.blendertablet.remote.network.ViewportStream
import java.io.IOException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import okio.Buffer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * El parser del multipart es la pieza con más riesgo de fallo sutil del stream:
 * un byte de desfase desincroniza todos los fotogramas siguientes.
 */
class ViewportStreamTest {
    private val stream = ViewportStream(CoroutineScope(Job()))

    private fun part(body: ByteArray, seq: Long = 1, stamp: String = "1787416962.539"): Buffer =
        Buffer().apply {
            writeUtf8("--btrframe\r\n")
            writeUtf8("Content-Type: image/jpeg\r\n")
            writeUtf8("Content-Length: ${body.size}\r\n")
            writeUtf8("X-Timestamp: $stamp\r\n")
            writeUtf8("X-Frame: $seq\r\n\r\n")
            write(body)
            writeUtf8("\r\n")
        }

    @Test
    fun `lee un frame con sus metadatos`() {
        val body = ByteArray(64) { it.toByte() }
        val read = stream.readPart(part(body, seq = 42))!!

        assertEquals(64, read.body.size)
        assertEquals(42L, read.seq)
        assertEquals(1787416962539L, read.stampMs)
        assertTrue(body.contentEquals(read.body))
    }

    @Test
    fun `encadena frames sin desincronizarse`() {
        val first = ByteArray(10) { 1 }
        val second = ByteArray(20) { 2 }
        val source = Buffer().apply {
            writeAll(part(first, seq = 1))
            writeAll(part(second, seq = 2))
        }

        val a = stream.readPart(source)!!
        val b = stream.readPart(source)!!

        assertEquals(1L, a.seq)
        assertEquals(10, a.body.size)
        assertEquals(2L, b.seq)
        assertEquals(20, b.body.size)
        assertTrue(second.contentEquals(b.body))
    }

    @Test
    fun `un cuerpo que contiene el separador no corta el frame`() {
        // Justo el caso que rompe a los parsers que buscan el boundary en el cuerpo.
        val body = "xx--btrframe\r\nContent-Length: 3\r\n\r\nyy".toByteArray()
        val read = stream.readPart(part(body))!!

        assertEquals(body.size, read.body.size)
        assertTrue(body.contentEquals(read.body))
    }

    @Test
    fun `fin de stream devuelve null`() {
        assertNull(stream.readPart(Buffer()))
    }

    @Test(expected = IOException::class)
    fun `una parte sin Content-Length es un error`() {
        val source = Buffer().apply {
            writeUtf8("--btrframe\r\nContent-Type: image/jpeg\r\n\r\n")
        }
        stream.readPart(source)
    }
}
