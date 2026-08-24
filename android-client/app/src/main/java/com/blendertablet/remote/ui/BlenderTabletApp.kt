package com.blendertablet.remote.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Adjust
import androidx.compose.material.icons.filled.AspectRatio
import androidx.compose.material.icons.filled.BugReport
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.automirrored.filled.CallMade
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.CenterFocusStrong
import androidx.compose.material.icons.filled.CropFree
import androidx.compose.material.icons.filled.CropSquare
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.DeleteSweep
import androidx.compose.material.icons.filled.Deselect
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Flip
import androidx.compose.material.icons.filled.Grid4x4
import androidx.compose.material.icons.filled.LibraryAdd
import androidx.compose.material.icons.filled.LinearScale
import androidx.compose.material.icons.filled.Mouse
import androidx.compose.material.icons.filled.OpenWith
import androidx.compose.material.icons.automirrored.filled.Redo
import androidx.compose.material.icons.automirrored.filled.RotateRight
import androidx.compose.material.icons.filled.RoundedCorner
import androidx.compose.material.icons.filled.Rowing
import androidx.compose.material.icons.filled.ScatterPlot
import androidx.compose.material.icons.filled.SelectAll
import androidx.compose.material.icons.filled.Straighten
import androidx.compose.material.icons.filled.Timeline
import androidx.compose.material.icons.filled.TouchApp
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material.icons.automirrored.filled.Undo
import androidx.compose.material.icons.filled.ViewInAr
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material.icons.filled.Transform
import androidx.compose.material.icons.filled.MyLocation
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.FilterQuality
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.blendertablet.remote.MainViewModel
import com.blendertablet.remote.model.ActionId
import com.blendertablet.remote.model.ActiveTool
import com.blendertablet.remote.model.AppUiState
import com.blendertablet.remote.model.BlenderMode
import com.blendertablet.remote.model.ConnectionStatus
import com.blendertablet.remote.model.Constraint
import com.blendertablet.remote.model.EditTool
import com.blendertablet.remote.model.GesturePhase
import com.blendertablet.remote.model.Orientation
import com.blendertablet.remote.model.RadialMenu
import com.blendertablet.remote.model.SurfaceCatalog
import com.blendertablet.remote.model.TouchContext
import com.blendertablet.remote.model.SelectionMode
import com.blendertablet.remote.model.SnapAction
import com.blendertablet.remote.model.ToolSession
import com.blendertablet.remote.model.TransformMode
import com.blendertablet.remote.model.TransformSession

/**
 * Pantalla única: el viewport ocupa todo y los controles flotan encima.
 *
 * Nada de barras fijas que roben altura (§9: el viewport debe ser el 85-95% de la
 * pantalla). Los controles son iconos pequeños, agrupados en una barra desplegable
 * que se abre desde un solo botón, y un menú radial en la pulsación larga.
 */
@Composable
fun BlenderTabletApp(viewModel: MainViewModel) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    val settings by viewModel.settings.collectAsStateWithLifecycle()
    // El diálogo solo se impone la primera vez. Después los datos están guardados y
    // se abre a mano desde el indicador de estado. rememberSaveable para que una
    // recreación de la Activity no lo haga reaparecer.
    var connectionOpen by rememberSaveable { mutableStateOf(!viewModel.hasSavedConnection) }

    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = Ink.Accent,
            surface = Ink.PanelSolid,
            background = Ink.Background,
            onSurface = Ink.OnPanel,
        )
    ) {
        Surface(Modifier.fillMaxSize(), color = Ink.Background) {
            Workspace(state, viewModel, settings.host) { connectionOpen = true }
        }

        if (connectionOpen) {
            ConnectionSettingsDialog(
                initial = settings,
                connecting = state.connection == ConnectionStatus.CONNECTING,
                onDismiss = { connectionOpen = false },
                onSave = {
                    viewModel.saveSettings(it)
                    connectionOpen = false
                },
            )
        }
    }
}

