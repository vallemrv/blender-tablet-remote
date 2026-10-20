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
import com.blendertablet.remote.model.ProportionalFalloffs
import com.blendertablet.remote.model.ActiveTool
import com.blendertablet.remote.model.Axis
import com.blendertablet.remote.model.AppUiState
import com.blendertablet.remote.model.BlenderMode
import com.blendertablet.remote.model.BlenderState
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
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.Base64
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
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
    private val resumePreferences = application.getSharedPreferences("workspace_resume", android.content.Context.MODE_PRIVATE)
    private val sessionKey = resumePreferences.getString("session_key", null) ?: java.util.UUID.randomUUID().toString().also {
        resumePreferences.edit().putString("session_key", it).apply()
    }
    private val client: RemoteBlenderClient = WebSocketRemoteBlenderClient(viewModelScope, sessionKey)
    private val snapPreferences = SnapPreferences(application)
    private val toolPreferences = com.blendertablet.remote.data.ToolPreferences(application)
    private val centerPreferences = com.blendertablet.remote.data.TransformCenterPreferences(application)
    private val duplicatePreferences = com.blendertablet.remote.data.DuplicatePreferences(application)
    private val local = MutableStateFlow(AppUiState(
        duplicateLinked = duplicatePreferences.linked,
        duplicateMode = duplicatePreferences.mode,
        snapType = snapPreferences.current.type,
        snapStep = snapPreferences.current.step,
        distanceStepMeters = snapPreferences.current.distanceStepMeters,
    ))
    private val preferences = ConnectionPreferences(application)
    private val stream = ViewportStream(viewModelScope)
    private var currentStreamEndpoint: com.blendertablet.remote.network.StreamEndpoint? = null
    private var videoForeground = true
    private val _h264Active = MutableStateFlow(false)
    val h264Active: StateFlow<Boolean> = _h264Active
    private val h264Stream = H264ViewportStream(viewModelScope) { fallbackToMjpeg() }
    val h264Size = h264Stream.size
    private var cadStroke = false
    private var facePickRole: String? = null
    private var lastFacePointer: Pair<Float, Float>? = null
    private var lastReferencePointer: Pair<Float, Float>? = null
    private var pendingCenterPreset: String? = null
    /** Punto donde bajó el dedo del arrastre en curso: BEGIN del manipulador. */
    private var dragStartPoint: Pair<Float, Float>? = null
    /** El arrastre de un dedo pertenece al manipulador (o a su órbita si no tocó asa). */
    private var gizmoDragActive = false
    private var selectionPaintId: String? = null
    private var gizmoPendingDx = 0f
    private var gizmoPendingDy = 0f
    private var gizmoLastPointer: Pair<Float, Float>? = null
    /** Último toque de selección en Edit (u, v, uptime) para reconocer el doble toque. */
    private var lastEditTap: Triple<Float, Float, Long>? = null
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
            client.errors.collect { error ->
                if (error != null && !client.toolSession.value.active && !client.toolSession.value.armed && !client.transformSession.value.active) {
                    local.update { it.copy(activeTool = ActiveTool.SELECT, shapeTool = ShapeTool.NONE, loopCutAwaitingTap = false) }
                }
            }
        }
        viewModelScope.launch {
            combine(client.connection, client.state) { connection, state ->
                connection == ConnectionStatus.CONNECTED && state.features.cad.available
            }.distinctUntilChanged().collect { ready ->
                cadStroke = false
                if (ready) client.cadCommand("cad.state")
            }
        }

        viewModelScope.launch {
            client.transformSession.collect { session ->
                val center = com.blendertablet.remote.model.TransformCenter.from(session, client.state.value.sceneScale.sceneId)
                if (center != null && (pendingCenterPreset == null || center.mode == pendingCenterPreset)) {
                    pendingCenterPreset = null
                    centerPreferences.save(center)
                }
            }
        }

        // La copia nace encima del original y no se ve. Como el Shift+D de Blender, se
        // entrega con Mover o Rotar según la intención elegida al duplicar.
        // Cancelar la transformación no deshace el duplicado: son pasos distintos.
        viewModelScope.launch {
            client.duplicates.collect { mode -> transformBegin(mode) }
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
        // El manipulador solo se dibuja cuando el arrastre de un dedo le pertenece.
        viewModelScope.launch {
            combine(client.connection, client.state, local) { status, remote, ui ->
                (status == ConnectionStatus.CONNECTED && remote.features.gizmo) to gizmoWanted(remote, ui)
            }.distinctUntilChanged().collect { (connected, wanted) ->
                if (connected) client.gizmoSet(wanted)
            }
        }
        // Cada escena arranca con sus propios pasos. Los ajustes manuales siguen
        // vivos mientras su identidad no cambie, también al reconectar.
        viewModelScope.launch {
            client.state.map { it.sceneScale }.distinctUntilChanged { old, new -> old.sceneId == new.sceneId }
                .collect { scale ->
                    if (scale.sceneId.isNotEmpty()) {
                        val unit = scale.lengthUnit.transformStepUnit()
                        local.update { it.copy(moveStepUnit = unit, scaleUnit = unit, gizmoEnabled = false) }
                        rememberSnapStep(scale.snapStep / client.state.value.unitScaleLength.coerceAtLeast(1e-12))
                        rememberDistanceStep(scale.snapStep)
                    }
                }
        }
        // Las unidades de Mover y Escalar siguen al preset real de la escena. Se observa
        // también al abrir otro .blend, no solo cuando el usuario toca el menú.
        viewModelScope.launch {
            client.state.map { it.sceneScale.lengthUnit }.distinctUntilChanged().collect { unit ->
                val stepUnit = unit.transformStepUnit()
                val shared = local.value.distanceStepMeters
                local.update { it.copy(
                    moveStepUnit = stepUnit,
                    moveStepValue = shared?.let { meters -> meters / stepUnit.meters } ?: it.moveStepValue,
                ) }
                applyScaleStep(shared?.let { it / stepUnit.meters } ?: local.value.scaleStepValue, stepUnit)
            }
        }
        // El catálogo de escalas no viaja en el snapshot (es fijo) y Nueva escena
        // lo necesita: se pide una vez por conexión, cuando ya se sabe si el servidor
        // lo soporta. Mismo motivo que los overlays de arriba.
        viewModelScope.launch {
            combine(client.connection, client.state) { status, remote ->
                status == ConnectionStatus.CONNECTED && remote.features.sceneScale
            }.distinctUntilChanged().collect { ready ->
                if (ready) client.requestSceneScales()
            }
        }
        // El puerto del vídeo lo anuncia el servidor en el "hello": el usuario solo
        // configura el de control y el vídeo se engancha solo (§63).
        viewModelScope.launch {
            client.toolSession.collect { session ->
                if (session.armed && !session.active && session.tool != EditTool.F2) toolPreferences.save(session.tool, session.parameters, client.state.value.unitScaleLength)
                if (session.active) local.update { it.copy(loopCutAwaitingTap = false) }
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
                    if (videoForeground) stream.start(endpoint.host, endpoint.port, endpoint.token, endpoint.path)
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
        videoForeground = true
        currentStreamEndpoint?.let { endpoint ->
            if (endpoint.format == "h264" && endpoint.framing == H264Framing.NAME) {
                // Fallback removed the SurfaceView. Recreate it before retrying AVC;
                // receiving the same dimensions again cannot signal recovery.
                stream.stop()
                _h264Active.value = true
            } else stream.start(endpoint.host, endpoint.port, endpoint.token, endpoint.path)
        }
        h264Stream.resume()
        client.retryNow()
    }

    /** Detiene MediaCodec antes de que Android invalide los buffers de la Surface. */
    fun onBackground() {
        videoForeground = false
        cancelCadStroke(); cancelMaterialStroke(); cancelSculptStroke()
        closeSessions()
        local.update { it.copy(activeTool = ActiveTool.SELECT, shapeTool = ShapeTool.NONE, referencePicking = false) }
        h264Stream.pause(); stream.stop()
    }

    fun disconnect() {
        closeSessions()
        local.update { it.copy(activeTool = ActiveTool.SELECT, shapeTool = ShapeTool.NONE) }
        cancelMaterialStroke()
        cancelSculptStroke()
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
     * al volver a primer plano se recrea la Surface y se reintenta H.264.
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
        closeSessions(commit = true)
        local.update { it.copy(activeTool = ActiveTool.SELECT, shapeTool = ShapeTool.NONE) }
    }
    /**
     * Cambiar de modo o de submodo invalida lo que hubiera abierto: una extrusión
     * de caras no significa nada en cuanto se pasa a vértices, y el servidor
     * respondería `session_invalidated` a mitad de un arrastre. Se descarta antes de
     * cambiar, que es la salida no destructiva.
     */
    fun enterCad() {
        cancelMaterialStroke()
        cancelSculptStroke()
        if (!client.state.value.features.cad.available) return
        closeSessions(commit = true)
        local.update { it.copy(activeTool = ActiveTool.SELECT, shapeTool = ShapeTool.NONE,
            referencePicking = false, cadTool = null, shortestPathActive = false) }
        client.cadCommand("mode.set", mapOf("mode" to "CAD"))
    }
    fun cadCommand(name: String, payload: Map<String, Any?> = emptyMap()) {
        if (!client.state.value.cad.workspace) return
        cancelCadStroke()
        local.update { it.copy(cadFacePick = null, cadParameterPick = null, cadParameterFeature = null) }
        client.cadCommand(name, payload)
    }
    fun cadPickParameter(key: String, feature: String) {
        cancelCadStroke()
        local.update { it.copy(cadFacePick = null, cadParameterPick = key, cadParameterFeature = feature) }
    }
    /** Hasta cara: el siguiente toque elige la cara plana donde termina la extrusión. */
    fun cadPickEndFace(target: String?) {
        cancelCadStroke()
        local.update { it.copy(cadFacePick = target) }
    }
    fun cadNgonSides(sides: Int) {
        local.update { it.copy(cadNgonSides = sides.coerceIn(3, 32)) }
    }

    fun cadGearTeeth(teeth: Int) {
        local.update { it.copy(cadGearTeeth = teeth.coerceIn(6, 150)) }
    }

    fun cadTool(type: String?) {
        cancelCadStroke()
        local.update { it.copy(cadFacePick = null, cadParameterPick = null, cadParameterFeature = null) }
        if (client.state.value.cad.surface.mode != "PROFILE") client.cadCommand("cad.surface.mode", mapOf("mode" to "PROFILE"))
        local.update { it.copy(cadTool = type?.takeIf { candidate -> candidate in client.state.value.features.cad.entities || (candidate == "TRIM" && client.state.value.features.cad.entityTrim) }) }
    }
    fun cadSurfaceMode(mode: String) {
        cancelCadStroke()
        local.update { it.copy(cadTool = null) }
        client.cadCommand("cad.surface.mode", mapOf("mode" to mode))
    }
    private var cadGestureMode: String? = null
    private var cadDepthStart = .02
    private var cadShiftStart = listOf(0.0, 0.0)
    private var cadPointerStartU = 0f
    private var cadPointerStartV = 0f
    private fun cancelCadStroke() {
        if (cadStroke) {
            cadStroke = false
            if (cadGestureMode == "DEPTH") client.cadCommand("cad.extrude.update", mapOf("depth" to cadDepthStart))
            else if (cadGestureMode == "PLANE") client.cadCommand("cad.plane.update", mapOf("offset" to cadDepthStart, "shift" to cadShiftStart, "release" to true))
            else if (cadGestureMode == "SHELL") client.cadCommand("cad.shell.update", mapOf("thickness" to cadDepthStart))
            else if (cadGestureMode == "FINISH") client.cadCommand("cad.finish.update", mapOf("width" to cadDepthStart))
            else if (cadGestureMode != "FACE") client.cadCommand("cad.session.cancel")
            cadGestureMode = null
        }
    }
    fun cadGesture(phase: GesturePhase, u: Float, v: Float) {
        if (!client.state.value.cad.workspace) { cadStroke = false; cadGestureMode = null; return }
        when (phase) {
            GesturePhase.BEGIN -> {
                val cad = client.state.value.cad
                cadPointerStartU = u
                cadPointerStartV = v
                if (cad.sessionActive && cad.operation in listOf("EXTRUDE", "CUT") && local.value.cadFacePick == "SESSION") {
                    cadStroke = true; cadGestureMode = "FACE"
                    return
                }
                if (cad.sessionActive && cad.operation in listOf("EXTRUDE", "CUT")) {
                    if (cad.extent == "THROUGH_ALL") {
                        cadStroke = false; cadGestureMode = null
                        return
                    }
                    cadStroke = true; cadGestureMode = "DEPTH"; cadDepthStart = cad.depth
                    return
                }
                if (cad.sessionActive && cad.operation in listOf("PLANE", "SPLIT")) {
                    // El lápiz agarra la flecha que toca (o la normal) y la sigue 1:1 bajo la punta.
                    cadStroke = true; cadGestureMode = "PLANE"; cadDepthStart = cad.plane?.offset ?: 0.0
                    cadShiftStart = cad.plane?.shift ?: listOf(0.0, 0.0)
                    client.cadCommand("cad.plane.update", mapOf("grab_u" to u, "grab_v" to v))
                    return
                }
                if (cad.sessionActive && cad.operation == "SHELL") {
                    cadStroke = true; cadGestureMode = "SHELL"; cadDepthStart = cad.thickness
                    return
                }
                if (cad.sessionActive && cad.operation in listOf("FILLET", "CHAMFER")) {
                    // Como Extruir: deslizar arriba/abajo cambia el ancho por pasos.
                    cadStroke = true; cadGestureMode = "FINISH"; cadDepthStart = cad.width
                    return
                }
                val type = local.value.cadTool
                if (cad.activeSketchId == null || cad.surface.mode != "PROFILE") return
                cadStroke = true
                // Con Arco armado, apoyar sobre el rombo de un arco ajusta su ángulo
                // en vez de empezar otro; el resto del lienzo sigue dibujando arcos.
                val angleHandle = type == "ARC" && cad.overlay.any { item ->
                    item.handles.any { it.intent == "ANGLE" && kotlin.math.hypot(it.point.first - u, it.point.second - v) < .025f }
                }
                cadGestureMode = when {
                    type == null || angleHandle -> "DRAG"
                    type == "TRIM" -> "TRIM"
                    type == "POLYGON" -> "POLY"
                    else -> "DRAW"
                }
                client.cadCommand(when (cadGestureMode) {
                    "TRIM" -> "cad.entity.trim"
                    "DRAG" -> "cad.drag.begin"
                    "POLY" -> "cad.polygon.begin"
                    else -> "cad.entity.begin"
                }, if (cadGestureMode == "TRIM") mapOf("phase" to "BEGIN", "u" to u, "v" to v) else if (cadGestureMode == "DRAG") mapOf("u" to u, "v" to v, "additive" to true) else when (type) {
                    null -> mapOf("u" to u, "v" to v)
                    "NGON" -> mapOf("type" to type, "sides" to local.value.cadNgonSides, "u" to u, "v" to v)
                    "GEAR" -> mapOf("type" to type, "teeth" to local.value.cadGearTeeth, "u" to u, "v" to v)
                    else -> mapOf("type" to type, "u" to u, "v" to v)
                })
            }
            GesturePhase.UPDATE -> if (cadStroke) {
                when (cadGestureMode) {
                    "DEPTH" -> client.cadCommand("cad.extrude.update", mapOf(
                        "gesture_u" to (u - cadPointerStartU), "gesture_v" to (v - cadPointerStartV),
                        "u" to u, "v" to v, "baseline_depth" to cadDepthStart))
                    "SHELL" -> client.cadCommand("cad.shell.update", mapOf("gesture" to (cadPointerStartV - v), "baseline_thickness" to cadDepthStart))
                    "FINISH" -> client.cadCommand("cad.finish.update", mapOf("gesture" to (cadPointerStartV - v), "baseline_width" to cadDepthStart))
                    "PLANE" -> client.cadCommand("cad.plane.update", mapOf("gesture_u" to (u - cadPointerStartU),
                        "gesture_v" to (v - cadPointerStartV), "u" to u, "v" to v, "baseline_offset" to cadDepthStart))
                    "TRIM" -> client.cadCommand("cad.entity.trim", mapOf("phase" to "UPDATE", "u" to u, "v" to v))
                    "DRAG" -> client.cadCommand("cad.drag.update", mapOf("u" to u, "v" to v))
                    "POLY" -> client.cadCommand("cad.polygon.update", mapOf("u" to u, "v" to v))
                    "DRAW" -> client.cadCommand("cad.entity.update", mapOf("u" to u, "v" to v))
                }
            }
            GesturePhase.END -> if (cadStroke) {
                cadStroke = false
                when (cadGestureMode) {
                    "DEPTH" -> client.cadCommand("cad.extrude.update", mapOf("settle" to true))
                    "PLANE" -> client.cadCommand("cad.plane.update", mapOf("release" to true))
                    "FACE" -> {
                        // La cara se sondea donde bajó el dedo, no donde se levantó.
                        local.update { it.copy(cadFacePick = null, cadParameterPick = null, cadParameterFeature = null) }
                        client.cadCommand("cad.extrude.update", mapOf("extent" to "TO_FACE",
                            "u" to cadPointerStartU, "v" to cadPointerStartV))
                    }
                    "TRIM" -> client.cadCommand("cad.entity.trim", mapOf("phase" to "END"))
                    "DRAG" -> client.cadCommand("cad.drag.end")
                    "POLY" -> client.cadCommand("cad.polygon.segment", mapOf("u" to u, "v" to v))
                    "DRAW" -> client.cadCommand("cad.session.confirm")
                }
                cadGestureMode = null
            }
            GesturePhase.CANCEL -> cancelCadStroke()
        }
    }

    val capturePng = client.capturePng
    fun clearCapture() = client.clearCapture()
    fun captureScene() { client.captureScene() }

    /**
     * Envía una imagen del tablero a Blender. PNG si tiene transparencia, JPEG si no;
     * se reduce hasta caber en un mensaje de control (base64 < 7 MB).
     */
    fun sendReferenceToBlender(path: String, name: String, opacity: Float) {
        viewModelScope.launch {
            // El panel ya decodificó esta copia privada; si desaparece, no hay nada que enviar.
            val encoded = withContext(Dispatchers.IO) { encodeReference(path) } ?: return@launch
            client.referenceAdd(name.substringBeforeLast('.'), encoded.first, encoded.second, opacity)
        }
    }

    private fun encodeReference(path: String): Pair<String, String>? {
        var bitmap = BitmapFactory.decodeFile(path) ?: return null
        val png = bitmap.hasAlpha()
        while (true) {
            val bytes = java.io.ByteArrayOutputStream().use { output ->
                bitmap.compress(if (png) Bitmap.CompressFormat.PNG else Bitmap.CompressFormat.JPEG, 92, output)
                output.toByteArray()
            }
            val text = Base64.encodeToString(bytes, Base64.NO_WRAP)
            if (text.length < 7_000_000 || maxOf(bitmap.width, bitmap.height) < 256) {
                return (if (png) "png" else "jpg") to text
            }
            bitmap = Bitmap.createScaledBitmap(bitmap, bitmap.width * 3 / 4, bitmap.height * 3 / 4, true)
        }
    }
    private var materialStrokeId: String? = null
    private var materialLightId: String? = null

    fun materialLightGesture(phase: GesturePhase, rotation: Float, energy: Float = 0f) {
        if (phase == GesturePhase.BEGIN) {
            if (!client.state.value.material.active || client.state.value.material.interaction != "LIGHTS") return
            cancelMaterialStroke()
            materialLightId = java.util.UUID.randomUUID().toString()
        }
        val id = materialLightId ?: return
        client.materialCommand("material.lighting", mapOf("phase" to phase.name.lowercase(), "gesture_id" to id,
            "rotation" to rotation, "energy" to energy))
        if (phase == GesturePhase.END || phase == GesturePhase.CANCEL) materialLightId = null
    }
    fun enterMaterials() {
        cancelSculptStroke(); cancelCadStroke(); closeSessions(commit = true); cancelMaterialStroke()
        local.update { it.copy(activeTool = ActiveTool.SELECT, shapeTool = ShapeTool.NONE, cadTool = null) }
        client.materialCommand("mode.set", mapOf("mode" to "MATERIAL"))
    }
    fun materialCommand(name: String, values: Map<String, Any?> = emptyMap()) {
        cancelMaterialStroke()
        client.materialCommand(name, values)
    }
    fun materialSettings(values: Map<String, Any?>) = materialCommand("material.settings", values)
    fun toggleMaterialStylus() { cancelMaterialStroke(); local.update { it.copy(materialStylusOnly = !it.materialStylusOnly) } }
    private fun cancelMaterialStroke() {
        materialLightGesture(GesturePhase.CANCEL, 0f, 0f)
        val id = materialStrokeId ?: return
        materialStrokeId = null
        client.materialCommand("material.stroke", mapOf("phase" to "cancel", "stroke_id" to id))
    }
    private fun materialStroke(phase: GesturePhase, points: List<com.blendertablet.remote.model.SculptPoint>) {
        val material = client.state.value.material
        if (!material.paintReady || material.paintBlocked || material.interaction != "PAINT") return
        if (phase == GesturePhase.BEGIN) { cancelMaterialStroke(); materialStrokeId = java.util.UUID.randomUUID().toString() }
        val id = materialStrokeId ?: return
        client.materialCommand("material.stroke", mapOf("phase" to phase.name.lowercase(), "stroke_id" to id, "points" to points.map { it.wire() }))
        if (phase == GesturePhase.END || phase == GesturePhase.CANCEL) materialStrokeId = null
    }
    private var sculptStrokeId: String? = null
    fun sculptSettings(values: Map<String, Any?>) {
        cancelSculptStroke()
        client.sculptCommand("sculpt.settings", values)
    }
    fun sculptCommand(name: String, values: Map<String, Any?> = emptyMap()) {
        cancelSculptStroke()
        client.sculptCommand(name, values)
    }
    fun toggleSculptSmooth() { cancelSculptStroke(); local.update { it.copy(sculptSmooth = !it.sculptSmooth) } }
    fun toggleSculptInvert() { cancelSculptStroke(); local.update { it.copy(sculptInvert = !it.sculptInvert) } }
    fun toggleSculptStylusOnly() { cancelSculptStroke(); local.update { it.copy(sculptStylusOnly = !it.sculptStylusOnly) } }
    private fun cancelSculptStroke() {
        val id = sculptStrokeId ?: return
        sculptStrokeId = null
        client.sculptCommand("sculpt.stroke", mapOf("phase" to "cancel", "stroke_id" to id, "points" to emptyList<Any>()))
    }
    fun sculptStroke(phase: GesturePhase, points: List<com.blendertablet.remote.model.SculptPoint>, smooth: Boolean, invert: Boolean) {
        if (client.state.value.material.active) { materialStroke(phase, points); return }
        if (client.connection.value != ConnectionStatus.CONNECTED || client.state.value.mode != BlenderMode.SCULPT) return
        if (phase == GesturePhase.BEGIN) {
            cancelSculptStroke()
            sculptStrokeId = java.util.UUID.randomUUID().toString()
        }
        val id = sculptStrokeId ?: return
        client.sculptCommand("sculpt.stroke", mapOf("phase" to phase.name.lowercase(), "stroke_id" to id,
            "points" to points.map { it.wire() }, "smooth" to (smooth || local.value.sculptSmooth),
            "invert" to (invert || local.value.sculptInvert)))
        if (phase == GesturePhase.END || phase == GesturePhase.CANCEL) sculptStrokeId = null
    }

    fun setMode(mode: BlenderMode) {
        cancelMaterialStroke()
        cancelSculptStroke()
        cancelCadStroke()
        local.update { it.copy(cadTool = null) }
        closeSessions(commit = true)
        local.update { it.copy(
            shapeTool = ShapeTool.NONE,
            activeTool = ActiveTool.SELECT,
            shortestPathActive = if (mode == BlenderMode.EDIT) it.shortestPathActive else false,
        ) }
        client.setMode(mode)
    }

    fun setSelectionMode(mode: SelectionMode) {
        val f2 = client.toolSession.value.armed && client.toolSession.value.tool == EditTool.F2
        closeSessions(commit = true)
        local.update { it.copy(shapeTool = ShapeTool.NONE, activeTool = if (f2) ActiveTool.SELECT else it.activeTool) }
        client.setSelectionMode(mode)
        if (f2 && mode != SelectionMode.FACE) {
            local.update { it.copy(activeTool = ActiveTool.F2) }
            client.toolBegin(EditTool.F2, emptyMap())
        }
    }

    private fun closeTransformForToolChange() {
        cancelTweakGesture()
        val tool = client.toolSession.value
        if (tool.active) toolPreferences.save(tool.tool, tool.parameters, client.state.value.unitScaleLength)
        if (client.connection.value == ConnectionStatus.CONNECTED) client.finishInteraction()
    }

    private fun closeSessions(commit: Boolean = false) {
        if (commit) closeTransformForToolChange()
        else {
            val wasTweak = local.value.activeTool == ActiveTool.TWEAK
            val cancelled = cancelTweakGesture()
            if (client.connection.value == ConnectionStatus.CONNECTED) {
                if (!wasTweak && !cancelled) client.transformCancel()
                client.toolCancel()
            }
        }
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
    fun undo() { cancelMaterialStroke(); cancelSculptStroke(); cancelCadStroke(); client.undo() }
    fun redo() { cancelMaterialStroke(); cancelSculptStroke(); cancelCadStroke(); client.redo() }
    fun repeatLast() = client.repeatLast()
    fun delete() {
        cancelMaterialStroke(); cancelSculptStroke()
        if (client.state.value.material.active) {
            client.editCatalogCommand("object.delete", mapOf("objects" to client.state.value.material.targets))
            materialCommand("material.select", mapOf("objects" to emptyList<String>())); return
        }
        if (client.state.value.mode == BlenderMode.SCULPT) client.setMode(BlenderMode.OBJECT)
        val cad = client.state.value.cad
        if (cad.workspace) {
            if (cad.surface.mode != "PROFILE") { cadCommand("cad.surface.clear"); return }
            if (cad.activeSketchId != null) {
                if (cad.selectionKind == "CONSTRAINT") {
                    cadCommand("cad.constraint.delete", mapOf("constraint_id" to cad.selectionId)); return
                }
                val rounding = cad.selectedEntity?.takeIf { it.isFillet && cad.selection.map { ref -> ref.id }.distinct().size == 1 }
                if (rounding != null) cadCommand("cad.fillet.remove", mapOf("entity_id" to rounding.id))
                else cadCommand("cad.entity.delete")
            }
            else if (cad.selectedFeature != null) cadCommand("cad.feature.delete", mapOf("feature_id" to cad.selectedFeature!!.id))
            else cad.selectedSketch?.let { sketch ->
                if (cad.selectionKind == "PROFILE") cadCommand("cad.entity.delete", mapOf("profile_ids" to cad.selection.map { it.id }.ifEmpty { listOfNotNull(cad.selectionId) }))
                else cadCommand("cad.sketch.delete", mapOf("sketch_id" to sketch.id))
            }
        } else client.delete()
    }
    fun duplicate(mode: TransformMode, linked: Boolean) {
        if (client.connection.value != ConnectionStatus.CONNECTED || client.state.value.cad.workspace ||
            client.state.value.mode !in setOf(BlenderMode.OBJECT, BlenderMode.EDIT)) return
        val edit = client.state.value.mode == BlenderMode.EDIT
        val rememberedLinked = if (edit) local.value.duplicateLinked else linked
        cancelTweakGesture()
        closeTransformForToolChange()
        duplicatePreferences.save(mode, rememberedLinked)
        local.update { it.copy(duplicateLinked = rememberedLinked, duplicateMode = mode,
            activeTool = ActiveTool.SELECT, shapeTool = ShapeTool.NONE, loopCutAwaitingTap = false) }
        client.duplicate(mode, linked && !edit)
    }
    fun frameSelected() {
        if (client.state.value.cad.workspace) cadCommand("cad.view.frame") else client.frameSelected()
    }
    /**
     * Un toque en el viewport. Normalmente selecciona, pero con una transformación
     * abierta y un snap geométrico elegido significa "pega el movimiento a esto":
     * el toque fija el destino. En Edit también permite continuar en otra selección
     * confirmando el paso anterior.
     */
    fun pick(u: Float, v: Float, stylus: Boolean = false) {
        if (client.state.value.material.active) {
            if (client.state.value.material.interaction == "SELECT")
                materialCommand("material.select", mapOf("u" to u, "v" to v, "additive" to true))
            return
        }
        if (client.state.value.cad.workspace) {
            val parameter = local.value.cadParameterPick
            if (parameter != null) {
                val feature = local.value.cadParameterFeature
                local.update { it.copy(cadParameterPick = null, cadParameterFeature = null) }
                if (feature?.startsWith("COMBINE:") == true) {
                    client.cadCommand("cad.combine.begin", mapOf("body_id" to feature.removePrefix("COMBINE:"), "u" to u, "v" to v))
                    return
                }
                client.cadCommand(if (feature == "SESSION") "cad.operation.update" else "cad.feature.set",
                    mapOf(parameter to true, "feature_id" to feature, "u" to u, "v" to v))
                return
            }
            val endFace = local.value.cadFacePick
            if (endFace != null && endFace != "SESSION") {
                local.update { it.copy(cadFacePick = null, cadParameterPick = null, cadParameterFeature = null) }
                client.cadCommand("cad.feature.set", mapOf("feature_id" to endFace, "extent" to "TO_FACE", "u" to u, "v" to v)); return
            }
            if (client.state.value.cad.surface.mode != "PROFILE") {
                client.cadCommand("cad.surface.select", mapOf("u" to u, "v" to v, "additive" to true)); return
            }
            client.cadCommand("cad.select", mapOf("u" to u, "v" to v, "additive" to true)); return
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
            client.transformSelect(u.toDouble(), v.toDouble(), if (stylus) 0.028 else 0.055, SelectionOp.TOGGLE)
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
                    val add = blender.features.loopCutMultiple
                    client.toolLoopPick(u.toDouble(), v.toDouble(), add = add)
                    return
                }
                if (client.toolSession.value.armed && client.toolSession.value.tool == EditTool.LOOP_CUT) {
                    client.toolLoopPick(u.toDouble(), v.toDouble(), add = false)
                    return
                }
                if (local.value.loopCutAwaitingTap) return
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
                client.transformSelect(u.toDouble(), v.toDouble(), if (stylus) 0.028 else 0.055, SelectionOp.TOGGLE)
            }
            return
        }
        // El pen apunta con precisión: un radio menor evita saltar al elemento vecino.
        // El dedo conserva una diana más grande y cómoda.
        val threshold = if (stylus) 0.028 else 0.055
        if (local.value.shortestPathActive && uiState.value.blender.mode == BlenderMode.EDIT) {
            client.shortestPath(u.toDouble(), v.toDouble(), threshold)
        } else {
            val blender = uiState.value.blender
            val plainEdit = blender.mode == BlenderMode.EDIT
            // Doble toque en el mismo sitio: el loop de lo tocado (Alt+clic de Blender);
            // en Vértices, la pieza enlazada. El ADD previo lo deja como semilla activa.
            val previous = lastEditTap
            val now = android.os.SystemClock.uptimeMillis()
            if (plainEdit && blender.activeObjectType == "MESH" && previous != null && now - previous.third <= EDIT_DOUBLE_TAP_MS &&
                kotlin.math.hypot(u - previous.first, v - previous.second) <= EDIT_DOUBLE_TAP_DISTANCE) {
                lastEditTap = null
                client.pick(u.toDouble(), v.toDouble(), threshold, SelectionOp.ADD)
                if (blender.selectionMode == SelectionMode.VERTEX) client.selectLinked()
                else client.selectLoop(SelectionOp.ADD)
                return
            }
            lastEditTap = if (plainEdit && blender.activeObjectType == "MESH") Triple(u, v, now) else null
            // En Edit el toque sin modificador acumula: añade o quita lo tocado, sin Mayús.
            client.pick(u.toDouble(), v.toDouble(), threshold, SelectionOp.TOGGLE)
        }
    }
    fun requestState() = client.requestState()
    fun addPrimitive(primitive: AddObject) = client.addPrimitive(primitive)
    fun snap(action: SnapAction) {
        selectTool()
        client.snap(action)
    }

    /** Navegación por vistas estándar y proyección (footer de vistas). */
    fun toggleViewPlaneLock() = client.viewPlaneLock(!client.state.value.view.planeLocked)
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
    fun toggleShading() {
        if (!client.state.value.material.active) client.viewShading("TOGGLE")
    }

    fun toggleProportional() {
        val enabled = !client.state.value.editSettings.proportional
        client.editSettings(mapOf("proportional" to enabled))
    }

    fun toggleAutoMerge() {
        client.editSettings(mapOf("auto_merge" to !client.state.value.editSettings.autoMerge))
    }

    fun setProportionalRadius(value: Double) {
        if (value.isFinite() && value > 0.0) client.editSettings(mapOf("radius" to value))
    }

    fun setProportionalFalloff(value: String) {
        if (value in ProportionalFalloffs) client.editSettings(mapOf("falloff" to value))
    }

    /** Aísla la selección (el `/` del footer de vistas). Optimista: no hay push. */
    fun toggleLocalView(target: String? = null) {
        val remote = client.state.value
        if (remote.material.active) { materialSettings(mapOf("isolate" to !remote.material.isolate)); return }
        if (remote.cad.workspace) { cadCommand("cad.settings", mapOf("show_scene" to !remote.cad.showScene)); return }
        val next = !local.value.localViewActive
        local.update { it.copy(localViewActive = next) }
        if (target != null) client.editCatalogCommand("view.local", mapOf("enabled" to next, "objects" to listOf(target)))
        else client.viewLocal(next)
    }

    fun selectMore() = client.selectMore()
    fun selectLess() = client.selectLess()

    fun activateSelection() {
        when {
            client.state.value.material.active -> materialSettings(mapOf("interaction" to "SELECT"))
            client.state.value.cad.workspace -> cadTool(null)
            else -> selectTool()
        }
    }

    fun toggleShortestPath() {
        activateSelection()
        local.update { it.copy(shortestPathActive = !it.shortestPathActive) }
    }

    /** B/C: arma/desarma la herramienta de arrastre por forma. */
    fun toggleShapeTool(tool: ShapeTool) {
        val next = if (local.value.shapeTool == tool) ShapeTool.NONE else tool
        if (next != ShapeTool.NONE) activateSelection()
        local.update { it.copy(shapeTool = next, shortestPathActive = false,
            circleRadius = if (next == ShapeTool.PAINT) it.circleRadius ?: .05f else it.circleRadius) }
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
    fun shapeSelect(shape: ShapeTool, phase: GesturePhase, u0: Float, v0: Float, u1: Float, v1: Float) {
        if (shape == ShapeTool.PAINT) {
            if (phase == GesturePhase.BEGIN) selectionPaintId = java.util.UUID.randomUUID().toString()
            val id = selectionPaintId ?: return
            client.editCatalogCommand("selection.paint", mapOf("phase" to phase.name, "stroke_id" to id,
                "u0" to u0, "v0" to v0, "u1" to u1, "v1" to v1, "radius" to (local.value.circleRadius ?: .05f)))
            if (phase == GesturePhase.END || phase == GesturePhase.CANCEL) selectionPaintId = null
            return
        }
        // Bisect es la excepción: no es selección y no se desarma sola tras un
        // arrastre (F4 permite redibujar la línea mientras la sesión sigue viva). El
        // watcher de [toolSession] es quien la desarma al salir de Bisect.
        if (shape == ShapeTool.LINE) {
            bisectDragLine(u0, v0, u1, v1)
            return
        }
        // Las regiones alternan su pertenencia con la misma intención múltiple del toque.
        val op = SelectionOp.TOGGLE
        when (shape) {
            ShapeTool.BOX -> client.boxSelect(u0.toDouble(), v0.toDouble(), u1.toDouble(), v1.toDouble(), op)
            ShapeTool.CIRCLE -> client.circleSelect(
                u0.toDouble(), v0.toDouble(),
                Math.hypot((u1 - u0).toDouble(), (v1 - v0).toDouble()),
                op,
            )
            ShapeTool.NONE, ShapeTool.LINE, ShapeTool.PAINT -> Unit
        }
        local.update { it.copy(shapeTool = ShapeTool.NONE) }
    }

    /** Acciones contextuales de selección (Edit y Object). */
    fun selectAll() {
        activateSelection()
        if (client.state.value.material.active) {
            materialCommand("material.select", mapOf("objects" to client.state.value.material.objects.map { it.id }))
        } else if (client.state.value.cad.workspace) {
            val sketch = client.state.value.cad.selectionSketch ?: return
            cadCommand("cad.select_all", mapOf("action" to "SELECT", "sketch_id" to sketch.id))
        } else client.selectAll(true)
    }
    fun deselectAll() {
        activateSelection()
        if (client.state.value.material.active) materialCommand("material.select", mapOf("objects" to emptyList<String>()))
        else if (client.state.value.cad.workspace) {
            cadCommand("cad.select_all", mapOf("action" to "DESELECT"))
        } else client.selectAll(false)
    }
    fun invertSelection() {
        activateSelection()
        val remote = client.state.value
        if (remote.material.active) materialCommand("material.select", mapOf("objects" to remote.material.objects.map { it.id }.filter { it !in remote.material.targets }))
        else if (remote.cad.workspace) cadCommand("cad.select_all", mapOf("action" to "INVERT", "sketch_id" to remote.cad.selectionSketch?.id))
        else client.invertSelection()
    }
    fun hideSelection() = client.hideSelection()
    fun hideObject(name: String? = null) {
        val remote = client.state.value
        if (remote.material.active) {
            client.hideObjects(remote.material.targets); materialCommand("material.select", mapOf("objects" to emptyList<String>())); return
        }
        if (remote.cad.workspace) {
            remote.cad.selectedFeature?.let { cadCommand("cad.feature.set", mapOf("feature_id" to it.id, "enabled" to !it.enabled)); return }
            remote.cad.selectedSketch?.let { cadCommand("cad.sketch.visibility", mapOf("sketch_id" to it.id, "visible" to !it.visible)) }
            return
        }
        if (remote.mode == BlenderMode.SCULPT) client.setMode(BlenderMode.OBJECT)
        client.hideObjects(name?.let(::listOf))
    }
    fun deleteObject(name: String) = client.editCatalogCommand("object.delete", mapOf("objects" to listOf(name)))

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
    fun listObjects() = client.listObjects()
    fun listOutliner() = client.listOutliner()
    fun outlinerCollection(action: String, payload: Map<String, Any?>) = client.outlinerCollection(action, payload)
    fun outlinerAction(id: String, action: String, value: Boolean? = null, name: String? = null) =
        client.outlinerAction(id, action, value, name)
    fun outlinerMove(id: String) = beginTransform(TransformMode.MOVE, id)
    fun vertexGroupCommand(action: String, payload: Map<String, Any?>) = client.vertexGroupCommand(action, payload)
    fun versioningCommand(action: String, payload: Map<String, Any?> = emptyMap()) = client.versioningCommand(action, payload)
    fun addModifier(type: String, parameters: Map<String, Any?> = emptyMap()) = client.modifierAdd(type, parameters)
    fun removeModifier(name: String) = client.modifierRemove(name)
    fun moveModifier(name: String, index: Int) = client.modifierMove(name, index)
    fun setModifier(name: String, key: String, value: Any?) = client.modifierSet(name, mapOf(key to value))
    fun setObjectProperties(id: String, revision: String, values: Map<String, Any?>, token: String) =
        client.setObjectProperties(id, revision, values, token)
    fun toggleModifier(name: String, viewport: Boolean? = null, render: Boolean? = null, editMode: Boolean? = null) = client.modifierToggle(name, viewport, render, editMode)
    fun applyModifier(name: String) = client.modifierApply(name)
    private var f2GestureId: String? = null
    fun f2Gesture(phase: GesturePhase, u: Float, v: Float) {
        val session = client.toolSession.value
        if (phase == GesturePhase.BEGIN) f2GestureId = java.util.UUID.randomUUID().toString()
        val id = f2GestureId ?: return
        if (session.armed && session.tool == EditTool.F2) client.editCatalogCommand("tool.f2_gesture",
            mapOf("phase" to phase.name, "gesture_id" to id, "u" to u, "v" to v))
        if (phase == GesturePhase.END || phase == GesturePhase.CANCEL) f2GestureId = null
    }

    fun selectSimilar(action: EditCatalogAction, criterion: String) {
        if (!action.enabled || action.command == null || action.variants.none { it.id == criterion && it.enabled }) return
        selectTool()
        client.editCatalogCommand(action.command, action.payload + ("type" to criterion))
    }

    fun selectLoop() {
        val op = SelectionOp.TOGGLE
        client.selectLoop(op)
    }
    fun selectRing() {
        val op = SelectionOp.ADD
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
        closeSessions(commit = true)
        local.update { it.copy(activeTool = ActiveTool.valueOf(tool.name), loopCutAwaitingTap = tool == EditTool.LOOP_CUT) }
        client.toolBegin(tool, toolDefaultParameters(tool))
    }

    fun beginAlignment(objectName: String?) {
        if (uiState.value.blender.mode != BlenderMode.OBJECT) return
        local.update { it.copy(activeTool = ActiveTool.SELECT, referencePicking = false, shapeTool = ShapeTool.NONE) }
        facePickRole = null
        lastFacePointer = null
        client.toolBegin(EditTool.ALIGN, toolPreferences.restore(EditTool.ALIGN,
            objectName?.let { mapOf("object" to it) } ?: emptyMap(), client.state.value.unitScaleLength))
    }

    fun setToolParameter(key: String, value: Any?) {
        when (key) {
            "snap_type" -> (value as? String)?.let { wire ->
                SnapType.entries.firstOrNull { it.name == wire }?.let(::rememberSnapType)
            }
            "snap_step" -> (value as? Number)?.toDouble()?.let { step ->
                if (client.toolSession.value.tool in DISTANCE_STEP_TOOLS)
                    rememberDistanceStep(step * client.state.value.unitScaleLength)
                else rememberSnapStep(step)
            }
        }
        client.toolParameter(mapOf(key to value))
    }

    fun nudgeTool(delta: Double) = client.toolNudge(delta)

    /** Dibujar: suelta el último vértice; el siguiente toque empieza otra línea. */
    fun drawBreak() = client.editCatalogCommand("tool.draw_break")

    /** Seguimiento absoluto del dedo para snap geométrico durante el arrastre. */
    fun toolPointer(u: Float, v: Float) {
        if (gizmoDragActive) {
            // UPDATE lleva juntos el delta acumulado (órbita) y el punto absoluto (asa).
            gizmoLastPointer = u to v
            client.gizmoDrag(GesturePhase.UPDATE, u.toDouble(), v.toDouble(),
                gizmoPendingDx.toDouble(), gizmoPendingDy.toDouble())
            gizmoPendingDx = 0f; gizmoPendingDy = 0f
            return
        }
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
        if (tool.active && tool.planarDrag && !tool.snapType.geometric) {
            client.toolExtrudeDrag(GesturePhase.UPDATE, u.toDouble(), v.toDouble())
            return
        }
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
        val id = com.blendertablet.remote.model.EditFooterCatalog.id(action) ?: return
        client.state.value.features.editCatalog.actionsFor(client.state.value.selectionMode)
            .firstOrNull { it.id == id }?.let(::editCatalogAction)
    }

    /** Igual que [editFooterAction], concentra el futuro adaptador del catálogo. */
    fun editCatalogAction(action: EditCatalogAction, variant: String? = null) {
        if (!action.enabled || action.command == null) return
        // Las sesiones existentes usan exactamente tool.begin {tool, parameters}.
        val tool = EditTool.fromWire(action.id)
        if (action.execution == "SESSION" && action.command == "tool.begin" && tool != null) {
            if (tool != EditTool.EXTRUDE || variant == null) closeTransformForToolChange()
            local.update { it.copy(activeTool = ActiveTool.valueOf(tool.name), loopCutAwaitingTap = false) }
            val params = action.parameters.associate { it.id to it.default }.toMutableMap()
            if (variant != null) params["variant"] = variant
            client.toolBegin(tool, withGlobalSnap(tool, params))
            return
        }
        selectTool()
        client.editCatalogCommand(action.command, action.payload)
    }
    fun confirmTool() {
        val session = client.toolSession.value
        if (session.active) toolPreferences.save(session.tool, session.parameters, client.state.value.unitScaleLength)
        local.update { it.copy(loopCutAwaitingTap = false) }
        client.toolConfirm()
    }

    fun cancelTool() {
        local.update { it.copy(loopCutAwaitingTap = false, activeTool = if (it.activeTool == ActiveTool.F2) ActiveTool.SELECT else it.activeTool) }
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
        EditTool.F2, EditTool.DRAW -> emptyMap()
        EditTool.LOOP_CUT -> mapOf("cuts" to 1.0, "smoothness" to 0.0, "factor" to 0.0, "snap_type" to "NONE")
        EditTool.BRIDGE_EDGE_LOOPS -> mapOf("twist_offset" to 0.0, "merge_factor" to 0.0, "snap_type" to "NONE")
        EditTool.ALIGN -> emptyMap()
        EditTool.KNIFE -> mapOf("snap" to 1.0)
        EditTool.BISECT -> mapOf("clear_inner" to 0.0, "clear_outer" to 0.0, "fill" to 0.0, "snap" to 1.0)
    })

    private fun withGlobalSnap(tool: EditTool, parameters: Map<String, Any?>): Map<String, Any?> {
        if ("snap_type" !in parameters) return toolPreferences.restore(tool, parameters, client.state.value.unitScaleLength)
        val chosen = local.value.snapType
        val extrudeGeometric = tool == EditTool.EXTRUDE &&
            (parameters["variant"] ?: "REGION") in setOf("REGION", "MANIFOLD")
        val compatible = if (extrudeGeometric || !chosen.geometric) chosen else SnapType.NONE
        val shared = local.value.distanceStepMeters
        val distanceTool = tool in DISTANCE_STEP_TOOLS
        // El paso común elegido por el usuario sustituye al automático por tamaño.
        val step = if (distanceTool && shared != null)
            shared / client.state.value.unitScaleLength.coerceAtLeast(1e-12) else local.value.snapStep
        return toolPreferences.restore(tool, parameters + mapOf(
            "snap_type" to compatible.name,
            "snap_step" to step,
        ) + if (distanceTool && shared == null) mapOf("auto_size" to true) else emptyMap(), client.state.value.unitScaleLength)
    }

    private fun rememberSnapType(type: SnapType) {
        local.update { it.copy(snapType = type) }
        snapPreferences.save(SnapSettings(type, local.value.snapStep, local.value.distanceStepMeters))
    }

    /**
     * Fija el paso métrico común y lo refleja en los pasos visibles de Mover, Escalar
     * (si usa mm/cm/m) y Tweak libre. Extruir/Bisel/Inset lo leen al abrirse.
     */
    private fun rememberDistanceStep(meters: Double) {
        if (!meters.isFinite() || meters <= 0.0) return
        val scaleLength = client.state.value.unitScaleLength.coerceAtLeast(1e-12)
        local.update { state -> state.copy(
            distanceStepMeters = meters,
            moveStepValue = if (state.moveStepUnit == TransformStepUnit.PERCENT) state.moveStepValue
                else meters / state.moveStepUnit.meters,
            scaleStepValue = if (state.scaleUnit == TransformStepUnit.PERCENT) state.scaleStepValue
                else meters / state.scaleUnit.meters,
            tweak = if (state.tweak.motion == TweakMotion.FREE) state.tweak.copy(snapStep = meters / scaleLength)
                else state.tweak,
        ) }
        snapPreferences.save(SnapSettings(local.value.snapType, local.value.snapStep, meters))
    }

    private fun rememberSnapStep(step: Double) {
        local.update { it.copy(snapStep = step) }
        snapPreferences.save(SnapSettings(local.value.snapType, step, local.value.distanceStepMeters))
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
        // F2 y Dibujar se desarman al repetir su botón.
        val armed = client.toolSession.value
        if (armed.armed && ((family.id == "F2" && armed.tool == EditTool.F2) || (family.id == "DRAW" && armed.tool == EditTool.DRAW))) {
            selectTool(); return
        }
        val available = family.variants.filter { it.availableIn(client.state.value.selectionMode) }
        if (variantId != null && available.none { it.id == variantId }) return
        val remembered = local.value.toolbarVariant[family.id]
        val variant = available.firstOrNull { it.id == (variantId ?: remembered) }
            ?: available.firstOrNull { it.id == family.defaultVariant }
            ?: available.firstOrNull()
            ?: return
        local.update { it.copy(toolbarVariant = it.toolbarVariant + (family.id to variant.id)) }
        val toolWire = (variant.payload["tool"] as? String) ?: (family.payload["tool"] as? String) ?: family.id
        val tool = EditTool.fromWire(toolWire) ?: return
        when (tool) {
            EditTool.LOOP_CUT, EditTool.KNIFE, EditTool.F2, EditTool.DRAW -> beginEditTool(tool)
            EditTool.BISECT -> {
                closeTransformForToolChange()
                local.update { it.copy(activeTool = ActiveTool.BISECT, loopCutAwaitingTap = false) }
                client.toolBegin(tool, toolDefaultParameters(tool))
            }
            else -> {
                if (tool != EditTool.EXTRUDE || variantId == null) closeTransformForToolChange()
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
    fun createFolder(folder: String, name: String) = client.fileCreateFolder(folder, name)
    fun clearFolderError() = client.clearFolderError()

    /**
     * Abre una transformación modal. Se mantiene abierta aunque se levante el dedo:
     * termina con [transformConfirm] o [transformCancel].
     */
    fun transformBegin(mode: TransformMode) = beginTransform(mode)

    private fun beginTransform(mode: TransformMode, outlinerTarget: String? = null) {
        if (local.value.activeTool == ActiveTool.TWEAK) {
            cancelTweakGesture()
            local.update { it.copy(activeTool = ActiveTool.SELECT) }
        }
        closeTransformForToolChange()
        local.update { it.copy(loopCutAwaitingTap = false) }
        if (mode == TransformMode.SCALE) {
            val unit = client.state.value.sceneScale.lengthUnit.transformStepUnit()
            local.update { it.copy(scaleUnit = unit,
                scaleStepValue = it.distanceStepMeters?.let { meters -> meters / unit.meters } ?: it.scaleStepValue) }
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
        val center = centerPreferences.forScene(client.state.value.sceneScale.sceneId)
        val snapType = snapTypeFor(mode).let {
            if (mode != TransformMode.MOVE && center.mode == "INDIVIDUAL" && it.geometric) SnapType.NONE else it
        }
        if (mode != TransformMode.MOVE && snapType.geometric) {
            lastReferencePointer = null
            local.update { it.copy(referencePicking = true, referenceRole = "SOURCE") }
        }
        if (outlinerTarget != null) {
            client.outlinerMove(outlinerTarget, constraint.axes, step, snapType, local.value.orientation, local.value.valueMode)
        } else client.transformBegin(
            mode, constraint.axes, step = step,
            snapType = snapType,
            orientation = local.value.orientation,
            valueMode = local.value.valueMode,
            scaleStepUnit = if (mode == TransformMode.SCALE) local.value.scaleUnit.scaleStepWireUnit else null,
            center = centerPreferences.forScene(client.state.value.sceneScale.sceneId),
        )
    }

    fun activateTweak() {
        closeTransformForToolChange()
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
        }.let { settings ->
            // El movimiento libre usa el paso común; SLIDE conserva su fracción del riel.
            val shared = local.value.distanceStepMeters
            if (settings.motion == TweakMotion.FREE && shared != null)
                settings.copy(snapStep = shared / client.state.value.unitScaleLength.coerceAtLeast(1e-12))
            else settings
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

    fun setTweakMotion(motion: TweakMotion) = updateTweakSettings { settings ->
        val shared = local.value.distanceStepMeters
        settings.copy(motion = motion, snapStep = if (motion == TweakMotion.FREE && shared != null)
            shared / client.state.value.unitScaleLength.coerceAtLeast(1e-12) else settings.snapStep)
    }

    fun setTweakSnapType(snapType: SnapType) = updateTweakSettings { it.copy(snapType = snapType) }

    fun setTweakSnapStep(step: Double) {
        if (!step.isFinite() || step <= 0.0) return
        updateTweakSettings { it.copy(snapStep = step) }
        if (local.value.activeTool == ActiveTool.TWEAK && local.value.tweak.motion == TweakMotion.FREE)
            rememberDistanceStep(step * client.state.value.unitScaleLength)
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
                center = centerPreferences.forScene(client.state.value.sceneScale.sceneId),
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
        if (normalized == "CENTER") {
            // «Señalar punto» sustituye el centro solo al fijar un candidato válido.
            lastReferencePointer = null
            local.update { it.copy(referencePicking = true, referenceRole = "CENTER") }
            return
        }
        val roleAlreadyLocked = session.sourceLocked
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
        if (preset !in setOf("SELECTION", "CURSOR", "OBJECT_ORIGIN", "INDIVIDUAL")) return
        // Elegir y confirmar enseguida no debe depender de que llegue el ACK.
        pendingCenterPreset = preset
        centerPreferences.save(com.blendertablet.remote.model.TransformCenter(preset))
        lastReferencePointer = null
        local.update { it.copy(referencePicking = false, referenceRole = "CENTER") }
        client.transformCenterPreset(preset)
    }

    fun setMoveStep(value: Double, unit: TransformStepUnit) {
        if (value <= 0.0) return
        // Cambiar solo la unidad expresa el paso común en ella; escribir un paso lo fija.
        val unitOnly = unit != local.value.moveStepUnit
        val shared = local.value.distanceStepMeters
        val step = if (unitOnly && shared != null && unit != TransformStepUnit.PERCENT) shared / unit.meters else value
        local.update { it.copy(moveStepValue = step, moveStepUnit = unit) }
        if (!unitOnly && unit != TransformStepUnit.PERCENT) rememberDistanceStep(step * unit.meters)
        val session = client.transformSession.value
        if (!session.active || session.mode != TransformMode.MOVE) return
        val blenderStep = moveStepInBlenderUnits(step, unit, uiState.value.blender.unitScaleLength)
            ?: ((session.referenceDistance ?: return) * step / 100.0)
        client.transformSnap(SnapType.INCREMENT, blenderStep, session.snapToSelection)
    }

    /** Una sola unidad para dimensiones, botones e incremento de Escalar. */
    fun setScaleStep(value: Double, unit: TransformStepUnit) {
        if (!value.isFinite() || value <= 0.0) return
        // Cambiar solo la unidad expresa el paso común en ella; escribir un paso lo fija.
        val shared = local.value.distanceStepMeters
        if (unit == TransformStepUnit.PERCENT) applyScaleStep(value, unit)
        else if (unit != local.value.scaleUnit) applyScaleStep(shared?.let { it / unit.meters } ?: value, unit)
        else {
            applyScaleStep(value, unit)
            rememberDistanceStep(value * unit.meters)
        }
    }

    private fun applyScaleStep(value: Double, unit: TransformStepUnit) {
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

    fun requestSceneScales() = client.requestSceneScales()
    fun fileNew(preset: String) { cancelSculptStroke(); client.fileNew(preset) }
    fun fileOpen(path: String) { cancelSculptStroke(); client.fileOpen(path) }
    fun fileSave() { cancelSculptStroke(); client.fileSave() }
    fun fileSaveAs(path: String) { cancelSculptStroke(); client.fileSaveAs(path) }
    fun fileSaveAs(folder: String, name: String) { cancelSculptStroke(); client.fileSaveAs(folder, name) }

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

    fun dragStart(u: Float, v: Float) {
        dragStartPoint = u to v
    }

    fun toggleGizmo() = local.update { it.copy(gizmoEnabled = !it.gizmoEnabled) }

    /** El manipulador se ofrece en Object/Edit con la selección normal, sin otras herramientas. */
    private fun gizmoWanted(remote: BlenderState, ui: AppUiState): Boolean =
        remote.features.gizmo && ui.gizmoEnabled && !(remote.mode == BlenderMode.EDIT && remote.activeObjectType == "CURVE") && !remote.cad.workspace && !remote.material.active &&
            (remote.mode == BlenderMode.OBJECT || remote.mode == BlenderMode.EDIT) &&
            ui.activeTool == ActiveTool.SELECT && ui.shapeTool == ShapeTool.NONE &&
            !ui.shortestPathActive && !ui.loopCutAwaitingTap

    /**
     * Arrastre de un dedo con el manipulador visible: BEGIN con el punto de apoyo y el
     * snap común; el servidor decide si agarra un asa u orbita. Devuelve si lo atendió.
     */
    private fun gizmoGesture(phase: GesturePhase, dx: Float, dy: Float): Boolean {
        if (phase == GesturePhase.BEGIN) {
            val start = dragStartPoint
            dragStartPoint = null
            val idle = !client.transformSession.value.active && !client.toolSession.value.active &&
                !client.toolSession.value.armed
            if (start == null || !idle || !gizmoWanted(client.state.value, local.value)) return false
            gizmoDragActive = true
            gizmoPendingDx = 0f; gizmoPendingDy = 0f
            gizmoLastPointer = start
            local.update { it.copy(gizmoDragging = true) }
            client.gizmoDrag(GesturePhase.BEGIN, start.first.toDouble(), start.second.toDouble(), 0.0, 0.0, gizmoSettings())
            return true
        }
        if (!gizmoDragActive) return false
        when (phase) {
            GesturePhase.UPDATE -> { gizmoPendingDx += dx; gizmoPendingDy += dy }
            else -> {
                val (u, v) = gizmoLastPointer ?: (0f to 0f)
                client.gizmoDrag(phase, u.toDouble(), v.toDouble(), gizmoPendingDx.toDouble(), gizmoPendingDy.toDouble())
                gizmoDragActive = false
                gizmoPendingDx = 0f; gizmoPendingDy = 0f
                gizmoLastPointer = null
                local.update { it.copy(gizmoDragging = false) }
            }
        }
        return true
    }

    /** Los mismos pasos que abrirían Mover/Rotar/Escalar desde el rail. */
    private fun gizmoSettings(): Map<String, Any?> {
        val scaleLength = client.state.value.unitScaleLength
        val move = moveStepInBlenderUnits(local.value.moveStepValue, local.value.moveStepUnit, scaleLength)
            ?: stepInBlenderUnits(stepsFor(TransformMode.MOVE)[localStepIndex(TransformMode.MOVE)], TransformMode.MOVE, scaleLength)
        val rotate = stepInBlenderUnits(stepsFor(TransformMode.ROTATE)[localStepIndex(TransformMode.ROTATE)], TransformMode.ROTATE, scaleLength)
        val scale = scaleStepForWire(local.value.scaleStepValue, local.value.scaleUnit, scaleLength)
        return mapOf(
            "snap_type" to if (local.value.snapType == SnapType.INCREMENT) "INCREMENT" else "NONE",
            "steps" to mapOf("MOVE" to move, "ROTATE" to rotate, "SCALE" to scale),
            "scale_step_unit" to local.value.scaleUnit.scaleStepWireUnit,
        )
    }

    /**
     * Arrastre de un dedo/stylus: se traduce al gesto de la herramienta activa.
     * El servidor lo agrupa y cierra un único paso de undo al soltar.
     */
    fun toolGesture(phase: GesturePhase, dx: Float, dy: Float) {
        if (gizmoGesture(phase, dx, dy)) return
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
            if (tool.planarDrag && !tool.snapType.geometric) {
                // Extruir en plano sigue al dedo: el punto absoluto llega por toolPointer.
                if (phase == GesturePhase.BEGIN) dragStartPoint?.let { (u, v) ->
                    client.toolExtrudeDrag(GesturePhase.BEGIN, u.toDouble(), v.toDouble())
                }
                return
            }
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

/** Herramientas Edit cuyo paso es una distancia y comparten el paso métrico común. */
private val DISTANCE_STEP_TOOLS = setOf(EditTool.EXTRUDE, EditTool.BEVEL, EditTool.INSET)
private const val EDIT_DOUBLE_TAP_MS = 320L
private const val EDIT_DOUBLE_TAP_DISTANCE = 0.03f
