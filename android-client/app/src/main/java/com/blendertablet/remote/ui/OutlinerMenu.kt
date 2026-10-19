package com.blendertablet.remote.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.blendertablet.remote.model.ActionId
import com.blendertablet.remote.model.OutlinerObject
import com.blendertablet.remote.model.OutlinerCollection
import com.blendertablet.remote.model.outlinerTreeRows
import com.blendertablet.remote.model.treeName

@Composable
fun OutlinerMenu(
    objects: List<OutlinerObject>, connected: Boolean, editable: Boolean,
    onOpen: () -> Unit, onMove: (String) -> Unit,
    onAction: (String, String, Boolean?, String?) -> Unit,
    collections: List<OutlinerCollection>, collectionsAvailable: Boolean,
    onCollection: (String, Map<String, Any?>) -> Unit,
) {
    var open by remember { mutableStateOf(false) }
    var query by remember { mutableStateOf("") }
    var rename by remember { mutableStateOf<OutlinerObject?>(null) }
    var createCollection by remember { mutableStateOf(false) }
    var moveToCollection by remember { mutableStateOf<List<String>?>(null) }
    var createTargets by remember { mutableStateOf(emptyList<String>()) }
    var renameCollection by remember { mutableStateOf<OutlinerCollection?>(null) }
    var collapsed by remember { mutableStateOf(emptySet<String>()) }
    val width = (LocalConfiguration.current.screenWidthDp - 32).coerceIn(280, 560).dp
    val maxHeight = (LocalConfiguration.current.screenHeightDp - 100).coerceAtLeast(140).dp
    Box {
        PillButton("Outliner", selected = open, enabled = connected) { onOpen(); open = true }
        DropdownMenu(open && connected, { open = false }, Modifier.width(width).heightIn(max = maxHeight),
            containerColor = Ink.PanelSolid) {
            Column(Modifier.padding(horizontal = 10.dp, vertical = 4.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text("OBJETOS · ${objects.size}", color = Ink.Accent, fontSize = 12.sp, modifier = Modifier.weight(1f))
                    IconAction(AppIcons.Cancel, "Cerrar Outliner") { open = false }
                }
                if (collectionsAvailable) Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    PillButton("+ Nueva colección", enabled = editable && collections.any { it.editable }) {
                        createTargets = objects.filter { it.selected }.map { it.id }; createCollection = true; open = false
                    }
                    val selection = objects.filter { it.selected }.map { it.id }
                    PillButton("Mover selección (${selection.size})", enabled = editable && selection.isNotEmpty()) {
                        moveToCollection = selection; open = false
                    }
                }
                BasicTextField(query, { query = it }, singleLine = true,
                    textStyle = TextStyle(color = Ink.OnPanel, fontSize = 13.sp), cursorBrush = SolidColor(Ink.Accent),
                    modifier = Modifier.fillMaxWidth().background(Color.White.copy(alpha = .06f), RoundedCornerShape(8.dp)).padding(10.dp),
                    decorationBox = { inner -> Box { if (query.isEmpty()) Text("Buscar objeto o colección…", color = Ink.Faint, fontSize = 13.sp); inner() } })
                if (!editable) Text("Termina la herramienta y entra en Object para modificar objetos.", color = Ink.Muted, fontSize = 11.sp)
                val rows = outlinerTreeRows(collections, objects, collapsed, query)
                if (rows.isEmpty()) Text("No hay coincidencias.", color = Ink.Muted, fontSize = 12.sp)
                rows.forEach { entry ->
                    val collection = entry.collection
                    if (collection != null) {
                        CollectionRow(collection, entry.depth, entry.expanded, entry.hasChildren,
                            onToggle = { collapsed = if (collection.id in collapsed) collapsed - collection.id else collapsed + collection.id },
                            toggleEnabled = query.isBlank(),
                            onRename = if (editable && collection.editable && !collection.root) ({
                                renameCollection = collection; open = false
                            }) else null,
                            onVisibility = if (editable && collection.editable && !collection.root) ({
                                onCollection("VISIBLE", mapOf("collection_id" to collection.id, "value" to collection.hidden))
                            }) else null,
                            onLock = if (editable && collection.editable && !collection.root) ({
                                onCollection("LOCK", mapOf("collection_id" to collection.id, "value" to !collection.locked))
                            }) else null)
                    }
                    entry.obj?.let { obj ->
                        Row(Modifier.fillMaxWidth().padding(start = (entry.depth.coerceAtMost(6) * 14).dp).background(if (obj.selected) Ink.Accent.copy(alpha = if (obj.active) .22f else .12f) else Color.Transparent,
                            RoundedCornerShape(8.dp)).padding(start = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                            HoverHelp(obj.name, "Tocar añade a la selección; volver a tocar lo quita.",
                                modifier = Modifier.weight(1f), enabled = editable && obj.canSelect) {
                                Column(Modifier.fillMaxWidth().heightIn(min = 44.dp)
                                    .then(if (editable && obj.canSelect) Modifier.clickableNoRipple {
                                        onAction(obj.id, "SELECT", null, null)
                                    } else Modifier), verticalArrangement = Arrangement.Center) {
                                    Text(obj.name, color = if (obj.visible) Ink.OnPanel else Ink.Faint, fontSize = 13.sp,
                                        maxLines = 1, overflow = TextOverflow.Ellipsis)
                                    val status = when {
                                        !obj.inViewLayer -> "Fuera de la capa de vista"
                                        !obj.visible && !obj.hidden -> "Oculto por colección o aislamiento"
                                        obj.collectionLocked -> "Bloqueado por colección"
                                        obj.locked -> "Selección bloqueada"
                                        obj.hidden -> "Oculto"
                                        else -> obj.parent?.let { "↳ $it" } ?: ""
                                    }
                                    if (status.isNotEmpty()) Text(status, color = Ink.Faint, fontSize = 10.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                }
                            }
                            IconAction(AppIcons.Move, "Mover ${obj.name}", enabled = editable && obj.editable && obj.canSelect) {
                                open = false; onMove(obj.id)
                            }
                            IconAction(AppIcons.action(ActionId.RENAME), "Renombrar ${obj.name}", enabled = editable && obj.editable) {
                                rename = obj; open = false
                            }
                            if (collectionsAvailable) IconAction(AppIcons.Collection, if (obj.selected) "Mover toda la selección a colección" else "Mover ${obj.name} a colección", enabled = editable && obj.editable) {
                                moveToCollection = if (obj.selected) objects.filter { it.selected }.map { it.id } else listOf(obj.id); open = false
                            }
                            IconAction(AppIcons.visibility(obj.visible), if (obj.hidden) "Mostrar ${obj.name}" else "Ocultar ${obj.name}",
                                enabled = editable && obj.editable && obj.inViewLayer && (obj.hidden || obj.visible)) {
                                onAction(obj.id, "VISIBLE", obj.hidden, null)
                            }
                            IconAction(AppIcons.selectionLock(obj.locked), if (obj.locked) "Desbloquear ${obj.name}" else "Bloquear ${obj.name}",
                                selected = obj.locked || obj.collectionLocked, enabled = editable && obj.editable && !obj.collectionLocked) {
                                onAction(obj.id, "LOCK", !obj.locked, null)
                            }
                        }
                    }
                }
            }
        }
    }
    renameCollection?.let { target ->
        RenameDialog(target.name, title = "Renombrar colección",
            onDismiss = { renameCollection = null; open = true }, onRename = { name ->
                onCollection("RENAME", mapOf("collection_id" to target.id, "name" to name))
                renameCollection = null; open = true
            })
    }
    rename?.let { target ->
        RenameDialog(target.name, onDismiss = { rename = null; open = true }, onRename = { name ->
            onAction(target.id, "RENAME", null, name); rename = null; open = true
        })
    }
    if (createCollection) NewCollectionDialog(
        collections, createTargets, editable,
        onDismiss = { createCollection = false; open = true },
        onCreate = { name, parent, ids ->
            onCollection("CREATE", mapOf("name" to name, "parent_id" to parent, "object_ids" to ids))
            collapsed = emptySet(); query = ""; createCollection = false; open = true
        })
    moveToCollection?.let { target ->
        AlertDialog(onDismissRequest = { moveToCollection = null; open = true }, containerColor = Ink.PanelSolid,
            title = { Text("Mover ${target.size} objetos a colección", color = Ink.OnPanel, fontSize = 16.sp) },
            text = {
                Column(Modifier.heightIn(max = 360.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    PillButton("+ Nueva colección", enabled = editable) {
                        createTargets = target; moveToCollection = null; createCollection = true
                    }
                    CollectionPicker(collections, editable) { collection ->
                        onCollection("MOVE_OBJECTS", mapOf("collection_id" to collection.id, "object_ids" to target))
                        collapsed = emptySet(); query = ""; moveToCollection = null; open = true
                    }
                }
            },
            confirmButton = {},
            dismissButton = { PillButton("Cancelar") { moveToCollection = null; open = true } })
    }
}

@Composable
private fun NewCollectionDialog(collections: List<OutlinerCollection>, selected: List<String>,
                                enabled: Boolean, onDismiss: () -> Unit,
                                onCreate: (String, String, List<String>) -> Unit) {
    var name by remember { mutableStateOf("Colección") }
    var parentId by remember { mutableStateOf(collections.firstOrNull { it.root }?.id) }
    var includeSelection by remember { mutableStateOf(selected.isNotEmpty()) }
    var parentMenu by remember { mutableStateOf(false) }
    val parent = collections.firstOrNull { it.id == parentId }
    AlertDialog(onDismissRequest = onDismiss, containerColor = Ink.PanelSolid,
        title = { Text("Nueva colección", color = Ink.OnPanel, fontSize = 16.sp) },
        text = { Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(name, { name = it }, label = { Text("Nombre") }, singleLine = true)
            Box {
                PillButton("Dentro de: ${parent?.treeName ?: "Elige colección"} ▾") { parentMenu = true }
                DropdownMenu(parentMenu, { parentMenu = false }, Modifier.width(300.dp).heightIn(max = 320.dp)) {
                    CollectionPicker(collections, enabled) { collection -> parentId = collection.id; parentMenu = false }
                }
            }
            PillButton("Mover selección (${selected.size})", selected = includeSelection, enabled = selected.isNotEmpty()) {
                includeSelection = !includeSelection
            }
        } },
        confirmButton = { PillButton("Crear", selected = true, enabled = enabled && name.isNotBlank() && parent?.editable == true) {
            parent?.let { onCreate(name.trim(), it.id, if (includeSelection) selected else emptyList()) }
        } },
        dismissButton = { PillButton("Cancelar", onClick = onDismiss) })
}

/** Misma jerarquía para explorar, elegir destino y elegir el padre de una colección. */
@Composable
private fun CollectionRow(
    collection: OutlinerCollection, depth: Int, expanded: Boolean, hasChildren: Boolean,
    onToggle: () -> Unit, toggleEnabled: Boolean = true,
    onChoose: (() -> Unit)? = null, chooseEnabled: Boolean = true,
    onRename: (() -> Unit)? = null,
    onVisibility: (() -> Unit)? = null, onLock: (() -> Unit)? = null,
) {
    Row(Modifier.fillMaxWidth().padding(start = (depth.coerceAtMost(6) * 14).dp),
        verticalAlignment = Alignment.CenterVertically) {
        IconAction(AppIcons.disclosure(expanded), "${if (expanded) "Plegar" else "Desplegar"} ${collection.treeName}",
            enabled = hasChildren && toggleEnabled, onClick = onToggle)
        HoverHelp(collection.treeName, if (collection.root) "Raíz: contiene todas las colecciones." else collection.path,
            modifier = Modifier.weight(1f), enabled = chooseEnabled) {
            Row(Modifier.fillMaxWidth().heightIn(min = 44.dp)
                .then(if (onChoose != null && chooseEnabled) Modifier.clickableNoRipple(onChoose)
                    else if (onChoose == null && hasChildren && toggleEnabled) Modifier.clickableNoRipple(onToggle) else Modifier),
                verticalAlignment = Alignment.CenterVertically) {
                Text(collection.treeName, color = if (chooseEnabled) Ink.Accent else Ink.Faint,
                    fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
        if (onRename != null) IconAction(AppIcons.action(ActionId.RENAME), "Renombrar ${collection.treeName}", onClick = onRename)
        if (onVisibility != null) IconAction(AppIcons.visibility(!collection.hidden),
            "${if (collection.hidden) "Mostrar" else "Ocultar"} colección ${collection.treeName}", onClick = onVisibility)
        if (onLock != null) IconAction(AppIcons.selectionLock(collection.locked),
            "${if (collection.locked) "Desbloquear" else "Bloquear"} colección ${collection.treeName}", selected = collection.locked, onClick = onLock)
    }
}

@Composable
private fun CollectionPicker(collections: List<OutlinerCollection>, enabled: Boolean, onChoose: (OutlinerCollection) -> Unit) {
    var collapsed by remember { mutableStateOf(emptySet<String>()) }
    outlinerTreeRows(collections, collapsed = collapsed).forEach { row ->
        row.collection?.let { collection ->
            CollectionRow(collection, row.depth, row.expanded, row.hasChildren,
                onToggle = { collapsed = if (collection.id in collapsed) collapsed - collection.id else collapsed + collection.id },
                onChoose = { onChoose(collection) }, chooseEnabled = enabled && collection.editable)
        }
    }
}