@Composable
private fun Workspace(state: AppUiState, vm: MainViewModel, host: String, openConnection: () -> Unit) {
    val frame by vm.viewportFrame.collectAsStateWithLifecycle()
    val stats by vm.streamStats.collectAsStateWithLifecycle()

    var navigating by remember { mutableStateOf(false) }
    var railOpen by remember { mutableStateOf(false) }
    var quickMenuAt by remember { mutableStateOf<Pair<Float, Float>?>(null) }
    var chromeVisible by remember { mutableStateOf(true) }
    var saveAsOpen by remember { mutableStateOf(false) }
    // Guarda a QUIÉN se renombra: el sondeo se borra al cerrar el anillo.
    var renameTarget by remember { mutableStateOf<String?>(null) }
    // Acción pendiente de confirmar porque descarta cambios sin guardar.
    var pendingDiscard by remember { mutableStateOf<PendingDiscard?>(null) }
    var modifiersOpen by remember { mutableStateOf(false) }
    LaunchedEffect(state.blender.activeObject, state.blender.mode, state.blender.features.modifiers) {
        if (!state.blender.features.modifiers || state.blender.mode != BlenderMode.OBJECT || state.blender.activeObjectType != "MESH") modifiersOpen = false
    }

    /** Nuevo y Abrir se tragan lo no guardado: se confirma solo si hay algo que perder. */
    fun guardDiscard(pending: PendingDiscard) {
        if (state.file.dirty) pendingDiscard = pending else pending.run()
    }

    val menuActions = MenuActions(
        onFileMenuOpened = vm::refreshFileMenu,
        onNew = { guardDiscard(PendingDiscard.New(vm::fileNew)) },
        onOpen = { path -> guardDiscard(PendingDiscard.Open(path) { vm.fileOpen(path) }) },
        onSave = vm::fileSave,
        onSaveAs = { saveAsOpen = true },
        onAdd = vm::addPrimitive,
        onSnap = vm::snap,
        onConnectionSettings = openConnection,
        onReconnect = vm::onForeground,
        onDisconnect = vm::disconnect,
        onRevealObject = vm::revealObject,
        onRevealAllObjects = vm::revealAllObjects,
        onApplyTransform = vm::applyTransform,
        // El icono conmuta: si el panel ya está abierto, lo cierra.
        onModifiers = {
            modifiersOpen = !modifiersOpen
            if (modifiersOpen) vm.openModifiers()
        },
    )

    val session by vm.transformSession.collectAsStateWithLifecycle()
    val toolSession by vm.toolSession.collectAsStateWithLifecycle()
    val probe by vm.touchProbe.collectAsStateWithLifecycle()

    // Mientras hay sesión manda lo que dice el servidor, no lo que se eligió: puede
    // haber recortado el snap geométrico o la restricción por no valer en ese modo.
    val constraint = if (session.active) session.constraint else state.constraint
    val orientation = if (session.active) session.orientation else state.orientation
    val snapType = if (session.active) session.snapType else state.snapType
    val availableOrientations = state.blender.context.availableOrientations.ifEmpty {
        if (state.blender.mode == BlenderMode.EDIT) Orientation.entries
        else listOf(Orientation.GLOBAL, Orientation.LOCAL, Orientation.VIEW)
    }

    Box(Modifier.fillMaxSize().background(Ink.Background)) {
        ViewportLayer(
            state = state,
            vm = vm,
            frame = frame?.bitmap,
            onNavigatingChange = { navigating = it },
            onLongPress = { x, y, u, v ->
                // El menú se abre ya, en el sitio donde está el dedo, y en paralelo
                // se pregunta qué hay debajo: esperar a la respuesta para dibujarlo
                // se notaría como un tirón.
                quickMenuAt = x to y
                vm.probeTouch(u, v)
            },
        )

        AnimatedVisibility(
            visible = chromeVisible,
            enter = fadeIn(tween(140)),
            exit = fadeOut(tween(120)),
        ) {
            Box(Modifier.fillMaxSize()) {
                MenuBar(
                    state = state,
                    fps = stats.fps,
                    lagMs = stats.lagMs,
                    streaming = stats.connected,
                    host = host,
                    actions = menuActions,
                    modifier = Modifier.align(Alignment.TopStart).padding(Metrics.EdgeMargin),
                )

                val modifiersAvailable = state.blender.features.modifiers &&
                    state.blender.mode == BlenderMode.OBJECT && state.blender.activeObjectType == "MESH"

                if (!railOpen) {
                    FloatingPanel(Modifier.align(Alignment.CenterStart).padding(start = Metrics.EdgeMargin)) {
                        IconAction(Icons.Default.Tune, "Abrir herramientas") { railOpen = true }
                    }
                }

                if (modifiersAvailable && !modifiersOpen) {
                    FloatingPanel(Modifier.align(Alignment.CenterEnd).padding(end = Metrics.EdgeMargin)) {
                        IconAction(Icons.Default.Build, "Abrir modificadores") {
                            modifiersOpen = true
                            vm.openModifiers()
                        }
                    }
                }

                if (modifiersOpen) ModifierPanel(
                    state.blender,
                    ModifierActions(vm::addModifier, vm::setModifier, vm::toggleModifier,
                        vm::moveModifier, vm::applyModifier, vm::removeModifier) { modifiersOpen = false },
                    Modifier.align(Alignment.CenterEnd).padding(end = Metrics.EdgeMargin),
                )

                ToolRail(
                    visible = railOpen,
                    modifier = Modifier.align(Alignment.CenterStart).padding(start = Metrics.EdgeMargin),
                ) { RailContent(state, session, toolSession, vm) { railOpen = false } }

                TransformBar(
                    session = session,
                    stepIndex = vm.stepIndex(session.mode),
                    snapType = snapType,
                    constraint = constraint,
                    orientation = orientation,
                    valueMode = if (session.active) session.valueMode else state.valueMode,
                    availableOrientations = availableOrientations,
                    onConstraint = vm::setConstraint,
                    onOrientation = vm::setOrientation,
                    onSnapType = vm::setSnapType,
                    onStep = { vm.setStep(session.mode, it) },
                    onValueMode = vm::setValueMode,
                    onValue = vm::transformValue,
                    onConfirm = vm::transformConfirm,
                    onCancel = vm::transformCancel,
                    modifier = Modifier.align(Alignment.BottomCenter).padding(Metrics.EdgeMargin),
                )

                EditToolTray(
                    session = toolSession,
                    onParameter = vm::setToolParameter,
                    onConfirm = vm::confirmTool,
                    onCancel = vm::cancelTool,
                    modifier = Modifier.align(Alignment.BottomCenter).padding(Metrics.EdgeMargin),
                )

                ViewFooter(
                    projection = state.blender.view.perspective,
                    activeAxisView = state.blender.view.axisView,
                    onAxis = vm::viewAxis,
                    onOrbit = vm::viewOrbitStep,
                    onZoom = vm::viewZoomStep,
                    onProjection = vm::viewPerspective,
                    onFrameSelected = vm::frameSelected,
                    onFrameAll = vm::viewFrameAll,
                    modifier = Modifier.align(Alignment.BottomEnd).padding(Metrics.EdgeMargin),
                )

                if (state.debugVisible) {
                    DebugOverlay(state, Modifier.align(Alignment.TopStart).padding(start = Metrics.EdgeMargin, top = 56.dp))
                }
            }
        }

        // Ocultar del todo la interfaz: modo "solo viewport" (§70).
        FloatingPanel(Modifier.align(Alignment.TopEnd).padding(Metrics.EdgeMargin)) {
            IconAction(
                icon = if (chromeVisible) Icons.Default.VisibilityOff else Icons.Default.Visibility,
                description = if (chromeVisible) "Ocultar controles" else "Mostrar controles",
                onClick = { chromeVisible = !chromeVisible },
            )
        }

        state.error?.let { message ->
            ErrorToast(message, Modifier.align(Alignment.TopCenter).padding(top = 64.dp))
        }

        quickMenuAt?.let { (x, y) ->
            val touchContext = vm.touchContext(probe)
            QuickMenu(
                open = true,
                center = x to y,
                actions = quickActions(touchContext, vm) {
                    renameTarget = touchContext.objectName ?: state.blender.activeObject
                },
                contextLabel = quickContextLabel(touchContext),
                onDismiss = {
                    quickMenuAt = null
                    vm.clearProbe()
                },
            )
        }

        if (saveAsOpen) {
            SaveAsDialog(
                // La tablet no conoce el disco del PC: se propone la carpeta del
                // archivo abierto y, si no hay, la del último reciente.
                initialFolder = state.file.path.substringBeforeLast('/', "")
                    .ifBlank { state.recentFiles.firstOrNull()?.folder.orEmpty() },
                initialName = state.file.name.takeIf { state.file.saved } ?: "sin-titulo.blend",
                onDismiss = { saveAsOpen = false },
                onSave = {
                    saveAsOpen = false
                    vm.fileSaveAs(it)
                },
            )
        }

        // Se renombra el objeto que se tocó, no el activo: el menú se abrió sobre
        // uno concreto y pueden no ser el mismo.
        renameTarget?.let { target ->
            RenameDialog(
                initialName = target,
                onDismiss = { renameTarget = null },
                onRename = {
                    renameTarget = null
                    vm.rename(it, target)
                },
            )
        }

        pendingDiscard?.let { pending ->
            ConfirmDiscardDialog(
                title = pending.title,
                message = "«${state.file.name}» tiene cambios sin guardar que se perderán.",
                confirmLabel = pending.confirmLabel,
                onDismiss = { pendingDiscard = null },
                onConfirm = {
                    pendingDiscard = null
                    pending.run()
                },
            )
        }
    }
}

