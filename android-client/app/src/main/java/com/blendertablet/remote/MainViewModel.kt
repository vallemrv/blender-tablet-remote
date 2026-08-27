package com.blendertablet.remote

import android.app.Application
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.blendertablet.remote.data.ConnectionPreferences
import com.blendertablet.remote.data.ConnectionSettings
import com.blendertablet.remote.model.ActiveTool
import com.blendertablet.remote.model.Axis
import com.blendertablet.remote.model.AppUiState
import com.blendertablet.remote.model.BlenderMode
import com.blendertablet.remote.model.Constraint
import com.blendertablet.remote.model.EditTool
import com.blendertablet.remote.model.EditFooterAction
import com.blendertablet.remote.model.EditCatalogAction
import com.blendertablet.remote.model.EditToolbarFamily
import com.blendertablet.remote.model.Gesture
import com.blendertablet.remote.model.GesturePhase
import com.blendertablet.remote.model.InputDebug
import com.blendertablet.remote.model.AddObject
import com.blendertablet.remote.model.Orientation
import com.blendertablet.remote.model.Projection
import com.blendertablet.remote.model.SelectionMode
import com.blendertablet.remote.model.SelectionOp
import com.blendertablet.remote.model.ShapeTool
import com.blendertablet.remote.model.SnapAction
import com.blendertablet.remote.model.SnapType
import com.blendertablet.remote.model.ToolSession
import com.blendertablet.remote.model.TouchContext
import com.blendertablet.remote.model.TouchProbe
import com.blendertablet.remote.model.TransformMode
import com.blendertablet.remote.model.TransformSession
import com.blendertablet.remote.model.ValueMode
import com.blendertablet.remote.model.stepsFor
import com.blendertablet.remote.network.RemoteBlenderClient
import com.blendertablet.remote.network.StreamStats
import com.blendertablet.remote.network.ViewportFrame
import com.blendertablet.remote.network.ViewportStream
import com.blendertablet.remote.network.H264Framing
import com.blendertablet.remote.network.H264ViewportStream
import android.view.Surface
import com.blendertablet.remote.network.WebSocketRemoteBlenderClient
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

class MainViewModel(application: Application) : AndroidViewModel(application) {
    private val client: RemoteBlenderClient = WebSocketRemoteBlenderClient(viewModelScope)
    private val local = MutableStateFlow(AppUiState())
    private val preferences = ConnectionPreferences(application)
    private val stream = ViewportStream(viewModelScope)
    private var currentStreamEndpoint: com.blendertablet.remote.network.StreamEndpoint? = null
    private val _h264Active = MutableStateFlow(false)
    val h264Active: StateFlow<Boolean> = _h264Active
    private val h264Stream = H264ViewportStream(viewModelScope) { fallbackToMjpeg() }
    val h264Size = h264Stream.size
    private var loopCutArmed = false
    // Debe inicializarse antes de `init`: StateFlow emite su valor actual en cuanto
    // empieza el collect y Main.immediate puede ejecutar esa emisión durante el
    // propio constructor del ViewModel.
    private val _knifeScreenPoints = MutableStateFlow<List<Pair<Float, Float>>>(emptyList())
    val knifeScreenPoints: StateFlow<List<Pair<Float, Float>>> = _knifeScreenPoints.asStateFlow()
    private val connectivity =
        application.getSystemService(ConnectivityManager::class.java)

    val settings: StateFlow<ConnectionSettings> = preferences.settings

    /** Hay datos guardados: el diálogo no tiene que salir al arrancar. */
    val hasSavedConnection: Boolean get() = preferences.current.isComplete

    val viewportFrame: StateFlow<ViewportFrame?> = stream.frame
    val streamStats: StateFlow<StreamStats> = stream.stats

    private val remote = combine(
        client.connection, client.state, client.errors, client.retryAttempt,
    ) { connection, blender, error, retryAttempt ->
        AppUiState(connection = connection, blender = blender, error = error, retryAttempt = retryAttempt)
    }

    private val document = combine(client.file, client.recentFiles, ::Pair)

