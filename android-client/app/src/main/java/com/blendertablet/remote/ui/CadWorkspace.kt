package com.blendertablet.remote.ui

import androidx.compose.foundation.horizontalScroll
import androidx.compose.ui.draw.clip
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.clickable
import androidx.compose.foundation.border
import androidx.compose.foundation.background
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.AccountTree
import androidx.compose.material.icons.filled.CenterFocusStrong
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Layers
import androidx.compose.material.icons.automirrored.filled.RotateRight
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.North
import androidx.compose.material.icons.filled.Straighten
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.blendertablet.remote.MainViewModel
import com.blendertablet.remote.model.*
import java.util.Locale

/** Sketch geometry and constraints own their rails; all input still uses InputSurface. */
@Composable
fun BoxScope.CadWorkspace(state: AppUiState, vm: MainViewModel, stackOpen: Boolean, onStackOpen: (Boolean) -> Unit,
                          stackBottom: Dp, onTrayHeight: (Int) -> Unit) {
    val cad = state.blender.cad
    val capabilities = state.blender.features.cad
    val connected = state.connection == ConnectionStatus.CONNECTED
    var constraintsVisible by rememberSaveable { mutableStateOf(false) }
    var constraintsSelectionOnly by rememberSaveable { mutableStateOf(true) }
    var showDiameter by rememberSaveable { mutableStateOf(false) }
    var offsetSource by remember(cad.documentId, cad.activeSketchId) { mutableStateOf<CadEntity?>(null) }
    var offsetSide by remember { mutableStateOf("OUTWARD") }
    var mirrorSource by remember(cad.documentId, cad.activeSketchId) { mutableStateOf<CadFeature?>(null) }
    var mirrorPlane by remember { mutableStateOf("XZ") }
    var renamingSketch by remember(cad.documentId) { mutableStateOf<CadSketch?>(null) }
    val historyScroll = rememberScrollState()
    var unit by remember(state.blender.sceneScale.lengthUnit) { mutableStateOf(state.blender.sceneScale.lengthUnit) }
    var pendingDimension by remember(cad.activeSketchId, cad.selection) { mutableStateOf<String?>(null) }
    // Solevado: the first profile/sketch waits for a second selection from another sketch.
    var loftFrom by remember(cad.activeSketchId) { mutableStateOf<Pair<String, String>?>(null) }
    LaunchedEffect(cad.selectionKind, cad.selectionId) {
        val from = loftFrom ?: return@LaunchedEffect
        val kind = cad.selectionKind; val id = cad.selectionId
        if (kind !in listOf("PROFILE", "SKETCH") || id == null || (kind to id) == from) return@LaunchedEffect
        loftFrom = null
        vm.cadCommand("cad.loft.create", mapOf(
            (if (from.first == "SKETCH") "from_sketch_id" else "from_profile_id") to from.second,
            (if (kind == "SKETCH") "to_sketch_id" else "to_profile_id") to id))
    }
    var editingConstraint by remember(cad.activeSketchId) { mutableStateOf<CadConstraint?>(null) }
    LaunchedEffect(cad.selectionKind, cad.selectionId, cad.revision) {
        editingConstraint = cad.selectedConstraint
        if (editingConstraint != null) pendingDimension = null
    }
    // Rollback bar position over the full stack; body filtering keeps the order.
    val barPos = cad.rollbackId?.let { id -> cad.history.indexOfFirst { it.id == id } }?.takeIf { it >= 0 }
    fun behindBar(nodeId: String) = barPos != null && cad.history.indexOfFirst { it.id == nodeId } > barPos
    var cutTarget by remember(cad.documentId) { mutableStateOf<String?>(null) }
    val targets = cad.features.filter { it.enabled && !behindBar(it.id) }.groupBy { it.bodyId }.values.map { body ->
        body.maxBy { feature -> cad.history.indexOfFirst { it.id == feature.id } }
    }
    LaunchedEffect(cad.selectedFeature?.id) { cad.selectedFeature?.let { cutTarget = it.id } }
    val target = targets.firstOrNull { it.id == cutTarget } ?: targets.singleOrNull()
    val editing = cad.activeSketchId != null
    val selectedSketch = cad.selectedSketch
    val bodyHistory = cad.history.filter { cad.activeBodyId == null || it.bodyId == cad.activeBodyId }
    val lastNode = bodyHistory.lastOrNull()
    val viewIndex = if (barPos == null) bodyHistory.size
        else bodyHistory.count { node -> !behindBar(node.id) }
    LaunchedEffect(lastNode?.id, cad.activeSketch?.entities?.lastOrNull()?.id, editing, constraintsVisible) {
        if (!editing || !constraintsVisible) {
            withFrameNanos { }; withFrameNanos { }
            historyScroll.scrollTo(historyScroll.maxValue)
        }
    }
    val depthPreview = cad.sessionActive && cad.operation in listOf("EXTRUDE", "CUT")
    val dragPreview = cad.sessionActive && cad.operation == "DRAG"
    // Dibujar muestra las mismas medidas en vivo que arrastrar; se editan al soltar.
    val drawPreview = cad.sessionActive && cad.operation in listOf("LINE", "RECTANGLE", "CIRCLE", "ARC")
    val livePreview = dragPreview || drawPreview
    val finishPreview = cad.sessionActive && cad.operation in listOf("FILLET", "CHAMFER")
    // Colocar un plano: el rail elige la base y la bandeja sus medidas, con preview en la vista.
    val planePreview = cad.sessionActive && cad.operation == "PLANE"
    val availableHeight = (LocalConfiguration.current.screenHeightDp - 320).coerceAtLeast(100).dp
    fun command(name: String, vararg values: Pair<String, Any?>) { if (connected) vm.cadCommand(name, mapOf(*values)) }
    fun editSketch(sketchId: String) {
        vm.cadTool(null)
        constraintsVisible = false
        command("cad.sketch.activate", "sketch_id" to sketchId)
    }
    fun beginFeature(operation: String) {
        vm.cadTool(null)
        command("cad.extrude.begin", "profile_id" to cad.selectionId.takeIf { cad.selectionKind == "PROFILE" },
            "sketch_id" to cad.selectionId.takeIf { cad.selectionKind == "SKETCH" }, "depth" to cad.step * 10,
            "operation" to operation, "target_id" to target?.id)
    }
    if (planePreview) ToolRail(Modifier.align(Alignment.CenterStart).padding(start = Metrics.EdgeMargin, top = 120.dp, bottom = 160.dp).heightIn(max = availableHeight)) {
        val plane = cad.plane
        capabilities.planes.forEach { base ->
            CadAction("PLANE_$base", "Plano base ${cadPlaneLabel(base)}", selected = plane?.base == base,
                enabled = connected && plane?.planeId == null) { command("cad.plane.update", "base" to base) }
        }
        CadAction("SKETCH_FACE", if (cad.surface.canSketch) "Plano en la cara seleccionada" else "Selecciona antes una cara del sólido",
            selected = plane?.base == "FACE", enabled = connected && plane?.planeId == null && cad.surface.canSketch) {
            command("cad.plane.update", "base" to "FACE")
        }
        CadAction("PLANE_EDGE", if (cad.surface.canEdgePlane) "Plano en la arista seleccionada · gíralo sobre ella" else "Selecciona antes una arista recta del sólido",
            selected = plane?.base == "EDGE", enabled = connected && plane?.planeId == null && cad.surface.canEdgePlane) {
            command("cad.plane.update", "base" to "EDGE")
        }
    } else ToolRail(Modifier.align(Alignment.CenterStart).padding(start = Metrics.EdgeMargin, top = 120.dp, bottom = 160.dp).heightIn(max = availableHeight)) {
        CadAction("SELECT", "Cursor · tocar alterna selección · arrastrar mueve", selected = state.cadTool == null && cad.surface.mode == "PROFILE", enabled = !cad.sessionActive) { vm.cadTool(null) }
        if (editing) {
            RailDivider()
            capabilities.entities.forEach { type ->
                CadAction(type, cadLabel(type), selected = state.cadTool == type, enabled = !cad.sessionActive || cad.operation == type) { vm.cadTool(type) }
            }
            if (capabilities.sketchEditing) CadAction("FILLET", "Redondear esquinas seleccionadas", selected = pendingDimension == "FILLET",
                enabled = !cad.sessionActive && cad.selection.any { it.id != "ORIGIN" }) { pendingDimension = "FILLET" }
            if (capabilities.sketchEditing) CadAction("PROJECT", "Proyectar punto, arista o cara al plano del croquis",
                selected = cad.surface.mode != "PROFILE", enabled = !cad.sessionActive) {
                if (cad.surface.mode != "PROFILE" && cad.surface.selection.isNotEmpty()) command("cad.reference.project")
                else vm.cadSurfaceMode(if (cad.surface.mode != "PROFILE") "PROFILE" else "EDGE")
            }
        } else {
            RailDivider()
            capabilities.planes.forEach { plane ->
                CadAction("PLANE_$plane", "Nuevo boceto en ${cadPlaneLabel(plane)}", enabled = connected && !cad.sessionActive) { command("cad.plane.begin", "base" to plane) }
            }
            if (capabilities.sketchEditing) CadAction("SKETCH_FACE", "Crear croquis en la cara seleccionada",
                enabled = connected && !cad.sessionActive && cad.surface.canSketch) { command("cad.plane.begin", "base" to "FACE") }
            if (capabilities.edgePlane) CadAction("PLANE_EDGE", if (cad.surface.canEdgePlane) "Plano en la arista seleccionada · gíralo sobre ella"
                else "Plano en una arista: elige antes una arista recta del sólido",
                enabled = connected && !cad.sessionActive && (cad.surface.canEdgePlane || cad.surface.mode != "EDGE")) {
                if (cad.surface.canEdgePlane) command("cad.plane.begin", "base" to "EDGE") else vm.cadSurfaceMode("EDGE")
            }
            RailDivider()
            val solidEdges = cad.surface.selection.any { it.kind == "EDGE" }
            CadAction("FILLET", "Redondear aristas del sólido", enabled = connected && !cad.sessionActive) {
                if (solidEdges) command("cad.finish.begin", "operation" to "FILLET") else vm.cadSurfaceMode("EDGE")
            }
            CadAction("CHAMFER", "Chaflán en aristas del sólido", enabled = connected && !cad.sessionActive) {
                if (solidEdges) command("cad.finish.begin", "operation" to "CHAMFER") else vm.cadSurfaceMode("EDGE")
            }
            RailDivider()
            if ("LOFT" in capabilities.features) CadAction("LOFT", "Solevado: une este perfil con el de otro croquis", selected = loftFrom != null,
                enabled = connected && !cad.sessionActive && (loftFrom != null || cad.selectionKind in listOf("PROFILE", "SKETCH"))) {
                loftFrom = if (loftFrom != null) null else cad.selectionKind!! to cad.selectionId!!
            }
            if ("REVOLVE" in capabilities.features) CadAction("REVOLVE", "Revolución: gira el perfil alrededor de un eje del croquis (puede apoyarse en él)",
                enabled = connected && !cad.sessionActive && cad.selectionKind in listOf("PROFILE", "SKETCH")) {
                command("cad.revolve.create", (if (cad.selectionKind == "SKETCH") "sketch_id" else "profile_id") to cad.selectionId)
            }
            if ("HELIX" in capabilities.features) CadAction("HELIX", "Barrido helicoidal del perfil alrededor de un eje del croquis",
                enabled = connected && !cad.sessionActive && cad.selectionKind in listOf("PROFILE", "SKETCH")) {
                command("cad.helix.create", (if (cad.selectionKind == "SKETCH") "sketch_id" else "profile_id") to cad.selectionId)
            }
            capabilities.features.filter { it in listOf("EXTRUDE", "CUT") }.forEach { operation ->
                CadAction(operation, cadLabel(operation), selected = depthPreview && cad.operation == operation,
                    enabled = connected && !cad.sessionActive && cad.selectionKind in listOf("PROFILE", "SKETCH") && (operation != "CUT" || target != null)) { beginFeature(operation) }
            }
        }
    }
    if (editing && capabilities.constraints.isNotEmpty()) ToolRail(
        Modifier.align(Alignment.CenterEnd).padding(end = Metrics.EdgeMargin, top = 142.dp, bottom = 180.dp)
            .heightIn(max = availableHeight)
    ) {
        cadConstraintGroups(capabilities.constraints).forEachIndexed { index, group ->
            if (index > 0) RailDivider()
            group.forEach { type ->
                CadAction(type, cadLabel(type), enabled = connected && !cad.sessionActive && cadConstraintEnabled(cad, type),
                    selected = pendingDimension == type) {
                    if (type in listOf("DISTANCE", "DISTANCE_X", "DISTANCE_Y", "RADIUS", "ANGLE")) {
                        val existing = cad.dimensionOptions[type]?.constraintId?.let { id -> cad.activeSketch?.constraints?.firstOrNull { it.id == id } }
                        if (existing != null) { editingConstraint = existing; pendingDimension = null }
                        else { pendingDimension = type; editingConstraint = null }
                    } else command("cad.constraint.add", "type" to type)
                }
            }
        }
    }
    val contextualConstraints = cad.activeSketch?.constraints.orEmpty().filter { c ->
        (cad.selectionKind == "CONSTRAINT" && cad.selectionId == c.id) || cad.selection.any { selected ->
            c.refs.any { ref -> cadRefsTouch(selected, ref) } ||
                cad.activeSketch?.entities?.firstOrNull { it.id == selected.id }?.dimensions?.any { c.id in it.constraintIds } == true
        }
    }
    val contextual = editing && cad.selection.isNotEmpty()
    // La pila ocupa el sitio del inspector de modificadores —icono cerrado bajo el
    // selector de modos, panel derecho con flecha de vuelta— y se abre y se cierra
    // igual que él. El contexto (planos, vista, finalizar boceto) vive arriba, en la
    // fila de Deshacer/Rehacer, sin franja propia bajo el menú.
    val stackEnd = Metrics.EdgeMargin + if (editing && capabilities.constraints.isNotEmpty()) 80.dp else 0.dp
    if (!stackOpen) FloatingPanel(
        Modifier.align(Alignment.TopEnd).padding(top = 142.dp, end = stackEnd),
    ) {
        IconAction(Icons.Default.AccountTree, "Abrir pila de operaciones") { onStackOpen(true) }
    }
    if (stackOpen) FloatingPanel(
        Modifier.align(Alignment.TopEnd).fillMaxHeight().padding(top = 142.dp, end = stackEnd, bottom = stackBottom)
    ) {
        Column(Modifier.width(300.dp).fillMaxHeight()) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                IconAction(Icons.AutoMirrored.Filled.ArrowBack, "Cerrar pila de operaciones") { onStackOpen(false) }
                Text(if (editing) "Editando ${cad.activeSketch?.name.orEmpty()}" else "Pila de operaciones",
                    color = Ink.Accent, fontSize = 11.sp, fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.weight(1f).padding(start = 2.dp))
            }
            HorizontalDivider()
            if (editing) {
                Row(Modifier.padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    PillButton("Figuras", selected = !constraintsVisible) { constraintsVisible = false }
                    PillButton("Restricciones", selected = constraintsVisible) { constraintsVisible = true }
                }
                if (constraintsVisible && contextual) PillButton("Solo selección", selected = constraintsSelectionOnly) {
                    constraintsSelectionOnly = !constraintsSelectionOnly
                }
            }
            Column(Modifier.weight(1f).verticalScroll(historyScroll).padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                if (editing) {
                    if (!constraintsVisible) cad.activeSketch?.entities?.forEachIndexed { index, drawing ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(AppIcons.cad(drawing.type), null, tint = Ink.Muted, modifier = Modifier.size(20.dp))
                            PillButton("${if (drawing.reference) "Referencia" else if (drawing.isFillet) "Redondeo" else if (drawing.isSquare) "Cuadrado" else cadLabel(drawing.type)} ${index + 1}", selected = cad.selection.any { it.id == drawing.id }, enabled = connected && !cad.sessionActive) {
                                vm.cadTool(null)
                                command("cad.select", "kind" to "ENTITY", "id" to drawing.id, "part" to "BODY", "additive" to true)
                            }
                            CadAction("DELETE", if (drawing.isFillet) "Quitar redondeo" else "Borrar figura", enabled = connected && !cad.sessionActive) {
                                command(if (drawing.isFillet) "cad.fillet.remove" else "cad.entity.delete", "entity_id" to drawing.id)
                            }
                            if (drawing.type in capabilities.offsetEntities) {
                                var menu by remember(drawing.id) { mutableStateOf(false) }
                                Box {
                                    IconAction(Icons.Default.MoreVert, "Acciones del contorno", enabled = connected && !cad.sessionActive) { menu = true }
                                    DropdownMenu(menu, { menu = false }) {
                                        DropdownMenuItem(text = { Text("Desfase por grosor") }, onClick = {
                                            menu = false; vm.cadTool(null); offsetSource = drawing; offsetSide = "OUTWARD"
                                            pendingDimension = null; editingConstraint = null
                                        })
                                    }
                                }
                            }
                        }
                    } else (if (contextual && constraintsSelectionOnly) contextualConstraints else cad.activeSketch?.constraints.orEmpty()).forEach { c ->
                        CadConstraintRow(c, cad.activeSketch!!, unit, !cad.sessionActive,
                            { command("cad.select", "kind" to "CONSTRAINT", "id" to c.id) },
                            { command("cad.constraint.delete", "constraint_id" to c.id) })
                    }
                } else {
                    var bodiesOpen by remember { mutableStateOf(false) }
                    Box {
                        PillButton(cad.bodies.firstOrNull { it.id == cad.activeBodyId }?.name ?: "Cuerpo") { bodiesOpen = true }
                        DropdownMenu(bodiesOpen, { bodiesOpen = false }) {
                            cad.bodies.forEach { body -> DropdownMenuItem(text = { Text(body.name) }, onClick = { bodiesOpen = false; command("cad.body.activate", "body_id" to body.id) }) }
                            DropdownMenuItem(text = { Text("Copia editable · Edición / Escultura") },
                                enabled = connected && !cad.sessionActive && targets.any { it.bodyId == cad.activeBodyId },
                                onClick = { bodiesOpen = false; command("cad.convert", "body_id" to cad.activeBodyId) })
                            DropdownMenuItem(text = { Text("Nuevo cuerpo") }, onClick = { bodiesOpen = false; command("cad.body.create") })
                        }
                    }
                    bodyHistory.forEachIndexed { index, node ->
                        if (barPos != null && index == viewIndex) CadRollbackBar()
                        val dimmed = behindBar(node.id)
                        val nodeEnabled = connected && !cad.sessionActive
                        if (node.kind == "SKETCH") {
                            val sketch = cad.sketches.firstOrNull { it.id == node.id }
                            if (sketch != null) {
                                CadStackNodeRow("SKETCH", sketch.name, selectedSketch?.id == sketch.id, dimmed, nodeEnabled,
                                    tap = { command("cad.history.rollback", "node_id" to node.id) },
                                    actions = listOf(
                                        CadNodeAction("Renombrar croquis") { renamingSketch = sketch },
                                        CadNodeAction("Editar boceto") { editSketch(sketch.id) },
                                        CadNodeAction("Seleccionar croquis completo", sketch.profiles.isNotEmpty()) {
                                            vm.cadTool(null); command("cad.select", "kind" to "SKETCH", "id" to sketch.id)
                                        },
                                        CadNodeAction("Copiar a otro plano paralelo") {
                                            vm.cadTool(null); command("cad.sketch.copy", "sketch_id" to sketch.id, "offset" to cad.step * 10)
                                        },
                                        CadNodeAction(if (sketch.visible) "Ocultar boceto" else "Mostrar boceto") {
                                            command("cad.sketch.visibility", "sketch_id" to sketch.id, "visible" to !sketch.visible)
                                        },
                                        CadNodeAction("Borrar boceto", cad.features.none { it.sketchId == sketch.id }) {
                                            command("cad.sketch.delete", "sketch_id" to sketch.id)
                                        },
                                    ))
                            }
                        } else {
                            val feature = cad.features.firstOrNull { it.id == node.id }
                            if (feature != null) {
                                CadStackNodeRow(feature.type, feature.name + if (!feature.enabled) " · desactivada" else "",
                                    cad.selectedFeature?.id == feature.id, dimmed, nodeEnabled,
                                    tap = { command("cad.history.rollback", "node_id" to node.id) },
                                    actions = listOfNotNull(
                                        CadNodeAction("Seleccionar") {
                                            vm.cadTool(null); command("cad.select", "kind" to "FEATURE", "id" to feature.id)
                                        },
                                        if (!feature.isFinish) CadNodeAction("Editar ${cad.sketches.firstOrNull { it.id == feature.sketchId }?.name ?: "boceto fuente"}") { editSketch(feature.sketchId) } else null,
                                        if (capabilities.featureMirror && feature.type in listOf("EXTRUDE", "CUT") && !feature.isMirror)
                                            CadNodeAction("Simetría de operación", feature.enabled && !dimmed) {
                                                vm.cadTool(null); mirrorSource = feature; mirrorPlane = "XZ"
                                                pendingDimension = null; editingConstraint = null
                                            } else null,
                                        CadNodeAction(if (feature.enabled) "Desactivar" else "Activar") {
                                            command("cad.feature.set", "feature_id" to feature.id, "enabled" to !feature.enabled)
                                        },
                                        CadNodeAction("Borrar") {
                                            vm.cadTool(null); command("cad.feature.delete", "feature_id" to feature.id)
                                        },
                                    ))
                            }
                        }
                    }
                    if (barPos != null && viewIndex >= bodyHistory.size) CadRollbackBar()
                }
            }
            if (!editing) {
                HorizontalDivider(Modifier.padding(top = 6.dp))
                Row(Modifier.padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                    PillButton("Atrás", enabled = connected && !cad.sessionActive && viewIndex > 1) {
                        command("cad.history.rollback", "node_id" to bodyHistory[viewIndex - 2].id)
                    }
                    PillButton("Adelante", enabled = connected && !cad.sessionActive && viewIndex < bodyHistory.size) {
                        command("cad.history.rollback", "node_id" to bodyHistory[viewIndex].id)
                    }
                    PillButton("Final", enabled = connected && !cad.sessionActive && barPos != null) {
                        command("cad.history.rollback")
                    }
                    Text(if (barPos == null) "Modelo completo" else "Hasta ${bodyHistory.getOrNull(viewIndex - 1)?.name.orEmpty()}",
                        color = Ink.Faint, fontSize = 11.sp, maxLines = 1, textAlign = TextAlign.End, modifier = Modifier.weight(1f))
                }
            }
        }
    }
    val focusManager = LocalFocusManager.current
    val editScope = listOf(cad.documentId, cad.activeSketchId, cad.selection, cad.selectionId,
        cad.sessionId, cad.revision, state.cadTool, pendingDimension, editingConstraint?.id, offsetSource?.id, mirrorSource?.id)
    var resetInputs by remember(editScope) { mutableIntStateOf(0) }
    val drafts = remember(editScope, resetInputs) { mutableStateMapOf<String, Double?>() }
    val validDrafts = drafts.values.all { it != null }
    val entity = cad.selectedEntity?.takeUnless { (cad.sessionActive && !livePreview) || pendingDimension != null || editingConstraint != null || offsetSource != null || cad.surface.mode != "PROFILE" }
    val feature = cad.selectedFeature?.takeUnless { cad.sessionActive || editing || mirrorSource != null || cad.surface.mode != "PROFILE" }
    // A sketch on a saved plane moves along its normal from the 3D tray.
    val offsetPlane = if (editing || feature != null || cad.sessionActive) null
        else selectedSketch?.planeId?.let { id -> cad.planes.firstOrNull { it.id == id } }
    /** Envía las medidas escritas del plano (las no escritas conservan su valor actual). */
    fun pushPlane() {
        val plane = cad.plane ?: return
        command("cad.plane.update", "offset" to (drafts["plane_offset"] ?: plane.offset),
            "tilt" to listOf(drafts["plane_tilt0"] ?: plane.tilt[0], drafts["plane_tilt1"] ?: plane.tilt[1]),
            "shift" to listOf(drafts["plane_shift0"] ?: plane.shift[0], drafts["plane_shift1"] ?: plane.shift[1]))
        drafts.keys.filter { it.startsWith("plane_") }.forEach { drafts.remove(it) }
    }
    fun acceptValues() {
        if (!connected || !validDrafts || livePreview) return
        focusManager.clearFocus()
        when {
            planePreview -> {
                if (drafts.keys.any { it.startsWith("plane_") }) pushPlane()
                command("cad.session.confirm")
            }
            depthPreview -> {
                drafts["depth"]?.let { command("cad.extrude.update", "depth" to it) }
                if (cad.canConfirm) command("cad.session.confirm")
            }
            finishPreview -> {
                drafts["width"]?.let { command("cad.finish.update", "width" to it) }
                if (cad.canConfirm) command("cad.session.confirm")
            }
            offsetSource != null -> {
                command("cad.entity.offset", "entity_id" to offsetSource!!.id,
                    "thickness" to (drafts["thickness"] ?: cad.step), "side" to offsetSide)
                offsetSource = null
            }
            mirrorSource != null -> {
                command("cad.feature.mirror", "feature_id" to mirrorSource!!.id,
                    "plane" to mirrorPlane, "offset" to (drafts["mirror_offset"] ?: 0.0))
                mirrorSource = null
            }
            feature?.isFinish == true && drafts["width"] != null -> command("cad.feature.set", "feature_id" to feature.id, "width" to drafts["width"])
            pendingDimension != null -> {
                val type = pendingDimension!!
                val value = drafts["constraint"] ?: cad.dimensionOptions[type]?.value ?: cad.step * 5
                if (type == "FILLET") command("cad.fillet", "radius" to value)
                else command("cad.constraint.add", "type" to type, "value" to value)
                pendingDimension = null
            }
            editingConstraint != null -> {
                val constraint = editingConstraint!!
                command("cad.constraint.set", "constraint_id" to constraint.id,
                    "sketch_id" to cad.sketches.firstOrNull { sketch -> sketch.constraints.any { it.id == constraint.id } }?.id,
                    "value" to (drafts["constraint"] ?: constraint.value))
                editingConstraint = null
            }
            entity != null && drafts.isNotEmpty() -> command("cad.entity.set", "entity_id" to entity.id,
                "values" to drafts.toMap(), "constrain" to true,
                "equal_ids" to cadOtherSelectedArcs(cad, entity).takeIf { it.isNotEmpty() })
            feature?.isMirror == true && drafts["mirror_offset"] != null -> command("cad.feature.set", "feature_id" to feature.id, "offset" to drafts["mirror_offset"])
            feature?.type == "REVOLVE" && drafts["angle"] != null -> command("cad.feature.set", "feature_id" to feature.id, "angle" to drafts["angle"])
            feature?.type == "HELIX" && drafts["pitch"] != null -> command("cad.feature.set", "feature_id" to feature.id, "pitch" to drafts["pitch"])
            feature != null && drafts["depth"] != null -> command("cad.feature.set", "feature_id" to feature.id, "depth" to drafts["depth"])
            offsetPlane != null && drafts["offset"] != null -> command("cad.plane.set", "plane_id" to offsetPlane.id,
                "translation" to offsetPlane.translation.take(2) + drafts["offset"]!!)
        }
    }
    fun discardValues() {
        focusManager.clearFocus()
        if (depthPreview || finishPreview || planePreview) command("cad.session.cancel")
        if (cad.selectionKind == "CONSTRAINT") command("cad.select_all", "action" to "DESELECT")
        pendingDimension = null; editingConstraint = null; offsetSource = null; mirrorSource = null; resetInputs++
    }
    val canAccept = connected && validDrafts && when {
        depthPreview || finishPreview -> cad.canConfirm
        planePreview -> true
        pendingDimension != null -> true
        offsetSource != null || mirrorSource != null -> true
        else -> drafts.isNotEmpty()
    }
    val parameterScroll = rememberScrollState()
    val hasValues = depthPreview || finishPreview || planePreview || pendingDimension != null || editingConstraint != null || entity != null || feature != null || offsetPlane != null || offsetSource != null || mirrorSource != null
    FloatingPanel(Modifier.align(Alignment.BottomCenter).fillMaxWidth().onSizeChanged { onTrayHeight(it.height) }.padding(Metrics.EdgeMargin)) {
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(cad.error ?: when {
                !connected -> "Reconectando · recuperando el documento de Blender"
                planePreview -> cad.plane?.let { plane ->
                    (if (plane.planeId != null) "Colocar plano guardado" else "Plano ${if (plane.base == "FACE") "en la cara" else cadPlaneLabel(plane.base)}") +
                        " · arrastra con el lápiz para separarlo · positivo: ${plane.positiveLabel.lowercase()} · ✓ " +
                        (if (plane.planeId != null) "aplica la posición" else "crea el croquis")
                } ?: "Colocando plano"
                offsetSource != null -> "Desfase vinculado: elige dentro o fuera y escribe el grosor · ✓ crea el contorno"
                mirrorSource != null -> "Simetría de ${mirrorSource!!.name}: elige el plano y su posición · ✓ crea la operación vinculada"
                feature?.isMirror == true -> "${feature.name} · perfil y profundidad siguen a la operación fuente"
                editingConstraint != null -> "${cadLabel(editingConstraint!!.type)} · escribe el valor · arrastra la cota para colocarla sin mover el dibujo"
                loftFrom != null -> "Solevado: toca el perfil del otro croquis (o elígelo en la pila) · vuelve a pulsar Solevado para cancelar"
                feature?.type == "REVOLVE" -> "${feature.name} · el perfil gira alrededor del eje elegido; puede apoyarse en él (conos, cúpulas) pero no cruzarlo"
                feature?.type == "HELIX" -> "${feature.name} · altura ${formatToolDistance(feature.pitch * feature.turns * lengthFactor(unit), 2)} ${unit.short} · el paso debe superar la altura del perfil · el eje es X, Y o una línea del croquis"
                feature?.type == "LOFT" -> "${feature.name} · une ${cad.sketches.firstOrNull { it.id == feature.sketchId }?.name.orEmpty()} con otro croquis · mover su plano lo actualiza"
                pendingDimension == "FILLET" -> "Redondeo: varias esquinas, el rectángulo entero o líneas unidas · un radio para todas · tras el primero, toca otra esquina"
                drafts.isNotEmpty() && !depthPreview -> "Medidas pendientes · ✓ aplica los cambios · × descarta"
                depthPreview -> if (cad.operation == "EXTRUDE")
                    "Extrusión · Simetría crece a los dos lados del croquis · si no, desliza en el sentido del plano · suelta para asentar"
                else "${cadLabel(cad.operation)} · desliza en el sentido del vaciado" +
                    " · una dirección o las dos · dos dedos navegan" + if (cad.transparent) " · transparencia automática" else ""
                finishPreview -> "${cadLabel(cad.operation)} · desliza arriba/abajo o escribe el ancho · ✓ lo añade a la pila"
                dragPreview -> "Medidas en vivo · suelta para fijar una medida con su candado"
                drawPreview -> "Medidas en vivo · Incremento redondea al paso y los puntos existentes atraen · suelta para editar las medidas"
                cad.sessionActive && cad.operation == "POLYGON" -> "Polígono: traza o toca cada vértice · cierra tocando el primer punto o con Cerrar · dos dedos descarta"
                editing && cad.surface.mode != "PROFILE" -> "Toca para añadir referencias; repite para quitarlas · puedes combinar Puntos/Aristas/Caras · Proyectar al plano copia toda la selección al croquis"
                cad.surface.mode == "FACE" -> if (cad.surface.selection.size > 1) "Dos referencias para medir · quita una cara seleccionada para crear el boceto" else "Toca una cara: se resalta en el vídeo · Boceto en cara usa exactamente esa selección"
                cad.surface.mode != "PROFILE" -> "Toca hasta dos referencias para medir · durante el boceto puedes proyectarlas para acotar desde ellas"
                editing && state.cadTool == "ARC" -> "Arrastra centro → inicio del arco · al soltar, arrastra el rombo del extremo para variar el ángulo"
                entity?.type == "ARC" && !entity.isFillet -> "Arrastra el rombo del extremo para variar el ángulo; centro, radio e inicio permanecen fijos"
                editing && state.cadTool == "NGON" -> "Polígono regular: arrastra del centro a un vértice · elige los lados antes o después · Entre caras es la llave de la tuerca"
                editing && state.cadTool == "SLOT" -> "Ranura: arrastra entre los centros de los extremos · Radio es la mitad del Ancho · Entre centros conserva la longitud recta"
                editing && state.cadTool == "GEAR" -> "Engranaje: arrastra del centro al círculo primitivo · Incremento elige un módulo normalizado · dientes antes o después"
                editing && state.cadTool != null -> "${cadLabel(state.cadTool!!)} · arrastra para dibujar · dos dedos navegan"
                entity?.type == "GEAR" -> cadGearSummary(entity, unit)
                entity?.isSquare == true -> if (entity.dimensions.any { it.constraintIds.isNotEmpty() })
                    "Cuadrado: una cota controla ambos lados; editar Lado actualiza esa misma cota"
                    else "Cuadrado: Igualdad une sus lados; Fijar medida añade una cota de tamaño"
                entity?.isFillet == true -> "Redondeo: cambia su radio · su papelera en Figuras recupera la esquina"
                editing -> "Cursor: toca para seleccionar o quitar · dos dedos giran la vista y se queda · Girar 90° y Enderezar la colocan"
                !editing && cad.rollbackId != null -> "Vista del pasado: ${cad.history.firstOrNull { it.id == cad.rollbackId }?.name.orEmpty()} · toca un nodo para ver el modelo en ese momento · Final restaura la pila completa"
                cad.selectionKind == "SKETCH" -> "${selectedSketch?.name.orEmpty()} completo · Extruir crea volumen y conserva los contornos interiores como huecos"
                selectedSketch != null -> "${selectedSketch.name} · perfil seleccionado · Seleccionar todo elige el croquis completo para extruir"
                else -> "Abre la pila (derecha) para editar un boceto · o crea uno en Planos, arriba, y selecciona un perfil para extruir"
            }, color = Ink.Muted, fontSize = 12.sp)
            Row(verticalAlignment = Alignment.CenterVertically) {
                key(editScope, resetInputs) {
                    Row(Modifier.weight(1f).horizontalScroll(parameterScroll), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                        if (cad.surface.mode != "PROFILE" || !editing) {
                            CadSurfaceControls(cad, unit, connected && !cad.sessionActive, vm)
                        }
                        if (capabilities.sketchEditing && (editing || depthPreview)) {
                            SnapControl(listOf(SnapType.NONE, SnapType.INCREMENT), if (cad.increment) SnapType.INCREMENT else SnapType.NONE,
                                { command("cad.settings", "increment" to (it == SnapType.INCREMENT)) })
                        }
                        CadSnapStepInput(cad.step, unit, { unit = it }) { command("cad.settings", "step" to it) }
                        offsetSource?.let { source ->
                            listOf("OUTWARD" to "Hacia fuera", "INWARD" to "Hacia dentro").forEach { (side, label) ->
                                PillButton(label, selected = offsetSide == side, enabled = connected) { offsetSide = side }
                            }
                            CadDimension("Grosor", drafts["thickness"] ?: cad.step, unit, source.id + "offset",
                                step = cad.step, minimum = .0000001, enabled = connected, onDone = ::acceptValues) { drafts["thickness"] = it }
                        }
                        mirrorSource?.let { source ->
                            CadMirrorPlaneSelector(mirrorPlane, connected) { mirrorPlane = it }
                            CadDimension("Posición del plano", drafts["mirror_offset"] ?: 0.0, unit, source.id + "mirror",
                                step = cad.step, minimum = -10000.0, enabled = connected, onDone = ::acceptValues) { drafts["mirror_offset"] = it }
                        }
                        editingConstraint?.takeIf { it.value != null }?.let { constraint ->
                            // Cota seleccionada: su valor y, al lado, quitarla. Nada más.
                            val angle = constraint.type == "ANGLE"
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                CadDimension(cadLabel(constraint.type), drafts["constraint"] ?: constraint.value!!, unit, constraint.id,
                                    degrees = angle, step = if (angle) 1.0 else cad.step, enabled = connected, readOnly = livePreview,
                                    minimum = if (angle) .01 else if (constraint.type in listOf("DISTANCE_X", "DISTANCE_Y")) 0.0 else .0000001,
                                    maximum = if (angle) 359.99 else 10000.0,
                                    onDone = ::acceptValues) { drafts["constraint"] = it }
                                CadAction("DELETE", "Quitar cota · conserva el dibujo", enabled = connected && !cad.sessionActive) {
                                    command("cad.constraint.delete", "constraint_id" to constraint.id,
                                        "sketch_id" to cad.sketches.firstOrNull { sketch -> sketch.constraints.any { it.id == constraint.id } }?.id)
                                    editingConstraint = null
                                }
                            }
                        }
                        pendingDimension?.let { type ->
                            val angle = type == "ANGLE"
                            CadDimension(if (type == "FILLET") "Radio" else cadLabel(type), drafts["constraint"] ?: cad.dimensionOptions[type]?.value ?: cad.step * 5, unit, type,
                                degrees = angle, step = if (angle) 1.0 else cad.step, maximum = if (angle) 180.0 else 10000.0,
                                enabled = connected, minimum = if (angle || type in listOf("DISTANCE_X", "DISTANCE_Y")) 0.0 else .0000001,
                                onDone = ::acceptValues) { drafts["constraint"] = it }
                        }
                        if (editing && state.cadTool == "NGON" && entity == null) {
                            CadSidesControl(state.cadNgonSides, enabled = !cad.sessionActive) { vm.cadNgonSides(it) }
                        }
                        if (editing && state.cadTool == "GEAR" && entity == null) {
                            CadCountControl("Dientes", state.cadGearTeeth, 6..150, enabled = !cad.sessionActive) { vm.cadGearTeeth(it) }
                        }
                        entity?.let { selected ->
                            if (selected.type == "GEAR") {
                                val editable = connected && !livePreview && drafts.isEmpty()
                                CadCountControl("Dientes", selected.values["teeth"]?.toInt() ?: 20, 6..150, editable) {
                                    command("cad.entity.set", "entity_id" to selected.id, "values" to mapOf("teeth" to it))
                                }
                                listOf(14.5, 20.0, 25.0).forEach { angle ->
                                    PillButton("${formatToolDistance(angle, 1)}°", selected = selected.values["pressure"] == angle, enabled = editable) {
                                        command("cad.entity.set", "entity_id" to selected.id, "values" to mapOf("pressure" to angle))
                                    }
                                }
                            }
                            if (selected.type == "NGON") {
                                val sides = selected.values["sides"]?.toInt() ?: 6
                                CadSidesControl(sides, enabled = connected && !livePreview && drafts.isEmpty()) {
                                    command("cad.entity.set", "entity_id" to selected.id, "values" to mapOf("sides" to it))
                                }
                            }
                            if (selected.type in listOf("CIRCLE", "SLOT") && selected.dimensions.any { it.field == "radius" }) {
                                PillButton("Radio", selected = !showDiameter, enabled = drafts.isEmpty()) { showDiameter = false }
                                PillButton(if (selected.type == "SLOT") "Ancho" else "Diámetro", selected = showDiameter, enabled = drafts.isEmpty()) { showDiameter = true }
                            }
                            // Solo medidas: la posición se fija con candados y cotas a otros
                            // puntos (origen, esquinas, centros), no escribiendo coordenadas.
                            // El ángulo del arco/redondeo es una medida más, con su candado.
                            val measures = cadDisplayMeasures(selected, showDiameter)
                            val fields = measures.map { it.field to it.label }
                            val otherArcs = cadOtherSelectedArcs(cad, selected)
                            if (otherArcs.isNotEmpty()) {
                                // El ángulo de un redondeo es automático: entonces solo se iguala el radio.
                                val roundings = selected.isFillet || cad.activeSketch?.entities.orEmpty().any { it.id in otherArcs && it.isFillet }
                                Text("${otherArcs.size + 1} arcos: " + if (roundings) "Radio se aplica a todos (Igualdad)" else "Radio y Ángulo se aplican a todos (Igualdad)",
                                    color = Ink.Accent, fontSize = 11.sp)
                            }
                            fields.forEach { (field, label) ->
                                val measure = measures.firstOrNull { it.field == field }
                                val degrees = measure?.constraintType == "ANGLE"
                                val bound = measure?.constraintIds?.isNotEmpty() == true
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    CadDimension(label + if (measure != null) if (bound) " · cota" else " · sin cota" else "",
                                        drafts[field] ?: selected.values[field] ?: 0.0, unit, selected.id + field,
                                        degrees = degrees, step = if (degrees) 1.0 else cad.step, enabled = connected, readOnly = livePreview,
                                        minimum = if (degrees) -359.99 else if (measure != null) .0000001 else -10000.0,
                                        maximum = if (field == "sweep") 359.99 else 10000.0,
                                        onDone = ::acceptValues) { drafts[field] = it?.takeIf { value -> field != "sweep" || kotlin.math.abs(value) in .01..359.99 } }
                                    if (measure != null && measure.lockable) CadAction("FIX", (if (bound) "Quitar cota: " else "Fijar medida: ") + label,
                                        selected = bound, enabled = connected && !livePreview && drafts.isEmpty()) {
                                        if (bound) command("cad.constraint.delete", "constraint_id" to measure.constraintIds.first())
                                        else command("cad.constraint.add", "type" to measure.constraintType,
                                            "value" to ((selected.values[field] ?: 0.0) * measure.valueFactor),
                                            "refs" to measure.refs.map { mapOf("id" to it.id, "part" to it.part) })
                                    }
                                }
                            }
                        }
                        if (!editing && !cad.sessionActive && "CUT" in capabilities.features) {
                            var expanded by remember { mutableStateOf(false) }
                            Box {
                                PillButton("Destino: ${cad.bodies.firstOrNull { it.id == target?.bodyId }?.name ?: "elegir cuerpo"}", enabled = connected && targets.isNotEmpty()) { expanded = true }
                                DropdownMenu(expanded, onDismissRequest = { expanded = false }) {
                                    targets.forEach { item -> DropdownMenuItem(text = { Text(cad.bodies.firstOrNull { it.id == item.bodyId }?.name ?: item.name) }, onClick = { cutTarget = item.id; expanded = false }) }
                                }
                            }
                        }
                        if (cad.sessionActive && cad.operation == "POLYGON") {
                            PillButton("Cerrar polígono", enabled = connected && cad.canClose) { vm.cadCommand("cad.polygon.close") }
                            RoundAction(AppIcons.cad("CANCEL"), "Descartar polígono", Ink.Bad, { vm.cadCommand("cad.session.cancel") })
                        }
                        if (planePreview) cad.plane?.let { plane ->
                            val axes = cadPlaneAxes(plane.base.takeIf { it != "FACE" && plane.planeId == null })
                            val id = cad.sessionId.orEmpty()
                            fun send(offset: Double = plane.offset, tilt: List<Double> = plane.tilt, shift: List<Double> = plane.shift) {
                                drafts.keys.filter { it.startsWith("plane_") }.forEach { drafts.remove(it) }
                                command("cad.plane.update", "offset" to offset, "tilt" to tilt, "shift" to shift)
                            }
                            if (plane.base == "EDGE") Text("Inclinar sobre la arista gira el plano alrededor de ella", color = Ink.Accent, fontSize = 11.sp)
                            CadDimension("Separación", plane.offset, unit, id + "offset", step = cad.step, enabled = connected,
                                onNudge = { send(offset = it) }, onDone = { drafts["plane_offset"]?.let { send(offset = it) } }) { drafts["plane_offset"] = it }
                            (0..1).forEach { i ->
                                CadDimension("Inclinar ${axes.rotation[i]}", plane.tilt[i], unit, id + "tilt$i", degrees = true, step = 5.0,
                                    minimum = -180.0, maximum = 180.0, enabled = connected,
                                    onNudge = { send(tilt = plane.tilt.toMutableList().also { list -> list[i] = it }) },
                                    onDone = { drafts["plane_tilt$i"]?.let { send(tilt = plane.tilt.toMutableList().also { list -> list[i] = it }) } }) { drafts["plane_tilt$i"] = it }
                            }
                            (0..1).forEach { i ->
                                CadDimension("Mover ${axes.inPlane[i]}", plane.shift[i], unit, id + "shift$i", step = cad.step, enabled = connected,
                                    onNudge = { send(shift = plane.shift.toMutableList().also { list -> list[i] = it }) },
                                    onDone = { drafts["plane_shift$i"]?.let { send(shift = plane.shift.toMutableList().also { list -> list[i] = it }) } }) { drafts["plane_shift$i"] = it }
                            }
                            PillButton("Ver escena", selected = cad.showScene, enabled = connected) { command("cad.settings", "show_scene" to !cad.showScene) }
                            if (cad.planes.isNotEmpty() && plane.planeId == null) {
                                var savedOpen by remember { mutableStateOf(false) }
                                Box {
                                    PillButton("Planos guardados", enabled = connected) { savedOpen = true }
                                    DropdownMenu(savedOpen, onDismissRequest = { savedOpen = false }) {
                                        if (capabilities.planePurge) DropdownMenuItem(text = { Text("Limpiar planos sin usar") }, onClick = {
                                            savedOpen = false; command("cad.session.cancel"); command("cad.plane.purge")
                                        })
                                        cad.planes.forEach { saved ->
                                            DropdownMenuItem(text = { Text("${saved.name} · nuevo croquis") }, onClick = {
                                                savedOpen = false; command("cad.session.cancel"); command("cad.sketch.create", "plane_id" to saved.id)
                                            })
                                            DropdownMenuItem(text = { Text("${saved.name} · colocar") }, onClick = {
                                                savedOpen = false; command("cad.plane.begin", "plane_id" to saved.id)
                                            })
                                        }
                                    }
                                }
                            }
                        }
                        if (depthPreview) {
                            PillButton("Una dirección", selected = cad.extent != "BOTH", enabled = connected) {
                                command("cad.extrude.update", "extent" to "ONE")
                            }
                            PillButton(if (cad.operation == "EXTRUDE") "Simetría" else "Dos direcciones", selected = cad.extent == "BOTH", enabled = connected) {
                                command("cad.extrude.update", "extent" to "BOTH")
                            }
                            if (cad.operation == "EXTRUDE" && cad.extent != "BOTH" && cad.positiveDirection.isNotEmpty()) {
                                val magnitude = kotlin.math.abs(cad.depth).coerceAtLeast(cad.step)
                                PillButton(cad.positiveDirection, selected = cad.depth >= 0, enabled = connected) {
                                    command("cad.extrude.update", "depth" to magnitude)
                                }
                                PillButton(cad.negativeDirection, selected = cad.depth < 0, enabled = connected) {
                                    command("cad.extrude.update", "depth" to -magnitude)
                                }
                            }
                            fun preview(value: Double) { drafts.remove("depth"); command("cad.extrude.update", "depth" to value) }
                            CadDimension("Profundidad", cad.depth, unit, cad.sessionId.orEmpty(), step = cad.step,
                                minimum = if (cad.operation == "EXTRUDE") -10000.0 else .0000001, enabled = connected, onNudge = ::preview,
                                onDone = { drafts["depth"]?.let(::preview) }) { drafts["depth"] = it }
                        } else if (finishPreview) {
                            fun preview(value: Double) { drafts.remove("width"); command("cad.finish.update", "width" to value) }
                            CadDimension("Ancho", cad.width, unit, cad.sessionId.orEmpty(), step = cad.step,
                                minimum = .0000001, enabled = connected, onNudge = ::preview,
                                onDone = { drafts["width"]?.let(::preview) }) { drafts["width"] = it }
                            if (cad.operation == "FILLET") CadCountControl("Segmentos", cad.segments, 1..16, connected) {
                                command("cad.finish.update", "segments" to it)
                            }
                        } else if (feature?.isMirror == true) {
                            CadMirrorPlaneSelector(feature.mirrorPlane, connected && drafts.isEmpty()) {
                                command("cad.feature.set", "feature_id" to feature.id, "plane" to it)
                            }
                            CadDimension("Posición del plano", drafts["mirror_offset"] ?: feature.mirrorOffset, unit, feature.id,
                                step = cad.step, minimum = -10000.0, enabled = connected, onDone = ::acceptValues) { drafts["mirror_offset"] = it }
                            PillButton("Operación fuente", enabled = connected) {
                                command("cad.select", "kind" to "FEATURE", "id" to feature.mirrorSourceId)
                            }
                            CadAction("VISIBLE", if (feature.enabled) "Desactivar simetría" else "Activar simetría", selected = feature.enabled, enabled = connected) {
                                command("cad.feature.set", "feature_id" to feature.id, "enabled" to !feature.enabled)
                            }
                            CadAction("DELETE", "Borrar simetría", enabled = connected) { command("cad.feature.delete", "feature_id" to feature.id) }
                        } else if (feature?.isFinish == true) {
                            CadDimension("Ancho", drafts["width"] ?: feature.width, unit, feature.id,
                                step = cad.step, minimum = .0000001, enabled = connected, onDone = ::acceptValues) { drafts["width"] = it }
                            if (feature.type == "FILLET") CadCountControl("Segmentos", feature.segments, 1..16, connected && drafts.isEmpty()) {
                                command("cad.feature.set", "feature_id" to feature.id, "segments" to it)
                            }
                            Text("${feature.edgeCount} aristas", color = Ink.Muted, fontSize = 12.sp)
                            CadAction("VISIBLE", if (feature.enabled) "Ocultar" else "Mostrar", selected = feature.enabled, enabled = connected) { command("cad.feature.set", "feature_id" to feature.id, "enabled" to !feature.enabled) }
                            CadAction("DELETE", "Borrar operación", enabled = connected) { command("cad.feature.delete", "feature_id" to feature.id) }
                        } else if (feature?.type == "REVOLVE") {
                            CadDimension("Ángulo", drafts["angle"] ?: feature.angle, unit, feature.id + "angle", degrees = true, step = 15.0,
                                minimum = .01, maximum = 360.0, enabled = connected, onDone = ::acceptValues) { drafts["angle"] = it }
                            val lines = cad.sketches.firstOrNull { it.id == feature.sketchId }?.entities.orEmpty().filter { it.type == "LINE" && it.construction }
                            (listOf("Y" to "Eje Y", "X" to "Eje X") + lines.mapIndexed { i, line -> line.id to "Eje línea ${i + 1}" }).forEach { (axis, label) ->
                                PillButton(label, selected = feature.axis == axis, enabled = connected && drafts.isEmpty()) {
                                    command("cad.feature.set", "feature_id" to feature.id, "axis" to axis)
                                }
                            }
                            CadAction("VISIBLE", if (feature.enabled) "Ocultar" else "Mostrar", selected = feature.enabled, enabled = connected) { command("cad.feature.set", "feature_id" to feature.id, "enabled" to !feature.enabled) }
                            CadAction("DELETE", "Borrar operación", enabled = connected) { command("cad.feature.delete", "feature_id" to feature.id) }
                        } else if (feature?.type == "HELIX") {
                            CadDimension("Paso", drafts["pitch"] ?: feature.pitch, unit, feature.id + "pitch",
                                step = cad.step, minimum = .0000001, enabled = connected, onDone = ::acceptValues) { drafts["pitch"] = it }
                            CadCountControl("Vueltas", kotlin.math.round(feature.turns).toInt().coerceAtLeast(1), 1..200, connected && drafts.isEmpty()) {
                                command("cad.feature.set", "feature_id" to feature.id, "turns" to it)
                            }
                            listOf("RIGHT" to "Derecha", "LEFT" to "Izquierda").forEach { (hand, label) ->
                                PillButton(label, selected = feature.hand == hand, enabled = connected && drafts.isEmpty()) {
                                    command("cad.feature.set", "feature_id" to feature.id, "hand" to hand)
                                }
                            }
                            val lines = cad.sketches.firstOrNull { it.id == feature.sketchId }?.entities.orEmpty().filter { it.type == "LINE" && it.construction }
                            (listOf("Y" to "Eje Y", "X" to "Eje X") + lines.mapIndexed { i, line -> line.id to "Eje línea ${i + 1}" }).forEach { (axis, label) ->
                                PillButton(label, selected = feature.axis == axis, enabled = connected && drafts.isEmpty()) {
                                    command("cad.feature.set", "feature_id" to feature.id, "axis" to axis)
                                }
                            }
                            CadAction("VISIBLE", if (feature.enabled) "Ocultar" else "Mostrar", selected = feature.enabled, enabled = connected) { command("cad.feature.set", "feature_id" to feature.id, "enabled" to !feature.enabled) }
                            CadAction("DELETE", "Borrar operación", enabled = connected) { command("cad.feature.delete", "feature_id" to feature.id) }
                        } else if (feature?.type == "LOFT") {
                            CadAction("VISIBLE", if (feature.enabled) "Ocultar" else "Mostrar", selected = feature.enabled, enabled = connected) { command("cad.feature.set", "feature_id" to feature.id, "enabled" to !feature.enabled) }
                            CadAction("DELETE", "Borrar operación", enabled = connected) { command("cad.feature.delete", "feature_id" to feature.id) }
                        } else if (offsetPlane != null) {
                            CadDimension("Separación Z", drafts["offset"] ?: offsetPlane.translation.getOrElse(2) { 0.0 }, unit, offsetPlane.id,
                                step = cad.step, enabled = connected, onDone = ::acceptValues) { drafts["offset"] = it }
                        } else feature?.let { selected ->
                            if (selected.type == "CUT" || selected.type == "EXTRUDE") {
                                PillButton("Una dirección", selected = selected.extent != "BOTH", enabled = connected) {
                                    command("cad.feature.set", "feature_id" to selected.id, "extent" to "ONE")
                                }
                                PillButton(if (selected.type == "EXTRUDE") "Simetría" else "Dos direcciones", selected = selected.extent == "BOTH", enabled = connected) {
                                    command("cad.feature.set", "feature_id" to selected.id, "extent" to "BOTH")
                                }
                            }
                            CadDimension("Profundidad", drafts["depth"] ?: selected.depth, unit, selected.id,
                                step = cad.step, minimum = if (selected.type == "EXTRUDE") -10000.0 else .0000001,
                                enabled = connected, onDone = ::acceptValues) { drafts["depth"] = it }
                            CadAction("VISIBLE", if (selected.enabled) "Ocultar" else "Mostrar", selected = selected.enabled, enabled = connected) { command("cad.feature.set", "feature_id" to selected.id, "enabled" to !selected.enabled) }
                            CadAction("DELETE", "Borrar operación", enabled = connected) { command("cad.feature.delete", "feature_id" to selected.id) }
                        }
                    }
                }
                if (hasValues && !livePreview) {
                    Spacer(Modifier.width(10.dp))
                    RoundAction(AppIcons.cad("CANCEL"), if (depthPreview || finishPreview || planePreview) "Descartar preview" else "Descartar medidas", Ink.Bad, ::discardValues)
                    Spacer(Modifier.width(4.dp))
                    RoundAction(AppIcons.cad("FINISH"), if (planePreview) (if (cad.plane?.planeId != null) "Aplicar posición del plano" else "Crear el plano y su croquis")
                        else if (depthPreview || finishPreview) "Confirmar ${cadLabel(cad.operation)}" else "Aplicar medidas",
                        if (canAccept) Ink.Ok else Ink.Faint, { if (canAccept) acceptValues() })
                }
            }
        }
    }
    renamingSketch?.let { sketch ->
        var name by remember(sketch.id) { mutableStateOf(sketch.name) }
        AlertDialog(onDismissRequest = { renamingSketch = null }, title = { Text("Renombrar croquis") },
            text = { OutlinedTextField(name, { name = it.take(80) }, singleLine = true, label = { Text("Nombre") }) },
            confirmButton = { TextButton(enabled = connected && name.isNotBlank(), onClick = {
                command("cad.sketch.rename", "sketch_id" to sketch.id, "name" to name.trim()); renamingSketch = null
            }) { Text("Guardar") } },
            dismissButton = { TextButton(onClick = { renamingSketch = null }) { Text("Cancelar") } })
    }
}

