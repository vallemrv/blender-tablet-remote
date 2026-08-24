package com.blendertablet.remote.ui

import androidx.compose.foundation.layout.Arrangement
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
 * Guardar como. La ruta es del PC, no de la tablet, así que se escribe a mano; para
 * no obligar a teclear un path entero se propone la carpeta del archivo actual (o la
 * del último reciente) y solo hay que cambiar el nombre.
 */
@Composable
fun SaveAsDialog(
    initialFolder: String,
    initialName: String,
    onDismiss: () -> Unit,
    onSave: (String) -> Unit,
) {
    var folder by remember { mutableStateOf(initialFolder) }
    var name by remember { mutableStateOf(initialName) }
    val complete = folder.isNotBlank() && name.isNotBlank()

    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = Ink.PanelSolid,
        title = { Text("Guardar como", color = Ink.OnPanel, fontSize = 16.sp) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedTextField(
                    value = folder,
                    onValueChange = { folder = it },
                    label = { Text("Carpeta en el PC") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text("Nombre") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Text(
                    "Si falta la extensión, el servidor añade .blend",
                    color = Ink.Faint,
                    fontSize = 11.sp,
                )
            }
        },
        confirmButton = {
            PillButton("Guardar", selected = true, enabled = complete) {
                onSave(folder.trimEnd('/') + "/" + name.trim())
            }
        },
        dismissButton = { PillButton("Cancelar", onClick = onDismiss) },
    )
}

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
) {
    var name by remember { mutableStateOf(initialName) }
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = Ink.PanelSolid,
        title = { Text("Renombrar objeto", color = Ink.OnPanel, fontSize = 16.sp) },
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
