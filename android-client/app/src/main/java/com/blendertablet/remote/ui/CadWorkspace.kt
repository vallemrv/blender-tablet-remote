package com.blendertablet.remote.ui

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.blendertablet.remote.MainViewModel
import com.blendertablet.remote.model.*
import java.util.Locale

/** Sketch geometry and constraints own their rails; all input still uses InputSurface. */
@Composable
fun BoxScope.CadWorkspace(state: AppUiState, vm: MainViewModel) {
    val cad = state.blender.cad
    val capabilities = state.blender.features.cad
    val connected = state.connection == ConnectionStatus.CONNECTED
    var modelVisible by rememberSaveable { mutableStateOf(true) }
    var constraintsVisible by rememberSaveable { mutableStateOf(false) }
    var planesOpen by remember { mutableStateOf(false) }
    var unit by remember(state.blender.sceneScale.lengthUnit) { mutableStateOf(state.blender.sceneScale.lengthUnit) }
    var pendingDimension by remember(cad.activeSketchId, cad.selection) { mutableStateOf<String?>(null) }
    var editingConstraint by remember(cad.activeSketchId) { mutableStateOf<CadConstraint?>(null) }
    LaunchedEffect(cad.revision) {
        editingConstraint?.let { selected -> editingConstraint = cad.sketches.flatMap { it.constraints }.firstOrNull { it.id == selected.id } }
    }
    var cutTarget by remember(cad.documentId) { mutableStateOf<String?>(null) }
    val consumed = cad.features.filter { it.enabled }.mapNotNull { it.targetId }.toSet()
    val targets = cad.features.filter { it.enabled && it.id !in consumed }
    LaunchedEffect(cad.selectedFeature?.id) { cad.selectedFeature?.let { cutTarget = it.id } }
    val target = targets.firstOrNull { it.id == cutTarget } ?: targets.singleOrNull()
    val editing = cad.activeSketchId != null
    val selectedSketch = cad.selectedSketch
    LaunchedEffect(cad.activeSketchId) { if (cad.activeSketchId != null) modelVisible = true }
    val depthPreview = cad.sessionActive && cad.operation in listOf("EXTRUDE", "CUT")
    val availableHeight = (LocalConfiguration.current.screenHeightDp - 320).coerceAtLeast(100).dp
    fun command(name: String, vararg values: Pair<String, Any?>) { if (connected) vm.cadCommand(name, mapOf(*values)) }
    fun editSketch(sketchId: String) {
        vm.cadTool(null)
        modelVisible = true; constraintsVisible = false
        command("cad.sketch.activate", "sketch_id" to sketchId)
    }
    fun beginFeature(operation: String) {
        vm.cadTool(null)
        command("cad.extrude.begin", "profile_id" to cad.selectionId, "depth" to cad.step * 10,
            "operation" to operation, "target_id" to target?.id)
    }
    FloatingPanel(Modifier.align(Alignment.TopStart).padding(start = Metrics.EdgeMargin, top = 76.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            PillButton("Dibujos · ${cad.sketches.sumOf { it.entities.size }}", selected = modelVisible && !constraintsVisible) {
                modelVisible = !modelVisible || constraintsVisible; constraintsVisible = false
            }
            Text(if (editing) "${cad.activeSketch?.name} · ${cad.activeSketch?.planeLabel}" else "Sólidos CAD", color = Ink.OnPanel, fontSize = 13.sp,
                modifier = Modifier.padding(horizontal = 8.dp))
            PillButton("Planos", enabled = connected && !cad.sessionActive) { planesOpen = true }
            if (editing) CadAction("PLANE_${cad.activeSketch?.plane}", "Volver al plano del boceto", enabled = !cad.sessionActive) {
                command("cad.sketch.activate", "sketch_id" to cad.activeSketchId)
            }
            if (editing) PillButton("Finalizar boceto", enabled = connected && !cad.sessionActive) {
                vm.cadTool(null); command("cad.sketch.finish")
            }
            else if (selectedSketch != null) PillButton("Editar boceto", enabled = connected && !cad.sessionActive) {
                editSketch(selectedSketch.id)
            }
        }
    }
    ToolRail(Modifier.align(Alignment.CenterStart).padding(start = Metrics.EdgeMargin, top = 120.dp, bottom = 160.dp).heightIn(max = availableHeight)) {
        CadAction("SELECT", "Cursor · tocar alterna selección · arrastrar mueve", selected = state.cadTool == null, enabled = !cad.sessionActive) { vm.cadTool(null) }
        if (editing) {
            if (capabilities.sketchEditing) {
                CadAction("ORIGIN", "Seleccionar origen fijo (0,0)", enabled = !cad.sessionActive) {
                    command("cad.select", "kind" to "ENTITY", "id" to "ORIGIN", "part" to "POINT", "additive" to true)
                }
                CadAction("CONSTRUCTION", "Dibujar geometría auxiliar · no forma parte del perfil", selected = cad.construction, enabled = !cad.sessionActive) {
                    command("cad.settings", "construction" to !cad.construction)
                }
            }
            RailDivider()
            capabilities.entities.forEach { type ->
                CadAction(type, cadLabel(type), selected = state.cadTool == type, enabled = !cad.sessionActive || cad.operation == type) { vm.cadTool(type) }
            }
            if (capabilities.sketchEditing) CadAction("FILLET", "Redondeo de dos líneas conectadas", selected = pendingDimension == "FILLET",
                enabled = !cad.sessionActive && (cad.selection.size == 2 || cad.selectedEntity?.type == "RECTANGLE")) { pendingDimension = "FILLET" }
        } else {
            RailDivider()
            capabilities.planes.forEach { plane ->
                CadAction("PLANE_$plane", "Nuevo boceto $plane", enabled = connected && !cad.sessionActive) { command("cad.sketch.create", "plane" to plane) }
            }
            if (capabilities.sketchEditing) CadAction("SKETCH", "Boceto sobre la cara superior del sólido seleccionado",
                enabled = !cad.sessionActive && cad.selectedFeature != null) { command("cad.sketch.create", "support_id" to cad.selectedFeature?.id) }
            RailDivider()
            capabilities.features.forEach { operation ->
                CadAction(operation, cadLabel(operation), selected = depthPreview && cad.operation == operation,
                    enabled = connected && !cad.sessionActive && cad.selectionKind == "PROFILE" && (operation != "CUT" || target != null)) { beginFeature(operation) }
            }
        }
    }
    if (editing && capabilities.constraints.isNotEmpty()) ToolRail(
        Modifier.align(Alignment.CenterEnd).padding(end = Metrics.EdgeMargin, top = 142.dp, bottom = 180.dp).heightIn(max = availableHeight)
    ) {
        capabilities.constraints.forEach { type ->
            CadAction(type, cadLabel(type), enabled = connected && !cad.sessionActive && cadConstraintEnabled(cad, type),
                selected = pendingDimension == type) {
                if (type in listOf("DISTANCE", "RADIUS")) {
                    val existing = cad.dimensionOptions[type]?.constraintId?.let { id -> cad.activeSketch?.constraints?.firstOrNull { it.id == id } }
                    if (existing != null) { editingConstraint = existing; pendingDimension = null }
                    else { pendingDimension = type; editingConstraint = null }
                } else command("cad.constraint.add", "type" to type)
            }
        }
    }
    val contextualConstraints = cad.activeSketch?.constraints.orEmpty().filter { c ->
        cad.selection.any { selected ->
            c.refs.any { ref -> cadRefsTouch(selected, ref) } ||
                cad.activeSketch?.entities?.firstOrNull { it.id == selected.id }?.dimensions?.any { c.id in it.constraintIds } == true
        }
    }
    val contextual = editing && cad.selection.isNotEmpty()
    if (modelVisible) FloatingPanel(
        Modifier.align(Alignment.CenterStart).padding(start = 80.dp, top = 132.dp, bottom = 170.dp).width(310.dp).heightIn(max = availableHeight)
    ) {
        Column(Modifier.verticalScroll(rememberScrollState()).padding(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                PillButton("Dibujos", selected = !constraintsVisible) { constraintsVisible = false }
                PillButton("Cotas y reglas", selected = constraintsVisible, enabled = editing) { constraintsVisible = true }
            }
            if (!constraintsVisible) {
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    PillButton("Nuevo cuerpo", enabled = !cad.sessionActive) { command("cad.body.create") }
                    PillButton("Nuevo boceto", enabled = !cad.sessionActive) { planesOpen = true }
                }
                cad.bodies.forEach { body ->
                    PillButton(body.name, selected = cad.activeBodyId == body.id, enabled = !cad.sessionActive) { command("cad.body.activate", "body_id" to body.id) }
                    cad.sketches.filter { it.bodyId == body.id }.forEach { sketch ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            PillButton("${if (cad.activeSketchId == sketch.id) "Editando" else "Editar"} ${sketch.name}", selected = cad.activeSketchId == sketch.id, enabled = !cad.sessionActive) { editSketch(sketch.id) }
                            CadAction("VISIBLE", "${if (sketch.visible) "Ocultar" else "Mostrar"} ${sketch.name}", selected = sketch.visible, enabled = !cad.sessionActive) {
                                command("cad.sketch.visibility", "sketch_id" to sketch.id, "visible" to !sketch.visible)
                            }
                            CadAction("DELETE", "Eliminar ${sketch.name}", enabled = !cad.sessionActive && cad.features.none { it.sketchId == sketch.id }) { command("cad.sketch.delete", "sketch_id" to sketch.id) }
                        }
                        Text("${sketch.planeLabel} · ${sketch.entities.size} figuras · ${sketch.constraints.size} restricciones", color = Ink.Faint, fontSize = 11.sp)
                        if (!editing) sketch.profiles.forEach { profile ->
                            PillButton(profile.label, selected = cad.selectionId == profile.id, enabled = !cad.sessionActive) { command("cad.select", "kind" to "PROFILE", "id" to profile.id) }
                        }
                        if (sketch.id == cad.activeSketchId) sketch.entities.forEachIndexed { index, drawing ->
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(AppIcons.cad(drawing.type), null, tint = Ink.Muted, modifier = Modifier.size(20.dp))
                                PillButton("${if (drawing.isFillet) "Redondeo" else if (drawing.isSquare) "Cuadrado" else cadLabel(drawing.type)} ${index + 1}", selected = cad.selection.any { it.id == drawing.id }, enabled = connected && !cad.sessionActive) {
                                    vm.cadTool(null)
                                    command("cad.select", "kind" to "ENTITY", "id" to drawing.id, "part" to "BODY", "additive" to true)
                                }
                                CadAction("DELETE", if (drawing.isFillet) "Quitar redondeo y recuperar esquina" else "Borrar ${cadLabel(drawing.type)} ${index + 1}", enabled = connected && !cad.sessionActive) {
                                    command(if (drawing.isFillet) "cad.fillet.remove" else "cad.entity.delete", "entity_id" to drawing.id)
                                }
                            }
                        }
                    }
                    cad.features.filter { it.bodyId == body.id }.forEach { feature ->
                        PillButton("${feature.name}${if (!feature.enabled) " · desactivada" else ""}", selected = cad.selectionId == feature.id, enabled = !cad.sessionActive) {
                            vm.cadTool(null); command("cad.select", "kind" to "FEATURE", "id" to feature.id)
                        }
                    }
                }
            } else if (contextual) contextualConstraints.forEach { c ->
                CadConstraintRow(c, cad.activeSketch!!, unit, !cad.sessionActive, { editingConstraint = c; pendingDimension = null },
                    { command("cad.constraint.delete", "constraint_id" to c.id) })
            } else cad.sketches.forEach { sketch ->
                if (sketch.constraints.isNotEmpty()) Text(sketch.name, color = Ink.Muted, fontSize = 12.sp)
                sketch.constraints.forEach { c -> CadConstraintRow(c, sketch, unit, !cad.sessionActive,
                    { editingConstraint = c; pendingDimension = null },
                    { command("cad.constraint.delete", "constraint_id" to c.id, "sketch_id" to sketch.id) }) }
            }
        }
    }
    if (planesOpen) CadPlanesDialog(cad, unit, { planesOpen = false }, { name, values -> vm.cadCommand(name, values) }, {
        planesOpen = false; vm.cadTool("PLANE_FACE")
    })
    val focusManager = LocalFocusManager.current
    val editScope = listOf(cad.documentId, cad.activeSketchId, cad.selection, cad.selectionId,
        cad.sessionId, cad.revision, state.cadTool, pendingDimension, editingConstraint?.id)
    var resetInputs by remember(editScope) { mutableIntStateOf(0) }
    val drafts = remember(editScope, resetInputs) { mutableStateMapOf<String, Double?>() }
    val validDrafts = drafts.values.all { it != null }
    val entity = cad.selectedEntity?.takeUnless { cad.sessionActive || pendingDimension != null || editingConstraint != null }
    val feature = cad.selectedFeature?.takeUnless { cad.sessionActive || editing }
    fun acceptValues() {
        if (!connected || !validDrafts) return
        focusManager.clearFocus()
        when {
            depthPreview -> {
                drafts["depth"]?.let { command("cad.extrude.update", "depth" to it) }
                if (cad.canConfirm) command("cad.session.confirm")
            }
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
            entity != null && drafts.isNotEmpty() -> command("cad.entity.set", "entity_id" to entity.id, "values" to drafts.toMap())
            feature != null && drafts["depth"] != null -> command("cad.feature.set", "feature_id" to feature.id, "depth" to drafts["depth"])
        }
    }
    fun discardValues() {
        focusManager.clearFocus()
        if (depthPreview) command("cad.session.cancel")
        pendingDimension = null; editingConstraint = null; resetInputs++
    }
    val canAccept = connected && validDrafts && when {
        depthPreview -> cad.canConfirm
        pendingDimension != null -> true
        else -> drafts.isNotEmpty()
    }
    val parameterScroll = rememberScrollState()
    val hasValues = depthPreview || pendingDimension != null || editingConstraint != null || entity != null || feature != null
    FloatingPanel(Modifier.align(Alignment.BottomCenter).fillMaxWidth().padding(Metrics.EdgeMargin)) {
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(cad.error ?: when {
                !connected -> "Reconectando · recuperando el documento de Blender"
                drafts.isNotEmpty() && !depthPreview -> "Medidas pendientes · ✓ aplica los cambios · × descarta"
                depthPreview -> "${cadLabel(cad.operation)} · desliza arriba/abajo para profundidad · dos dedos navegan" + if (cad.transparent) " · transparencia automática" else ""
                state.cadTool == "PLANE_FACE" -> "Toca una cara plana para guardar su plano; después abre Planos para crear el boceto"
                state.cadTool == "ARC" -> "Arrastra centro → inicio del arco · ajusta radio y ángulo en la bandeja"
                state.cadTool != null -> "${cadLabel(state.cadTool!!)} · arrastra para dibujar · dos dedos navegan"
                entity?.isSquare == true -> if (entity.dimensions.any { it.constraintIds.isNotEmpty() })
                    "Cuadrado: una cota controla ambos lados; editar Lado actualiza esa misma cota"
                    else "Cuadrado: Igualdad une sus lados; Fijar medida añade una cota de tamaño"
                entity?.isFillet == true -> "Redondeo: cambia su radio o Quitar redondeo para recuperar la esquina"
                editing -> "Cursor: toca para seleccionar o quitar · arrastra para mover el grupo · Cotas y reglas permite editar o quitar medidas"
                selectedSketch != null -> "${selectedSketch.name} seleccionado · Editar boceto abre su geometría"
                else -> "Abre Dibujos para editar un boceto · o crea uno en Planos y selecciona un perfil para extruir"
            }, color = Ink.Muted, fontSize = 12.sp)
            Row(verticalAlignment = Alignment.CenterVertically) {
                key(editScope, resetInputs) {
                    Row(Modifier.weight(1f).horizontalScroll(parameterScroll), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                        if (editing && !cad.sessionActive) {
                            Text("${cad.selection.size} seleccionados", color = Ink.Muted, fontSize = 11.sp)
                            PillButton("Seleccionar todo", enabled = connected && cad.activeSketch?.entities?.isNotEmpty() == true) {
                                vm.selectAll()
                            }
                            PillButton("Deseleccionar todo", enabled = connected && cad.selection.isNotEmpty()) {
                                vm.deselectAll()
                            }
                            PillButton("Borrar selección", enabled = connected && cad.selection.any { it.id != "ORIGIN" }) { vm.delete() }
                            PillButton("Redondear esquina", enabled = connected && (cad.selection.size == 2 || cad.selectedEntity?.type == "RECTANGLE")) { pendingDimension = "FILLET" }
                            cad.selectedEntity?.let { selected -> PillButton("Construcción", selected = selected.construction, enabled = connected) {
                                command("cad.entity.construction", "construction" to !selected.construction)
                            } }
                        }
                        if (capabilities.sketchEditing && ((editing && state.cadTool == null) || depthPreview)) {
                            SnapControl(listOf(SnapType.NONE, SnapType.INCREMENT), if (cad.increment) SnapType.INCREMENT else SnapType.NONE,
                                { command("cad.settings", "increment" to (it == SnapType.INCREMENT)) })
                        }
                        CadSnapStepInput(cad.step, unit, { unit = it }) { command("cad.settings", "step" to it) }
                        editingConstraint?.let { constraint ->
                            PillButton("Quitar cota", enabled = connected) {
                                command("cad.constraint.delete", "constraint_id" to constraint.id,
                                    "sketch_id" to cad.sketches.firstOrNull { sketch -> sketch.constraints.any { it.id == constraint.id } }?.id)
                                editingConstraint = null
                            }
                            CadDimension(cadLabel(constraint.type), drafts["constraint"] ?: constraint.value ?: 0.0, unit, constraint.id,
                                step = cad.step, enabled = connected, minimum = .0000001, onDone = ::acceptValues) { drafts["constraint"] = it }
                        }
                        pendingDimension?.let { type ->
                            CadDimension(if (type == "DISTANCE") "Distancia" else "Radio", drafts["constraint"] ?: cad.dimensionOptions[type]?.value ?: cad.step * 5, unit, type,
                                step = cad.step, enabled = connected, minimum = .0000001, onDone = ::acceptValues) { drafts["constraint"] = it }
                        }
                        entity?.let { selected ->
                            val coordinates = when (selected.type) {
                                "RECTANGLE" -> emptyList()
                                "CIRCLE" -> listOf("x" to "Centro X", "y" to "Centro Y")
                                "ARC" -> if (selected.isFillet) emptyList() else listOf("start" to "Inicio", "sweep" to "Ángulo")
                                else -> listOf("x" to "X inicio", "y" to "Y inicio", "x2" to "X final", "y2" to "Y final")
                            }
                            val fields = selected.dimensions.map { it.field to it.label } + coordinates
                            fields.forEach { (field, label) ->
                                val measure = selected.dimensions.firstOrNull { it.field == field }
                                val degrees = field in listOf("start", "sweep")
                                val bound = measure?.constraintIds?.isNotEmpty() == true
                                CadDimension(label + if (measure != null) if (bound) " · cota" else " · sin cota" else "",
                                    drafts[field] ?: selected.values[field] ?: 0.0, unit, selected.id + field,
                                    degrees = degrees, step = if (degrees) 1.0 else cad.step, enabled = connected,
                                    minimum = if (measure != null) .0000001 else -10000.0,
                                    maximum = if (field == "sweep") 359.99 else 10000.0,
                                    onDone = ::acceptValues) { drafts[field] = it?.takeIf { value -> field != "sweep" || kotlin.math.abs(value) in .01..359.99 } }
                                measure?.let { spec ->
                                    PillButton(if (bound) "Quitar cota" else "Fijar medida", enabled = connected && drafts.isEmpty()) {
                                        if (bound) command("cad.constraint.delete", "constraint_id" to spec.constraintIds.first())
                                        else command("cad.constraint.add", "type" to spec.constraintType,
                                            "value" to ((selected.values[field] ?: 0.0) * spec.valueFactor),
                                            "refs" to spec.refs.map { mapOf("id" to it.id, "part" to it.part) })
                                    }
                                }
                            }
                            if (selected.isFillet) PillButton("Quitar redondeo", enabled = connected && drafts.isEmpty()) {
                                command("cad.fillet.remove", "entity_id" to selected.id)
                            }
                        }
                        if (!editing && !cad.sessionActive && "CUT" in capabilities.features) {
                            var expanded by remember { mutableStateOf(false) }
                            Box {
                                PillButton("Destino: ${target?.name ?: "elegir sólido"}", enabled = connected && targets.isNotEmpty()) { expanded = true }
                                DropdownMenu(expanded, onDismissRequest = { expanded = false }) {
                                    targets.forEach { item -> DropdownMenuItem(text = { Text(item.name) }, onClick = { cutTarget = item.id; expanded = false }) }
                                }
                            }
                        }
                        if (depthPreview) {
                            fun preview(value: Double) { drafts.remove("depth"); command("cad.extrude.update", "depth" to value) }
                            CadDimension("Profundidad", cad.depth, unit, cad.sessionId.orEmpty(), step = cad.step,
                                minimum = .0000001, enabled = connected, onNudge = ::preview,
                                onDone = { drafts["depth"]?.let(::preview) }) { drafts["depth"] = it }
                        } else feature?.let { selected ->
                            CadDimension("Profundidad", drafts["depth"] ?: selected.depth, unit, selected.id,
                                step = cad.step, minimum = .0000001, enabled = connected, onDone = ::acceptValues) { drafts["depth"] = it }
                            CadAction("VISIBLE", if (selected.enabled) "Ocultar" else "Mostrar", selected = selected.enabled, enabled = connected) { command("cad.feature.set", "feature_id" to selected.id, "enabled" to !selected.enabled) }
                            CadAction("CONVERT", "Crear copia de malla (conserva el modelo CAD)", enabled = selected.enabled && connected) { command("cad.convert", "feature_id" to selected.id) }
                            CadAction("DELETE", "Borrar operación", enabled = connected) { command("cad.feature.delete", "feature_id" to selected.id) }
                        }
                    }
                }
                if (hasValues) {
                    Spacer(Modifier.width(10.dp))
                    RoundAction(AppIcons.cad("CANCEL"), if (depthPreview) "Descartar preview" else "Descartar medidas", Ink.Bad, ::discardValues)
                    Spacer(Modifier.width(4.dp))
                    RoundAction(AppIcons.cad("FINISH"), if (depthPreview) "Confirmar ${cadLabel(cad.operation)}" else "Aplicar medidas",
                        if (canAccept) Ink.Ok else Ink.Faint, { if (canAccept) acceptValues() })
                }
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

internal fun cadConstraintEnabled(cad: CadState, type: String): Boolean {
    val refs = cad.selection
    if (refs.isEmpty()) return false
    val entities = refs.map { ref -> if (ref.id == "ORIGIN") CadEntity("ORIGIN", "ORIGIN", emptyMap()) else cad.activeSketch?.entities?.firstOrNull { it.id == ref.id } ?: return false }
    fun point(i: Int) = refs[i].part in listOf("START", "END", "CENTER", "RIM", "P0", "P1", "P2", "P3", "POINT")
    fun line(i: Int) = (entities[i].type == "LINE" && refs[i].part == "BODY") || (entities[i].type == "RECTANGLE" && refs[i].part.startsWith("EDGE"))
    val points = refs.indices.all(::point)
    val lines = refs.indices.all(::line)
    val curves = entities.all { it.type in listOf("CIRCLE", "ARC") }
    return when (type) {
        "FIX" -> refs.none { it.id == "ORIGIN" }
        "COINCIDENT" -> refs.size == 2 && points
        "MIDPOINT" -> refs.size == 2 && ((point(0) && line(1)) || (line(0) && point(1)))
        "SYMMETRIC" -> refs.size == 3 && points
        "HORIZONTAL", "VERTICAL" -> refs.size == 1 && lines
        "PARALLEL", "PERPENDICULAR" -> refs.size == 2 && lines
        "EQUAL" -> refs.size == 2 && (lines || curves)
        "DISTANCE" -> (refs.size == 1 && lines) || (refs.size == 2 && points)
        "RADIUS" -> refs.size == 1 && curves
        "TANGENT" -> refs.size == 2 && entities.any { it.type == "LINE" } && entities.any { it.type in listOf("CIRCLE", "ARC") }
        else -> false
    }
}

internal fun cadLabel(type: String) = when (type) {
    "RECTANGLE" -> "Rectángulo"; "SQUARE" -> "Cuadrado"; "CIRCLE" -> "Círculo"; "LINE" -> "Línea"; "ARC" -> "Arco"; "FILLET" -> "Redondeo"
    "COINCIDENT" -> "Coincidente"; "HORIZONTAL" -> "Horizontal"; "VERTICAL" -> "Vertical"; "PARALLEL" -> "Paralela"; "PERPENDICULAR" -> "Perpendicular"
    "TANGENT" -> "Tangente"; "EQUAL" -> "Igualdad"; "DISTANCE" -> "Distancia / longitud"; "RADIUS" -> "Radio"; "FIX" -> "Fijar selección"; "MIDPOINT" -> "Punto medio"; "SYMMETRIC" -> "Simetría (3 puntos; último = centro)"
    "EXTRUDE" -> "Extruir"; "CUT" -> "Vaciar"; else -> type
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CadAction(intent: String, description: String, selected: Boolean = false, enabled: Boolean = true, onClick: () -> Unit) {
    TooltipBox(positionProvider = TooltipDefaults.rememberTooltipPositionProvider(TooltipAnchorPosition.Above),
        tooltip = { PlainTooltip { Text(description) } }, state = rememberTooltipState()) {
        IconAction(AppIcons.cad(intent), description, selected = selected, enabled = enabled, onClick = onClick)
    }
}

/** Same compact fields and accelerating buttons as Edit; CAD wire values are metres. */
@Composable
private fun CadDimension(
    label: String, meters: Double, unit: LengthUnit, identity: String,
    step: Double, enabled: Boolean, degrees: Boolean = false,
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
        StepperButton("−", enabled && value != null && value > minimum) { nudge(-1) }
        val displayed = (input.pending ?: meters) * factor
        CompactNumericField(value = input.text ?: formatToolDistance(displayed, detailDecimalPlaces(displayed, if (degrees || unit == LengthUnit.MILLIMETERS) 2 else 4)),
            onValueChange = { if (enabled) { input.text = it; onDraft(input.read(meters, factor, minimum, maximum)) } },
            modifier = Modifier.width(84.dp), textAlign = TextAlign.End, placeholder = if (degrees) "°" else unit.short,
            textColor = if (value == null) Ink.Bad else if (enabled) Ink.OnPanel else Ink.Faint,
            onDone = { if (enabled && value != null) { input.pending = value; input.text = null; onDone() } })
        Text(if (degrees) "°" else unit.short, color = Ink.Muted, fontSize = 12.sp)
        StepperButton("+", enabled && value != null && value < maximum) { nudge(1) }
    }
}


@Composable
private fun CadConstraintRow(c: CadConstraint, sketch: CadSketch, unit: LengthUnit, enabled: Boolean, edit: () -> Unit, delete: () -> Unit) {
    val factor = when (unit) { LengthUnit.MILLIMETERS -> 1000.0; LengthUnit.CENTIMETERS -> 100.0; LengthUnit.METERS -> 1.0 }
    val value = c.value?.let { " · ${formatToolDistance(it * factor, detailDecimalPlaces(it * factor, 2))} ${unit.short}" }.orEmpty()
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

@Composable
private fun CadPlanesDialog(cad: CadState, unit: LengthUnit, dismiss: () -> Unit,
    command: (String, Map<String, Any?>) -> Unit, pickFace: () -> Unit) {
    var base by remember { mutableStateOf("XY") }
    var source by remember { mutableStateOf<String?>(null) }
    var planeToEdit by remember { mutableStateOf<CadPlane?>(null) }
    val factor = when (unit) { LengthUnit.MILLIMETERS -> 1000.0; LengthUnit.CENTIMETERS -> 100.0; LengthUnit.METERS -> 1.0 }
    var translation by remember { mutableStateOf(listOf("0","0","0")) }
    var rotation by remember { mutableStateOf(listOf("0","0","0")) }
    fun parse(values: List<String>) = values.map { it.replace(',', '.').toDoubleOrNull()?.takeIf { number -> number.isFinite() } }
    val position = parse(translation)
    val angles = parse(rotation)
    val valid = position.all { it != null } && angles.all { it != null }
    AlertDialog(onDismissRequest = dismiss, title = { Text("Planos y bocetos") }, text = {
        Column(Modifier.heightIn(max = 480.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Nuevo boceto en un plano base")
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) { listOf("XY","XZ","YZ").forEach { p ->
                PillButton(p) { command("cad.sketch.create", mapOf("plane" to p)); dismiss() }
            } }
            cad.sketches.forEach { sketch -> PillButton("Usar plano de ${sketch.name}") {
                command("cad.sketch.create", mapOf("reference_sketch_id" to sketch.id)); dismiss()
            } }
            cad.planes.forEach { p ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    PillButton("Boceto en ${p.name}") { command("cad.sketch.create", mapOf("plane_id" to p.id)); dismiss() }
                    PillButton("Ajustar") { planeToEdit = p; translation = p.translation.map { String.format(Locale.US,"%.8g",it * factor) }; rotation = p.rotation.map { it.toString() } }
                }
            }
            PillButton("Plano desde cara plana…", onClick = pickFace)
            PillButton("Ver objetos de la escena", selected = cad.showScene) { command("cad.settings", mapOf("show_scene" to !cad.showScene)) }
            HorizontalDivider()
            Text(planeToEdit?.let { "Ajustar ${it.name}" } ?: "Crear plano desplazado / inclinado")
            if (planeToEdit == null) {
                Row { listOf("XY","XZ","YZ").forEach { p -> PillButton(p, selected = base == p && source == null) { base = p; source = null } } }
                cad.sketches.forEach { sketch -> PillButton("Relativo a ${sketch.name}", selected = source == sketch.id) { source = sketch.id } }
            }
            CadVectorFields("Desplazamiento", translation, unit.short) { translation = it }
            CadVectorFields("Giro local", rotation, "°") { rotation = it }
            Text("Los desplazamientos y giros son relativos al plano elegido. Guardar aplica todas las cotas juntas.", fontSize = 12.sp)
            PillButton(if (planeToEdit == null) "Guardar nuevo plano" else "Guardar posición", enabled = valid) {
                command(if (planeToEdit == null) "cad.plane.create" else "cad.plane.set", mapOf(
                    "plane_id" to planeToEdit?.id,"base" to base,"reference_sketch_id" to source,"translation" to position.map { it!! / factor },"rotation" to angles.map { it!! }))
                planeToEdit = null
            }
        }
    }, confirmButton = { TextButton(onClick = dismiss) { Text("Cerrar") } })
}


@Composable
private fun CadVectorFields(label: String, values: List<String>, unit: String, change: (List<String>) -> Unit) {
    Text("$label · $unit", fontSize = 12.sp)
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        listOf("X","Y","Z").forEachIndexed { index, axis ->
            OutlinedTextField(values[index], { value -> change(values.toMutableList().also { it[index] = value }) },
                label = { Text(axis) }, singleLine = true,
                isError = values[index].replace(',', '.').toDoubleOrNull()?.isFinite() != true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), modifier = Modifier.weight(1f))
        }
    }
}
