package com.blendertablet.remote.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Icon
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.text.TextRange
import androidx.compose.runtime.setValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.layout.Layout
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Campo exacto de 48 dp: Material TextField impone 56 dp y se recorta en las trays. */
@Composable
fun CompactNumericField(
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    textAlign: TextAlign = TextAlign.Center,
    placeholder: String? = null,
    textColor: Color = Ink.OnPanel,
    fontSize: androidx.compose.ui.unit.TextUnit = 13.sp,
    onFocusChange: (Boolean) -> Unit = {},
    /** Tocar el campo selecciona todo su contenido: lo que se escribe sustituye al valor. */
    selectAllOnFocus: Boolean = false,
    /** Nombre corto dentro del propio campo (eje o magnitud), nunca una pastilla aparte. */
    caption: String? = null,
    captionColor: Color = Ink.Faint,
    /** Unidad tras el número, en pequeño; no forma parte del texto editable. */
    suffix: String? = null,
    onDone: () -> Unit,
) {
    // Confirmar suelta el foco: el número vuelve a poder deslizarse sin otro toque.
    val focusManager = androidx.compose.ui.platform.LocalFocusManager.current
    val decoration: @Composable (@Composable () -> Unit) -> Unit = { inner ->
        NumericFieldBox(value, placeholder, textAlign, caption, captionColor, suffix, inner)
    }
    if (!selectAllOnFocus) {
        BasicTextField(
            value = value,
            onValueChange = onValueChange,
            singleLine = true,
            textStyle = TextStyle(color = textColor, fontSize = fontSize, textAlign = textAlign),
            cursorBrush = SolidColor(Ink.Accent),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Text, imeAction = ImeAction.Done),
            keyboardActions = KeyboardActions(onDone = { onDone(); focusManager.clearFocus() }),
            modifier = modifier
                .onFocusChanged { onFocusChange(it.isFocused) }
                .height(Metrics.Touch)
                .clip(RoundedCornerShape(7.dp))
                .background(Color.White.copy(alpha = .07f)),
            decorationBox = decoration,
        )
        return
    }
    // Con texto alineado a la derecha, un toque deja el cursor delante del número y
    // lo tecleado se antepone («45» sobre «0» da «450»). Se selecciona todo al enfocar,
    // después de que el propio toque coloque el cursor.
    var field by remember { mutableStateOf(TextFieldValue(value, TextRange(value.length))) }
    if (field.text != value) field = TextFieldValue(value, TextRange(value.length))
    var focused by remember { mutableStateOf(false) }
    LaunchedEffect(focused) {
        if (focused) field = field.copy(selection = TextRange(0, field.text.length))
    }
    BasicTextField(
        value = field,
        onValueChange = { next -> field = next; if (next.text != value) onValueChange(next.text) },
        singleLine = true,
        textStyle = TextStyle(color = textColor, fontSize = fontSize, textAlign = textAlign),
        cursorBrush = SolidColor(Ink.Accent),
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Text, imeAction = ImeAction.Done),
        keyboardActions = KeyboardActions(onDone = { onDone(); focusManager.clearFocus() }),
        modifier = modifier
            .onFocusChanged { focused = it.isFocused; onFocusChange(it.isFocused) }
            .height(Metrics.Touch)
            .clip(RoundedCornerShape(7.dp))
            .background(Color.White.copy(alpha = .07f)),
        decorationBox = decoration,
    )
}

@Composable
private fun NumericFieldBox(value: String, placeholder: String?, textAlign: TextAlign, caption: String?,
                            captionColor: Color, suffix: String?, inner: @Composable () -> Unit) {
    Row(Modifier.fillMaxSize().padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        if (!caption.isNullOrBlank()) Text(caption, color = captionColor, fontSize = 11.sp, maxLines = 1,
            fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(end = 6.dp))
        Box(Modifier.weight(1f),
            contentAlignment = if (textAlign == TextAlign.End) Alignment.CenterEnd else Alignment.Center) {
            if (value.isEmpty() && placeholder != null) {
                Text(placeholder, color = Ink.Faint, fontSize = 11.sp, maxLines = 1)
            }
            inner()
        }
        if (!suffix.isNullOrBlank()) Text(suffix, color = Ink.Muted, fontSize = 11.sp, maxLines = 1,
            modifier = Modifier.padding(start = 3.dp))
    }
}

