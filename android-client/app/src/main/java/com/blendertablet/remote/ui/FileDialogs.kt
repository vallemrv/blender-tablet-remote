package com.blendertablet.remote.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * Confirmación antes de descartar cambios. Solo se enseña si el archivo está sucio:
 * preguntar siempre entrena a decir que sí sin leer.
 */
@Composable
fun ConfirmDiscardDialog(
    title: String,
    message: String,
    confirmLabel: String,
    onDismiss: () -> Unit,
    onConfirm: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = Ink.PanelSolid,
        title = { Text(title, color = Ink.OnPanel, fontSize = 16.sp) },
        text = { Text(message, color = Ink.Muted, fontSize = 13.sp) },
        confirmButton = {
            PillButton(confirmLabel, selected = true) { onConfirm() }
        },
        dismissButton = { PillButton("Cancelar", onClick = onDismiss) },
    )
}

/** Renombrar el objeto activo. Una sola caja de texto, nada más. */
@Composable
fun RenameDialog(
    initialName: String,
    onDismiss: () -> Unit,
    onRename: (String) -> Unit,
    title: String = "Renombrar objeto",
) {
    var name by remember { mutableStateOf(initialName) }
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = Ink.PanelSolid,
        title = { Text(title, color = Ink.OnPanel, fontSize = 16.sp) },
        text = {
            OutlinedTextField(
                value = name,
                onValueChange = { name = it },
                label = { Text("Nombre") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
        },
        confirmButton = {
            PillButton("Renombrar", selected = true, enabled = name.isNotBlank()) {
                onRename(name.trim())
            }
        },
        dismissButton = { PillButton("Cancelar", onClick = onDismiss) },
    )
}


@Composable
fun NewSceneDialog(
    presets: List<com.blendertablet.remote.model.SceneScale>,
    onDismiss: () -> Unit,
    onCreate: (String) -> Unit,
) {
    var selected by remember { mutableStateOf<String?>(null) }
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = Ink.PanelSolid,
        title = { Text("Nueva escena", color = Ink.OnPanel, fontSize = 16.sp) },
        text = {
            Column(verticalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(8.dp)) {
                Text("Elige la escala de trabajo. Define las unidades, los pasos iniciales y la rejilla; queda asociada a esta escena.",
                    color = Ink.Muted, fontSize = 13.sp)
                presets.forEach { preset ->
                    PillButton("${preset.label} · ${preset.lengthUnit.short}", selected = selected == preset.id) {
                        selected = preset.id
                    }
                }
                if (presets.isEmpty()) Text("Cargando escalas…", color = Ink.Muted, fontSize = 13.sp)
            }
        },
        confirmButton = {
            PillButton("Crear", selected = true, enabled = presets.any { it.id == selected }) {
                selected?.let(onCreate)
            }
        },
        dismissButton = { PillButton("Cancelar", onClick = onDismiss) },
    )
}
