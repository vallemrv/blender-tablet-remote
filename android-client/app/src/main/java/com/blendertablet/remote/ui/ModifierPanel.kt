package com.blendertablet.remote.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.material3.OutlinedTextField
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.text.style.TextAlign
import com.blendertablet.remote.model.BlenderMode
import com.blendertablet.remote.model.BlenderState
import com.blendertablet.remote.model.LengthUnit
import com.blendertablet.remote.model.ModifierDefault
import com.blendertablet.remote.model.ModifierParameterDescriptor
import com.blendertablet.remote.model.NumericExpression
import com.blendertablet.remote.model.ModifierState
import com.blendertablet.remote.model.ObjectChoiceFilter
import java.math.BigDecimal
import java.math.MathContext
import java.math.RoundingMode
import kotlin.math.roundToInt

data class ModifierActions(
    val add: (String, Map<String, Any?>) -> Unit,
    val set: (String, String, Any?) -> Unit,
    val toggle: (String, Boolean?, Boolean?, Boolean?) -> Unit,
    val move: (String, Int) -> Unit,
    val apply: (String) -> Unit,
    val remove: (String) -> Unit,
    val group: (String, Map<String, Any?>) -> Unit,
    val close: () -> Unit,
)

/**
 * Inspector de modificadores, generado exclusivamente desde `modifier.add_options`.
 *
 * Se construye con las primitivas de la app (`FloatingPanel`, `IconAction`,
 * `ScrubRow`) y no con `Card`/`IconButton`/`TextButton` de Material: un panel con
 * otra familia de controles se lee como una segunda aplicación pegada encima.
 *
 * La lista tiene altura máxima y scroll propio. Sin eso, cuatro modificadores con sus
 * parámetros desbordaban la pantalla y las acciones de los últimos quedaban fuera.
 */
@Composable
fun ModifierPanel(state: BlenderState, actions: ModifierActions, modifier: Modifier = Modifier) {
    FloatingPanel(modifier.widthIn(max = 300.dp).heightIn(max = 560.dp)) {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Header(state, actions)
            Column(Modifier.heightIn(max = 420.dp).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(6.dp)) {
                if (state.vertexGroupsAvailable) VertexGroupControls(state, actions.group)
                if (state.modifiers.isEmpty()) Empty()
                else state.modifiers.forEachIndexed { index, item -> ModifierCard(item, index, state, actions) }
            }
        }
    }
}

/**
 * Cabecera: flecha de cierre a la izquierda, título, y añadir a la derecha.
 *
 * La flecha va primero porque es la salida, y en un panel anclado al borde la salida
 * se busca hacia dentro de la pantalla.
 */
@Composable
private fun Header(state: BlenderState, actions: ModifierActions) {
    var addOpen by remember { mutableStateOf(false) }
    var query by remember { mutableStateOf("") }

    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        IconAction(
            AppIcons.Back,
            "Cerrar modificadores",
            onClick = actions.close,
        )
        Text(
            "MODIFICADORES",
            color = Ink.Accent,
            fontSize = 11.sp,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.weight(1f).padding(start = 2.dp),
        )
        Box {
            IconAction(
                AppIcons.Add,
                "Añadir modificador",
                selected = addOpen,
                enabled = state.modifierOptions.isNotEmpty(),
                onClick = { query = ""; addOpen = true },
            )
            DropdownMenu(
                expanded = addOpen,
                onDismissRequest = { addOpen = false },
                containerColor = Ink.PanelSolid,
                modifier = Modifier.widthIn(min = 190.dp),
            ) {
                OutlinedTextField(query, { query = it }, singleLine = true, label = { Text("Buscar modificador") },
                    modifier = Modifier.width(260.dp).padding(horizontal = 8.dp))
                val matches = state.modifierOptions.filter { modifierMatchesQuery(it.type, it.label, query) &&
                    (state.mode != BlenderMode.EDIT || it.type != "MULTIRES") }
                if (matches.isEmpty()) Text("Sin coincidencias", color = Ink.Muted, modifier = Modifier.padding(12.dp))
                for (descriptor in matches) {
                    DropdownMenuItem(
                        text = { Text(descriptor.label, color = Ink.OnPanel, fontSize = 13.sp) },
                        leadingIcon = {
                            Icon(AppIcons.modifier(descriptor.type), null, Modifier.size(18.dp), tint = Ink.Muted)
                        },
                        onClick = {
                            addOpen = false
                            actions.add(
                                descriptor.type,
                                descriptor.parameters.filter { !it.readOnly && it.type != "action" }
                                    .associate { it.name to it.default.wireValue() },
                            )
                        },
                    )
                }
            }
        }
    }
}

