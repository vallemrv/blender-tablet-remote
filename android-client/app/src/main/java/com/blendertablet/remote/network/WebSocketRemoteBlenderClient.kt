package com.blendertablet.remote.network

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
import com.blendertablet.remote.model.RecentFile
import com.blendertablet.remote.model.SelectionMode
import com.blendertablet.remote.model.SnapAction
import com.blendertablet.remote.model.SnapType
import com.blendertablet.remote.model.ToolSession
import com.blendertablet.remote.model.TouchProbe
import com.blendertablet.remote.model.TransformMode
import com.blendertablet.remote.model.TransformSession
import com.blendertablet.remote.model.ValueMode
import java.net.Proxy
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
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
    private val _retryAttempt = MutableStateFlow(0)
    private val _file = MutableStateFlow(FileInfo())
    private val _recentFiles = MutableStateFlow<List<RecentFile>>(emptyList())
    private val _transformSession = MutableStateFlow(TransformSession())
    private val _toolSession = MutableStateFlow(ToolSession())
    private val _touchProbe = MutableStateFlow<TouchProbe?>(null)
    private val _streamEndpoint = MutableStateFlow<StreamEndpoint?>(null)
    override val connection: StateFlow<ConnectionStatus> = _connection.asStateFlow()
    override val state: StateFlow<BlenderState> = _state.asStateFlow()
    override val errors: StateFlow<String?> = _errors.asStateFlow()
    override val retryAttempt: StateFlow<Int> = _retryAttempt.asStateFlow()
    override val file: StateFlow<FileInfo> = _file.asStateFlow()
    override val recentFiles: StateFlow<List<RecentFile>> = _recentFiles.asStateFlow()
    override val transformSession: StateFlow<TransformSession> = _transformSession.asStateFlow()
    override val toolSession: StateFlow<ToolSession> = _toolSession.asStateFlow()
    override val touchProbe: StateFlow<TouchProbe?> = _touchProbe.asStateFlow()
    override val streamEndpoint: StateFlow<StreamEndpoint?> = _streamEndpoint.asStateFlow()

    /** A dónde queremos estar conectados. null = el usuario ha pedido desconectar. */
    private data class Target(val host: String, val port: Int, val token: String)

    private companion object {
        /**
         * Comandos cuya respuesta ES el estado de la sesión modal. No incluye
         * `transform.move/rotate/scale`, que son transformaciones sueltas y sí deben
         * refrescar la escena.
         */
        val MODAL_COMMANDS = setOf(
            "transform.begin", "transform.axes", "transform.snap",
            "transform.value", "transform.nudge", "transform.status",
            "transform.snap_candidate",
        )

        /** Comandos cuya respuesta ES el estado de la sesión de herramienta. */
        val TOOL_COMMANDS = setOf(
            "tool.begin", "tool.parameter", "tool.nudge", "tool.status",
        )
    }

    @Volatile private var target: Target? = null
    @Volatile private var socket: WebSocket? = null
    private var retryJob: Job? = null
    private var attempt = 0
    private val generation = AtomicInteger(0)
    private val pending = ConcurrentHashMap<String, String>()
    @Volatile private var lastStateRefreshAt = 0L

    /** Arrastre acumulado que todavía no se ha mandado como `tool.nudge`. */
    @Volatile private var pendingNudge = 0.0
    @Volatile private var nudgeInFlight = false

    private val token: String get() = target?.token.orEmpty()

    override fun connect(host: String, port: Int, token: String) {
        val next = Target(host, port, token)
        target = next
        attempt = 0
        _retryAttempt.value = 0
        _errors.value = null
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
        attempt = 0
        _retryAttempt.value = 0
        _streamEndpoint.value = null
        _transformSession.value = TransformSession()
        _toolSession.value = ToolSession()
        _touchProbe.value = null
        pendingNudge = 0.0
        nudgeInFlight = false
        _connection.value = ConnectionStatus.DISCONNECTED
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
        val generation = this.generation.incrementAndGet()
        retryJob?.cancel()
        retryJob = null
        // cancel() y no close(): el socket viejo puede estar medio muerto y esperar
        // su handshake de cierre retrasaría el intento nuevo hasta el timeout.
        socket?.cancel()
        pending.clear()
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

    private fun command(name: String, payload: JSONObject = JSONObject()) {
        val id = UUID.randomUUID().toString()
        val message = JSONObject()
            .put("type", "command")
            .put("id", id)
            .put("command", name)
            .put("payload", payload)
        if (token.isNotBlank()) message.put("token", token)
        if (socket?.send(message.toString()) == true) pending[id] = name else reportOffline()
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
     */
    override fun gesture(
        gesture: Gesture,
        phase: GesturePhase,
        dx: Double,
        dy: Double,
        factor: Double,
        axis: Axis?,
    ) {
        val message = JSONObject()
            .put("type", "gesture")
            .put("gesture", gesture.name.lowercase())
            .put("phase", phase.name.lowercase())
            .put("dx", dx)
            .put("dy", dy)
            .put("factor", factor)
        axis?.let { message.put("axis", it.name) }
        if (token.isNotBlank()) message.put("token", token)
        if (socket?.send(message.toString()) != true) reportOffline()
    }

    override fun requestState() = command("scene.get_state")
    override fun select(name: String?) = command("object.select", JSONObject().apply { name?.let { put("name", it) } })
    override fun pick(u: Double, v: Double, threshold: Double) = command(
        "selection.pick",
        JSONObject().put("u", u).put("v", v).put("threshold", threshold),
    )
    override fun delete() = command("object.delete")
    override fun duplicate() = command("object.duplicate")
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
    override fun selectLoop() = command("selection.loop")
    override fun selectRing() = command("selection.ring")

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
    override fun revealSelection() = command("selection.reveal")
    override fun hideObjects(objects: List<String>?, unselected: Boolean) = command("object.hide", JSONObject().apply {
        objects?.let { put("objects", JSONArray(it)) }; put("unselected", unselected)
    })
    override fun revealObjects(objects: List<String>?, select: Boolean) = command("object.reveal", JSONObject().apply {
        objects?.let { put("objects", JSONArray(it)) }; put("select", select)
    })
    override fun transformApply(location: Boolean, rotation: Boolean, scale: Boolean) = command(
        "transform.apply", JSONObject().put("location", location).put("rotation", rotation).put("scale", scale))
    override fun requestModifierOptions() = command("modifier.add_options")
    override fun modifierAdd(type: String, parameters: Map<String, Any?>) = command("modifier.add", JSONObject().put("type", type).put("parameters", JSONObject(parameters)))
    override fun modifierRemove(name: String) = command("modifier.remove", JSONObject().put("name", name))
    override fun modifierMove(name: String, index: Int) = command("modifier.move", JSONObject().put("name", name).put("index", index))
    override fun modifierSet(name: String, parameters: Map<String, Any?>) = command("modifier.set", JSONObject().put("name", name).put("parameters", JSONObject(parameters)))
    override fun modifierToggle(name: String, viewport: Boolean?, render: Boolean?) = command("modifier.toggle", JSONObject().put("name", name).apply { viewport?.let { put("viewport", it) }; render?.let { put("render", it) } })
    override fun modifierApply(name: String) = command("modifier.apply", JSONObject().put("name", name))
    override fun meshDelete(what: String) = command("mesh.delete", JSONObject().put("what", what))
    override fun undo() = command("history.undo")
    override fun redo() = command("history.redo")
    override fun frameSelected() = command("view.frame_selected")
    override fun viewAxis(name: String) = command("view.axis", JSONObject().put("axis", name))
    override fun viewFrameAll() = command("view.frame_all")
    override fun viewPerspective(projection: Projection) =
        command("view.perspective", JSONObject().put("mode", projection.name))

    override fun addPrimitive(primitive: AddObject) =
        command("object.add", JSONObject().put("primitive", primitive.name))

    override fun snap(action: SnapAction) = command(action.command)

    override fun fileInfo() = command("file.info")
    override fun fileNew() = command("file.new")
    override fun fileOpen(path: String) = command("file.open", JSONObject().put("path", path))
    override fun fileSave() = command("file.save")
    override fun fileSaveAs(path: String) = command("file.save_as", JSONObject().put("path", path))
    override fun requestRecentFiles() = command("file.recent", JSONObject().put("limit", 12))

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

    override fun transformSnap(snapType: SnapType, step: Double) = command(
        "transform.snap",
        JSONObject()
            .put("snap", snapType != SnapType.NONE)
            .put("snap_type", snapType.name)
            .put("step", step),
    )

    override fun transformSnapCandidate(u: Double, v: Double, snapType: SnapType, lock: Boolean) = command(
        "transform.snap_candidate",
        JSONObject().put("u", u).put("v", v).put("snap_type", snapType.name).put("lock", lock),
    )

    override fun transformValue(values: List<Double>?, angleDegrees: Double?) {
        val payload = JSONObject()
        values?.let { payload.put("values", JSONArray(it)) }
        angleDegrees?.let { payload.put("angle", it) }
        command("transform.value", payload)
    }

    override fun transformConfirm() = command("transform.confirm")
    override fun transformCancel() = command("transform.cancel")

    override fun toolBegin(tool: EditTool, parameters: Map<String, Double>) =
        command(
            "tool.begin",
            JSONObject()
                .put("tool", tool.wire)
                .put("parameters", JSONObject(parameters)),
        )

    override fun toolParameter(parameters: Map<String, Double>) =
        command("tool.parameter", JSONObject().put("parameters", JSONObject(parameters)))

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
        val key = _toolSession.value.primaryKey
        val limit = when (key) {
            "cuts" -> 1.0
            "factor" -> 0.02
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
                // El servidor devuelve el estado en "result" (ver docs/protocol.md).
                val result = message.optJSONObject("result")
                // El hueco queda libre incluso si el nudge falló: si no, un error
                // dejaría la herramienta sorda al arrastre para siempre.
                if (command == "tool.nudge") nudgeInFlight = false
                when {
                    !message.optBoolean("ok", false) -> {
                        // Un sondeo fallido no es un error que enseñar: significa que
                        // bajo el dedo no había nada, y el menú radial ya sabe qué
                        // ofrecer en ese caso.
                        if (command == "snap.query") _touchProbe.value = TouchProbe(hit = false)
                        else _errors.value = message.optString("error", "Error remoto")
                    }
                    command == "scene.get_state" -> result?.let(::updateState)
                    command == "server.capabilities" -> result?.let { caps ->
                        _state.value = _state.value.copy(features = StateParser.features(caps))
                    }
                    command == "modifier.add_options" -> result?.let { options ->
                        _state.value = _state.value.copy(modifierOptions = StateParser.modifierOptions(options))
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
                    // selection.pick ya incluye el snapshot: evita esperar el evento
                    // semántico y hacer un segundo viaje scene.get_state.
                    command == "selection.pick" -> result?.let(::updateState)
                    command == "file.recent" -> updateRecentFiles(result)
                    // Los modales devuelven el estado de la sesión; confirmar y
                    // cancelar la cierran y sí necesitan refrescar la escena.
                    command in MODAL_COMMANDS -> _transformSession.value = StateParser.session(result)
                    command in TOOL_COMMANDS -> {
                        _toolSession.value = StateParser.toolSession(result)
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
                        _transformSession.value = StateParser.session(payload)
                    message.optString("event") == "modifiers.changed" -> payload?.let {
                        _state.value = _state.value.copy(modifiers = StateParser.modifiers(it.optJSONArray("modifiers")))
                    }
                    message.optString("event") == "visibility.changed" -> payload?.let {
                        _state.value = _state.value.copy(hiddenObjects = StateParser.hiddenObjects(it.optJSONArray("hidden_objects")))
                    }
                    // scene.changed al conectar ya trae el estado completo: nos ahorra el viaje.
                    payload?.has("mode") == true -> updateState(payload)
                    else -> requestState()
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
                    StreamEndpoint(destination.host, stream.optInt("port"), token)
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

    private fun updateRecentFiles(json: JSONObject?) {
        val files = json?.optJSONArray("files") ?: JSONArray()
        _recentFiles.value = (0 until files.length()).mapNotNull { index ->
            files.optJSONObject(index)?.let {
                RecentFile(
                    name = it.optString("name"),
                    path = it.optString("path"),
                    folder = it.optString("folder"),
                    exists = it.optBoolean("exists", true),
                )
            }
        }
    }

    private fun updateState(json: JSONObject) {
        val old = _state.value
        _state.value = StateParser.state(json).copy(
            features = old.features,
            modifierOptions = old.modifierOptions,
        )
    }
}
