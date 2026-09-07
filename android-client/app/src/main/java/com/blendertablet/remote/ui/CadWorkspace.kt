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

/** CAD chrome reuses the shared viewport, floating panels and file menu. */
@Composable
fun BoxScope.CadWorkspace(state: AppUiState, vm: MainViewModel) {
    val cad = state.blender.cad
    val capabilities = state.blender.features.cad
    val connected = state.connection == ConnectionStatus.CONNECTED
    var modelVisible by rememberSaveable { mutableStateOf(true) }
    val toolbarWidth = (LocalConfiguration.current.screenWidthDp.dp - 260.dp).coerceIn(220.dp, 600.dp)
    var unit by remember(state.blender.sceneScale.lengthUnit) { mutableStateOf(state.blender.sceneScale.lengthUnit) }
    fun command(name: String, vararg values: Pair<String, Any?>) { if (connected) vm.cadCommand(name, mapOf(*values)) }
    FloatingPanel(Modifier.align(Alignment.TopStart).padding(start = Metrics.EdgeMargin, top = 76.dp).widthIn(max = toolbarWidth)) {
        Row(Modifier.horizontalScroll(rememberScrollState()), verticalAlignment = Alignment.CenterVertically) {
            PillButton("Modelo", selected = modelVisible) { modelVisible = !modelVisible }
            PillButton("Seleccionar", selected = state.cadTool == null) { vm.cadTool(null) }
            if (cad.activeSketchId == null) capabilities.planes.forEach { plane ->
                PillButton("Boceto $plane", enabled = connected && !cad.sessionActive) { command("cad.sketch.create", "plane" to plane) }
            } else {
                capabilities.entities.forEach { type ->
                    PillButton(cadEntityLabel(type), selected = state.cadTool == type, enabled = connected && !cad.sessionActive) { vm.cadTool(type) }
                }
                PillButton("Finalizar boceto") { vm.cadTool(null); command("cad.sketch.finish") }
            }
        }
    }
    if (modelVisible) FloatingPanel(Modifier.align(Alignment.CenterStart).padding(start = Metrics.EdgeMargin, top = 142.dp, bottom = 156.dp).width(210.dp)) {
        Column(Modifier.verticalScroll(rememberScrollState()).padding(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("Modelo CAD", color = Ink.OnPanel, fontSize = 14.sp)
            if (cad.isolated) Text("Vista CAD aislada", color = Ink.Muted, fontSize = 12.sp)
            if (cad.sketches.isEmpty()) Text("Crea un boceto y dibuja con un dedo o lápiz.", color = Ink.Muted, fontSize = 12.sp)
            cad.sketches.forEach { sketch ->
                PillButton("${sketch.name} · ${sketch.plane}", selected = cad.activeSketchId == sketch.id) {
                    vm.cadTool(null); command("cad.sketch.activate", "sketch_id" to sketch.id)
                }
                if (cad.activeSketchId == sketch.id) sketch.entities.forEach { entity ->
                    PillButton(cadEntityLabel(entity.type), selected = cad.selectionId == entity.id) {
                        vm.cadTool(null); command("cad.select", "kind" to "ENTITY", "id" to entity.id)
                    }
                }
                if (cad.activeSketchId == null) sketch.profiles.forEach { profile ->
                    PillButton(profile.label, selected = cad.selectionId == profile.id) {
                        command("cad.select", "kind" to "PROFILE", "id" to profile.id)
                    }
                }
            }
            cad.features.forEach { feature ->
                PillButton(feature.name + if (!feature.enabled) " · oculta" else "", selected = cad.selectionId == feature.id) {
                    vm.cadTool(null); command("cad.select", "kind" to "FEATURE", "id" to feature.id)
                }
            }
        }
    }
    FloatingPanel(Modifier.align(Alignment.BottomCenter).fillMaxWidth().padding(Metrics.EdgeMargin)) {
        Column(Modifier.padding(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(cad.error ?: when {
                !connected -> "Reconectando · el documento se recuperará desde Blender"
                cad.sessionActive && cad.operation == "EXTRUDE" -> "Extrusión · revisa la vista previa y confirma"
                state.cadTool != null -> "Arrastra para dibujar · dos dedos navegan y cancelan el trazo"
                cad.activeSketchId != null -> "Boceto ${cad.activeSketch?.plane.orEmpty()} · selecciona una figura para editar sus cotas"
                else -> "Selecciona un perfil para extruir o abre un boceto para editarlo"
            }, color = Ink.Muted, fontSize = 12.sp)
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                CadUnitSelector(unit) { unit = it }
                cad.selectedEntity?.takeUnless { cad.sessionActive }?.let { entity ->
                    val fields = when (entity.type) {
                        "RECTANGLE" -> listOf("width" to "Ancho", "height" to "Alto")
                        "CIRCLE" -> listOf("diameter" to "Diámetro")
                        else -> listOf("x" to "X inicio", "y" to "Y inicio", "x2" to "X final", "y2" to "Y final")
                    }
                    fields.forEach { (key, label) ->
                        CadDimension(label, entity.values[key] ?: 0.0, unit, entity.id + key) {
                            command("cad.entity.set", "entity_id" to entity.id, "values" to mapOf(key to it))
                        }
                    }
                    PillButton("Borrar figura") { command("cad.entity.delete", "entity_id" to entity.id) }
                }
                if (cad.selectionKind == "PROFILE" && cad.activeSketchId == null && "EXTRUDE" in capabilities.features && !cad.sessionActive) {
                    PillButton("Extruir") { command("cad.extrude.begin", "profile_id" to cad.selectionId, "depth" to 0.02) }
                }
                if (cad.sessionActive && cad.operation == "EXTRUDE") {
                    CadDimension("Profundidad", cad.depth, unit, "extrude") { command("cad.extrude.update", "depth" to it) }
                    PillButton("Confirmar", enabled = cad.canConfirm && connected) { command("cad.session.confirm") }
                    PillButton("Cancelar") { command("cad.session.cancel") }
                } else cad.selectedFeature?.let { feature ->
                    CadDimension("Profundidad", feature.depth, unit, feature.id) { command("cad.feature.set", "feature_id" to feature.id, "depth" to it) }
                    PillButton(if (feature.enabled) "Ocultar" else "Mostrar") { command("cad.feature.set", "feature_id" to feature.id, "enabled" to !feature.enabled) }
                    PillButton("Editar boceto") { command("cad.sketch.activate", "sketch_id" to feature.sketchId) }
                    PillButton("Convertir a malla", enabled = feature.enabled && connected) { command("cad.convert", "feature_id" to feature.id) }
                    PillButton("Borrar extrusión") { command("cad.feature.delete", "feature_id" to feature.id) }
                }
            }
        }
    }
}

private fun cadEntityLabel(type: String) = when (type) { "RECTANGLE" -> "Rectángulo"; "CIRCLE" -> "Círculo"; "LINE" -> "Línea"; else -> type }

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
private fun CadDimension(label: String, meters: Double, unit: LengthUnit, identity: String, onApply: (Double) -> Unit) {
    val factor = when (unit) { LengthUnit.MILLIMETERS -> 1000.0; LengthUnit.CENTIMETERS -> 100.0; LengthUnit.METERS -> 1.0 }
    var text by remember(identity, meters, unit) { mutableStateOf(String.format(Locale.US, "%.4f", meters * factor).trimEnd('0').trimEnd('.')) }
    val value = text.replace(',', '.').toDoubleOrNull()?.takeIf { it.isFinite() }
    OutlinedTextField(value = text, onValueChange = { text = it }, label = { Text(label) },
        suffix = { Text(unit.short) }, singleLine = true, isError = value == null,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), modifier = Modifier.width(126.dp))
    TextButton(onClick = { value?.let { onApply(it / factor) } }, enabled = value != null) { Text("Aplicar") }
}
