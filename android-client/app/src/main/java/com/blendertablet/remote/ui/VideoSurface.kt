package com.blendertablet.remote.ui

import android.view.Surface
import android.view.SurfaceHolder
import android.view.SurfaceView
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView

/**
 * Plano de vídeo para MediaCodec. No recibe entrada: [InputSurface] continúa siendo
 * la única autoridad táctil y debe componerse después, ocupando el mismo rectángulo.
 */
@Composable
internal fun VideoSurface(
    modifier: Modifier = Modifier,
    onSurfaceAvailable: (Surface) -> Unit,
    onSurfaceChanged: (Surface, Int, Int) -> Unit,
    onSurfaceDestroyed: (Surface) -> Unit,
) {
    AndroidView(
        modifier = modifier,
        factory = { context ->
            SurfaceView(context).apply {
                isClickable = false
                isFocusable = false
                holder.addCallback(object : SurfaceHolder.Callback {
                    override fun surfaceCreated(holder: SurfaceHolder) = onSurfaceAvailable(holder.surface)
                    override fun surfaceChanged(holder: SurfaceHolder, format: Int, width: Int, height: Int) =
                        onSurfaceChanged(holder.surface, width, height)
                    override fun surfaceDestroyed(holder: SurfaceHolder) = onSurfaceDestroyed(holder.surface)
                })
            }
        },
    )
}
