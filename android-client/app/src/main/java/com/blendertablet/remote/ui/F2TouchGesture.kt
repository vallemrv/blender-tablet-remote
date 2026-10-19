package com.blendertablet.remote.ui

import com.blendertablet.remote.model.GesturePhase

/** Release commits the last dispatched sample; navigation/palm cancellation never commits. */
internal class F2TouchGesture(var dispatch: (GesturePhase, Float, Float) -> Unit = { _,_,_ -> }) {
    var active = false
        private set
    private var u = 0f
    private var v = 0f
    fun begin(x: Float, y: Float) { cancel(); active=true; u=x; v=y; dispatch(GesturePhase.BEGIN,u,v) }
    fun move(x: Float, y: Float) { if (active) { u=x; v=y; dispatch(GesturePhase.UPDATE,u,v) } }
    fun end() { if (active) { active=false; dispatch(GesturePhase.END,u,v) } }
    fun cancel() { if (active) { active=false; dispatch(GesturePhase.CANCEL,u,v) } }
}
