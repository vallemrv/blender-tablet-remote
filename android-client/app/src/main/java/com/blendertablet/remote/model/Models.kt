package com.blendertablet.remote.model

/**
 * RECONNECTING es distinto de CONNECTING: significa que la app ya sabe a dónde ir
 * y lo está reintentando sola, sin que el usuario tenga que tocar nada.
 */
enum class ConnectionStatus { DISCONNECTED, CONNECTING, RECONNECTING, CONNECTED }
enum class BlenderMode { OBJECT, EDIT }
enum class SelectionMode { VERTEX, EDGE, FACE }
/** Atajos de la página Edit; su adaptador wire vive en MainViewModel. */
enum class EditFooterAction { MAKE_EDGE_FACE, KNIFE, SEPARATE, SPLIT, NORMALS, NORMALS_OUTSIDE, NORMALS_INSIDE, NORMALS_FLIP }
enum class ActiveTool { SELECT, TWEAK, MOVE, ROTATE, SCALE, EXTRUDE, BEVEL, INSET, SUBDIVIDE, LOOP_CUT, BRIDGE_EDGE_LOOPS, KNIFE, BISECT }

/**
 * Operación de selección que aplican el tap, la caja y el círculo. Mayús/Ctrl/Alt
 * de la barra superior la fijan: TOGGLE alterna, ADD añade y REMOVE quita; el
 * nombre viaja tal cual al servidor (`mode` de `selection.*`).
 */
enum class SelectionOp { SET, ADD, REMOVE, TOGGLE }

/**
 * Herramienta de arrastre por forma. BOX/CIRCLE se arman desde la barra superior
 * (B/C); LINE la arma automáticamente Bisect (edit_toolbar) mientras está armado o
 * activo — no tiene botón propio, es el mismo mecanismo de "un dedo dibuja" que ya
 * usan B/C, reinterpretado como línea de corte en vez de selección.
 */
enum class ShapeTool { NONE, BOX, CIRCLE, LINE }

data class HiddenObject(val name: String, val type: String)
data class ObjectChoiceFilter(val type: String? = null, val excludeSelf: Boolean = false)
sealed interface ModifierDefault {
    data class Integer(val value: Int) : ModifierDefault
    data class Decimal(val value: Double) : ModifierDefault
    data class BooleanValue(val value: Boolean) : ModifierDefault
    data class Text(val value: String) : ModifierDefault
    data class Vector(val value: List<Double>) : ModifierDefault
    data object Null : ModifierDefault
}
data class ModifierParameterDescriptor(
    val name: String, val type: String, val default: ModifierDefault,
    val min: Double? = null, val max: Double? = null, val step: Double? = null,
    val values: List<String> = emptyList(), val objectFilter: ObjectChoiceFilter? = null,
)
data class ModifierTypeDescriptor(val type: String, val parameters: List<ModifierParameterDescriptor>)
data class ModifierState(
    val name: String, val type: String, val showViewport: Boolean = true,
    val showRender: Boolean = true, val parameters: Map<String, Any?> = emptyMap(),
)
data class ServerFeatures(
    val modifiers: Boolean = false, val visibility: Boolean = false,
    val transformApply: Boolean = false, val objectShading: Boolean = false,
    val loopCut: Boolean = false,
    val shading: Boolean = false, val localView: Boolean = false,
    /** `view.overlays`: el ojo puede apagar rejilla y overlays del viewport. */
    val overlays: Boolean = false,
    val selectionGrow: Boolean = false, val selectionShapes: Boolean = false,
    /** `selection.shortest_path`: Ctrl+toque real en Edit Mode. */
    val selectionShortestPath: Boolean = false,
    /** `selection.tweak`: seleccionar y mover en un único arrastre. */
    val selectionTweak: Boolean = false,
    /** Colocación del loop cut tocando la malla (`edit_tools.loop_cut.pick`). */
    val loopCutPick: Boolean = false,
    /** Mayús+toque acumula cortes y permite volver al anterior. */
    val loopCutMultiple: Boolean = false,
    /** Knife por segmentos de arrastre con candidato proyectado por el servidor. */
    val knifeDrag: Boolean = false,
    val fileBrowse: Boolean = false,
    val editSettings: Boolean = false,
    /** Catálogo contextual de Edit; vacío conserva por completo la interfaz legacy. */
    val editCatalog: EditCatalog = EditCatalog(),
    /** Barra de tools activas; vacío conserva el rail y `edit_catalog` legacy. */
    val editToolbar: EditToolbar = EditToolbar(),
)