/** Acción que descarta el archivo abierto y por tanto necesita confirmación. */
private sealed class PendingDiscard(
    val title: String,
    val confirmLabel: String,
    val run: () -> Unit,
) {
    class New(run: () -> Unit) : PendingDiscard("Archivo nuevo", "Descartar y crear", run)
    class Open(val path: String, run: () -> Unit) :
        PendingDiscard("Abrir archivo", "Descartar y abrir", run)
}

/**
 * El vídeo y la capa táctil. Ya no dibuja manipulador: los ejes viven en la barra de
 * transformación, donde son botones grandes con cifras en vez de flechas finas que
 * tapaban el objeto.
 */
@Composable
private fun ViewportLayer(
    state: AppUiState,
    vm: MainViewModel,
    frame: android.graphics.Bitmap?,
    onNavigatingChange: (Boolean) -> Unit,
    onLongPress: (px: Float, py: Float, u: Float, v: Float) -> Unit,
) {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        if (frame == null) {
            EmptyViewport()
            InputSurface(
                modifier = Modifier.fillMaxSize(),
                onDebug = vm::updateInput,
                onToolGesture = vm::toolGesture,
                onViewGesture = { g, phase, dx, dy, factor -> vm.viewGesture(g, phase, dx, dy, factor) },
                onTap = vm::pick,
                onDoubleTap = vm::frameSelected,
                onLongPress = onLongPress,
            )
            return@Box
        }

        // Imagen y capa táctil comparten rectángulo exacto: así el toque cae donde
        // se ve, aunque sobren bandas por diferencia de proporción (§39).
        Box(
            Modifier
                .aspectRatio(frame.width.toFloat() / frame.height.toFloat())
                .fillMaxSize(),
        ) {
            Image(
                bitmap = frame.asImageBitmap(),
                contentDescription = "Viewport de Blender",
                modifier = Modifier.fillMaxSize(),
                contentScale = ContentScale.Fit,
                // El JPEG ya suaviza; interpolar otra vez emborrona las aristas.
                filterQuality = FilterQuality.None,
            )
            InputSurface(
                modifier = Modifier.fillMaxSize(),
                onDebug = vm::updateInput,
                onToolGesture = vm::toolGesture,
                onViewGesture = { g, phase, dx, dy, factor ->
                    val moving = phase == GesturePhase.BEGIN || phase == GesturePhase.UPDATE
                    onNavigatingChange(moving)
                    vm.viewGesture(g, phase, dx, dy, factor)
                    if (!moving) vm.requestState()
                },
                onTap = vm::pick,
                onDoubleTap = vm::frameSelected,
                onLongPress = onLongPress,
            )
        }
    }
}

