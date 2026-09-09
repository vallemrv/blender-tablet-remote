package com.blendertablet.remote.ui

import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class RepeatingPressTest {
    @Test fun shortTapMakesExactlyOneStepAndLeavesNoRepeater() = runTest {
        var value = 0
        val press = RepeatingPress { value++ }
        press.press(this)
        advanceTimeBy(100)
        press.release(); press.click()
        advanceTimeBy(2000)
        assertEquals(1, value)
    }

    @Test fun holdAcceleratesAndReleaseDoesNotAddAStep() = runTest {
        val times = mutableListOf<Long>()
        val press = RepeatingPress { times += testScheduler.currentTime }
        press.press(this)
        advanceTimeBy(399)
        assertTrue(times.isEmpty())
        advanceTimeBy(3601); runCurrent()
        val early = times.count { it in 400..1399 }
        val late = times.count { it in 3000..3999 }
        assertTrue("The held button should accelerate", late > early)
        assertTrue("Repeats must remain bounded", times.zipWithNext().all { (a, b) -> b - a >= 80 })
        val atRelease = times.size
        press.release(); press.click()
        advanceTimeBy(1000)
        assertEquals(atRelease, times.size)
        press.press(this); advanceTimeBy(100); press.release(); press.click()
        assertEquals(atRelease + 1, times.size)
    }

    @Test fun cancellingForScrollOrDisableStopsAndAllowsNextClick() = runTest {
        var value = 0
        val press = RepeatingPress { value++ }
        press.press(this); advanceTimeBy(1500)
        press.cancel()
        val stopped = value
        advanceTimeBy(1000)
        assertEquals(stopped, value)
        // Accessibility can invoke click directly without a pointer press.
        press.click()
        assertEquals(stopped + 1, value)
    }

    @Test fun movingAwayBeforeHoldDoesNotChangeValue() = runTest {
        var value = 0
        val press = RepeatingPress { value++ }
        press.press(this); advanceTimeBy(200); press.cancel()
        advanceTimeBy(2000)
        assertEquals(0, value)
    }
}