/** Frequent sketch actions form their own group next to undo/redo. */
@Composable
fun CadSelectionActions(state: AppUiState, vm: MainViewModel) {
    val cad = state.blender.cad
    val enabled = state.connection == ConnectionStatus.CONNECTED && !cad.sessionActive && cad.surface.mode == "PROFILE"
    val entities = cad.activeSketch?.entities.orEmpty().filter { e -> cad.selection.any { it.id == e.id } }
    IconAction(AppIcons.cad("SELECT_ALL"), "Seleccionar todo el croquis", enabled = enabled && cad.selectionSketch?.entities?.isNotEmpty() == true) { vm.selectAll() }
    IconAction(AppIcons.cad("DESELECT_ALL"), "Deseleccionar todo", enabled = enabled && cad.selectionId != null) { vm.deselectAll() }
    if (cad.activeSketchId == null) return
    IconAction(AppIcons.cad("DELETE"), "Borrar selección", enabled = enabled && cad.selection.any { it.id != "ORIGIN" }) { vm.delete() }
    val construction = if (entities.isEmpty()) cad.construction else entities.all { it.construction }
    IconAction(AppIcons.cad("CONSTRUCTION"), if (entities.isEmpty()) "Dibujar construcción" else "Construcción de la selección",
        selected = construction, enabled = enabled) {
        vm.cadCommand(if (entities.isEmpty()) "cad.settings" else "cad.entity.construction", mapOf("construction" to !construction))
    }
    IconAction(AppIcons.cad("WELD"), "Soldar extremos en el último punto seleccionado", enabled = enabled && cadWeldEnabled(cad)) {
        vm.cadCommand("cad.points.weld")
    }
}

