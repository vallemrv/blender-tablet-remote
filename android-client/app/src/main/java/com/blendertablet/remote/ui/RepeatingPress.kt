package com.blendertablet.remote.ui

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/** A short click is exact; a held press repeats without adding a release click. */
internal class RepeatingPress(private val onStep: () -> Unit) {
    private var job: Job? = null
    private var repeated = false

    fun press(scope: CoroutineScope) {
        release()
        repeated = false
        job = scope.launch {
            delay(400)
            var count = 0
            while (isActive) {
                repeated = true
                onStep()
                // Accelerate the cadence, keeping the user's numerical step exact.
                delay((180L - count++ * 12L).coerceAtLeast(80L))
            }
        }
    }

    fun release() {
        job?.cancel()
        job = null
    }

    fun click() {
        release()
        val singleStep = !repeated
        repeated = false
        if (singleStep) onStep()
    }

    fun cancel() {
        release()
        repeated = false
    }
}