/**
 * Piezas de interfaz reutilizables: botones de icono compactos, píldoras y paneles
 * flotantes. Nada de botones grandes con texto; el espacio es del viewport (§10).
 */

/** Botón de icono. Área táctil de 48 dp aunque el icono mida 20. */
@Composable
fun IconAction(
    icon: ImageVector,
    description: String,
    modifier: Modifier = Modifier,
    selected: Boolean = false,
    enabled: Boolean = true,
    tint: Color? = null,
    onClick: () -> Unit,
) {
    val background = if (selected) Ink.Accent.copy(alpha = .22f) else Color.Transparent
    val content = when {
        !enabled -> Ink.Faint
        selected -> Ink.Accent
        else -> tint ?: Ink.OnPanel
    }
    HoverHelp(
        title = description, explanation = IconHelp.explanation(icon, description), enabled = enabled,
        modifier = modifier
            .size(Metrics.Touch)
            .clip(RoundedCornerShape(10.dp))
            .background(background)
            .then(if (enabled) Modifier.clickableNoRipple(onClick) else Modifier),
        contentAlignment = Alignment.Center,
    ) {
        // Color.Unspecified keeps a multicolour icon's own colours; disabled only dims it.
        if (tint == Color.Unspecified) Icon(icon, description, Modifier.size(Metrics.IconSize).alpha(if (enabled) 1f else .35f), tint = Color.Unspecified)
        else Icon(icon, description, Modifier.size(Metrics.IconSize), tint = content)
    }
}

/** Botón compacto con texto, para modos y acciones nombradas. */
@Composable
fun PillButton(
    label: String,
    modifier: Modifier = Modifier,
    selected: Boolean = false,
    enabled: Boolean = true,
    repeatOnHold: Boolean = false,
    onClick: () -> Unit,
) {
    val background = if (selected) Ink.Accent.copy(alpha = .22f) else Color.White.copy(alpha = .05f)
    val content = when {
        !enabled -> Ink.Faint
        selected -> Ink.Accent
        else -> Ink.Muted
    }
    Box(
        modifier
            .height(Metrics.Touch)
            .clip(RoundedCornerShape(9.dp))
            .background(background)
            .then(if (selected) Modifier.border(1.dp, Ink.Accent.copy(alpha = .5f), RoundedCornerShape(9.dp)) else Modifier)
            .then(if (repeatOnHold) Modifier.repeatingClick(enabled, onClick)
                else if (enabled) Modifier.clickableNoRipple(onClick) else Modifier)
            .padding(horizontal = 12.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = content, fontSize = 13.sp, fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal)
    }
}

/** Contenedor flotante translúcido: la base de todos los paneles de la app. */
@Composable
fun FloatingPanel(
    modifier: Modifier = Modifier,
    content: @Composable () -> Unit,
) {
    Surface(
        modifier = modifier,
        color = Ink.Panel,
        shape = RoundedCornerShape(Metrics.Radius),
        border = null,
        tonalElevation = 0.dp,
    ) {
        Box(Modifier.padding(Metrics.PanelPadding)) { content() }
    }
}

/** Barra vertical permanente de herramientas, con scroll si no cabe completa. */
@Composable
fun ToolRail(
    modifier: Modifier = Modifier,
    content: @Composable () -> Unit,
) {
    FloatingPanel(modifier = modifier.widthIn(max = 72.dp).heightIn(max = 560.dp)) {
        Column(
            Modifier.verticalScroll(rememberScrollState()),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(2.dp),
        ) { content() }
    }
}

/**
 * Botón cuadrado de un solo carácter (− y +), la mitad de ancho que un icono.
 *
 * Vive aquí y no en cada panel porque los steppers de la bandeja de Edit y los del
 * inspector de modificadores tienen que sentirse el mismo control: era justo lo que
 * se había perdido al escribir el inspector con `TextButton` de Material.
 */
