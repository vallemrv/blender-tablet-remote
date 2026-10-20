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
    val sectionFields = fields.filterNot { it.id in setOf("visible", "render", "in_front") }
    val groups = sectionFields.map { it.group }.distinct()
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
    val help = if (properties == null) "Elige un objeto o imagen en ⋯ Más."
        else "Los cambios se aplican directamente. Deshacer recupera el valor anterior."
    val section = sectionFields.filter { it.group == selectedGroup }
    val (rowFields, optionFields) = section.partition { it.type == "number" }
    val inFrontField = fields.firstOrNull { it.id == "in_front" }
    val more = TrayMore(
        reference = {
            TrayOption(properties?.name ?: "Ningún objeto", "Elige otro objeto o una imagen de referencia de la escena.") {
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
            }
        },
        shape = if (inFrontField == null && optionFields.isEmpty()) null else ({
            inFrontField?.let { field ->
                val inFront = (drafts[field.id] ?: properties?.values?.get(field.id)) == true
                TrayOption("Mostrar delante", "Dibuja el objeto por delante del resto aunque quede detrás.") {
                    IconAction(AppIcons.InFront, "Mostrar delante", selected = inFront,
                        enabled = !field.readOnly) { edit(field, !inFront) }
                }
            }
            optionFields.forEach { field ->
                TrayOption(field.label, "") {
                    PropertyControl(field, drafts[field.id] ?: properties?.values?.get(field.id),
                        field.id in drafts, unit, !field.readOnly, stepMeters, onFocus = {}, onChange = { edit(field, it) })
                }
            }
        }),
    )
    SingleLineTray(
        title = selectedGroup ?: "Objeto",
        modifier = modifier, help = help, hintKey = "object.properties", more = more,
    ) {
        if (groups.size > 1) Box {
            var sectionMenu by remember { mutableStateOf(false) }
            IconAction(AppIcons.Dropdown, "Sección · ${selectedGroup.orEmpty()}") { sectionMenu = true }
            DropdownMenu(sectionMenu, { sectionMenu = false }) {
                groups.forEach { name -> DropdownMenuItem(
                    text = { Text(name) },
                    trailingIcon = { if (name == selectedGroup) Icon(AppIcons.Checked, null, tint = Ink.Accent) },
                    onClick = { properties?.let { onSelectSection(it.id, name) }; sectionMenu = false }) }
            }
        }
        rowFields.forEach { field ->
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
        "number" -> {
            val text = if (draft) value as? String ?: "" else (value as? Number)?.let {
                val shown = objectPropertyDisplay(it, field, unit)
                formatToolDistance(shown, if (field.unit == "count") 0 else 2)
            }.orEmpty()
            val step = when (field.unit) {
                "length" -> stepMeters / unit.transformStepUnit().meters
                "percent", "angle", "count" -> 1.0
                else -> .1
            }
            val min = field.min?.let { objectPropertyDisplay(it, field, unit) } ?: -Double.MAX_VALUE
            val max = field.max?.let { objectPropertyDisplay(it, field, unit) } ?: Double.MAX_VALUE
            var base by remember(field.id) { mutableStateOf<Double?>(null) }
            val neutral = objectPropertyNeutral(field)?.let { objectPropertyDisplay(it, field, unit) }
            val axis = field.label.takeIf { it.length == 1 }?.let { axisColor(it) }
            HoverHelp(field.label, numberHelp(neutral != null), enabled = enabled) {
                ScrubNumber(enabled = enabled,
                    onScrubStart = { base = com.blendertablet.remote.model.NumericExpression.evaluate(text) },
                    onScrub = { steps -> base?.let { start ->
                        val raw = start.toBigDecimal().add(step.toBigDecimal().multiply(steps.toBigDecimal())).toDouble()
                        onChange(formatToolDistance(raw.coerceIn(min, max), null))
                    } },
                    onReset = neutral?.let { { onChange(formatToolDistance(it, null)) } }) { box ->
                    CompactNumericField(text, { if (enabled) onChange(it) }, modifier = box.width(if (field.label.length > 1) 136.dp else 112.dp),
                        textColor = if (!enabled) Ink.Faint else if (draft && objectPropertyNumber(text, field, unit) == null) Ink.Bad else Ink.OnPanel,
                        fontSize = 16.sp, textAlign = androidx.compose.ui.text.style.TextAlign.End,
                        caption = field.label, captionColor = axis ?: Ink.Faint, suffix = suffix,
                        selectAllOnFocus = true, onFocusChange = onFocus, onDone = {})
                }
            }
        }
        "bool" -> PillButton(if (value == true) "Activado" else "Desactivado",
            selected = value == true, enabled = enabled) { onChange(value != true) }
        "enum" -> {
            var open by remember(field.id) { mutableStateOf(false) }
            Box {
                PillButton("${field.choices[value] ?: value} ▾", enabled = enabled) { open = true }
                DropdownMenu(open, { open = false }) {
                    field.choices.forEach { (key, label) -> DropdownMenuItem(text = { Text(label) },
                        onClick = { open = false; onChange(key) }) }
                }
            }
        }
    }
}

/** Valor al mantener pulsado: posición y giro a cero, escala a 1 y opacidad completa. */
internal fun objectPropertyNeutral(field: ObjectPropertyField): Double? = when {
    field.id.startsWith("location_") || field.id.startsWith("rotation_") -> 0.0
    field.id.startsWith("scale_") -> 1.0
    field.id == "opacity" -> 1.0
    else -> null
}

/** Ejes con el color de Blender también en los campos de propiedades. */
internal fun axisColor(letter: String): androidx.compose.ui.graphics.Color? = when (letter) {
    "X" -> Ink.AxisX; "Y" -> Ink.AxisY; "Z" -> Ink.AxisZ; else -> null
}
