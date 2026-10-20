package com.blendertablet.remote.ui

import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
import androidx.compose.foundation.horizontalScroll
import androidx.compose.ui.draw.clip
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.clickable
import androidx.compose.foundation.border
import androidx.compose.foundation.background
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.*
import com.blendertablet.remote.model.Constraint
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
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
    LaunchedEffect(cad.sketchReview, cad.sketchFailure?.featureId) {
        if (cad.sketchReview) onStackOpen(true)
    }
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
    // Barrido: the profile waits for the path sketch, tapped in the stack. A path
    // has no closed profile, so the tap creates the sweep instead of selecting it.
    var sweepFrom by remember(cad.activeSketchId) { mutableStateOf<Pair<String, String>?>(null) }
    var editingConstraint by remember(cad.activeSketchId) { mutableStateOf<CadConstraint?>(null) }
    LaunchedEffect(cad.selectionKind, cad.selectionId, cad.revision) {
        editingConstraint = cad.selectedConstraint
        if (editingConstraint != null) pendingDimension = null
    }
    // Rollback bar position over the full stack; body filtering keeps the order.
    val barPos = cad.rollbackId?.let { id -> cad.history.indexOfFirst { it.id == id } }?.takeIf { it >= 0 }
    fun behindBar(nodeId: String) = barPos != null && cad.history.indexOfFirst { it.id == nodeId } > barPos
    var cutTarget by remember(cad.documentId) { mutableStateOf<String?>(null) }
    val operatedTargets = cad.features.filter { it.enabled && !behindBar(it.id) }.groupBy { it.bodyId }.values.map { body ->
        body.maxBy { feature -> cad.history.indexOfFirst { it.id == feature.id } }
    }
    val targets = operatedTargets + cad.bodies.filter { body -> operatedTargets.none { it.bodyId == body.id } }.mapNotNull { body ->
        cad.features.firstOrNull { it.id == body.sourceFeatureId && it.enabled && !behindBar(it.id) }?.copy(bodyId = body.id, name = body.name)
    }
    LaunchedEffect(cad.selectedFeature?.id) { cad.selectedFeature?.let { cutTarget = it.bodyId } }
    LaunchedEffect(cad.selectedSketch?.bodyId) {
        cad.bodies.firstOrNull { it.id == cad.selectedSketch?.bodyId && it.sourceFeatureId != null }?.let { cutTarget = it.id }
    }
    val target = targets.firstOrNull { it.bodyId == cutTarget } ?: targets.singleOrNull()
    val editing = cad.activeSketchId != null
    val selectedSketch = cad.selectedSketch
    val cutSelection = cadCutSelection(cad)
    val shownProfiles = cadShownProfiles(cad)
    val multipleProfiles = shownProfiles.size > 1
    val selectionTarget = targets.firstOrNull { it.bodyId == cad.activeSketch?.bodyId }
    val bodyHistory = cad.history.filter { cad.activeBodyId == null || it.bodyId == cad.activeBodyId }
    val lastNode = bodyHistory.lastOrNull()
    val viewIndex = if (barPos == null) bodyHistory.size
        else bodyHistory.count { node -> !behindBar(node.id) }
    LaunchedEffect(lastNode?.id, cad.activeSketch?.entities?.lastOrNull()?.id, editing, constraintsVisible) {
        if (!cad.sketchReview && (!editing || !constraintsVisible)) {
            withFrameNanos { }; withFrameNanos { }
            historyScroll.scrollTo(historyScroll.maxValue)
        }
    }
    val depthPreview = cad.sessionActive && cad.operation in listOf("EXTRUDE", "CUT")
    val dragPreview = cad.sessionActive && cad.operation == "DRAG"
    // Dibujar muestra las mismas medidas en vivo que arrastrar; se editan al soltar.
    val drawPreview = cad.sessionActive && cad.operation in listOf("LINE", "RECTANGLE", "CIRCLE", "ARC")
    val livePreview = dragPreview || drawPreview
    val dynamicPreview = cad.sessionActive && cad.operationControls != null
    val shellPreview = cad.sessionActive && cad.operation == "SHELL"
    val finishPreview = cad.sessionActive && cad.operation in listOf("FILLET", "CHAMFER")
    // Colocar un plano: el rail elige la base y la bandeja sus medidas, con preview en la vista.
    val planePreview = cad.sessionActive && cad.operation in listOf("PLANE", "SPLIT")
    val availableHeight = (LocalConfiguration.current.screenHeightDp - 260).coerceAtLeast(100).dp
    fun command(name: String, vararg values: Pair<String, Any?>) { if (connected) vm.cadCommand(name, mapOf(*values)) }
    fun beginFeature(operation: String) {
        vm.cadTool(null)
        if (operation == "CUT" && multipleProfiles) {
            command("cad.extrude.begin", "profile_ids" to shownProfiles, "depth" to cad.step * 10,
                "operation" to operation, "target_id" to target?.id, "target_body_id" to target?.bodyId)
            return
        }
        command("cad.extrude.begin", "profile_id" to cad.selectionId.takeIf { cad.selectionKind == "PROFILE" },
            "sketch_id" to cad.selectionId.takeIf { cad.selectionKind == "SKETCH" }, "depth" to cad.step * 10,
            "operation" to operation, "target_id" to target?.id, "target_body_id" to target?.bodyId)
    }
    if (planePreview) ToolRail(Modifier.align(Alignment.CenterStart).padding(start = Metrics.EdgeMargin).heightIn(max = availableHeight)) {
        RailLabel("CROQUIS")
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
    } else ToolRail(Modifier.align(Alignment.CenterStart).padding(start = Metrics.EdgeMargin).heightIn(max = availableHeight)) {
        RailLabel(if (editing) "CROQUIS" else "OPERACIONES")
        CadToolContext(state, vm)
        if (!editing) {
            cad.selectedSketch?.let { sketch ->
                if ("HOLE" in capabilities.features && sketch.entities.any { it.type in listOf("POINT", "CIRCLE") })
                    CadAction("HOLE", "Taladro métrico", enabled = connected && !cad.sessionActive) { command("cad.hole.begin", "sketch_id" to sketch.id) }
            }
            cad.selectedFeature?.let { selected ->
                if ("PATTERN" in capabilities.features && selected.type in listOf("EXTRUDE", "CUT", "HOLE"))
                    CadAction("PATTERN", "Patrón", enabled = connected && !cad.sessionActive && selected.enabled) {
                        command("cad.pattern.begin", "source_ids" to listOf(selected.id))
                    }
                if (capabilities.featureMirror && selected.type in listOf("EXTRUDE", "CUT") && !selected.isMirror)
                    CadAction("MIRROR", "Simetría de operación", enabled = connected && !cad.sessionActive && selected.enabled) {
                        vm.cadTool(null); mirrorSource = selected; mirrorPlane = "XZ"; pendingDimension = null; editingConstraint = null
                    }
            }
        }
        if (editing) {
            RailDivider()
            capabilities.entities.forEach { type ->
                CadAction(type, cadLabel(type), selected = state.cadTool == type, enabled = !cad.sessionActive || cad.operation == type) { vm.cadTool(type) }
                // Subdividir creates a point too: it lives right below Punto.
                if (type == "POINT" && capabilities.midpointPoints) CadAction("SUBDIVIDE",
                    "Subdividir: crear punto medio de una arista o entre dos puntos",
                    enabled = connected && !cad.sessionActive && cad.surface.mode == "PROFILE" && cadMidpointCreationEnabled(cad)) {
                    vm.cadTool(null)
                    command("cad.points.midpoint")
                }
            }
            if (capabilities.sketchEditing) CadAction("FILLET", "Redondear esquinas seleccionadas", selected = pendingDimension == "FILLET",
                enabled = !cad.sessionActive && cad.selection.any { it.id != "ORIGIN" }) { pendingDimension = "FILLET" }
            if (capabilities.entityTrim) CadAction("TRIM", "Recortar tramo entre intersecciones", selected = state.cadTool == "TRIM",
                enabled = connected && (!cad.sessionActive || cad.operation == "TRIM")) { vm.cadTool(if (state.cadTool == "TRIM") null else "TRIM") }
            if (capabilities.offsetEntities.isNotEmpty()) {
                val source = cadOffsetSource(cad, capabilities.offsetEntities)
                CadAction("OFFSET", if (source != null) "Desfase por grosor: contorno concéntrico vinculado"
                    else "Desfase: selecciona un círculo, rectángulo o ranura", selected = offsetSource != null,
                    enabled = connected && !cad.sessionActive && (offsetSource != null || source != null)) {
                    if (offsetSource != null) offsetSource = null
                    else { vm.cadTool(null); offsetSource = source; offsetSide = "OUTWARD"; pendingDimension = null; editingConstraint = null }
                }
            }
            if (capabilities.sketchEditing) CadAction("PROJECT", "Proyectar punto, arista o cara al plano del croquis",
                selected = cad.surface.mode != "PROFILE", enabled = !cad.sessionActive) {
                if (cad.surface.mode != "PROFILE" && cad.surface.selection.isNotEmpty()) command("cad.reference.project")
                else vm.cadSurfaceMode(if (cad.surface.mode != "PROFILE") "PROFILE" else "EDGE")
            }
            if (capabilities.selectedCut && "CUT" in capabilities.features) {
                RailDivider()
                CadAction("CUT", "Vaciar selección (${cutSelection.size})",
                    enabled = connected && !cad.sessionActive && cutSelection.isNotEmpty() && selectionTarget != null) {
                    vm.cadTool(null)
                    command("cad.extrude.begin", "operation" to "CUT", "sketch_id" to cad.activeSketchId,
                        "entity_ids" to cutSelection, "depth" to cad.step * 10,
                        "target_id" to selectionTarget?.id, "target_body_id" to selectionTarget?.bodyId)
                }
            }
        } else {
            RailDivider()
            if ("LOFT" in capabilities.features) CadAction("LOFT", "Solevado: une este perfil con el de otro croquis", selected = loftFrom != null,
                enabled = connected && !cad.sessionActive && !multipleProfiles && (loftFrom != null || cad.selectionKind in listOf("PROFILE", "SKETCH"))) {
                loftFrom = if (loftFrom != null) null else cad.selectionKind!! to cad.selectionId!!
            }
            if ("SWEEP" in capabilities.features) CadAction("SWEEP", "Barrido: lleva este perfil por las líneas y arcos de otro croquis", selected = sweepFrom != null,
                enabled = connected && !cad.sessionActive && !multipleProfiles && (sweepFrom != null || cad.selectionKind in listOf("PROFILE", "SKETCH"))) {
                sweepFrom = if (sweepFrom != null) null else cad.selectionKind!! to cad.selectionId!!
                if (sweepFrom != null) onStackOpen(true)
            }
            if ("REVOLVE" in capabilities.features) CadAction("REVOLVE", "Revolución: gira el perfil alrededor de un eje del croquis (puede apoyarse en él)",
                enabled = connected && !cad.sessionActive && !multipleProfiles && cad.selectionKind in listOf("PROFILE", "SKETCH")) {
                command("cad.revolve.create", (if (cad.selectionKind == "SKETCH") "sketch_id" else "profile_id") to cad.selectionId)
            }
            if ("HELIX" in capabilities.features) CadAction("HELIX", "Barrido helicoidal del perfil alrededor de un eje del croquis",
                enabled = connected && !cad.sessionActive && !multipleProfiles && cad.selectionKind in listOf("PROFILE", "SKETCH")) {
                command("cad.helix.create", (if (cad.selectionKind == "SKETCH") "sketch_id" else "profile_id") to cad.selectionId)
            }
            capabilities.features.filter { it in listOf("EXTRUDE", "CUT") }.forEach { operation ->
                CadAction(operation, if (operation == "CUT" && multipleProfiles) "Vaciar selección (${shownProfiles.size})" else cadLabel(operation), selected = depthPreview && cad.operation == operation,
                    enabled = connected && !cad.sessionActive && cad.selectionKind in listOf("PROFILE", "SKETCH") && (operation != "CUT" || target != null) && (!multipleProfiles || operation == "CUT" && capabilities.profileMultiselect)) { beginFeature(operation) }
            }
        }
    }
    if (editing && capabilities.constraints.isNotEmpty()) ToolRail(
        Modifier.align(Alignment.CenterEnd).padding(end = Metrics.EdgeMargin, top = 142.dp, bottom = 180.dp)
            .heightIn(max = availableHeight)
    ) {
        RailLabel("SELECCIÓN")
        SelectionIntentControls(state, vm)
        IconAction(AppIcons.action(if (cad.selectionId != null) ActionId.DESELECT_ALL else ActionId.SELECT_ALL),
            if (cad.selectionId != null) "Deseleccionar todo" else "Seleccionar todo") {
            if (cad.selectionId != null) vm.deselectAll() else vm.selectAll()
        }
        IconAction(AppIcons.action(ActionId.SELECT_INVERT), "Invertir selección", onClick = vm::invertSelection)
        RailDivider()
        RailLabel("RESTRICCIONES")
        cadConstraintGroups(capabilities.constraints).forEachIndexed { index, group ->
            if (index > 0) RailDivider()
            group.forEach { type ->
                CadAction(type, cadLabel(type), enabled = connected && !cad.sessionActive && cadConstraintEnabled(cad, type)) {
                    command("cad.constraint.add", "type" to type)
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
    // igual que él. Las operaciones viven en el rail izquierdo y la vista en el pie.
    val stackEnd = Metrics.EdgeMargin + if (!editing || capabilities.constraints.isNotEmpty()) Metrics.HelperRailInset else 0.dp
    if (!stackOpen) FloatingPanel(
        Modifier.align(Alignment.TopEnd).padding(top = 142.dp, end = stackEnd),
    ) {
        IconAction(AppIcons.cad("MODEL"), "Abrir pila de operaciones") { onStackOpen(true) }
    }
    if (stackOpen) FloatingPanel(
        Modifier.align(Alignment.TopEnd).fillMaxHeight().padding(top = 142.dp, end = stackEnd, bottom = stackBottom)
    ) {
        Column(Modifier.width(300.dp).fillMaxHeight()) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                IconAction(AppIcons.Back, "Cerrar pila de operaciones") { onStackOpen(false) }
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
                            if ("SPLIT" in capabilities.features) DropdownMenuItem(text = { Text("Partir por plano") },
                                leadingIcon = { Icon(AppIcons.cad("SPLIT"), null) },
                                enabled = connected && !cad.sessionActive,
                                onClick = { bodiesOpen = false; command("cad.plane.begin", "split_body_id" to cad.activeBodyId) })
                            if ("COMBINE" in capabilities.features) DropdownMenuItem(text = { Text("Combinar con otro cuerpo") },
                                enabled = connected && !cad.sessionActive && cad.bodies.size > 1,
                                onClick = { bodiesOpen = false; vm.cadPickParameter("pick_tool_body", "COMBINE:" + cad.activeBodyId) })
                            DropdownMenuItem(text = { Text("Nuevo cuerpo") }, onClick = { bodiesOpen = false; command("cad.body.create") })
                        }
                    }
                    cad.kernel?.let { Text("Motor · $it", color = Ink.Muted, fontSize = 12.sp) }
                    bodyHistory.forEachIndexed { index, node ->
                        if (barPos != null && index == viewIndex) CadRollbackBar()
                        val dimmed = behindBar(node.id)
                        val nodeEnabled = connected && !cad.sessionActive
                        if (node.kind == "SKETCH") {
                            val sketch = cad.sketches.firstOrNull { it.id == node.id }
                            if (sketch != null) {
                                CadStackNodeRow("SKETCH", sketch.name, selectedSketch?.id == sketch.id, dimmed, nodeEnabled,
                                    tap = {
                                        val from = sweepFrom
                                        if (from != null && sketch.id != from.second) {
                                            sweepFrom = null
                                            command("cad.sweep.create", (if (from.first == "SKETCH") "sketch_id" else "profile_id") to from.second,
                                                "path_sketch_id" to sketch.id)
                                        } else command("cad.history.rollback", "node_id" to node.id)
                                    },
                                    )
                            }
                        } else {
                            val feature = cad.features.firstOrNull { it.id == node.id }
                            if (feature != null) {
                                CadStackNodeRow(feature.type, feature.name + if (!feature.enabled) " · desactivada" else "",
                                    cad.selectedFeature?.id == feature.id, dimmed, nodeEnabled,
                                    reveal = cad.sketchReview && cad.sketchFailure?.featureId == feature.id,
                                    tap = { command("cad.history.rollback", "node_id" to node.id) },
                                    )
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
                    Text(if (cad.sketchReview) "Fallo en este paso" else if (barPos == null) "Modelo completo" else "Hasta ${bodyHistory.getOrNull(viewIndex - 1)?.name.orEmpty()}",
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
    fun sendPlane(offset: Double? = null, tilt: List<Double>? = null, shift: List<Double>? = null) {
        val plane = cad.plane ?: return
        drafts.keys.filter { it.startsWith("plane_") }.forEach { drafts.remove(it) }
        command("cad.plane.update", "offset" to (offset ?: plane.offset), "tilt" to (tilt ?: plane.tilt), "shift" to (shift ?: plane.shift))
    }
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
            dynamicPreview -> {
                if (planePreview) pushPlane()
                if (drafts.isNotEmpty()) command("cad.operation.update", *drafts.map { it.key to it.value }.toTypedArray())
                drafts.clear()
                command("cad.session.confirm")
            }
            cad.operationControls != null && feature != null -> {
                command("cad.feature.set", "feature_id" to feature.id, *drafts.map { it.key to it.value }.toTypedArray())
                drafts.clear()
            }
            planePreview -> {
                if (drafts.keys.any { it.startsWith("plane_") }) pushPlane()
                command("cad.session.confirm")
            }
            depthPreview -> {
                drafts["depth"]?.let { command("cad.extrude.update", "depth" to it) }
                if (cad.canConfirm) command("cad.session.confirm")
            }
            shellPreview -> {
                val thickness = drafts["thickness"]
                if (thickness != null) {
                    drafts.remove("thickness")
                    command("cad.shell.update", "thickness" to thickness)
                } else if (cad.canConfirm) command("cad.session.confirm")
            }
            finishPreview -> {
                val width = drafts["width"]
                if (width != null) {
                    drafts.remove("width")
                    command("cad.finish.update", "width" to width)
                } else if (cad.canConfirm) command("cad.session.confirm")
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
            feature?.type == "SHELL" && drafts["thickness"] != null -> command("cad.feature.set", "feature_id" to feature.id, "thickness" to drafts["thickness"])
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
        if (depthPreview || finishPreview || shellPreview || dynamicPreview || planePreview) command("cad.session.cancel")
        if (cad.selectionKind == "CONSTRAINT") command("cad.select_all", "action" to "DESELECT")
        pendingDimension = null; editingConstraint = null; offsetSource = null; mirrorSource = null; resetInputs++
    }
    val canAccept = connected && validDrafts && when {
        dynamicPreview -> cad.canConfirm || drafts.isNotEmpty()
        depthPreview -> cad.canConfirm
        shellPreview -> cad.canConfirm || drafts["thickness"] != null
        finishPreview -> cad.canConfirm || drafts["width"] != null
        planePreview -> true
        pendingDimension != null -> true
        offsetSource != null || mirrorSource != null -> true
        else -> drafts.isNotEmpty()
    }
    val hasValues = depthPreview || finishPreview || shellPreview || dynamicPreview || planePreview || pendingDimension != null || editingConstraint != null || entity != null || feature != null || offsetPlane != null || offsetSource != null || mirrorSource != null
    val arcSelectionHelp = entity?.let { selected ->
        val otherArcs = cadOtherSelectedArcs(cad, selected)
        if (otherArcs.isEmpty()) null else {
            val roundings = selected.isFillet || cad.activeSketch?.entities.orEmpty().any { it.id in otherArcs && it.isFillet }
            "${otherArcs.size + 1} arcos: " + if (roundings) "Radio se aplica a todos (Igualdad)" else "Radio y Ángulo se aplican a todos (Igualdad)"
        }
    }
    val help = cad.error ?: when {
        !connected -> "Reconectando · recuperando el documento de Blender"
        state.cadParameterPick != null -> if (state.cadParameterPick == "pick_tool_body") "Toca la pieza que se usará como herramienta" else "Toca la referencia en la pieza para fijar la dirección o el eje"
        cad.operationControls != null -> cad.operationControls.label + " · ajusta los parámetros · ✓ confirma · × cancela"
        planePreview -> cad.plane?.let { plane ->
            (if (plane.planeId != null) "Colocar plano guardado" else "Plano ${if (plane.base == "FACE") "en la cara" else cadPlaneLabel(plane.base)}") +
                " · arrastra las flechas: roja/verde lo deslizan, azul (o fuera de ellas) lo separa · positivo: ${plane.positiveLabel.lowercase()} · ✓ " +
                (if (plane.planeId != null) "aplica la posición" else "crea el croquis")
        } ?: "Colocando plano"
        editing && cad.sketchPending -> "Pieza pendiente de actualizar · pulsa Finalizar boceto al terminar"
        editing && !cad.sessionActive && capabilities.selectedCut && cutSelection.isNotEmpty() -> "${cutSelection.size} elementos seleccionados · Vaciar utiliza solo estos contornos"
        offsetSource != null -> "Desfase vinculado: elige dentro o fuera y escribe el grosor · ✓ crea el contorno"
        mirrorSource != null -> "Simetría de ${mirrorSource!!.name}: elige el plano y su posición · ✓ crea la operación vinculada"
        feature?.isMirror == true -> "${feature.name} · perfil y profundidad siguen a la operación fuente"
        editingConstraint != null -> "${cadLabel(editingConstraint!!.type)} · escribe el valor · arrastra la cota para colocarla sin mover el dibujo"
        sweepFrom != null -> "Barrido: elige en la pila el croquis del recorrido (una cadena abierta de líneas y arcos) · vuelve a pulsar Barrido para cancelar"
        feature?.type == "SWEEP" -> "${feature.name} · el perfil recorre las líneas y arcos del otro croquis · editarlo actualiza el barrido"
        loftFrom != null -> "Solevado: toca el perfil del otro croquis (o elígelo en la pila) · vuelve a pulsar Solevado para cancelar"
        feature?.type == "REVOLVE" -> "${feature.name} · el perfil gira alrededor del eje elegido; puede apoyarse en él (conos, cúpulas) pero no cruzarlo"
        feature?.type == "HELIX" -> "${feature.name} · altura ${formatToolDistance(feature.pitch * feature.turns * lengthFactor(unit), 2)} ${unit.short} · el paso debe superar la altura del perfil · el eje es X, Y o una línea del croquis"
        feature?.type == "LOFT" -> "${feature.name} · une ${cad.sketches.firstOrNull { it.id == feature.sketchId }?.name.orEmpty()} con otro croquis · mover su plano lo actualiza"
        state.cadFacePick != null -> "Hasta cara: toca la cara plana donde termina · su plano corta la extrusión, también inclinado · vuelve a pulsar para cancelar"
        pendingDimension == "FILLET" -> "Redondeo: varias esquinas, el rectángulo entero o líneas unidas · un radio para todas · tras el primero, toca otra esquina"
        drafts.isNotEmpty() && !depthPreview -> "Medidas pendientes · ✓ aplica los cambios · × descarta"
        depthPreview && cad.extent == "THROUGH_ALL" -> "Perforar todo · atraviesa el cuerpo completo · se adapta si cambia el grosor · dos dedos navegan"
        depthPreview -> if (cad.operation == "EXTRUDE")
            "Extrusión · Simetría crece a los dos lados del croquis · si no, desliza en el sentido del plano · suelta para asentar"
        else "${cadLabel(cad.operation)} · desliza en el sentido del vaciado" +
            " · una dirección o las dos · dos dedos navegan" + if (cad.transparent) " · transparencia automática" else ""
        shellPreview -> "Carcasa · ${cad.faceCount} caras abiertas · arrastra o escribe el grosor · ✓ lo añade a la pila"
        feature?.type == "SHELL" -> "Carcasa · ${feature.faceCount} caras abiertas · las paredes siguen al sólido anterior"
        finishPreview -> "${cadLabel(cad.operation)} · desliza arriba/abajo o escribe el ancho · ✓ lo añade a la pila"
        dragPreview -> "Medidas en vivo · suelta para fijar una medida con su candado"
        drawPreview -> "Medidas en vivo · Incremento redondea al paso y los puntos existentes atraen · suelta para editar las medidas"
        cad.sessionActive && cad.operation == "POLYGON" -> "Polígono: traza o toca cada vértice · cierra tocando el primer punto o con Cerrar · dos dedos descarta"
        editing && cad.surface.mode != "PROFILE" -> "Toca para añadir referencias; tocar de nuevo las quita · puedes combinar Puntos/Aristas/Caras · Proyectar al plano copia toda la selección al croquis"
        cad.surface.mode == "FACE" -> if (cad.surface.selection.size > 1) "Dos referencias para medir · quita una cara seleccionada para crear el boceto" else "Toca una cara: se resalta en el vídeo · Boceto en cara usa exactamente esa selección"
        cad.surface.mode != "PROFILE" -> "Toca hasta dos referencias para medir · durante el boceto puedes proyectarlas para acotar desde ellas"
        editing && state.cadTool == "ARC" -> "Arrastra centro → inicio del arco · sigue en Arco para el siguiente · arrastra un rombo para variar su ángulo"
        editing && state.cadTool == "POINT" -> "Toca para crear un punto de referencia · Cursor permite elegirlo junto a una arista para Punto medio"
        entity?.type == "ARC" && !entity.isFillet -> "Arrastra el rombo del extremo para variar el ángulo; centro, radio e inicio permanecen fijos"
        editing && state.cadTool == "NGON" -> "Polígono regular: arrastra del centro a un vértice · elige los lados antes o después · Entre caras es la llave de la tuerca"
        editing && state.cadTool == "SLOT" -> "Ranura: arrastra entre los centros de los extremos · Radio es la mitad del Ancho · Entre centros conserva la longitud recta"
        editing && state.cadTool == "GEAR" -> "Engranaje: arrastra del centro al círculo primitivo · Incremento elige un módulo normalizado · dientes antes o después"
        editing && state.cadTool != null -> "${cadLabel(state.cadTool!!)} · arrastra para dibujar · dos dedos navegan"
        entity?.type == "GEAR" -> cadGearSummary(entity, unit)
        entity?.isSquare == true -> if (entity.dimensions.any { it.constraintIds.isNotEmpty() })
            "Cuadrado: una cota controla ambos lados; editar Lado actualiza esa misma cota"
            else "Cuadrado: Igualdad une sus lados; Fijar medida añade una cota de tamaño"
        entity?.isFillet == true -> "Redondeo: cambia su radio · Borrar en el radial recupera la esquina"
        editing -> "Seleccionar: toca para añadir; tocar lo seleccionado lo quita · dos dedos giran la vista y se queda · Girar 90° y Enderezar la colocan"
        !editing && cad.rollbackId != null -> "Vista del pasado: ${cad.history.firstOrNull { it.id == cad.rollbackId }?.name.orEmpty()} · toca un nodo para ver el modelo en ese momento · Final restaura la pila completa"
        multipleProfiles -> "${shownProfiles.size} contornos seleccionados · Vaciar usa solo estos · toca uno seleccionado para quitarlo"
        cad.selectionKind == "PROFILE" && capabilities.profileMultiselect -> "Toca para añadir o quitar contornos del mismo boceto · Vaciar usa la selección"
        cad.selectionKind == "SKETCH" -> "${selectedSketch?.name.orEmpty()} completo · Extruir crea volumen y conserva los contornos interiores como huecos"
        selectedSketch != null -> "${selectedSketch.name} · perfil seleccionado · Seleccionar todo elige el croquis completo para extruir"
        else -> "Abre la pila (derecha) para editar un boceto · o crea uno en el rail izquierdo, y selecciona un perfil para extruir"
    }
    fun cadOperationChange(controls: CadOperationControls, values: Map<String, Any?>) {
        val pick = values.keys.firstOrNull { it.startsWith("pick_") }
        if (pick != null) { vm.cadPickParameter(pick, if (dynamicPreview) "SESSION" else controls.id); return }
        values.keys.forEach { drafts.remove(it) }
        if (dynamicPreview) command("cad.operation.update", *values.entries.map { it.key to it.value }.toTypedArray())
        else command("cad.feature.set", "feature_id" to controls.id, *values.entries.map { it.key to it.value }.toTypedArray())
    }
    var relationType by remember(cad.selection) { mutableStateOf<String?>(null) }
    val review = if (cad.sketchReview) "Revisa este paso en la pila. Se muestra la última pieza válida." else null
    val measures = listOfNotNull(arcSelectionHelp, cadSurfaceSummary(cad, unit).takeIf { cad.surface.selection.isNotEmpty() })
        .joinToString(" · ").ifBlank { null }
    val guidance = if (cad.error != null) "" else help
    val extentOwner = if (depthPreview) null else feature?.takeIf { it.type == "CUT" || it.type == "EXTRUDE" }
    // Opciones con nombre (lado, extensión, ejes, planos…): en «⋯ Más», por grupos.
    val showSnap = capabilities.sketchEditing && (editing || depthPreview || shellPreview)
    val revolveLike = feature?.takeIf { it.type == "REVOLVE" || it.type == "HELIX" }
    val referenceOptions = (planePreview && cad.planes.isNotEmpty() && cad.plane?.planeId == null) ||
        mirrorSource != null || feature?.isMirror == true || revolveLike != null ||
        (!editing && !cad.sessionActive && "CUT" in capabilities.features) ||
        cad.operationControls?.fields.orEmpty().any { it.type == "ACTION" } || depthPreview || extentOwner != null
    val shapeOptions = (planePreview) || offsetSource != null || entity?.type == "GEAR" ||
        (entity?.type in listOf("CIRCLE", "SLOT") && entity?.dimensions?.any { it.field == "radius" } == true) ||
        depthPreview || extentOwner != null || shellPreview || feature?.type == "SHELL" || feature?.type == "HELIX" ||
        cad.operationControls?.fields.orEmpty().any { it.type in listOf("BOOL", "ENUM", "MULTI") } ||
        (editing && editingConstraint == null && pendingDimension == null && cadTrayDimensionTypes(cad, capabilities.constraints).size > 1)
    val more = TrayMore(
        precision = {
            if (showSnap) TrayOption("Snap", "Incremento redondea medidas y gestos al paso; los números escritos son exactos.") {
                SnapControl(listOf(SnapType.NONE, SnapType.INCREMENT), if (cad.increment) SnapType.INCREMENT else SnapType.NONE,
                    { command("cad.settings", "increment" to (it == SnapType.INCREMENT)) })
            }
            TrayOption("Paso", "Cuánto avanza cada salto al dibujar, arrastrar o deslizar un número. También elige la unidad.") {
                CadSnapStepInput(cad.step, unit, { unit = it }) { command("cad.settings", "step" to it) }
            }
        },
        reference = if (!referenceOptions) null else ({
            if (planePreview && cad.planes.isNotEmpty() && cad.plane?.planeId == null) TrayOption("Planos guardados",
                "Reutiliza un plano anterior para el nuevo croquis o recolócalo.") {
                var savedOpen by remember { mutableStateOf(false) }
                Box {
                    PillButton("Elegir ▾", enabled = connected) { savedOpen = true }
                    DropdownMenu(savedOpen, onDismissRequest = { savedOpen = false }) {
                        if (capabilities.planePurge) DropdownMenuItem(text = { Text("Limpiar planos sin usar") }, onClick = {
                            savedOpen = false; command("cad.session.cancel"); command("cad.plane.purge")
                        })
                        cad.planes.forEach { saved ->
                            // Qué bocetos usa cada plano: el nombre solo dice de dónde salió.
                            val users = cad.sketches.filter { it.planeId == saved.id }.joinToString(", ") { it.name }
                            DropdownMenuItem(text = { Text("${saved.name} (${users.ifEmpty { "sin usar" }}) · ${if (cad.operation == "SPLIT") "plano de corte" else "nuevo croquis"}") }, onClick = {
                                savedOpen = false; command("cad.session.cancel");
                                if (cad.operation == "SPLIT") command("cad.plane.begin", "plane_id" to saved.id, "split_body_id" to cad.activeBodyId)
                                else command("cad.sketch.create", "plane_id" to saved.id)
                            })
                            if (cad.operation != "SPLIT") DropdownMenuItem(text = { Text("${saved.name} (${users.ifEmpty { "sin usar" }}) · recolocar") }, onClick = {
                                savedOpen = false; command("cad.plane.begin", "plane_id" to saved.id, "split_body_id" to cad.activeBodyId.takeIf { cad.operation == "SPLIT" })
                            })
                        }
                    }
                }
            }
            mirrorSource?.let { TrayOption("Plano de simetría", "Plano del documento sobre el que se refleja la operación.") {
                CadMirrorPlaneSelector(mirrorPlane, connected) { mirrorPlane = it }
            } }
            if (feature?.isMirror == true) {
                TrayOption("Plano de simetría", "Plano del documento sobre el que se refleja la operación.") {
                    CadMirrorPlaneSelector(feature.mirrorPlane, connected && drafts.isEmpty()) {
                        command("cad.feature.set", "feature_id" to feature.id, "plane" to it)
                    }
                }
                TrayOption("Operación fuente", "Selecciona la operación que se refleja.") {
                    PillButton("Ir", enabled = connected) { command("cad.select", "kind" to "FEATURE", "id" to feature.mirrorSourceId) }
                }
            }
            revolveLike?.let { selected ->
                TrayOption("Eje", "Eje del croquis o línea de construcción alrededor de la que gira el perfil.") {
                    val lines = cad.sketches.firstOrNull { it.id == selected.sketchId }?.entities.orEmpty().filter { it.type == "LINE" && it.construction }
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                        AxisSelector(when (selected.axis) { "X" -> Constraint.X; "Y" -> Constraint.Y; else -> Constraint.FREE },
                            onSelect = { command("cad.feature.set", "feature_id" to selected.id, "axis" to it.name) },
                            axes = listOf(com.blendertablet.remote.model.Axis.X, com.blendertablet.remote.model.Axis.Y),
                            allowFree = false, enabled = connected && drafts.isEmpty())
                        lines.forEachIndexed { i, line ->
                            PillButton("L${i + 1}", selected = selected.axis == line.id, enabled = connected && drafts.isEmpty()) {
                                command("cad.feature.set", "feature_id" to selected.id, "axis" to line.id)
                            }
                        }
                    }
                }
            }
            if (depthPreview || extentOwner != null) TrayOption("Hasta cara", "El siguiente toque elige la cara plana donde termina la operación.") {
                val owner = if (depthPreview) "SESSION" else extentOwner!!.id
                val active = if (depthPreview) cad.extent == "TO_FACE" || state.cadFacePick == "SESSION"
                    else extentOwner!!.extent == "TO_FACE" || state.cadFacePick == extentOwner.id
                PillButton(if (state.cadFacePick == owner) "Toca la cara…" else "Elegir", selected = active, enabled = connected) {
                    vm.cadPickEndFace(if (state.cadFacePick == owner) null else owner)
                }
            }
            if (!editing && !cad.sessionActive && "CUT" in capabilities.features) TrayOption("Destino",
                "Cuerpo sobre el que actúa Vaciar.") {
                var expanded by remember { mutableStateOf(false) }
                Box {
                    PillButton("${cad.bodies.firstOrNull { it.id == target?.bodyId }?.name ?: "Elegir cuerpo"} ▾", enabled = connected && targets.isNotEmpty()) { expanded = true }
                    DropdownMenu(expanded, onDismissRequest = { expanded = false }) {
                        targets.forEach { item -> DropdownMenuItem(text = { Text(cad.bodies.firstOrNull { it.id == item.bodyId }?.name ?: item.name) }, onClick = { cutTarget = item.bodyId; expanded = false }) }
                    }
                }
            }
            cad.operationControls?.let { controls -> CadOperationOptions(controls, connected, onlyActions = true) { values ->
                cadOperationChange(controls, values) } }
        }),
        shape = if (!shapeOptions) null else ({
            if (planePreview) cad.plane?.let { plane ->
                val axes = cadPlaneAxes(plane.base.takeIf { it != "FACE" && plane.planeId == null })
                val id = cad.sessionId.orEmpty()
                (0..1).forEach { i ->
                    TrayOption("Inclinar ${axes.rotation[i]}", "Gira el plano alrededor de este eje, en grados.") {
                        CadDimension("°", plane.tilt[i], unit, id + "tilt$i", degrees = true, step = 5.0,
                            minimum = -180.0, maximum = 180.0, enabled = connected,
                            onNudge = { sendPlane(tilt = plane.tilt.toMutableList().also { list -> list[i] = it }) },
                            onDone = { drafts["plane_tilt$i"]?.let { sendPlane(tilt = plane.tilt.toMutableList().also { list -> list[i] = it }) } }) { drafts["plane_tilt$i"] = it }
                    }
                }
                (0..1).forEach { i ->
                    TrayOption("Mover ${axes.inPlane[i]}", "Desplaza el plano dentro de sí mismo.") {
                        CadDimension(axes.inPlane[i], plane.shift[i], unit, id + "shift$i", step = cad.step, enabled = connected,
                            onNudge = { sendPlane(shift = plane.shift.toMutableList().also { list -> list[i] = it }) },
                            onDone = { drafts["plane_shift$i"]?.let { sendPlane(shift = plane.shift.toMutableList().also { list -> list[i] = it }) } }) { drafts["plane_shift$i"] = it }
                    }
                }
            }
            if (offsetSource != null) TrayOption("Lado", "Crea el contorno vinculado fuera o dentro de la figura.") {
                listOf("OUTWARD" to "Fuera", "INWARD" to "Dentro").forEach { (side, label) ->
                    PillButton(label, selected = offsetSide == side, enabled = connected) { offsetSide = side }
                }
            }
            entity?.takeIf { it.type == "GEAR" }?.let { gear ->
                TrayOption("Ángulo de presión", "Dos engranajes engranan si comparten módulo y ángulo.") {
                    val editable = connected && !livePreview && drafts.isEmpty()
                    listOf(14.5, 20.0, 25.0).forEach { angle ->
                        PillButton("${formatToolDistance(angle, 1)}°", selected = gear.values["pressure"] == angle, enabled = editable) {
                            command("cad.entity.set", "entity_id" to gear.id, "values" to mapOf("pressure" to angle))
                        }
                    }
                }
            }
            entity?.takeIf { it.type in listOf("CIRCLE", "SLOT") && it.dimensions.any { d -> d.field == "radius" } }?.let { selected ->
                TrayOption("Medida", "Radio o ${if (selected.type == "SLOT") "ancho" else "diámetro"}: la misma cota en dos formas.") {
                    PillButton("Radio", selected = !showDiameter, enabled = drafts.isEmpty()) { showDiameter = false }
                    PillButton(if (selected.type == "SLOT") "Ancho" else "Diámetro", selected = showDiameter, enabled = drafts.isEmpty()) { showDiameter = true }
                }
            }
            if (depthPreview) {
                TrayOption("Extensión", "Una dirección, a los dos lados del croquis o, al vaciar, a través de todo.") {
                    PillButton("Una", selected = cad.extent == "ONE" && state.cadFacePick == null, enabled = connected) {
                        command("cad.extrude.update", "extent" to "ONE")
                    }
                    PillButton(if (cad.operation == "EXTRUDE") "Simetría" else "Dos", selected = cad.extent == "BOTH" && state.cadFacePick == null, enabled = connected) {
                        command("cad.extrude.update", "extent" to "BOTH")
                    }
                    if (cad.operation == "CUT") PillButton("Todo", selected = cad.extent == "THROUGH_ALL" && state.cadFacePick == null, enabled = connected) {
                        focusManager.clearFocus(); drafts.remove("depth")
                        command("cad.extrude.update", "extent" to "THROUGH_ALL")
                    }
                }
                if (cad.operation == "EXTRUDE" && cad.extent !in listOf("BOTH", "TO_FACE", "THROUGH_ALL") && cad.positiveDirection.isNotEmpty())
                    TrayOption("Sentido", "Hacia qué lado del plano crece la extrusión.") {
                        val magnitude = kotlin.math.abs(cad.depth).coerceAtLeast(cad.step)
                        PillButton(cad.positiveDirection, selected = cad.depth >= 0, enabled = connected) {
                            command("cad.extrude.update", "depth" to magnitude)
                        }
                        PillButton(cad.negativeDirection, selected = cad.depth < 0, enabled = connected) {
                            command("cad.extrude.update", "depth" to -magnitude)
                        }
                    }
            }
            extentOwner?.let { selected ->
                TrayOption("Extensión", "Una dirección, a los dos lados del croquis o, al vaciar, a través de todo.") {
                    PillButton("Una", selected = selected.extent == "ONE" && state.cadFacePick == null, enabled = connected) {
                        command("cad.feature.set", "feature_id" to selected.id, "extent" to "ONE")
                    }
                    PillButton(if (selected.type == "EXTRUDE") "Simetría" else "Dos", selected = selected.extent == "BOTH" && state.cadFacePick == null, enabled = connected) {
                        command("cad.feature.set", "feature_id" to selected.id, "extent" to "BOTH")
                    }
                    if (selected.type == "CUT") PillButton("Todo", selected = selected.extent == "THROUGH_ALL" && state.cadFacePick == null, enabled = connected) {
                        focusManager.clearFocus(); drafts.remove("depth")
                        command("cad.feature.set", "feature_id" to selected.id, "extent" to "THROUGH_ALL")
                    }
                }
            }
            if (shellPreview) TrayOption("Lado", "Hacia dentro conserva el exterior; hacia fuera, el interior.") {
                CadShellSideControl(cad.side, connected && validDrafts) { side ->
                    drafts["thickness"]?.let { value -> drafts.remove("thickness"); command("cad.shell.update", "thickness" to value) }
                    command("cad.shell.update", "side" to side)
                }
            }
            if (feature?.type == "SHELL") TrayOption("Lado", "Hacia dentro conserva el exterior; hacia fuera, el interior.") {
                CadShellSideControl(feature.side, connected && validDrafts) { side ->
                    command("cad.feature.set", "feature_id" to feature.id, "side" to side,
                        "thickness" to (drafts["thickness"] ?: feature.thickness))
                    drafts.remove("thickness")
                }
            }
            if (feature?.type == "HELIX") TrayOption("Sentido de giro", "Hélice a derechas o a izquierdas.") {
                listOf("RIGHT" to "Derecha", "LEFT" to "Izquierda").forEach { (hand, label) ->
                    PillButton(label, selected = feature.hand == hand, enabled = connected && drafts.isEmpty()) {
                        command("cad.feature.set", "feature_id" to feature.id, "hand" to hand)
                    }
                }
            }
            cad.operationControls?.let { controls -> CadOperationOptions(controls, connected, onlyActions = false) { values ->
                cadOperationChange(controls, values) } }
            if (editing && editingConstraint == null && pendingDimension == null)
                CadRelationalType(cad, capabilities.constraints, relationType) { relationType = it }
        }),
    )
    SingleLineTray(
        title = if (cad.error != null) "Revisar CAD" else if (editing) "Croquis" else "CAD",
        onCancel = if (hasValues && !livePreview) ::discardValues else null,
        onConfirm = if (hasValues && !livePreview) ::acceptValues else null,
        confirmEnabled = canAccept,
        help = guidance, alert = listOfNotNull(cad.error, review).joinToString(" · ").ifBlank { null },
        status = measures, more = more, hintKey = "cad." + guidance.take(24),
        modifier = Modifier.align(Alignment.BottomCenter).fillMaxWidth().onSizeChanged { onTrayHeight(it.height) }.padding(Metrics.EdgeMargin),
    ) {
        key(editScope, resetInputs) {
            if (cad.surface.mode != "PROFILE" || !editing) {
                CadSurfaceControls(cad, capabilities, unit, connected && !cad.sessionActive, vm)
            }
            offsetSource?.let { source ->
                CadDimension("Grosor", drafts["thickness"] ?: cad.step, unit, source.id + "offset",
                    step = cad.step, minimum = .0000001, enabled = connected, onDone = ::acceptValues) { drafts["thickness"] = it }
            }
            mirrorSource?.let { source ->
                CadDimension("Posición", drafts["mirror_offset"] ?: 0.0, unit, source.id + "mirror",
                    step = cad.step, minimum = -10000.0, enabled = connected, onDone = ::acceptValues) { drafts["mirror_offset"] = it }
            }
            editingConstraint?.takeIf { it.value != null }?.let { constraint ->
                // Cota seleccionada: su valor y, al lado, quitarla. Nada más.
                val angle = constraint.type == "ANGLE"
                CadDimension(cadShortLabel(constraint.type), drafts["constraint"] ?: constraint.value!!, unit, constraint.id,
                    degrees = angle, step = if (angle) 1.0 else cad.step, enabled = connected, readOnly = livePreview,
                    minimum = if (angle) .01 else if (constraint.type in listOf("DISTANCE_X", "DISTANCE_Y")) 0.0 else .0000001,
                    maximum = if (angle) 359.99 else 10000.0,
                    onDone = ::acceptValues) { drafts["constraint"] = it }
            }
            if (editing && editingConstraint == null && pendingDimension == null) {
                CadRelationalDimensions(cad, capabilities.constraints, unit, connected && !cad.sessionActive, vm, relationType)
            }
            pendingDimension?.let { type ->
                val angle = type == "ANGLE"
                CadDimension(if (type == "FILLET") "Radio" else cadShortLabel(type), drafts["constraint"] ?: cad.dimensionOptions[type]?.value ?: cad.step * 5, unit, type,
                    degrees = angle, step = if (angle) 1.0 else cad.step, maximum = if (angle) 180.0 else 10000.0,
                    // Distancia 0 entre dos puntos los une (coincidencia).
                    enabled = connected, minimum = if (angle || type in listOf("DISTANCE", "DISTANCE_X", "DISTANCE_Y")) 0.0 else .0000001,
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
                }
                if (selected.type == "NGON") {
                    val sides = selected.values["sides"]?.toInt() ?: 6
                    CadSidesControl(sides, enabled = connected && !livePreview && drafts.isEmpty()) {
                        command("cad.entity.set", "entity_id" to selected.id, "values" to mapOf("sides" to it))
                    }
                }
                // Solo medidas: la posición se fija con candados y cotas a otros
                // puntos (origen, esquinas, centros), no escribiendo coordenadas.
                // El ángulo del arco/redondeo es una medida más, con su candado.
                val measures = cadDisplayMeasures(selected, showDiameter)
                measures.forEach { measure ->
                    val field = measure.field
                    val label = measure.label
                    val degrees = measure.constraintType == "ANGLE"
                    val bound = measure.constraintIds.isNotEmpty()
                    CadDimension(label, drafts[field] ?: selected.values[field] ?: 0.0, unit, selected.id + field,
                        degrees = degrees, step = if (degrees) 1.0 else cad.step, enabled = connected, readOnly = livePreview,
                        minimum = if (degrees) -359.99 else .0000001,
                        maximum = if (field == "sweep") 359.99 else 10000.0,
                        onDone = ::acceptValues) { drafts[field] = it?.takeIf { value -> field != "sweep" || kotlin.math.abs(value) in .01..359.99 } }
                    if (measure.lockable) CadAction("DIMENSION_LOCK", (if (bound) "Quitar cota: " else "Fijar medida: ") + label,
                        selected = bound, enabled = connected && !livePreview && drafts.isEmpty()) {
                        if (bound) command("cad.constraint.delete", "constraint_id" to measure.constraintIds.first())
                        else command("cad.constraint.add", "type" to measure.constraintType,
                            "value" to ((selected.values[field] ?: 0.0) * measure.valueFactor),
                            "refs" to measure.refs.map { mapOf("id" to it.id, "part" to it.part) })
                    }
                }
            }
            if (cad.sessionActive && cad.operation == "POLYGON") {
                IconAction(AppIcons.trayToggle("close_cut")!!, "Cerrar polígono", enabled = connected && cad.canClose) {
                    vm.cadCommand("cad.polygon.close")
                }
                TrayExits(onCancel = { vm.cadCommand("cad.session.cancel") })
            }
            if (planePreview) cad.plane?.let { plane ->
                CadDimension("Separación", plane.offset, unit, cad.sessionId.orEmpty() + "offset", step = cad.step, enabled = connected,
                    onNudge = { sendPlane(offset = it) }, onDone = { drafts["plane_offset"]?.let { sendPlane(offset = it) } }) { drafts["plane_offset"] = it }
            }
            if (cad.operationControls != null) {
                CadOperationFields(cad.operationControls, unit, connected, drafts, ::acceptValues) { values ->
                    cadOperationChange(cad.operationControls, values)
                }
            } else if (depthPreview) {
                if (cad.extent == "TO_FACE") {
                    Text("Hasta la cara", color = Ink.Muted, fontSize = 11.sp)
                } else if (cad.extent == "THROUGH_ALL") {
                    Text("Todo el grosor", color = Ink.Muted, fontSize = 11.sp)
                } else {
                    fun preview(value: Double) { drafts.remove("depth"); command("cad.extrude.update", "depth" to value) }
                    CadDimension("Profundidad", cad.depth, unit, cad.sessionId.orEmpty(), step = cad.step,
                        minimum = if (cad.operation == "EXTRUDE") -10000.0 else .0000001, enabled = connected, onNudge = ::preview,
                        onDone = { drafts["depth"]?.let(::preview) }) { drafts["depth"] = it }
                }
            } else if (shellPreview) {
                fun preview(value: Double) { drafts.remove("thickness"); command("cad.shell.update", "thickness" to value) }
                CadDimension("Grosor", cad.thickness, unit, cad.sessionId.orEmpty(), step = cad.step,
                    minimum = .0000001, enabled = connected, onNudge = ::preview,
                    onDone = { drafts["thickness"]?.let(::preview) }) { drafts["thickness"] = it }
            } else if (finishPreview) {
                fun preview(value: Double) { drafts.remove("width"); command("cad.finish.update", "width" to value) }
                CadDimension("Ancho", cad.width, unit, cad.sessionId.orEmpty(), step = cad.step,
                    minimum = .0000001, enabled = connected, onNudge = ::preview,
                    onDone = { drafts["width"]?.let(::preview) }) { drafts["width"] = it }
                if (cad.operation == "FILLET") CadCountControl("Segmentos", cad.segments, 1..16, connected) {
                    command("cad.finish.update", "segments" to it)
                }
            } else if (feature?.isMirror == true) {
                CadDimension("Posición", drafts["mirror_offset"] ?: feature.mirrorOffset, unit, feature.id,
                    step = cad.step, minimum = -10000.0, enabled = connected, onDone = ::acceptValues) { drafts["mirror_offset"] = it }
            } else if (feature?.type == "SHELL") {
                CadDimension("Grosor", drafts["thickness"] ?: feature.thickness, unit, feature.id,
                    step = cad.step, minimum = .0000001, enabled = connected, onDone = ::acceptValues) { drafts["thickness"] = it }
            } else if (feature?.isFinish == true) {
                CadDimension("Ancho", drafts["width"] ?: feature.width, unit, feature.id,
                    step = cad.step, minimum = .0000001, enabled = connected, onDone = ::acceptValues) { drafts["width"] = it }
                if (feature.type == "FILLET") CadCountControl("Segmentos", feature.segments, 1..16, connected && drafts.isEmpty()) {
                    command("cad.feature.set", "feature_id" to feature.id, "segments" to it)
                }
                Text("${feature.edgeCount} aristas", color = Ink.Muted, fontSize = 11.sp)
            } else if (feature?.type == "REVOLVE") {
                CadDimension("Ángulo", drafts["angle"] ?: feature.angle, unit, feature.id + "angle", degrees = true, step = 15.0,
                    minimum = .01, maximum = 360.0, enabled = connected, onDone = ::acceptValues) { drafts["angle"] = it }
            } else if (feature?.type == "HELIX") {
                CadDimension("Paso", drafts["pitch"] ?: feature.pitch, unit, feature.id + "pitch",
                    step = cad.step, minimum = .0000001, enabled = connected, onDone = ::acceptValues) { drafts["pitch"] = it }
                CadCountControl("Vueltas", kotlin.math.round(feature.turns).toInt().coerceAtLeast(1), 1..200, connected && drafts.isEmpty()) {
                    command("cad.feature.set", "feature_id" to feature.id, "turns" to it)
                }
            } else if (feature?.type == "LOFT" || feature?.type == "SWEEP") {
            } else if (offsetPlane != null) {
                CadDimension("Separación Z", drafts["offset"] ?: offsetPlane.translation.getOrElse(2) { 0.0 }, unit, offsetPlane.id,
                    step = cad.step, enabled = connected, onDone = ::acceptValues) { drafts["offset"] = it }
            } else feature?.let { selected ->
                if (selected.extent == "TO_FACE") Text("Hasta la cara", color = Ink.Muted, fontSize = 11.sp)
                else if (selected.extent == "THROUGH_ALL") Text("Todo el grosor", color = Ink.Muted, fontSize = 11.sp)
                else CadDimension("Profundidad", drafts["depth"] ?: selected.depth, unit, selected.id,
                    step = cad.step, minimum = if (selected.type == "EXTRUDE") -10000.0 else .0000001,
                    enabled = connected, onDone = ::acceptValues) { drafts["depth"] = it }
            }
        }
    }

}




internal fun cadHasProjectedCurves(cad: CadState): Boolean =
    cad.activeSketch?.entities.orEmpty().any { it.reference && it.type != "POINT" }

internal fun cadCloseReferenceEnabled(cad: CadState): Boolean {
    val entities = cad.activeSketch?.entities.orEmpty()
    val selected = cad.selection.map { it.id }.toSet()
    val targets = entities.filter { if (selected.isEmpty()) it.reference && it.type != "POINT" else it.id in selected }
    return targets.isNotEmpty() && targets.all { it.reference && it.type != "POINT" }
}

internal fun cadMidpointCreationEnabled(cad: CadState): Boolean {
    fun entity(ref: CadSelection) = cad.activeSketch?.entities?.firstOrNull { it.id == ref.id }
    val refs = cad.selection
    if (refs.size == 1) {
        val e = entity(refs[0]) ?: return false
        return (e.type == "LINE" && refs[0].part == "BODY") ||
            (e.type in listOf("RECTANGLE", "NGON") && refs[0].part.startsWith("EDGE")) ||
            (e.type == "SLOT" && refs[0].part == "AXIS")
    }
    return refs.size == 2 && refs.distinct().size == 2 && refs.all { ref ->
        val e = if (ref.id == "ORIGIN") CadEntity("ORIGIN", "ORIGIN", emptyMap()) else entity(ref) ?: return false
        cadPointPart(e, ref.part)
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

/** Acciones de boceto en el mismo rail izquierdo que las operaciones CAD. */
@Composable
fun CadToolContext(state: AppUiState, vm: MainViewModel) {
    val cad = state.blender.cad
    val enabled = state.connection == ConnectionStatus.CONNECTED && !cad.sessionActive
    if (cad.activeSketchId == null) {
        IconAction(AppIcons.cad("NEW_PLANE"), "Nuevo plano y croquis", enabled = enabled) {
            vm.cadCommand("cad.plane.begin", mapOf("base" to if (cad.surface.canSketch) "FACE" else if (cad.surface.canEdgePlane) "EDGE" else "XY"))
        }
        val sketch = cad.selectedSketch ?: cad.selectedFeature?.sketchId?.let { id -> cad.sketches.firstOrNull { it.id == id } }
        if (sketch != null) IconAction(AppIcons.cad("SKETCH"), "Editar boceto", enabled = enabled) {
            vm.cadTool(null); vm.cadCommand("cad.sketch.activate", mapOf("sketch_id" to sketch.id))
        }
    } else {
        IconAction(AppIcons.FinishSketch, "Finalizar boceto", enabled = enabled) {
            vm.cadTool(null); vm.cadCommand("cad.sketch.finish")
        }
        val entities = cad.activeSketch?.entities.orEmpty().filter { e -> cad.selection.any { it.id == e.id } }
        val construction = if (entities.isEmpty()) cad.construction else entities.all { it.construction }
        IconAction(AppIcons.cad("CONSTRUCTION"), "Construcción", selected = construction, enabled = enabled) {
            vm.cadCommand(if (entities.isEmpty()) "cad.settings" else "cad.entity.construction", mapOf("construction" to !construction))
        }
        if (state.blender.features.cad.referenceProfile && cadHasProjectedCurves(cad)) IconAction(AppIcons.cad("CLOSE_REFERENCE"),
            "Cerrar perfil proyectado", enabled = enabled && cadCloseReferenceEnabled(cad)) { vm.cadCommand("cad.reference.close") }
    }
}

@Composable
fun CadViewActions(state: AppUiState, vm: MainViewModel) {
    val cad = state.blender.cad
    val enabled = state.connection == ConnectionStatus.CONNECTED && !cad.sessionActive
    Row {
        IconAction(AppIcons.cad("VIEW_ROLL"), "Girar 90°", enabled = enabled) { vm.cadCommand("cad.view.roll", mapOf("degrees" to 90)) }
        IconAction(AppIcons.cad("VIEW_ALIGN"), "Enderezar", enabled = enabled) { vm.cadCommand("cad.view.align") }
        IconAction(AppIcons.Frame, "Encuadrar boceto", enabled = enabled, onClick = vm::frameSelected)
    }
    Row {
        IconAction(AppIcons.cad("PERSPECTIVE"), "Perspectiva / ortográfica", selected = state.blender.view.perspective == Projection.PERSP) {
            vm.viewPerspective(if (state.blender.view.perspective == Projection.PERSP) Projection.ORTHO else Projection.PERSP)
        }
        if (state.blender.features.cad.sectionView) IconAction(AppIcons.cad("SECTION"), "Vista en sección", selected = cad.section) {
            vm.cadCommand("cad.settings", mapOf("section" to !cad.section))
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
    fun point(i: Int) = cadPointPart(entities[i], refs[i].part)
    fun line(i: Int) = (entities[i].type == "LINE" && refs[i].part == "BODY") || (entities[i].type in listOf("RECTANGLE", "NGON") && refs[i].part.startsWith("EDGE"))
    val points = refs.indices.all(::point)
    val lines = refs.indices.all(::line)
    val curves = entities.all { it.type in listOf("CIRCLE", "ARC") }
    return when (type) {
        "FIX" -> refs.none { it.id == "ORIGIN" }
        "COINCIDENT" -> refs.size == 2 && points
        "POINT_ON_LINE" -> cadPointOnLineEnabled(refs, entities)
        "MIDPOINT" -> (refs.size == 2 && ((point(0) && line(1)) || (line(0) && point(1)))) ||
            (refs.size == 3 && refs.distinct().size == 3 && points)
        "SYMMETRIC" -> refs.size == 3 && points
        "SYMMETRIC_LINE" -> refs.size == 3 && point(0) && point(1) && line(2)
        "HORIZONTAL", "VERTICAL" -> lines
        "PARALLEL", "PERPENDICULAR" -> refs.size == 2 && lines
        "COLLINEAR" -> refs.size == 2 && refs.distinct().size == 2 && lines
        "EQUAL" -> if (curves) refs.map { it.id }.distinct().size >= 2 else refs.size >= 2 && lines
        "DISTANCE", "DISTANCE_X", "DISTANCE_Y" -> (refs.size == 1 && lines) || (refs.size == 2 && points)
        "RADIUS" -> refs.size == 1 && entities[0].type in listOf("CIRCLE", "ARC", "SLOT")
        "ANGLE" -> refs.size == 2 && refs.distinct().size == 2 && lines
        "TANGENT" -> refs.size == 2 && refs.map { it.id }.distinct().size == 2 && refs.all { it.part == "BODY" } &&
            entities.any { it.type in listOf("CIRCLE", "ARC") } && entities.all { it.type in listOf("LINE", "CIRCLE", "ARC") }
        else -> false
    }
}

private fun cadPointPart(entity: CadEntity, part: String): Boolean = when (entity.type) {
    "ORIGIN", "POINT" -> part == "POINT"
    "LINE" -> part in listOf("START", "END")
    "CIRCLE" -> part in listOf("CENTER", "RIM")
    "ARC" -> part in listOf("CENTER", "START", "END") || (part == "CORNER" && entity.isFillet)
    "RECTANGLE" -> part in listOf("P0", "P1", "P2", "P3")
    "NGON" -> part == "CENTER" || (part.startsWith("P") && part.removePrefix("P").toIntOrNull()
        ?.let { it in 0 until (entity.values["sides"]?.toInt() ?: 6) } == true)
    "SLOT" -> part in listOf("CENTER", "START", "END", "SIDE")
    "GEAR" -> part == "CENTER"
    else -> false
}

private fun cadPointOnLineEnabled(refs: List<CadSelection>, entities: List<CadEntity>): Boolean {
    if (refs.size != 2 || refs[0].id == refs[1].id) return false
    fun corner(part: String, prefix: String, count: Int): Boolean = part.startsWith(prefix) &&
        (part.removePrefix(prefix).toIntOrNull()?.let { it in 0 until count } == true)
    fun point(i: Int) = cadPointPart(entities[i], refs[i].part)
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
    )
    return groups.map { group -> group.filter { it in available } }.filter { it.isNotEmpty() }
}

internal val cadDimensionTypes = setOf("DISTANCE", "DISTANCE_X", "DISTANCE_Y", "RADIUS", "ANGLE")

internal fun cadTrayDimensionTypes(cad: CadState, available: List<String>): List<String> =
    if (cad.selection.size < 2) emptyList() else available.filter {
        it in cadDimensionTypes && cadConstraintEnabled(cad, it) && it in cad.dimensionOptions
    }

@Composable
private fun CadRelationalDimensions(cad: CadState, available: List<String>, unit: LengthUnit,
                                    enabled: Boolean, vm: MainViewModel, chosen: String?) {
    val options = cadTrayDimensionTypes(cad, available)
    if (options.isEmpty()) return
    val type = chosen?.takeIf { it in options } ?: options.first()
    val option = cad.dimensionOptions.getValue(type)
    var draft by remember(cad.selection, type) { mutableStateOf<Double?>(null) }
    val angle = type == "ANGLE"
    CadDimension(cadShortLabel(type), draft ?: option.value, unit, "relation$type",
        degrees = angle, step = if (angle) 1.0 else cad.step, minimum = 0.0,
        maximum = if (angle) 180.0 else 10000.0, enabled = enabled,
        onDone = { if (option.constraintId != null && draft != null)
            vm.cadCommand("cad.constraint.set", mapOf("constraint_id" to option.constraintId, "value" to draft)) },
        onNudge = { draft = it; if (option.constraintId != null)
            vm.cadCommand("cad.constraint.set", mapOf("constraint_id" to option.constraintId, "value" to it)) }) { draft = it }
    CadAction("DIMENSION_LOCK", if (option.constraintId == null) "Fijar cota" else "Quitar cota",
        selected = option.constraintId != null, enabled = enabled) {
        if (option.constraintId != null) vm.cadCommand("cad.constraint.delete", mapOf("constraint_id" to option.constraintId))
        else vm.cadCommand("cad.constraint.add", mapOf("type" to type, "value" to (draft ?: option.value)))
    }
}

/** Qué cota mide la selección de dos elementos, cuando hay varias posibles. */
@Composable
private fun CadRelationalType(cad: CadState, available: List<String>, chosen: String?, choose: (String) -> Unit) {
    val options = cadTrayDimensionTypes(cad, available)
    if (options.size < 2) return
    val type = chosen?.takeIf { it in options } ?: options.first()
    TrayOption("Tipo de cota", "Distancia diagonal, horizontal o vertical, radio o ángulo entre la selección.") {
        options.forEach { option -> PillButton(cadShortLabel(option), selected = option == type) { choose(option) } }
    }
}

/** Nombre corto de una cota, para el rótulo dentro de su campo. */
internal fun cadShortLabel(type: String) = when (type) {
    "DISTANCE" -> "Distancia"; "DISTANCE_X" -> "Dist. H"; "DISTANCE_Y" -> "Dist. V"
    "RADIUS" -> "Radio"; "ANGLE" -> "Ángulo"; else -> cadLabel(type)
}

/** Medidas derivadas del módulo: el círculo primitivo engrana y el paso es π·m. */
private fun cadGearSummary(gear: CadEntity, unit: LengthUnit): String {
    val module = gear.values["module"] ?: return "Engranaje"
    val teeth = gear.values["teeth"] ?: 20.0
    val factor = when (unit) { LengthUnit.MILLIMETERS -> 1000.0; LengthUnit.CENTIMETERS -> 100.0; LengthUnit.METERS -> 1.0 }
    fun text(meters: Double) = formatToolDistance(meters * factor, 2) + " " + unit.short
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
    "TANGENT" -> "Tangente (línea y arco, o dos arcos/círculos)"; "EQUAL" -> "Igualdad (tamaño del primero; en arcos también el ángulo, salvo redondeos)"; "EQUAL_ANGLE" -> "Igualdad de ángulo"; "DISTANCE" -> "Distancia diagonal / longitud"; "DISTANCE_X" -> "Distancia horizontal"; "DISTANCE_Y" -> "Distancia vertical"; "RADIUS" -> "Radio"; "ANGLE" -> "Ángulo"; "FIX" -> "Fijar selección"; "MIDPOINT" -> "Punto medio (punto + arista, o 3 puntos; último = medio)"; "SYMMETRIC" -> "Simetría (3 puntos; último = centro)"; "SYMMETRIC_LINE" -> "Simetría respecto a línea (2 puntos + eje)"
    "TRIM" -> "Recortar"; "SPLIT" -> "Partir cuerpo"; "COMBINE" -> "Combinar"; "PATTERN" -> "Patrón"; "HOLE" -> "Taladro"; "SHELL" -> "Carcasa"; "EXTRUDE" -> "Extruir"; "CUT" -> "Vaciar"; "LOFT" -> "Solevado"; "HELIX" -> "Barrido helicoidal"; "REVOLVE" -> "Revolución"; "SWEEP" -> "Barrido"; else -> type
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


/** One node of the operation stack: tap shows the model as of that node; ⋮ opens its actions. */
@Composable
private fun CadStackNodeRow(icon: String, label: String, selected: Boolean, dimmed: Boolean, enabled: Boolean,
                            tap: () -> Unit, reveal: Boolean = false) {
    val bringIntoView = remember { BringIntoViewRequester() }
    LaunchedEffect(reveal) {
        if (reveal) {
            withFrameNanos { }; withFrameNanos { }
            bringIntoView.bringIntoView()
        }
    }
    Box(Modifier.bringIntoViewRequester(bringIntoView)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            Icon(AppIcons.cad(icon), null, tint = if (dimmed) Ink.Faint else Ink.Muted, modifier = Modifier.size(20.dp))
            PillButton(label, modifier = Modifier.weight(1f), selected = selected, enabled = enabled && !dimmed, onClick = tap)

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
    step: Double, enabled: Boolean, degrees: Boolean = false, readOnly: Boolean = false, scalar: Boolean = false,
    minimum: Double = -10000.0, maximum: Double = 10000.0,
    onNudge: ((Double) -> Unit)? = null,
    onDone: () -> Unit,
    onDraft: (Double?) -> Unit,
) {
    val factor = if (degrees || scalar) 1.0 else when (unit) { LengthUnit.MILLIMETERS -> 1000.0; LengthUnit.CENTIMETERS -> 100.0; LengthUnit.METERS -> 1.0 }
    val input = remember(identity, factor) { CadNumberDraft() }
    SideEffect { input.acknowledge(meters) }
    val value = input.read(meters, factor, minimum, maximum)
    val suffix = if (scalar) "" else if (degrees) "°" else unit.short
    val decimals = if (degrees || unit == LengthUnit.MILLIMETERS) 2 else 4
    val width = if (label.length > 7) 150.dp else 120.dp
    if (readOnly) {
        // Medida en vivo durante un gesto: se lee, todavía no se edita.
        val live = meters * factor
        Row(Modifier.width(width).height(Metrics.Touch).padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(label, color = Ink.Faint, fontSize = 11.sp, maxLines = 1, modifier = Modifier.padding(end = 6.dp))
            Text(formatToolDistance(live, 2), color = Ink.OnPanel, fontSize = 16.sp,
                maxLines = 1, textAlign = TextAlign.End, modifier = Modifier.weight(1f))
            Text(suffix, color = Ink.Muted, fontSize = 11.sp, modifier = Modifier.padding(start = 3.dp))
        }
        return
    }
    var scrubbed by remember(identity) { mutableStateOf(0) }
    val displayed = (input.pending ?: meters) * factor
    HoverHelp(label, numberHelp(false), enabled = enabled) {
        // Cada paso deslizado acumula sobre el pendiente local, igual que un −/+ mantenido:
        // los acuses atrasados del servidor no lo devuelven atrás.
        ScrubNumber(enabled = enabled, onScrubStart = { scrubbed = 0 }, onScrub = { steps ->
            var next: Double? = null
            repeat(kotlin.math.abs(steps - scrubbed)) {
                next = input.nudge(meters, factor, step, if (steps > scrubbed) 1 else -1, minimum, maximum) ?: next
            }
            scrubbed = steps
            next?.let { if (onNudge != null) onNudge(it) else onDraft(it) }
        }) { field ->
            CompactNumericField(value = input.text ?: formatToolDistance(displayed, 2),
                onValueChange = { if (enabled) { input.text = it; onDraft(input.read(meters, factor, minimum, maximum)) } },
                modifier = field.width(width), textAlign = TextAlign.End, placeholder = suffix, fontSize = 16.sp,
                textColor = if (value == null) Ink.Bad else if (enabled) Ink.OnPanel else Ink.Faint, selectAllOnFocus = true,
                caption = label, suffix = suffix,
                onDone = { if (enabled && value != null) { input.pending = value; input.text = null; onDone() } })
        }
    }
}


@Composable
private fun CadConstraintRow(c: CadConstraint, sketch: CadSketch, unit: LengthUnit, enabled: Boolean, edit: () -> Unit, delete: () -> Unit) {
    val factor = when (unit) { LengthUnit.MILLIMETERS -> 1000.0; LengthUnit.CENTIMETERS -> 100.0; LengthUnit.METERS -> 1.0 }
    val value = c.value?.let { if (c.type == "ANGLE") " · ${formatToolDistance(it, 2)}°"
        else " · ${formatToolDistance(it * factor, 2)} ${unit.short}" }.orEmpty()
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
    "BODY" -> "completa"; "START" -> "inicio"; "END" -> "final"; "CENTER" -> "centro"; "CORNER" -> "esquina"; "RIM" -> "radio"
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

internal fun cadShellEnabled(cad: CadState, capabilities: CadCapabilities): Boolean =
    "SHELL" in capabilities.features && cad.activeSketchId == null && cad.surface.selection.isNotEmpty() &&
        cad.surface.selection.all { it.kind == "FACE" && it.planar && it.featureId != null } &&
        cad.surface.selection.map { it.objectName }.distinct().size == 1

@Composable
private fun CadShellSideControl(side: String, enabled: Boolean, select: (String) -> Unit) {
    listOf("INSIDE" to "Hacia dentro", "OUTSIDE" to "Hacia fuera").forEach { (value, label) ->
        PillButton(label, selected = side == value, enabled = enabled) { select(value) }
    }
}

@Composable
private fun CadSurfaceControls(cad: CadState, capabilities: CadCapabilities, unit: LengthUnit, enabled: Boolean, vm: MainViewModel) {
    val edges = cad.surface.selection.isNotEmpty() && cad.surface.selection.all { it.kind == "EDGE" }
    if (cadShellEnabled(cad, capabilities)) {
        CadAction("SHELL", "Carcasa", enabled = enabled) { vm.cadCommand("cad.shell.begin") }
    }
    if (cad.activeSketchId == null && edges) {
        // Varias aristas del sólido se redondean o achaflanan de una vez, como un paso de la pila.
        CadAction("FILLET", "Redondear aristas", enabled = enabled) { vm.cadCommand("cad.finish.begin", mapOf("operation" to "FILLET")) }
        CadAction("CHAMFER", "Chaflán en aristas", enabled = enabled) { vm.cadCommand("cad.finish.begin", mapOf("operation" to "CHAMFER")) }
    }
}

internal fun cadSurfaceSummary(cad: CadState, unit: LengthUnit): String {
    val factor = lengthFactor(unit)
    if (cad.surface.selection.size > 2 && cad.surface.selection.all { it.kind == "FACE" }) {
        val total = cad.surface.measurements.filter { it.unit == "AREA" }.sumOf { it.value } * factor * factor
        return "${cad.surface.selection.size} caras · Área total: ${formatToolDistance(total, 2)} ${unit.short}²"
    }
    if (cad.surface.selection.size > 2 && cad.surface.selection.all { it.kind == "EDGE" }) {
        val total = cad.surface.measurements.filter { it.unit == "LENGTH" }.sumOf { it.value } * factor
        return "${cad.surface.selection.size} aristas · Longitud total: ${formatToolDistance(total, 2)} ${unit.short}"
    }
    val measures = cad.surface.measurements.map { measurement ->
        val scale = when (measurement.unit) { "AREA" -> factor * factor; "ANGLE" -> 1.0; else -> factor }
        val suffix = when (measurement.unit) { "AREA" -> unit.short + "²"; "ANGLE" -> "°"; else -> unit.short }
        "${measurement.label}: ${formatToolDistance(measurement.value * scale, 2)} $suffix"
    }
    return (listOf("${cad.surface.selection.size} referencias seleccionadas") + measures).joinToString(" · ")
}


/** Número de lados de un polígono regular: 6 hace tuercas y sus alojamientos. */
@Composable
private fun CadSidesControl(sides: Int, enabled: Boolean, onChange: (Int) -> Unit) =
    CadCountControl("Lados", sides, 3..32, enabled, onChange)

/** Cantidad discreta (lados, segmentos) con −/+ compartidos; nunca usa unidades. */
@Composable
private fun CadCountControl(label: String, value: Int, range: IntRange, enabled: Boolean, onChange: (Int) -> Unit) {
    var base by remember { mutableStateOf(value) }
    var text by remember(value) { mutableStateOf<String?>(null) }
    HoverHelp(label, numberHelp(false), enabled = enabled) {
        ScrubNumber(enabled = enabled, onScrubStart = { base = value },
            onScrub = { steps -> (base + steps).coerceIn(range).let { if (it != value) onChange(it) } }) { field ->
            CompactNumericField(text ?: "$value", { text = it }, modifier = field.width(112.dp), fontSize = 16.sp,
                textAlign = TextAlign.End, selectAllOnFocus = true, caption = label,
                onDone = { text?.let { com.blendertablet.remote.model.NumericExpression.evaluate(it, value.toDouble()) }
                    ?.let { kotlin.math.round(it).toInt().coerceIn(range) }?.let(onChange); text = null })
        }
    }
}

/** Única figura seleccionada del boceto que admite desfase vinculado, o null. */
internal fun cadOffsetSource(cad: CadState, types: Collection<String>): CadEntity? =
    cad.selection.map { it.id }.distinct().singleOrNull()
        ?.let { id -> cad.activeSketch?.entities?.firstOrNull { it.id == id && it.type in types } }


/** Números del esquema de la operación publicada por Blender, en la fila de la bandeja. */
@Composable
private fun CadOperationFields(controls: CadOperationControls, unit: LengthUnit, enabled: Boolean,
    drafts: MutableMap<String, Double?>, done: () -> Unit, change: (Map<String, Any?>) -> Unit) {
    controls.fields.filter { it.type == "NUMBER" }.forEach { field -> key(controls.id, field.key) {
        CadDimension(field.label, field.number, unit, controls.id + field.key, step = field.step,
            enabled = enabled, degrees = field.unit == "ANGLE", scalar = field.unit == "SCALAR",
            minimum = field.minimum, maximum = field.maximum, onNudge = { change(mapOf(field.key to it)) },
            onDone = { drafts[field.key]?.let { change(mapOf(field.key to it)) } }) { drafts[field.key] = it }
    } }
}

/** Opciones con nombre del esquema en «⋯ Más»: acciones de elección en Referencia y el resto en Forma. */
@Composable
private fun CadOperationOptions(controls: CadOperationControls, enabled: Boolean, onlyActions: Boolean,
                                change: (Map<String, Any?>) -> Unit) {
    controls.fields.filter { if (onlyActions) it.type == "ACTION" else it.type in listOf("BOOL", "ENUM", "MULTI") }
        .forEach { field -> key(controls.id, field.key) {
        TrayOption(field.label, "") {
            when (field.type) {
                "BOOL" -> PillButton(if (field.boolean) "Activado" else "Desactivado", selected = field.boolean, enabled = enabled) {
                    change(mapOf(field.key to !field.boolean))
                }
                "ACTION" -> PillButton("Elegir", enabled = enabled) { change(mapOf(field.key to true)) }
                else -> {
                    var open by remember { mutableStateOf(false) }
                    val current = if (field.type == "MULTI") field.ids?.size?.toString() ?: "Todos"
                        else field.options.firstOrNull { it.first == field.value }?.second ?: field.value
                    Box {
                        PillButton("$current ▾", enabled = enabled) { open = true }
                        DropdownMenu(open, onDismissRequest = { open = false }) {
                            if (field.type == "MULTI") DropdownMenuItem(text = { Text("Todos") }, onClick = { change(mapOf(field.key to if (field.allNull) null else field.options.map { it.first })); open = false })
                            field.options.forEach { (id, label) ->
                                val selected = if (field.type == "MULTI") field.ids == null || id in field.ids else id == field.value
                                DropdownMenuItem(text = { Text((if (selected) "✓ " else "") + label) }, onClick = {
                                    if (field.type == "MULTI") {
                                        val ids = field.ids ?: field.options.map { it.first }
                                        val next = if (id in ids) ids - id else ids + id
                                        if (next.isNotEmpty()) change(mapOf(field.key to next))
                                    } else { if (id != field.value) change(mapOf(field.key to id)); open = false }
                                })
                            }
                        }
                    }
                }
            }
        }
    } }
}