@Composable
private fun Empty() {
    Text(
        "Sin modificadores. Añade uno con +.",
        color = Ink.Faint,
        fontSize = 11.sp,
        modifier = Modifier.padding(horizontal = 4.dp, vertical = 8.dp),
    )
}

/** Una tarjeta por modificador: identidad, visibilidad, parámetros y orden. */
@Composable
private fun ModifierCard(
    item: ModifierState,
    index: Int,
    state: BlenderState,
    actions: ModifierActions,
) {
    val specs = state.modifierOptions.firstOrNull { it.type == item.type }?.parameters.orEmpty()
    var expanded by remember(item.name) { mutableStateOf(true) }

    Box(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(11.dp))
            .background(Ink.Elevated)
            .padding(8.dp),
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                ModifierHeaderButton(
                    AppIcons.disclosure(expanded),
                    if (expanded) "Plegar ${item.name}" else "Desplegar ${item.name}",
                ) { expanded = !expanded }
                Icon(AppIcons.modifier(item.type), item.type, Modifier.size(16.dp), tint = Ink.Accent)
                Spacer(Modifier.width(4.dp))
                Text(
                    item.name,
                    color = Ink.OnPanel,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.weight(1f),
                )
                ModifierHeaderButton(
                    AppIcons.MoveUp, "Subir en la pila",
                    enabled = index > 0,
                ) { actions.move(item.name, index - 1) }
                ModifierHeaderButton(
                    AppIcons.MoveDown, "Bajar en la pila",
                    enabled = index < state.modifiers.lastIndex,
                ) { actions.move(item.name, index + 1) }
                ModifierHeaderButton(
                    AppIcons.visibility(true),
                    if (item.showViewport) "Visible en el viewport" else "Oculto en el viewport",
                    selected = item.showViewport,
                ) { actions.toggle(item.name, !item.showViewport, null, null) }
                if (state.mode == BlenderMode.EDIT) ModifierHeaderButton(
                    AppIcons.ModeEdit, "Mostrar modificador en edición", selected = item.showInEditMode,
                ) { actions.toggle(item.name, null, null, !item.showInEditMode) }
                ModifierHeaderButton(
                    AppIcons.Render,
                    if (item.showRender) "Visible en el render" else "Oculto en el render",
                    selected = item.showRender,
                ) { actions.toggle(item.name, null, !item.showRender, null) }
            }

            if (expanded) {
                for (spec in specs) {
                    ModifierParameter(item, spec, state, actions.set)
                }

                Row(horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                    Spacer(Modifier.weight(1f))
                    IconAction(AppIcons.ApplyModifier, "Aplicar (solo Object)", enabled = state.mode == BlenderMode.OBJECT, tint = Ink.Ok) { actions.apply(item.name) }
                    IconAction(AppIcons.Delete, "Eliminar", tint = Ink.Bad) { actions.remove(item.name) }
                }
            }
        }
    }
}

/** Botón compacto de cabecera: la pila completa debe caber en una sola línea. */
@Composable
private fun ModifierHeaderButton(
    icon: ImageVector,
    description: String,
    enabled: Boolean = true,
    selected: Boolean = false,
    onClick: () -> Unit,
) {
    HoverHelp(
        title = description, explanation = IconHelp.explanation(icon, description), enabled = enabled,
        modifier = Modifier
            .size(28.dp)
            .clip(RoundedCornerShape(7.dp))
            .background(if (selected) Ink.Accent.copy(alpha = .18f) else Color.Transparent)
            .then(if (enabled) Modifier.clickableNoRipple(onClick) else Modifier),
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            icon,
            description,
            Modifier.size(17.dp),
            tint = when {
                !enabled -> Ink.Faint.copy(alpha = .35f)
                selected -> Ink.Accent
                else -> Ink.Faint
            },
        )
    }
}