@Composable
private fun EmptyViewport() {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text("SIN VÍDEO", color = Ink.Faint, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
        Spacer(Modifier.height(4.dp))
        Text("Arranca el servidor en Blender y conecta", color = Ink.Faint, fontSize = 12.sp)
    }
}

/**
 * Contenido de la barra desplegable: la herramienta activa y el submodo de selección.
 *
 * El rail elige; el footer muestra las opciones. Mover/Rotar/Escalar abren la
 * transformación modal; Extruir/Bisel/Inset/Subdividir abren la herramienta
 * paramétrica; Vértice/Arista/Cara eligen el submodo con iconos propios.
 */
@Composable
private fun RailContent(
    state: AppUiState,
    session: TransformSession,
    toolSession: ToolSession,
    vm: MainViewModel,
    onClose: () -> Unit,
) {
    val editable = state.blender.activeObject != null
    val inEdit = state.blender.mode == BlenderMode.EDIT

    IconAction(Icons.Default.Close, "Ocultar herramientas", onClick = onClose)
    RailDivider()
    RailLabel("MODO")
    IconAction(
        Icons.Default.ViewInAr, "Object Mode",
        selected = !inEdit,
        onClick = { vm.setMode(BlenderMode.OBJECT) },
    )
    IconAction(
        Icons.Default.Straighten, "Edit Mode",
        selected = inEdit,
        enabled = editable,
        onClick = { vm.setMode(BlenderMode.EDIT) },
    )

    RailDivider()
    RailLabel("HERRAMIENTA")
    IconAction(
        Icons.Default.Mouse, "Seleccionar",
        selected = state.activeTool == ActiveTool.SELECT && !session.active && !toolSession.active,
        onClick = vm::selectTool,
    )
    IconAction(
        Icons.Default.OpenWith, "Mover",
        selected = session.active && session.mode == TransformMode.MOVE,
        enabled = editable,
        onClick = { vm.transformBegin(TransformMode.MOVE) },
    )
    IconAction(
        Icons.AutoMirrored.Filled.RotateRight, "Rotar",
        selected = session.active && session.mode == TransformMode.ROTATE,
        enabled = editable,
        onClick = { vm.transformBegin(TransformMode.ROTATE) },
    )
    IconAction(
        Icons.Default.AspectRatio, "Escalar",
        selected = session.active && session.mode == TransformMode.SCALE,
        enabled = editable,
        onClick = { vm.transformBegin(TransformMode.SCALE) },
    )

    if (inEdit) {
        RailDivider()
        RailLabel("EDITAR")
        // Cada herramienta pide un tipo de elemento: Inset solo trabaja con caras y
        // Subdividir con aristas. Sin lo que necesita, el servidor respondería
        // `empty_selection`; se apaga el botón en vez de dejar que falle.
        val counts = state.blender.context
        for (tool in EditTool.entries) {
            if (counts.availableTools.isNotEmpty() && ActiveTool.valueOf(tool.name) !in counts.availableTools) continue
            val ready = when (tool) {
                EditTool.EXTRUDE -> counts.countFor(state.blender.selectionMode) > 0
                EditTool.BEVEL -> counts.countFor(state.blender.selectionMode) > 0
                EditTool.INSET -> counts.selectionCounts.faces > 0
                EditTool.SUBDIVIDE -> counts.selectionCounts.edges > 0
                EditTool.LOOP_CUT -> true // sin arista queda armada y el próximo tap la elige
            }
            IconAction(
                icon = editToolIcon(tool),
                description = if (ready) tool.label else "${tool.label} · ${tool.requirement}",
                selected = toolSession.active && toolSession.tool == tool,
                enabled = ready || toolSession.active,
                onClick = { vm.beginEditTool(tool) },
            )
        }

        RailDivider()
        // El conteo de selección del submodo activo orienta sin abrir un panel.
        val count = state.blender.context.countFor(state.blender.selectionMode)
        RailLabel("SEL${if (count > 0) " · $count" else ""}")
        IconAction(
            Icons.Default.ScatterPlot, "Vértices",
            selected = state.blender.selectionMode == SelectionMode.VERTEX,
            onClick = { vm.setSelectionMode(SelectionMode.VERTEX) },
        )
        IconAction(
            Icons.Default.LinearScale, "Aristas",
            selected = state.blender.selectionMode == SelectionMode.EDGE,
            onClick = { vm.setSelectionMode(SelectionMode.EDGE) },
        )
        IconAction(
            Icons.Default.CropSquare, "Caras",
            selected = state.blender.selectionMode == SelectionMode.FACE,
            onClick = { vm.setSelectionMode(SelectionMode.FACE) },
        )
    }

    RailDivider()
    IconAction(Icons.AutoMirrored.Filled.Undo, "Deshacer", onClick = vm::undo)
    IconAction(Icons.AutoMirrored.Filled.Redo, "Rehacer", onClick = vm::redo)
    IconAction(Icons.Default.ContentCopy, "Duplicar", enabled = editable, onClick = vm::duplicate)

    RailDivider()
    IconAction(Icons.Default.BugReport, "Diagnóstico", selected = state.debugVisible, onClick = vm::toggleDebug)
}

