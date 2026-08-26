package com.blendertablet.remote.network

import java.io.EOFException
import java.io.IOException
import java.nio.ByteBuffer
import java.nio.ByteOrder
import okio.BufferedSource

internal data class H264Packet(val sequence: Long, val captureTimeUs: Long, val width: Int, val height: Int, val config: Boolean, val keyframe: Boolean, val payload: ByteArray)

internal object H264Framing {
    const val NAME = "btr-h264-v1"
    private const val HEADER_SIZE = 32
    private const val MAX_PAYLOAD = 16 * 1024 * 1024

    fun read(source: BufferedSource): H264Packet? {
        if (source.exhausted()) return null
        val bytes = try { source.readByteArray(HEADER_SIZE.toLong()) } catch (_: EOFException) { return null }
        if (bytes.size != HEADER_SIZE) throw EOFException("Cabecera H.264 truncada")
        val header = ByteBuffer.wrap(bytes).order(ByteOrder.BIG_ENDIAN)
        if (header.int != 0x42545248) throw IOException("Magic BTRH inválido")
        if (header.get().toInt() and 0xff != 1) throw IOException("Versión H.264 no soportada")
        val flags = header.get().toInt() and 0xff
        val headerLength = header.short.toInt() and 0xffff
        if (headerLength < HEADER_SIZE) throw IOException("header_len inválido")
        val seq = header.int.toLong() and 0xffffffffL
        val captureUs = header.long
        val payloadLength = header.int
        val width = header.int
        val height = header.int
        if (payloadLength !in 1..MAX_PAYLOAD || width <= 0 || height <= 0) throw IOException("Cabecera H.264 inválida")
        if (headerLength > HEADER_SIZE) source.skip((headerLength - HEADER_SIZE).toLong())
        return H264Packet(seq, captureUs, width, height, flags and 1 != 0, flags and 2 != 0, source.readByteArray(payloadLength.toLong()))
    }
}
