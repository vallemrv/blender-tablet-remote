package com.blendertablet.remote.network

import com.blendertablet.remote.model.ActiveTool
import com.blendertablet.remote.model.Axis
import com.blendertablet.remote.model.BlenderMode
import com.blendertablet.remote.model.BlenderState
import com.blendertablet.remote.model.Constraint
import com.blendertablet.remote.model.EditTool
import com.blendertablet.remote.model.Orientation
import com.blendertablet.remote.model.Projection
import com.blendertablet.remote.model.SceneContext
import com.blendertablet.remote.model.SelectionCounts
import com.blendertablet.remote.model.SelectionMode
import com.blendertablet.remote.model.SnapCandidate
import com.blendertablet.remote.model.SnapType
import com.blendertablet.remote.model.ToolSession
import com.blendertablet.remote.model.Transform
import com.blendertablet.remote.model.TransformMode
import com.blendertablet.remote.model.TransformSession
import com.blendertablet.remote.model.ValueMode
import com.blendertablet.remote.model.ViewState
import org.json.JSONArray
import org.json.JSONObject
import com.blendertablet.remote.model.*

/**
 * Traduce el JSON del servidor a los modelos de la app.
 *
 * Vive fuera del cliente WebSocket para separar la decodificación del transporte y
 * centralizar la tolerancia a cambios del contrato.
 *
 * Todo se lee de forma tolerante: un campo que falte o traiga un valor desconocido cae
 * en el valor por defecto en vez de romper la conexión. El servidor puede ser más nuevo
 * que la app.
 */
object StateParser {

    fun unitScaleLength(json: JSONObject?): Double =
        json?.optJSONObject("units")?.optDouble("scale_length", 1.0)
            ?.takeIf { it.isFinite() && it > 0.0 } ?: 1.0

    /** `scene_scale` repite la escala real para mantenerla al cargar otro `.blend`. */
    fun sceneScaleLength(json: JSONObject?, fallback: Double): Double =
        json?.optDouble("scale_length", fallback)
            ?.takeIf { it.isFinite() && it > 0.0 } ?: fallback

    /**
     * Escala de trabajo. Un servidor que no la publica se comporta como hasta ahora,
     * así que el default equivale al preset medio y la UI simplemente no la ofrece.
     */
    fun sceneScale(json: JSONObject?, fallback: SceneScale = SceneScale()): SceneScale {
        if (json == null) return fallback
        return SceneScale(
            id = json.optString("id", fallback.id).ifBlank { fallback.id },
            label = json.optString("label", fallback.label).ifBlank { fallback.label },
            hint = json.optString("hint", fallback.hint),
            lengthUnit = LengthUnit.fromWire(json.optString("length_unit")) ?: fallback.lengthUnit,
            clipStart = json.optDouble("clip_start", fallback.clipStart),
            clipEnd = json.optDouble("clip_end", fallback.clipEnd),
            snapStep = json.optDouble("snap_step", fallback.snapStep),
            moveStep = json.optDouble("move_step", fallback.moveStep),
            primitiveSize = json.optDouble("primitive_size", fallback.primitiveSize),
            proportionalRadius = json.optDouble("proportional_radius", fallback.proportionalRadius),
            proportionalRadiusStep = json.optDouble(
                "proportional_radius_step", fallback.proportionalRadiusStep),
        )
    }

    /** Catálogo de presets de `scene.scale`, en el orden que manda el servidor. */
    fun sceneScalePresets(json: JSONObject?): List<SceneScale> {
        val array = json?.optJSONArray("presets") ?: return emptyList()
        return (0 until array.length()).mapNotNull { array.optJSONObject(it) }
            .map { sceneScale(it) }
    }