@Composable
private fun ModifierParameter(
    item: ModifierState,
    declaredSpec: ModifierParameterDescriptor,
    state: BlenderState,
    set: (String, String, Any?) -> Unit,
) {
    if (!modifierParameterVisible(item, declaredSpec)) return
    val actualMaximum = declaredSpec.maxParameter?.let { (item.parameters[it] as? Number)?.toDouble() }
    val spec = if (declaredSpec.type != "action" && actualMaximum != null)
        declaredSpec.copy(max = actualMaximum) else declaredSpec
    val value = item.parameters[spec.name]
    if (spec.readOnly) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(spec.label, color = Ink.Faint, fontSize = 11.sp)
            Text(value?.toString() ?: "—", color = Ink.OnPanel, fontSize = 12.sp)
        }
        return
    }
    when (spec.type) {
        "action" -> PillButton(spec.label, enabled = state.mode != BlenderMode.EDIT && (spec.max == null || actualMaximum == null || actualMaximum < spec.max)) {
            set(item.name, spec.name, true)
        }
        "bool" -> Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(spec.label, color = Ink.Faint, fontSize = 11.sp, modifier = Modifier.weight(1f))
            IconAction(
                AppIcons.Checked,
                if (value == true) "${spec.label}: activado" else "${spec.label}: desactivado",
                selected = value == true,
                tint = Ink.Faint,
            ) { set(item.name, spec.name, value != true) }
        }

        "enum" -> ChoiceRow(
            label = spec.label,
            current = spec.valueLabels[value?.toString()] ?: value?.toString() ?: "—",
            options = spec.values.map { it to (spec.valueLabels[it] ?: it) },
        ) { set(item.name, spec.name, it) }

        // El operando de un booleano no puede ser el propio objeto ni una luz: el
        // filtro lo declara el backend y aquí solo se obedece.
        "vertex_group" -> ChoiceRow(
            label = spec.label,
            current = value?.toString()?.takeIf { it.isNotEmpty() } ?: "Todo el objeto",
            options = listOf("" to "Todo el objeto") + state.vertexGroups.map { it.name to it.name },
        ) { set(item.name, spec.name, it.orEmpty()) }
        "object" -> ChoiceRow(
            label = spec.label,
            current = value?.toString() ?: "ninguno",
            options = buildList {
                add(null to "Sin operando")
                val filter = spec.objectFilter ?: ObjectChoiceFilter()
                state.objects
                    .filter { (_, type) -> filter.type == null || type == filter.type }
                    .filter { (name, _) -> !filter.excludeSelf || name != state.activeObject }
                    .forEach { (name, _) -> add(name to name) }
            },
        ) { set(item.name, spec.name, it) }

        "float3" -> {
            val vector = vectorOf(value)
            for (axis in 0..2) {
                ScrubRow(
                    label = "${spec.name} ${"XYZ"[axis]}",
                    value = vector[axis],
                    text = formatModifierValue(vector[axis], isInt = false, spec.step),
                    step = step(spec),
                ) { set(item.name, spec.name, vector.stepped(axis, it - vector[axis], spec)) }
            }
        }

        else -> {
            val isInt = spec.type == "int"
            val current = (value as? Number)?.toDouble() ?: 0.0
            if (spec.editable) {
                EditableModifierScalar(item, spec, state, current) { set(item.name, spec.name, it) }
                return
            }
            ScrubRow(
                label = spec.label,
                value = current,
                text = formatModifierValue(current, isInt, spec.step),
                step = step(spec),
            ) { set(item.name, spec.name, stepModifierScalar(it, isInt, 0.0, spec)) }
        }
    }
}

/** Exact typed values use the descriptor's wire units; drafts survive scene snapshots. */
@Composable
private fun EditableModifierScalar(
    item: ModifierState,
    spec: ModifierParameterDescriptor,
    state: BlenderState,
    current: Double,
    set: (Number) -> Unit,
) {
    val factor = modifierScalarFactor(spec, state)
    val suffix = when (spec.unit) { "LENGTH" -> state.sceneScale.lengthUnit.short; "ANGLE" -> "°"; else -> "" }
    var draft by remember(state.activeObject, item.name, spec.name, factor) { mutableStateOf<String?>(null) }
    val focus = LocalFocusManager.current
    val typed = draft?.let { parseModifierScalar(it, spec, factor, current) }
    fun commit() {
        val number = typed ?: return
        set(number)
        focus.clearFocus()
        draft = null
    }
    var base by remember { mutableStateOf(current) }
    val valid = draft == null || typed != null
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(spec.label, color = Ink.Faint, fontSize = 11.sp,
            modifier = Modifier.weight(1f).padding(end = 4.dp))
        HoverHelp(spec.label, numberHelp(false)) {
            // Deslizar parte del valor al empezar (o del borrador válido) y avanza por el paso.
            ScrubNumber(enabled = valid, onScrubStart = { base = typed?.toDouble() ?: current },
                onScrub = { steps -> draft = null; set(stepModifierScalar(base, spec.type == "int", steps * step(spec), spec)) }) { field ->
                CompactNumericField(
                    value = draft ?: formatEditableModifierValue(current * factor),
                    onValueChange = { draft = it },
                    modifier = field.width(96.dp), fontSize = 16.sp, textAlign = TextAlign.End,
                    textColor = if (valid) Ink.OnPanel else Ink.Bad, suffix = suffix.ifEmpty { null },
                    onDone = ::commit,
                )
            }
        }
        if (draft != null) ModifierHeaderButton(AppIcons.Confirm, "Confirmar ${spec.label}", enabled = typed != null) { commit() }
    }
}

