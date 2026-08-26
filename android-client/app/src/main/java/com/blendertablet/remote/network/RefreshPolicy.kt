package com.blendertablet.remote.network

/** Decide si un evento sin snapshot necesita consultar toda la escena. */
internal fun shouldRequestSceneSnapshot(
    transformActive: Boolean,
    toolActive: Boolean,
    selectionPending: Boolean,
): Boolean = !transformActive && !toolActive && !selectionPending
