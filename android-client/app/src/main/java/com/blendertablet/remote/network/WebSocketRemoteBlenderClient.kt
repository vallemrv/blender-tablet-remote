package com.blendertablet.remote.network

import android.util.Log
import com.blendertablet.remote.model.Axis
import com.blendertablet.remote.model.BlenderMode
import com.blendertablet.remote.model.BlenderState
import com.blendertablet.remote.model.ConnectionStatus
import com.blendertablet.remote.model.EditTool
import com.blendertablet.remote.model.FileInfo
import com.blendertablet.remote.model.Gesture
import com.blendertablet.remote.model.GesturePhase
import com.blendertablet.remote.model.AddObject
import com.blendertablet.remote.model.Orientation
import com.blendertablet.remote.model.Projection
import com.blendertablet.remote.model.RemoteFiles
import com.blendertablet.remote.model.SelectionMode
import com.blendertablet.remote.model.SelectionOp
import com.blendertablet.remote.model.Shading
import com.blendertablet.remote.model.SnapAction
import com.blendertablet.remote.model.SnapType
import com.blendertablet.remote.model.ToolSession
import com.blendertablet.remote.model.LoopProbe
import com.blendertablet.remote.model.TouchProbe
import com.blendertablet.remote.model.TransformMode
import com.blendertablet.remote.model.SceneScale
import com.blendertablet.remote.model.TransformSession
import com.blendertablet.remote.model.TweakSettings
import com.blendertablet.remote.model.ValueMode
import java.net.Proxy
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONArray
import org.json.JSONObject