@Composable
fun StepperButton(label: String, enabled: Boolean = true, onClick: () -> Unit) {
    Box(
        Modifier
            .size(Metrics.Touch)
            .clip(RoundedCornerShape(9.dp))
            .background(Color.White.copy(alpha = .05f))
            .repeatingClick(enabled, onClick),
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = if (enabled) Ink.Muted else Ink.Faint, fontSize = 16.sp)
    }
}

/**
 * Un estado con varias opciones se muestra como el icono de la opción activa; al
 * tocarlo se abre su selector. Sustituye a las pastillas «etiqueta: valor».
 */
@Composable
fun <T> ChoiceIcon(
    options: List<T>,
    selected: T,
    description: String,
    icon: (T) -> ImageVector,
    label: (T) -> String,
    active: Boolean = false,
    enabled: Boolean = true,
    multicolor: Boolean = false,
    onSelect: (T) -> Unit,
) {
    if (options.isEmpty()) return
    var open by remember(options) { mutableStateOf(false) }
    Box {
        IconAction(icon(selected), "$description · ${label(selected)}", selected = active, enabled = enabled,
            tint = if (multicolor) Color.Unspecified else null) { open = true }
        androidx.compose.material3.DropdownMenu(open, onDismissRequest = { open = false }) {
            options.forEach { option ->
                androidx.compose.material3.DropdownMenuItem(
                    text = { Text(label(option)) },
                    leadingIcon = { Icon(icon(option), null,
                        tint = if (multicolor) Color.Unspecified else if (option == selected) Ink.Accent else Ink.Muted) },
                    trailingIcon = { if (option == selected) Icon(AppIcons.Checked, null, tint = Ink.Accent) },
                    onClick = { open = false; if (option != selected) onSelect(option) },
                )
            }
        }
    }
}

/**
 * Fila `etiqueta [−] valor [+]`: un número que se ajusta a pasos con el dedo.
 *
 * El valor se enseña centrado entre los dos botones para que el pulgar no lo tape al
 * repetir toques, y la etiqueta va en gris pequeño para que la cifra sea lo que se lee.
 */
@Composable
fun StepperRow(
    label: String,
    value: String,
    modifier: Modifier = Modifier,
    minusEnabled: Boolean = true,
    plusEnabled: Boolean = true,
    onMinus: () -> Unit,
    onPlus: () -> Unit,
) {
    Row(modifier, verticalAlignment = Alignment.CenterVertically) {
        Text(
            label,
            color = Ink.Faint,
            fontSize = 11.sp,
            modifier = Modifier.weight(1f).padding(end = 6.dp),
        )
        StepperButton("−", minusEnabled, onMinus)
        Text(
            value,
            color = Ink.OnPanel,
            fontSize = 13.sp,
            textAlign = TextAlign.Center,
            modifier = Modifier.width(56.dp),
        )
        StepperButton("+", plusEnabled, onPlus)
    }
}

/** Separador fino para agrupar iconos dentro de la barra. */
@Composable
fun RailDivider() {
    Box(
        Modifier
            .padding(vertical = 4.dp)
            .width(24.dp)
            .height(1.dp)
            .background(Ink.Divider),
    )
}

@Composable
fun RailLabel(text: String) {
    Text(
        text,
        color = Ink.Faint,
        fontSize = 7.sp,
        fontWeight = FontWeight.SemiBold,
        maxLines = 1,
        modifier = Modifier.padding(top = 4.dp, bottom = 2.dp),
    )
}

/** Fila horizontal compacta, para la barra superior. */
@Composable
fun TopStrip(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    FloatingPanel(modifier) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            content()
        }
    }
}

@Composable
fun StatusDot(color: Color, label: String, modifier: Modifier = Modifier) {
    Row(modifier.padding(horizontal = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(7.dp).clip(RoundedCornerShape(4.dp)).background(color))
        Spacer(Modifier.width(6.dp))
        Text(label, color = Ink.Muted, fontSize = 12.sp)
    }
}

