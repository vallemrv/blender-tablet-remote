package com.blendertablet.remote.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.scaleOut
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.Row
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
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Icon
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Campo exacto de 34 dp: Material TextField impone 56 dp y se recorta en las trays. */
@Composable
fun CompactNumericField(
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    textAlign: TextAlign = TextAlign.Center,
    placeholder: String? = null,
    textColor: Color = Ink.OnPanel,
    onFocusChange: (Boolean) -> Unit = {},
    onDone: () -> Unit,
) {
    BasicTextField(
        value = value,
        onValueChange = onValueChange,
        singleLine = true,
        textStyle = TextStyle(color = textColor, fontSize = 13.sp, textAlign = textAlign),
        cursorBrush = SolidColor(Ink.Accent),
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number, imeAction = ImeAction.Done),
        keyboardActions = KeyboardActions(onDone = { onDone() }),
        modifier = modifier
            .onFocusChanged { onFocusChange(it.isFocused) }
            .height(34.dp)
            .clip(RoundedCornerShape(7.dp))
            .background(Color.White.copy(alpha = .07f)),
        decorationBox = { inner ->
            Box(
                Modifier.fillMaxSize().padding(horizontal = 6.dp),
                contentAlignment = if (textAlign == TextAlign.End) Alignment.CenterEnd else Alignment.Center,
            ) {
                if (value.isEmpty() && placeholder != null) {
                    Text(placeholder, color = Ink.Faint, fontSize = 11.sp, maxLines = 1)
                }
                inner()
            }
        },
    )
}

/**
 * Piezas de interfaz reutilizables: botones de icono compactos, píldoras y paneles
 * flotantes. Nada de botones grandes con texto; el espacio es del viewport (§10).
 */

/** Botón de icono. Área táctil de 44 dp aunque el icono mida 20. */
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
    Box(
        modifier
            .size(Metrics.Touch)
            .clip(RoundedCornerShape(10.dp))
            .background(background)
            .then(if (enabled) Modifier.clickableNoRipple(onClick) else Modifier),
        contentAlignment = Alignment.Center,
    ) {
        Icon(icon, description, Modifier.size(Metrics.IconSize), tint = content)
    }
}

/** Botón compacto con texto, para modos y acciones nombradas. */
@Composable
fun PillButton(
    label: String,
    modifier: Modifier = Modifier,
    selected: Boolean = false,
    enabled: Boolean = true,
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
            .height(34.dp)
            .clip(RoundedCornerShape(9.dp))
            .background(background)
            .then(if (selected) Modifier.border(1.dp, Ink.Accent.copy(alpha = .5f), RoundedCornerShape(9.dp)) else Modifier)
            .then(if (enabled) Modifier.clickableNoRipple(onClick) else Modifier)
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

/**
 * Barra vertical desplegable de herramientas: la lista scrollable que se abre desde
 * un solo icono, para que en reposo la pantalla sea todo viewport.
 */
@Composable
fun ToolRail(
    visible: Boolean,
    modifier: Modifier = Modifier,
    content: @Composable () -> Unit,
) {
    AnimatedVisibility(
        visible = visible,
        // Transiciones cortas: 120-200 ms, nada decorativo (§54).
        enter = fadeIn(tween(140)) + scaleIn(tween(140), initialScale = .92f),
        exit = fadeOut(tween(120)) + scaleOut(tween(120), targetScale = .92f),
        modifier = modifier,
    ) {
        FloatingPanel(modifier = Modifier.widthIn(max = 72.dp).heightIn(max = 560.dp)) {
            Column(
                Modifier.verticalScroll(rememberScrollState()),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(2.dp),
            ) { content() }
        }
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
            .width(28.dp)
            .height(34.dp)
            .clip(RoundedCornerShape(9.dp))
            .background(Color.White.copy(alpha = .05f))
            .then(if (enabled) Modifier.clickableNoRipple(onClick) else Modifier),
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = if (enabled) Ink.Muted else Ink.Faint, fontSize = 15.sp)
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
    Box(
        modifier
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