    fun state(json: JSONObject): BlenderState {
        val selected = json.optJSONArray("selected_objects") ?: JSONArray()
        return BlenderState(
            mode = if (json.optString("mode").startsWith("EDIT")) BlenderMode.EDIT else BlenderMode.OBJECT,
            activeObject = json.optString("active_object").takeIf { it.isNotBlank() && it != "null" },
            selectedObjects = List(selected.length()) { selected.optString(it) },
            selectionMode = enum(json.optString("selection_mode"), SelectionMode.VERTEX),
            transform = json.optJSONObject("active")?.let(::transform),
            context = context(json),
            view = view(json.optJSONObject("view"), json.optString("shading")),
            activeObjectType = json.optJSONObject("active")?.optString("type")?.takeIf(String::isNotBlank),
            activeShadeSmooth = json.optJSONObject("active")
                ?.optJSONObject("mesh")?.optBoolean("shade_smooth") == true,
            objects = objects(json.optJSONArray("objects")),
            hiddenObjects = hiddenObjects(json.optJSONArray("hidden_objects")),
            modifiers = modifiers(json.optJSONObject("active")?.optJSONArray("modifiers")),
            editSettings = editSettings(json.optJSONObject("edit_settings")),
            sceneScale = sceneScale(json.optJSONObject("scene_scale")),
        )
    }

    fun editSettings(json: JSONObject?): EditSettings = EditSettings(
        proportional = json?.optBoolean("proportional", false) ?: false,
        proportionalConnected = json?.optBoolean("proportional_connected", false) ?: false,
        falloff = json?.optString("falloff", "SMOOTH") ?: "SMOOTH",
        radius = json?.optDouble("radius", 1.0) ?: 1.0,
        autoMerge = json?.optBoolean("auto_merge", false) ?: false,
        mergeThreshold = json?.optDouble("merge_threshold", 0.001) ?: 0.001,
    )

    fun hiddenObjects(array: JSONArray?): List<HiddenObject> = if (array == null) emptyList() else
        (0 until array.length()).mapNotNull { array.optJSONObject(it) }.map {
            HiddenObject(it.optString("name"), it.optString("type"))
        }

    fun modifiers(array: JSONArray?): List<ModifierState> = if (array == null) emptyList() else
        (0 until array.length()).mapNotNull { array.optJSONObject(it) }.map { item ->
            ModifierState(item.optString("name"), item.optString("type"),
                item.optBoolean("show_viewport", true), item.optBoolean("show_render", true),
                jsonMap(item.optJSONObject("parameters")))
        }

    fun modifierOptions(json: JSONObject?): List<ModifierTypeDescriptor> {
        val types = json?.optJSONObject("types") ?: return emptyList()
        return types.keys().asSequence().map { type ->
            val params = types.optJSONObject(type)?.optJSONObject("parameters") ?: JSONObject()
            ModifierTypeDescriptor(type, params.keys().asSequence().map { name ->
                val p = params.getJSONObject(name)
                ModifierParameterDescriptor(name, p.optString("type"), defaultValue(p),
                    p.optDouble("min").takeUnless { p.isNull("min") || !p.has("min") },
                    p.optDouble("max").takeUnless { p.isNull("max") || !p.has("max") },
                    p.optDouble("step").takeUnless { p.isNull("step") || !p.has("step") },
                    strings(p.optJSONArray("values")), p.optJSONObject("object_filter")?.let {
                        ObjectChoiceFilter(it.optString("type").takeIf(String::isNotBlank), it.optBoolean("exclude_self"))
                    })
            }.toList())
        }.toList()
    }

