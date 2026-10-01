package com.blendertablet.remote.network

import org.junit.Assert.*
import org.junit.Test

class H264DecoderPolicyTest {
    private fun unit(seq: Long, key: Boolean = false, config: Boolean = key) =
        H264AccessUnit(byteArrayOf(1), seq * 40_000, key, config, seq)

    @Test fun reconnectRejectsOldWorkEvenAtTheSameResolution() {
        val policy = H264DecoderPolicy()
        val old = policy.restart()
        assertTrue(policy.offer(old, unit(1, true), 0))
        val current = policy.restart()
        assertNull(policy.peek())
        assertFalse(policy.offer(old, unit(2, true), 1))
        assertFalse(policy.offer(current, unit(3), 2))
        assertTrue(policy.offer(current, unit(4, true), 3))
        assertEquals(4L, policy.remove().sequence)
    }

    @Test fun saturatedProducerDropsTheEntireGopBeforeTheHandlerCanAccumulateWork() {
        val policy = H264DecoderPolicy(capacity = 2)
        val epoch = policy.restart()
        assertTrue(policy.offer(epoch, unit(1, true), 0))
        assertTrue(policy.offer(epoch, unit(2), 1))
        assertFalse(policy.offer(epoch, unit(3), 2))
        assertNull(policy.peek())
        assertTrue(policy.prepare(2))
        assertFalse(policy.offer(epoch, unit(4), 3))
        assertTrue(policy.offer(epoch, unit(5, true), 4))
        assertEquals(5L, policy.remove().sequence)
    }

    @Test fun keyframeThatOverflowsTheQueueIsKeptAsTheNewBaseline() {
        val policy = H264DecoderPolicy(capacity = 1)
        val epoch = policy.restart()
        policy.offer(epoch, unit(1, true), 0)
        assertTrue(policy.offer(epoch, unit(2, true), 1))
        assertTrue(policy.prepare(1))
        assertEquals(2L, policy.remove().sequence)
    }

    @Test fun expiredFramesAreNeverPlayedAfterAStall() {
        val policy = H264DecoderPolicy(maxAgeNs = 100)
        val epoch = policy.restart()
        policy.offer(epoch, unit(1, true), 0)
        assertTrue(policy.prepare(101))
        assertNull(policy.peek())
        assertFalse(policy.offer(epoch, unit(2), 102))
        assertTrue(policy.offer(epoch, unit(3, true), 103))
    }

    @Test fun slowConsumerRecoversFromRecentKeyframeWithoutWaitingToFillQueue() {
        val policy = H264DecoderPolicy(maxAgeNs = 100)
        val epoch = policy.restart()
        policy.offer(epoch, unit(1, true), 0)
        assertTrue(policy.offer(epoch, unit(2, true), 101))
        assertTrue(policy.prepare(101))
        assertEquals(2L, policy.remove().sequence)
    }

    @Test fun missingSequenceInvalidatesReferencesAndConfigurationDoesNotReplaceIdr() {
        val policy = H264DecoderPolicy()
        val epoch = policy.restart()
        policy.offer(epoch, unit(1, true), 0)
        policy.remove()
        assertFalse(policy.offer(epoch, unit(3), 1))
        assertTrue(policy.prepare(1))
        assertTrue(policy.offer(epoch, unit(4, config = true), 2))
        policy.remove()
        assertFalse(policy.offer(epoch, unit(5), 3))
        assertTrue(policy.offer(epoch, unit(6, true), 4))
    }

    @Test fun continuousStreamIncludingSequenceWrapPreservesEveryReference() {
        val policy = H264DecoderPolicy()
        val epoch = policy.restart()
        listOf(0xfffffffeL, 0xffffffffL, 0L, 1L).forEachIndexed { i, seq ->
            assertTrue(policy.offer(epoch, unit(seq, i == 0), i.toLong()))
            assertFalse(policy.prepare(i.toLong()))
            assertEquals(seq, policy.remove().sequence)
        }
    }
}