internal fun cadWeldEnabled(cad: CadState): Boolean = cad.selection.distinct().size >= 2 && cad.selection.all { ref ->
    val entity = cad.activeSketch?.entities?.firstOrNull { it.id == ref.id }
    when (entity?.type) {
        "LINE", "ARC" -> ref.part in listOf("START", "END")
        "RECTANGLE" -> ref.part in listOf("P0", "P1", "P2", "P3")
        else -> ref.id == "ORIGIN" && ref.part == "POINT"
    }
}

/** Contexto CAD en la fila del ojo junto a Deshacer/Rehacer, como Materiales: sin franja propia. */
@Composable
fun CadTopActions(state: AppUiState, vm: MainViewModel) {
    val cad = state.blender.cad
    val connected = state.connection == ConnectionStatus.CONNECTED
    val editing = cad.activeSketchId != null
    fun command(name: String, vararg values: Pair<String, Any?>) { if (connected) vm.cadCommand(name, mapOf(*values)) }
    if (editing) IconAction(Icons.Default.Straighten, "Medir desde el sólido", enabled = connected && !cad.sessionActive) { vm.cadSurfaceMode("EDGE") }
    else IconAction(Icons.Default.Layers, "Nuevo plano y croquis", enabled = connected && !cad.sessionActive) {
        command("cad.plane.begin", "base" to if (cad.surface.canSketch) "FACE" else if (cad.surface.canEdgePlane) "EDGE" else "XY")
    }
    if (editing) {
        if (state.blender.features.cad.sectionView) IconAction(AppIcons.cad("SECTION"),
            if (cad.section) "Quitar la sección" else "Vista en sección: corta la pieza por el plano del boceto",
            selected = cad.section, enabled = connected) { command("cad.settings", "section" to !cad.section) }
        val perspective = state.blender.view.perspective == Projection.PERSP
        IconAction(AppIcons.cad("PERSPECTIVE"), if (perspective) "Volver a vista ortográfica" else "Ver el boceto en perspectiva",
            selected = perspective, enabled = connected) { vm.viewPerspective(if (perspective) Projection.ORTHO else Projection.PERSP) }
        IconAction(Icons.AutoMirrored.Filled.RotateRight, "Girar la vista 90° sobre el plano",
            enabled = connected && !cad.sessionActive) { command("cad.view.roll", "degrees" to 90) }
        IconAction(Icons.Default.North, "Enderezar: de frente y sin girar",
            enabled = connected && !cad.sessionActive) { command("cad.view.align") }
        IconAction(AppIcons.cad("FINISH"), "Finalizar boceto", enabled = connected && !cad.sessionActive) {
            vm.cadTool(null); command("cad.sketch.finish")
        }
    } else {
        IconAction(Icons.Default.CenterFocusStrong, "Encuadrar la vista 3D del sólido",
            enabled = connected && !cad.sessionActive) {
            command("cad.view.solid")
        }
        cad.selectedSketch?.let { sketch ->
            IconAction(Icons.Default.Edit, "Editar ${sketch.name}", enabled = connected && !cad.sessionActive) {
                vm.cadTool(null); command("cad.sketch.activate", "sketch_id" to sketch.id)
            }
        }
    }
}