private fun editToolIcon(tool: EditTool) = when (tool) {
    EditTool.EXTRUDE -> Icons.AutoMirrored.Filled.CallMade
    EditTool.BEVEL -> Icons.Default.RoundedCorner
    EditTool.INSET -> Icons.Default.CropFree
    EditTool.SUBDIVIDE -> Icons.Default.Grid4x4
    EditTool.LOOP_CUT -> Icons.Default.LinearScale
}

/** Qué borra `mesh.delete` según el submodo de selección. */
private fun deleteWhat(mode: SelectionMode): String = when (mode) {
    SelectionMode.VERTEX -> "VERTS"
    SelectionMode.EDGE -> "EDGES"
    SelectionMode.FACE -> "FACES"
}

/**
 * Menú radial de la pulsación larga.
 *
 * Qué acciones salen lo decide [RadialMenu.actionsFor] a partir de lo que hay bajo el
 * dedo; aquí solo se les pone icono y se les conecta el comando. Esa separación es lo
 * que permite comprobar en un test que el long click no invade el rail ni el top: la
 * lista de [ActionId] es dato, no interfaz.
 */
private fun quickActions(
    context: TouchContext,
    vm: MainViewModel,
    onRename: () -> Unit,
): List<QuickAction> = RadialMenu.actionsFor(context).map { id ->
    val label = SurfaceCatalog.labelOf(id)
    when (id) {
        ActionId.SELECT_ALL -> QuickAction(label, Icons.Default.SelectAll) { vm.selectAll() }
        ActionId.DESELECT_ALL -> QuickAction(label, Icons.Default.Deselect) { vm.deselectAll() }
        ActionId.SELECT_INVERT -> QuickAction(label, Icons.Default.Flip) { vm.invertSelection() }
        ActionId.SELECT_UNDER -> QuickAction(label, Icons.Default.TouchApp) {
            context.objectName?.let { vm.selectObject(it, add = false) }
        }
        ActionId.SELECT_ADD_UNDER -> QuickAction(label, Icons.Default.LibraryAdd) {
            context.objectName?.let { vm.selectObject(it, add = true) }
        }
        ActionId.SELECT_LOOP -> QuickAction(label, Icons.Default.Timeline) { vm.selectLoop() }
        ActionId.SELECT_RING -> QuickAction(label, Icons.Default.Rowing) { vm.selectRing() }
        ActionId.HIDE_OBJECT -> QuickAction(label, Icons.Default.VisibilityOff) { vm.hideObject(context.objectName) }
        ActionId.HIDE_GEOMETRY -> QuickAction(label, Icons.Default.VisibilityOff) { vm.hideSelection() }
        ActionId.REVEAL_GEOMETRY -> QuickAction(label, Icons.Default.Visibility) { vm.revealSelection() }
        ActionId.DUPLICATE_LINKED -> QuickAction(label, Icons.Default.ContentCopy) { vm.duplicateLinked() }
        ActionId.RENAME -> QuickAction(label, Icons.Default.Edit, onClick = onRename)
        ActionId.DISSOLVE -> QuickAction(label, Icons.Default.DeleteSweep) { vm.meshDelete("ONLY_FACES") }
        ActionId.APPLY_TRANSFORMS -> QuickAction(
            label, Icons.Default.Transform,
            children = listOf(
                QuickAction("Posición", Icons.Default.OpenWith) { vm.applyTransform(true, false, false) },
                QuickAction("Rotación", Icons.AutoMirrored.Filled.RotateRight) { vm.applyTransform(false, true, false) },
                QuickAction("Escala", Icons.Default.AspectRatio) { vm.applyTransform(false, false, true) },
            ),
        )
        ActionId.SET_ORIGIN -> QuickAction(
            label, Icons.Default.MyLocation,
            children = listOf(
                QuickAction("Al cursor", Icons.Default.MyLocation) { vm.snap(SnapAction.ORIGIN_TO_CURSOR) },
                QuickAction("A geometría", Icons.Default.CenterFocusStrong) { vm.snap(SnapAction.ORIGIN_TO_GEOMETRY) },
                QuickAction("Centro masas", Icons.Default.Adjust) { vm.snap(SnapAction.ORIGIN_TO_MASS) },
            ),
        )
        // Borrar es el destructivo: rojo y siempre el último del anillo.
        ActionId.DELETE -> QuickAction(label, Icons.Default.Delete, tint = Ink.Bad) {
            if (context.mode == BlenderMode.EDIT) vm.meshDelete(deleteWhat(context.selectionMode))
            else vm.delete()
        }
        // El catálogo tiene más acciones, pero son de otras superficies y
        // RadialMenu no las emite. Un `else` mudo evitaría que se notara.
        else -> QuickAction(label, Icons.Default.Adjust, enabled = false)
    }
}

