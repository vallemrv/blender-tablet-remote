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
import androidx.compose.material3.DropdownMenu
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

@Composable
fun OutlinerMenu(
    objects: List<OutlinerObject>, connected: Boolean, editable: Boolean,
    onOpen: () -> Unit, onMove: (String) -> Unit,
    onAction: (String, String, Boolean?, String?) -> Unit,
) {
    var open by remember { mutableStateOf(false) }
    var query by remember { mutableStateOf("") }
    var rename by remember { mutableStateOf<OutlinerObject?>(null) }
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
                BasicTextField(query, { query = it }, singleLine = true,
                    textStyle = TextStyle(color = Ink.OnPanel, fontSize = 13.sp), cursorBrush = SolidColor(Ink.Accent),
                    modifier = Modifier.fillMaxWidth().background(Color.White.copy(alpha = .06f), RoundedCornerShape(8.dp)).padding(10.dp),
                    decorationBox = { inner -> Box { if (query.isEmpty()) Text("Buscar objeto…", color = Ink.Faint, fontSize = 13.sp); inner() } })
                if (!editable) Text("Termina la herramienta y entra en Object para modificar objetos.", color = Ink.Muted, fontSize = 11.sp)
                val filtered = objects.filter { it.name.contains(query, ignoreCase = true) || it.collections.any { c -> c.contains(query, true) } }
                if (filtered.isEmpty()) Text(if (objects.isEmpty()) "No hay objetos en esta escena." else "No hay coincidencias.",
                    color = Ink.Muted, fontSize = 12.sp, modifier = Modifier.padding(12.dp))
                filtered.forEach { obj ->
                    Row(Modifier.fillMaxWidth().background(if (obj.active) Ink.Accent.copy(alpha = .16f) else Color.Transparent,
                        RoundedCornerShape(8.dp)).padding(start = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                        HoverHelp(obj.name, "Selecciona este objeto y muestra sus propiedades.",
                            modifier = Modifier.weight(1f), enabled = editable && obj.canSelect) {
                            Column(Modifier.fillMaxWidth().heightIn(min = 44.dp)
                                .then(if (editable && obj.canSelect) Modifier.clickableNoRipple {
                                    onAction(obj.id, "SELECT", null, null)
                                } else Modifier), verticalArrangement = Arrangement.Center) {
                                Text(obj.name, color = if (obj.visible) Ink.OnPanel else Ink.Faint, fontSize = 13.sp,
                                    maxLines = 1, overflow = TextOverflow.Ellipsis)
                                val location = obj.parent?.let { "↳ $it" } ?: obj.collections.joinToString(" · ")
                                val status = when {
                                    !obj.inViewLayer -> "Fuera de la capa de vista"
                                    !obj.visible && !obj.hidden -> "Oculto por colección o aislamiento"
                                    obj.locked -> "Selección bloqueada"
                                    obj.hidden -> "Oculto"
                                    else -> location
                                }
                                Text(status, color = Ink.Faint, fontSize = 10.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            }
                        }
                        IconAction(AppIcons.Move, "Mover ${obj.name}", enabled = editable && obj.editable && obj.canSelect) {
                            open = false; onMove(obj.id)
                        }
                        IconAction(AppIcons.action(ActionId.RENAME), "Renombrar ${obj.name}", enabled = editable && obj.editable) {
                            rename = obj; open = false
                        }
                        IconAction(AppIcons.visibility(obj.visible), if (obj.hidden) "Mostrar ${obj.name}" else "Ocultar ${obj.name}",
                            enabled = editable && obj.editable && obj.inViewLayer && (obj.hidden || obj.visible)) {
                            onAction(obj.id, "VISIBLE", obj.hidden, null)
                        }
                        IconAction(AppIcons.selectionLock(obj.locked), if (obj.locked) "Desbloquear ${obj.name}" else "Bloquear ${obj.name}",
                            selected = obj.locked, enabled = editable && obj.editable) {
                            onAction(obj.id, "LOCK", !obj.locked, null)
                        }
                    }
                }
            }
        }
    }
    rename?.let { target ->
        RenameDialog(target.name, onDismiss = { rename = null; open = true }, onRename = { name ->
            onAction(target.id, "RENAME", null, name); rename = null; open = true
        })
    }
}