class WebSocketRemoteBlenderClient(
    private val scope: CoroutineScope,
    // El endpoint vive dentro de WireGuard. No debe atravesar el proxy HTTP que
    // Android o una VPN puedan publicar mediante ProxySelector: algunos proxies
    // reescriben Sec-WebSocket-Key y OkHttp rechaza correctamente la respuesta.
    private val http: OkHttpClient = OkHttpClient.Builder()
        .proxy(Proxy.NO_PROXY)
        // Sin ping, una conexión medio muerta (el móvil pasa de WiFi a datos, el PC
        // suspende) parece viva hasta el primer comando. El ping la delata en
        // segundos y dispara la reconexión antes de que el usuario toque nada.
        .pingInterval(10, TimeUnit.SECONDS)
        .connectTimeout(5, TimeUnit.SECONDS)
        .build(),
) : RemoteBlenderClient {
    private val _connection = MutableStateFlow(ConnectionStatus.DISCONNECTED)
    private val _state = MutableStateFlow(BlenderState())
    private val _errors = MutableStateFlow<String?>(null)
    private val _notices = MutableStateFlow<String?>(null)
    // Un duplicado es un instante, no un estado: quien llegue tarde no debe encontrárselo.
    private val _duplicates = MutableSharedFlow<Unit>(extraBufferCapacity = 1)
    private val _retryAttempt = MutableStateFlow(0)
    private val _file = MutableStateFlow(FileInfo())
    private val _remoteFiles = MutableStateFlow(RemoteFiles())
    private val _transformSession = MutableStateFlow(TransformSession())
    private val _toolSession = MutableStateFlow(ToolSession())
    private val _touchProbe = MutableStateFlow<TouchProbe?>(null)
    private val _streamEndpoint = MutableStateFlow<StreamEndpoint?>(null)
    private val _sceneScalePresets = MutableStateFlow<List<SceneScale>>(emptyList())
    override val sceneScalePresets: StateFlow<List<SceneScale>> = _sceneScalePresets.asStateFlow()
    override val connection: StateFlow<ConnectionStatus> = _connection.asStateFlow()
    override val state: StateFlow<BlenderState> = _state.asStateFlow()
    override val errors: StateFlow<String?> = _errors.asStateFlow()
    override val notices: StateFlow<String?> = _notices.asStateFlow()
    override val duplicates: Flow<Unit> = _duplicates.asSharedFlow()
    override val retryAttempt: StateFlow<Int> = _retryAttempt.asStateFlow()
    override val file: StateFlow<FileInfo> = _file.asStateFlow()
    override val remoteFiles: StateFlow<RemoteFiles> = _remoteFiles.asStateFlow()
    override val transformSession: StateFlow<TransformSession> = _transformSession.asStateFlow()
    override val toolSession: StateFlow<ToolSession> = _toolSession.asStateFlow()
    override val touchProbe: StateFlow<TouchProbe?> = _touchProbe.asStateFlow()
    override val streamEndpoint: StateFlow<StreamEndpoint?> = _streamEndpoint.asStateFlow()

    /** A dónde queremos estar conectados. null = el usuario ha pedido desconectar. */
    private data class Target(val host: String, val port: Int, val token: String)

    private companion object {
        const val LATENCY_TAG = "BTR-Control"
        /**
         * Comandos cuya respuesta ES el estado de la sesión modal. No incluye
         * `transform.move/rotate/scale`, que son transformaciones sueltas y sí deben
         * refrescar la escena.
         */
        val MODAL_COMMANDS = setOf(
            "transform.begin", "transform.axes", "transform.snap",
            "transform.value", "transform.nudge", "transform.status",
            "transform.snap_candidate",
            "transform.reference_candidate",
        )

        /** Comandos cuya respuesta ES el estado de la sesión de herramienta. */
        val TOOL_COMMANDS = setOf(
            "tool.begin", "tool.parameter", "tool.nudge", "tool.status",
            "tool.loop_pick", "tool.loop_pop", "tool.knife_drag", "tool.knife_point", "tool.knife_pop",
            "tool.knife_new_stroke", "tool.knife_close",
            "tool.drag_line", "tool.snap_candidate", "tool.face_pick",
        )
    }

    @Volatile private var target: Target? = null
    @Volatile private var socket: WebSocket? = null
    private var retryJob: Job? = null
    private var attempt = 0
    private val generation = AtomicInteger(0)
    private val pending = ConcurrentHashMap<String, String>()
    private val sentAtNs = ConcurrentHashMap<String, Long>()
    private val stateRequestInFlight = AtomicBoolean(false)
    private val toolSnapInFlight = AtomicBoolean(false)
    @Volatile private var pendingToolSnap: ToolSnapRequest? = null
    private data class ToolSnapRequest(val u: Double, val v: Double, val type: SnapType, val lock: Boolean)
    private val knifeDragInFlight = AtomicBoolean(false)
    @Volatile private var pendingKnifeDrag: KnifeDragRequest? = null
    private data class KnifeDragRequest(val phase: GesturePhase, val u: Double, val v: Double)
    private val transformSnapInFlight = AtomicBoolean(false)
    @Volatile private var pendingTransformSnap: ToolSnapRequest? = null

    // Identificadores de comando: un contador basta (un SecureRandom por envío era
    // caro y no aporta nada: los ids solo tienen que ser únicos por conexión).
    private val commandId = AtomicLong(0)

    // ¿Hay un selection.pick esperando respuesta? Equivalente al antiguo
    // pending.containsValue("selection.pick") sin recorrer la tabla entera.
    private val pickInFlight = AtomicBoolean(false)
    @Volatile private var lastStateRefreshAt = 0L

    /** Arrastre acumulado que todavía no se ha mandado como `tool.nudge`. */
    @Volatile private var pendingNudge = 0.0
    @Volatile private var nudgeInFlight = false

    private val token: String get() = target?.token.orEmpty()

    /**
     * Fragmento JSON del token, precodificado: los gestos van a 30 Hz desde el hilo
     * de UI y construir ahí un JSONObject entero costaba más que el propio mensaje.
     */
    @Volatile private var tokenJson = ""
    private fun rebuildTokenJson() {
        val value = token
        tokenJson = if (value.isBlank()) "" else ",\"token\":${JSONObject.quote(value)}"
    }

    override fun connect(host: String, port: Int, token: String) {
        val next = Target(host, port, token)
        target = next
        attempt = 0
        _retryAttempt.value = 0
        _errors.value = null
        _notices.value = null
        rebuildTokenJson()
        open(next)
    }

    override fun disconnect() {
        target = null
        generation.incrementAndGet() // invalida a los listeners aún en vuelo
        retryJob?.cancel()
        retryJob = null
        socket?.close(1000, "Client disconnect")
        socket = null
        pending.clear()
        sentAtNs.clear()
        stateRequestInFlight.set(false)
        pickInFlight.set(false)
        rebuildTokenJson()
        attempt = 0
        _retryAttempt.value = 0
        _streamEndpoint.value = null
        _transformSession.value = TransformSession()
        _toolSession.value = ToolSession()
        _touchProbe.value = null
        _loopProbe.value = null
        _remoteFiles.value = RemoteFiles()
        pendingNudge = 0.0
        nudgeInFlight = false
        _connection.value = ConnectionStatus.DISCONNECTED
    }

    override fun clearNotice() {
        _notices.value = null
    }

    override fun clearError() {
        _errors.value = null
    }

    override fun retryNow() {
        val current = target ?: return
        if (_connection.value == ConnectionStatus.CONNECTED) return
        // Solo se adelanta una espera. Si no hay reintento en cola es que ya hay un
        // intento en vuelo, y cortarlo para empezar otro solo lo retrasaría: pasa en
        // cada arranque, donde onResume llega justo detrás de la conexión inicial.
        if (retryJob?.isActive != true) return
        attempt = 0
        _retryAttempt.value = 0
        open(current)
    }

    private fun open(destination: Target) {
        // Capabilities belong to this connection; a previous CAD server must not
        // enable commands against an older backend during the next handshake.
        _state.value = _state.value.copy(
            cad = com.blendertablet.remote.model.CadState(),
            features = _state.value.features.copy(cad = com.blendertablet.remote.model.CadCapabilities()),
        )
        val generation = this.generation.incrementAndGet()
        retryJob?.cancel()
        retryJob = null
        // cancel() y no close(): el socket viejo puede estar medio muerto y esperar
        // su handshake de cierre retrasaría el intento nuevo hasta el timeout.
        socket?.cancel()
        pending.clear()
        sentAtNs.clear()
        stateRequestInFlight.set(false)
        pickInFlight.set(false)
        _connection.value =
            if (attempt == 0) ConnectionStatus.CONNECTING else ConnectionStatus.RECONNECTING
        val request = Request.Builder().url("ws://${destination.host}:${destination.port}").build()
        socket = http.newWebSocket(request, Listener(destination, generation))
    }

    /** Programa el siguiente intento. No hace nada si ya hay uno en cola. */
    private fun scheduleRetry(destination: Target) {
        if (target != destination) return // el usuario cambió de destino o desconectó
        if (retryJob?.isActive == true) return
        attempt += 1
        _retryAttempt.value = attempt
        _connection.value = ConnectionStatus.RECONNECTING
        val wait = Backoff.delayMs(attempt)
        retryJob = scope.launch {
            delay(wait)
            if (target == destination) open(destination)
        }
    }

    override fun cadCommand(name: String, payload: Map<String, Any?>) {
        if (!_state.value.features.cad.available) return
        require(name.startsWith("cad.") || (name == "mode.set" && payload["mode"] == "CAD"))
        command(name, JSONObject(payload))
    }

    private fun command(name: String, payload: JSONObject = JSONObject()) {
        sendCommand(name, payload)
    }

    override fun editCatalogCommand(command: String, payload: Map<String, Any?>) {
        command(command, JSONObject(payload))
    }

    private fun sendCommand(name: String, payload: JSONObject = JSONObject()): Boolean {
        val id = "c${commandId.incrementAndGet()}"
        val message = JSONObject()
            .put("type", "command")
            .put("id", id)
            .put("command", name)
            .put("payload", payload)
        if (token.isNotBlank()) message.put("token", token)
        // Registrar antes de enviar evita una carrera con sockets/fakes muy rápidos:
        // la respuesta nunca puede adelantarse a su entrada en `pending`.
        pending[id] = name
        sentAtNs[id] = System.nanoTime()
        return if (socket?.send(message.toString()) == true) {
            if (name == "selection.pick" || name == "selection.shortest_path") pickInFlight.set(true)
            if (name == "selection.pick" || name == "selection.shortest_path" || name.startsWith("transform.")) {
                Log.d(LATENCY_TAG, "send command=$name id=$id")
            }
            true
        } else {
            pending.remove(id)
            sentAtNs.remove(id)
            reportOffline()
            false
        }
    }

    /**
     * Un envío fallido durante una reconexión no es noticia: la barra ya dice
     * "Reconectando" y el aviso solo taparía la pantalla. Solo se avisa cuando de
     * verdad no hay a dónde ir.
     */
    private fun reportOffline() {
        if (target == null) _errors.value = "No hay una conexión activa"
    }

    /**
     * Los gestos no llevan id ni esperan respuesta: el servidor agrupa los UPDATE y
     * responder a cada uno saturaría el canal de vuelta durante un arrastre.
     *
     * El mensaje se construye a mano, en el hilo que llama (a 30 Hz, durante el
     * arrastre): un JSONObject por gesto era asignación y serialización regaladas en
     * el momento peor. El token ya viene precodificado en [tokenJson].
     */
    override fun gesture(
        gesture: Gesture,
        phase: GesturePhase,
        dx: Double,
        dy: Double,
        factor: Double,
        axis: Axis?,
    ) {
        val message = buildString(160) {
            append("{\"type\":\"gesture\",\"gesture\":\"").append(gesture.name.lowercase())
                .append("\",\"phase\":\"").append(phase.name.lowercase())
                .append("\",\"dx\":").append(dx)
                .append(",\"dy\":").append(dy)
                .append(",\"factor\":").append(factor)
            if (axis != null) append(",\"axis\":\"").append(axis.name).append('"')
            append(tokenJson)
            append('}')
        }
        if (socket?.send(message) != true) reportOffline()
    }

    override fun requestState() {
        // Un evento scene.changed puede llegar mientras la consulta anterior sigue
        // en vuelo. Una sola fotografía reciente basta; apilarlas roba tiempo de
        // hilo principal a picking, transformaciones y captura.
        if (!stateRequestInFlight.compareAndSet(false, true)) return
        if (!sendCommand("scene.get_state")) stateRequestInFlight.set(false)
    }
    override fun select(name: String?) = command("object.select", JSONObject().apply { name?.let { put("name", it) } })
    override fun pick(u: Double, v: Double, threshold: Double, mode: SelectionOp) = command(
        "selection.pick",
        JSONObject().put("u", u).put("v", v).put("threshold", threshold).put("mode", mode.name),
    )
    override fun shortestPath(u: Double, v: Double, threshold: Double, extend: Boolean) = command(
        "selection.shortest_path",
        JSONObject().put("u", u).put("v", v).put("threshold", threshold).put("extend", extend),
    )
    override fun delete() = command("object.delete")
    override fun duplicate() = command(duplicateCommand(state.value.mode))
    override fun duplicateLinked() = command("object.duplicate", JSONObject().put("linked", true))
    override fun rename(newName: String, target: String?) = command(
        "object.rename",
        JSONObject().put("new_name", newName).apply { target?.let { put("name", it) } },
    )
    override fun selectAll(value: Boolean) =
        if (_state.value.mode == BlenderMode.EDIT) command("selection.all", JSONObject().put("value", value))
        else command("object.select_all", JSONObject().put("value", value))
    override fun selectObject(name: String, add: Boolean) = command(
        "object.select",
        JSONObject().put("name", name).put("mode", if (add) "ADD" else "SET").put("active", true),
    )
    override fun selectLoop(mode: SelectionOp) =
        command("selection.loop", JSONObject().put("mode", mode.name))
    override fun selectRing() = command("selection.ring")
    override fun selectLinked() = command("selection.linked")

    override fun probeTouch(u: Double, v: Double, snapType: SnapType) = command(
        "snap.query",
        JSONObject().put("u", u).put("v", v).put("snap_type", snapType.name),
    )

    override fun clearProbe() {
        _touchProbe.value = null
    }
    override fun setMode(mode: BlenderMode) = command(if (mode == BlenderMode.OBJECT) "mode.object" else "mode.edit")
    override fun setSelectionMode(mode: SelectionMode) = command("selection.${mode.name.lowercase()}")
    override fun invertSelection() = command("selection.invert")
    override fun hideSelection() = command("selection.hide")
    override fun hideObjects(objects: List<String>?, unselected: Boolean) = command("object.hide", JSONObject().apply {
        objects?.let { put("objects", JSONArray(it)) }; put("unselected", unselected)
    })
    override fun revealObjects(objects: List<String>?, select: Boolean) = command("object.reveal", JSONObject().apply {
        objects?.let { put("objects", JSONArray(it)) }; put("select", select)
    })
    override fun shadeObjects(objects: List<String>?, mode: String) = command("object.shade", JSONObject().apply {
        objects?.let { put("objects", JSONArray(it)) }; put("mode", mode)
    })
    override fun transformApply(location: Boolean, rotation: Boolean, scale: Boolean) = command(
        "transform.apply", JSONObject().put("location", location).put("rotation", rotation).put("scale", scale))
    override fun requestModifierOptions() = command("modifier.add_options")
    override fun listObjects() = command("scene.list_objects")
    override fun requestSceneScales() = command("scene.scale")
    override fun setSceneScale(preset: String) =
        command("scene.scale_set", JSONObject().put("preset", preset))
    override fun modifierAdd(type: String, parameters: Map<String, Any?>) = command("modifier.add", JSONObject().put("type", type).put("parameters", JSONObject(parameters)))
    override fun modifierRemove(name: String) = command("modifier.remove", JSONObject().put("name", name))
    override fun modifierMove(name: String, index: Int) = command("modifier.move", JSONObject().put("name", name).put("index", index))
    override fun modifierSet(name: String, parameters: Map<String, Any?>) = command("modifier.set", JSONObject().put("name", name).put("parameters", JSONObject(parameters)))
    override fun modifierToggle(name: String, viewport: Boolean?, render: Boolean?) = command("modifier.toggle", JSONObject().put("name", name).apply { viewport?.let { put("viewport", it) }; render?.let { put("render", it) } })
    override fun modifierApply(name: String) = command("modifier.apply", JSONObject().put("name", name))
    override fun meshDelete(what: String) = command("mesh.delete", JSONObject().put("what", what))
    override fun meshDissolve(what: String) = command("mesh.dissolve", JSONObject().put("what", what))
    override fun undo() = command("history.undo")
    override fun redo() = command("history.redo")
    override fun repeatLast() = command("history.repeat_last")
    override fun frameSelected() = command("view.frame_selected")
    override fun viewAxis(name: String) = command("view.axis", JSONObject().put("axis", name))
    override fun viewFrameAll() = command("view.frame_all")
    override fun viewPerspective(projection: Projection) =
        command("view.perspective", JSONObject().put("mode", projection.name))

    override fun viewShading(mode: String) = command("view.shading", JSONObject().put("mode", mode))

    override fun viewOverlays(show: Boolean) = command("view.overlays", JSONObject().put("show", show))

    override fun viewLocal(enabled: Boolean?) = command(
        "view.local",
        JSONObject().apply { enabled?.let { put("enabled", it) } },
    )

    override fun selectMore() = command("selection.more")
    override fun selectLess() = command("selection.less")

    override fun boxSelect(u0: Double, v0: Double, u1: Double, v1: Double, mode: SelectionOp) = command(
        "selection.box",
        JSONObject().put("u0", u0).put("v0", v0).put("u1", u1).put("v1", v1).put("mode", mode.name),
    )

    override fun circleSelect(u: Double, v: Double, radius: Double, mode: SelectionOp) = command(
        "selection.circle",
        JSONObject().put("u", u).put("v", v).put("radius", radius).put("mode", mode.name),
    )

    override fun addPrimitive(primitive: AddObject) =
        command("object.add", JSONObject().put("primitive", primitive.name))

    override fun snap(action: SnapAction) = command(action.command)

    override fun fileInfo() = command("file.info")
    override fun fileNew() = command("file.new")
    override fun fileOpen(path: String) = command("file.open", JSONObject().put("path", path))
    override fun fileSave() = command("file.save")
    override fun fileSaveAs(path: String) = command("file.save_as", JSONObject().put("path", path))
    override fun fileSaveAs(folder: String, name: String) = command(
        "file.save_as",
        JSONObject().put("folder", folder).put("name", name),
    )
    override fun fileLocations() {
        _remoteFiles.value = _remoteFiles.value.copy(loading = true)
        command("file.locations")
    }
    override fun fileBrowse(path: String?) {
        _remoteFiles.value = _remoteFiles.value.copy(loading = true)
        command("file.browse", JSONObject().apply { path?.let { put("path", it) } })
    }
    override fun fileDefaultFolder(path: String) =
        command("file.default_folder", JSONObject().put("path", path))

    override fun selectionTweak(
        phase: GesturePhase,
        u: Double,
        v: Double,
        dx: Double,
        dy: Double,
        settings: TweakSettings?,
    ) = command("selection.tweak", JSONObject()
        .put("phase", phase.name)
        .put("u", u).put("v", v)
        .put("dx", dx).put("dy", dy)
        .apply {
            settings?.let {
                put("motion", it.motion.name)
                put("snap_type", it.effectiveSnapType.name)
                put("snap_step", it.snapStep)
                put("clamp", it.clamp)
            }
        })

    override fun transformBegin(
        mode: TransformMode,
        axes: Set<Axis>,
        step: Double,
        snapType: SnapType,
        orientation: Orientation,
        valueMode: ValueMode,
    ) =
        command(
            "transform.begin",
            JSONObject()
                .put("mode", mode.name)
                .put("axes", axesArray(axes))
                // `snap` es el booleano histórico y `snap_type` el que manda; se
                // envían coherentes para no depender de cuál lea el servidor.
                .put("snap", snapType != SnapType.NONE)
                .put("snap_type", snapType.name)
                .put("step", step)
                .put("orientation", orientation.name)
                .put("value_mode", valueMode.name),
        )

    override fun transformAxes(axes: Set<Axis>) =
        command("transform.axes", JSONObject().put("axes", axesArray(axes)))

    override fun transformOrientation(orientation: Orientation) =
        command("transform.orientation", JSONObject().put("orientation", orientation.name))

    override fun transformSnap(snapType: SnapType, step: Double, snapToSelection: Boolean) = command(
        "transform.snap",
        JSONObject()
            .put("snap", snapType != SnapType.NONE)
            .put("snap_type", snapType.name)
            .put("snap_to_selection", snapToSelection)
            .put("step", step),
    )

    override fun transformSnapCandidate(u: Double, v: Double, snapType: SnapType, lock: Boolean) {
        pendingTransformSnap = ToolSnapRequest(u, v, snapType, lock)
        flushTransformSnap()
    }

    override fun transformReferenceCandidate(u: Double, v: Double, lock: Boolean, role: String) = command(
        "transform.reference_candidate",
        JSONObject().put("u", u).put("v", v).put("lock", lock).put("role", role),
    )

    override fun transformReferenceClear(role: String) = command(
        "transform.reference_candidate", JSONObject().put("clear", true).put("role", role),
    )

    override fun transformCenterPreset(preset: String) = command(
        "transform.reference_candidate",
        JSONObject().put("role", "CENTER").put("preset", preset),
    )

    override fun editSettings(parameters: Map<String, Any?>) =
        command("edit.settings_set", JSONObject(parameters))

    private fun flushTransformSnap() {
        if (!transformSnapInFlight.compareAndSet(false, true)) return
        val request = pendingTransformSnap
        if (request == null || !_transformSession.value.active) {
            transformSnapInFlight.set(false)
            return
        }
        pendingTransformSnap = null
        command(
            "transform.snap_candidate",
            JSONObject().put("u", request.u).put("v", request.v)
                .put("snap_type", request.type.name).put("lock", request.lock),
        )
    }

    override fun transformValue(values: List<Double>?, angleDegrees: Double?, dimensions: List<Double>?) {
        val payload = JSONObject()
        values?.let { payload.put("values", JSONArray(it)) }
        angleDegrees?.let { payload.put("angle", it) }
        dimensions?.let { payload.put("dimensions", JSONArray(it)) }
        command("transform.value", payload)
    }

    override fun transformConfirm() = command("transform.confirm")
    override fun transformCancel() = command("transform.cancel")

    override fun toolBegin(tool: EditTool, parameters: Map<String, Any?>) =
        command(
            "tool.begin",
            JSONObject()
                .put("tool", tool.wire)
                .put("parameters", JSONObject(parameters)),
        )

    override fun toolFacePick(u: Double, v: Double, role: String, phase: String) = command(
        "tool.face_pick", JSONObject().put("u", u).put("v", v).put("role", role).put("phase", phase),
    )

    override fun toolParameter(parameters: Map<String, Any?>) =
        command("tool.parameter", JSONObject().put("parameters", JSONObject(parameters)))

    override fun toolSnapCandidate(u: Double, v: Double, snapType: SnapType, lock: Boolean) {
        pendingToolSnap = ToolSnapRequest(u, v, snapType, lock)
        flushToolSnap()
    }

    private fun flushToolSnap() {
        if (!toolSnapInFlight.compareAndSet(false, true)) return
        val request = pendingToolSnap
        if (request == null || !_toolSession.value.active) {
            toolSnapInFlight.set(false)
            return
        }
        pendingToolSnap = null
        command(
            "tool.snap_candidate",
            JSONObject().put("u", request.u).put("v", request.v)
                .put("snap_type", request.type.name).put("lock", request.lock),
        )
    }

    /**
     * Empuja el parámetro primario mientras se arrastra el dedo.
     *
     * Cada `tool.nudge` reconstruye la malla entera desde la copia BMesh y vuelve a
     * ejecutar la operación, así que **no se encadena uno nuevo hasta que conteste el
     * anterior**: el arrastre se acumula y se manda de golpe. Así el ritmo lo marca lo
     * que Blender puede digerir y no los 30 Hz del dedo, que en una malla densa
     * dejarían al hilo principal sin aire. Es el mismo motivo por el que los gestos de
     * navegación van por su canal y no como comandos.
     */
    override fun toolNudge(delta: Double) {
        // Defensa de frontera: Knife/Bisect nunca admiten nudge aunque otro caller
        // invoque accidentalmente este método en el futuro.
        if (!_toolSession.value.acceptsViewportNudge) return
        val key = _toolSession.value.primaryKey
        val limit = when (key) {
            "cuts" -> 1.0
            // Loop Cut necesita conservar una porción útil del arrastre mientras
            // Blender reconstruye el preview. 0.02 descartaba casi todo el gesto
            // con lápiz y hacía depender la velocidad de la latencia del servidor.
            "factor" -> 0.12
            else -> 0.025
        }
        // Solo conservamos un paso pequeño mientras hay preview en vuelo. Acumular
        // todo el arrastre sin imagen hacía que, al contestar Blender, la herramienta
        // saltase violentamente hasta una posición que el usuario nunca pudo ver.
        pendingNudge = (pendingNudge + delta).coerceIn(-limit, limit)
        flushNudge()
    }

    private fun flushNudge() {
        if (nudgeInFlight || pendingNudge == 0.0) return
        if (!_toolSession.value.active) {
            pendingNudge = 0.0
            return
        }
        val delta = pendingNudge
        pendingNudge = 0.0
        nudgeInFlight = true
        command("tool.nudge", JSONObject().put("delta", delta))
    }

    override fun toolConfirm() = command("tool.confirm")
    override fun toolCancel() = command("tool.cancel")

    private val _loopProbe = MutableStateFlow<LoopProbe?>(null)
    override val loopProbe: StateFlow<LoopProbe?> = _loopProbe.asStateFlow()

    override fun meshLoopProbe(u: Double, v: Double) =
        command("mesh.loop_probe", JSONObject().put("u", u).put("v", v))

    override fun clearLoopProbe() {
        _loopProbe.value = null
    }

    override fun toolLoopPick(u: Double, v: Double, add: Boolean) =
        command("tool.loop_pick", JSONObject().put("u", u).put("v", v).put("add", add))

    override fun toolLoopPop() = command("tool.loop_pop")

    override fun toolKnifePoint(u: Double, v: Double) =
        command("tool.knife_point", JSONObject().put("u", u).put("v", v))

    override fun toolKnifeDrag(phase: GesturePhase, u: Double, v: Double) {
        pendingKnifeDrag = KnifeDragRequest(phase, u, v)
        flushKnifeDrag()
    }

    private fun flushKnifeDrag() {
        if (!knifeDragInFlight.compareAndSet(false, true)) return
        val request = pendingKnifeDrag
        if (request == null || !_toolSession.value.active) {
            knifeDragInFlight.set(false)
            return
        }
        pendingKnifeDrag = null
        command("tool.knife_drag", JSONObject().put("phase", request.phase.name)
            .put("u", request.u).put("v", request.v))
    }

    override fun requestToolStatus() = command("tool.status")

    override fun toolKnifePop() = command("tool.knife_pop")

    override fun toolKnifeNewStroke() = command("tool.knife_new_stroke")

    override fun toolKnifeClose() = command("tool.knife_close")

    override fun toolDragLine(startU: Double, startV: Double, endU: Double, endV: Double) = command(
        "tool.drag_line",
        JSONObject()
            .put("start", JSONArray(listOf(startU, startV)))
            .put("end", JSONArray(listOf(endU, endV))),
    )

    private fun axesArray(axes: Set<Axis>) = JSONArray().apply {
        // Se mandan siempre en orden X, Y, Z: en ROTATE el servidor usa el primero,
        // y un Set no garantiza cuál sería.
        for (axis in Axis.entries) if (axis in axes) put(axis.name)
    }

    override fun setLocation(x: Double, y: Double, z: Double) = absolute("transform.move", x, y, z)
    override fun setRotation(x: Double, y: Double, z: Double) = absolute("transform.rotate", x, y, z)
    override fun setScale(x: Double, y: Double, z: Double) = absolute("transform.scale", x, y, z)

    /** `absolute` hace que el servidor asigne el valor en vez de sumarlo. */
    private fun absolute(name: String, x: Double, y: Double, z: Double) =
        command(name, JSONObject().put("x", x).put("y", y).put("z", z).put("absolute", true))

    /**
     * [generation] identifica el intento al que pertenece este listener. Un socket
     * abandonado puede seguir notificando después de que hayamos abierto otro, y sus
     * eventos no deben tocar el estado ni disparar reintentos. Comparar la instancia
     * de WebSocket no serviría: un fallo inmediato llega antes de que `socket` esté
     * asignado.
     */
    private inner class Listener(
        private val destination: Target,
        private val generation: Int,
    ) : WebSocketListener() {
        private val stale: Boolean get() = generation != this@WebSocketRemoteBlenderClient.generation.get()

        override fun onOpen(webSocket: WebSocket, response: Response) {
            if (stale) return
            attempt = 0
            _retryAttempt.value = 0
            _errors.value = null
            _connection.value = ConnectionStatus.CONNECTED
            requestState()
            command("server.capabilities")
            // El nombre del .blend va en la barra superior desde el primer momento.
            fileInfo()
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            if (stale) return
            runCatching { handle(JSONObject(text)) }
                .onFailure { _errors.value = "Mensaje remoto no válido: ${it.message}" }
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            if (stale) return
            // Solo el primer fallo se muestra: repetir el mismo error en cada
            // reintento convierte el aviso en ruido permanente.
            if (attempt == 0) _errors.value = t.message ?: "Error de conexión"
            scheduleRetry(destination)
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            if (stale) return
            // El servidor ha cerrado (Blender se cierra, el add-on se reinicia):
            // también se reintenta, es el caso más común de reconexión.
            scheduleRetry(destination)
        }
    }

    private fun handle(message: JSONObject) {
        when (message.optString("type")) {
            "response" -> {
                val id = message.optString("id")
                val command = pending.remove(id)
                val sent = sentAtNs.remove(id)
                if (command == "selection.pick" || command == "selection.shortest_path") pickInFlight.set(false)
                if (sent != null && (command == "selection.pick" || command == "selection.shortest_path" || command?.startsWith("transform.") == true)) {
                    Log.d(LATENCY_TAG, "response command=$command ok=${message.optBoolean("ok", false)} rtt=${(System.nanoTime() - sent) / 1_000_000}ms")
                }
                if (command == "scene.get_state") stateRequestInFlight.set(false)
                // El servidor devuelve el estado en "result" (ver docs/protocol.md).
                val result = message.optJSONObject("result")
                // El hueco queda libre incluso si el nudge falló: si no, un error
                // dejaría la herramienta sorda al arrastre para siempre.
                if (command == "tool.nudge") nudgeInFlight = false
                if (command == "tool.snap_candidate") toolSnapInFlight.set(false)
                if (command == "tool.knife_drag") knifeDragInFlight.set(false)
                if (command == "transform.snap_candidate") transformSnapInFlight.set(false)
                // La copia nace pegada al original, así que el duplicado no se ve y el
                // toque se repite creyendo que no funcionó. Se avisa aparte del `when`
                // de abajo para no robarle el refresco de estado a la rama genérica.
                if (command != null && message.optBoolean("ok", false)) {
                    duplicateNotice(command, result)?.let {
                        _notices.value = it
                        // Solo cuando el servidor confirma que creó algo: armar el Mover
                        // antes de eso agarraría el original, no la copia.
                        _duplicates.tryEmit(Unit)
                    }
                }
                when {
                    !message.optBoolean("ok", false) -> {
                        // Un sondeo fallido no es un error que enseñar: significa que
                        // bajo el dedo no había nada, y el menú radial ya sabe qué
                        // ofrecer en ese caso. Lo mismo el sondeo de loop cut.
                        if (command == "snap.query") _touchProbe.value = TouchProbe(hit = false)
                        else if (command == "mesh.loop_probe") _loopProbe.value = LoopProbe(hit = false)
                        else if (command == "tool.snap_candidate") flushToolSnap()
                        else if (command == "tool.knife_drag") flushKnifeDrag()
                        else if (command == "transform.snap_candidate") flushTransformSnap()
                        // Una línea de Bisect que no cruza geometría es un intento normal
                        // (el usuario dibuja de nuevo), no un error que enseñar: el
                        // backend ya deja la tool exactamente como estaba (armada o
                        // activa con el plano anterior).
                        else if (command == "tool.drag_line") Unit
                        else _errors.value = message.optString("error", "Error remoto")
                    }
                    command != null && command.startsWith("cad.") -> result?.let {
                        _state.value = _state.value.copy(cad = CadParser.state(it))
                    }
                    command == "mode.set" && _state.value.features.cad.available -> cadCommand("cad.state")
                    command == "scene.get_state" -> result?.let(::updateState)
                    command == "server.capabilities" -> result?.let { caps ->
                        _state.value = _state.value.copy(
                            features = StateParser.features(caps),
                            unitScaleLength = StateParser.unitScaleLength(caps),
                        )
                    }
                    command == "modifier.add_options" -> result?.let { options ->
                        _state.value = _state.value.copy(modifierOptions = StateParser.modifierOptions(options))
                    }
                    command == "scene.list_objects" -> result?.let { listing ->
                        _state.value = _state.value.copy(objects = StateParser.objects(listing.optJSONArray("objects")))
                    }
                    command == "scene.scale" -> result?.let { scales ->
                        _sceneScalePresets.value = StateParser.sceneScalePresets(scales)
                        scales.optJSONObject("scale")?.let { scale ->
                            _state.value = _state.value.copy(
                                sceneScale = StateParser.sceneScale(scale),
                                unitScaleLength = StateParser.sceneScaleLength(
                                    scale, _state.value.unitScaleLength),
                            )
                        }
                    }
                    // Responde con la escala ya aplicada: se pinta sin esperar al
                    // siguiente snapshot, que puede tardar hasta 100 ms.
                    command == "scene.scale_set" -> result?.let { scale ->
                        _state.value = _state.value.copy(
                            sceneScale = StateParser.sceneScale(scale),
                            unitScaleLength = StateParser.sceneScaleLength(
                                scale, _state.value.unitScaleLength),
                        )
                    }
                    command != null && command.startsWith("modifier.") -> result?.let { stack ->
                        _state.value = _state.value.copy(modifiers = StateParser.modifiers(stack.optJSONArray("modifiers")))
                    }
                    (command == "object.hide" || command == "object.reveal") -> result?.let { visibility ->
                        _state.value = _state.value.copy(
                            hiddenObjects = StateParser.hiddenObjects(visibility.optJSONArray("hidden_objects")),
                            selectedObjects = (visibility.optJSONArray("selected_objects") ?: JSONArray()).let { a -> (0 until a.length()).map { a.optString(it) } },
                            activeObject = visibility.optString("active_object").takeIf { it.isNotBlank() && it != "null" })
                    }
                    command == "object.shade" -> result?.let(::updateState)
                    // selection.pick ya incluye el snapshot: evita esperar el evento
                    // semántico y hacer un segundo viaje scene.get_state. Lo mismo
                    // box/circle/more/less, que vuelven con el estado completo.
                    command == "selection.pick" || command == "selection.shortest_path" ||
                        command == "selection.box" || command == "selection.circle" ||
                        command == "selection.more" || command == "selection.less" -> result?.let(::updateState)
                    // El toggle de wireframe responde con el shading nuevo: pintarlo ya,
                    // sin esperar al scene.get_state de seguimiento.
                    command == "view.shading" -> result?.let { r ->
                        val shading = if (r.optString("shading") == "WIREFRAME") Shading.WIREFRAME else Shading.SOLID
                        _state.value = _state.value.copy(view = _state.value.view.copy(shading = shading))
                    }
                    command == "edit.settings_set" -> result?.let(::updateState)
                    command == "file.locations" -> updateFileLocations(result)
                    command == "file.browse" -> updateFileBrowser(result)
                    command == "file.default_folder" -> {
                        updateFileLocations(result)
                        fileBrowse(result?.optString("default_folder")?.takeIf { it.isNotBlank() })
                    }
                    // Los modales devuelven el estado de la sesión; confirmar y
                    // cancelar la cierran y sí necesitan refrescar la escena.
                    command in MODAL_COMMANDS -> {
                        acceptTransformSession(
                            StateParser.session(result), allowReplace = command == "transform.begin",
                        )
                        if (command == "transform.snap_candidate") {
                            transformSnapInFlight.set(false)
                            flushTransformSnap()
                        }
                    }
                    command in TOOL_COMMANDS -> {
                        _toolSession.value = StateParser.toolSession(result)
                        if (command == "tool.snap_candidate") {
                            toolSnapInFlight.set(false)
                            flushToolSnap()
                        }
                        if (command == "tool.knife_drag") {
                            knifeDragInFlight.set(false)
                            flushKnifeDrag()
                        }
                        // Lo que se acumuló mientras el servidor pensaba sale ahora.
                        flushNudge()
                    }
                    // Sondeo del menú radial: no cambia nada de la escena, solo
                    // cuenta qué hay bajo el dedo.
                    command == "snap.query" -> _touchProbe.value = TouchProbe(
                        hit = result?.optBoolean("hit") == true,
                        objectName = result?.optString("object")?.takeIf { it.isNotBlank() && it != "null" },
                        elementId = result?.optString("id")?.takeIf { it.isNotBlank() },
                    )
                    // Sondeo de loop cut: igual de silencioso si no hay nada bajo
                    // el dedo — la bandeja sigue mostrando el hint de "toca la malla".
                    command == "mesh.loop_probe" -> _loopProbe.value = StateParser.loopProbe(result)
                    command == "transform.confirm" || command == "transform.cancel" -> {
                        _transformSession.value = TransformSession()
                        requestState()
                    }
                    command == "tool.confirm" || command == "tool.cancel" -> {
                        _toolSession.value = ToolSession()
                        requestState()
                    }
                    command != null && command.startsWith("file.") -> {
                        result?.let(::updateFileInfo)
                        // Abrir o empezar de cero cambia la escena entera: el estado
                        // que teníamos es de otro archivo.
                        if (command == "file.new" || command == "file.open") requestState()
                    }
                    command != null && System.currentTimeMillis() - lastStateRefreshAt >= 200L -> {
                        lastStateRefreshAt = System.currentTimeMillis()
                        requestState()
                    }
                }
            }
            "event" -> {
                val payload = message.optJSONObject("payload")
                when {
                    message.optString("event") == "error" ->
                        _errors.value = payload?.optString("message") ?: "Error remoto"
                    // Marcador en vivo del arrastre. Llega a 10 Hz y NO debe pedir el
                    // estado completo: sería un viaje por cada fotograma del gesto.
                    message.optString("event") == "transform.session" ->
                        acceptTransformSession(StateParser.session(payload))
                    message.optString("event") == "cad.state" ->
                        _state.value = _state.value.copy(cad = CadParser.state(payload))
                    message.optString("event") == "tool.session" ->
                        _toolSession.value = StateParser.toolSession(payload)
                    message.optString("event") == "modifiers.changed" -> payload?.let {
                        _state.value = _state.value.copy(modifiers = StateParser.modifiers(it.optJSONArray("modifiers")))
                    }
                    message.optString("event") == "visibility.changed" -> payload?.let {
                        _state.value = _state.value.copy(hiddenObjects = StateParser.hiddenObjects(it.optJSONArray("hidden_objects")))
                    }
                    // scene.changed al conectar ya trae el estado completo: nos ahorra el viaje.
                    payload?.has("mode") == true -> updateState(payload)
                    else -> {
                        // Durante un modal el vídeo y transform.session son el
                        // feedback en vivo. Pedir además snapshots completos por
                        // cada scene.changed compite con el gesto en la cola de
                        // Blender. selection.pick ya devuelve su propio snapshot.
                        if (shouldRequestSceneSnapshot(
                                transformActive = _transformSession.value.active,
                                toolActive = _toolSession.value.active,
                                selectionPending = pickInFlight.get(),
                            )
                        ) requestState()
                    }
                }
            }
            "hello" -> {
                if (message.optBoolean("auth_required") && token.isBlank()) {
                    _errors.value = "Este servidor exige token"
                }
                // El vídeo va al mismo host que el control, pero a su propio puerto.
                val stream = message.optJSONObject("stream")
                val destination = target
                _streamEndpoint.value = if (destination != null && stream?.optBoolean("running") == true) {
                    val alternatives = stream.optJSONArray("alternatives")
                    StreamEndpoint(
                        destination.host, stream.optInt("port"), token,
                        stream.optString("format"), stream.optString("path"),
                        stream.optString("framing").ifBlank { null },
                        (0 until (alternatives?.length() ?: 0)).mapNotNull { index ->
                            alternatives?.optJSONObject(index)?.let {
                                StreamAlternative(it.optString("format"), it.optString("path"))
                            }
                        },
                    )
                } else {
                    null
                }
            }
        }
    }

    private fun updateFileInfo(json: JSONObject) {
        _file.value = FileInfo(
            name = json.optString("name").ifBlank { "Sin título" },
            path = json.optString("path"),
            saved = json.optBoolean("saved"),
            dirty = json.optBoolean("dirty"),
        )
    }

    private fun updateFileLocations(json: JSONObject?) {
        val parsed = StateParser.fileLocations(json)
        _remoteFiles.value = _remoteFiles.value.copy(
            defaultFolder = parsed.defaultFolder,
            locations = parsed.locations,
            loading = false,
        )
    }

    private fun updateFileBrowser(json: JSONObject?) {
        val parsed = StateParser.fileBrowse(json)
        _remoteFiles.value = _remoteFiles.value.copy(
            path = parsed.path,
            parent = parsed.parent,
            defaultFolder = parsed.defaultFolder,
            breadcrumbs = parsed.breadcrumbs,
            entries = parsed.entries,
            loading = false,
        )
    }

    private fun acceptTransformSession(incoming: TransformSession, allowReplace: Boolean = false) {
        val current = _transformSession.value
        if (shouldAcceptTransformSession(current, incoming, allowReplace)) {
            _transformSession.value = incoming
        }
    }

    private fun updateState(json: JSONObject) {
        val old = _state.value
        val parsed = StateParser.state(json)
        // Los snapshots de selección (pick/box/circle/more/less) se piden con
        // include_view=False: no traen ni vista ni shading. Conservar lo que ya
        // sabíamos en vez de rebobinar la proyección y el wireframe.
        _state.value = parsed.copy(
            features = old.features,
            cad = if (json.has("cad")) parsed.cad else old.cad,
            modifierOptions = old.modifierOptions,
            view = if (json.has("view") || json.has("shading")) parsed.view else old.view,
            unitScaleLength = json.optJSONObject("scene_scale")?.let { scale ->
                StateParser.sceneScaleLength(scale, old.unitScaleLength)
            } ?: old.unitScaleLength,
            // La escala viaja con la vista, así que un snapshot de selección tampoco
            // la trae y volvería al preset por defecto en cada toque.
            sceneScale = if (json.has("scene_scale")) parsed.sceneScale else old.sceneScale,
        )
    }
}