    fun features(json: JSONObject?): ServerFeatures {
        val f = json?.optJSONObject("features") ?: return ServerFeatures()
        val view = f.optJSONObject("view")
        val selection = f.optJSONObject("selection")
        return ServerFeatures(
            f.optJSONObject("history")?.optBoolean("repeat_last") == true,
            f.has("modifiers"), f.has("visibility"), f.has("transform_apply"),
            f.has("object_shading"),
            f.optJSONObject("context") != null,
            view?.has("shading") == true,
            view?.optBoolean("local_view", false) == true,
            view?.optBoolean("overlays", false) == true,
            selection?.optBoolean("grow", false) == true,
            selection?.has("shapes") == true,
            selection?.optBoolean("shortest_path", false) == true,
            selection?.optJSONObject("tweak") != null,
            f.optJSONObject("edit_tools")?.optJSONObject("loop_cut")
                ?.optBoolean("pick", false) == true,
            f.optJSONObject("edit_tools")?.optJSONObject("loop_cut")
                ?.optBoolean("multiple", false) == true,
            f.optJSONObject("edit_tools")?.optJSONObject("knife")
                ?.optBoolean("drag", false) == true,
            f.optJSONObject("files")?.optBoolean("browse", false) == true,
            f.optJSONObject("edit_settings") != null,
            editCatalog(f.optJSONObject("edit_catalog")),
            editToolbar(f.optJSONObject("edit_toolbar")),
            tweakMotions(selection?.optJSONObject("tweak")),
            tweakSnapTypes(selection?.optJSONObject("tweak")),
            f.optJSONObject("scene_scale") != null,
        )
    }

    /**
     * Modos de Tweak anunciados. Un servidor que no los publica sigue admitiendo el
     * arrastre libre, así que ese es el mínimo; los nombres que esta versión no conoce
     * se ignoran en vez de romper el resto de capabilities.
     */
    fun tweakMotions(tweak: JSONObject?): List<TweakMotion> {
        val array = tweak?.optJSONArray("motion") ?: return listOf(TweakMotion.FREE)
        val parsed = (0 until array.length()).mapNotNull { index ->
            runCatching { TweakMotion.valueOf(array.optString(index).uppercase()) }.getOrNull()
        }
        return parsed.ifEmpty { listOf(TweakMotion.FREE) }
    }

    /** Destinos de snap del Tweak. Sin anuncio no se ofrece ninguno. */
    fun tweakSnapTypes(tweak: JSONObject?): List<SnapType> {
        val array = tweak?.optJSONArray("snap_types") ?: return emptyList()
        return (0 until array.length()).mapNotNull { index ->
            runCatching { SnapType.valueOf(array.optString(index).uppercase()) }.getOrNull()
        }
    }

    /**
     * Lee la barra de tools activas sin asumir que el servidor conoce exactamente
     * esta versión: familias, variantes y parámetros desconocidos se ignoran en vez
     * de impedir que la tablet use el resto del servidor (mismo criterio que
     * [editCatalog]).
     */
    fun editToolbar(json: JSONObject?): EditToolbar {
        val array = json?.optJSONArray("families") ?: return EditToolbar()
        val families = (0 until array.length()).mapNotNull { array.optJSONObject(it) }.mapNotNull { family ->
            val id = family.optString("id")
            if (id.isBlank()) return@mapNotNull null
            EditToolbarFamily(
                id = id,
                label = family.optString("label").ifBlank { id },
                defaultVariant = family.optString("default_variant"),
                command = family.optString("command").takeIf(String::isNotBlank),
                payload = jsonMap(family.optJSONObject("payload")),
                input = family.optString("input", "PARAMETRIC"),
                requirements = jsonMap(family.optJSONObject("requirements")),
                variants = editToolbarVariants(family.optJSONArray("variants")),
                parameters = editParameters(family.optJSONArray("parameters")),
            )
        }
        return EditToolbar(families)
    }

    private fun editToolbarVariants(array: JSONArray?): List<EditToolbarVariant> =
        if (array == null) emptyList() else (0 until array.length()).mapNotNull { array.optJSONObject(it) }
            .mapNotNull { item ->
                item.optString("id").takeIf(String::isNotBlank)?.let { id ->
                    EditToolbarVariant(
                        id = id,
                        label = item.optString("label").ifBlank { id },
                        enabled = item.optBoolean("enabled", true),
                        input = item.optString("input").takeIf(String::isNotBlank),
                        payload = jsonMap(item.optJSONObject("payload")),
                        requirements = jsonMap(item.optJSONObject("requirements")),
                        parameters = editParameters(item.optJSONArray("parameters")),
                    )
                }
            }

