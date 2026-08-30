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
import com.blendertablet.remote.model.RemoteFiles
import com.blendertablet.remote.model.SelectionMode
import com.blendertablet.remote.model.SelectionOp
import com.blendertablet.remote.model.SnapAction
import com.blendertablet.remote.model.SnapType
import com.blendertablet.remote.model.ToolSession
import com.blendertablet.remote.model.LoopProbe
import com.blendertablet.remote.model.TouchProbe
import com.blendertablet.remote.model.TransformMode
import com.blendertablet.remote.model.TransformSession
import com.blendertablet.remote.model.ValueMode
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.StateFlow
import com.blendertablet.remote.model.ModifierDefault

/** Dónde está el vídeo del viewport. Lo anuncia el servidor, no se configura a mano. */
data class StreamEndpoint(
    val host: String, val port: Int, val token: String,
    val format: String, val path: String, val framing: String? = null,
    val alternatives: List<StreamAlternative> = emptyList(),
)
data class StreamAlternative(val format: String, val path: String)

interface RemoteBlenderClient {
    val connection: StateFlow<ConnectionStatus>
    val state: StateFlow<BlenderState>
    val errors: StateFlow<String?>

    /**
     * Confirmación de una acción que salió bien pero no se ve en el viewport. Va por
     * separado de [errors] porque un éxito no se pinta con los colores de un fallo.
     */
    val notices: StateFlow<String?>

    /**
     * El servidor acaba de confirmar un duplicado que creó geometría u objetos. Es un
     * hecho, no una decisión: qué hacer después (encadenar un Mover) lo elige la capa
     * que conoce las preferencias del usuario, no esta.
     */
    val duplicates: Flow<Unit>

    /** Reintentos encadenados sin éxito; vuelve a 0 en cuanto la conexión se abre. */
    val retryAttempt: StateFlow<Int>

    /** El .blend abierto en el PC. */
    val file: StateFlow<FileInfo>

    val remoteFiles: StateFlow<RemoteFiles>

    /** La transformación modal en curso, según el servidor. */
    val transformSession: StateFlow<TransformSession>

    /** La herramienta paramétrica de Edit Mode en curso, según el servidor. */
    val toolSession: StateFlow<ToolSession>

    /**
     * Qué había bajo el dedo en la última pulsación larga. null = sin sondear.
     * Lo alimenta [probeTouch], que **no toca la selección**.
     */
    val touchProbe: StateFlow<TouchProbe?>

    /** null cuando no hay vídeo disponible (desconectado o captura apagada). */
    val streamEndpoint: StateFlow<StreamEndpoint?>

    /**
     * Fija el destino y se queda enganchado a él: si la conexión se cae, el cliente
     * reintenta solo con espera creciente hasta que [disconnect] diga lo contrario.
     */
    fun connect(host: String, port: Int, token: String)

    /** Corta y deja de reintentar. Solo lo pide el usuario. */
    fun disconnect()

    /** Borra el último error mostrado (el toast se auto-descarta a los ~5 s). */
    fun clearError()

    /** Borra el último aviso mostrado (el toast se auto-descarta a los ~3 s). */
    fun clearNotice()

    /**
     * Reintenta ya, sin esperar al backoff. Lo llaman los eventos que hacen probable
     * que ahora sí funcione: volver a primer plano o recuperar la red.
     */
    fun retryNow()
    fun requestState()
    fun select(name: String? = null)

    /**
     * Selección por toque: [u] y [v] normalizados 0..1 con origen arriba-izquierda.
     * El servidor lanza un rayo desde la cámara del viewport. [mode] aplica el
     * modificador Ctrl/Alt (ADD/REMOVE) o sustituye (SET).
     */
    fun pick(u: Double, v: Double, threshold: Double = 0.035, mode: SelectionOp = SelectionOp.SET)
    fun shortestPath(u: Double, v: Double, threshold: Double = 0.035, extend: Boolean = false)

    /**
     * Pregunta qué hay en [u], [v] **sin seleccionarlo**: es lo que necesita el menú
     * radial para responder a lo que hay bajo el dedo. La respuesta aparece en
     * [touchProbe].
     */
    fun probeTouch(u: Double, v: Double, snapType: SnapType)

