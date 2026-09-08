package com.blendertablet.remote.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material.icons.filled.ChevronRight
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.blendertablet.remote.model.AppUiState
import com.blendertablet.remote.model.BlenderMode
import com.blendertablet.remote.model.ConnectionStatus
import com.blendertablet.remote.model.SnapAction
import com.blendertablet.remote.model.SnapGroup

/**
 * Barra superior de menús desplegables.
 *
 * En una tablet la barra compite directamente con el viewport (§9): tres títulos
 * cortos ocupan una franja mínima y todo lo demás vive dentro, en submenús.
 */
@Composable
fun MenuBar(
    state: AppUiState,
    fps: Float,
    lagMs: Long,
    streaming: Boolean,
    host: String,
    actions: MenuActions,
    modifier: Modifier = Modifier,
) {
    TopStrip(modifier) {
        MenuAnchor("Archivo", onOpen = actions.onFileMenuOpened) { close ->
            fileMenu(state, actions, close)
        }
        if (!state.blender.cad.workspace) MenuAnchor("Objeto") { close -> objectMenu(state, actions, close) }
        if (state.blender.features.sceneScale) {
            MenuAnchor("Escena") { close -> sceneMenu(state, actions, close) }
        }
        MenuPlaceholder("Layouts")
        if (!state.blender.cad.workspace && state.blender.hiddenObjects.isNotEmpty() && state.blender.features.visibility) {
            MenuAnchor("Ocultos") { close -> hiddenMenu(state, actions, close) }
        }
        // Modificadores no es un menú: es un panel que se enseña o se esconde, así que
        // un icono conmutable dice más que un desplegable con una sola entrada.
        ConnectionMenu(state, fps, lagMs, streaming, host, actions)

        // El nombre del archivo, fuera de los menús: es lo que orienta de un vistazo.
        Text(
            state.file.name + if (state.file.dirty) " •" else "",
            color = if (state.file.dirty) Ink.Warn else Ink.Faint,
            fontSize = 11.sp,
            modifier = Modifier.padding(start = 4.dp, end = 6.dp),
        )
    }
}