internal fun cadRefsTouch(a: CadSelection, b: CadSelection): Boolean {
    if (a.id != b.id) return false
    if (a.part == b.part || a.part == "BODY" || b.part == "BODY") return true
    fun roles(ref: CadSelection): Set<String> = if (ref.part.startsWith("EDGE")) {
        val i = ref.part.removePrefix("EDGE").toIntOrNull() ?: return emptySet()
        setOf("P$i", "P${(i + 1) % 4}")
    } else setOf(ref.part)
    return roles(a).intersect(roles(b)).isNotEmpty()
}

/** Other arcs selected with [entity]: tray values apply to all of them through equalities. */
internal fun cadOtherSelectedArcs(cad: CadState, entity: CadEntity): List<String> =
    if (entity.type != "ARC") emptyList() else cad.selection.map { it.id }.distinct()
        .filter { id -> id != entity.id && cad.activeSketch?.entities?.any { it.id == id && it.type == "ARC" } == true }

internal fun cadDisplayMeasures(entity: CadEntity, fullWidth: Boolean): List<CadMeasure> = entity.dimensions.map {
    if (fullWidth && it.field == "radius") when (entity.type) {
        "CIRCLE" -> it.copy(field = "diameter", label = "Diámetro", valueFactor = .5)
        "SLOT" -> it.copy(field = "width", label = "Ancho", valueFactor = .5)
        else -> it
    } else it
}

