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
    var modelVisible by rememberSaveable { mutableStateOf(false) }
    var unit by remember(state.blender.sceneScale.lengthUnit) { mutableStateOf(state.blender.sceneScale.lengthUnit) }
    var pendingDimension by remember(cad.activeSketchId, cad.selection) { mutableStateOf<String?>(null) }
    var editingConstraint by remember(cad.activeSketchId) { mutableStateOf<CadConstraint?>(null) }
    var cutTarget by remember(cad.documentId) { mutableStateOf<String?>(null) }
    val consumed = cad.features.filter { it.enabled }.mapNotNull { it.targetId }.toSet()
    val targets = cad.features.filter { it.enabled && it.id !in consumed }
    LaunchedEffect(cad.selectedFeature?.id) { cad.selectedFeature?.let { cutTarget = it.id } }
    val target = targets.firstOrNull { it.id == cutTarget } ?: targets.singleOrNull()
    val editing = cad.activeSketchId != null
    val selectedSketch = cad.selectedSketch
    val depthPreview = cad.sessionActive && cad.operation in listOf("EXTRUDE", "CUT")
    val availableHeight = (LocalConfiguration.current.screenHeightDp - 320).coerceAtLeast(100).dp
    fun command(name: String, vararg values: Pair<String, Any?>) { if (connected) vm.cadCommand(name, mapOf(*values)) }
    fun editSketch(sketchId: String) {
        vm.cadTool(null)
        modelVisible = false
        command("cad.sketch.activate", "sketch_id" to sketchId)
    }
    fun beginFeature(operation: String) {
        vm.cadTool(null)
        command("cad.extrude.begin", "profile_id" to cad.selectionId, "depth" to cad.step * 10,
            "operation" to operation, "target_id" to target?.id)
    }
    FloatingPanel(Modifier.align(Alignment.TopStart).padding(start = Metrics.EdgeMargin, top = 76.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            PillButton("Bocetos · ${cad.sketches.size}", selected = modelVisible) { modelVisible = !modelVisible }
            Text(if (editing) "${cad.activeSketch?.name} · ${cad.activeSketch?.plane}" else "Sólidos CAD", color = Ink.OnPanel, fontSize = 13.sp,
                modifier = Modifier.padding(horizontal = 8.dp))
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
        CadAction("SELECT", "Seleccionar puntos, aristas o perfiles", selected = state.cadTool == null, enabled = !cad.sessionActive) { vm.cadTool(null) }
        if (editing) {
            if (capabilities.sketchEditing) {
                CadAction("MULTI", "Selección múltiple · toca para añadir o quitar", selected = state.cadTool == "MULTI", enabled = !cad.sessionActive) { vm.cadTool("MULTI") }
                CadAction("MOVE", "Mover puntos o aristas con el lápiz", selected = state.cadTool == "MOVE") { vm.cadTool("MOVE") }
            }
            RailDivider()
            capabilities.entities.forEach { type ->
                CadAction(type, cadLabel(type), selected = state.cadTool == type, enabled = !cad.sessionActive || cad.operation == type) { vm.cadTool(type) }
            }
            if (capabilities.sketchEditing) CadAction("FILLET", "Redondeo de dos líneas conectadas", selected = pendingDimension == "FILLET",
                enabled = !cad.sessionActive && cad.selection.size == 2) { pendingDimension = "FILLET" }
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
                if (type in listOf("DISTANCE", "RADIUS")) pendingDimension = type
                else command("cad.constraint.add", "type" to type)
            }
        }
    }
    if (modelVisible) FloatingPanel(Modifier.align(Alignment.CenterStart).padding(start = 80.dp, top = 132.dp, bottom = 170.dp).width(230.dp)) {
        Column(Modifier.verticalScroll(rememberScrollState()).padding(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("Modelo CAD", color = Ink.OnPanel, fontSize = 14.sp)
            cad.sketches.forEach { sketch ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                PillButton("${if (cad.activeSketchId == sketch.id) "Editando" else "Editar"} ${sketch.name} · ${sketch.plane}", selected = cad.activeSketchId == sketch.id, enabled = connected && !cad.sessionActive) {
                    editSketch(sketch.id)
                }
                    CadAction("DELETE", "Eliminar ${sketch.name}", enabled = !cad.sessionActive && cad.features.none { it.sketchId == sketch.id }) { command("cad.sketch.delete", "sketch_id" to sketch.id) }
                }
                if (cad.activeSketchId == sketch.id) {
                    sketch.entities.forEachIndexed { index, entity ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(AppIcons.cad(entity.type), null, tint = Ink.Muted, modifier = Modifier.size(20.dp))
                            PillButton("${cadLabel(entity.type)} ${index + 1}", selected = cad.selection.any { it.id == entity.id }, enabled = !cad.sessionActive) {
                                command("cad.select", "kind" to "ENTITY", "id" to entity.id, "additive" to (state.cadTool == "MULTI"))
                            }
                        }
                    }
                    sketch.constraints.forEach { constraint ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(AppIcons.cad(constraint.type), null, tint = Ink.Accent, modifier = Modifier.size(20.dp))
                            if (constraint.value != null) PillButton(cadLabel(constraint.type), enabled = !cad.sessionActive) {
                                editingConstraint = constraint; pendingDimension = null
                            } else Text(cadLabel(constraint.type), color = Ink.Muted, fontSize = 12.sp, modifier = Modifier.weight(1f))
                            CadAction("DELETE", "Eliminar ${cadLabel(constraint.type)}", enabled = !cad.sessionActive) { command("cad.constraint.delete", "constraint_id" to constraint.id) }
                        }
                    }
                } else if (!editing) sketch.profiles.forEach { profile ->
                    PillButton(profile.label, selected = cad.selectionId == profile.id, enabled = !cad.sessionActive) { command("cad.select", "kind" to "PROFILE", "id" to profile.id) }
                }
            }
            cad.features.forEach { feature ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(AppIcons.cad(feature.type), null, tint = Ink.Muted, modifier = Modifier.size(20.dp))
                    PillButton(feature.name + if (!feature.enabled) " · oculta" else "", selected = cad.selectionId == feature.id, enabled = !cad.sessionActive) {
                        vm.cadTool(null); command("cad.select", "kind" to "FEATURE", "id" to feature.id)
                    }
                }
            }
        }
    }
    FloatingPanel(Modifier.align(Alignment.BottomCenter).fillMaxWidth().padding(Metrics.EdgeMargin)) {
        Column(Modifier.padding(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(cad.error ?: when {
                !connected -> "Reconectando · recuperando el documento de Blender"
                depthPreview -> "${cadLabel(cad.operation)} · desliza arriba/abajo para profundidad · dos dedos navegan" + if (cad.transparent) " · transparencia automática" else ""
                state.cadTool == "MOVE" -> "Arrastra un punto o una arista · la selección se mueve respetando sus restricciones"
                state.cadTool == "MULTI" -> "Toca puntos o aristas para añadir/quitar · elige una restricción en el rail derecho"
                state.cadTool == "ARC" -> "Arrastra centro → inicio del arco · ajusta el radio y el ángulo en la bandeja"
                state.cadTool != null -> "${cadLabel(state.cadTool!!)} · arrastra para dibujar · dos dedos navegan"
                editing -> "Seleccionar · toca puntos o aristas para editar sus cotas · Mover permite arrastrarlos · Finalizar boceto vuelve a los sólidos"
                selectedSketch != null -> "${selectedSketch.name} seleccionado · Editar boceto abre su geometría y actualiza las operaciones dependientes"
                else -> "Abre Bocetos para editar uno existente · o crea uno en XY/XZ/YZ y selecciona un perfil para extruir"
            }, color = Ink.Muted, fontSize = 12.sp)
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                if (editing && !cad.sessionActive) {
                    PillButton("Seleccionar", selected = state.cadTool == null, enabled = connected) { vm.cadTool(null) }
                    if (capabilities.sketchEditing) PillButton("Mover", selected = state.cadTool == "MOVE", enabled = connected) { vm.cadTool("MOVE") }
                }
                CadUnitSelector(unit) { unit = it }
                if (capabilities.sketchEditing && (state.cadTool == "MOVE" || depthPreview)) {
                    SnapControl(listOf(SnapType.NONE, SnapType.INCREMENT), if (cad.increment) SnapType.INCREMENT else SnapType.NONE,
                        { command("cad.settings", "increment" to (it == SnapType.INCREMENT)) })
                    CadSnapStepInput(cad.step, unit) { command("cad.settings", "step" to it) }
                }
                editingConstraint?.let { constraint ->
                    CadDimension(cadLabel(constraint.type), constraint.value ?: 0.0, unit, constraint.id) {
                        command("cad.constraint.set", "constraint_id" to constraint.id, "value" to it); editingConstraint = null
                    }
                    CadAction("CANCEL", "Cerrar cota") { editingConstraint = null }
                }
                pendingDimension?.let { type ->
                    CadDimension(if (type == "DISTANCE") "Distancia" else "Radio", cad.step * 5, unit, type) { value ->
                        if (type == "FILLET") command("cad.fillet", "radius" to value)
                        else command("cad.constraint.add", "type" to type, "value" to value)
                        pendingDimension = null
                    }
                    CadAction("CANCEL", "Cerrar cota") { pendingDimension = null }
                }
                cad.selectedEntity?.takeUnless { cad.sessionActive || pendingDimension != null || editingConstraint != null || state.cadTool == "MOVE" }?.let { entity ->
                    val fields = when (entity.type) {
                        "RECTANGLE" -> listOf("width" to "Ancho", "height" to "Alto")
                        "CIRCLE" -> listOf("diameter" to "Diámetro", "x" to "Centro X", "y" to "Centro Y")
                        "ARC" -> listOf("radius" to "Radio", "start" to "Inicio", "sweep" to "Ángulo")
                        else -> listOf("x" to "X inicio", "y" to "Y inicio", "x2" to "X final", "y2" to "Y final")
                    }
                    fields.forEach { (key, label) ->
                        CadDimension(label, entity.values[key] ?: 0.0, unit, entity.id + key, degrees = key in listOf("start", "sweep")) {
                            command("cad.entity.set", "entity_id" to entity.id, "values" to mapOf(key to it))
                        }
                    }
                    CadAction("DELETE", "Borrar figura") { command("cad.entity.delete", "entity_id" to entity.id) }
                }
                if (!editing && !cad.sessionActive && "CUT" in capabilities.features) {
                    var expanded by remember { mutableStateOf(false) }
                    Box {
                        PillButton("Destino: ${target?.name ?: "elegir sólido"}", enabled = targets.isNotEmpty()) { expanded = true }
                        DropdownMenu(expanded, onDismissRequest = { expanded = false }) {
                            targets.forEach { item -> DropdownMenuItem(text = { Text(item.name) }, onClick = { cutTarget = item.id; expanded = false }) }
                        }
                    }
                }
                if (depthPreview) {
                    var pendingDepth by remember(cad.sessionId) { mutableStateOf<Double?>(null) }
                    LaunchedEffect(cad.depth) { if (pendingDepth?.let { kotlin.math.abs(it - cad.depth) < 1e-9 } == true) pendingDepth = null }
                    fun nudge(direction: Int) {
                        val value = ((pendingDepth ?: cad.depth) + direction * cad.step).coerceAtLeast(.0000001)
                        pendingDepth = value; command("cad.extrude.update", "depth" to value)
                    }
                    StepperButton("−", enabled = connected) { nudge(-1) }
                    CadDimension("Profundidad", cad.depth, unit, "depth") { command("cad.extrude.update", "depth" to it) }
                    StepperButton("+", enabled = connected) { nudge(1) }
                    CadAction("FINISH", "Confirmar ${cadLabel(cad.operation)}", enabled = cad.canConfirm && connected) { command("cad.session.confirm") }
                    CadAction("CANCEL", "Cancelar preview") { command("cad.session.cancel") }
                } else cad.selectedFeature?.let { feature ->
                    CadDimension("Profundidad", feature.depth, unit, feature.id) { command("cad.feature.set", "feature_id" to feature.id, "depth" to it) }
                    CadAction("VISIBLE", if (feature.enabled) "Ocultar" else "Mostrar", selected = feature.enabled) { command("cad.feature.set", "feature_id" to feature.id, "enabled" to !feature.enabled) }
                    CadAction("CONVERT", "Convertir a malla", enabled = feature.enabled && connected) { command("cad.convert", "feature_id" to feature.id) }
                    CadAction("DELETE", "Borrar operación") { command("cad.feature.delete", "feature_id" to feature.id) }
                }
            }
        }
    }
}

