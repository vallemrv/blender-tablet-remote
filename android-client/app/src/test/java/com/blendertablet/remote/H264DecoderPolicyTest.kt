package com.blendertablet.remote

import com.blendertablet.remote.network.H264DecoderPolicy
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class H264DecoderPolicyTest {
    @Test fun `ignora inter frames hasta keyframe`() {
        val policy = H264DecoderPolicy()
        assertFalse(policy.accept(keyframe = false))
        assertTrue(policy.accept(keyframe = true))
        assertTrue(policy.accept(keyframe = false))
    }

    @Test fun `saturacion abandona GOP y exige keyframe`() {
        val policy = H264DecoderPolicy(capacity = 2)
        assertTrue(policy.accept(keyframe = true))
        assertTrue(policy.accept(keyframe = false))
        assertFalse(policy.accept(keyframe = false))
        assertTrue(policy.needsKeyframe)
        assertFalse(policy.accept(keyframe = false))
        assertTrue(policy.accept(keyframe = true))
    }

    @Test fun `consumo libera capacidad`() {
        val policy = H264DecoderPolicy(capacity = 1)
        assertTrue(policy.accept(keyframe = true))
        policy.consumed()
        assertTrue(policy.accept(keyframe = false))
    }

    @Test fun `keyframe que incluye configuracion abre el GOP`() {
        val policy = H264DecoderPolicy()
        assertTrue(policy.accept(keyframe = true))
        policy.consumed()
        assertTrue(policy.accept(keyframe = false))
    }
}