    /** Olvida el último sondeo, al cerrar el menú radial. */
    fun clearProbe()

    fun delete()
    fun duplicate()
    fun duplicateLinked()
    /**
     * Renombra [target], o el objeto activo si no se dice cuál. El menú radial manda
     * siempre el que hay bajo el dedo: puede no ser el activo.
     */
    fun rename(newName: String, target: String? = null)
    fun selectAll(value: Boolean = true)

    /** Selecciona el objeto tocado; [add] lo añade a la selección en vez de sustituirla. */
    fun selectObject(name: String, add: Boolean)
    fun setMode(mode: BlenderMode)
    fun setSelectionMode(mode: SelectionMode)
    fun invertSelection()
    fun hideSelection()
    fun hideObjects(objects: List<String>? = null, unselected: Boolean = false)
    fun revealObjects(objects: List<String>? = null, select: Boolean = true)
    fun shadeObjects(objects: List<String>? = null, mode: String = "TOGGLE")
    fun transformApply(location: Boolean, rotation: Boolean, scale: Boolean)
    fun requestModifierOptions()

    /** Lista de objetos de la escena, para el picker de operando del Booleano. */
    fun listObjects()
    fun modifierAdd(type: String, parameters: Map<String, Any?> = emptyMap())
    fun modifierRemove(name: String)
    fun modifierMove(name: String, index: Int)
    fun modifierSet(name: String, parameters: Map<String, Any?>)
    fun modifierToggle(name: String, viewport: Boolean? = null, render: Boolean? = null)
    fun modifierApply(name: String)

    /** Loop y Ring parten de una arista ya seleccionada. */
    fun selectLoop(mode: SelectionOp = SelectionOp.SET)
    fun selectRing()

    /** La `L` de Blender: extiende la selección a las islas conectadas. */
    fun selectLinked()
    fun selectionTweak(phase: GesturePhase, u: Double = 0.0, v: Double = 0.0, dx: Double = 0.0, dy: Double = 0.0)
    fun meshDelete(what: String)
    fun undo()
    fun redo()

    /**
     * Gesto continuo. [dx] y [dy] son fracción de pantalla (1.0 = ancho completo),
     * no píxeles; [factor] es multiplicativo y solo lo usan ZOOM y SCALE.
     *
     * [axis] restringe el movimiento a un eje: es lo que manda el manipulador al
     * arrastrar una de sus flechas. El servidor lo lee en la fase BEGIN.
     */
    fun gesture(
        gesture: Gesture,
        phase: GesturePhase,
        dx: Double = 0.0,
        dy: Double = 0.0,
        factor: Double = 1.0,
        axis: Axis? = null,
    )

    fun frameSelected()

    /** Vista estándar: FRONT/BACK/LEFT/RIGHT/TOP/BOTTOM. */
    fun viewAxis(name: String)
    fun viewFrameAll()

    /** Cambia la proyección de la cámara remota. */
    fun viewPerspective(projection: Projection)

    /** Wireframe/sólido del viewport capturado. */
    fun viewShading(mode: String = "TOGGLE")

    /** Rejilla, ejes y demás overlays del viewport capturado. */
    fun viewOverlays(show: Boolean)

    /** Aísla la selección ocultando el resto (el `/` de Blender). */
    fun viewLocal(enabled: Boolean? = null)

    /** Crecer/disminuir la selección en Edit Mode (Ctrl+Plus / Ctrl+Minus). */
    fun selectMore()
    fun selectLess()

    /** Selección por caja: (u0,v0)-(u1,v1) normalizados, más [mode]. */
    fun boxSelect(u0: Double, v0: Double, u1: Double, v1: Double, mode: SelectionOp)

    /** Selección por círculo: centro (u,v) y [radius] normalizados, más [mode]. */
    fun circleSelect(u: Double, v: Double, radius: Double, mode: SelectionOp)

    /** Coloca el objeto activo en coordenadas absolutas (panel numérico). */
    fun setLocation(x: Double, y: Double, z: Double)