internal fun cadConstraintEnabled(cad: CadState, type: String): Boolean {
    val refs = cad.selection
    val entities = refs.mapNotNull { ref -> cad.activeSketch?.entities?.firstOrNull { it.id == ref.id } }
    if (refs.isEmpty() || entities.size != refs.size) return false
    val points = refs.all { it.part in listOf("START", "END", "CENTER", "RIM", "P0", "P1", "P2", "P3") }
    val lines = entities.zip(refs).all { (e, r) -> e.type == "LINE" || (e.type == "RECTANGLE" && r.part.startsWith("EDGE")) }
    val curves = entities.all { it.type in listOf("CIRCLE", "ARC") }
    return when (type) {
        "FIX" -> refs.size == 1
        "COINCIDENT" -> refs.size == 2 && points
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
    "TANGENT" -> "Tangente"; "EQUAL" -> "Igualdad"; "DISTANCE" -> "Distancia / longitud"; "RADIUS" -> "Radio"; "FIX" -> "Fijar geometría"
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

@Composable
private fun CadUnitSelector(unit: LengthUnit, onUnit: (LengthUnit) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    Box {
        PillButton(unit.short) { expanded = true }
        DropdownMenu(expanded, onDismissRequest = { expanded = false }) {
            LengthUnit.entries.forEach { item -> DropdownMenuItem(text = { Text(item.short) }, onClick = { onUnit(item); expanded = false }) }
        }
    }
}

@Composable
private fun CadDimension(label: String, meters: Double, unit: LengthUnit, identity: String, degrees: Boolean = false, onApply: (Double) -> Unit) {
    val factor = if (degrees) 1.0 else when (unit) { LengthUnit.MILLIMETERS -> 1000.0; LengthUnit.CENTIMETERS -> 100.0; LengthUnit.METERS -> 1.0 }
    var draft by remember(identity, unit) { mutableStateOf<String?>(null) }
    val text = draft ?: String.format(Locale.US, "%.4f", meters * factor).trimEnd('0').trimEnd('.')
    val value = text.replace(',', '.').toDoubleOrNull()?.takeIf { it.isFinite() }
    OutlinedTextField(value = text, onValueChange = { draft = it }, label = { Text(label) },
        suffix = { Text(if (degrees) "°" else unit.short) }, singleLine = true, isError = value == null,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), modifier = Modifier.width(126.dp))
    CadAction("FINISH", "Aplicar $label", enabled = value != null) { value?.let { onApply(it / factor); draft = null } }
}