/**
 * Botón redondo con fondo teñido, para confirmar (verde) y descartar (rojo): las dos
 * salidas de una sesión, que no deben confundirse entre sí ni con el resto.
 */
@Composable
fun RoundAction(
    icon: ImageVector,
    description: String,
    color: Color,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    HoverHelp(
        title = description, explanation = IconHelp.explanation(icon, description),
        modifier = modifier
            .size(Metrics.Touch)
            .clip(RoundedCornerShape(12.dp))
            .background(color.copy(alpha = .25f))
            .border(1.dp, color.copy(alpha = .6f), RoundedCornerShape(12.dp))
            .clickableNoRipple(onClick),
        contentAlignment = Alignment.Center,
    ) {
        Icon(icon, description, Modifier.size(22.dp), tint = color)
    }
}

/** Rótulo de una bandeja inferior: la herramienta en curso, igual en todas. */
@Composable
fun TrayTitle(text: String, modifier: Modifier = Modifier) {
    Text(
        text.uppercase(),
        color = Ink.Accent,
        fontSize = 11.sp,
        fontWeight = FontWeight.SemiBold,
        maxLines = 1,
        overflow = TextOverflow.Ellipsis,
        modifier = modifier.widthIn(max = 160.dp),
    )
}

/**
 * Opciones de nivel 3 de una bandeja, siempre en los mismos tres grupos y orden:
 * Precisión (snap, paso, unidad), Referencia (centro, orientación, fuente…) y Forma
 * (proporcional, perfil y opciones propias). Un grupo nulo no se muestra.
 */
class TrayMore(
    val precision: (@Composable ColumnScope.() -> Unit)? = null,
    val reference: (@Composable ColumnScope.() -> Unit)? = null,
    val shape: (@Composable ColumnScope.() -> Unit)? = null,
) {
    internal val groups get() = listOf("Precisión" to precision, "Referencia" to reference, "Forma" to shape)
        .mapNotNull { (name, content) -> content?.let { name to it } }
    val isEmpty get() = groups.isEmpty()
}

/**
 * Bandeja inferior común: `[Nombre] [valor/ejes] [icono][icono] [⋯] … [×][✓]`.
 *
 * Una sola fila fija, sin scroll horizontal: el nombre, «⋯ Más» y las salidas se
 * miden primero y nunca se desplazan; el contenido directo ocupa el resto. Lo poco
 * frecuente vive en [more]. Debajo, como mucho, un aviso de estado y la ayuda.
 */
@Composable
fun SingleLineTray(
    title: String,
    onCancel: (() -> Unit)? = null,
    onConfirm: (() -> Unit)? = null,
    confirmEnabled: Boolean = true,
    modifier: Modifier = Modifier,
    help: String = "",
    alert: String? = null,
    /** Información viva (medidas, candidato de snap, qué señalar): siempre visible. */
    status: String? = null,
    more: TrayMore? = null,
    /** La ayuda bajo la fila solo acompaña las primeras veces; después queda en el hover. */
    hintKey: String = title,
    content: @Composable RowScope.() -> Unit,
) {
    val context = androidx.compose.ui.platform.LocalContext.current
    val firstTimes = remember(hintKey) { com.blendertablet.remote.data.TrayHints(context).consume(hintKey) }
    FloatingPanel(modifier) {
        Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
            TrayRow(
                title = { HoverHelp(title, help) { TrayTitle(title) } },
                content = {
                    Row(Modifier.clipToBounds(), verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp), content = content)
                },
                more = { if (more != null && !more.isEmpty) TrayMoreButton(more, help) },
                exits = { if (onCancel != null) Row(verticalAlignment = Alignment.CenterVertically) {
                    TrayExits(onCancel, onConfirm, confirmEnabled) } },
            )
            if (!alert.isNullOrBlank()) Text(alert, color = Ink.Warn, fontSize = 11.sp, maxLines = 2,
                overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(horizontal = 4.dp))
            if (!status.isNullOrBlank()) Text(status, color = Ink.Ok, fontSize = 11.sp, maxLines = 1,
                overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(horizontal = 4.dp))
            if (firstTimes && help.isNotBlank()) Text(help, color = Ink.Muted, fontSize = 11.sp,
                maxLines = 2, overflow = TextOverflow.Ellipsis,
                modifier = Modifier.padding(start = 4.dp, end = 4.dp, bottom = 3.dp))
        }
    }
}