@Composable
private fun CadMirrorPlaneSelector(selected: String, enabled: Boolean, onSelect: (String) -> Unit) {
    listOf("XY" to "XY · horizontal", "XZ" to "XZ · frontal", "YZ" to "YZ · lateral").forEach { (plane, label) ->
        PillButton(label, selected = plane == selected, enabled = enabled) { onSelect(plane) }
    }
}

internal fun cadConstraintEnabled(cad: CadState, type: String): Boolean {
    val refs = cad.selection
    if (refs.isEmpty()) return false
    val entities = refs.map { ref -> if (ref.id == "ORIGIN") CadEntity("ORIGIN", "ORIGIN", emptyMap()) else cad.activeSketch?.entities?.firstOrNull { it.id == ref.id } ?: return false }
    fun point(i: Int) = refs[i].part in listOf("START", "END", "CENTER", "RIM", "P0", "P1", "P2", "P3", "POINT")
    fun line(i: Int) = (entities[i].type == "LINE" && refs[i].part == "BODY") || (entities[i].type in listOf("RECTANGLE", "NGON") && refs[i].part.startsWith("EDGE"))
    val points = refs.indices.all(::point)
    val lines = refs.indices.all(::line)
    val curves = entities.all { it.type in listOf("CIRCLE", "ARC") }
    return when (type) {
        "FIX" -> refs.none { it.id == "ORIGIN" }
        "COINCIDENT" -> refs.size == 2 && points
        "POINT_ON_LINE" -> cadPointOnLineEnabled(refs, entities)
        "MIDPOINT" -> refs.size == 2 && ((point(0) && line(1)) || (line(0) && point(1)))
        "SYMMETRIC" -> refs.size == 3 && points
        "SYMMETRIC_LINE" -> refs.size == 3 && point(0) && point(1) && line(2)
        "HORIZONTAL", "VERTICAL" -> lines
        "PARALLEL", "PERPENDICULAR" -> refs.size == 2 && lines
        "COLLINEAR" -> refs.size == 2 && refs.distinct().size == 2 && lines
        "EQUAL" -> if (curves) refs.map { it.id }.distinct().size >= 2 else refs.size >= 2 && lines
        "DISTANCE", "DISTANCE_X", "DISTANCE_Y" -> (refs.size == 1 && lines) || (refs.size == 2 && points)
        "RADIUS" -> refs.size == 1 && entities[0].type in listOf("CIRCLE", "ARC", "SLOT")
        "ANGLE" -> refs.size == 2 && refs.distinct().size == 2 && lines
        "TANGENT" -> refs.size == 2 && entities.any { it.type == "LINE" } && entities.any { it.type in listOf("CIRCLE", "ARC") }
        else -> false
    }
}