    /** Rotación absoluta en radianes. */
    fun setRotation(x: Double, y: Double, z: Double)

    fun setScale(x: Double, y: Double, z: Double)

    /** Añade una primitiva en el cursor 3D. */
    fun addPrimitive(primitive: AddObject)

    /** Ejecuta una entrada del menú de cursor/origen. */
    fun snap(action: SnapAction)

    fun fileInfo()
    fun fileNew()
    fun fileOpen(path: String)

    /** Falla con código `no_path` si el archivo no se ha guardado nunca. */
    fun fileSave()
    fun fileSaveAs(path: String)
    /** Forma segura para paths opacos: el backend une y valida carpeta y nombre. */
    fun fileSaveAs(folder: String, name: String)
    fun fileLocations()
    fun fileBrowse(path: String? = null)
    fun fileDefaultFolder(path: String)

    /**
     * Transformación modal: se abre, se ajusta cuantas veces haga falta y **solo
     * termina con [transformConfirm] o [transformCancel]**. Soltar el dedo no la
     * cierra, para poder recolocar la mano a mitad de un desplazamiento largo.
     */
    fun transformBegin(
        mode: TransformMode,
        axes: Set<Axis>,
        step: Double,
        snapType: SnapType = SnapType.NONE,
        orientation: Orientation = Orientation.GLOBAL,
        valueMode: ValueMode = ValueMode.RELATIVE,
    )

    fun transformAxes(axes: Set<Axis>)
    fun transformSnap(snapType: SnapType, step: Double)

    /**
     * Engancha el movimiento al elemento que haya en [u], [v]. Solo vale en MOVE: el
     * servidor responde `wrong_tool` en rotar y escalar.
     */
    fun transformSnapCandidate(u: Double, v: Double, snapType: SnapType, lock: Boolean = true)
    fun transformReferenceCandidate(u: Double, v: Double, lock: Boolean = false)
    fun transformReferenceClear()

    /** Valor exacto: [values] para mover/escalar, [angleDegrees] para rotar. */
    fun transformValue(values: List<Double>?, angleDegrees: Double?)
    fun transformConfirm()
    fun transformCancel()

    fun editSettings(parameters: Map<String, Any?>)

    /** Herramientas paramétricas de Edit Mode (preview → confirmar/cancelar). */
    fun toolBegin(tool: EditTool, parameters: Map<String, Any?>)
    fun toolParameter(parameters: Map<String, Any?>)
    fun toolNudge(delta: Double)
    fun toolSnapCandidate(u: Double, v: Double, snapType: SnapType, lock: Boolean = false)
    fun toolConfirm()
    fun toolCancel()
    fun meshDissolve(what: String)

    /**
     * Coloca el próximo loop cut donde caiga el toque (u,v): la respuesta llega en
     * [loopProbe] y trae la arista y el factor listos para `toolBegin`.
     */
    fun meshLoopProbe(u: Double, v: Double)

    /** Resultado del último [meshLoopProbe]; null = sin sondear. */
    val loopProbe: StateFlow<LoopProbe?>

    /** Olvida el último sondeo de loop cut. */
    fun clearLoopProbe()

    /** Re-ubica el corte de una sesión LOOP_CUT activa tocando la malla. */
    fun toolLoopPick(u: Double, v: Double, add: Boolean = false)
    fun toolLoopPop()

    /** Knife: añade un punto a la polilínea. */
    fun toolKnifePoint(u: Double, v: Double)
    fun toolKnifeDrag(phase: GesturePhase, u: Double, v: Double)
    fun requestToolStatus()
    fun toolKnifePop()
    fun toolKnifeNewStroke()
    fun toolKnifeClose()

    /**
     * Bisect: arrastre de línea completo (inicio/fin normalizados, al soltar el
     * dedo). Arma la sesión si estaba solo armada, o redibuja el plano si ya
     * estaba activa.
     */
    fun toolDragLine(startU: Double, startV: Double, endU: Double, endV: Double)

    /** Ejecuta exclusivamente un comando publicado por el catálogo Edit. */
    fun editCatalogCommand(command: String, payload: Map<String, Any?> = emptyMap())
}