data class EditSettings(
    val proportional: Boolean = false,
    val proportionalConnected: Boolean = false,
    val falloff: String = "SMOOTH",
    val radius: Double = 1.0,
    val autoMerge: Boolean = false,
    val mergeThreshold: Double = 0.001,
)

/** Contrato extensible del menú Edit. Las claves wire se mantienen opacas a la UI. */
data class EditCatalog(
    val groups: Map<SelectionMode, List<EditCatalogAction>> = emptyMap(),
) {
    val available: Boolean get() = groups.values.any { it.isNotEmpty() }
    fun actionsFor(mode: SelectionMode) = groups[mode].orEmpty()
}

data class EditCatalogAction(
    val id: String,
    val label: String,
    val enabled: Boolean = true,
    val execution: String = "DISCRETE",
    /** Comando publicado por el backend; ausente significa que no es ejecutable. */
    val command: String? = null,
    /** Payload fijo publicado por el backend; no se reconstruye en Android. */
    val payload: Map<String, Any?> = emptyMap(),
    /** Requisitos opacos para filtrar/diagnosticar sin asumir campos futuros. */
    val requirements: Map<String, Any?> = emptyMap(),
    val variants: List<EditCatalogVariant> = emptyList(),
    val parameters: List<EditCatalogParameter> = emptyList(),
)

data class EditCatalogVariant(val id: String, val label: String, val enabled: Boolean = true)
data class EditCatalogParameter(
    val id: String,
    val label: String,
    val type: String,
    val default: Any? = null,
    /** Valores del enum, si `type` es enum. */
    val values: List<String> = emptyList(),
    /** Variantes a las que se aplica; vacío = todas. */
    val appliesTo: List<String> = emptyList(),
)

/** Gestos continuos del protocolo. El nombre en minúsculas es el que viaja por el cable. */
enum class Gesture { ORBIT, PAN, ZOOM, ROLL, MOVE, ROTATE, SCALE }

/**
 * Fases de un gesto. El servidor agrupa los UPDATE y cierra un único paso de undo
 * al recibir END, así que un arrastre completo debe abrirse y cerrarse siempre.
 */
enum class GesturePhase { BEGIN, UPDATE, END, CANCEL }

/** Los tres ejes. El nombre viaja tal cual al servidor. */
enum class Axis { X, Y, Z }

/** Modo de la transformación modal. El nombre viaja tal cual. */
enum class TransformMode(val label: String) { MOVE("Mover"), ROTATE("Rotar"), SCALE("Escalar") }

/**
 * Incremento al que cuadra el snap. Se ofrece en las unidades en que se piensa
 * (milímetros, centímetros, metros), pero Blender trabaja en metros y es eso lo que
 * viaja: `step` ya va convertido.
 */
data class StepPreset(val label: String, val step: Double)

val MoveSteps = listOf(
    StepPreset("1 mm", 0.001),
    StepPreset("1 cm", 0.01),
    StepPreset("10 cm", 0.1),
    StepPreset("1 m", 1.0),
)

/** El servidor recibe el ángulo en grados en `transform.value`, y el paso en radianes. */
val RotateSteps = listOf(
    StepPreset("1°", Math.toRadians(1.0)),
    StepPreset("5°", Math.toRadians(5.0)),
    StepPreset("15°", Math.toRadians(15.0)),
    StepPreset("45°", Math.toRadians(45.0)),
)

// La etiqueta se lee en porcentaje (lo que piensa quien escala) pero por el cable
// viaja el factor, que es lo que usa el servidor.
val ScaleSteps = listOf(
    StepPreset("1%", 0.01),
    StepPreset("5%", 0.05),
    StepPreset("10%", 0.1),
    StepPreset("25%", 0.25),
)

fun stepsFor(mode: TransformMode) = when (mode) {
    TransformMode.MOVE -> MoveSteps
    TransformMode.ROTATE -> RotateSteps
    TransformMode.SCALE -> ScaleSteps
}

fun defaultStepIndex(mode: TransformMode): Int = when (mode) {
    TransformMode.MOVE -> 0   // 1 mm
    TransformMode.ROTATE -> 1 // 5°
    TransformMode.SCALE -> 1  // 5 %
}

fun stepInBlenderUnits(preset: StepPreset, mode: TransformMode, scaleLength: Double): Double =
    if (mode == TransformMode.MOVE) preset.step / scaleLength.coerceAtLeast(1e-12) else preset.step

