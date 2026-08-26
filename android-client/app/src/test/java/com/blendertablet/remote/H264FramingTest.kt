package com.blendertablet.remote

import com.blendertablet.remote.network.H264Framing
import java.nio.ByteBuffer
import java.nio.ByteOrder
import okio.Buffer
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class H264FramingTest {
    @Test fun `parsea cabecera big endian congelada`() {
        val payload = byteArrayOf(0, 0, 0, 1, 0x65, 7)
        val header = ByteBuffer.allocate(32).order(ByteOrder.BIG_ENDIAN).apply {
            put("BTRH".toByteArray()); put(1); put(3); putShort(32)
            putInt(0xf0000001.toInt()); putLong(1234567); putInt(payload.size); putInt(1280); putInt(720)
        }.array()
        val packet = H264Framing.read(Buffer().write(header).write(payload))!!
        assertEquals(0xf0000001L, packet.sequence)
        assertEquals(1234567, packet.captureTimeUs)
        assertEquals(1280, packet.width)
        assertEquals(720, packet.height)
        assertTrue(packet.config)
        assertTrue(packet.keyframe)
        assertArrayEquals(payload, packet.payload)
    }
}
