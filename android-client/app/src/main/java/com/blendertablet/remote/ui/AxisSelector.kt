package com.blendertablet.remote.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.blendertablet.remote.model.Axis
import com.blendertablet.remote.model.Constraint

internal val AxisColors = mapOf(Axis.X to Ink.AxisX, Axis.Y to Ink.AxisY, Axis.Z to Ink.AxisZ)

/**
 * El único control de ejes de la app (norma de controles): Mover, Rotar, Escalar,
 * Extruir, esquemas y CAD.
 *
 * `[Libre] [X | valor] [Y | valor] [Z | valor] [Plano]`
 *
 * - La pestaña de color de cada celda restringe a ese eje; tocarla otra vez vuelve a
 *   Libre (sin Libre, [allowFree] falso, un eje siempre queda elegido).
 * - [value] dibuja el número del eje dentro de su celda: eje y valor no se repiten en
 *   dos filas de letras.
 * - [planes] muestra el interruptor «Plano»: con él activo, tocar un eje lo excluye
 *   (se mueve en el plano de los otros dos) y su celda se ve tachada.
 * - Sin pulsación larga: todo se hace con toques visibles.
 */
@Composable
fun AxisSelector(
    selected: Constraint,
    onSelect: (Constraint) -> Unit,
    modifier: Modifier = Modifier,
    axes: List<Axis> = Axis.entries,
    allowFree: Boolean = true,
    planes: Boolean = false,
    enabled: Boolean = true,
    value: (@Composable (Axis) -> Unit)? = null,
    trailing: (@Composable () -> Unit)? = null,
) {
    // El modo Plano se deduce de la restricción vigente; el interruptor solo cambia el
    // significado del siguiente toque mientras no hay ninguna restricción.
    var planeArmed by remember { mutableStateOf(false) }
    val planeMode = planes && (selected.axes.size == 2 || (selected == Constraint.FREE && planeArmed))
    Row(modifier, horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
        if (allowFree) {
            val free = selected == Constraint.FREE
            HoverHelp("Libre", "Sin restricción: sigue al dedo.", enabled = enabled) {
                Box(Modifier.height(Metrics.Touch).clip(RoundedCornerShape(10.dp))
                    .background(if (free) Ink.Accent.copy(alpha = .22f) else Color.Transparent)
                    .then(if (enabled) Modifier.clickableNoRipple { onSelect(Constraint.FREE) } else Modifier)
                    .padding(horizontal = 10.dp), contentAlignment = Alignment.Center) {
                    Text("Libre", color = if (!enabled) Ink.Faint else if (free) Ink.Accent else Ink.Muted,
                        fontSize = 13.sp, fontWeight = if (free) FontWeight.SemiBold else FontWeight.Normal)
                }
            }
        }
        axes.forEach { axis ->
            val color = AxisColors.getValue(axis)
            val excluded = planeMode && selected.axes.size == 2 && axis !in selected.axes
            val active = axis in selected.axes && !excluded
            val dimmed = selected != Constraint.FREE && !active
            val shape = RoundedCornerShape(10.dp)
            Row(
                Modifier.height(Metrics.Touch).clip(shape)
                    .background(if (active) color.copy(alpha = .22f) else Ink.Elevated.copy(alpha = .5f))
                    .then(if (active) Modifier.border(1.dp, color.copy(alpha = .7f), shape) else Modifier)
                    .alpha(if (dimmed) .55f else 1f),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                val help = if (planeMode) "Toca para mover en el plano de los otros dos ejes (excluye ${axis.name})."
                    else "Toca para restringir a ${axis.name}; otra vez vuelve a Libre."
                HoverHelp("Eje ${axis.name}", help, enabled = enabled) {
                    Box(Modifier.width(36.dp).height(Metrics.Touch)
                        .then(if (enabled) Modifier.clickableNoRipple {
                            onSelect(axisSelectorTap(selected, axis, planeMode, allowFree))
                        } else Modifier)
                        .drawWithContent {
                            drawContent()
                            if (excluded) drawLine(color, Offset(6.dp.toPx(), size.height - 12.dp.toPx()),
                                Offset(size.width - 6.dp.toPx(), 12.dp.toPx()), strokeWidth = 2.dp.toPx())
                        },
                        contentAlignment = Alignment.Center) {
                        Text(axis.name, color = if (enabled) color else Ink.Faint, fontSize = 16.sp,
                            fontWeight = if (active) FontWeight.Bold else FontWeight.SemiBold)
                    }
                }
                value?.invoke(axis)
            }
        }
        if (planes) {
            val on = planeMode
            IconAction(AppIcons.AxisPlane, if (on) "Plano: activado" else "Plano: desactivado",
                selected = on, enabled = enabled) {
                if (selected == Constraint.FREE) planeArmed = !planeArmed
                else onSelect(axisSelectorTogglePlane(selected)).also { planeArmed = false }
            }
        }
        trailing?.invoke()
    }
}

/** Qué restricción deja tocar la pestaña de un eje. */
internal fun axisSelectorTap(current: Constraint, axis: Axis, planeMode: Boolean, allowFree: Boolean = true): Constraint {
    val target = if (planeMode) Constraint.ofAxes(Axis.entries.toSet() - axis) else Constraint.ofAxes(setOf(axis))
    return if (current == target) (if (allowFree) Constraint.FREE else current) else target
}

/** El interruptor Plano conserva el eje elegido y cambia su sentido: solo ese eje ↔ plano sin él. */
internal fun axisSelectorTogglePlane(current: Constraint): Constraint = when (current.axes.size) {
    1 -> Constraint.ofAxes(Axis.entries.toSet() - current.axes)
    2 -> Constraint.ofAxes(Axis.entries.toSet() - current.axes)
    else -> current
}

internal fun constraintLabel(value: Constraint) = when (value) {
    Constraint.FREE -> "Libre"
    Constraint.X, Constraint.Y, Constraint.Z -> "Solo eje ${value.name}"
    else -> "Plano ${value.name}"
}
