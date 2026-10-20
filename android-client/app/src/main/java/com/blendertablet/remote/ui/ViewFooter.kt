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
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
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
 * ORTHO). El encuadre y `/` salen de aquí (doble toque y menú contextual,
 * respectivamente); `+`/`−` crecen/disminuyen la selección en Edit Mode.
 */
@Composable
fun ViewFooter(
    projection: Projection,
    activeAxisView: String?,
    planeLocked: Boolean,
    planeLockAvailable: Boolean,
    onPlaneLock: () -> Unit,
    inEdit: Boolean,
    selectionMode: SelectionMode,
    showEditShortcuts: Boolean,
    /** Cuchillo vive en la barra de tools activas cuando `edit_toolbar` existe (F1). */
    connectVerticesEnabled: Boolean = false,
    onAxis: (String) -> Unit,
    onOrbit: (Float, Float) -> Unit,
    onRotate180: () -> Unit,
    onProjection: (Projection) -> Unit,
    onFrameSelected: () -> Unit,
    onEditAction: (EditFooterAction) -> Unit,
    connectModeActive: Boolean = false,
    onConnectMode: () -> Unit = {},
    contextKeys: (@Composable () -> Unit)? = null,
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
                Column(verticalArrangement = Arrangement.spacedBy(KeyGap)) {
                    if (inEdit && showEditShortcuts) {
                        Row(horizontalArrangement = Arrangement.spacedBy(KeyGap)) {
                            PageKey(AppIcons.Views, "Página de vistas", selected = !editPage) {
                                editPage = false
                            }
                            PageKey(AppIcons.EditShortcuts, "Atajos de Edit", selected = editPage) {
                                editPage = true
                            }
                        }
                    }
                    if (contextKeys != null) {
                        contextKeys()
                    } else if (editPage && inEdit && showEditShortcuts) {
                        EditKeys(selectionMode, connectVerticesEnabled, connectModeActive, onConnectMode, normalsPage, { normalsPage = it }, onEditAction)
                    } else {
                    Row(horizontalArrangement = Arrangement.spacedBy(KeyGap)) {
                        NumKey("7", "Superior / inferior", activeAxisView in setOf("TOP", "BOTTOM")) { opposite("TOP", "BOTTOM") }
                        NumKey("8", "Orbitar arriba", enabled = !planeLocked) { onOrbit(0f, -0.06f) }
                        NumKey("9", "Girar 180°", enabled = !planeLocked) { onRotate180() }
                        // El candado es una tecla más de la botonera, junto a las vistas que fija.
                        if (planeLockAvailable) PageKey(AppIcons.selectionLock(planeLocked),
                            if (planeLocked) "Desbloquear plano de vista" else "Bloquear plano · elige primero una vista",
                            selected = planeLocked, enabled = planeLocked || activeAxisView != null, onClick = onPlaneLock)
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(KeyGap)) {
                        NumKey("4", "Orbitar izquierda", enabled = !planeLocked) { onOrbit(-0.06f, 0f) }
                        NumKey(
                            "5",
                            if (projection == Projection.PERSP) "Perspectiva" else "Ortográfica",
                            selected = projection == Projection.ORTHO,
                            enabled = !planeLocked,
                        ) {
                            onProjection(if (projection == Projection.PERSP) Projection.ORTHO else Projection.PERSP)
                        }
                        NumKey("6", "Orbitar derecha", enabled = !planeLocked) { onOrbit(0.06f, 0f) }
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(KeyGap)) {
                        NumKey("1", "Frontal / trasera", activeAxisView in setOf("FRONT", "BACK")) { opposite("FRONT", "BACK") }
                        NumKey("2", "Orbitar abajo", enabled = !planeLocked) { onOrbit(0f, 0.06f) }
                        NumKey("3", "Derecha / izquierda", activeAxisView in setOf("RIGHT", "LEFT")) { opposite("RIGHT", "LEFT") }
                        PageKey(AppIcons.Frame, "Encuadrar objeto", selected = false, onClick = onFrameSelected)
                    }
                    Spacer(Modifier.height(2.dp))
                    }
                }
            }

            HoverHelp(
                title = if (expanded) "Plegar vistas" else "Desplegar vistas",
                explanation = "Abre o recoge los controles de orientación, proyección y atajos.",
                modifier = Modifier
                    .clip(RoundedCornerShape(8.dp))
                    .clickableNoRipple { expanded = !expanded }
                    .padding(horizontal = 8.dp, vertical = 4.dp),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    AppIcons.drawer(expanded),
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
    connectVerticesEnabled: Boolean,
    connectModeActive: Boolean,
    onConnectMode: () -> Unit,
    normalsPage: Boolean,
    setNormalsPage: (Boolean) -> Unit,
    onAction: (EditFooterAction) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(KeyGap)) {
        if (normalsPage) {
            Row(horizontalArrangement = Arrangement.spacedBy(KeyGap)) {
                PageKey(AppIcons.Back, "Volver a atajos", selected = false) { setNormalsPage(false) }
                EditKey(AppIcons.editCatalog("RECALCULATE_NORMALS_OUTSIDE"), "⇧N", "Recalcular exterior") {
                    onAction(EditFooterAction.NORMALS_OUTSIDE)
                }
                EditKey(AppIcons.editCatalog("RECALCULATE_NORMALS_INSIDE"), null, "Recalcular interior") {
                    onAction(EditFooterAction.NORMALS_INSIDE)
                }
                EditKey(AppIcons.editCatalog("FLIP_NORMALS"), null, "Voltear normales") {
                    onAction(EditFooterAction.NORMALS_FLIP)
                }
            }
            return
        }
        Row(horizontalArrangement = Arrangement.spacedBy(KeyGap)) {
            EditKey(AppIcons.editCatalog("MAKE_EDGE_FACE"), "F",
                if (selectionMode == SelectionMode.EDGE) "Rellenar" else "Crear arista/cara",
                enabled = selectionMode != SelectionMode.FACE) { onAction(EditFooterAction.MAKE_EDGE_FACE) }
            EditKey(AppIcons.editCatalog("SEPARATE"), "P", "Separar a objeto") { onAction(EditFooterAction.SEPARATE) }
            EditKey(AppIcons.editCatalog("SPLIT"), "Y", "Split") { onAction(EditFooterAction.SPLIT) }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(KeyGap)) {
            // J une la selección; «Unir J» es una herramienta armable aparte: tocar la
            // arma, tocar otra vez (o ×) la desarma. Ninguna depende de mantener pulsado.
            EditKey(AppIcons.editCatalog("CONNECT_VERTICES"), "J", "Conectar vértices",
                enabled = connectVerticesEnabled && selectionMode == SelectionMode.VERTEX) {
                onAction(EditFooterAction.CONNECT_VERTICES)
            }
            EditKey(AppIcons.ConnectPairs, "J", if (connectModeActive) "Unir J activo · toca para salir" else "Unir J · pares seguidos",
                selected = connectModeActive, onClick = onConnectMode)
            EditKey(AppIcons.editCatalog("NORMALS"), "N", "Normales", enabled = selectionMode == SelectionMode.FACE) { setNormalsPage(true) }
        }
    }
}

