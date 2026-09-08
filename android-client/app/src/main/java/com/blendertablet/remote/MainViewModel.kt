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
import com.blendertablet.remote.data.SnapPreferences
import com.blendertablet.remote.data.SnapSettings
import com.blendertablet.remote.model.ActiveTool
import com.blendertablet.remote.model.Axis
import com.blendertablet.remote.model.AppUiState
import com.blendertablet.remote.model.BlenderMode
import com.blendertablet.remote.model.ConnectionStatus
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
import com.blendertablet.remote.model.TransformStepUnit
import com.blendertablet.remote.model.TweakMotion
import com.blendertablet.remote.model.TweakSettings
import com.blendertablet.remote.model.ValueMode
import com.blendertablet.remote.model.scaleStepForWire
import com.blendertablet.remote.model.scaleStepWireUnit
import com.blendertablet.remote.model.moveStepInBlenderUnits
import com.blendertablet.remote.model.transformStepUnit
import com.blendertablet.remote.model.stepsFor
import com.blendertablet.remote.model.stepInBlenderUnits
import com.blendertablet.remote.model.defaultStepIndex
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
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch

class MainViewModel(application: Application) : AndroidViewModel(application) {
    private val client: RemoteBlenderClient = WebSocketRemoteBlenderClient(viewModelScope)
    private val snapPreferences = SnapPreferences(application)
    private val local = MutableStateFlow(AppUiState(
        snapType = snapPreferences.current.type,
        snapStep = snapPreferences.current.step,
    ))
    private val preferences = ConnectionPreferences(application)
    private val stream = ViewportStream(viewModelScope)
    private var currentStreamEndpoint: com.blendertablet.remote.network.StreamEndpoint? = null
    private val _h264Active = MutableStateFlow(false)
    val h264Active: StateFlow<Boolean> = _h264Active
    private val h264Stream = H264ViewportStream(viewModelScope) { fallbackToMjpeg() }
    val h264Size = h264Stream.size
    private var cadStroke = false
    private var loopCutArmed = false
    private var facePickRole: String? = null
    private var lastFacePointer: Pair<Float, Float>? = null
    private var lastReferencePointer: Pair<Float, Float>? = null
    // Debe inicializarse antes de `init`: StateFlow emite su valor actual en cuanto
    // empieza el collect y Main.immediate puede ejecutar esa emisión durante el
    // propio constructor del ViewModel.
    private val _knifeScreenPoints = MutableStateFlow<List<List<Pair<Float, Float>>>>(emptyList())
    val knifeScreenPoints: StateFlow<List<List<Pair<Float, Float>>>> = _knifeScreenPoints.asStateFlow()
    private val connectivity =
        application.getSystemService(ConnectivityManager::class.java)

    val settings: StateFlow<ConnectionSettings> = preferences.settings

    /** Hay datos guardados: el diálogo no tiene que salir al arrancar. */
    val hasSavedConnection: Boolean get() = preferences.current.isComplete

    val viewportFrame: StateFlow<ViewportFrame?> = stream.frame
    val streamStats: StateFlow<StreamStats> = stream.stats

    private val remote = combine(
        client.connection, client.state, client.errors, client.retryAttempt, client.notices,
    ) { connection, blender, error, retryAttempt, notice ->
        AppUiState(connection = connection, blender = blender, error = error,
                   retryAttempt = retryAttempt, notice = notice)
    }