    /**
     * Lee el catálogo sin asumir que el servidor conoce exactamente esta versión.
     * Grupos, acciones, variantes y parámetros desconocidos se ignoran en vez de
     * impedir que la tablet use el resto del servidor.
     */
    fun editCatalog(json: JSONObject?): EditCatalog {
        val groups = json?.optJSONObject("groups") ?: return EditCatalog()
        val parsed = SelectionMode.entries.associateWith { mode ->
            val actions = groups.optJSONArray(mode.name) ?: return@associateWith emptyList()
            (0 until actions.length()).mapNotNull { actions.optJSONObject(it) }.mapNotNull { action ->
                val id = action.optString("id")
                if (id.isBlank()) return@mapNotNull null
                EditCatalogAction(
                    id = id,
                    label = action.optString("label").ifBlank { id },
                    enabled = action.optBoolean("enabled", true),
                    execution = action.optString("execution", "DISCRETE"),
                    command = action.optString("command").takeIf(String::isNotBlank),
                    payload = jsonMap(action.optJSONObject("payload")),
                    requirements = jsonMap(action.optJSONObject("requirements")),
                    variants = editVariants(action.optJSONArray("variants")),
                    parameters = editParameters(action.optJSONArray("parameters")),
                )
            }
        }.filterValues { it.isNotEmpty() }
        return EditCatalog(parsed)
    }

    private fun editVariants(array: JSONArray?): List<EditCatalogVariant> =
        if (array == null) emptyList() else (0 until array.length()).mapNotNull { array.optJSONObject(it) }
            .mapNotNull { item -> item.optString("id").takeIf(String::isNotBlank)?.let { id ->
                EditCatalogVariant(id, item.optString("label").ifBlank { id }, item.optBoolean("enabled", true))
            } }

    private fun editParameters(array: JSONArray?): List<EditCatalogParameter> =
        if (array == null) emptyList() else (0 until array.length()).mapNotNull { array.optJSONObject(it) }
            .mapNotNull { item -> item.optString("id").takeIf(String::isNotBlank)?.let { id ->
                EditCatalogParameter(
                    id, item.optString("label").ifBlank { id }, item.optString("type"),
                    if (item.has("default") && !item.isNull("default")) item.get("default") else null,
                    strings(item.optJSONArray("values")),
                    strings(item.optJSONArray("applies_to")),
                )
            } }

    private fun defaultValue(p: JSONObject): ModifierDefault {
        if (!p.has("default") || p.isNull("default")) return ModifierDefault.Null
        return when (p.optString("type")) {
            "int" -> ModifierDefault.Integer(p.optInt("default"))
            "float" -> ModifierDefault.Decimal(p.optDouble("default"))
            "bool" -> ModifierDefault.BooleanValue(p.optBoolean("default"))
            "float3" -> ModifierDefault.Vector(doubles(p.optJSONArray("default")))
            else -> ModifierDefault.Text(p.optString("default"))
        }
    }
    /** Lista de objetos de la escena (nombre a tipo), para el picker de operando. */
    fun objects(a: JSONArray?): List<Pair<String, String>> =
        if (a == null) emptyList() else (0 until a.length()).mapNotNull { a.optJSONObject(it) }
            .map { it.optString("name") to it.optString("type") }
    private fun strings(a: JSONArray?): List<String> = if (a == null) emptyList() else (0 until a.length()).map { a.optString(it) }
    private fun doubles(a: JSONArray?): List<Double> = if (a == null) emptyList() else (0 until a.length()).map { a.optDouble(it) }
    private fun jsonMap(o: JSONObject?): Map<String, Any?> = if (o == null) emptyMap() else o.keys().asSequence().associateWith { k -> if (o.isNull(k)) null else o.get(k) }