private fun cadPointOnLineEnabled(refs: List<CadSelection>, entities: List<CadEntity>): Boolean {
    if (refs.size != 2 || refs[0].id == refs[1].id) return false
    fun corner(part: String, prefix: String, count: Int): Boolean = part.startsWith(prefix) &&
        (part.removePrefix(prefix).toIntOrNull()?.let { it in 0 until count } == true)
    fun point(i: Int): Boolean {
        val part = refs[i].part
        return when (entities[i].type) {
            "ORIGIN", "POINT" -> part == "POINT"
            "LINE" -> part in listOf("START", "END")
            "CIRCLE" -> part in listOf("CENTER", "RIM")
            "ARC" -> part in listOf("CENTER", "START", "END")
            "RECTANGLE" -> corner(part, "P", 4)
            "NGON" -> part == "CENTER" || corner(part, "P", entities[i].values["sides"]?.toInt() ?: 6)
            "SLOT" -> part in listOf("CENTER", "START", "END", "SIDE")
            "GEAR" -> part == "CENTER"
            else -> false
        }
    }
    fun line(i: Int): Boolean = when (entities[i].type) {
        "LINE" -> refs[i].part == "BODY"
        "RECTANGLE" -> corner(refs[i].part, "EDGE", 4)
        "NGON" -> corner(refs[i].part, "EDGE", entities[i].values["sides"]?.toInt() ?: 6)
        "SLOT" -> refs[i].part == "AXIS"
        else -> false
    }
    return (point(0) && line(1)) || (line(0) && point(1))
}