/** Etiqueta del centro del menú radial: qué hay bajo el dedo, no el modo global. */
private fun quickContextLabel(context: TouchContext): String = when {
    context.mode == BlenderMode.EDIT && !context.hit -> "Malla"
    context.mode == BlenderMode.EDIT -> when (context.selectionMode) {
        SelectionMode.VERTEX -> "Vértice"
        SelectionMode.EDGE -> "Arista"
        SelectionMode.FACE -> "Cara"
    }
    context.objectName != null -> context.objectName
    else -> "Escena"
}

@Composable
private fun ErrorToast(message: String, modifier: Modifier = Modifier) {
    FloatingPanel(modifier) {
        Text(message, color = Ink.Bad, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 4.dp))
    }
}

@Composable
private fun DebugOverlay(state: AppUiState, modifier: Modifier = Modifier) {
    FloatingPanel(modifier) {
        Column(verticalArrangement = Arrangement.spacedBy(1.dp)) {
            val input = state.input
            Text("dedos ${input.pointerCount}  ·  ${input.tool}", color = Ink.Muted, fontSize = 11.sp)
            Text("presión ${"%.2f".format(input.pressure)}", color = Ink.Faint, fontSize = 11.sp)
            Text("x ${input.x.toInt()}  y ${input.y.toInt()}", color = Ink.Faint, fontSize = 11.sp)
            Text("modo ${state.blender.mode}", color = Ink.Faint, fontSize = 11.sp)
        }
    }
}