/** Mide nombre, Más y salidas antes que el contenido; las salidas quedan a la derecha. */
@Composable
private fun TrayRow(
    title: @Composable () -> Unit,
    content: @Composable () -> Unit,
    more: @Composable () -> Unit,
    exits: @Composable () -> Unit,
) {
    val gap = with(LocalDensity.current) { 8.dp.roundToPx() }
    Layout(contents = listOf(title, content, more, exits)) { (titles, contents, mores, exit), constraints ->
        val loose = constraints.copy(minWidth = 0, minHeight = 0)
        val t = titles.map { it.measure(loose) }
        val e = exit.map { it.measure(loose) }
        val m = mores.map { it.measure(loose) }
        fun width(list: List<androidx.compose.ui.layout.Placeable>) = list.sumOf { it.width }
        val fixed = width(t) + width(e) + width(m) + gap * 3
        val total = if (constraints.hasBoundedWidth) constraints.maxWidth else fixed + 2000
        val c = contents.map { it.measure(loose.copy(maxWidth = (total - fixed).coerceAtLeast(0))) }
        val height = (t + e + m + c).maxOfOrNull { it.height } ?: 0
        layout(total, height) {
            var x = 0
            t.forEach { it.placeRelative(x, (height - it.height) / 2); x += it.width }
            x += gap
            c.forEach { it.placeRelative(x, (height - it.height) / 2); x += it.width }
            if (width(c) > 0) x += gap
            m.forEach { it.placeRelative(x, (height - it.height) / 2); x += it.width }
            var right = total - width(e)
            e.forEach { it.placeRelative(right, (height - it.height) / 2); right += it.width }
        }
    }
}

/** «⋯ Más»: panel vertical sobre la bandeja, por grupos, con una frase por opción. */
@Composable
private fun TrayMoreButton(more: TrayMore, help: String) {
    var open by remember { mutableStateOf(false) }
    Box {
        IconAction(AppIcons.More, "Más opciones", selected = open) { open = true }
        androidx.compose.material3.DropdownMenu(open, onDismissRequest = { open = false }) {
            Column(Modifier.widthIn(min = 300.dp, max = 400.dp).padding(horizontal = 14.dp, vertical = 6.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)) {
                if (help.isNotBlank()) Text(help, color = Ink.Muted, fontSize = 11.sp)
                more.groups.forEach { (name, group) ->
                    Text(name.uppercase(), color = Ink.Accent, fontSize = 11.sp, fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.padding(top = 4.dp))
                    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) { group() }
                }
            }
        }
    }
}

/** Una opción de «⋯ Más»: nombre, su control a la derecha y una frase debajo. */
@Composable
fun TrayOption(label: String, help: String, content: @Composable RowScope.() -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(label, color = Ink.OnPanel, fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f))
            content()
        }
        if (help.isNotBlank()) Text(help, color = Ink.Muted, fontSize = 11.sp)
    }
}

/**
 * Las salidas de una bandeja, fijas a la derecha: Cancelar (rojo) y, si hay algo
 * que aplicar, Confirmar (verde; apagado mientras no sea posible).
 */
@Composable
fun TrayExits(
    onCancel: () -> Unit,
    onConfirm: (() -> Unit)? = null,
    confirmEnabled: Boolean = true,
) {
    Spacer(Modifier.width(10.dp))
    RoundAction(AppIcons.Cancel, "Cancelar", Ink.Bad, onCancel)
    if (onConfirm != null) {
        Spacer(Modifier.width(4.dp))
        RoundAction(AppIcons.Confirm, "Confirmar", if (confirmEnabled) Ink.Ok else Ink.Faint,
            onClick = { if (confirmEnabled) onConfirm() })
    }
}
