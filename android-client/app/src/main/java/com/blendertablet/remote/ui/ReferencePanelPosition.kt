package com.blendertablet.remote.ui

/** Coordenadas absolutas del área útil: ningún rail recorta el recorrido del tablero. */
internal fun referencePanelPosition(x: Float, y: Float, width: Float, height: Float,
                                    panelWidth: Float, panelHeight: Float): Pair<Float, Float> =
    x.coerceIn(0f, (width - panelWidth).coerceAtLeast(0f)) to
        y.coerceIn(0f, (height - panelHeight).coerceAtLeast(0f))