internal fun modifierScalarFactor(spec: ModifierParameterDescriptor, state: BlenderState): Double =
    if (spec.unit == "LENGTH") state.unitScaleLength * when (state.sceneScale.lengthUnit) {
        LengthUnit.MILLIMETERS -> 1000.0
        LengthUnit.CENTIMETERS -> 100.0
        LengthUnit.METERS -> 1.0
    } else 1.0

internal fun parseModifierScalar(text: String, spec: ModifierParameterDescriptor, factor: Double, current: Double = 0.0): Number? {
    if (!factor.isFinite() || factor <= 0.0) return null
    val value = NumericExpression.evaluate(text, current * factor)?.div(factor) ?: return null
    if (!value.isFinite() || value < (spec.min ?: -Double.MAX_VALUE) || value > (spec.max ?: Double.MAX_VALUE)) return null
    return if (spec.type == "int") {
        if (value % 1.0 != 0.0 || value < Int.MIN_VALUE || value > Int.MAX_VALUE) null else value.toInt()
    } else value
}

internal fun formatEditableModifierValue(value: Double): String =
    formatToolDistance(value, MaxDecimals)

/** Fila con una opción elegible: etiqueta a la izquierda, valor pulsable a la derecha. */
@Composable
private fun ChoiceRow(
    label: String,
    current: String,
    options: List<Pair<String?, String>>,
    onSelect: (String?) -> Unit,
) {
    var open by remember { mutableStateOf(false) }
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(label, color = Ink.Faint, fontSize = 11.sp, modifier = Modifier.weight(1f))
        Box {
            PillButton(current, selected = open) { open = true }
            DropdownMenu(
                expanded = open,
                onDismissRequest = { open = false },
                containerColor = Ink.PanelSolid,
                modifier = Modifier.widthIn(min = 170.dp),
            ) {
                for ((wire, text) in options) {
                    DropdownMenuItem(
                        text = { Text(text, color = Ink.OnPanel, fontSize = 13.sp) },
                        onClick = {
                            open = false
                            onSelect(wire)
                        },
                    )
                }
            }
        }
    }
}



private fun step(spec: ModifierParameterDescriptor): Double =
    spec.step ?: if (spec.type == "int") 1.0 else 0.1

private fun clamp(value: Double, spec: ModifierParameterDescriptor): Double =
    value.coerceIn(spec.min ?: -Double.MAX_VALUE, spec.max ?: Double.MAX_VALUE)

internal fun stepModifierScalar(
    current: Double,
    isInt: Boolean,
    delta: Double,
    spec: ModifierParameterDescriptor,
): Number {
    val next = clamp(current + delta, spec)
    return if (isInt) next.roundToInt() else next
}

private fun vectorOf(value: Any?): List<Double> = when (value) {
    is org.json.JSONArray -> List(3) { value.optDouble(it) }
    is List<*> -> List(3) { (value.getOrNull(it) as? Number)?.toDouble() ?: 0.0 }
    else -> listOf(0.0, 0.0, 0.0)
}

private fun List<Double>.stepped(axis: Int, delta: Double, spec: ModifierParameterDescriptor): List<Double> =
    toMutableList().also { it[axis] = clamp(it[axis] + delta, spec) }

internal fun formatModifierValue(value: Double, isInt: Boolean, step: Double?): String {
    if (isInt) return value.roundToInt().toString()
    val decimals = BigDecimal.valueOf(step ?: 0.1).stripTrailingZeros().scale().coerceIn(0, MaxDecimals)
    return BigDecimal.valueOf(value)
        .setScale(decimals, RoundingMode.HALF_UP)
        .stripTrailingZeros()
        .toPlainString()
}

private fun ModifierDefault.wireValue(): Any? = when (this) {
    is ModifierDefault.Integer -> value
    is ModifierDefault.Decimal -> value
    is ModifierDefault.BooleanValue -> value
    is ModifierDefault.Text -> value
    is ModifierDefault.Vector -> value
    ModifierDefault.Null -> null
}

internal fun modifierParameterVisible(item: ModifierState, spec: ModifierParameterDescriptor): Boolean =
    spec.visibleWhen.all { (key, values) -> item.parameters[key]?.toString() in values }

internal fun modifierMatchesQuery(type: String, label: String, query: String): Boolean {
    fun normalize(value: String) = java.text.Normalizer.normalize(value, java.text.Normalizer.Form.NFD)
        .replace(Regex("\\p{M}+"), "").lowercase(java.util.Locale.ROOT).replace('_', ' ')
    val terms = normalize(query).trim().split(Regex("\\s+")).filter { it.isNotEmpty() }
    val searchable = normalize(type + " " + label)
    return terms.all { it in searchable }
}
