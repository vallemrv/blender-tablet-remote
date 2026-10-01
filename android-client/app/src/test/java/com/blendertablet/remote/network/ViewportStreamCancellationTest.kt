package com.blendertablet.remote.network

import java.net.InetAddress
import java.net.ServerSocket
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import org.junit.Assert.*
import org.junit.Test

class ViewportStreamCancellationTest {
    @Test fun repeatedBackgroundStopsCloseTheActualBlockedHttpConnections() {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        val stream = ViewportStream(scope)
        try {
            repeat(3) {
                ServerSocket(0, 1, InetAddress.getByName("127.0.0.1")).use { server ->
                    val ready = CountDownLatch(1)
                    val disconnected = CountDownLatch(1)
                    val reader = thread(isDaemon = true) {
                        server.accept().use { socket ->
                            socket.soTimeout = 3000
                            val input = socket.getInputStream().bufferedReader()
                            while (input.readLine()?.isNotEmpty() == true) { }
                            socket.getOutputStream().write("HTTP/1.1 200 OK\r\nContent-Type: multipart/x-mixed-replace; boundary=btrframe\r\nConnection: close\r\n\r\n".toByteArray())
                            socket.getOutputStream().flush()
                            ready.countDown()
                            if (input.read() == -1) disconnected.countDown()
                        }
                    }
                    stream.start("127.0.0.1", server.localPort, "")
                    assertTrue(ready.await(3, TimeUnit.SECONDS))
                    stream.stop()
                    assertTrue("stop must cancel the socket blocked waiting for video", disconnected.await(2, TimeUnit.SECONDS))
                    reader.join(1000)
                    assertNull(stream.frame.value)
                    assertFalse(stream.stats.value.connected)
                    assertNull(stream.stats.value.error)
                }
            }
        } finally { stream.stop(); scope.cancel() }
    }
}
