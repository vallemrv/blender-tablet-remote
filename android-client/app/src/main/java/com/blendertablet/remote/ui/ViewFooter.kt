package com.blendertablet.remote.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.blendertablet.remote.model.Projection
import com.blendertablet.remote.model.EditFooterAction
import com.blendertablet.remote.model.SelectionMode

/**
 * Teclado de vistas inspirado en el numpad de Blender, en una cuadrícula 4×3.
 *
 * Las vistas (7/1/3) alternan entre la cara y su opuesta; 9 ya no duplica a 7, sino
 * que gira la vista 180°. 5 enseña el estado real de la proyección (resaltado solo en
 * ORTHO). El encuadre sale de aquí (lo hace el doble toque): en su sitio `/` aísla la
 * selección, y `+`/`−` crecen/disminuyen la selección en Edit Mode.
 */
@Composable
fun ViewFooter(
    projection: Projection,
    activeAxisView: String?,
    inEdit: Boolean,
    selectionMode: SelectionMode,
    showEditShortcuts: Boolean,
    localViewActive: Boolean,
    showLocal: Boolean,
    showGrow: Boolean,
    onAxis: (String) -> Unit,
    onOrbit: (Float, Float) -> Unit,
    onRotate180: () -> Unit,
    onProjection: (Projection) -> Unit,
    onLocal: () -> Unit,
    onMore: () -> Unit,
    onLess: () -> Unit,
    onEditAction: (EditFooterAction) -> Unit,
    modifier: Modifier = Modifier,
) {
    var expanded by remember { mutableStateOf(false) }
    var editPage by remember { mutableStateOf(false) }
    var normalsPage by remember { mutableStateOf(false) }

    fun opposite(primary: String, reverse: String) {
        onAxis(if (activeAxisView == primary) reverse else primary)
    }

    FloatingPanel(modifier) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            AnimatedVisibility(
                visible = expanded,
                enter = fadeIn(tween(120)) + expandVertically(tween(140)),
                exit = fadeOut(tween(100)) + shrinkVertically(tween(120)),
            ) {
                Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    if (inEdit && showEditShortcuts) {
                        Row(horizontalArrangement = Arrangement.spacedBy(3.dp)) {
                            NumKey("V", "Página de vistas", selected = !editPage) { editPage = false }
                            NumKey("E", "Atajos de Edit", selected = editPage) { editPage = true }
                        }
                    }
                    if (editPage && inEdit && showEditShortcuts) {
                        EditKeys(selectionMode, normalsPage, { normalsPage = it }, onEditAction)
                    } else {
                    Row(horizontalArrangement = Arrangement.spacedBy(3.dp)) {
                        NumKey("7", "Superior / inferior", activeAxisView in setOf("TOP", "BOTTOM")) { opposite("TOP", "BOTTOM") }
                        NumKey("8", "Orbitar arriba") { onOrbit(0f, -0.06f) }
                        NumKey("9", "Girar 180°") { onRotate180() }
                        NumKey("+", "Crecer selección", enabled = inEdit && showGrow, onClick = onMore)
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(3.dp)) {
                        NumKey("4", "Orbitar izquierda") { onOrbit(-0.06f, 0f) }
                        NumKey(
                            "5",
                            if (projection == Projection.PERSP) "Perspectiva" else "Ortográfica",
                            selected = projection == Projection.ORTHO,
                        ) {
                            onProjection(if (projection == Projection.PERSP) Projection.ORTHO else Projection.PERSP)
                        }
                        NumKey("6", "Orbitar derecha") { onOrbit(0.06f, 0f) }
                        NumKey("−", "Decrecer selección", enabled = inEdit && showGrow, onClick = onLess)
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(3.dp)) {
                        NumKey("1", "Frontal / trasera", activeAxisView in setOf("FRONT", "BACK")) { opposite("FRONT", "BACK") }
                        NumKey("2", "Orbitar abajo") { onOrbit(0f, 0.06f) }
                        NumKey("3", "Derecha / izquierda", activeAxisView in setOf("RIGHT", "LEFT")) { opposite("RIGHT", "LEFT") }
                        NumKey("/", "Aislar selección", selected = localViewActive, enabled = showLocal, onClick = onLocal)
                    }
                    Spacer(Modifier.height(2.dp))
                    }
                }
            }

            Box(
                Modifier
                    .clip(RoundedCornerShape(8.dp))
                    .clickableNoRipple { expanded = !expanded }
                    .padding(horizontal = 8.dp, vertical = 4.dp),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    if (expanded) Icons.Default.ExpandMore else Icons.Default.ExpandLess,
                    if (expanded) "Plegar vistas" else "Desplegar vistas",
                    Modifier.size(16.dp), tint = Ink.Faint,
                )
            }
        }
    }
}

@Composable
private fun EditKeys(
    selectionMode: SelectionMode,
    normalsPage: Boolean,
    setNormalsPage: (Boolean) -> Unit,
    onAction: (EditFooterAction) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
        if (normalsPage) {
            Row(horizontalArrangement = Arrangement.spacedBy(3.dp)) {
                NumKey("←", "Volver a atajos") { setNormalsPage(false) }
                NumKey("Ext", "Recalcular exterior") { onAction(EditFooterAction.NORMALS_OUTSIDE) }
                NumKey("Int", "Recalcular interior") { onAction(EditFooterAction.NORMALS_INSIDE) }
                NumKey("Vol", "Voltear normales") { onAction(EditFooterAction.NORMALS_FLIP) }
            }
            return
        }
        Row(horizontalArrangement = Arrangement.spacedBy(3.dp)) {
            NumKey("F", if (selectionMode == SelectionMode.EDGE) "Rellenar" else "Crear arista/cara",
                enabled = selectionMode != SelectionMode.FACE) { onAction(EditFooterAction.MAKE_EDGE_FACE) }
            NumKey("K", "Cuchillo") { onAction(EditFooterAction.KNIFE) }
            NumKey("P", "Separar a objeto") { onAction(EditFooterAction.SEPARATE) }
            NumKey("Y", "Split") { onAction(EditFooterAction.SPLIT) }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(3.dp)) {
            NumKey("N", "Normales", enabled = selectionMode == SelectionMode.FACE) { setNormalsPage(true) }
        }
    }
}

@Composable
private fun NumKey(
    label: String,
    description: String,
    selected: Boolean = false,
    enabled: Boolean = true,
    onClick: () -> Unit,
) {
    val background = when {
        !enabled -> Color.Transparent
        selected -> Ink.Accent.copy(alpha = .24f)
        else -> Color.White.copy(alpha = .05f)
    }
    val content = when {
        !enabled -> Ink.Faint
        selected -> Ink.Accent
        else -> Ink.Muted
    }
    Box(
        Modifier
            .size(38.dp)
            .clip(RoundedCornerShape(9.dp))
            .background(background)
            .then(if (enabled) Modifier.clickableNoRipple(onClick) else Modifier),
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = content, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
    }
}