/**
 * La transformación en curso, tal como la cuenta el servidor.
 *
 * Los valores llegan por el evento `transform.session` a 10 Hz: es el marcador que
 * se lee mientras se arrastra el dedo.
 */
data class TransformSession(
    val active: Boolean = false,
    val mode: TransformMode = TransformMode.MOVE,
    val axes: Set<Axis> = emptySet(),
    val snap: Boolean = false,
    val snapType: SnapType = SnapType.NONE,
    /** El elemento al que se está pegando ahora mismo, si el snap es geométrico. */
    val snapCandidate: SnapCandidate? = null,
    val step: Double = 0.01,
    val orientation: Orientation = Orientation.GLOBAL,
    val valueMode: ValueMode = ValueMode.RELATIVE,
    val proportional: Boolean = false,
    val proportionalRadius: Double = 1.0,
    val proportionalFalloff: String = "SMOOTH",
    /** Metros o factor, según el modo. En ROTATE no se usa: manda [angle]. */
    val values: List<Double> = listOf(0.0, 0.0, 0.0),
    /** Grados. */
    val angle: Double = 0.0,
) {
    /** La restricción en curso derivada de los ejes, para enseñarla en la barra. */
    val constraint: Constraint get() = Constraint.ofAxes(axes)
}

/** Familias del menú Add de Blender. Las de un solo elemento no abren submenú. */
enum class AddCategory(val label: String) {
    MESH("Malla"),
    CURVE("Curva"),
    SURFACE("Superficie"),
    METABALL("Metaball"),
    TEXT("Texto"),
    EMPTY("Vacío"),
    LIGHT("Luz"),
    CAMERA("Cámara"),
}

/**
 * Lo que se puede añadir. **El nombre del enum viaja tal cual** como `primitive` de
 * `object.add`, así que debe coincidir con las claves de `_add_catalog()` del backend;
 * `android_contract.py` lo comprueba.
 */
enum class AddObject(val label: String, val category: AddCategory) {
    PLANE("Plano", AddCategory.MESH),
    CUBE("Cubo", AddCategory.MESH),
    CIRCLE("Círculo", AddCategory.MESH),
    SPHERE("Esfera UV", AddCategory.MESH),
    ICO_SPHERE("Icoesfera", AddCategory.MESH),
    CYLINDER("Cilindro", AddCategory.MESH),
    CONE("Cono", AddCategory.MESH),
    TORUS("Toro", AddCategory.MESH),
    GRID("Rejilla", AddCategory.MESH),
    MONKEY("Suzanne", AddCategory.MESH),

    BEZIER_CURVE("Bézier", AddCategory.CURVE),
    BEZIER_CIRCLE("Círculo Bézier", AddCategory.CURVE),
    NURBS_CURVE("NURBS", AddCategory.CURVE),
    NURBS_CIRCLE("Círculo NURBS", AddCategory.CURVE),
    PATH("Trayectoria", AddCategory.CURVE),

    SURFACE_CURVE("Curva NURBS", AddCategory.SURFACE),
    SURFACE_CIRCLE("Círculo NURBS", AddCategory.SURFACE),
    SURFACE_PATCH("Superficie", AddCategory.SURFACE),
    SURFACE_CYLINDER("Cilindro", AddCategory.SURFACE),
    SURFACE_SPHERE("Esfera", AddCategory.SURFACE),
    SURFACE_TORUS("Toro", AddCategory.SURFACE),

    META_BALL("Bola", AddCategory.METABALL),
    META_CAPSULE("Cápsula", AddCategory.METABALL),
    META_PLANE("Plano", AddCategory.METABALL),
    META_ELLIPSOID("Elipsoide", AddCategory.METABALL),
    META_CUBE("Cubo", AddCategory.METABALL),

    TEXT("Texto", AddCategory.TEXT),

    EMPTY_PLAIN_AXES("Ejes", AddCategory.EMPTY),
    EMPTY_ARROWS("Flechas", AddCategory.EMPTY),
    EMPTY_SINGLE_ARROW("Flecha", AddCategory.EMPTY),
    EMPTY_CIRCLE("Círculo", AddCategory.EMPTY),
    EMPTY_CUBE("Cubo", AddCategory.EMPTY),
    EMPTY_SPHERE("Esfera", AddCategory.EMPTY),
    EMPTY_CONE("Cono", AddCategory.EMPTY),