/** Entrada visual reservada para un menú todavía sin comportamiento. */
@Composable
private fun MenuPlaceholder(title: String) {
    Row(
        Modifier.heightIn(min = 34.dp).padding(start = 10.dp, end = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(title, color = Ink.Muted, fontSize = 13.sp)
        Icon(Icons.Default.ArrowDropDown, null, Modifier.size(18.dp), tint = Ink.Faint)
    }
}

/** Lo que la barra puede pedirle a la app. Agrupado para no pasar diez lambdas. */
data class MenuActions(
    val onFileMenuOpened: () -> Unit,
    val onNew: () -> Unit,
    val onBrowseOpen: () -> Unit,
    val onSave: () -> Unit,
    val onSaveAs: () -> Unit,
    val onSnap: (SnapAction) -> Unit,
    val onConnectionSettings: () -> Unit,
    val onReconnect: () -> Unit,
    val onDisconnect: () -> Unit,
    val onRevealObject: (String) -> Unit,
    val onRevealAllObjects: () -> Unit,
    val onApplyTransform: (Boolean, Boolean, Boolean) -> Unit,
    val onModifiers: () -> Unit,
    val onSceneScale: (String) -> Unit,
)

// ------------------------------------------------------------- árbol de menú

/**
 * Un nivel de menú. Se describe como datos y no como composables anidados porque
 * `DropdownMenu` no admite submenús: el árbol se recorre sustituyendo el contenido
 * del mismo desplegable, y para eso hace falta poder navegarlo.
 */
sealed interface MenuNode

data class MenuLeaf(
    val label: String,
    val enabled: Boolean = true,
    val selected: Boolean = false,
    val hint: String? = null,
    val onClick: () -> Unit,
) : MenuNode

data class MenuGroup(val label: String, val children: List<MenuNode>) : MenuNode

data class MenuHeading(val label: String) : MenuNode

data class MenuNote(val label: String) : MenuNode

object MenuSeparator : MenuNode

// ------------------------------------------------------------------- Archivo

private fun fileMenu(state: AppUiState, actions: MenuActions, close: () -> Unit): List<MenuNode> = listOf(
    MenuLeaf("Nuevo") { close(); actions.onNew() },
    MenuLeaf("Abrir…", enabled = state.blender.features.fileBrowse) { close(); actions.onBrowseOpen() },
    MenuSeparator,
    // Una sola entrada "Guardar": sin ruta previa abre el diálogo de nombre por su
    // cuenta. Antes había dos entradas que hacían lo mismo en ese caso.
    MenuLeaf("Guardar", enabled = state.file.saved || state.blender.features.fileBrowse, hint = state.file.path.takeIf { state.file.saved }) {
        close()
        if (state.file.saved) actions.onSave() else actions.onSaveAs()
    },
    MenuLeaf("Guardar como…", enabled = state.blender.features.fileBrowse) { close(); actions.onSaveAs() },
)

// -------------------------------------------------------------------- Objeto

private fun objectMenu(state: AppUiState, actions: MenuActions, close: () -> Unit): List<MenuNode> {
    val inEdit = state.blender.mode == BlenderMode.EDIT

    // Sin "Añadir" a propósito: el catálogo Add vive en el menú contextual del
    // long-click (Object Mode, vacío), donde de verdad se usa. Aquí solo queda
    // lo que opera sobre lo existente.
    return SnapGroup.entries.filter { it != SnapGroup.ORIGIN }.map { group ->
        MenuGroup(
            group.label,
            SnapAction.of(group).map { snap ->
                MenuLeaf(snap.label, enabled = !(snap.objectOnly && inEdit)) {
                    close()
                    actions.onSnap(snap)
                }
            },
        )
    }
}

// -------------------------------------------------------------------- Escena

/**
 * Escala de trabajo: una sola elección ajusta unidad, profundidad, pasos y tamaño de
 * primitivas. La unidad no se ofrece por separado para impedir estados contradictorios.
 */
internal fun sceneMenu(state: AppUiState, actions: MenuActions, close: () -> Unit): List<MenuNode> {
    val scale = state.blender.sceneScale
    val presets = state.sceneScalePresets.ifEmpty { listOf(scale) }
    return buildList {
        add(MenuHeading("Escala de la escena"))
        presets.forEach { preset ->
            add(
                MenuLeaf(preset.label, selected = preset.id == scale.id, hint = preset.hint) {
                    close()
                    actions.onSceneScale(preset.id)
                },
            )
        }
        add(MenuNote("No reescala lo ya modelado"))
    }
}

private fun hiddenMenu(state: AppUiState, actions: MenuActions, close: () -> Unit): List<MenuNode> = buildList {
    state.blender.hiddenObjects.forEach { hidden ->
        add(MenuLeaf(hidden.name, selected = false, hint = hidden.type) { close(); actions.onRevealObject(hidden.name) })
    }
    add(MenuSeparator)
    add(MenuLeaf("Mostrar todos") { close(); actions.onRevealAllObjects() })
}

// ------------------------------------------------------------------ Conexión

@Composable
private fun ConnectionMenu(
    state: AppUiState,
    fps: Float,
    lagMs: Long,
    streaming: Boolean,
    host: String,
    actions: MenuActions,
) {
    var open by remember { mutableStateOf(false) }
    val (color, label) = when (state.connection) {
        ConnectionStatus.CONNECTED -> Ink.Ok to "Conectado"
        ConnectionStatus.CONNECTING -> Ink.Warn to "Conectando"
        ConnectionStatus.RECONNECTING -> Ink.Warn to "Reconectando (${state.retryAttempt})"
        ConnectionStatus.DISCONNECTED -> Ink.Bad to "Desconectado"
    }
    val title = if (state.connection == ConnectionStatus.CONNECTED && state.blender.features.sceneScale) {
        val scale = state.blender.sceneScale
        "$label · ${scale.label} · ${scale.lengthUnit.short}"
    } else {
        label
    }

    Box {
        // El punto de estado es el propio botón: ya se miraba ahí, y ahorra un título.
        StatusDot(color, title, Modifier.clickableNoRipple { open = true })
        DropdownMenu(
            expanded = open,
            onDismissRequest = { open = false },
            containerColor = Ink.PanelSolid,
            modifier = Modifier.widthIn(min = 210.dp),
        ) {
            MenuLevel(
                nodes = listOf(
                    MenuHeading(host.ifBlank { "Sin equipo configurado" }),
                    MenuNote(
                        buildString {
                            append(label)
                            if (streaming) {
                                append("  ·  ${fps.toInt()} fps")
                                if (lagMs > 0) append("  ·  +$lagMs ms")
                            } else {
                                append("  ·  sin vídeo")
                            }
                        }
                    ),
                    MenuSeparator,
                    MenuLeaf("Preferencias de conexión…") { open = false; actions.onConnectionSettings() },
                    MenuLeaf("Reconectar ahora", enabled = state.connection != ConnectionStatus.CONNECTED) {
                        open = false
                        actions.onReconnect()
                    },
                    MenuLeaf("Desconectar", enabled = state.connection != ConnectionStatus.DISCONNECTED) {
                        open = false
                        actions.onDisconnect()
                    },
                ),
                onEnterGroup = {},
            )
        }
    }
}

// ------------------------------------------------------------------- piezas

/**
 * Botón de la barra con su desplegable. [content] recibe la lambda de cierre para que
 * cada hoja pueda cerrar el menú antes de ejecutar su acción.
 */
@Composable
private fun MenuAnchor(
    title: String,
    onOpen: () -> Unit = {},
    content: (close: () -> Unit) -> List<MenuNode>,
) {
    var open by remember { mutableStateOf(false) }
    // Ruta de submenús abierta. Se vacía al cerrar para no reabrir a media profundidad.
    var path by remember { mutableStateOf<List<MenuGroup>>(emptyList()) }
    val close = { open = false }

    fun dismiss() {
        open = false
        path = emptyList()
    }

    Box {
        Row(
            Modifier
                .heightIn(min = 34.dp)
                .clip(RoundedCornerShape(9.dp))
                .background(if (open) Ink.Accent.copy(alpha = .22f) else Color.Transparent)
                .clickableNoRipple {
                    path = emptyList()
                    open = true
                    onOpen()
                }
                .padding(start = 10.dp, end = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(title, color = if (open) Ink.Accent else Ink.Muted, fontSize = 13.sp)
            Icon(
                Icons.Default.ArrowDropDown,
                null,
                Modifier.size(18.dp),
                tint = if (open) Ink.Accent else Ink.Faint,
            )
        }

        DropdownMenu(
            expanded = open,
            onDismissRequest = ::dismiss,
            containerColor = Ink.PanelSolid,
            modifier = Modifier.widthIn(min = 210.dp),
        ) {
            val root = content(close)
            val current = path.lastOrNull()?.children ?: root

            if (path.isNotEmpty()) {
                MenuBack(path.joinToString(" · ") { it.label }) { path = path.dropLast(1) }
            }
            MenuLevel(current) { group -> path = path + group }
        }
    }
}

/** Pinta un nivel del árbol. Los grupos avisan por [onEnterGroup] en vez de actuar. */
@Composable
private fun MenuLevel(nodes: List<MenuNode>, onEnterGroup: (MenuGroup) -> Unit) {
    for (node in nodes) {
        when (node) {
            is MenuHeading -> Heading(node.label)
            is MenuNote -> Note(node.label)
            MenuSeparator -> Separator()
            is MenuGroup -> DropdownMenuItem(
                text = { Text(node.label, color = Ink.OnPanel, fontSize = 13.sp) },
                trailingIcon = {
                    Icon(Icons.Default.ChevronRight, null, Modifier.size(16.dp), tint = Ink.Faint)
                },
                onClick = { onEnterGroup(node) },
            )
            is MenuLeaf -> DropdownMenuItem(
                enabled = node.enabled,
                text = {
                    Column {
                        Text(
                            node.label,
                            color = when {
                                !node.enabled -> Ink.Faint
                                node.selected -> Ink.Accent
                                else -> Ink.OnPanel
                            },
                            fontSize = 13.sp,
                            fontWeight = if (node.selected) FontWeight.SemiBold else FontWeight.Normal,
                        )
                        node.hint?.let {
                            Text(it, color = Ink.Faint, fontSize = 10.sp, maxLines = 1)
                        }
                    }
                },
                onClick = node.onClick,
            )
        }
    }
}

@Composable
private fun MenuBack(trail: String, onBack: () -> Unit) {
    DropdownMenuItem(
        text = { Text("← $trail", color = Ink.Accent, fontSize = 12.sp, maxLines = 1) },
        onClick = onBack,
    )
    Separator()
}

@Composable
private fun Heading(text: String) {
    Text(
        text,
        color = Ink.Faint,
        fontSize = 9.sp,
        fontWeight = FontWeight.SemiBold,
        modifier = Modifier.padding(start = 12.dp, top = 8.dp, bottom = 2.dp),
    )
}

@Composable
private fun Note(text: String) {
    Text(text, color = Ink.Faint, fontSize = 11.sp, modifier = Modifier.padding(horizontal = 12.dp, vertical = 2.dp))
}

@Composable
private fun Separator() {
    Box(
        Modifier
            .padding(horizontal = 12.dp, vertical = 5.dp)
            .width(180.dp)
            .height(1.dp)
            .background(Ink.Divider),
    )
}
