package com.blendertablet.remote.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateDpAsState
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
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Adjust
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.AspectRatio
import androidx.compose.material.icons.filled.BlurOn
import androidx.compose.material.icons.filled.BugReport
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.automirrored.filled.CallMade
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.CenterFocusStrong
import androidx.compose.material.icons.filled.CropFree
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.DeleteSweep
import androidx.compose.material.icons.filled.Deselect
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Flip
import androidx.compose.material.icons.filled.Grid4x4
import androidx.compose.material.icons.filled.Hexagon
import androidx.compose.material.icons.filled.Hub
import androidx.compose.material.icons.filled.JoinFull
import androidx.compose.material.icons.filled.LibraryAdd
import androidx.compose.material.icons.filled.ContentCut
import androidx.compose.material.icons.filled.Lens
import androidx.compose.material.icons.filled.Lightbulb
import androidx.compose.material.icons.filled.LinearScale
import androidx.compose.material.icons.filled.Mouse
import androidx.compose.material.icons.filled.OpenWith
import androidx.compose.material.icons.filled.PhotoCamera
import androidx.compose.material.icons.automirrored.filled.Redo
import androidx.compose.material.icons.automirrored.filled.RotateRight
import androidx.compose.material.icons.automirrored.filled.ShowChart
import androidx.compose.material.icons.filled.RoundedCorner
import androidx.compose.material.icons.filled.Rowing
import androidx.compose.material.icons.filled.SelectAll
import androidx.compose.material.icons.filled.ShowChart
import androidx.compose.material.icons.filled.TextFields
import androidx.compose.material.icons.filled.Timeline
import androidx.compose.material.icons.filled.TouchApp
import androidx.compose.material.icons.automirrored.filled.Undo
import androidx.compose.material.icons.filled.ViewInAr
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material.icons.filled.Transform
import androidx.compose.material.icons.filled.MyLocation
import androidx.compose.material.icons.filled.Waves
import androidx.compose.material.icons.filled.WbSunny
import androidx.compose.material.icons.filled.ZoomOutMap
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
import kotlinx.coroutines.delay
import com.blendertablet.remote.MainViewModel
import com.blendertablet.remote.model.ActionId
import com.blendertablet.remote.model.ActiveTool
import com.blendertablet.remote.model.AddCategory
import com.blendertablet.remote.model.AddObject
import com.blendertablet.remote.model.AppUiState
import com.blendertablet.remote.model.BlenderMode
import com.blendertablet.remote.model.ConnectionStatus
import com.blendertablet.remote.model.Constraint
import com.blendertablet.remote.model.EditTool
import com.blendertablet.remote.model.EditFooterAction
import com.blendertablet.remote.model.EditCatalogAction
import com.blendertablet.remote.model.Gesture
import com.blendertablet.remote.model.GesturePhase
import com.blendertablet.remote.model.Orientation
import com.blendertablet.remote.model.RadialMenu
import com.blendertablet.remote.model.SurfaceCatalog
import com.blendertablet.remote.model.TouchContext
import com.blendertablet.remote.model.SelectionMode
import com.blendertablet.remote.model.SelectionOp
import com.blendertablet.remote.model.ShapeTool
import com.blendertablet.remote.model.SnapAction
import com.blendertablet.remote.model.ToolSession
import com.blendertablet.remote.model.TransformMode
import com.blendertablet.remote.model.TransformSession
import com.blendertablet.remote.model.isTransformToolSelected
import com.blendertablet.remote.model.bottomTrayVisible

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
    val h264Active by vm.h264Active.collectAsStateWithLifecycle()
    val h264Size by vm.h264Size.collectAsStateWithLifecycle()
    val remoteFiles by vm.remoteFiles.collectAsStateWithLifecycle()

    var quickMenuAt by remember { mutableStateOf<Pair<Float, Float>?>(null) }
    // El ojo vive en el estado del ViewModel, no aquí: apagar los controles apaga
    // también los overlays del servidor, y esa parte no es local.
    val chromeVisible = state.controlsVisible
    var fileBrowserMode by remember { mutableStateOf<FileBrowserMode?>(null) }
    // Guarda a QUIÉN se renombra: el sondeo se borra al cerrar el anillo.
    var renameTarget by remember { mutableStateOf<String?>(null) }
    // Acción pendiente de confirmar porque descarta cambios sin guardar.
    var pendingDiscard by remember { mutableStateOf<PendingDiscard?>(null) }
    var modifiersOpen by remember { mutableStateOf(false) }
    var referencesOpen by rememberSaveable { mutableStateOf(false) }
    LaunchedEffect(state.blender.activeObject, state.blender.mode, state.blender.features.modifiers, state.blender.cad.workspace) {
        if (state.blender.cad.workspace || !state.blender.features.modifiers || state.blender.mode != BlenderMode.OBJECT || state.blender.activeObjectType != "MESH") modifiersOpen = false
    }

    // El toast de error se auto-descarta: un aviso que no caduca es ruido permanente.
    LaunchedEffect(state.error) {
        if (state.error != null) {
            delay(5000)
            vm.clearError()
        }
    }

    // El aviso de confirmación se va antes: se lee de un vistazo y estorba menos.
    LaunchedEffect(state.notice) {
        if (state.notice != null) {
            delay(3000)
            vm.clearNotice()
        }
    }

    /** Nuevo y Abrir se tragan lo no guardado: se confirma solo si hay algo que perder. */
    fun guardDiscard(pending: PendingDiscard) {
        if (state.file.dirty) pendingDiscard = pending else pending.run()
    }

    val menuActions = MenuActions(
        onFileMenuOpened = vm::refreshFileMenu,
        onNew = { guardDiscard(PendingDiscard.New(vm::fileNew)) },
        onBrowseOpen = {
            fileBrowserMode = FileBrowserMode.OPEN
            vm.openFileBrowser()
        },
        onSave = vm::fileSave,
        onSaveAs = {
            fileBrowserMode = FileBrowserMode.SAVE
            vm.openFileBrowser()
        },
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
        onSceneScale = vm::setSceneScale,
        onReferences = { referencesOpen = true },
    )

    val session by vm.transformSession.collectAsStateWithLifecycle()
    val toolSession by vm.toolSession.collectAsStateWithLifecycle()
    val probe by vm.touchProbe.collectAsStateWithLifecycle()
    val knifeScreenPoints by vm.knifeScreenPoints.collectAsStateWithLifecycle()

    // Hay una bandeja horizontal inferior ocupando el borde de abajo: la de
    // transformación, la de herramienta paramétrica o el aviso de Loop Cut esperando
    // toque. Mientras exista, el teclado de vistas se eleva para no solaparse.
    val sculptActive = state.blender.mode == BlenderMode.SCULPT
    val trayPresent = sculptActive || state.blender.cad.workspace || bottomTrayVisible(
        session.active, toolSession.active, state.activeTool, state.loopCutAwaitingTap,
        toolSessionArmed = toolSession.armed,
    )
    val trayInset by animateDpAsState(
        targetValue = if (sculptActive) 132.dp else if (state.blender.cad.workspace) 132.dp else if (trayPresent) Metrics.TrayInset else 0.dp,
        animationSpec = tween(160),
        label = "tray-inset",
    )

    // Mientras hay sesión manda lo que dice el servidor, no lo que se eligió: puede
    // haber recortado el snap geométrico o la restricción por no valer en ese modo.
    val constraint = if (session.active) session.constraint else state.constraint
    val orientation = if (session.active) session.orientation else state.orientation
    val snapType = if (session.active) session.snapType else state.snapType
    val availableOrientations = state.blender.context.availableOrientations.ifEmpty {
        if (state.blender.mode == BlenderMode.EDIT) Orientation.entries
        else listOf(Orientation.GLOBAL, Orientation.LOCAL, Orientation.VIEW)
    }

    // Callbacks del viewport en un solo objeto recordado: sin esto, ViewportLayer
    // recibía `state` y `vm` enteros y se invalidaba con cada cambio de estado (o sea,
    // con cada toque y cada snapshot) aunque solo dibuje el último frame.
    val viewportInput = remember(vm) {
        ViewportInput(
            onDebug = vm::updateInput,
            onToolGesture = vm::toolGesture,
            onToolPointer = vm::toolPointer,
            onKnifeDrag = vm::knifeDrag,
            onTweakDrag = vm::tweakGesture,
            onCadGesture = vm::cadGesture,
            onSculptStroke = vm::sculptStroke,
            onViewGestureLive = { g, phase, dx, dy, factor ->
                vm.viewGesture(g, phase, dx, dy, factor)
                if (phase != GesturePhase.BEGIN && phase != GesturePhase.UPDATE) vm.requestState()
            },
            onViewGesturePlain = vm::viewGesture,
            onTap = vm::pick,
            onDoubleTap = vm::frameSelected,
            onSurfaceAvailable = vm::attachVideoSurface,
            onSurfaceChanged = vm::changeVideoSurface,
            onSurfaceDestroyed = vm::detachVideoSurface,
        )
    }

    Box(Modifier.fillMaxSize().background(Ink.Background)) {
        ViewportLayer(
            frame = frame?.bitmap,
            h264Active = h264Active,
            h264Size = h264Size,
            input = viewportInput,
            sculptEnabled = sculptActive && state.connection == ConnectionStatus.CONNECTED,
            sculptStylusOnly = state.sculptStylusOnly,
            sculptRadius = state.blender.sculpt.radius,
            sculptPressureSize = state.blender.sculpt.pressureSize,
            cadDrawingEnabled = state.connection == ConnectionStatus.CONNECTED && state.blender.cad.workspace && ((state.blender.cad.activeSketchId != null && state.cadTool != null && state.cadTool != "MULTI") ||
                (state.blender.features.cad.sketchEditing && state.blender.cad.sessionActive && state.blender.cad.operation in listOf("EXTRUDE", "CUT"))),
            cadOverlay = if (state.blender.cad.workspace) state.blender.cad.overlay else emptyList(),
            shapeTool = if (state.blender.cad.workspace) ShapeTool.NONE else state.shapeTool,
            fixedCircleRadius = state.circleRadius,
            knifePoints = knifeScreenPoints,
            knifeActive = !state.blender.cad.workspace && toolSession.active && toolSession.tool == EditTool.KNIFE &&
                state.blender.features.knifeDrag,
            tweakActive = !state.blender.cad.workspace && state.activeTool == ActiveTool.TWEAK &&
                state.blender.mode == BlenderMode.EDIT,
            longPressEnabled = !sculptActive && !state.blender.cad.workspace && toolSession.input != "REPEAT_TAP" && viewportLongPressEnabled(session.active, toolSession.active),
            repeatTap = toolSession.armed && toolSession.input == "REPEAT_TAP",
            independentTaps = state.blender.mode == BlenderMode.EDIT || state.blender.cad.workspace,
            // Los marcadores de transformación ya forman parte del fotograma.
            snapCandidate = if (state.blender.cad.workspace) null else toolSession.snapCandidate,
            cancelPickOnNavigation = toolSession.input == "FACE_PAIR",
            proportionalCircle = if (state.blender.cad.workspace) null else session.proportionalCircle,
            navigationOrbitEnabled = (sculptActive || navigationOrbitVisible(
                session.active,
                toolSession.active,
                state.activeTool,
            )) && quickMenuAt == null && !modifiersOpen,
            onShape = vm::shapeSelect,
            onLongPress = { x, y, u, v ->
                // El menú se abre ya, en el sitio donde está el dedo, y en paralelo
                // se pregunta qué hay debajo: esperar a la respuesta para dibujarlo
                // se notaría como un tirón.
                quickMenuAt = x to y
                vm.probeTouch(u, v)
            },
        )

        // Con B/C armada el dedo dibuja la forma en vez de orbitar: el chip enseña
        // que la herramienta está activa y ofrece la vuelta a la selección normal.
        // Vive fuera del chrome porque con los controles ocultos sería la única
        // pista de por qué el toque ya no selecciona.
        AnimatedVisibility(
            visible = state.shapeTool != ShapeTool.NONE,
            enter = fadeIn(tween(140)),
            exit = fadeOut(tween(120)),
        ) {
            FloatingPanel(Modifier.align(Alignment.TopCenter).padding(top = Metrics.EdgeMargin)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        if (state.shapeTool == ShapeTool.BOX) "Selección por caja"
                        else "Selección por círculo",
                        color = Ink.Muted,
                        fontSize = 12.sp,
                        modifier = Modifier.padding(start = 6.dp, end = 2.dp),
                    )
                    IconAction(Icons.Default.Close, "Volver a la selección normal") {
                        vm.toggleShapeTool(state.shapeTool)
                    }
                }
            }
        }

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

                if (!state.blender.cad.workspace && !sculptActive) {
                val modifiersAvailable = state.blender.features.modifiers &&
                    state.blender.mode == BlenderMode.OBJECT && state.blender.activeObjectType == "MESH"

                if (modifiersAvailable && !modifiersOpen) {
                    FloatingPanel(
                        Modifier
                            .align(Alignment.TopEnd)
                            .padding(top = 142.dp, end = Metrics.EdgeMargin),
                    ) {
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
                    Modifier
                        .align(Alignment.TopEnd)
                        .padding(
                            top = 142.dp,
                            end = Metrics.EdgeMargin,
                            bottom = 74.dp,
                        ),
                )

                ToolRail(
                    modifier = Modifier.align(Alignment.CenterStart).padding(start = Metrics.EdgeMargin),
                ) { RailContent(state, session, toolSession, vm) }

                if (state.activeTool == ActiveTool.TWEAK && state.blender.mode == BlenderMode.EDIT) {
                    TweakHelpersTray(
                        settings = state.tweak,
                        selectionMode = state.blender.selectionMode,
                        motions = state.blender.features.tweakMotions,
                        snapTypes = state.blender.features.tweakSnapTypes,
                        unitScaleLength = state.blender.unitScaleLength,
                        lengthUnit = state.blender.sceneScale.lengthUnit,
                        onSlide = vm::setTweakMotion,
                        onSnapType = vm::setTweakSnapType,
                        onSnapStep = vm::setTweakSnapStep,
                        onClamp = vm::toggleTweakClamp,
                        modifier = Modifier.align(Alignment.BottomCenter).fillMaxWidth().padding(Metrics.EdgeMargin),
                    )
                }

                if (state.activeTool != ActiveTool.TWEAK) TransformBar(
                    session = session,
                    unitScaleLength = state.blender.unitScaleLength,
                    proportionalUnit = state.blender.sceneScale.lengthUnit,
                    proportionalRadiusStep = state.blender.sceneScale.proportionalRadiusStep,
                    stepIndex = vm.stepIndex(session.mode),
                    snapType = snapType,
                    constraint = constraint,
                    orientation = orientation,
                    valueMode = if (session.active) session.valueMode else state.valueMode,
                    referencePicking = state.referencePicking,
                    referencePickingRole = state.referenceRole,
                    canChangeSelection = state.blender.mode == BlenderMode.EDIT && state.blender.features.transformStepSelection,
                    selectionPicking = session.active && state.transformSelectionSessionId == session.sessionId,
                    onChooseSelection = vm::chooseTransformSelection,
                    moveStepValue = state.moveStepValue,
                    moveStepUnit = state.moveStepUnit,
                    scaleStepValue = state.scaleStepValue,
                    scaleUnit = state.scaleUnit,
                    availableOrientations = availableOrientations,
                    onConstraint = vm::setConstraint,
                    onOrientation = vm::setOrientation,
                    onSnapType = vm::setSnapType,
                    onSnapToSelection = vm::setSnapToSelection,
                    onStep = { vm.setStep(session.mode, it) },
                    onValueMode = vm::setValueMode,
                    onReference = vm::toggleTransformReference,
                    onCenterPreset = vm::setTransformCenterPreset,
                    onMoveStep = vm::setMoveStep,
                    onScaleStep = vm::setScaleStep,
                    onValue = vm::transformValue,
                    onFlatten = vm::flattenScaleAxis,
                    onProportionalRadiusValue = vm::setProportionalRadius,
                    onProportionalFalloff = vm::cycleProportionalFalloff,
                    onConfirm = vm::transformConfirm,
                    onCancel = vm::transformCancel,
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .fillMaxWidth()
                        .padding(Metrics.EdgeMargin),
                )

                EditToolTray(
                    session = toolSession,
                    variantLabel = state.blender.features.editToolbar.families
                        .firstNotNullOfOrNull { activeVariantOf(it, toolSession)?.label },
                    selectionMode = state.blender.selectionMode,
                    unitScaleLength = state.blender.unitScaleLength,
                    onParameter = vm::setToolParameter,
                    onConfirm = vm::confirmTool,
                    onCancel = vm::cancelTool,
                    onLoopPop = vm::loopCutPop,
                    lengthUnit = state.blender.sceneScale.lengthUnit,
                    awaitingPick = state.activeTool == ActiveTool.LOOP_CUT &&
                        !toolSession.active && state.loopCutAwaitingTap,
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .fillMaxWidth()
                        .padding(Metrics.EdgeMargin),
                )

                KnifeTray(
                    session = toolSession,
                    onKnifePop = vm::knifePop,
                    onKnifeNewStroke = vm::knifeNewStroke,
                    onKnifeClose = vm::knifeClose,
                    onKnifeSnap = vm::knifeSnap,
                    onKnifeSnapMode = vm::knifeSnapMode,
                    onConfirm = vm::confirmTool,
                    onCancel = vm::cancelTool,
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .fillMaxWidth()
                        .padding(Metrics.EdgeMargin),
                )

                BisectTray(
                    session = toolSession,
                    onParameter = vm::setToolParameter,
                    onConfirm = vm::confirmTool,
                    onCancel = vm::cancelTool,
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .fillMaxWidth()
                        .padding(Metrics.EdgeMargin),
                )

                }
                if (state.blender.cad.workspace) CadWorkspace(state, vm)
                if (sculptActive) SculptWorkspace(state, vm)
                if (referencesOpen) ReferencePanel(Modifier.align(Alignment.TopCenter).padding(top = 76.dp),
                    onDismiss = { referencesOpen = false })

                if (!state.blender.cad.workspace || state.blender.cad.activeSketchId == null) ViewFooter(
                    onFrameSelected = vm::frameSelected,
                    projection = state.blender.view.perspective,
                    activeAxisView = state.blender.view.axisView,
                    inEdit = !state.blender.cad.workspace && state.blender.mode == BlenderMode.EDIT,
                    selectionMode = state.blender.selectionMode,
                    showEditShortcuts = state.blender.features.editCatalog.available,
                    editToolbarAvailable = state.blender.features.editToolbar.available,
                    connectVerticesEnabled = state.blender.features.editCatalog.actionsFor(SelectionMode.VERTEX)
                        .any { it.id == "CONNECT_VERTICES" && it.enabled },
                    showGrow = state.blender.features.selectionGrow,
                    onAxis = vm::viewAxis,
                    onOrbit = vm::viewOrbitStep,
                    onRotate180 = { vm.viewOrbitStep(1f, 0f) },
                    onProjection = vm::viewPerspective,
                    onMore = vm::selectMore,
                    onLess = vm::selectLess,
                    onEditAction = vm::editFooterAction,
                    modifier = Modifier
                        .align(Alignment.BottomEnd)
                        .padding(Metrics.EdgeMargin)
                        .padding(bottom = trayInset),
                )

                if (state.debugVisible) {
                    DebugOverlay(vm, state.blender.mode, Modifier.align(Alignment.TopStart).padding(start = Metrics.EdgeMargin, top = 56.dp))
                }

                if (!state.blender.cad.workspace && state.shapeTool == ShapeTool.CIRCLE) {
                    CircleRadiusBar(
                        selected = state.circleRadius,
                        onRadius = vm::setCircleRadius,
                        modifier = Modifier.align(Alignment.TopCenter).padding(top = 62.dp),
                    )
                }
            }
        }

        // Barra de tools junto al ojo (wireframe, Ctrl/Alt, undo/redo). Vive fuera del chrome
        // solo para que el ojo siga accesible: la propia barra se esconde con el
        // resto y deja el viewport limpio, sin controles y sin rejilla (§70).
        TopToolbar(
            state = state,
            vm = vm,
            chromeVisible = chromeVisible,
            onToggleChrome = vm::toggleControls,
            modifier = Modifier.align(Alignment.TopEnd).padding(Metrics.EdgeMargin),
        )
        if (chromeVisible) {
            ModeRail(
                state = state,
                vm = vm,
                modifier = Modifier.align(Alignment.TopEnd).padding(end = Metrics.EdgeMargin, top = 76.dp),
            )
        }

        state.error?.let { message ->
            ErrorToast(message, Modifier.align(Alignment.TopCenter).padding(top = 64.dp))
        }

        // Un error tapa al aviso: si algo ha fallado, esa es la noticia.
        if (state.error == null) {
            state.notice?.let { message ->
                NoticeToast(message, Modifier.align(Alignment.TopCenter).padding(top = 64.dp))
            }
        }

        quickMenuAt?.let { (x, y) ->
            // Un único anillo curado para Object y Edit (plan 001): el catálogo del
            // servidor ya no se vuelca entero al anillo, vive detrás del sector
            // "Tools de malla" como panel vertical (ver quickActions/EDIT_MESH_TOOLS).
            val touchContext = vm.touchContext(probe)
            val dismiss = {
                quickMenuAt = null
                vm.clearProbe()
            }
            val meshToolsChildren = if (touchContext.mode == BlenderMode.EDIT && state.blender.features.editCatalog.available) {
                // Ya en el anillo (Loop/Ring/Ocultar) o en la barra izquierda
                // (Extrude/Inset/Loop Cut/Cut) no se repiten aquí (F1 "cero duplicidades").
                val excluded = RADIAL_TOP_LEVEL_CATALOG_IDS +
                    if (state.blender.features.editToolbar.available)
                        state.blender.features.editToolbar.families.flatMap { family ->
                            family.variants.map { variant ->
                                (variant.payload["tool"] ?: family.payload["tool"] ?: family.id).toString()
                            }
                        }.toSet() else emptySet()
                val catalogActions = state.blender.features.editCatalog.actionsFor(state.blender.selectionMode)
                    .filter { it.id !in excluded }
                editCatalogActions(catalogActions, vm)
            } else {
                emptyList()
            }
            val actions = quickActions(touchContext, vm, meshToolsChildren) {
                renameTarget = touchContext.objectName ?: state.blender.activeObject
            }
            QuickMenu(
                open = true,
                center = x to y,
                actions = actions,
                contextLabel = quickContextLabel(touchContext),
                onDismiss = dismiss,
            )
        }

        fileBrowserMode?.let { mode ->
            FileBrowserDialog(
                mode = mode,
                files = remoteFiles,
                initialName = state.file.name.takeIf { state.file.saved } ?: "sin-titulo.blend",
                onBrowse = vm::browseFiles,
                onSetDefault = vm::setDefaultFolder,
                onDismiss = { fileBrowserMode = null },
                onOpen = { path ->
                    fileBrowserMode = null
                    guardDiscard(PendingDiscard.Open(path) { vm.fileOpen(path) })
                },
                onSave = { folder, name ->
                    fileBrowserMode = null
                    vm.fileSaveAs(folder, name)
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

/** IDs de `edit_catalog` que ya viven directamente en el anillo de nivel 1. */
private val RADIAL_TOP_LEVEL_CATALOG_IDS =
    setOf("SELECT_LOOP", "SELECT_RING", "SELECT_LINKED", "DELETE", "HIDE")

/** Convierte el contrato opaco en filas, sin repartir nombres wire por la UI. */
private fun editCatalogActions(actions: List<EditCatalogAction>, vm: MainViewModel): List<QuickAction> =
    actions.map { action ->
        val variants = action.variants.filter { it.enabled }
        if (variants.isEmpty()) {
            QuickAction(action.label, AppIcons.editCatalog(action.id), enabled = action.enabled) {
                vm.editCatalogAction(action)
            }
        } else {
            // Tap conserva la primera variante contractual (REGION); el long-click
            // abre el selector compacto. Las incompatibles no se dibujan activas.
            val default = variants.first()
            QuickAction(
                action.label, AppIcons.editCatalog(action.id), enabled = action.enabled,
                opensChildrenOnClick = false,
                onClick = { vm.editCatalogAction(action, default.id) },
                children = variants.map { variant ->
                    QuickAction(variant.label, AppIcons.editCatalog(action.id), enabled = action.enabled) {
                        vm.editCatalogAction(action, variant.id)
                    }
                },
            )
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
 * Callbacks que la capa del viewport necesita, agrupados para poder pasarlos en un
 * único `remember`: así Compose puede saltarse la recomposición cuando nada cambie.
 */
class ViewportInput(
    val onDebug: (com.blendertablet.remote.model.InputDebug) -> Unit,
    val onToolGesture: (GesturePhase, Float, Float) -> Unit,
    val onToolPointer: (Float, Float) -> Unit,
    val onKnifeDrag: (GesturePhase, Float, Float) -> Unit,
    val onTweakDrag: (GesturePhase, Float, Float, Float, Float) -> Unit,
    val onCadGesture: (GesturePhase, Float, Float) -> Unit,
    val onSculptStroke: (GesturePhase, List<com.blendertablet.remote.model.SculptPoint>, Boolean, Boolean) -> Unit,
    /** Con vídeo activo: al soltar el gesto se refresca el estado. */
    val onViewGestureLive: (Gesture, GesturePhase, Float, Float, Float) -> Unit,
    /** Sin vídeo: solo navega, no hay nada que refrescar aún. */
    val onViewGesturePlain: (Gesture, GesturePhase, Float, Float, Float) -> Unit,
    val onTap: (Float, Float, Boolean) -> Unit,
    val onDoubleTap: () -> Unit,
    val onSurfaceAvailable: (android.view.Surface) -> Unit,
    val onSurfaceChanged: (android.view.Surface, Int, Int) -> Unit,
    val onSurfaceDestroyed: (android.view.Surface) -> Unit,
)

/**
 * El vídeo y la capa táctil. Ya no dibuja manipulador: los ejes viven en la barra de
 * transformación, donde son botones grandes con cifras en vez de flechas finas que
 * tapaban el objeto.
 *
 * Solo depende del frame y de callbacks estables: ni del estado general ni del
 * ViewModel, que la invalidaban a 60-120 Hz durante el toque.
 */
@Composable
private fun ViewportLayer(
    frame: android.graphics.Bitmap?,
    h264Active: Boolean,
    h264Size: Pair<Int, Int>?,
    input: ViewportInput,
    sculptEnabled: Boolean,
    sculptStylusOnly: Boolean,
    sculptRadius: Float,
    sculptPressureSize: Boolean,
    shapeTool: ShapeTool,
    fixedCircleRadius: Float?,
    cadDrawingEnabled: Boolean,
    cadOverlay: List<com.blendertablet.remote.model.CadOverlay>,
    knifeActive: Boolean,
    tweakActive: Boolean,
    longPressEnabled: Boolean,
    repeatTap: Boolean,
    independentTaps: Boolean,
    knifePoints: List<List<Pair<Float, Float>>>,
    snapCandidate: com.blendertablet.remote.model.SnapCandidate?,
    proportionalCircle: com.blendertablet.remote.model.ProportionalCircle?,
    cancelPickOnNavigation: Boolean,
    navigationOrbitEnabled: Boolean,
    onShape: (ShapeTool, Float, Float, Float, Float) -> Unit,
    onLongPress: (px: Float, py: Float, u: Float, v: Float) -> Unit,
) {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        if (h264Active) {
            val videoModifier = if (h264Size != null) {
                Modifier.aspectRatio(h264Size.first.toFloat() / h264Size.second.toFloat()).fillMaxSize()
            } else Modifier.fillMaxSize()
            Box(videoModifier) {
                VideoSurface(
                    modifier = Modifier.fillMaxSize(),
                    onSurfaceAvailable = input.onSurfaceAvailable,
                    onSurfaceChanged = input.onSurfaceChanged,
                    onSurfaceDestroyed = input.onSurfaceDestroyed,
                )
                InputSurface(
                    modifier = Modifier.fillMaxSize(),
                    onDebug = input.onDebug,
                    onToolGesture = input.onToolGesture,
                    onToolPointer = input.onToolPointer,
                    onViewGesture = input.onViewGestureLive,
                    onTap = input.onTap,
                    onDoubleTap = input.onDoubleTap,
                    repeatTap = repeatTap,
                    independentTaps = independentTaps,
                    sculptEnabled = sculptEnabled,
                    sculptStylusOnly = sculptStylusOnly,
                    sculptRadius = sculptRadius,
                    sculptPressureSize = sculptPressureSize,
                    onSculptStroke = input.onSculptStroke,
                    cadDrawingEnabled = cadDrawingEnabled,
                    onCadGesture = input.onCadGesture,
                    cadOverlay = cadOverlay,
                    knifeActive = knifeActive,
                    onKnifeDrag = input.onKnifeDrag,
                    tweakActive = tweakActive,
                    onTweakDrag = input.onTweakDrag,
                    longPressEnabled = longPressEnabled,
                    onLongPress = onLongPress,
                    shapeTool = shapeTool,
                    fixedCircleRadius = fixedCircleRadius,
                    navigationOrbitEnabled = navigationOrbitEnabled,
                    knifePoints = knifePoints,
                    snapCandidate = snapCandidate,
                    cancelPickOnNavigation = cancelPickOnNavigation,
                    proportionalCircle = proportionalCircle,
                    onShape = onShape,
                )
            }
            return@Box
        }
        if (frame == null) {
            EmptyViewport()
            InputSurface(
                modifier = Modifier.fillMaxSize(),
                onDebug = input.onDebug,
                onToolGesture = input.onToolGesture,
                onToolPointer = input.onToolPointer,
                onViewGesture = input.onViewGesturePlain,
                onTap = input.onTap,
                onDoubleTap = input.onDoubleTap,
                repeatTap = repeatTap,
                independentTaps = independentTaps,
                sculptEnabled = sculptEnabled,
                sculptStylusOnly = sculptStylusOnly,
                sculptRadius = sculptRadius,
                sculptPressureSize = sculptPressureSize,
                onSculptStroke = input.onSculptStroke,
                cadDrawingEnabled = cadDrawingEnabled,
                onCadGesture = input.onCadGesture,
                cadOverlay = cadOverlay,
                knifeActive = knifeActive,
                onKnifeDrag = input.onKnifeDrag,
                tweakActive = tweakActive,
                onTweakDrag = input.onTweakDrag,
                longPressEnabled = longPressEnabled,
                onLongPress = onLongPress,
                shapeTool = shapeTool,
                fixedCircleRadius = fixedCircleRadius,
                navigationOrbitEnabled = sculptEnabled && navigationOrbitEnabled,
                knifePoints = knifePoints,
                snapCandidate = snapCandidate,
                cancelPickOnNavigation = cancelPickOnNavigation,
                proportionalCircle = proportionalCircle,
                onShape = onShape,
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
            // El wrapper es barato pero no gratis: una vez por frame nuevo basta.
            val imageBitmap = remember(frame) { frame.asImageBitmap() }
            Image(
                bitmap = imageBitmap,
                contentDescription = "Viewport de Blender",
                modifier = Modifier.fillMaxSize(),
                contentScale = ContentScale.Fit,
                // El JPEG ya suaviza; interpolar otra vez emborrona las aristas.
                filterQuality = FilterQuality.None,
            )
            InputSurface(
                modifier = Modifier.fillMaxSize(),
                onDebug = input.onDebug,
                onToolGesture = input.onToolGesture,
                onToolPointer = input.onToolPointer,
                onViewGesture = input.onViewGestureLive,
                onTap = input.onTap,
                onDoubleTap = input.onDoubleTap,
                repeatTap = repeatTap,
                independentTaps = independentTaps,
                sculptEnabled = sculptEnabled,
                sculptStylusOnly = sculptStylusOnly,
                sculptRadius = sculptRadius,
                sculptPressureSize = sculptPressureSize,
                onSculptStroke = input.onSculptStroke,
                cadDrawingEnabled = cadDrawingEnabled,
                onCadGesture = input.onCadGesture,
                cadOverlay = cadOverlay,
                knifeActive = knifeActive,
                onKnifeDrag = input.onKnifeDrag,
                tweakActive = tweakActive,
                onTweakDrag = input.onTweakDrag,
                longPressEnabled = longPressEnabled,
                onLongPress = onLongPress,
                shapeTool = shapeTool,
                fixedCircleRadius = fixedCircleRadius,
                navigationOrbitEnabled = sculptEnabled && navigationOrbitEnabled,
                knifePoints = knifePoints,
                snapCandidate = snapCandidate,
                cancelPickOnNavigation = cancelPickOnNavigation,
                proportionalCircle = proportionalCircle,
                onShape = onShape,
            )
        }
    }
}

/** Las sesiones propietarias del viewport tienen prioridad total sobre el long-click. */
internal fun viewportLongPressEnabled(transformActive: Boolean, toolActive: Boolean): Boolean =
    !transformActive && !toolActive

/** Tweak navega con dos dedos y no debe perder viewport por un control redundante. */
internal fun navigationOrbitVisible(
    transformActive: Boolean,
    toolActive: Boolean,
    activeTool: ActiveTool,
): Boolean = (transformActive || toolActive) && activeTool != ActiveTool.TWEAK

@Composable
private fun EmptyViewport() {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text("SIN VÍDEO", color = Ink.Faint, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
        Spacer(Modifier.height(4.dp))
        Text("Arranca el servidor en Blender y conecta", color = Ink.Faint, fontSize = 12.sp)
    }
}

/**
 * Contenido del rail permanente: selección, transformaciones, herramientas Edit y
 * diagnóstico. Si crece más que la altura disponible conserva scroll propio.
 */
@Composable
private fun RailContent(
    state: AppUiState,
    session: TransformSession,
    toolSession: ToolSession,
    vm: MainViewModel,
) {
    val editable = state.blender.activeObject != null
    val inEdit = state.blender.mode == BlenderMode.EDIT

    RailLabel("HERRAMIENTA")
    IconAction(
        Icons.Default.Mouse, "Seleccionar",
        selected = state.activeTool == ActiveTool.SELECT && !session.active && !toolSession.active,
        onClick = vm::selectTool,
    )
    if (inEdit && state.blender.features.selectionTweak) {
        TweakToolButton(
            selected = state.activeTool == ActiveTool.TWEAK,
            enabled = true,
            vm = vm,
        )
    }
    IconAction(
        Icons.Default.OpenWith, "Mover",
        selected = isTransformToolSelected(state.activeTool, session, TransformMode.MOVE),
        enabled = editable,
        onClick = { vm.transformBegin(TransformMode.MOVE) },
    )
    IconAction(
        Icons.AutoMirrored.Filled.RotateRight, "Rotar",
        selected = isTransformToolSelected(state.activeTool, session, TransformMode.ROTATE),
        enabled = editable,
        onClick = { vm.transformBegin(TransformMode.ROTATE) },
    )
    IconAction(
        Icons.Default.AspectRatio, "Escalar",
        selected = isTransformToolSelected(state.activeTool, session, TransformMode.SCALE),
        enabled = editable,
        onClick = { vm.transformBegin(TransformMode.SCALE) },
    )
    // Barra de tools activas (edit_toolbar, B0/F1): Extrude, Inset, Loop Cut y Cut
    // agrupados con la lógica de Blender, en vez de duplicarlos en el catálogo
    // contextual. Un servidor sin la feature no la anuncia y no se dibuja nada aquí.
    if (inEdit && state.blender.features.editToolbar.available) {
        RailDivider()
        RailLabel("EDITAR")
        ToolbarFamilyButtons(state.blender.features.editToolbar.families, toolSession, state.toolbarVariant, state.blender.selectionMode, vm)
    }

    // El catálogo contextual toma propiedad de las operaciones topológicas. En un
    // servidor antiguo no existe y el rail histórico sigue íntegro.
    if (inEdit && !state.blender.features.editCatalog.available) {
        RailDivider()
        RailLabel("EDITAR")
        // Cada herramienta pide un tipo de elemento: Inset solo trabaja con caras y
        // Subdividir con aristas. Sin lo que necesita, el servidor respondería
        // `empty_selection`; se apaga el botón en vez de dejar que falle.
        val counts = state.blender.context
        for (tool in EditTool.entries) {
            if (tool == EditTool.ALIGN) continue
            if (counts.availableTools.isNotEmpty() && ActiveTool.valueOf(tool.name) !in counts.availableTools) continue
            val ready = when (tool) {
                EditTool.EXTRUDE -> counts.countFor(state.blender.selectionMode) > 0
                EditTool.BEVEL -> counts.countFor(state.blender.selectionMode) > 0
                EditTool.INSET -> counts.selectionCounts.faces > 0
                EditTool.SUBDIVIDE -> counts.selectionCounts.edges > 0
                EditTool.REVOLVE -> counts.selectionCounts.verts > 0
                EditTool.SWEEP -> counts.selectionCounts.edges > 0
                EditTool.LOOP_CUT -> true // sin arista queda armada y el próximo tap la elige
                EditTool.BRIDGE_EDGE_LOOPS -> counts.selectionCounts.edges >= 6
                EditTool.KNIFE -> true // no exige selección previa
                // Bisect es de edit_toolbar (B4): un servidor sin esa feature no lo
                // anuncia en available_tools y este rail legacy nunca lo ofrece.
                EditTool.BISECT -> true
                EditTool.ALIGN -> false
            }
            IconAction(
                icon = AppIcons.editTool(tool),
                description = if (ready) tool.label else "${tool.label} · ${tool.requirement}",
                selected = toolSession.active && toolSession.tool == tool ||
                    (tool == EditTool.LOOP_CUT && state.activeTool == ActiveTool.LOOP_CUT && !toolSession.active),
                enabled = ready || toolSession.active,
                onClick = { vm.beginEditTool(tool) },
            )
        }
    }

    RailDivider()
    IconAction(Icons.Default.BugReport, "Diagnóstico", selected = state.debugVisible, onClick = vm::toggleDebug)
}

/** Qué borra `mesh.delete` según el submodo de selección. */
private fun deleteWhat(mode: SelectionMode): String = when (mode) {
    SelectionMode.VERTEX -> "VERTS"
    SelectionMode.EDGE -> "EDGES"
    SelectionMode.FACE -> "FACES"
}

/**
 * Menú de la pulsación larga: el mismo anillo radial en Object y en Edit (plan 001).
 *
 * Qué acciones salen lo decide [RadialMenu.actionsFor] a partir de lo que hay bajo el
 * dedo; aquí solo se les pone icono y se les conecta el comando. Esa separación es lo
 * que permite comprobar en un test que el long click no invade el rail ni el top: la
 * lista de [ActionId] es dato, no interfaz.
 */
private fun quickActions(
    context: TouchContext,
    vm: MainViewModel,
    /** Catálogo de vértice/arista/cara ya filtrado y sin duplicar el anillo (F1/F4). */
    meshToolsChildren: List<QuickAction>,
    selectionOnly: Boolean = false,
    onRename: () -> Unit,
): List<QuickAction> = (if (selectionOnly) RadialMenu.selectionActions(context) else RadialMenu.actionsFor(context))
    // Sin catálogo del servidor (edit_catalog no disponible) no hay nada que abrir.
    .filter { it != ActionId.EDIT_MESH_TOOLS || meshToolsChildren.isNotEmpty() }
    .map { id ->
    val label = SurfaceCatalog.labelOf(id, context)
    when (id) {
        // El catálogo Add completo, antes en el menú Objeto del top: en el vacío del
        // long-click está donde se le necesita, y el panel flotante lo ordena por
        // categorías con salida por la X de la cabecera. Al ser un panel vertical con
        // scroll (plan 001), Malla no necesita paginarse aunque tenga diez primitivas.
        ActionId.ADD_OBJECT -> QuickAction(
            label, Icons.Default.Add, tint = Ink.Accent,
            children = AddCategory.entries.map { category ->
                val items = AddObject.of(category)
                // Texto y Cámara son categorías de un solo elemento: un subnivel con
                // una entrada sería un clic de más para nada.
                if (items.size == 1) {
                    QuickAction(items.first().label, AppIcons.addCategory(category)) { vm.addPrimitive(items.first()) }
                } else {
                    QuickAction(
                        category.label, AppIcons.addCategory(category),
                        children = items.map { item ->
                            QuickAction(item.label, AppIcons.addCategory(category)) { vm.addPrimitive(item) }
                        },
                    )
                }
            },
        )
        // Separar/Split/Normales/Bevel/Subdivide/Bridge/Borrar: el catálogo del
        // servidor, ya sin lo que vive en el anillo (Loop/Ring/Ocultar) ni en la
        // barra izquierda (Extrude/Inset/Loop Cut/Cut).
        ActionId.EDIT_MESH_TOOLS -> QuickAction(label, AppIcons.action(id), children = meshToolsChildren)
        ActionId.EDIT_SELECTION_TOOLS -> QuickAction(label, AppIcons.action(id),
            children = quickActions(context, vm, emptyList(), selectionOnly = true, onRename = onRename))
        ActionId.SELECT_ALL -> QuickAction(label, Icons.Default.SelectAll) { vm.selectAll() }
        ActionId.DESELECT_ALL -> QuickAction(label, Icons.Default.Deselect) { vm.deselectAll() }
        // Caja y Círculo arman el arrastre por forma y cierran el menú: el siguiente
        // arrastre de un dedo dibuja la forma en vez de orbitar.
        ActionId.TOOL_BOX -> QuickAction(label, Icons.Default.SelectAll) { vm.armShapeTool(ShapeTool.BOX) }
        ActionId.TOOL_CIRCLE -> QuickAction(label, Icons.Default.BlurOn) { vm.armShapeTool(ShapeTool.CIRCLE) }
        ActionId.SELECT_INVERT -> QuickAction(label, Icons.Default.Flip) { vm.invertSelection() }
        ActionId.SELECT_UNDER -> QuickAction(label, Icons.Default.TouchApp) {
            context.objectName?.let { vm.selectObject(it, add = false) }
        }
        ActionId.SELECT_ADD_UNDER -> QuickAction(label, Icons.Default.LibraryAdd) {
            context.objectName?.let { vm.selectObject(it, add = true) }
        }
        ActionId.SELECT_LOOP -> QuickAction(label, Icons.Default.Timeline) { vm.selectLoop() }
        ActionId.SELECT_RING -> QuickAction(label, Icons.Default.Rowing) { vm.selectRing() }
        ActionId.SELECT_LINKED -> QuickAction(label, Icons.Default.Hub) { vm.selectLinked() }
        ActionId.HIDE_OBJECT -> QuickAction(label, Icons.Default.VisibilityOff) { vm.hideObject(context.objectName) }
        // Iconos por cara del interruptor: el rótulo dice qué hará y el icono lo repite
        // sin leer. Suave = esfera, plano = facetas; aislar = enfocar, ver todo = salir.
        ActionId.SHADE_OBJECT -> QuickAction(
            label,
            AppIcons.shading(context.shadeSmooth),
        ) { vm.toggleObjectShading(context.objectName) }
        ActionId.VIEW_LOCAL -> QuickAction(
            label,
            AppIcons.localView(context.localView),
        ) { vm.toggleLocalView() }
        ActionId.HIDE_GEOMETRY -> QuickAction(label, Icons.Default.VisibilityOff) { vm.hideSelection() }
        ActionId.DUPLICATE -> if (context.mode == BlenderMode.EDIT) {
            QuickAction("Duplicar selección", AppIcons.Duplicate) { vm.runDuplicateVariant(false) }
        } else {
            val linked = vm.uiState.value.duplicateLinked
            QuickAction(
                if (linked) "Duplicar enlazado" else "Duplicar",
                if (linked) AppIcons.DuplicateLinked else AppIcons.Duplicate,
                opensChildrenOnClick = false,
                onClick = { vm.runDuplicateVariant(linked) },
                children = listOf(
                    QuickAction("Duplicar", AppIcons.Duplicate) { vm.runDuplicateVariant(false) },
                    QuickAction("Duplicar enlazado", AppIcons.DuplicateLinked) { vm.runDuplicateVariant(true) },
                ),
            )
        }
        ActionId.RENAME -> QuickAction(label, Icons.Default.Edit, onClick = onRename)
        ActionId.DISSOLVE -> QuickAction(label, Icons.Default.DeleteSweep) {
            vm.meshDissolve(deleteWhat(context.selectionMode))
        }
        ActionId.APPLY_TRANSFORMS -> QuickAction(
            label, Icons.Default.Transform,
            children = listOf(
                QuickAction("Posición", Icons.Default.OpenWith, onClick = { vm.applyTransform(true, false, false) }),
                QuickAction("Rotación", Icons.AutoMirrored.Filled.RotateRight, onClick = { vm.applyTransform(false, true, false) }),
                QuickAction("Escala", Icons.Default.AspectRatio, onClick = { vm.applyTransform(false, false, true) }),
                QuickAction("Todas", AppIcons.action(ActionId.APPLY_TRANSFORMS), onClick = { vm.applyTransform(true, true, true) }),
            ),
        )
        ActionId.PLACE_OBJECT -> QuickAction(
            label, AppIcons.action(id),
            children = listOf(
                QuickAction("Alinear caras", AppIcons.editTool(EditTool.ALIGN)) { vm.beginAlignment(context.objectName) },
                QuickAction("Origen al cursor", Icons.Default.MyLocation) { vm.snap(SnapAction.ORIGIN_TO_CURSOR) },
                QuickAction("Origen a geometría", Icons.Default.CenterFocusStrong) { vm.snap(SnapAction.ORIGIN_TO_GEOMETRY) },
                QuickAction("Origen al centro de masas", Icons.Default.Adjust) { vm.snap(SnapAction.ORIGIN_TO_MASS) },
            ),
        )
        // Borrar es el destructivo: rojo y siempre el último del anillo.
        ActionId.DELETE -> if (context.mode == BlenderMode.EDIT) QuickAction(
            "Borrar / disolver", Icons.Default.Delete, tint = Ink.Bad,
            children = listOf(
                QuickAction("Borrar ${context.selectionMode.name.lowercase()}", Icons.Default.Delete, tint = Ink.Bad) {
                    vm.meshDelete(deleteWhat(context.selectionMode))
                },
                QuickAction("Disolver ${context.selectionMode.name.lowercase()}", Icons.Default.DeleteSweep) {
                    vm.meshDissolve(deleteWhat(context.selectionMode))
                },
            ),
        ) else QuickAction(label, Icons.Default.Delete, tint = Ink.Bad) { vm.delete() }
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
private fun CircleRadiusBar(
    selected: Float?,
    onRadius: (Float?) -> Unit,
    modifier: Modifier = Modifier,
) {
    FloatingPanel(modifier) {
        Row(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("Radio", color = Ink.Muted, fontSize = 11.sp)
            PillButton("Libre", selected = selected == null) { onRadius(null) }
            listOf(.05f to "5%", .10f to "10%", .20f to "20%", .30f to "30%").forEach { (radius, label) ->
                PillButton(label, selected = selected == radius) { onRadius(radius) }
            }
        }
    }
}

@Composable
private fun ErrorToast(message: String, modifier: Modifier = Modifier) {
    FloatingPanel(modifier) {
        Text(message, color = Ink.Bad, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 4.dp))
    }
}

@Composable
private fun NoticeToast(message: String, modifier: Modifier = Modifier) {
    FloatingPanel(modifier) {
        Text(message, color = Ink.Accent, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 4.dp))
    }
}

@Composable
private fun DebugOverlay(vm: MainViewModel, mode: BlenderMode, modifier: Modifier = Modifier) {
    // Recolecta el flujo de entrada aquí, no en Workspace: a 60-120 Hz solo debe
    // recomponerse este panel, y únicamente cuando el diagnóstico está abierto.
    val input by vm.inputDebug.collectAsStateWithLifecycle()
    FloatingPanel(modifier) {
        Column(verticalArrangement = Arrangement.spacedBy(1.dp)) {
            Text("dedos ${input.pointerCount}  ·  ${input.tool}", color = Ink.Muted, fontSize = 11.sp)
            Text("presión ${"%.2f".format(input.pressure)}", color = Ink.Faint, fontSize = 11.sp)
            Text("x ${input.x.toInt()}  y ${input.y.toInt()}", color = Ink.Faint, fontSize = 11.sp)
            Text("modo $mode", color = Ink.Faint, fontSize = 11.sp)
        }
    }
}
