package com.blendertablet.remote.ui

import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.sp

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.blendertablet.remote.model.CadDrawingMeshTarget
import com.blendertablet.remote.model.NumericExpression

@Composable
fun DrawingMeshDialog(target: CadDrawingMeshTarget, current: Boolean, onDismiss: () -> Unit, onCreate: (Int) -> Unit) {
    var input by remember(target) { mutableStateOf("64") }
    val parsed = NumericExpression.evaluate(input)
    val resolution = parsed?.takeIf { it in 3.0..4096.0 && it == kotlin.math.floor(it) }?.toInt()
    fun create() { if (current && (!target.curved || resolution != null)) onCreate(if(target.curved) resolution!! else 64) }
    AlertDialog(onDismissRequest = onDismiss, title = { Text("Crear malla del dibujo") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("${target.name} · ${target.count} figuras")
                Text("Crea una copia de vértices y aristas, sin caras. El boceto original se conserva.")
                if (target.curved) {
                    Text("Vértices por círculo completo; los arcos usan la parte correspondiente.")
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        QuickToolValues(listOf(32,64,128), parsed ?: 64.0) { input = it.toInt().toString() }
                        var base by remember { mutableStateOf(64) }
                        HoverHelp("Resolución", numberHelp(true)) {
                            ScrubNumber(enabled = resolution != null, onScrubStart = { base = resolution ?: 64 },
                                onScrub = { steps -> input = (base + steps).coerceIn(3, 4096).toString() },
                                onReset = { input = "64" }) { field ->
                                CompactNumericField(input, { input = it }, field.width(96.dp), fontSize = 16.sp,
                                    textAlign = TextAlign.End, selectAllOnFocus = true, onDone = ::create)
                            }
                        }
                    }
                }
                Text("Las líneas y los polígonos conservan sus vértices originales.")
                if (!current) Text("El boceto ha cambiado. Cierra y vuelve a seleccionar el dibujo.", color = Ink.Warn)
            }
        },
        confirmButton = { TextButton(onClick = ::create, enabled = current && (!target.curved || resolution != null)) { Text("Crear malla") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancelar") } })
}