    val uiState = combine(
        local, remote, client.file, client.sceneScalePresets,
    ) { ui, net, file, scalePresets ->
        ui.copy(
            connection = net.connection,
            blender = net.blender,
            error = net.error,
            notice = net.notice,
            retryAttempt = net.retryAttempt,
            file = file,
            sceneScalePresets = scalePresets,
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
            combine(client.connection, client.state) { connection, state ->
                connection == ConnectionStatus.CONNECTED && state.features.cad.available
            }.distinctUntilChanged().collect { ready ->
                cadStroke = false
                local.update { it.copy(cadTool = null) }
                if (ready) client.cadCommand("cad.state")
            }
        }

        viewModelScope.launch {
            client.state.collect { state ->
                if (loopCutArmed && state.mode == BlenderMode.EDIT && state.context.selectionCounts.edges > 0) {
                    loopCutArmed = false
                    client.toolBegin(EditTool.LOOP_CUT, toolDefaultParameters(EditTool.LOOP_CUT))
                }
            }
        }
        // La copia nace encima del original y no se ve. Como el Shift+D de Blender, se
        // entrega agarrada al gesto de mover: así se ve nacer y se coloca de una vez.
        // Cancelar el Mover no deshace el duplicado, son pasos de undo distintos.
        viewModelScope.launch {
            client.duplicates.collect { transformBegin(TransformMode.MOVE) }
        }
        // Los overlays los apaga el ojo, pero viven en el servidor: si la conexión
        // se cae con la interfaz oculta, Blender se queda sin rejilla y el estado
        // local ya no manda nada. Al (re)conectar se reimpone lo que dice el ojo.
        // Se espera a que además estén las capabilities: CONNECTED llega antes de
        // saber si el servidor entiende `view.overlays`, y preguntarlo a ciegas
        // dispararía un error visible contra un backend anterior.
        viewModelScope.launch {
            combine(client.connection, client.state) { status, remote ->
                status == ConnectionStatus.CONNECTED && remote.features.overlays
            }.distinctUntilChanged().collect { ready ->
                if (ready) client.viewOverlays(local.value.controlsVisible)
            }
        }
        // Las unidades de Mover y Escalar siguen al preset real de la escena. Se observa
        // también al abrir otro .blend, no solo cuando el usuario toca el menú.
        viewModelScope.launch {
            client.state.map { it.sceneScale.lengthUnit }.distinctUntilChanged().collect { unit ->
                local.update { it.copy(moveStepUnit = unit.transformStepUnit()) }
                setScaleStep(local.value.scaleStepValue, unit.transformStepUnit())
            }
        }
        // El catálogo de escalas no viaja en el snapshot (es fijo) y el menú Escena
        // lo necesita: se pide una vez por conexión, cuando ya se sabe si el servidor
        // lo soporta. Mismo motivo que los overlays de arriba.
        viewModelScope.launch {
            combine(client.connection, client.state) { status, remote ->
                status == ConnectionStatus.CONNECTED && remote.features.sceneScale
            }.distinctUntilChanged().collect { ready ->
                if (ready) client.requestSceneScales()
            }
        }
        // El toque elige el anillo; el corte comienza centrado. Un sondeo fallido
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
                                mapOf("edge" to probe.edge.toDouble(), "factor" to 0.0),
                        )
                    }
                }
            }
        }
        // El puerto del vídeo lo anuncia el servidor en el "hello": el usuario solo
        // configura el de control y el vídeo se engancha solo (§63).
        viewModelScope.launch {
            client.toolSession.collect { session ->
                if (session.tool != EditTool.KNIFE) {
                    if (_knifeScreenPoints.value.isNotEmpty()) _knifeScreenPoints.value = emptyList()
                } else {
                    fun screen(points: List<List<Double>>) = points.mapNotNull { point ->
                        if (point.size >= 2) point[0].toFloat() to point[1].toFloat() else null
                    }
                    _knifeScreenPoints.value = session.projectedStrokes.map(::screen) +
                        listOf(screen(session.projectedPoints))
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
    fun onForeground() {
        h264Stream.resume()
        client.retryNow()
    }

    /** Detiene MediaCodec antes de que Android invalide los buffers de la Surface. */
    fun onBackground() = h264Stream.pause()

    fun disconnect() {
        h264Stream.stopTransport()
        stream.stop()
        client.disconnect()
    }

    /** El toast de error se auto-descarta: la UI lo limpia a los ~5 s. */
    fun clearError() = client.clearError()

    /** El aviso dura menos que el error: confirma, no reclama atención. */
    fun clearNotice() = client.clearNotice()

    fun attachVideoSurface(surface: Surface) = h264Stream.attachSurface(surface)
    fun changeVideoSurface(surface: Surface, width: Int, height: Int) =
        h264Stream.surfaceChanged(surface, width, height)
    fun detachVideoSurface(surface: Surface) = h264Stream.detachSurface(surface)

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
    fun enterCad() {
        if (!client.state.value.features.cad.available) return
        closeSessions()
        local.update { it.copy(activeTool = ActiveTool.SELECT, shapeTool = ShapeTool.NONE,
            referencePicking = false, cadTool = null, shortestPathActive = false) }
        client.cadCommand("mode.set", mapOf("mode" to "CAD"))
    }
    fun cadCommand(name: String, payload: Map<String, Any?> = emptyMap()) {
        if (!client.state.value.cad.workspace) return
        cancelCadStroke()
        client.cadCommand(name, payload)
    }
    fun cadTool(type: String?) {
        cancelCadStroke()
        local.update { it.copy(cadTool = type?.takeIf { candidate -> candidate in client.state.value.features.cad.entities ||
            (client.state.value.features.cad.sketchEditing && candidate in listOf("MOVE", "MULTI")) }) }
    }
    private var cadGestureMode: String? = null
    private var cadDepthStart = .02
    private var cadPointerStartV = 0f
    private fun cancelCadStroke() {
        if (cadStroke) {
            cadStroke = false
            if (cadGestureMode == "DEPTH") client.cadCommand("cad.extrude.update", mapOf("depth" to cadDepthStart))
            else client.cadCommand("cad.session.cancel")
            cadGestureMode = null
        }
    }
    fun cadGesture(phase: GesturePhase, u: Float, v: Float) {
        if (!client.state.value.cad.workspace) { cadStroke = false; cadGestureMode = null; return }
        when (phase) {
            GesturePhase.BEGIN -> {
                val cad = client.state.value.cad
                cadPointerStartV = v
                if (cad.sessionActive && cad.operation in listOf("EXTRUDE", "CUT")) {
                    cadStroke = true; cadGestureMode = "DEPTH"; cadDepthStart = cad.depth
                    return
                }
                val type = local.value.cadTool ?: return
                if (cad.activeSketchId == null || type == "MULTI") return
                cadStroke = true
                cadGestureMode = if (type == "MOVE") "DRAG" else "DRAW"
                client.cadCommand(if (type == "MOVE") "cad.drag.begin" else "cad.entity.begin", mapOf("type" to type, "u" to u, "v" to v))
            }
            GesturePhase.UPDATE -> if (cadStroke) {
                when (cadGestureMode) {
                    "DEPTH" -> client.cadCommand("cad.extrude.update", mapOf("gesture" to (cadPointerStartV - v), "baseline_depth" to cadDepthStart))
                    "DRAG" -> client.cadCommand("cad.drag.update", mapOf("u" to u, "v" to v))
                    "DRAW" -> client.cadCommand("cad.entity.update", mapOf("u" to u, "v" to v))
                }
            }
            GesturePhase.END -> if (cadStroke) {
                cadStroke = false
                when (cadGestureMode) {
                    "DRAG" -> client.cadCommand("cad.drag.end")
                    "DRAW" -> client.cadCommand("cad.session.confirm")
                }
                cadGestureMode = null
            }
            GesturePhase.CANCEL -> cancelCadStroke()
        }
    }

    fun setMode(mode: BlenderMode) {
        cancelCadStroke()
        local.update { it.copy(cadTool = null) }
        closeSessions()
        local.update { it.copy(
            shapeTool = ShapeTool.NONE,
            activeTool = if (mode != BlenderMode.EDIT && it.activeTool == ActiveTool.TWEAK)
                ActiveTool.SELECT else it.activeTool,
            shortestPathActive = if (mode == BlenderMode.EDIT) it.shortestPathActive else false,
        ) }
        client.setMode(mode)
    }

    fun setSelectionMode(mode: SelectionMode) {
        closeSessions()
        local.update { it.copy(shapeTool = ShapeTool.NONE) }
        client.setSelectionMode(mode)
    }

    private fun closeTransformForToolChange() {
        val wasTweak = local.value.activeTool == ActiveTool.TWEAK
        val cancelled = cancelTweakGesture()
        // END ya enviado puede seguir figurando como MOVE hasta recibir su respuesta.
        // El cierre de Tweak es su propio END/CANCEL, identificado por sesión.
        if (!wasTweak && !cancelled && client.transformSession.value.active) client.transformCancel()
    }

    private fun closeSessions() {
        closeTransformForToolChange()
        if (client.toolSession.value.active) client.toolCancel()
        loopCutArmed = false
        local.update { it.copy(loopCutAwaitingTap = false) }
    }
    /**
     * El ojo de la barra superior: esconde toda la interfaz y, con ella, la rejilla
     * y los overlays del viewport remoto. Un "ocultar controles" que dejara la
     * rejilla puesta no serviría para lo que se usa (ver el modelo limpio), así que
     * el mismo gesto apaga `space.overlay` en el servidor.
     */
    fun toggleControls() {
        val visible = !local.value.controlsVisible
        local.update { it.copy(controlsVisible = visible) }
        if (client.state.value.features.overlays) client.viewOverlays(visible)
    }
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
    fun undo() { cancelCadStroke(); client.undo() }
    fun redo() { cancelCadStroke(); client.redo() }
    fun repeatLast() = client.repeatLast()
    fun delete() = client.delete()
    fun duplicate() = client.duplicate()
    fun runDuplicateVariant(linked: Boolean) {
        local.update { it.copy(duplicateLinked = linked) }
        if (linked) client.duplicateLinked() else client.duplicate()
    }
    fun frameSelected() = client.frameSelected()
    /**
     * Un toque en el viewport. Normalmente selecciona, pero con una transformación
     * abierta y un snap geométrico elegido significa "pega el movimiento a esto":
     * el toque fija el destino. En Edit también permite continuar en otra selección
     * confirmando el paso anterior.
     */
    fun pick(u: Float, v: Float, stylus: Boolean = false) {
        if (client.state.value.cad.workspace) {
            client.cadCommand("cad.select", mapOf("u" to u, "v" to v, "additive" to (local.value.cadTool == "MULTI"))); return
        }
        val surfaceTool = client.toolSession.value
        if (surfaceTool.armed && surfaceTool.input == "REPEAT_TAP") {
            client.toolExtrudeCursor(u.toDouble(), v.toDouble())
            return
        }
        if (surfaceTool.active && surfaceTool.input == "FACE_PAIR") {
            client.toolFacePick(u.toDouble(), v.toDouble(),
                surfaceTool.parameters["pick_role"] as? String ?: "SOURCE", "TAP")
            return
        }
        if (choosingTransformSelection()) {
            client.transformSelect(u.toDouble(), v.toDouble(), if (stylus) 0.028 else 0.055, local.value.selectionOp)
            return
        }
        if (local.value.referencePicking && client.transformSession.value.active) {
            client.transformReferenceCandidate(u.toDouble(), v.toDouble(), lock = true)
            local.update { it.copy(referencePicking = false) }
            return
        }
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
        // Loop Cut: el toque elige el anillo y crea su corte centrado.
        if (local.value.activeTool == ActiveTool.LOOP_CUT) {
            val blender = uiState.value.blender
            if (blender.mode == BlenderMode.EDIT) {
                if (client.toolSession.value.active) {
                    val add = blender.features.loopCutMultiple && local.value.selectionOp == SelectionOp.TOGGLE
                    client.toolLoopPick(u.toDouble(), v.toDouble(), add = add)
                    return
                }
                if (local.value.loopCutAwaitingTap) {
                    client.meshLoopProbe(u.toDouble(), v.toDouble())
                    return
                }
            }
        }
        val session = client.transformSession.value
        if (session.active && session.snapType.geometric) {
            if (session.mode != TransformMode.MOVE && session.source.isEmpty()) {
                client.transformReferenceCandidate(
                    u.toDouble(), v.toDouble(), lock = true, role = "SOURCE",
                )
                local.update { it.copy(referencePicking = false, referenceRole = "SOURCE") }
                return
            }
            client.transformSnapCandidate(u.toDouble(), v.toDouble(), session.snapType)
            return
        }
        if (session.active) {
            if (client.state.value.mode == BlenderMode.EDIT && client.state.value.features.transformStepSelection &&
                local.value.activeTool != ActiveTool.TWEAK) {
                client.transformSelect(u.toDouble(), v.toDouble(), if (stylus) 0.028 else 0.055, local.value.selectionOp)
            }
            return
        }
        // El pen apunta con precisión: un radio menor evita saltar al elemento vecino.
        // El dedo conserva una diana más grande y cómoda.
        val threshold = if (stylus) 0.028 else 0.055
        if (local.value.shortestPathActive && uiState.value.blender.mode == BlenderMode.EDIT) {
            client.shortestPath(u.toDouble(), v.toDouble(), threshold)
        } else {
            client.pick(u.toDouble(), v.toDouble(), threshold, local.value.selectionOp)
        }
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

    fun toggleProportional() {
        val enabled = !client.state.value.editSettings.proportional
        client.editSettings(mapOf("proportional" to enabled))
        client.transformSession.value.takeIf { it.active }?.let { transformBegin(it.mode) }
    }

    fun toggleAutoMerge() {
        client.editSettings(mapOf("auto_merge" to !client.state.value.editSettings.autoMerge))
    }

    fun scaleProportionalRadius(factor: Double) {
        val current = client.state.value
        setProportionalRadius(
            current.editSettings.radius + current.sceneScale.proportionalRadiusStep * factor
        )
    }

    fun setProportionalRadius(value: Double) {
        val radius = value.coerceIn(0.0001, 1_000.0)
        client.editSettings(mapOf("radius" to radius))
        client.transformSession.value.takeIf { it.active }?.let { transformBegin(it.mode) }
    }

    fun cycleProportionalFalloff() {
        val options = listOf("SMOOTH", "SPHERE", "ROOT", "SHARP", "LINEAR", "CONSTANT", "INVERSE_SQUARE")
        val current = client.state.value.editSettings.falloff
        val next = options[(options.indexOf(current).coerceAtLeast(0) + 1) % options.size]
        client.editSettings(mapOf("falloff" to next))
        client.transformSession.value.takeIf { it.active }?.let { transformBegin(it.mode) }
    }

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
        local.update { it.copy(
            selectionOp = if (it.selectionOp == op && !it.shortestPathActive) SelectionOp.SET else op,
            shortestPathActive = false,
        ) }
    }

    fun toggleShortestPath() {
        local.update { it.copy(
            shortestPathActive = !it.shortestPathActive,
            selectionOp = SelectionOp.SET,
        ) }
    }

    /** B/C: arma/desarma la herramienta de arrastre por forma. */
    fun toggleShapeTool(tool: ShapeTool) {
        local.update { it.copy(shapeTool = if (it.shapeTool == tool) ShapeTool.NONE else tool) }
    }

    /** El menú radial siempre arma B/C; repetir el botón nunca debe desarmarla. */
    fun armShapeTool(tool: ShapeTool) {
        require(tool == ShapeTool.BOX || tool == ShapeTool.CIRCLE)
        local.update { it.copy(shapeTool = tool, shortestPathActive = false) }
    }

    fun setCircleRadius(radius: Float?) {
        local.update { it.copy(circleRadius = radius?.coerceIn(0.01f, 0.5f)) }
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
        // Mayús+arrastre extiende, no alterna: es el Shift de la caja de Blender, que
        // suma lo barrido en vez de invertir cada elemento que toca.
        val op = local.value.selectionOp.let { if (it == SelectionOp.TOGGLE) SelectionOp.ADD else it }
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
    fun hideObject(name: String? = null) = client.hideObjects(name?.let(::listOf))
    fun toggleObjectShading(name: String? = null) = client.shadeObjects(name?.let(::listOf))
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
    /** Preset de escala: unidades, profundidad de cámara, pasos y tamaño al añadir. */
    fun setSceneScale(preset: String) = client.setSceneScale(preset = preset)

    fun addModifier(type: String, parameters: Map<String, Any?> = emptyMap()) = client.modifierAdd(type, parameters)
    fun removeModifier(name: String) = client.modifierRemove(name)
    fun moveModifier(name: String, index: Int) = client.modifierMove(name, index)
    fun setModifier(name: String, key: String, value: Any?) = client.modifierSet(name, mapOf(key to value))
    fun toggleModifier(name: String, viewport: Boolean? = null, render: Boolean? = null) = client.modifierToggle(name, viewport, render)
    fun applyModifier(name: String) = client.modifierApply(name)
    fun selectLoop() {
        val op = local.value.selectionOp
        client.selectLoop(op)
    }
    fun selectRing() {
        val op = local.value.selectionOp.let { if (it == SelectionOp.TOGGLE) SelectionOp.ADD else it }
        client.selectRing(op)
    }

    /** La `L` de Blender: de lo tocado a toda la pieza suelta que lo contiene. */
    fun selectLinked() = client.selectLinked()
    fun selectObject(name: String, add: Boolean) = client.selectObject(name, add)
    fun meshDelete(what: String) = client.meshDelete(what)
    fun meshDissolve(what: String) = client.meshDissolve(what)
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
            objectShadingAvailable = blender.features.objectShading,
            shadeSmooth = blender.activeShadeSmooth,
            localView = local.value.localViewActive,
        )
    }

    /** Herramientas paramétricas de Edit Mode. */
    fun beginEditTool(tool: EditTool) {
        closeTransformForToolChange()
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

    fun beginAlignment(objectName: String?) {
        if (uiState.value.blender.mode != BlenderMode.OBJECT) return
        local.update { it.copy(activeTool = ActiveTool.SELECT, referencePicking = false, shapeTool = ShapeTool.NONE) }
        facePickRole = null
        lastFacePointer = null
        client.toolBegin(EditTool.ALIGN, objectName?.let { mapOf("object" to it) } ?: emptyMap())
    }

    fun setToolParameter(key: String, value: Any?) {
        when (key) {
            "snap_type" -> (value as? String)?.let { wire ->
                SnapType.entries.firstOrNull { it.name == wire }?.let(::rememberSnapType)
            }
            "snap_step" -> (value as? Number)?.toDouble()?.let(::rememberSnapStep)
        }
        client.toolParameter(mapOf(key to value))
    }

    fun nudgeTool(delta: Double) = client.toolNudge(delta)

    /** Seguimiento absoluto del dedo para snap geométrico durante el arrastre. */
    fun toolPointer(u: Float, v: Float) {
        if (client.state.value.cad.workspace || choosingTransformSelection()) return
        val surfaceTool = client.toolSession.value
        if (surfaceTool.active && surfaceTool.input == "FACE_PAIR") {
            lastFacePointer = u to v
            client.toolFacePick(u.toDouble(), v.toDouble(), facePickRole ?:
                (surfaceTool.parameters["pick_role"] as? String ?: "SOURCE"), "UPDATE")
            return
        }
        if (local.value.referencePicking && client.transformSession.value.active) {
            lastReferencePointer = u to v
            client.transformReferenceCandidate(
                u.toDouble(), v.toDouble(), lock = false, role = local.value.referenceRole,
            )
            return
        }
        val tool = client.toolSession.value
        if (tool.active && tool.snapType.geometric) {
            client.toolSnapCandidate(u.toDouble(), v.toDouble(), tool.snapType, lock = false)
            return
        }
        val transform = client.transformSession.value
        if (transform.active && transform.snapType.geometric &&
            (transform.mode == TransformMode.MOVE || transform.source.isNotEmpty())) {
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
            EditFooterAction.CONNECT_VERTICES -> "CONNECT_VERTICES"
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
            closeTransformForToolChange()
            local.update { it.copy(activeTool = ActiveTool.valueOf(tool.name), loopCutAwaitingTap = false) }
            val params = action.parameters.associate { it.id to it.default }.toMutableMap()
            if (variant != null) params["variant"] = variant
            client.toolBegin(tool, withGlobalSnap(tool, params))
            return
        }
        if (action.id == "CONNECT_VERTICES") selectTool()
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
    fun knifeNewStroke() = client.toolKnifeNewStroke()
    fun loopCutPop() = client.toolLoopPop()
    fun knifeClose() = client.toolKnifeClose()

    /** Compatibilidad con servidores antiguos que aún colocan Knife por toque. */
    fun knifeTap(u: Float, v: Float) {
        val strokes = _knifeScreenPoints.value.ifEmpty { listOf(emptyList()) }
        _knifeScreenPoints.value = strokes.dropLast(1) + listOf(strokes.last() + (u to v))
        client.toolKnifePoint(u.toDouble(), v.toDouble())
    }

    fun knifeDrag(phase: GesturePhase, u: Float, v: Float) =
        client.toolKnifeDrag(phase, u.toDouble(), v.toDouble())

    /** Knife: conmuta el snap a vértice/arista. */
    fun knifeSnap(enabled: Boolean) {
        if (client.toolSession.value.active) client.toolParameter(mapOf("snap" to enabled))
    }

    fun knifeSnapMode(mode: String) {
        if (client.toolSession.value.active) client.toolParameter(mapOf("snap_mode" to mode))
    }

    /**
     * `snap_type: NONE` se siembra para las tools que lo anuncian en el catálogo
     * (offset/thickness/factor/merge_factor). Sin esta clave en la sesión inicial,
     * [ToolSession.availableSnapTypes] no puede distinguir "sin snap anunciado" de
     * "snap aún no fijado" y el selector de la bandeja no aparece.
     */
    private fun toolDefaultParameters(tool: EditTool): Map<String, Any?> = withGlobalSnap(tool, when (tool) {
        EditTool.EXTRUDE -> mapOf("offset" to 0.0, "snap_type" to "NONE")
        EditTool.BEVEL -> mapOf("offset" to 0.02, "segments" to 1.0, "snap_type" to "NONE")
        EditTool.INSET -> mapOf(
            "thickness" to 0.1,
            "depth" to 0.0,
            "boundary" to true,
            "snap_type" to "NONE",
        )
        EditTool.SUBDIVIDE -> mapOf("cuts" to 1.0)
        EditTool.REVOLVE, EditTool.SWEEP -> emptyMap()
        EditTool.LOOP_CUT -> mapOf("cuts" to 1.0, "smoothness" to 0.0, "factor" to 0.0, "snap_type" to "NONE")
        EditTool.BRIDGE_EDGE_LOOPS -> mapOf("twist_offset" to 0.0, "merge_factor" to 0.0, "snap_type" to "NONE")
        EditTool.ALIGN -> emptyMap()
        EditTool.KNIFE -> mapOf("snap" to 1.0)
        EditTool.BISECT -> mapOf("clear_inner" to 0.0, "clear_outer" to 0.0, "fill" to 0.0, "snap" to 1.0)
    })

    private fun withGlobalSnap(tool: EditTool, parameters: Map<String, Any?>): Map<String, Any?> {
        if ("snap_type" !in parameters) return parameters
        val chosen = local.value.snapType
        val compatible = if (tool == EditTool.EXTRUDE || !chosen.geometric) chosen else SnapType.NONE
        return parameters + mapOf(
            "snap_type" to compatible.name,
            "snap_step" to local.value.snapStep,
        )
    }

    private fun rememberSnapType(type: SnapType) {
        local.update { it.copy(snapType = type) }
        snapPreferences.save(SnapSettings(type, local.value.snapStep))
    }

    private fun rememberSnapStep(step: Double) {
        local.update { it.copy(snapStep = step) }
        snapPreferences.save(SnapSettings(local.value.snapType, step))
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
                closeTransformForToolChange()
                local.update { it.copy(activeTool = ActiveTool.BISECT, loopCutAwaitingTap = false) }
                client.toolBegin(tool, toolDefaultParameters(tool))
            }
            else -> {
                closeTransformForToolChange()
                local.update { it.copy(activeTool = ActiveTool.valueOf(tool.name), loopCutAwaitingTap = false) }
                val params = (family.parameters + variant.parameters)
                    .associate { it.id to it.default }.toMutableMap<String, Any?>()
                params["variant"] = variant.id
                client.toolBegin(tool, withGlobalSnap(tool, params))
            }
        }
    }

    /** Bisect: arrastre de línea completo del viewport (F4), inicio/fin normalizados. */
    fun bisectDragLine(u0: Float, v0: Float, u1: Float, v1: Float) =
        client.toolDragLine(u0.toDouble(), v0.toDouble(), u1.toDouble(), v1.toDouble())

    /** Al abrir Archivo refresca el estado del documento; Recientes ya no forma parte del menú. */
    fun refreshFileMenu() {
        client.fileInfo()
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
        if (local.value.activeTool == ActiveTool.TWEAK) {
            cancelTweakGesture()
            local.update { it.copy(activeTool = ActiveTool.SELECT) }
        }
        // Una transformación y una herramienta paramétrica no conviven: cerrar la otra.
        if (client.toolSession.value.active) client.toolCancel()
        loopCutArmed = false
        local.update { it.copy(loopCutAwaitingTap = false) }
        if (mode == TransformMode.SCALE) {
            local.update { it.copy(scaleUnit = client.state.value.sceneScale.lengthUnit.transformStepUnit()) }
        }
        val preset = stepsFor(mode)[localStepIndex(mode)]
        val scaleLength = uiState.value.blender.unitScaleLength
        // MOVE y SCALE leen el paso del campo de la barra, que es el que el usuario ve
        // y el que mueven los botones +/−. Con PERCENT en MOVE no hay distancia de
        // referencia todavía, así que ahí sigue mandando el preset hasta que exista.
        val step = when (mode) {
            TransformMode.MOVE ->
                moveStepInBlenderUnits(local.value.moveStepValue, local.value.moveStepUnit, scaleLength)
            TransformMode.SCALE -> scaleStepForWire(local.value.scaleStepValue, local.value.scaleUnit, scaleLength)
            TransformMode.ROTATE -> null
        } ?: stepInBlenderUnits(preset, mode, scaleLength)
        val constraint = if (mode == TransformMode.ROTATE && local.value.constraint.axes.size > 1) {
            // Un giro es alrededor de UN eje: un plano elegido para mover no vale.
            Constraint.Z
        } else {
            local.value.constraint
        }
        val snapType = snapTypeFor(mode)
        if (mode != TransformMode.MOVE && snapType.geometric) {
            lastReferencePointer = null
            local.update { it.copy(referencePicking = true, referenceRole = "SOURCE") }
        }
        client.transformBegin(
            mode, constraint.axes, step = step,
            snapType = snapType,
            orientation = local.value.orientation,
            valueMode = local.value.valueMode,
            scaleStepUnit = if (mode == TransformMode.SCALE) local.value.scaleUnit.scaleStepWireUnit else null,
        )
    }

    fun activateTweak() {
        closeTransformForToolChange()
        if (client.toolSession.value.active || client.toolSession.value.armed) client.toolCancel()
        loopCutArmed = false
        local.update { it.copy(activeTool = ActiveTool.TWEAK, loopCutAwaitingTap = false,
            shapeTool = ShapeTool.NONE, referencePicking = false) }
    }

    private var tweakGestureActive = false

    private fun cancelTweakGesture(): Boolean {
        if (!tweakGestureActive) return false
        tweakGestureActive = false
        client.selectionTweak(GesturePhase.CANCEL, 0.0, 0.0, 0.0, 0.0, null)
        return true
    }

    fun tweakGesture(phase: GesturePhase, u: Float, v: Float, dx: Float, dy: Float) {
        if (local.value.activeTool != ActiveTool.TWEAK) {
            cancelTweakGesture()
            return
        }
        if (phase == GesturePhase.BEGIN) tweakGestureActive = true
        else if (!tweakGestureActive) return
        // Los ajustes solo acompañan al BEGIN: el servidor los conserva hasta soltar.
        val settings = if (phase == GesturePhase.BEGIN) local.value.tweak.let {
            if (uiState.value.blender.selectionMode == SelectionMode.FACE)
                it.copy(motion = TweakMotion.FREE) else it
        } else null
        client.selectionTweak(phase, u.toDouble(), v.toDouble(), dx.toDouble(), dy.toDouble(), settings)
        if (phase == GesturePhase.END || phase == GesturePhase.CANCEL) {
            tweakGestureActive = false
            client.requestState()
        }
    }

    /** Las ayudas cambian el siguiente gesto; nunca activan ni reabren la herramienta. */
    private fun updateTweakSettings(change: (TweakSettings) -> TweakSettings) {
        if (local.value.activeTool != ActiveTool.TWEAK) return
        cancelTweakGesture()
        local.update { it.copy(tweak = change(it.tweak)) }
    }

    fun setTweakMotion(motion: TweakMotion) = updateTweakSettings { it.copy(motion = motion) }

    fun setTweakSnapType(snapType: SnapType) = updateTweakSettings { it.copy(snapType = snapType) }

    fun setTweakSnapStep(step: Double) {
        if (!step.isFinite() || step <= 0.0) return
        updateTweakSettings { it.copy(snapStep = step) }
    }

    fun toggleTweakClamp() = updateTweakSettings { it.copy(clamp = !it.clamp) }

    /**
     * El snap elegido, recortado a lo que admite el modo anunciado.
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
     * Elige la orientación en vivo conservando session_id, valores y referencias.
     */
    fun setOrientation(orientation: Orientation) {
        local.update { it.copy(orientation = orientation) }
        val session = client.transformSession.value
        if (session.active) client.transformOrientation(orientation)
    }

    /** Elige el tipo de snap. Con sesión abierta se aplica en vivo. */
    fun setSnapType(type: SnapType) {
        rememberSnapType(type)
        val session = client.transformSession.value
        if (session.active) {
            client.transformSnap(snapTypeFor(session.mode), session.step, session.snapToSelection)
            if (session.mode != TransformMode.MOVE && type.geometric && session.source.isEmpty()) {
                lastReferencePointer = null
                local.update { it.copy(referencePicking = true, referenceRole = "SOURCE") }
            }
        }
    }

    fun setStep(mode: TransformMode, index: Int) {
        local.update { it.copy(stepIndex = it.stepIndex + (mode to index)) }
        val session = client.transformSession.value
        if (session.active) {
            val preset = stepsFor(mode)[index]
            client.transformSnap(
                session.snapType,
                stepInBlenderUnits(preset, mode, uiState.value.blender.unitScaleLength),
                session.snapToSelection,
            )
        }
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
                scaleStepUnit = if (session.mode == TransformMode.SCALE) local.value.scaleUnit.scaleStepWireUnit else null,
            )
        }
    }

    fun stepIndex(mode: TransformMode) = localStepIndex(mode)

    private fun localStepIndex(mode: TransformMode) =
        local.value.stepIndex[mode] ?: defaultStepIndex(mode)

    fun transformValue(values: List<Double>?, angleDegrees: Double?, dimensions: List<Double>?) =
        client.transformValue(values, angleDegrees, dimensions)

    fun toggleTransformReference(role: String) {
        local.update { it.copy(transformSelectionSessionId = null) }
        val session = client.transformSession.value
        if (!session.active) return
        val normalized = if (session.mode == TransformMode.MOVE) "SOURCE" else role
        val roleAlreadyLocked = if (normalized == "CENTER") session.centerLocked else session.sourceLocked
        if (roleAlreadyLocked && !local.value.referencePicking) {
            client.transformReferenceClear(normalized)
        } else {
            lastReferencePointer = null
            local.update { it.copy(referencePicking = !it.referencePicking, referenceRole = normalized) }
        }
    }

    private fun choosingTransformSelection(): Boolean {
        val session = client.transformSession.value
        return session.active && session.sessionId == local.value.transformSelectionSessionId
    }

    fun chooseTransformSelection() {
        val session = client.transformSession.value
        if (!session.active || client.state.value.mode != BlenderMode.EDIT) return
        local.update { it.copy(
            transformSelectionSessionId = if (choosingTransformSelection()) null else session.sessionId,
            referencePicking = false,
        ) }
    }

    fun flattenScaleAxis(axis: String) {
        if (client.transformSession.value.mode != TransformMode.SCALE || !client.transformSession.value.active) return
        local.update { it.copy(referencePicking = false) }
        client.transformFlatten(axis)
    }

    fun setTransformCenterPreset(preset: String) {
        if (!client.transformSession.value.active) return
        lastReferencePointer = null
        local.update { it.copy(referencePicking = false, referenceRole = "CENTER") }
        client.transformCenterPreset(preset)
    }

    fun setMoveStep(value: Double, unit: TransformStepUnit) {
        if (value <= 0.0) return
        local.update { it.copy(moveStepValue = value, moveStepUnit = unit) }
        val session = client.transformSession.value
        if (!session.active || session.mode != TransformMode.MOVE) return
        val blenderStep = moveStepInBlenderUnits(value, unit, uiState.value.blender.unitScaleLength)
            ?: ((session.referenceDistance ?: return) * value / 100.0)
        client.transformSnap(SnapType.INCREMENT, blenderStep, session.snapToSelection)
    }

    /** Una sola unidad para dimensiones, botones e incremento de Escalar. */
    fun setScaleStep(value: Double, unit: TransformStepUnit) {
        if (!value.isFinite() || value <= 0.0) return
        local.update { it.copy(scaleStepValue = value, scaleUnit = unit) }
        val session = client.transformSession.value
        if (!session.active || session.mode != TransformMode.SCALE) return
        client.transformSnap(
            session.snapType,
            scaleStepForWire(value, unit, client.state.value.unitScaleLength),
            session.snapToSelection, unit.scaleStepWireUnit,
        )
    }

    fun setSnapToSelection(enabled: Boolean) {
        val session = client.transformSession.value
        if (!session.active) return
        client.transformSnap(session.snapType, session.step, enabled)
    }

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
    fun viewGesture(gesture: Gesture, phase: GesturePhase, dx: Float, dy: Float, factor: Float) {
        client.gesture(gesture, phase, dx.toDouble(), dy.toDouble(), factor.toDouble())
        if ((phase == GesturePhase.END || phase == GesturePhase.CANCEL) &&
            client.toolSession.value.tool == EditTool.KNIFE
        ) client.requestToolStatus()
    }

    /**
     * Arrastre de un dedo/stylus: se traduce al gesto de la herramienta activa.
     * El servidor lo agrupa y cierra un único paso de undo al soltar.
     */
    fun toolGesture(phase: GesturePhase, dx: Float, dy: Float) {
        if (choosingTransformSelection()) return
        if (client.toolSession.value.armed && client.toolSession.value.input == "REPEAT_TAP") return
        if (client.state.value.cad.workspace) {
            client.gesture(Gesture.ORBIT, phase, dx.toDouble(), dy.toDouble())
            return
        }
        val surfaceTool = client.toolSession.value
        if (surfaceTool.active && surfaceTool.input == "FACE_PAIR") {
            if (phase == GesturePhase.BEGIN) {
                facePickRole = surfaceTool.parameters["pick_role"] as? String ?: "SOURCE"
                lastFacePointer = null
            } else if (phase == GesturePhase.END || phase == GesturePhase.CANCEL) {
                val pointer = lastFacePointer ?: (0f to 0f)
                client.toolFacePick(pointer.first.toDouble(), pointer.second.toDouble(), facePickRole ?:
                    (surfaceTool.parameters["pick_role"] as? String ?: "SOURCE"), phase.name)
                facePickRole = null
                lastFacePointer = null
            }
            return
        }
        // Con una herramienta paramétrica abierta, el arrastre la alimenta a ella:
        // sube/baja el parámetro primario (offset, grosor o cortes) y no orbita.
        val tool = client.toolSession.value
        if (tool.active) {
            if (tool.acceptsViewportNudge && !tool.snapType.geometric &&
                (phase == GesturePhase.UPDATE || phase == GesturePhase.END)
            ) {
                client.toolNudge(tool.viewportNudge(dy.toDouble()))
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
            if (local.value.referencePicking) {
                if (phase == GesturePhase.END) {
                    lastReferencePointer?.let { (u, v) ->
                        client.transformReferenceCandidate(
                            u.toDouble(), v.toDouble(), lock = true,
                            role = local.value.referenceRole,
                        )
                    }
                    local.update { it.copy(referencePicking = false) }
                }
                return
            }
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
