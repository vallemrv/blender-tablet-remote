package com.blendertablet.remote.ui

import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.sp

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.blendertablet.remote.model.BlenderMode
import com.blendertablet.remote.model.BlenderState

@Composable
internal fun VertexGroupControls(state: BlenderState, command: (String, Map<String, Any?>) -> Unit) {
    var expanded by remember(state.activeObject) { mutableStateOf(false) }
    var chosen by remember(state.activeObject) { mutableStateOf<String?>(null) }
    var menu by remember(state.activeObject) { mutableStateOf(false) }
    var rename by remember(state.activeObject) { mutableStateOf<Boolean?>(null) }
    var name by remember(state.activeObject) { mutableStateOf("") }
    var weight by remember(state.activeObject) { mutableStateOf("1") }
    val group = state.vertexGroups.firstOrNull { it.name == chosen }
        ?: state.vertexGroups.firstOrNull { it.name == state.activeVertexGroup }
        ?: state.vertexGroups.firstOrNull()
    val editing = state.mode == BlenderMode.EDIT
    val parsedWeight = vertexGroupWeight(weight)
    val hasSelection = state.context.selectionCounts.verts > 0
    PillButton("Grupos de vértices (${state.vertexGroups.size})", selected = expanded) { expanded = !expanded }
    if (!expanded) return
    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        Box(Modifier.weight(1f)) {
            PillButton(group?.name ?: "Sin grupos", enabled = state.vertexGroups.isNotEmpty()) { menu = true }
            DropdownMenu(menu, { menu = false }) {
                state.vertexGroups.forEach { candidate ->
                    DropdownMenuItem(text = { Text(candidate.name) }, onClick = { chosen = candidate.name; menu = false })
                }
            }
        }
        PillButton("Guardar selección") { name = ""; rename = false }
    }
    if (group != null) {
        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            PillButton("Renombrar") { name = group.name; rename = true }
            PillButton("Borrar") { command("delete", mapOf("name" to group.name)); chosen = null }
        }
        if (!editing) Text("Entra en Edit y selecciona vértices para asignarlos.", fontSize = 11.sp, color = Ink.Muted)
        if (group.locked) Text("Grupo bloqueado en Blender", fontSize = 11.sp, color = Ink.Muted)
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("Peso (0–1)", fontSize = 12.sp, color = Ink.Muted)
            var base by remember { mutableStateOf(1.0) }
            HoverHelp("Peso", numberHelp(true)) {
                ScrubNumber(enabled = parsedWeight != null, onScrubStart = { base = parsedWeight ?: 1.0 },
                    onScrub = { steps -> weight = formatToolDistance((base + steps * .05).coerceIn(0.0, 1.0), 2) },
                    onReset = { weight = "1" }) { field ->
                    CompactNumericField(weight, { weight = it }, field.width(96.dp), fontSize = 16.sp,
                        textAlign = TextAlign.End, selectAllOnFocus = true, onDone = {})
                }
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            PillButton("Asignar", enabled = editing && hasSelection && !group.locked && parsedWeight != null) {
                command("edit", mapOf("name" to group.name, "action" to "ASSIGN", "weight" to parsedWeight))
            }
            PillButton("Quitar", enabled = editing && hasSelection && !group.locked) {
                command("edit", mapOf("name" to group.name, "action" to "REMOVE"))
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            PillButton("Seleccionar", enabled = editing) { command("edit", mapOf("name" to group.name, "action" to "SELECT")) }
            PillButton("Deseleccionar", enabled = editing) { command("edit", mapOf("name" to group.name, "action" to "DESELECT")) }
        }
    }
    if (rename == false) SaveVertexGroupDialog(
        onDismiss = { rename = null },
        onSave = { newName ->
            command("create", mapOf("name" to newName, "assign_selection" to true))
            chosen = newName; rename = null
        },
    )
    if (rename == true && group != null) {
        AlertDialog(onDismissRequest = { rename = null }, containerColor = Ink.PanelSolid,
            title = { Text("Renombrar grupo") },
            text = { OutlinedTextField(name, { name = it }, singleLine = true, label = { Text("Nombre") }) },
            confirmButton = { PillButton("Renombrar", enabled = vertexGroupNameValid(name)) {
                val newName = name.trim()
                command("rename", mapOf("name" to group.name, "new_name" to newName))
                chosen = newName; rename = null
            } }, dismissButton = { PillButton("Cancelar") { rename = null } })
    }

}

internal fun vertexGroupWeight(text: String): Double? = text.trim().replace(',', '.').toDoubleOrNull()
    ?.takeIf { it.isFinite() && it in 0.0..1.0 }

/** Saving a selection is the same interaction in painting and modifier groups. */
@Composable
internal fun SaveVertexGroupDialog(onDismiss: () -> Unit, onSave: (String) -> Unit) {
    var name by remember { mutableStateOf("") }
    AlertDialog(onDismissRequest = onDismiss, containerColor = Ink.PanelSolid,
        title = { Text("Guardar selección como grupo") },
        text = { Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Guarda los vértices seleccionados en Edit. El grupo sirve para modificadores y como zona de pintura.")
            OutlinedTextField(name, { name = it }, singleLine = true, label = { Text("Nombre del grupo") })
        } },
        confirmButton = { PillButton("Guardar", enabled = vertexGroupNameValid(name)) { onSave(name.trim()) } },
        dismissButton = { PillButton("Cancelar", onClick = onDismiss) })
}

internal fun vertexGroupNameValid(name: String): Boolean = name.isNotBlank() && name.trim().toByteArray().size <= 63
