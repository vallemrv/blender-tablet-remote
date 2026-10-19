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
import androidx.compose.material3.Icon
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
import com.blendertablet.remote.model.liveObjectPropertyNumber
import com.blendertablet.remote.model.transformStepUnit

/** Inspector del activo: cambios inmediatos; solo el texto incompleto permanece local. */
@Composable
fun ObjectPropertiesTray(
    properties: ObjectProperties?,
    selectedSection: String?,
    onSelectSection: (String, String) -> Unit,
    unit: LengthUnit,
    result: ObjectPropertiesResult?,
    stepMeters: Double,
    objects: List<Pair<String, String>>,
    onOpenObjects: () -> Unit,
    onSelectObject: (String) -> Unit,
    onApply: (String, String, Map<String, Any?>, String) -> Unit,
    modifier: Modifier = Modifier,
) {
    var drafts by remember(properties?.id, unit) { mutableStateOf<Map<String, Any?>>(emptyMap()) }
    var lastToken by remember(properties?.id, unit) { mutableStateOf<String?>(null) }
    var focused by remember(properties?.id, unit) { mutableStateOf<Set<String>>(emptySet()) }
    val fields = properties?.fields.orEmpty()
    val groups = fields.map { it.group }.distinct()
    val selectedGroup = selectedSection?.takeIf { it in groups } ?: groups.firstOrNull()

    LaunchedEffect(result, lastToken) {
        if (lastToken != null && result?.token == lastToken) {
            drafts = drafts.filterKeys { it in focused }
            lastToken = null
        }
    }
    fun edit(field: ObjectPropertyField, value: Any?) {
        val target = properties ?: return
        drafts = drafts + (field.id to value)
        val wire = if (field.type == "number") liveObjectPropertyNumber(value as String, field, unit) else value
        if (wire != null) {
            val token = java.util.UUID.randomUUID().toString()
            lastToken = token
            onApply(target.id, target.revision, mapOf(field.id to wire), token)
        }
    }
    val help = if (properties == null) "Elige un objeto o imagen."
        else "Los cambios se aplican directamente. Deshacer recupera el valor anterior."
    SingleLineTray(
        title = "Objeto",
        modifier = modifier,
    ) {
        Box {
            var objectMenu by remember { mutableStateOf(false) }
            IconAction(AppIcons.material("OBJECTS"), "Elegir objeto o imagen",
                enabled = lastToken == null) { onOpenObjects(); objectMenu = true }
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
        if (groups.isNotEmpty()) Box {
            var sectionMenu by remember { mutableStateOf(false) }
            PillButton("$selectedGroup ▾", selected = true) { sectionMenu = true }
            DropdownMenu(sectionMenu, { sectionMenu = false }) {
                groups.forEach { name -> DropdownMenuItem(
                    text = { Text(name) },
                    trailingIcon = { if (name == selectedGroup) Icon(AppIcons.Checked, null, tint = Ink.Accent) },
                    onClick = { properties?.let { onSelectSection(it.id, name) }; sectionMenu = false }) }
            }
        }
        fields.filter { it.group == selectedGroup }.forEach { field ->
            PropertyControl(field, drafts[field.id] ?: properties?.values?.get(field.id),
                field.id in drafts, unit, !field.readOnly, stepMeters,
                onFocus = { active ->
                    focused = if (active) focused + field.id else focused - field.id
                    if (!active && lastToken == null) drafts = drafts - field.id
                }, onChange = { edit(field, it) })
        }

    }
}

@Composable
private fun PropertyControl(field: ObjectPropertyField, value: Any?, draft: Boolean, unit: LengthUnit,
                            enabled: Boolean, stepMeters: Double, onFocus: (Boolean) -> Unit,
                            onChange: (Any?) -> Unit) {
    val suffix = when (field.unit) { "length" -> unit.short; "percent" -> "%"; "factor" -> "×"; "angle" -> "°"; else -> "" }
    when (field.type) {
        "number" -> Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            val text = if (draft) value as? String ?: "" else (value as? Number)?.let {
                val shown = objectPropertyDisplay(it, field, unit)
                formatToolDistance(shown, detailDecimalPlaces(shown, 4))
            }.orEmpty()
            Text(field.label, color = Ink.Muted, fontSize = 12.sp)
            val step = when (field.unit) {
                "length" -> stepMeters / unit.transformStepUnit().meters
                "percent", "angle" -> 1.0
                else -> .1
            }
            fun nudge(direction: Int) {
                val current = com.blendertablet.remote.model.NumericExpression.evaluate(text) ?: return
                val raw = current.toBigDecimal().add(step.toBigDecimal().multiply(direction.toBigDecimal())).toDouble()
                val min = field.min?.let { objectPropertyDisplay(it, field, unit) } ?: -Double.MAX_VALUE
                val max = field.max?.let { objectPropertyDisplay(it, field, unit) } ?: Double.MAX_VALUE
                onChange(formatToolDistance(raw.coerceIn(min, max), null))
            }
            StepperButton("−", enabled) { nudge(-1) }
            if (enabled) CompactNumericField(text, { onChange(it) }, modifier = Modifier.width(104.dp),
                textColor = if (draft && objectPropertyNumber(text, field, unit) == null) Ink.Bad else Ink.OnPanel,
                selectAllOnFocus = true, onFocusChange = onFocus, onDone = {})
            else Text(text, color = Ink.Faint, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
                modifier = Modifier.width(104.dp).padding(6.dp))
            StepperButton("+", enabled) { nudge(1) }
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