    LIGHT_POINT("Punto", AddCategory.LIGHT),
    LIGHT_SUN("Sol", AddCategory.LIGHT),
    LIGHT_SPOT("Foco", AddCategory.LIGHT),
    LIGHT_AREA("Área", AddCategory.LIGHT),

    CAMERA("Cámara", AddCategory.CAMERA);

    companion object {
        fun of(category: AddCategory) = entries.filter { it.category == category }
    }
}

/** Los tres bloques del menú de cursor y origen, cada uno su submenú. */
enum class SnapGroup(val label: String) {
    CURSOR("Cursor 3D"),
    SELECTION("Snap selección"),
    ORIGIN("Establecer origen"),
}

/**
 * El menú Shift+S de Blender. [command] es el comando del protocolo.
 *
 * `objectOnly` marca las que exigen Object Mode: el servidor las rechaza en Edit y
 * es mejor enseñarlas en gris que dejar que fallen.
 */
enum class SnapAction(
    val label: String,
    val command: String,
    val group: SnapGroup,
    val objectOnly: Boolean = false,
) {
    CURSOR_TO_WORLD("Al origen del mundo", "snap.cursor_to_world", SnapGroup.CURSOR),
    CURSOR_TO_SELECTED("A la selección", "snap.cursor_to_selected", SnapGroup.CURSOR),
    CURSOR_TO_ACTIVE("Al objeto activo", "snap.cursor_to_active", SnapGroup.CURSOR),
    CURSOR_TO_GRID("A la rejilla", "snap.cursor_to_grid", SnapGroup.CURSOR),

    SELECTED_TO_CURSOR("Al cursor", "snap.selected_to_cursor", SnapGroup.SELECTION, objectOnly = true),
    SELECTED_TO_GRID("A la rejilla", "snap.selected_to_grid", SnapGroup.SELECTION, objectOnly = true),

    ORIGIN_TO_CURSOR("Al cursor 3D", "snap.origin_to_cursor", SnapGroup.ORIGIN, objectOnly = true),
    ORIGIN_TO_GEOMETRY("A la geometría", "snap.origin_to_geometry", SnapGroup.ORIGIN, objectOnly = true),
    ORIGIN_TO_MASS("Al centro de masas", "snap.origin_to_center_of_mass", SnapGroup.ORIGIN, objectOnly = true);

    companion object {
        fun of(group: SnapGroup) = entries.filter { it.group == group }
    }
}

/** El .blend abierto en el PC. */
data class FileInfo(
    val name: String = "Sin título",
    val path: String = "",
    /** false = nunca se ha guardado, así que "Guardar" tiene que pedir nombre. */
    val saved: Boolean = false,
    val dirty: Boolean = false,
)

enum class RemoteFileType { DIRECTORY, BLEND }

data class RemoteFileEntry(
    val name: String,
    val path: String,
    val type: RemoteFileType,
)

data class RemoteLocation(
    val id: String,
    val label: String,
    val path: String,
)

data class RemoteBreadcrumb(val name: String, val path: String)

/** Estado del explorador del disco del PC. Los paths son opacos para Android. */
data class RemoteFiles(
    val path: String = "",
    val parent: String? = null,
    val defaultFolder: String = "",
    val breadcrumbs: List<RemoteBreadcrumb> = emptyList(),
    val entries: List<RemoteFileEntry> = emptyList(),
    val locations: List<RemoteLocation> = emptyList(),
    val loading: Boolean = false,
)

/** Punto en coordenadas del viewport remoto: 0..1, origen arriba-izquierda. */
data class ViewportPoint(val u: Float, val v: Float)

/**
 * Manipulador proyectado por el servidor.
 *
 * Los gizmos nativos de Blender no salen en el vídeo (`draw_view3d` no dibuja los
 * overlays de la región), así que el servidor solo manda dónde cae el origen y la
 * punta de cada eje, y la app los dibuja a un tamaño usable con el dedo.
 */
data class Gizmo(
    val visible: Boolean = false,
    val objectName: String? = null,
    val origin: ViewportPoint? = null,
    val axes: Map<Axis, ViewportPoint> = emptyMap(),
)

/** Transformación del objeto activo, para el panel numérico. */
data class Transform(
    val location: List<Float> = listOf(0f, 0f, 0f),
    val rotationEuler: List<Float> = listOf(0f, 0f, 0f),
    val scale: List<Float> = listOf(1f, 1f, 1f),
)

