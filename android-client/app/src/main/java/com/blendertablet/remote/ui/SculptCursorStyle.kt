package com.blendertablet.remote.ui

/** The cursor reports the effective brush intent, including temporary pen modifiers. */
data class SculptCursorStyle(
    val smooth: Boolean = false,
    val invert: Boolean = false,
    val mask: Boolean = false,
) {
    fun color(penSmooth: Boolean = false, penInvert: Boolean = false): Int = when {
        smooth || penSmooth -> 0xff66b8ff.toInt()
        invert || penInvert -> 0xffffad55.toInt()
        mask -> 0xffd49bff.toInt()
        else -> 0xffffffff.toInt()
    }
}
