package com.blendertablet.remote.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.expandVertically
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.blendertablet.remote.model.Transform
import kotlin.math.roundToInt

private val AxisColors = listOf(Color(0xFFE05B62), Color(0xFF8BC34A), Color(0xFF4A90D9))
private val AxisLabels = listOf("X", "Y", "Z")

/** Qué fila de la transformación se está editando. Solo una a la vez. */
private enum class Field(val label: String, val short: String, val decimals: Int) {
    LOCATION("Posición", "Pos", 3),
    ROTATION("Rotación", "Rot", 1),
    SCALE("Escala", "Esc", 3),
}

/**
 * Transformación del objeto activo, en una barra inferior que se despliega.
 *
 * Sustituye al panel numérico fijo, que ocupaba una esquina permanentemente para algo
 * que se consulta a ratos. En reposo es una sola línea con los valores en crudo; se
 * toca y se abre lo editable, una fila cada vez.
 */
@Composable
fun TransformFooter(
    objectName: String,
    transform: Transform,
    onLocation: (Float, Float, Float) -> Unit,
    onRotationDegrees: (Float, Float, Float) -> Unit,
    onScale: (Float, Float, Float) -> Unit,
    modifier: Modifier = Modifier,
) {
    var expanded by remember { mutableStateOf(false) }
    var field by remember { mutableStateOf(Field.LOCATION) }
    val degrees = transform.rotationEuler.map { Math.toDegrees(it.toDouble()).toFloat() }

    val values = when (field) {
        Field.LOCATION -> transform.location
        Field.ROTATION -> degrees
        Field.SCALE -> transform.scale
    }
    val commit = when (field) {
        Field.LOCATION -> onLocation
        Field.ROTATION -> onRotationDegrees
        Field.SCALE -> onScale
    }

    FloatingPanel(modifier) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            AnimatedVisibility(
                visible = expanded,
                enter = fadeIn(tween(120)) + expandVertically(tween(140)),
                exit = fadeOut(tween(100)) + shrinkVertically(tween(120)),
            ) {
                Column {
                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        for (option in Field.entries) {
                            PillButton(option.label, selected = option == field) { field = option }
                        }
                    }
                    Spacer(Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        for (index in 0..2) {
                            AxisField(
                                label = AxisLabels[index],
                                color = AxisColors[index],
                                value = values.getOrElse(index) { 0f },
                                decimals = field.decimals,
                                onCommit = { typed ->
                                    val next = values.toMutableList()
                                    while (next.size < 3) next.add(0f)
                                    next[index] = typed
                                    commit(next[0], next[1], next[2])
                                },
                            )
                        }
                    }
                    Spacer(Modifier.height(6.dp))
                }
            }

            Row(
                Modifier
                    .clip(RoundedCornerShape(8.dp))
                    .clickableNoRipple { expanded = !expanded }
                    .padding(horizontal = 6.dp, vertical = 2.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(objectName, color = Ink.OnPanel, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.width(10.dp))
                // Resumen plegado: los tres ejes de la fila activa, con su color.
                Text(field.short, color = Ink.Faint, fontSize = 11.sp)
                Spacer(Modifier.width(5.dp))
                for (index in 0..2) {
                    Text(
                        format(values.getOrElse(index) { 0f }, field.decimals),
                        color = AxisColors[index],
                        fontSize = 11.sp,
                        modifier = Modifier.padding(end = 7.dp),
                    )
                }
                Icon(
                    if (expanded) Icons.Default.ExpandMore else Icons.Default.ExpandLess,
                    if (expanded) "Plegar" else "Desplegar",
                    Modifier.size(16.dp),
                    tint = Ink.Faint,
                )
            }
        }
    }
}

@Composable
private fun AxisField(
    label: String,
    color: Color,
    value: Float,
    decimals: Int,
    onCommit: (Float) -> Unit,
) {
    val formatted = format(value, decimals)
    // Mientras se escribe mandan las teclas; en cuanto se confirma vuelve a mandar
    // Blender. Si no, el estado que llega a 10 Hz borraría lo tecleado.
    var editing by remember { mutableStateOf(false) }
    var text by remember { mutableStateOf(formatted) }
    if (!editing && text != formatted) text = formatted

    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            Modifier
                .size(14.dp)
                .clip(RoundedCornerShape(4.dp))
                .background(color.copy(alpha = .85f)),
            contentAlignment = Alignment.Center,
        ) {
            Text(label, color = Color.Black.copy(alpha = .75f), fontSize = 9.sp, fontWeight = FontWeight.Bold)
        }
        TextField(
            value = text,
            onValueChange = { editing = true; text = it },
            singleLine = true,
            textStyle = TextStyle(fontSize = 13.sp, textAlign = TextAlign.End),
            colors = TextFieldDefaults.colors(
                focusedContainerColor = Color.Transparent,
                unfocusedContainerColor = Color.Transparent,
                focusedTextColor = Ink.OnPanel,
                unfocusedTextColor = Ink.Muted,
            ),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number, imeAction = ImeAction.Done),
            keyboardActions = KeyboardActions(onDone = {
                text.replace(',', '.').trim().toFloatOrNull()?.let(onCommit)
                editing = false
            }),
            modifier = Modifier.width(96.dp),
        )
    }
}

private fun format(value: Float, decimals: Int): String {
    val factor = when (decimals) {
        1 -> 10f
        2 -> 100f
        else -> 1000f
    }
    val rounded = (value * factor).roundToInt() / factor
    // Evita "-0.0" y las colas de coma flotante.
    return if (rounded == 0f) "0" else rounded.toString()
}