    /** El contexto canónico (conteos y opciones válidas) viene mezclado en el estado. */
    fun context(json: JSONObject): SceneContext {
        val counts = json.optJSONObject("selection_counts") ?: JSONObject()
        return SceneContext(
            selectionCounts = SelectionCounts(
                objects = counts.optInt("objects", 0),
                verts = counts.optInt("verts", 0),
                edges = counts.optInt("edges", 0),
                faces = counts.optInt("faces", 0),
            ),
            availableTools = enums(json.optJSONArray("available_tools"), ActiveTool.entries),
            availableConstraints = enums(json.optJSONArray("available_constraints"), Constraint.entries),
            availableOrientations = enums(json.optJSONArray("available_orientations"), Orientation.entries),
            availableSnapTypes = enums(json.optJSONArray("available_snap_types"), SnapType.entries),
            selectionCenter = floats(json.optJSONArray("selection_center")),
            selectionNormal = floats(json.optJSONArray("selection_normal")),
        )
    }

    fun session(json: JSONObject?): TransformSession {
        if (json == null || !json.optBoolean("active")) return TransformSession()
        val axes = json.optJSONArray("axes") ?: JSONArray()
        val values = json.optJSONArray("values") ?: JSONArray()
        val baseDimensions = json.optJSONArray("base_dimensions") ?: JSONArray()
        val dimensions = json.optJSONArray("dimensions") ?: JSONArray()
        return TransformSession(
            active = true,
            sessionId = json.optString("session_id").takeIf { it.isNotBlank() },
            mode = enum(json.optString("mode"), TransformMode.MOVE),
            axes = enums(axes, Axis.entries).toSet(),
            snap = json.optBoolean("snap"),
            snapType = enum(json.optString("snap_type"), SnapType.NONE),
            snapCandidate = candidate(json.optJSONObject("snap_candidate")),
            referenceCandidate = candidate(json.optJSONObject("reference_candidate")),
            referenceLocked = json.optBoolean("reference_locked", false),
            referenceRole = json.optString("reference_role").takeIf { it.isNotBlank() },
            centerLocked = json.optBoolean("center_locked", false),
            sourceLocked = json.optBoolean("source_locked", false),
            referencePosition = floats(json.optJSONArray("reference_position")),
            referenceDistance = json.optDouble("reference_distance").takeIf { !it.isNaN() },
            center = optionalFloats(json.optJSONArray("center")),
            source = optionalFloats(json.optJSONArray("source")),
            target = optionalFloats(json.optJSONArray("target")),
            baseDimensions = List(3) { baseDimensions.optDouble(it, 0.0) },
            dimensions = List(3) { dimensions.optDouble(it, 0.0) },
            step = json.optDouble("step", 0.01),
            orientation = enum(json.optString("orientation"), Orientation.GLOBAL),
            valueMode = enum(json.optString("value_mode"), ValueMode.RELATIVE),
            proportional = json.optBoolean("proportional", false),
            proportionalRadius = json.optDouble("proportional_radius", 1.0),
            proportionalFalloff = json.optString("proportional_falloff", "SMOOTH"),
            proportionalCircle = json.optJSONObject("proportional_circle")?.let { circle ->
                com.blendertablet.remote.model.ProportionalCircle(
                    optionalFloats(circle.optJSONArray("center")),
                    circle.optDouble("radius", 0.0).toFloat(),
                )
            },
            values = List(3) { values.optDouble(it, 0.0) },
            angle = json.optDouble("angle", 0.0),
        )
    }