/** Separación entre teclas del pie (norma: 48 dp con 8 dp de separación). */
private val KeyGap = 8.dp

/**
 * Tecla de atajo del pie: el icono de la acción a 48 dp y la letra de Blender como
 * marca pequeña en la esquina, nunca como contenido principal.
 */
@Composable
private fun EditKey(
    icon: ImageVector,
    letter: String?,
    description: String,
    selected: Boolean = false,
    enabled: Boolean = true,
    onClick: () -> Unit,
) {
    val content = if (!enabled) Ink.Faint else if (selected) Ink.Accent else Ink.OnPanel
    HoverHelp(
        title = description, explanation = IconHelp.explanation(icon, description), enabled = enabled,
        modifier = Modifier
            .size(Metrics.Touch)
            .clip(RoundedCornerShape(9.dp))
            .background(if (!enabled) Color.Transparent else if (selected) Ink.Accent.copy(alpha = .24f) else Color.White.copy(alpha = .05f))
            .then(if (enabled) Modifier.clickableNoRipple(onClick) else Modifier),
        contentAlignment = Alignment.Center,
    ) {
        Icon(icon, description, Modifier.size(Metrics.IconSize), tint = content)
        if (letter != null) Text(letter, color = if (enabled) Ink.Muted else Ink.Faint, fontSize = 9.sp,
            fontWeight = FontWeight.Bold, modifier = Modifier.align(Alignment.TopEnd).padding(top = 2.dp, end = 4.dp))
    }
}

@Composable
private fun PageKey(
    icon: ImageVector,
    description: String,
    selected: Boolean,
    enabled: Boolean = true,
    onClick: () -> Unit,
) {
    val background = when {
        !enabled -> Color.Transparent
        selected -> Ink.Accent.copy(alpha = .24f)
        else -> Color.White.copy(alpha = .05f)
    }
    val content = if (!enabled) Ink.Faint else if (selected) Ink.Accent else Ink.Muted
    HoverHelp(
        title = description, explanation = IconHelp.explanation(icon, description), enabled = enabled,
        modifier = Modifier
            .size(Metrics.Touch)
            .clip(RoundedCornerShape(9.dp))
            .background(background)
            .then(if (enabled) Modifier.clickableNoRipple(onClick) else Modifier),
        contentAlignment = Alignment.Center,
    ) {
        Icon(icon, description, Modifier.size(Metrics.IconSize), tint = content)
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
    HoverHelp(
        title = description, enabled = enabled,
        modifier = Modifier
            .size(Metrics.Touch)
            .clip(RoundedCornerShape(9.dp))
            .background(background)
            .then(if (!enabled) Modifier else Modifier.clickableNoRipple(onClick)),
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = content, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
    }
}
