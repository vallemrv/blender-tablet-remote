package com.blendertablet.remote.ui

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.blendertablet.remote.model.TransformMode

/** La copia se crea al pulsar Duplicar; elegir la intención aún no modifica la escena. */
@Composable
fun DuplicateDialog(edit: Boolean, initialMode: TransformMode, initialLinked: Boolean,
                    onDismiss: () -> Unit, onDuplicate: (TransformMode, Boolean) -> Unit) {
    var mode by remember { mutableStateOf(initialMode) }
    var linked by remember { mutableStateOf(initialLinked) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (edit) "Duplicar selección" else "Duplicar") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("Colocar la copia con")
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    for (choice in listOf(TransformMode.MOVE, TransformMode.ROTATE)) {
                        Column {
                            IconAction(AppIcons.transform(choice), choice.label, selected = mode == choice) { mode = choice }
                            Text(choice.label, style = MaterialTheme.typography.labelMedium)
                        }
                    }
                }
                if (!edit) {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        IconAction(AppIcons.DuplicateLinked, "Copia enlazada", selected = linked) { linked = !linked }
                        Text("Copia enlazada\nComparte la geometría con el original.", modifier = Modifier.weight(1f), style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = { onDuplicate(mode, linked && !edit) }) { Text("Duplicar") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancelar") } },
    )
}