internal fun shouldAcceptTransformSession(
    current: TransformSession,
    incoming: TransformSession,
    allowReplace: Boolean = false,
): Boolean = allowReplace || !current.active ||
    (incoming.active && incoming.sessionId != null && incoming.sessionId == current.sessionId)

internal fun duplicateCommand(mode: BlenderMode): String =
    if (mode == BlenderMode.EDIT) "mesh.duplicate" else "object.duplicate"

/**
 * Texto del aviso de duplicado, o null si la respuesta no dice que se creara nada.
 *
 * La copia aparece superpuesta al original, así que sin confirmación el toque parece
 * perdido y se repite. Se nombra la unidad que el usuario cree estar duplicando —la de
 * su submodo—, no las tres a la vez: duplicar una cara arrastra sus aristas y vértices,
 * y decir "4 vértices, 4 aristas, 1 cara" describe la topología, no el gesto.
 */
internal fun duplicateNotice(command: String, result: JSONObject?): String? {
    if (result == null || (command != "mesh.duplicate" && command != "object.duplicate")) return null
    if (command == "object.duplicate") {
        val created = result.optJSONArray("created")?.length() ?: 0
        return if (created > 0) plural(created, "objeto duplicado", "objetos duplicados") else null
    }
    val counts = result.optJSONObject("duplicated") ?: return null
    val faces = counts.optInt("faces")
    val edges = counts.optInt("edges")
    val verts = counts.optInt("verts")
    return when {
        faces > 0 -> plural(faces, "cara duplicada", "caras duplicadas")
        edges > 0 -> plural(edges, "arista duplicada", "aristas duplicadas")
        verts > 0 -> plural(verts, "vértice duplicado", "vértices duplicados")
        else -> null
    }
}

private fun plural(count: Int, singular: String, plural: String) =
    if (count == 1) "1 $singular" else "$count $plural"