    /**
     * El candidato geométrico bajo el dedo. `id` es del tipo `Cube:VERTEX:3` y es lo
     * único que distingue dos candidatos del mismo tipo.
     */
    fun candidate(json: JSONObject?): SnapCandidate? {
        if (json == null || !json.optBoolean("hit", true)) return null
        val type = SnapType.entries.firstOrNull { it.name == json.optString("snap_type") } ?: return null
        return SnapCandidate(
            type = type,
            id = json.optString("id"),
            objectName = json.optString("object").takeIf { it.isNotBlank() && it != "null" },
            position = doubles(json.optJSONArray("position")),
            screen = doubles(json.optJSONArray("screen")),
            distance = json.optDouble("distance").takeUnless { it.isNaN() },
        )
    }

    fun toolSession(json: JSONObject?): ToolSession {
        if (json == null) return ToolSession()
        val active = json.optBoolean("active")
        val armed = json.optBoolean("armed")
        if (!active && !armed) return ToolSession()
        val tool = EditTool.fromWire(json.optString("tool")) ?: return ToolSession()
        val params = json.optJSONObject("parameters") ?: JSONObject()
        // Los valores llegan tipados (números, bools del modal, falloff string) y
        // se conservan así: la bandeja de Loop Cut los lee con la forma original.
        // org.json entrega Integer/Long/Double (boxed), por eso `is Number`.
        val values = mutableMapOf<String, Any?>()
        for (key in params.keys()) {
            values[key] = when (val raw = params.get(key)) {
                is Boolean -> raw
                is Number -> raw.toDouble()
                is String -> raw
                else -> null
            }
        }
        val pointsArray = json.optJSONArray("points")
        val points = if (pointsArray == null) emptyList() else (0 until pointsArray.length()).mapNotNull { index ->
            pointsArray.optJSONArray(index)?.let { point ->
                List(3) { i -> point.optDouble(i, 0.0) }
            }
        }
        val line = json.optJSONObject("line")?.let(::dragLine)
        val projectedArray = json.optJSONArray("projected_points")
        val projected = if (projectedArray == null) emptyList() else
            (0 until projectedArray.length()).mapNotNull { index ->
                projectedArray.optJSONArray(index)?.let { point -> List(2) { i -> point.optDouble(i, 0.0) } }
            }
        fun pointGroups(key: String, dimensions: Int): List<List<List<Double>>> {
            val groups = json.optJSONArray(key) ?: return emptyList()
            return (0 until groups.length()).mapNotNull { groupIndex ->
                groups.optJSONArray(groupIndex)?.let { group ->
                    (0 until group.length()).mapNotNull { pointIndex ->
                        group.optJSONArray(pointIndex)?.let { point ->
                            List(dimensions) { i -> point.optDouble(i, 0.0) }
                        }
                    }
                }
            }
        }
        return ToolSession(
            active = active, armed = armed, tool = tool, parameters = values,
            points = points, strokes = pointGroups("strokes", 3),
            projectedPoints = projected, projectedStrokes = pointGroups("projected_strokes", 2),
            closed = json.optBoolean("closed"), line = line,
            snapType = enum(json.optString("snap_type", params.optString("snap_type")), SnapType.NONE),
            snapStep = json.optDouble("snap_step", params.optDouble("snap_step", 0.1)),
            snapCandidate = candidate(json.optJSONObject("snap_candidate")),
            loopCount = json.optInt("loop_count", if (active && tool == EditTool.LOOP_CUT) 1 else 0),
        )
    }

    /** Bisect: línea de arrastre en `u`/`v` normalizados, tal como la fijó el servidor. */
    private fun dragLine(json: JSONObject): DragLine? {
        val start = json.optJSONArray("start") ?: return null
        val end = json.optJSONArray("end") ?: return null
        return DragLine(List(2) { start.optDouble(it, 0.0) }, List(2) { end.optDouble(it, 0.0) })
    }