data class BlenderState(
    val mode: BlenderMode = BlenderMode.OBJECT,
    val activeObject: String? = null,
    val selectedObjects: List<String> = emptyList(),
    val selectionMode: SelectionMode = SelectionMode.VERTEX,
    val gizmo: Gizmo = Gizmo(),
    val transform: Transform? = null,
    val context: SceneContext = SceneContext(),
    val view: ViewState = ViewState(),
    val activeObjectType: String? = null,
    /** El objeto activo está sombreado suave: rotula el interruptor Plano/Suave. */
    val activeShadeSmooth: Boolean = false,
    val objects: List<Pair<String, String>> = emptyList(),
    val hiddenObjects: List<HiddenObject> = emptyList(),
    val modifiers: List<ModifierState> = emptyList(),
    val modifierOptions: List<ModifierTypeDescriptor> = emptyList(),
    val features: ServerFeatures = ServerFeatures(),
    val editSettings: EditSettings = EditSettings(),
    /** Metros físicos representados por una Blender Unit. */
    val unitScaleLength: Double = 1.0,
)

data class InputDebug(
    val pointerCount: Int = 0,
    val tool: String = "Finger",
    val pressure: Float = 0f,
    val tilt: Float = 0f,
    val orientation: Float = 0f,
    val buttonState: Int = 0,
    val x: Float = 0f,
    val y: Float = 0f,
)

data class AppUiState(
    val connection: ConnectionStatus = ConnectionStatus.DISCONNECTED,
    /** Reintentos encadenados sin éxito. 0 mientras la conexión aguanta. */
    val retryAttempt: Int = 0,
    val blender: BlenderState = BlenderState(),
    val activeTool: ActiveTool = ActiveTool.SELECT,
    val controlsVisible: Boolean = true,
    val debugVisible: Boolean = false,
    val error: String? = null,
    /** Confirmación efímera de una acción cuyo efecto no se ve en el viewport. */
    val notice: String? = null,
    val file: FileInfo = FileInfo(),
    /** Preferencias de la barra de transformación; sobreviven a cerrar la sesión. */
    val snapType: SnapType = SnapType.NONE,
    /** Último paso elegido para las herramientas paramétricas con snap escalar. */
    val snapStep: Double = 0.1,
    val stepIndex: Map<TransformMode, Int> = emptyMap(),
    /** Restricción elegida para la próxima transformación. */
    val constraint: Constraint = Constraint.FREE,
    val orientation: Orientation = Orientation.GLOBAL,
    val valueMode: ValueMode = ValueMode.RELATIVE,
    /** Operación acumulativa de Mayús o sustractiva de Alt. */
    val selectionOp: SelectionOp = SelectionOp.SET,
    /** Ctrl armado para que el siguiente toque seleccione el camino más corto. */
    val shortestPathActive: Boolean = false,
    /** Herramienta de forma (B/C) armada en la barra superior. */
    val shapeTool: ShapeTool = ShapeTool.NONE,
    /** `view.local` activo: aislar la selección (el `/` del footer de vistas). */
    val localViewActive: Boolean = false,
    /** Loop Cut armado esperando el toque que coloca el corte. */
    val loopCutAwaitingTap: Boolean = false,
    /** Última variante usada por familia de `edit_toolbar` (id de familia -> id de variante). */
    val toolbarVariant: Map<String, String> = emptyMap(),
    /** Variante discreta recordada por la familia Duplicar del rail (Object Mode). */
    val duplicateLinked: Boolean = false,
)

/**
 * ¿Hay una bandeja horizontal inferior ocupando el borde de abajo?
 *
 * Es la señal que eleva el teclado de vistas: transformación modal activa, herramienta
 * paramétrica activa o Loop Cut esperando el toque que coloca el corte. Extraído a una
 * función pura para poder probar el layout sin montar la interfaz.
 */
fun bottomTrayVisible(
    sessionActive: Boolean,
    toolSessionActive: Boolean,
    activeTool: ActiveTool,
    loopCutAwaitingTap: Boolean,
    /** Bisect armado (edit_toolbar) esperando el arrastre de línea que activa la sesión. */
    toolSessionArmed: Boolean = false,
): Boolean = (sessionActive && activeTool != ActiveTool.TWEAK) || toolSessionActive ||
    (activeTool == ActiveTool.LOOP_CUT && !toolSessionActive && loopCutAwaitingTap) ||
    (activeTool == ActiveTool.BISECT && !toolSessionActive && toolSessionArmed)