/** Rail de restricciones por intención: posición, orientación, relación y cotas; lo no agrupado va al final. */
internal fun cadConstraintGroups(available: List<String>): List<List<String>> {
    val groups = listOf(
        listOf("COINCIDENT", "POINT_ON_LINE", "MIDPOINT", "FIX"),
        listOf("HORIZONTAL", "VERTICAL", "PARALLEL", "COLLINEAR", "PERPENDICULAR", "TANGENT"),
        listOf("EQUAL", "SYMMETRIC", "SYMMETRIC_LINE"),
        listOf("DISTANCE", "DISTANCE_X", "DISTANCE_Y", "RADIUS", "ANGLE"),
    )
    val rest = available.filter { type -> groups.none { type in it } }
    return (groups.map { group -> group.filter { it in available } } + listOf(rest)).filter { it.isNotEmpty() }
}

/** Medidas derivadas del módulo: el círculo primitivo engrana y el paso es π·m. */
private fun cadGearSummary(gear: CadEntity, unit: LengthUnit): String {
    val module = gear.values["module"] ?: return "Engranaje"
    val teeth = gear.values["teeth"] ?: 20.0
    val factor = when (unit) { LengthUnit.MILLIMETERS -> 1000.0; LengthUnit.CENTIMETERS -> 100.0; LengthUnit.METERS -> 1.0 }
    fun text(meters: Double) = formatToolDistance(meters * factor, detailDecimalPlaces(meters * factor, 2)) + " " + unit.short
    return "Engranaje · Ø primitivo ${text(module * teeth)} · Ø exterior ${text(module * (teeth + 2))} · paso ${text(Math.PI * module)} · " +
        "engrana con otro del mismo módulo y ángulo de presión"
}

private fun lengthFactor(unit: LengthUnit) = when (unit) { LengthUnit.MILLIMETERS -> 1000.0; LengthUnit.CENTIMETERS -> 100.0; LengthUnit.METERS -> 1.0 }

internal fun cadLabel(type: String) = when (type) {
    "POINT_ON_LINE" -> "Punto sobre recta"
    "OFFSET" -> "Desfase por grosor"
    "MIRROR" -> "Simetría de operación"
    "COLLINEAR" -> "Colineal (misma recta)"
    "RECTANGLE" -> "Rectángulo"; "NGON" -> "Polígono regular"; "SLOT" -> "Ranura"; "GEAR" -> "Engranaje"; "CIRCLE" -> "Círculo"; "LINE" -> "Línea"; "POINT" -> "Punto"; "ARC" -> "Arco"; "POLYGON" -> "Polígono"; "FILLET" -> "Redondeo"; "CHAMFER" -> "Chaflán"; "PROJECT" -> "Proyectar"
    "COINCIDENT" -> "Coincidente"; "HORIZONTAL" -> "Horizontal"; "VERTICAL" -> "Vertical"; "PARALLEL" -> "Paralela"; "PERPENDICULAR" -> "Perpendicular"
    "TANGENT" -> "Tangente"; "EQUAL" -> "Igualdad (tamaño del primero; en arcos también el ángulo, salvo redondeos)"; "EQUAL_ANGLE" -> "Igualdad de ángulo"; "DISTANCE" -> "Distancia diagonal / longitud"; "DISTANCE_X" -> "Distancia horizontal"; "DISTANCE_Y" -> "Distancia vertical"; "RADIUS" -> "Radio"; "ANGLE" -> "Ángulo"; "FIX" -> "Fijar selección"; "MIDPOINT" -> "Punto medio"; "SYMMETRIC" -> "Simetría (3 puntos; último = centro)"; "SYMMETRIC_LINE" -> "Simetría respecto a línea (2 puntos + eje)"
    "EXTRUDE" -> "Extruir"; "CUT" -> "Vaciar"; "LOFT" -> "Solevado"; "HELIX" -> "Barrido helicoidal"; "REVOLVE" -> "Revolución"; else -> type
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CadAction(intent: String, description: String, selected: Boolean = false, enabled: Boolean = true, onClick: () -> Unit) {
    TooltipBox(positionProvider = TooltipDefaults.rememberTooltipPositionProvider(TooltipAnchorPosition.Above),
        tooltip = { PlainTooltip { Text(description) } }, state = rememberTooltipState()) {
        IconAction(AppIcons.cad(intent), description, selected = selected, enabled = enabled,
            tint = if (AppIcons.cadMulticolor(intent)) Color.Unspecified else null, onClick = onClick)
    }
}

private class CadNodeAction(val label: String, val enabled: Boolean = true, val action: () -> Unit)

/** One node of the operation stack: tap shows the model as of that node; ⋮ opens its actions. */
@Composable
private fun CadStackNodeRow(icon: String, label: String, selected: Boolean, dimmed: Boolean, enabled: Boolean,
                            tap: () -> Unit, actions: List<CadNodeAction>) {
    var menuOpen by remember { mutableStateOf(false) }
    Box {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            Icon(AppIcons.cad(icon), null, tint = if (dimmed) Ink.Faint else Ink.Muted, modifier = Modifier.size(20.dp))
            PillButton(label, modifier = Modifier.weight(1f), selected = selected, enabled = enabled && !dimmed, onClick = tap)
            IconAction(Icons.Default.MoreVert, "Acciones del nodo", enabled = enabled && !dimmed) { menuOpen = true }
        }
        DropdownMenu(menuOpen, { menuOpen = false }) {
            actions.forEach { item ->
                DropdownMenuItem(text = { Text(item.label) }, enabled = enabled && item.enabled,
                    onClick = { menuOpen = false; item.action() })
            }
        }
    }
}

