package com.blendertablet.remote.model

import org.junit.Assert.*
import org.junit.Test

class SculptSamplesTest {
    @Test fun pressureAndCurvedHistorySurviveBatching() {
        val samples = SculptSamples(3)
        samples.add(.1f, .1f, .1f, 0.0)
        samples.add(.2f, .3f, .4f, .008)
        samples.add(.4f, .2f, .9f, .016)
        assertTrue(samples.full)
        val batch = samples.drain()
        assertEquals(listOf(.1f, .4f, .9f), batch.map { it.pressure })
        assertEquals(listOf(.1f, .3f, .2f), batch.map { it.v })
        assertFalse(samples.full)
        assertTrue(samples.add(.5f, .4f, 0f, .024))
        assertEquals(0f, samples.drain().single().pressure)
    }
    @Test fun repeatedHistoricalSamplesAreNotAppliedTwiceAcrossBatches() {
        val samples = SculptSamples()
        samples.add(.2f, .2f, .2f, .04)
        samples.drain()
        assertFalse(samples.add(.3f, .3f, .3f, .04))
        assertFalse(samples.add(.1f, .1f, .1f, .03))
        assertTrue(samples.add(.5f, .4f, .8f, .05))
        assertEquals(1, samples.drain().size)
    }
    @Test fun cancelDiscardsQueuedGeometryAndAllowsNewTimeOrigin() {
        val samples = SculptSamples()
        samples.add(.9f, .9f, 1f, 40.0)
        samples.clear()
        assertTrue(samples.drain().isEmpty())
        assertTrue(samples.add(.1f, .1f, .3f, 0.0))
        assertEquals(.1f, samples.drain().single().u)
    }
    @Test fun pressureNeverInventsForceForInvalidOrZeroSamples() {
        val samples = SculptSamples()
        samples.add(-1f, 2f, Float.NaN, 0.0)
        samples.add(.2f, .2f, 2f, .01)
        val batch = samples.drain()
        assertEquals(SculptPoint(0f, 1f, 0f, 0.0), batch[0])
        assertEquals(1f, batch[1].pressure)
        assertFalse(samples.add(Float.NaN, .4f, .5f, .02))
    }
}