    val uiState = combine(local, remote, document) { ui, net, (file, recent) ->
        ui.copy(
            connection = net.connection,
            blender = net.blender,
            error = net.error,
            retryAttempt = net.retryAttempt,
            file = file,
            recentFiles = recent,
        )
    }
        // Dos emisiones con el mismo contenido no deben recomponer nada: el servidor
        // manda scene.changed con generosidad y AppUiState compara por valor.
        .distinctUntilChanged()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), AppUiState())

    /**
     * Al recuperar la red hay que reintentar ya: el backoff puede estar en una
     * espera larga y sería absurdo tener WiFi y seguir esperando 30 segundos.
     */
    private val networkCallback = object : ConnectivityManager.NetworkCallback() {
        override fun onAvailable(network: Network) = client.retryNow()
    }

    init {
        viewModelScope.launch {
            client.state.collect { state ->
                if (loopCutArmed && state.mode == BlenderMode.EDIT && state.context.selectionCounts.edges > 0) {
                    loopCutArmed = false
                    client.toolBegin(EditTool.LOOP_CUT, toolDefaultParameters(EditTool.LOOP_CUT))
                }
            }
        }
        // Colocación por toque: el sondeo responde con la arista y el factor, y
        // con ellos arranca la sesión donde cayó el dedo. Un sondeo fallido
        // simplemente deja el hint vivo para el próximo toque.
        viewModelScope.launch {
            client.loopProbe.collect { probe ->
                if (probe != null && probe.hit && probe.edge >= 0) {
                    val awaiting = local.value.loopCutAwaitingTap
                    if (awaiting && !client.toolSession.value.active) {
                        local.update { it.copy(loopCutAwaitingTap = false) }
                        client.clearLoopProbe()
                        client.toolBegin(
                            EditTool.LOOP_CUT,
                            toolDefaultParameters(EditTool.LOOP_CUT) +
                                mapOf("edge" to probe.edge.toDouble(), "factor" to probe.factor),
                        )
                    }
                }
            }
        }
        // El puerto del vídeo lo anuncia el servidor en el "hello": el usuario solo
        // configura el de control y el vídeo se engancha solo (§63).
        viewModelScope.launch {
            client.toolSession.collect { session ->
                // Reconciliar el overlay del Knife contra el servidor: si un toque
                // falló (miss) o se quitó un punto, el contador no crece y se recorta
                // la lista optimista.
                val count = if (session.tool == EditTool.KNIFE) session.points.size else 0
                if (session.tool != EditTool.KNIFE) {
                    if (_knifeScreenPoints.value.isNotEmpty()) _knifeScreenPoints.value = emptyList()
                } else if (_knifeScreenPoints.value.size > count) {
                    _knifeScreenPoints.value = _knifeScreenPoints.value.take(count)
                }
                // Bisect arma el mismo mecanismo de "un dedo dibuja" que B/C (F4): un
                // dedo traza la línea de corte en vez de orbitar, mientras la tool
                // esté armada o activa. Se desarma solo al salir de Bisect, sin tocar
                // una caja/círculo que el usuario hubiera armado a mano.
                val bisectDrawing = (session.armed || session.active) && session.tool == EditTool.BISECT
                if (bisectDrawing && local.value.shapeTool != ShapeTool.LINE) {
                    local.update { it.copy(shapeTool = ShapeTool.LINE) }
                } else if (!bisectDrawing && local.value.shapeTool == ShapeTool.LINE) {
                    local.update { it.copy(shapeTool = ShapeTool.NONE) }
                }
            }
        }
        viewModelScope.launch {
            client.streamEndpoint.collect { endpoint ->
                currentStreamEndpoint = endpoint
                if (endpoint == null) {
                    h264Stream.stopTransport(); stream.stop(); _h264Active.value = false
                } else if (endpoint.format == "h264" && endpoint.framing == H264Framing.NAME) {
                    stream.stop(); _h264Active.value = true; h264Stream.start(endpoint)
                } else {
                    h264Stream.stopTransport(); _h264Active.value = false
                    stream.start(endpoint.host, endpoint.port, endpoint.token, endpoint.path)
                }
            }
        }
        // Recuperación tras un fallback a MJPEG (§ fallbackToMjpeg): si h264Stream
        // vuelve a decodificar frames de verdad -algo solo posible si una Surface
        // nueva reabrió la conexión- se apaga el MJPEG y se vuelve a H.264.
        viewModelScope.launch {
            h264Stream.size.collect { size ->
                if (size != null && !_h264Active.value && currentStreamEndpoint?.format == "h264") {
                    stream.stop()
                    _h264Active.value = true
                }
            }
        }

        connectivity?.registerNetworkCallback(
            NetworkRequest.Builder()
                .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                .build(),
            networkCallback,
        )

        val saved = preferences.current
        if (saved.isComplete && saved.autoConnect) {
            client.connect(saved.host, saved.port, saved.token)
        }
    }

    /** Guarda las preferencias y aplica el destino nuevo de inmediato. */
    fun saveSettings(settings: ConnectionSettings) {
        preferences.save(settings)
        if (settings.isComplete) client.connect(settings.host, settings.port, settings.token)
        else client.disconnect()
    }

    /**
     * La app vuelve a primer plano. Si el sistema mató el socket mientras estaba
     * detrás, esto lo recupera sin que el usuario se entere; si sigue viva, no hace
     * nada.
     */
    fun onForeground() = client.retryNow()

    fun disconnect() {
        h264Stream.stopTransport()
        stream.stop()
        client.disconnect()
    }

    /** El toast de error se auto-descarta: la UI lo limpia a los ~5 s. */
    fun clearError() = client.clearError()

    fun attachVideoSurface(surface: Surface) = h264Stream.attachSurface(surface)
    fun detachVideoSurface() = h264Stream.detachSurface()

    /**
     * H.264 se rindió tras varios reintentos (§ "el vídeo pierde calidad al hacer
     * resize"). No es definitivo: [h264Stream] conserva el endpoint deseado, así que
     * la próxima [attachVideoSurface] (el siguiente resize, o volver a primer plano)
     * puede recuperarlo solo — ver el collector de `h264Stream.size` en `init`.
     */
    private fun fallbackToMjpeg() {
        val endpoint = currentStreamEndpoint ?: return
        val alternative = endpoint.alternatives.firstOrNull { it.format == "mjpeg" } ?: return
        h264Stream.pauseForFallback()
        _h264Active.value = false
        stream.start(endpoint.host, endpoint.port, endpoint.token, alternative.path)
    }
    /** Volver a Seleccionar cierra cualquier sesión (transformación o herramienta). */
    fun selectTool() {
        closeSessions()
        local.update { it.copy(activeTool = ActiveTool.SELECT, shapeTool = ShapeTool.NONE) }
    }
    /**
     * Cambiar de modo o de submodo invalida lo que hubiera abierto: una extrusión
     * de caras no significa nada en cuanto se pasa a vértices, y el servidor
     * respondería `session_invalidated` a mitad de un arrastre. Se descarta antes de
     * cambiar, que es la salida no destructiva.
     */
    fun setMode(mode: BlenderMode) {
        closeSessions()
        local.update { it.copy(shapeTool = ShapeTool.NONE) }
        client.setMode(mode)
    }

    fun setSelectionMode(mode: SelectionMode) {
        closeSessions()
        local.update { it.copy(shapeTool = ShapeTool.NONE) }
        client.setSelectionMode(mode)
    }

    private fun closeSessions() {
        if (client.transformSession.value.active) client.transformCancel()
        if (client.toolSession.value.active) client.toolCancel()
        loopCutArmed = false
        local.update { it.copy(loopCutAwaitingTap = false) }
    }
    fun toggleControls() = local.update { it.copy(controlsVisible = !it.controlsVisible) }
    fun toggleDebug() = local.update { it.copy(debugVisible = !it.debugVisible) }

    /**
     * Telemetría del toque, fuera de [AppUiState] a propósito: llega a la frecuencia
     * del digitizador (60-120 Hz) y meterla en el estado general recompondría toda la
     * interfaz por cada MotionEvent. Solo la lee el overlay de diagnóstico, y solo
     * cuando está visible.
     */
    private val _inputDebug = MutableStateFlow(InputDebug())
    val inputDebug: StateFlow<InputDebug> = _inputDebug.asStateFlow()

    fun updateInput(input: InputDebug) {
        _inputDebug.value = input
    }
    fun undo() = client.undo()
    fun redo() = client.redo()
    fun delete() = client.delete()
    fun duplicate() = client.duplicate()
    fun frameSelected() = client.frameSelected()
    /**
     * Un toque en el viewport. Normalmente selecciona, pero con una transformación
     * abierta y un snap geométrico elegido significa "pega el movimiento a esto":
     * seleccionar a mitad de un desplazamiento no tendría sentido, y tocar el destino
     * es la forma corta de decir a dónde va.
     */
    fun pick(u: Float, v: Float, stylus: Boolean = false) {
        // Knife activo: el toque coloca un punto de la polilínea.
        val knife = client.toolSession.value
        if (knife.active && knife.tool == EditTool.KNIFE) {
            knifeTap(u, v)
            return
        }
        if (knife.active && knife.snapType.geometric) {
            client.toolSnapCandidate(u.toDouble(), v.toDouble(), knife.snapType, lock = true)
            return
        }
        // Loop Cut activo: el toque COLOCA el corte (primer toque) o lo re-ubica
        // (sesión ya abierta). Es el hover+click del Ctrl+R, con el dedo.
        if (local.value.activeTool == ActiveTool.LOOP_CUT) {
            val blender = uiState.value.blender
            if (blender.mode == BlenderMode.EDIT) {
                if (client.toolSession.value.active) {
                    client.toolLoopPick(u.toDouble(), v.toDouble())
                    return
                }
                if (local.value.loopCutAwaitingTap) {
                    client.meshLoopProbe(u.toDouble(), v.toDouble())
                    return
                }
            }
        }
        val session = client.transformSession.value
        if (session.active && session.mode == TransformMode.MOVE && session.snapType.geometric) {
            client.transformSnapCandidate(u.toDouble(), v.toDouble(), session.snapType)
            return
        }
        if (session.active) return
        // El pen apunta con precisión: un radio menor evita saltar al elemento vecino.
        // El dedo conserva una diana más grande y cómoda.
        client.pick(u.toDouble(), v.toDouble(), if (stylus) 0.018 else 0.045, local.value.selectionOp)
    }
    fun requestState() = client.requestState()
    fun addPrimitive(primitive: AddObject) = client.addPrimitive(primitive)
    fun snap(action: SnapAction) = client.snap(action)

    /** Navegación por vistas estándar y proyección (footer de vistas). */
    fun viewAxis(name: String) = client.viewAxis(name)
    fun viewOrbitStep(dx: Float, dy: Float) {
        client.gesture(Gesture.ORBIT, GesturePhase.BEGIN)
        client.gesture(Gesture.ORBIT, GesturePhase.UPDATE, dx.toDouble(), dy.toDouble())
        client.gesture(Gesture.ORBIT, GesturePhase.END)
    }
    fun viewZoomStep(factor: Float) {
        client.gesture(Gesture.ZOOM, GesturePhase.BEGIN)
        client.gesture(Gesture.ZOOM, GesturePhase.UPDATE, factor = factor.toDouble())
        client.gesture(Gesture.ZOOM, GesturePhase.END)
    }
    fun viewFrameAll() = client.viewFrameAll()
    fun viewPerspective(projection: Projection) = client.viewPerspective(projection)

    /** Wireframe/sólido del viewport capturado (botón de la barra superior). */
    fun toggleShading() = client.viewShading("TOGGLE")

    /** Aísla la selección (el `/` del footer de vistas). Optimista: no hay push. */
    fun toggleLocalView() {
        val next = !local.value.localViewActive
        local.update { it.copy(localViewActive = next) }
        client.viewLocal(next)
    }

    fun selectMore() = client.selectMore()
    fun selectLess() = client.selectLess()

    /**
     * Ctrl/Alt: fijan la operación de selección del siguiente tap/caja/círculo.
     * Pulsar el mismo lo desarma; pulsar el otro cambia el modificador.
     */
    fun toggleSelectionOp(op: SelectionOp) {
        local.update { it.copy(selectionOp = if (it.selectionOp == op) SelectionOp.SET else op) }
    }

    /** B/C: arma/desarma la herramienta de arrastre por forma. */
    fun toggleShapeTool(tool: ShapeTool) {
        local.update { it.copy(shapeTool = if (it.shapeTool == tool) ShapeTool.NONE else tool) }
    }

    /** El menú radial siempre arma B/C; repetir el botón nunca debe desarmarla. */
    fun armShapeTool(tool: ShapeTool) {
        require(tool == ShapeTool.BOX || tool == ShapeTool.CIRCLE)
        local.update { it.copy(shapeTool = tool) }
    }

    /**
     * La forma terminada de dibujar en el viewport. Box recibe las dos esquinas;
     * Circle el centro y un punto del borde, del que sale el radio. La operación
     * respeta el modificador Ctrl/Alt fijado.
     */
    /**
     * La forma terminada de dibujar en el viewport. Box recibe las dos esquinas;
     * Circle el centro y un punto del borde, del que sale el radio. La operación
     * respeta el modificador Ctrl/Alt fijado.
     *
     * Es de UN SOLO USO: tras dibujar y seleccionar, la herramienta se desarma sola
     * y el siguiente gesto vuelve a ser navegación/selección normal. Para otra caja
     * hay que rearmarla desde el long-click (B/C).
     */
    fun shapeSelect(shape: ShapeTool, u0: Float, v0: Float, u1: Float, v1: Float) {
        // Bisect es la excepción: no es selección y no se desarma sola tras un
        // arrastre (F4 permite redibujar la línea mientras la sesión sigue viva). El
        // watcher de [toolSession] es quien la desarma al salir de Bisect.
        if (shape == ShapeTool.LINE) {
            bisectDragLine(u0, v0, u1, v1)
            return
        }
        val op = local.value.selectionOp
        when (shape) {
            ShapeTool.BOX -> client.boxSelect(u0.toDouble(), v0.toDouble(), u1.toDouble(), v1.toDouble(), op)
            ShapeTool.CIRCLE -> client.circleSelect(
                u0.toDouble(), v0.toDouble(),
                Math.hypot((u1 - u0).toDouble(), (v1 - v0).toDouble()),
                op,
            )
            ShapeTool.NONE, ShapeTool.LINE -> Unit
        }
        local.update { it.copy(shapeTool = ShapeTool.NONE) }
    }

    /** Acciones contextuales de selección (Edit y Object). */
    fun selectAll() = client.selectAll(true)
    fun deselectAll() = client.selectAll(false)
    fun invertSelection() = client.invertSelection()
    fun hideSelection() = client.hideSelection()
    fun revealSelection() = client.revealSelection()
    fun hideObject(name: String? = null) = client.hideObjects(name?.let(::listOf))
    fun revealObject(name: String) = client.revealObjects(listOf(name))
    fun revealAllObjects() = client.revealObjects()
    fun applyTransform(location: Boolean, rotation: Boolean, scale: Boolean) =
        client.transformApply(location, rotation, scale)
    fun openModifiers() {
        client.requestModifierOptions()
        // La lista de objetos (para el picker de operando) no viene en el snapshot
        // habitual: se pide aparte al abrir el inspector.
        client.listObjects()
    }
    fun addModifier(type: String, parameters: Map<String, Any?> = emptyMap()) = client.modifierAdd(type, parameters)
    fun removeModifier(name: String) = client.modifierRemove(name)
    fun moveModifier(name: String, index: Int) = client.modifierMove(name, index)
    fun setModifier(name: String, key: String, value: Any?) = client.modifierSet(name, mapOf(key to value))
    fun toggleModifier(name: String, viewport: Boolean? = null, render: Boolean? = null) = client.modifierToggle(name, viewport, render)
    fun applyModifier(name: String) = client.modifierApply(name)
    fun selectLoop() = client.selectLoop()
    fun selectRing() = client.selectRing()
    fun selectObject(name: String, add: Boolean) = client.selectObject(name, add)
    fun meshDelete(what: String) = client.meshDelete(what)
    fun meshDissolve(what: String) = client.meshDissolve(what)
    fun duplicateLinked() = client.duplicateLinked()
    fun rename(newName: String, target: String? = null) = client.rename(newName, target)

    /**
     * Qué hay bajo el dedo, para que el menú radial responda a eso y no solo al modo.
     * En Edit se pregunta por el submodo activo; en Object, por la cara, que es lo
     * que identifica el objeto tocado.
     */
    val touchProbe: StateFlow<TouchProbe?> = client.touchProbe

    fun probeTouch(u: Float, v: Float) {
        val state = uiState.value.blender
        val type = if (state.mode == BlenderMode.EDIT) {
            when (state.selectionMode) {
                SelectionMode.VERTEX -> SnapType.VERTEX
                SelectionMode.EDGE -> SnapType.EDGE
                SelectionMode.FACE -> SnapType.FACE
            }
        } else {
            SnapType.FACE
        }
        client.probeTouch(u.toDouble(), v.toDouble(), type)
    }

    fun clearProbe() = client.clearProbe()

    /** El contexto del menú radial: modo, submodo y lo que devolvió el sondeo. */
    fun touchContext(probe: TouchProbe?): TouchContext {
        val blender = uiState.value.blender
        val objectName = probe?.objectName
        return TouchContext(
            mode = blender.mode,
            selectionMode = blender.selectionMode,
            hit = probe?.hit == true,
            objectName = objectName,
            objectSelected = objectName != null && objectName in blender.selectedObjects,
            hasSelection = blender.context.hasSelection(blender.mode, blender.selectionMode),
        )
    }

    /** Herramientas paramétricas de Edit Mode. */
    fun beginEditTool(tool: EditTool) {
        if (client.transformSession.value.active) client.transformCancel()
        local.update { it.copy(activeTool = ActiveTool.valueOf(tool.name), loopCutAwaitingTap = false) }
        if (tool == EditTool.LOOP_CUT && client.state.value.context.selectionCounts.edges == 0) {
            if (client.state.value.features.loopCutPick) {
                // Sin arista elegida, el PRÓXIMO TOQUE en la malla coloca el corte:
                // el flujo Ctrl+R de la tablet. No hay que seleccionar nada antes.
                local.update { it.copy(loopCutAwaitingTap = true) }
            } else {
                // Servidor sin colocación por toque: se mantiene el flujo histórico
                // de seleccionar una arista y esperar el snapshot.
                loopCutArmed = true
                client.setSelectionMode(SelectionMode.EDGE)
            }
        } else client.toolBegin(tool, toolDefaultParameters(tool))
    }

    fun setToolParameter(key: String, value: Any?) =
        client.toolParameter(mapOf(key to value))

    fun nudgeTool(delta: Double) = client.toolNudge(delta)

    /** Seguimiento absoluto del dedo para snap geométrico durante el arrastre. */
    fun toolPointer(u: Float, v: Float) {
        val tool = client.toolSession.value
        if (tool.active && tool.snapType.geometric) {
            client.toolSnapCandidate(u.toDouble(), v.toDouble(), tool.snapType, lock = false)
            return
        }
        val transform = client.transformSession.value
        if (transform.active && transform.mode == TransformMode.MOVE && transform.snapType.geometric) {
            client.transformSnapCandidate(u.toDouble(), v.toDouble(), transform.snapType, lock = false)
        }
    }

    /**
     * Único punto de enlace de los atajos Edit. B3--B8 aún no fijan sus comandos
     * wire: mantenerlo deliberadamente sin envío evita que la UI invente protocolos.
     */
    fun editFooterAction(action: EditFooterAction) {
        val id = when (action) {
            EditFooterAction.MAKE_EDGE_FACE -> "MAKE_EDGE_FACE"
            EditFooterAction.KNIFE -> "KNIFE"
            EditFooterAction.SEPARATE -> "SEPARATE"
            EditFooterAction.SPLIT -> "SPLIT"
            EditFooterAction.NORMALS -> return
            EditFooterAction.NORMALS_OUTSIDE -> "RECALCULATE_NORMALS_OUTSIDE"
            EditFooterAction.NORMALS_INSIDE -> "RECALCULATE_NORMALS_INSIDE"
            EditFooterAction.NORMALS_FLIP -> "FLIP_NORMALS"
        }
        client.state.value.features.editCatalog.actionsFor(client.state.value.selectionMode)
            .firstOrNull { it.id == id }?.let(::editCatalogAction)
    }

    /** Igual que [editFooterAction], concentra el futuro adaptador del catálogo. */
    fun editCatalogAction(action: EditCatalogAction, variant: String? = null) {
        if (!action.enabled || action.command == null) return
        // Las sesiones existentes usan exactamente tool.begin {tool, parameters}.
        val tool = EditTool.fromWire(action.id)
        if (action.execution == "SESSION" && action.command == "tool.begin" && tool != null) {
            if (client.transformSession.value.active) client.transformCancel()
            local.update { it.copy(activeTool = ActiveTool.valueOf(tool.name), loopCutAwaitingTap = false) }
            val params = action.parameters.associate { it.id to it.default }.toMutableMap()
            if (variant != null) params["variant"] = variant
            client.toolBegin(tool, params)
            return
        }
        client.editCatalogCommand(action.command, action.payload)
    }
    fun confirmTool() {
        loopCutArmed = false
        local.update { it.copy(loopCutAwaitingTap = false) }
        client.toolConfirm()
    }

    fun cancelTool() {
        loopCutArmed = false
        local.update { it.copy(loopCutAwaitingTap = false) }
        client.toolCancel()
    }

    /** Knife: quitar el último punto y cerrar la polilínea. */
    fun knifePop() = client.toolKnifePop()
    fun knifeClose() = client.toolKnifeClose()

    /** Knife: un toque añade un punto (optimista; se recorta si el servidor lo rechaza). */
    fun knifeTap(u: Float, v: Float) {
        _knifeScreenPoints.value = _knifeScreenPoints.value + (u to v)
        client.toolKnifePoint(u.toDouble(), v.toDouble())
    }

    /** Knife: conmuta el snap a vértice/arista. */
    fun knifeSnap(enabled: Boolean) {
        if (client.toolSession.value.active) client.toolParameter(mapOf("snap" to enabled))
    }

    /**
     * `snap_type: NONE` se siembra para las tools que lo anuncian en el catálogo
     * (offset/thickness/factor/merge_factor). Sin esta clave en la sesión inicial,
     * [ToolSession.availableSnapTypes] no puede distinguir "sin snap anunciado" de
     * "snap aún no fijado" y el selector de la bandeja no aparece.
     */
    private fun toolDefaultParameters(tool: EditTool): Map<String, Any?> = when (tool) {
        EditTool.EXTRUDE -> mapOf("offset" to 0.0, "snap_type" to "NONE")
        EditTool.BEVEL -> mapOf("offset" to 0.02, "segments" to 1.0, "snap_type" to "NONE")
        EditTool.INSET -> mapOf("thickness" to 0.1, "depth" to 0.0, "snap_type" to "NONE")
        EditTool.SUBDIVIDE -> mapOf("cuts" to 1.0)
        EditTool.LOOP_CUT -> mapOf("cuts" to 1.0, "smoothness" to 0.0, "factor" to 0.0, "snap_type" to "NONE")
        EditTool.BRIDGE_EDGE_LOOPS -> mapOf("twist_offset" to 0.0, "merge_factor" to 0.0, "snap_type" to "NONE")
        EditTool.KNIFE -> mapOf("snap" to 1.0)
        EditTool.BISECT -> mapOf("clear_inner" to 0.0, "clear_outer" to 0.0, "fill" to 0.0, "snap" to 1.0)
    }

    /**
     * Activa una familia de la barra de tools activas (`edit_toolbar`, B1/F1).
     *
     * Tap sin variante conserva la última usada en esta familia, o la variante por
     * defecto del servidor. Loop Cut y Knife reutilizan exactamente el flujo que ya
     * tenían (toque en viewport / puntos); Bisect arma la sesión y espera el
     * arrastre de línea; Extrude/Inset abren la sesión con la variante como
     * parámetro, igual que ya hacía el catálogo contextual.
     */
    fun activateToolbarFamily(family: EditToolbarFamily, variantId: String? = null) {
        val remembered = local.value.toolbarVariant[family.id]
        val variant = family.variants.firstOrNull { it.id == (variantId ?: remembered) }
            ?: family.variants.firstOrNull { it.id == family.defaultVariant }
            ?: family.variants.firstOrNull { it.enabled }
            ?: return
        local.update { it.copy(toolbarVariant = it.toolbarVariant + (family.id to variant.id)) }
        val toolWire = (variant.payload["tool"] as? String) ?: (family.payload["tool"] as? String) ?: family.id
        val tool = EditTool.fromWire(toolWire) ?: return
        when (tool) {
            EditTool.LOOP_CUT, EditTool.KNIFE -> beginEditTool(tool)
            EditTool.BISECT -> {
                if (client.transformSession.value.active) client.transformCancel()
                local.update { it.copy(activeTool = ActiveTool.BISECT, loopCutAwaitingTap = false) }
                client.toolBegin(tool, toolDefaultParameters(tool))
            }
            else -> {
                if (client.transformSession.value.active) client.transformCancel()
                local.update { it.copy(activeTool = ActiveTool.valueOf(tool.name), loopCutAwaitingTap = false) }
                val params = (family.parameters + variant.parameters)
                    .associate { it.id to it.default }.toMutableMap<String, Any?>()
                params["variant"] = variant.id
                client.toolBegin(tool, params)
            }
        }
    }

    /** Bisect: arrastre de línea completo del viewport (F4), inicio/fin normalizados. */
    fun bisectDragLine(u0: Float, v0: Float, u1: Float, v1: Float) =
        client.toolDragLine(u0.toDouble(), v0.toDouble(), u1.toDouble(), v1.toDouble())

    /** Al abrir el menú Archivo: refresca nombre, "sin guardar" y recientes. */
    fun refreshFileMenu() {
        client.fileInfo()
        client.requestRecentFiles()
    }

    val transformSession: StateFlow<TransformSession> = client.transformSession

    /** Herramienta paramétrica de Edit Mode en curso (Extrude/Bevel/Inset/Subdivide). */
    val toolSession: StateFlow<ToolSession> = client.toolSession
    val remoteFiles = client.remoteFiles

    fun openFileBrowser() {
        client.fileLocations()
        client.fileBrowse()
    }

    fun browseFiles(path: String) = client.fileBrowse(path)
    fun setDefaultFolder(path: String) = client.fileDefaultFolder(path)

    /**
     * Abre una transformación modal. Se mantiene abierta aunque se levante el dedo:
     * termina con [transformConfirm] o [transformCancel].
     */
    fun transformBegin(mode: TransformMode) {
        // Una transformación y una herramienta paramétrica no conviven: cerrar la otra.
        if (client.toolSession.value.active) client.toolCancel()
        loopCutArmed = false
        local.update { it.copy(loopCutAwaitingTap = false) }
        val step = stepsFor(mode)[localStepIndex(mode)].step
        val constraint = if (mode == TransformMode.ROTATE && local.value.constraint.axes.size > 1) {
            // Un giro es alrededor de UN eje: un plano elegido para mover no vale.
            Constraint.Z
        } else {
            local.value.constraint
        }
        client.transformBegin(
            mode, constraint.axes, step = step,
            snapType = snapTypeFor(mode),
            orientation = local.value.orientation,
            valueMode = local.value.valueMode,
        )
    }

    /**
     * El snap elegido, recortado a lo que admite el modo: los geométricos solo
     * existen en MOVE, y pedirlos en rotar o escalar daría `wrong_tool`.
     */
    private fun snapTypeFor(mode: TransformMode): SnapType {
        val chosen = local.value.snapType
        return if (chosen in SnapType.forMode(mode)) chosen else SnapType.NONE
    }

    /** Elige la restricción (ejes o planos). Con la sesión abierta, la aplica en vivo. */
    fun setConstraint(constraint: Constraint) {
        local.update { it.copy(constraint = constraint) }
        val session = client.transformSession.value
        if (session.active) client.transformAxes(constraint.axes)
    }

    /**
     * Elige la orientación. El servidor no la cambia en vivo, así que si hay sesión
     * abierta se reabre conservando ejes, snap y paso; el delta vuelve a cero.
     */
    fun setOrientation(orientation: Orientation) {
        local.update { it.copy(orientation = orientation) }
        val session = client.transformSession.value
        if (session.active) {
            client.transformBegin(
                session.mode, session.axes, session.step,
                snapType = session.snapType,
                orientation = orientation,
                valueMode = session.valueMode,
            )
        }
    }

    /** Elige el tipo de snap. Con sesión abierta se aplica en vivo. */
    fun setSnapType(type: SnapType) {
        local.update { it.copy(snapType = type) }
        val session = client.transformSession.value
        if (session.active) client.transformSnap(snapTypeFor(session.mode), session.step)
    }

    fun setStep(mode: TransformMode, index: Int) {
        local.update { it.copy(stepIndex = it.stepIndex + (mode to index)) }
        val session = client.transformSession.value
        if (session.active) client.transformSnap(session.snapType, stepsFor(mode)[index].step)
    }

    /**
     * Relativo (delta desde que se abrió) o absoluto (coordenada destino). El servidor
     * lo fija en `begin`, así que cambiarlo con la sesión viva la reabre; el delta
     * acumulado vuelve a cero, que es justo lo que se espera al cambiar de criterio.
     */
    fun setValueMode(valueMode: ValueMode) {
        local.update { it.copy(valueMode = valueMode) }
        val session = client.transformSession.value
        if (session.active) {
            client.transformBegin(
                session.mode, session.axes, session.step,
                snapType = session.snapType,
                orientation = session.orientation,
                valueMode = valueMode,
            )
        }
    }

    fun stepIndex(mode: TransformMode) = localStepIndex(mode)

    private fun localStepIndex(mode: TransformMode) =
        local.value.stepIndex[mode] ?: stepsFor(mode).indexOfFirst { it.step >= 0.01 }.coerceAtLeast(0)

    fun transformValue(values: List<Double>?, angleDegrees: Double?) =
        client.transformValue(values, angleDegrees)

    fun transformConfirm() = client.transformConfirm()
    fun transformCancel() = client.transformCancel()

    fun fileNew() = client.fileNew()
    fun fileOpen(path: String) = client.fileOpen(path)
    fun fileSave() = client.fileSave()
    fun fileSaveAs(path: String) = client.fileSaveAs(path)
    fun fileSaveAs(folder: String, name: String) = client.fileSaveAs(folder, name)

    fun setLocation(x: Float, y: Float, z: Float) =
        client.setLocation(x.toDouble(), y.toDouble(), z.toDouble())

    /** El panel muestra grados; el protocolo trabaja en radianes. */
    fun setRotationDegrees(x: Float, y: Float, z: Float) = client.setRotation(
        Math.toRadians(x.toDouble()), Math.toRadians(y.toDouble()), Math.toRadians(z.toDouble()),
    )

    fun setScale(x: Float, y: Float, z: Float) =
        client.setScale(x.toDouble(), y.toDouble(), z.toDouble())

    /** Gestos de navegación: orbit, pan y zoom van tal cual al servidor. */
    fun viewGesture(gesture: Gesture, phase: GesturePhase, dx: Float, dy: Float, factor: Float) =
        client.gesture(gesture, phase, dx.toDouble(), dy.toDouble(), factor.toDouble())

    /**
     * Arrastre de un dedo/stylus: se traduce al gesto de la herramienta activa.
     * El servidor lo agrupa y cierra un único paso de undo al soltar.
     */
    fun toolGesture(phase: GesturePhase, dx: Float, dy: Float) {
        // Con una herramienta paramétrica abierta, el arrastre la alimenta a ella:
        // sube/baja el parámetro primario (offset, grosor o cortes) y no orbita.
        val tool = client.toolSession.value
        if (tool.active) {
            if (tool.acceptsViewportNudge && !tool.snapType.geometric &&
                (phase == GesturePhase.UPDATE || phase == GesturePhase.END)
            ) {
                client.toolNudge((-dy).toDouble())
            }
            // Knife se maneja por taps (tool.knife_point), no por arrastre. El
            // arrastre de un dedo queda deliberadamente inerte durante la sesión;
            // dos dedos y el círculo de navegación usan onViewGesture y no pasan
            // por aquí, por lo que siguen moviendo la cámara.
            return
        }

        // Con una transformación modal abierta, el arrastre la alimenta a ella y no
        // orbita: el dedo está transformando, no navegando. El servidor ignora el
        // tipo de gesto y usa el modo que eligió la barra.
        val session = client.transformSession.value
        if (session.active) {
            val gesture = when (session.mode) {
                TransformMode.MOVE -> Gesture.MOVE
                TransformMode.ROTATE -> Gesture.ROTATE
                TransformMode.SCALE -> Gesture.SCALE
            }
            client.gesture(gesture, phase, dx.toDouble(), dy.toDouble())
            return
        }

        // Sin ninguna sesión abierta, arrastrar un dedo orbita: tocar selecciona y
        // arrastrar mueve la cámara. Mover, rotar y escalar ya no son "herramientas
        // activas" que reinterpreten el arrastre, sino sesiones que se abren desde el
        // rail, y mientras una está viva se la alimenta arriba.
        client.gesture(Gesture.ORBIT, phase, dx.toDouble(), dy.toDouble())
    }

    override fun onCleared() {
        h264Stream.close()
        runCatching { connectivity?.unregisterNetworkCallback(networkCallback) }
        stream.stop()
        client.disconnect()
        super.onCleared()
    }
}