/** The rollback bar: everything below it is future history, hidden until advanced. */
@Composable
private fun CadRollbackBar() {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        HorizontalDivider(Modifier.weight(1f), thickness = 1.dp, color = Ink.Accent.copy(alpha = .6f))
        Text("la vista llega aquí", color = Ink.Accent, fontSize = 10.sp)
        HorizontalDivider(Modifier.weight(1f), thickness = 1.dp, color = Ink.Accent.copy(alpha = .6f))
    }
}

/** Same compact fields and accelerating buttons as Edit; CAD wire values are metres. */
@Composable
private fun CadDimension(
    label: String, meters: Double, unit: LengthUnit, identity: String,
    step: Double, enabled: Boolean, degrees: Boolean = false, readOnly: Boolean = false,
    minimum: Double = -10000.0, maximum: Double = 10000.0,
    onNudge: ((Double) -> Unit)? = null,
    onDone: () -> Unit,
    onDraft: (Double?) -> Unit,
) {
    val factor = if (degrees) 1.0 else when (unit) { LengthUnit.MILLIMETERS -> 1000.0; LengthUnit.CENTIMETERS -> 100.0; LengthUnit.METERS -> 1.0 }
    val input = remember(identity, factor) { CadNumberDraft() }
    SideEffect { input.acknowledge(meters) }
    val value = input.read(meters, factor, minimum, maximum)
    fun nudge(direction: Int) {
        val next = input.nudge(meters, factor, step, direction, minimum, maximum) ?: return
        if (onNudge != null) onNudge(next) else onDraft(next)
    }
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(label, color = Ink.Faint, fontSize = 11.sp)
        StepperButton("−", enabled && !readOnly && value != null && value > minimum) { nudge(-1) }
        val displayed = (input.pending ?: meters) * factor
        if (readOnly) Box(Modifier.width(84.dp).height(34.dp).padding(horizontal = 6.dp), contentAlignment = Alignment.CenterEnd) {
            val live = meters * factor
            Text(formatToolDistance(live, detailDecimalPlaces(live, if (degrees || unit == LengthUnit.MILLIMETERS) 2 else 4)),
                color = Ink.OnPanel, fontSize = 13.sp, maxLines = 1)
        } else CompactNumericField(value = input.text ?: formatToolDistance(displayed, detailDecimalPlaces(displayed, if (degrees || unit == LengthUnit.MILLIMETERS) 2 else 4)),
            onValueChange = { if (enabled) { input.text = it; onDraft(input.read(meters, factor, minimum, maximum)) } },
            modifier = Modifier.width(84.dp), textAlign = TextAlign.End, placeholder = if (degrees) "°" else unit.short,
            textColor = if (value == null) Ink.Bad else if (enabled) Ink.OnPanel else Ink.Faint, selectAllOnFocus = true,
            onDone = { if (enabled && value != null) { input.pending = value; input.text = null; onDone() } })
        Text(if (degrees) "°" else unit.short, color = Ink.Muted, fontSize = 12.sp)
        StepperButton("+", enabled && !readOnly && value != null && value < maximum) { nudge(1) }
    }
}


@Composable
private fun CadConstraintRow(c: CadConstraint, sketch: CadSketch, unit: LengthUnit, enabled: Boolean, edit: () -> Unit, delete: () -> Unit) {
    val factor = when (unit) { LengthUnit.MILLIMETERS -> 1000.0; LengthUnit.CENTIMETERS -> 100.0; LengthUnit.METERS -> 1.0 }
    val value = c.value?.let { if (c.type == "ANGLE") " · ${formatToolDistance(it, 2)}°"
        else " · ${formatToolDistance(it * factor, detailDecimalPlaces(it * factor, 2))} ${unit.short}" }.orEmpty()
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        Column(Modifier.weight(1f)) {
            Text(cadLabel(c.type) + value, color = Ink.OnPanel, fontSize = 12.sp)
            Text(c.refs.joinToString(" ↔ ") { ref ->
                if (ref.id == "ORIGIN") "Origen" else "Figura ${sketch.entities.indexOfFirst { it.id == ref.id } + 1} · ${cadPartLabel(ref.part)}"
            }, color = Ink.Faint, fontSize = 11.sp)
        }
        if (c.value != null) PillButton("Editar", enabled = enabled, onClick = edit)
        CadAction("DELETE", if (c.value != null) "Quitar cota · conserva el dibujo" else "Quitar restricción", enabled = enabled, onClick = delete)
    }
}

private fun cadPartLabel(part: String) = when (part) {
    "BODY" -> "completa"; "START" -> "inicio"; "END" -> "final"; "CENTER" -> "centro"; "RIM" -> "radio"
    else -> if (part.startsWith("EDGE")) "lado ${part.removePrefix("EDGE").toIntOrNull()?.plus(1)}" else part
}

internal fun cadPlaneLabel(plane: String) = when (plane) {
    "XY" -> "Superior (XY)"; "XZ" -> "Frontal (XZ)"; "YZ" -> "Lateral (YZ)"; else -> plane
}

/**
 * Axis names of a plane in world terms. Translation/rotation are stored in the
 * plane's local frame (x, y, normal); base planes map those to world axes.
 * Planes framed by a face or another sketch have no fixed world axes.
 */
internal data class CadPlaneAxes(val inPlane: List<String>, val rotation: List<String>, val positive: String, val negative: String)

internal fun cadPlaneAxes(base: String?): CadPlaneAxes = when (base) {
    "XY" -> CadPlaneAxes(listOf("X", "Y"), listOf("X", "Y", "Z"), "hacia arriba (+Z)", "hacia abajo (−Z)")
    "XZ" -> CadPlaneAxes(listOf("X", "Z"), listOf("X", "Z", "−Y"), "hacia delante (−Y)", "hacia atrás (+Y)")
    "YZ" -> CadPlaneAxes(listOf("Y", "Z"), listOf("Y", "Z", "X"), "hacia la derecha (+X)", "hacia la izquierda (−X)")
    "EDGE" -> CadPlaneAxes(listOf("a lo largo", "transversal"), listOf("sobre la arista", "transversal", "normal"), "hacia fuera", "hacia dentro")
    else -> CadPlaneAxes(listOf("U", "V"), listOf("U", "V", "normal"), "hacia fuera de la cara", "hacia dentro")
}

@Composable
private fun CadSurfaceControls(cad: CadState, unit: LengthUnit, enabled: Boolean, vm: MainViewModel) {
    if (cad.surface.mode != "PROFILE") PillButton("Ver escena", selected = cad.showScene, enabled = enabled) { vm.cadCommand("cad.settings", mapOf("show_scene" to !cad.showScene)) }
    val edges = cad.surface.selection.isNotEmpty() && cad.surface.selection.all { it.kind == "EDGE" }
    if (cad.activeSketchId != null && cad.surface.selection.isNotEmpty()) {
        Text("${cad.surface.selection.size} referencias seleccionadas", color = Ink.Accent, fontSize = 11.sp)
        PillButton("Limpiar", enabled = enabled) { vm.cadCommand("cad.surface.clear") }
    } else if (cad.surface.selection.size > 2 && edges) {
        Text("${cad.surface.selection.size} aristas · ${cad.surface.selection.first().objectName}", color = Ink.Accent, fontSize = 11.sp)
        PillButton("Limpiar", enabled = enabled) { vm.cadCommand("cad.surface.clear") }
    } else if (cad.surface.selection.isNotEmpty()) {
        cad.surface.selection.forEachIndexed { index,item ->
            Text("${index+1} · ${if (index == 0) "Azul" else "Naranja"} · ${item.objectName}", color = if (index == 0) Ink.Accent else Ink.Warn, fontSize = 11.sp)
        }
        PillButton("Limpiar", enabled = enabled) { vm.cadCommand("cad.surface.clear") }
    }
    if (cad.activeSketchId == null && edges) {
        // Varias aristas del sólido se redondean o achaflanan de una vez, como un paso de la pila.
        CadAction("FILLET", "Redondear aristas", enabled = enabled) { vm.cadCommand("cad.finish.begin", mapOf("operation" to "FILLET")) }
        CadAction("CHAMFER", "Chaflán en aristas", enabled = enabled) { vm.cadCommand("cad.finish.begin", mapOf("operation" to "CHAMFER")) }
    }
    if (cad.activeSketchId != null && cad.surface.selection.isNotEmpty()) {
        PillButton("Proyectar al plano (${cad.surface.selection.size})", enabled = enabled) { vm.cadCommand("cad.reference.project") }
    }
    val factor = when (unit) { LengthUnit.MILLIMETERS -> 1000.0; LengthUnit.CENTIMETERS -> 100.0; LengthUnit.METERS -> 1.0 }
    cad.surface.measurements.forEach { measurement ->
        val scale = when (measurement.unit) { "AREA" -> factor * factor; "ANGLE" -> 1.0; else -> factor }
        val suffix = when (measurement.unit) { "AREA" -> unit.short + "²"; "ANGLE" -> "°"; else -> unit.short }
        Text("${measurement.label}: ${formatToolDistance(measurement.value * scale, detailDecimalPlaces(measurement.value * scale, 3))} $suffix", color = Ink.OnPanel, fontSize = 12.sp)
    }
}


/** Número de lados de un polígono regular: 6 hace tuercas y sus alojamientos. */
@Composable
private fun CadSidesControl(sides: Int, enabled: Boolean, onChange: (Int) -> Unit) =
    CadCountControl("Lados", sides, 3..32, enabled, onChange)

/** Cantidad discreta (lados, segmentos) con −/+ compartidos; nunca usa unidades. */
@Composable
private fun CadCountControl(label: String, value: Int, range: IntRange, enabled: Boolean, onChange: (Int) -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(label, color = Ink.Muted, fontSize = 12.sp)
        StepperButton("−", enabled && value > range.first) { onChange(value - 1) }
        Text("$value", fontSize = 14.sp)
        StepperButton("+", enabled && value < range.last) { onChange(value + 1) }
    }
}