    /** `mesh.loop_probe`: dónde caería el corte si se confirma el toque. */
    fun loopProbe(json: JSONObject?): LoopProbe {
        if (json == null) return LoopProbe()
        return LoopProbe(
            hit = json.optBoolean("hit"),
            edge = json.optInt("edge", -1),
            factor = json.optDouble("factor", 0.0),
            ring = json.optInt("ring", 0),
        )
    }

    /** `file.browse`: listado del explorador del disco del PC. Paths opacos. */
    fun fileBrowse(json: JSONObject?): RemoteFiles {
        if (json == null) return RemoteFiles()
        return RemoteFiles(
            path = json.optString("path"),
            parent = json.optString("parent").takeIf { it.isNotBlank() && it != "null" },
            defaultFolder = json.optString("default_folder"),
            breadcrumbs = breadcrumbs(json.optJSONArray("breadcrumbs")),
            entries = fileEntries(json.optJSONArray("entries")),
        )
    }

    /** `file.locations`: lugares navegables + carpeta por defecto. */
    fun fileLocations(json: JSONObject?): RemoteFiles {
        if (json == null) return RemoteFiles()
        return RemoteFiles(
            defaultFolder = json.optString("default_folder"),
            locations = locations(json.optJSONArray("locations")),
        )
    }

    /** Un tipo de entrada que la app no reconoce se descarta: el servidor puede ser más nuevo. */
    fun fileEntries(array: JSONArray?): List<RemoteFileEntry> =
        if (array == null) emptyList() else (0 until array.length()).mapNotNull { index ->
            array.optJSONObject(index)?.let { item ->
                val type = runCatching { RemoteFileType.valueOf(item.optString("type")) }.getOrNull()
                    ?: return@let null
                RemoteFileEntry(item.optString("name"), item.optString("path"), type)
            }
        }

    private fun locations(array: JSONArray?): List<RemoteLocation> =
        if (array == null) emptyList() else (0 until array.length()).mapNotNull { index ->
            array.optJSONObject(index)?.let {
                RemoteLocation(it.optString("id"), it.optString("label"), it.optString("path"))
            }
        }

    private fun breadcrumbs(array: JSONArray?): List<RemoteBreadcrumb> =
        if (array == null) emptyList() else (0 until array.length()).mapNotNull { index ->
            array.optJSONObject(index)?.let {
                RemoteBreadcrumb(it.optString("name"), it.optString("path"))
            }
        }

    fun view(json: JSONObject?, shadingWire: String? = null): ViewState {
        val shading = enum(shadingWire, Shading.SOLID)
        if (json == null) return ViewState(shading = shading)
        return ViewState(
            perspective = enum(json.optString("perspective"), Projection.PERSP),
            axisView = json.optString("axis_view").takeIf { it.isNotBlank() && it != "null" },
            shading = shading,
        )
    }

    fun transform(json: JSONObject): Transform = Transform(
        location = floats(json.optJSONArray("location"), 0f),
        rotationEuler = floats(json.optJSONArray("rotation_euler"), 0f),
        scale = floats(json.optJSONArray("scale"), 1f),
    )

    /** Tres componentes siempre: un vector a medias descuadraría el panel numérico. */
    private fun floats(array: JSONArray?, fallback: Float = 0f): List<Float> =
        List(3) { array?.optDouble(it, fallback.toDouble())?.toFloat() ?: fallback }

    private fun optionalFloats(array: JSONArray?): List<Float> =
        if (array == null) emptyList() else floats(array)

    private inline fun <reified T : Enum<T>> enum(name: String?, fallback: T): T =
        T::class.java.enumConstants?.firstOrNull { it.name == name } ?: fallback

    /** Los valores que la app no reconoce se descartan: el servidor puede ser más nuevo. */
    private fun <T : Enum<T>> enums(array: JSONArray?, options: List<T>): List<T> {
        if (array == null) return emptyList()
        return (0 until array.length()).mapNotNull { index ->
            val name = array.optString(index)
            options.firstOrNull { it.name == name }
        }
    }
}
