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
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ArrowDownward
import androidx.compose.material.icons.filled.ArrowUpward
import androidx.compose.material.icons.filled.AutoAwesomeMotion
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Deblur
import androidx.compose.material.icons.filled.JoinFull
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.Layers
import androidx.compose.material.icons.filled.Flip
import androidx.compose.material.icons.filled.PhotoCamera
import androidx.compose.material.icons.filled.RoundedCorner
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.blendertablet.remote.model.BlenderState
import com.blendertablet.remote.model.ModifierDefault
import com.blendertablet.remote.model.ModifierParameterDescriptor
import com.blendertablet.remote.model.ModifierState
import com.blendertablet.remote.model.ObjectChoiceFilter
import java.math.BigDecimal
import java.math.RoundingMode
import kotlin.math.roundToInt

data class ModifierActions(
    val add: (String, Map<String, Any?>) -> Unit,
    val set: (String, String, Any?) -> Unit,
    val toggle: (String, Boolean?, Boolean?) -> Unit,
    val move: (String, Int) -> Unit,
    val apply: (String) -> Unit,
    val remove: (String) -> Unit,
    val close: () -> Unit,
)

/**
 * Inspector de modificadores, generado exclusivamente desde `modifier.add_options`.
 *
 * Se construye con las primitivas de la app (`FloatingPanel`, `IconAction`,
 * `StepperRow`) y no con `Card`/`IconButton`/`TextButton` de Material: un panel con
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
            if (state.modifiers.isEmpty()) {
                Empty()
            } else {
                Column(
                    Modifier
                        .heightIn(max = 420.dp)
                        .verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    state.modifiers.forEachIndexed { index, item ->
                        ModifierCard(item, index, state, actions)
                    }
                }
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

    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        IconAction(
            Icons.AutoMirrored.Filled.ArrowBack,
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
                Icons.Default.Add,
                "Añadir modificador",
                selected = addOpen,
                enabled = state.modifierOptions.isNotEmpty(),
                onClick = { addOpen = true },
            )
            DropdownMenu(
                expanded = addOpen,
                onDismissRequest = { addOpen = false },
                containerColor = Ink.PanelSolid,
                modifier = Modifier.widthIn(min = 190.dp),
            ) {
                for (descriptor in state.modifierOptions) {
                    DropdownMenuItem(
                        text = { Text(labelOf(descriptor.type), color = Ink.OnPanel, fontSize = 13.sp) },
                        leadingIcon = {
                            Icon(iconOf(descriptor.type), null, Modifier.size(18.dp), tint = Ink.Muted)
                        },
                        onClick = {
                            addOpen = false
                            actions.add(
                                descriptor.type,
                                descriptor.parameters.associate { it.name to it.default.wireValue() },
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
                    if (expanded) Icons.Default.KeyboardArrowDown else Icons.AutoMirrored.Filled.KeyboardArrowRight,
                    if (expanded) "Plegar ${item.name}" else "Desplegar ${item.name}",
                ) { expanded = !expanded }
                Icon(iconOf(item.type), item.type, Modifier.size(16.dp), tint = Ink.Accent)
                Spacer(Modifier.width(4.dp))
                Text(
                    item.name,
                    color = Ink.OnPanel,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.weight(1f),
                )
                ModifierHeaderButton(
                    Icons.Default.ArrowUpward, "Subir en la pila",
                    enabled = index > 0,
                ) { actions.move(item.name, index - 1) }
                ModifierHeaderButton(
                    Icons.Default.ArrowDownward, "Bajar en la pila",
                    enabled = index < state.modifiers.lastIndex,
                ) { actions.move(item.name, index + 1) }
                ModifierHeaderButton(
                    Icons.Default.Visibility,
                    if (item.showViewport) "Visible en el viewport" else "Oculto en el viewport",
                    selected = item.showViewport,
                ) { actions.toggle(item.name, !item.showViewport, null) }
                ModifierHeaderButton(
                    Icons.Default.PhotoCamera,
                    if (item.showRender) "Visible en el render" else "Oculto en el render",
                    selected = item.showRender,
                ) { actions.toggle(item.name, null, !item.showRender) }
            }

            if (expanded) {
                for (spec in specs) {
                    ModifierParameter(item, spec, state, actions.set)
                }

                Row(horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                    Spacer(Modifier.weight(1f))
                    IconAction(Icons.Default.Check, "Aplicar", tint = Ink.Ok) { actions.apply(item.name) }
                    IconAction(Icons.Default.Delete, "Eliminar", tint = Ink.Bad) { actions.remove(item.name) }
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
    Box(
        Modifier
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
    spec: ModifierParameterDescriptor,
    state: BlenderState,
    set: (String, String, Any?) -> Unit,
) {
    val value = item.parameters[spec.name]
    when (spec.type) {
        "bool" -> Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(spec.name, color = Ink.Faint, fontSize = 11.sp, modifier = Modifier.weight(1f))
            IconAction(
                Icons.Default.Check,
                if (value == true) "${spec.name}: activado" else "${spec.name}: desactivado",
                selected = value == true,
                tint = Ink.Faint,
            ) { set(item.name, spec.name, value != true) }
        }

        "enum" -> ChoiceRow(
            label = spec.name,
            current = value?.toString() ?: "—",
            options = spec.values.map { it to it },
        ) { set(item.name, spec.name, it) }

        // El operando de un booleano no puede ser el propio objeto ni una luz: el
        // filtro lo declara el backend y aquí solo se obedece.
        "object" -> ChoiceRow(
            label = spec.name,
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
                StepperRow(
                    label = "${spec.name} ${"XYZ"[axis]}",
                    value = formatModifierValue(vector[axis], isInt = false, spec.step),
                    onMinus = { set(item.name, spec.name, vector.stepped(axis, -step(spec), spec)) },
                    onPlus = { set(item.name, spec.name, vector.stepped(axis, step(spec), spec)) },
                )
            }
        }

        else -> {
            val isInt = spec.type == "int"
            val current = (value as? Number)?.toDouble() ?: 0.0
            fun apply(delta: Double) {
                set(item.name, spec.name, stepModifierScalar(current, isInt, delta, spec))
            }
            StepperRow(
                label = spec.name,
                value = formatModifierValue(current, isInt, spec.step),
                minusEnabled = spec.min == null || current > spec.min,
                plusEnabled = spec.max == null || current < spec.max,
                onMinus = { apply(-step(spec)) },
                onPlus = { apply(step(spec)) },
            )
        }
    }
}

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

/**
 * Un icono por familia de modificador.
 *
 * El tipo llega del backend como texto, así que un tipo nuevo cae en el icono genérico
 * en vez de dejar el hueco vacío: la app puede ser más vieja que el servidor.
 */
private fun iconOf(type: String): ImageVector = when (type) {
    "SUBSURF" -> Icons.Default.Deblur
    "ARRAY" -> Icons.Default.AutoAwesomeMotion
    "BEVEL" -> Icons.Default.RoundedCorner
    "SOLIDIFY" -> Icons.Default.Layers
    "BOOLEAN" -> Icons.Default.JoinFull
    "MIRROR" -> Icons.Default.Flip
    else -> Icons.Default.Tune
}

private fun labelOf(type: String): String = when (type) {
    "SUBSURF" -> "Subdivisión"
    "ARRAY" -> "Matriz"
    "BEVEL" -> "Bisel"
    "SOLIDIFY" -> "Solidificar"
    "BOOLEAN" -> "Booleano"
    "MIRROR" -> "Espejo"
    else -> type
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
    val decimals = BigDecimal.valueOf(step ?: 0.1).stripTrailingZeros().scale().coerceIn(0, 8)
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
