package com.blendertablet.remote.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.sp
import com.blendertablet.remote.model.LengthUnit
import com.blendertablet.remote.model.ObjectProperties
import com.blendertablet.remote.model.ObjectPropertiesResult
import com.blendertablet.remote.model.ObjectPropertyField
import com.blendertablet.remote.model.objectPropertyDisplay
import com.blendertablet.remote.model.objectPropertyNumber

/** Inspector del activo. El esquema decide los campos; los borradores son locales. */
@Composable
fun ObjectPropertiesTray(
    properties: ObjectProperties?,
    unit: LengthUnit,
    result: ObjectPropertiesResult?,
    objects: List<Pair<String, String>>,
    onOpenObjects: () -> Unit,
    onSelectObject: (String) -> Unit,
    onApply: (String, String, Map<String, Any?>, String) -> Unit,
    modifier: Modifier = Modifier,
) {
    var drafts by remember(properties?.id, unit) { mutableStateOf<Map<String, Any?>>(emptyMap()) }
    var baseline by remember(properties?.id, unit) { mutableStateOf<String?>(null) }
    var pending by remember(properties?.id, unit) { mutableStateOf<String?>(null) }
    val fields = properties?.fields.orEmpty()
    val groups = fields.map { it.group }.distinct()
    var group by remember(properties?.id) { mutableStateOf(groups.firstOrNull().orEmpty()) }
    val selectedGroup = group.takeIf { it in groups } ?: groups.firstOrNull()
    val changedRemotely = baseline != null && baseline != properties?.revision

    LaunchedEffect(result, pending) {
        if (pending != null && result?.token == pending) {
            if (result?.success == true) { drafts = emptyMap(); baseline = null }
            pending = null
        }
    }
    fun edit(field: ObjectPropertyField, value: Any?) {
        if (pending != null) return
        if (drafts.isEmpty()) baseline = properties?.revision
        drafts = drafts + (field.id to value)
    }
    val values = drafts.mapValues { (id, value) ->
        val field = fields.firstOrNull { it.id == id }
        if (field == null) null
        else if (field.type == "number") objectPropertyNumber(value as String, field, unit) else value
    }
    val valid = properties != null && drafts.isNotEmpty() && values.values.none { it == null } && !changedRemotely && pending == null

    val help = when {
        properties == null -> "Elige un objeto o imagen con el selector de objetos."
        pending != null -> "Aplicando propiedades…"
        changedRemotely -> "El objeto ha cambiado. Cancela el borrador para cargar sus valores actuales."
        drafts.isNotEmpty() -> "Cambios sin aplicar: Confirmar los guarda; Cancelar descarta el borrador."
        selectedGroup == "Posición" -> properties.note
        else -> "Propiedades del objeto activo · ${unit.short}"
    }
    SingleLineTray(
        title = "Objeto",
        modifier = modifier,
        onCancel = { if (pending == null) { drafts = emptyMap(); baseline = null } },
        onConfirm = {
            if (valid && properties != null) {
                val token = java.util.UUID.randomUUID().toString()
                pending = token
                onApply(properties.id, baseline ?: properties.revision, values, token)
            }
        },
        confirmEnabled = valid,
    ) {
        Box {
            var objectMenu by remember { mutableStateOf(false) }
            IconAction(AppIcons.material("OBJECTS"), "Elegir objeto o imagen",
                enabled = drafts.isEmpty() && pending == null) { onOpenObjects(); objectMenu = true }
            DropdownMenu(objectMenu, { objectMenu = false }, Modifier.heightIn(max = 320.dp)) {
                objects.forEach { (name, type) -> DropdownMenuItem(
                    text = { Text("$name · $type") },
                    onClick = { objectMenu = false; onSelectObject(name) }) }
            }
        }
        HoverHelp(properties?.name ?: "Elegir objeto", help) {
            Text(properties?.name ?: "Elige un objeto", color = Ink.Muted, fontSize = 12.sp,
                maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.widthIn(max = 160.dp))
        }
        groups.forEach { name -> PillButton(name, selected = name == selectedGroup) { group = name } }
        fields.filter { it.group == selectedGroup }.forEach { field ->
            PropertyControl(field, drafts[field.id] ?: properties?.values?.get(field.id),
                field.id in drafts, unit, pending == null && !field.readOnly) { edit(field, it) }
        }
        val status = when {
            pending != null -> "Aplicando…"
            changedRemotely -> "El objeto cambió: cancela el borrador"
            drafts.isNotEmpty() -> "Sin aplicar"
            else -> null
        }
        if (status != null) HoverHelp(status, help) {
            Text(status, color = if (changedRemotely) Ink.Bad else Ink.Muted, fontSize = 11.sp, maxLines = 1)
        }
    }
}

@Composable
private fun PropertyControl(field: ObjectPropertyField, value: Any?, draft: Boolean, unit: LengthUnit,
                            enabled: Boolean, onChange: (Any?) -> Unit) {
    val suffix = when (field.unit) { "length" -> unit.short; "percent" -> "%"; "factor" -> "×"; else -> "" }
    when (field.type) {
        "number" -> Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            val text = if (draft) value as? String ?: "" else (value as? Number)?.let {
                val shown = objectPropertyDisplay(it, field, unit)
                formatToolDistance(shown, detailDecimalPlaces(shown, 4))
            }.orEmpty()
            Text(field.label, color = Ink.Muted, fontSize = 12.sp)
            if (enabled) CompactNumericField(text, { onChange(it) }, modifier = Modifier.width(104.dp),
                textColor = if (draft && objectPropertyNumber(text, field, unit) == null) Ink.Bad else Ink.OnPanel,
                selectAllOnFocus = true, onDone = {})
            else Text(text, color = Ink.Faint, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
                modifier = Modifier.width(104.dp).padding(6.dp))
            Text(suffix, color = Ink.Muted, fontSize = 12.sp)
        }
        "bool" -> PillButton("${field.label}: ${if (value == true) "Sí" else "No"}",
            selected = value == true, enabled = enabled) { onChange(value != true) }
        "enum" -> {
            var open by remember(field.id) { mutableStateOf(false) }
            Box {
                PillButton("${field.label}: ${field.choices[value] ?: value}", enabled = enabled) { open = true }
                DropdownMenu(open, { open = false }) {
                    field.choices.forEach { (key, label) -> DropdownMenuItem(text = { Text(label) },
                        onClick = { open = false; onChange(key) }) }
                }
            }
        }
    }
}
