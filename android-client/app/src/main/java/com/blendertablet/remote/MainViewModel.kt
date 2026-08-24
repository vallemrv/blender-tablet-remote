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
import com.blendertablet.remote.model.Gesture
import com.blendertablet.remote.model.GesturePhase
import com.blendertablet.remote.model.InputDebug
import com.blendertablet.remote.model.AddObject
import com.blendertablet.remote.model.Orientation
import com.blendertablet.remote.model.Projection
import com.blendertablet.remote.model.SelectionMode
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
import com.blendertablet.remote.network.WebSocketRemoteBlenderClient
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

class MainViewModel(application: Application) : AndroidViewModel(application) {
    private val client: RemoteBlenderClient = WebSocketRemoteBlenderClient(viewModelScope)
    private val local = MutableStateFlow(AppUiState())
    private val preferences = ConnectionPreferences(application)
    private val stream = ViewportStream(viewModelScope)
    private var loopCutArmed = false
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
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), AppUiState())

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
        // El puerto del vídeo lo anuncia el servidor en el "hello": el usuario solo
        // configura el de control y el vídeo se engancha solo (§63).
        viewModelScope.launch {
            client.streamEndpoint.collect { endpoint ->
                if (endpoint == null) stream.stop()
                else stream.start(endpoint.host, endpoint.port, endpoint.token)
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
        stream.stop()
        client.disconnect()
    }
    /** Volver a Seleccionar cierra cualquier sesión (transformación o herramienta). */
    fun selectTool() {
        closeSessions()
        local.update { it.copy(activeTool = ActiveTool.SELECT) }
    }
    /**
     * Cambiar de modo o de submodo invalida lo que hubiera abierto: una extrusión
     * de caras no significa nada en cuanto se pasa a vértices, y el servidor
     * respondería `session_invalidated` a mitad de un arrastre. Se descarta antes de
     * cambiar, que es la salida no destructiva.
     */
    fun setMode(mode: BlenderMode) {
        closeSessions()
        client.setMode(mode)
    }

    fun setSelectionMode(mode: SelectionMode) {
        closeSessions()
        client.setSelectionMode(mode)
    }

    private fun closeSessions() {
        if (client.transformSession.value.active) client.transformCancel()
        if (client.toolSession.value.active) client.toolCancel()
    }
    fun toggleControls() = local.update { it.copy(controlsVisible = !it.controlsVisible) }
    fun toggleDebug() = local.update { it.copy(debugVisible = !it.debugVisible) }
    fun updateInput(input: InputDebug) = local.update { it.copy(input = input) }
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
        val session = client.transformSession.value
        if (session.active && session.mode == TransformMode.MOVE && session.snapType.geometric) {
            client.transformSnapCandidate(u.toDouble(), v.toDouble(), session.snapType)
            return
        }
        if (session.active) return
        // El pen apunta con precisión: un radio menor evita saltar al elemento vecino.
        // El dedo conserva una diana más grande y cómoda.
        client.pick(u.toDouble(), v.toDouble(), if (stylus) 0.018 else 0.045)
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
    fun openModifiers() = client.requestModifierOptions()
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
        local.update { it.copy(activeTool = ActiveTool.valueOf(tool.name)) }
        if (tool == EditTool.LOOP_CUT && client.state.value.context.selectionCounts.edges == 0) {
            loopCutArmed = true
            client.setSelectionMode(SelectionMode.EDGE)
        } else client.toolBegin(tool, toolDefaultParameters(tool))
    }

    fun setToolParameter(key: String, value: Double) =
        client.toolParameter(mapOf(key to value))

    fun nudgeTool(delta: Double) = client.toolNudge(delta)
    fun confirmTool() = client.toolConfirm()
    fun cancelTool() { loopCutArmed = false; client.toolCancel() }

    private fun toolDefaultParameters(tool: EditTool): Map<String, Double> = when (tool) {
        EditTool.EXTRUDE -> mapOf("offset" to 0.0)
        EditTool.BEVEL -> mapOf("offset" to 0.02, "segments" to 1.0)
        EditTool.INSET -> mapOf("thickness" to 0.1, "depth" to 0.0)
        EditTool.SUBDIVIDE -> mapOf("cuts" to 1.0)
        EditTool.LOOP_CUT -> mapOf("cuts" to 1.0, "smoothness" to 0.0, "factor" to 0.0)
    }

    /** Al abrir el menú Archivo: refresca nombre, "sin guardar" y recientes. */
    fun refreshFileMenu() {
        client.fileInfo()
        client.requestRecentFiles()
    }

    val transformSession: StateFlow<TransformSession> = client.transformSession

    /** Herramienta paramétrica de Edit Mode en curso (Extrude/Bevel/Inset/Subdivide). */
    val toolSession: StateFlow<ToolSession> = client.toolSession

    /**
     * Abre una transformación modal. Se mantiene abierta aunque se levante el dedo:
     * termina con [transformConfirm] o [transformCancel].
     */
    fun transformBegin(mode: TransformMode) {
        // Una transformación y una herramienta paramétrica no conviven: cerrar la otra.
        if (client.toolSession.value.active) client.toolCancel()
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
            if (phase == GesturePhase.UPDATE || phase == GesturePhase.END) {
                client.toolNudge((-dy).toDouble())
            }
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
        runCatching { connectivity?.unregisterNetworkCallback(networkCallback) }
        stream.stop()
        client.disconnect()
        super.onCleared()
    }
}
