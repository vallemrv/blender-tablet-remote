package com.blendertablet.remote.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.blendertablet.remote.model.RemoteFileEntry
import com.blendertablet.remote.model.RemoteFileType
import com.blendertablet.remote.model.RemoteFiles

enum class FileBrowserMode { OPEN, SAVE }

@Composable
fun FileBrowserDialog(
    mode: FileBrowserMode,
    files: RemoteFiles,
    canCreateFolder: Boolean,
    onCreateFolder: (folder: String, name: String) -> Unit,
    onClearFolderError: () -> Unit,
    initialName: String,
    onBrowse: (String) -> Unit,
    onSetDefault: (String) -> Unit,
    onDismiss: () -> Unit,
    onOpen: (String) -> Unit,
    onSave: (folder: String, name: String) -> Unit,
) {
    var name by remember(initialName) { mutableStateOf(initialName) }
    var newFolderOpen by remember(files.path) { mutableStateOf(false) }
    var folderName by remember(files.path) { mutableStateOf("") }
    val dismiss = { if (!files.creatingFolder) onDismiss() }
    AlertDialog(
        onDismissRequest = dismiss,
        containerColor = Ink.PanelSolid,
        title = {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                Text(if (mode == FileBrowserMode.OPEN) "Abrir archivo" else "Guardar como", fontSize = 16.sp)
                if (mode == FileBrowserMode.SAVE && canCreateFolder) {
                    IconAction(AppIcons.NewFolder, "Nueva carpeta", enabled = files.path.isNotBlank() && !files.loading && !files.creatingFolder) {
                        onClearFolderError(); folderName = ""; newFolderOpen = true
                    }
                }
            }
        },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                if (files.locations.isNotEmpty()) {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        files.locations.forEach { location ->
                            PillButton(location.label, selected = location.path == files.path) { onBrowse(location.path) }
                        }
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(5.dp), modifier = Modifier.fillMaxWidth()) {
                    files.parent?.let { PillButton("↑", onClick = { onBrowse(it) }) }
                    files.breadcrumbs.takeLast(4).forEach { crumb ->
                        Text(
                            crumb.name,
                            color = Ink.Accent,
                            fontSize = 12.sp,
                            modifier = Modifier.clickable { onBrowse(crumb.path) },
                        )
                    }
                }
                Text(files.path.ifBlank { "Cargando…" }, color = Ink.Faint, fontSize = 11.sp)
                LazyColumn(Modifier.fillMaxWidth().heightIn(min = 180.dp, max = 360.dp)) {
                    items(files.entries, key = { it.rowKey }) { entry ->
                        FileRow(entry) {
                            if (entry.type == RemoteFileType.DIRECTORY) onBrowse(entry.path)
                            else if (mode == FileBrowserMode.OPEN) onOpen(entry.path)
                            else name = entry.name
                        }
                    }
                    if (!files.loading && files.entries.isEmpty()) {
                        item { Text("Carpeta vacía", color = Ink.Faint, fontSize = 13.sp) }
                    }
                }
                if (mode == FileBrowserMode.SAVE) {
                    OutlinedTextField(
                        value = name,
                        onValueChange = { name = it },
                        label = { Text("Nombre del archivo") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
                if (files.path.isNotBlank()) {
                    PillButton(
                        if (files.path == files.defaultFolder) "✓ Carpeta predeterminada" else "Usar esta carpeta por defecto",
                        selected = files.path == files.defaultFolder,
                        onClick = { onSetDefault(files.path) },
                    )
                }
            }
        },
        confirmButton = {
            if (mode == FileBrowserMode.SAVE) {
                PillButton("Guardar", selected = true, enabled = files.path.isNotBlank() && name.isNotBlank()) {
                    onSave(files.path, name.trim())
                }
            }
        },
        dismissButton = { PillButton("Cancelar", enabled = !files.creatingFolder, onClick = dismiss) },
    )
    if (newFolderOpen) {
        val cleanName = folderName.trim()
        val valid = cleanName.isNotEmpty() && cleanName !in setOf(".", "..") &&
            cleanName.none { it in "/\\:\u0000" }
        AlertDialog(
            onDismissRequest = { if (!files.creatingFolder) newFolderOpen = false },
            title = { Text("Nueva carpeta") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(folderName, { folderName = it; onClearFolderError() },
                        label = { Text("Nombre de la carpeta") }, singleLine = true,
                        enabled = !files.creatingFolder, modifier = Modifier.fillMaxWidth())
                    files.folderError?.let { Text(it, color = Ink.Warn) }
                    if (cleanName.isNotEmpty() && !valid) Text("Escribe solo el nombre, sin rutas ni separadores.", color = Ink.Warn)
                }
            },
            confirmButton = {
                PillButton(if (files.creatingFolder) "Creando…" else "Crear", selected = true,
                    enabled = valid && !files.creatingFolder) { onCreateFolder(files.path, cleanName) }
            },
            dismissButton = { PillButton("Cancelar", enabled = !files.creatingFolder) { newFolderOpen = false } },
        )
    }
}

@Composable
private fun FileRow(entry: RemoteFileEntry, onClick: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Text(if (entry.type == RemoteFileType.DIRECTORY) "📁" else "◈", fontSize = 18.sp)
        Text(entry.name, color = Ink.OnPanel, fontSize = 14.sp, fontWeight = FontWeight.Medium)
    }
}
