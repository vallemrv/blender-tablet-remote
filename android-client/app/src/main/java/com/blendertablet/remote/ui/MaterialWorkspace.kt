package com.blendertablet.remote.ui

import android.net.Uri
import android.util.Base64
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Check
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.blendertablet.remote.MainViewModel
import com.blendertablet.remote.model.AppUiState
import com.blendertablet.remote.model.MaterialPreset
import com.blendertablet.remote.model.MaterialState
import com.blendertablet.remote.model.SurfaceControl
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.roundToInt

/**
 * Materiales reparte sus controles en cuatro superficies fijas, en vez de apilar
 * tres filas con scroll en una única bandeja donde selección, catálogo y pincel
 * competían por el mismo sitio.
 *
 * Rail izquierdo: qué hace el dedo (seleccionar, pintar, borrar) y con qué trazo.
 * Barra superior: sobre qué se trabaja (objetos, zona, aislamiento, ambiente).
 * Panel derecho: la biblioteca —base, tinte, acabado, detalle— con Aplicar.
 * Bandeja inferior: los dos ajustes continuos del pincel y la ayuda del momento.
 *
 * Cada cosa tiene un solo sitio, y el que se usa durante el trazo (tamaño,
 * intensidad, trazo, borrar) queda al alcance sin abrir nada.
 */
@Composable
fun BoxScope.MaterialWorkspace(state: AppUiState, vm: MainViewModel) {
    val material = state.blender.material
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var colorsOpen by rememberSaveable { mutableStateOf(false) }
    var saveOpen by remember { mutableStateOf(false) }
    var saveName by remember { mutableStateOf("") }
    var libraryOpen by rememberSaveable { mutableStateOf(true) }
    val importer = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) scope.launch {
            runCatching {
                val text = withContext(Dispatchers.IO) {
                    context.contentResolver.openInputStream(uri)?.use { input ->
                        val bytes = input.readBytesBounded(65536)
                        bytes.toString(Charsets.UTF_8)
                    } ?: error("No se pudo abrir el material")
                }
                vm.materialCommand("material.import", mapOf("recipe" to JSONObject(text)))
            }.onFailure { Toast.makeText(context, it.message ?: "Receta inválida", Toast.LENGTH_LONG).show() }
        }
    }
    // La biblioteca ocupa el sitio del inspector de modificadores —bajo el rail de
    // modos, con su mismo margen— y se abre y se cierra igual que él. El contexto
    // (objetos, aislar, zona, luz) vive arriba, en la fila de Deshacer/Rehacer.
    val railHeight = (LocalConfiguration.current.screenHeightDp - 260).coerceAtLeast(120).dp

    MaterialToolRail(
        material = material,
        stylusOnly = state.materialStylusOnly,
        vm = vm,
        modifier = Modifier
            .align(Alignment.CenterStart)
            .padding(start = Metrics.EdgeMargin)
            .heightIn(max = railHeight),
    )

    if (!libraryOpen) FloatingPanel(
        Modifier.align(Alignment.TopEnd).padding(top = 142.dp, end = Metrics.EdgeMargin),
    ) {
        IconAction(AppIcons.materials, "Abrir biblioteca de materiales") { libraryOpen = true }
    }

    if (libraryOpen) MaterialLibrary(
        material = material,
        vm = vm,
        onColor = { colorsOpen = true },
        onImport = { importer.launch(arrayOf("application/json", "text/plain", "application/octet-stream")) },
        onSave = {
            saveName = material.presets.firstOrNull { it.id == material.preset }?.label.orEmpty()
            saveOpen = true
        },
        onClose = { libraryOpen = false },
        modifier = Modifier
            .align(Alignment.TopEnd)
            .padding(top = 142.dp, end = Metrics.EdgeMargin, bottom = 114.dp),
    )

    MaterialBrushTray(
        material = material,
        stylusOnly = state.materialStylusOnly,
        vm = vm,
        onColor = { colorsOpen = true },
        modifier = Modifier.align(Alignment.BottomCenter).fillMaxWidth().padding(Metrics.EdgeMargin),
    )

    if (colorsOpen) SimpleColorDialog(material.color, { colorsOpen = false }) {
        vm.materialSettings(mapOf("color" to it)); colorsOpen = false
    }
    if (saveOpen) AlertDialog(onDismissRequest = { saveOpen = false }, title = { Text("Guardar material") },
        text = { Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Se guarda tal como se ve —material, color, acabado, ajustes y grano— en el catálogo de esta escena.")
            Text(surfaceSummary(material.surface), color = Ink.Accent, fontSize = 13.sp)
            OutlinedTextField(saveName, { saveName = it }, label = { Text("Nombre") }, singleLine = true)
        } }, confirmButton = { TextButton(enabled = saveName.isNotBlank(), onClick = {
            vm.materialCommand("material.save", mapOf("label" to saveName.trim())); saveOpen = false
        }) { Text("Guardar") } }, dismissButton = { TextButton(onClick = { saveOpen = false }) { Text("Cancelar") } })
}

/**
 * Sobre qué se pinta —objetos, aislamiento, zona y luz— en la fila del ojo, junto a
 * Deshacer/Rehacer.
 *
 * Ningún otro modo abre una segunda franja horizontal bajo el menú, así que
 * Materiales tampoco: son cinco iconos en el panel que ya existe. Lo que no cabe en
 * un símbolo —cuántos objetos hay, qué zona está elegida— se dice con la marca del
 * icono y con el desplegable, no con una etiqueta permanente ocupando el viewport.
 */
@Composable
fun MaterialTopActions(state: AppUiState, vm: MainViewModel) {
    val material = state.blender.material
    var objectsOpen by remember { mutableStateOf(false) }
    var zoneOpen by remember { mutableStateOf(false) }
    var lightOpen by remember { mutableStateOf(false) }
    var groupOpen by remember { mutableStateOf(false) }
    var groupName by remember { mutableStateOf("Zona de pintura") }
    val targets = material.targets.size
    val zone = material.regions.firstOrNull { it.id == material.scope }

    Box {
        IconAction(AppIcons.material("OBJECTS"),
            if (targets == 0) "Sin objetos elegidos" else "Objetos: " + material.targets.joinToString(),
            selected = targets > 0) { objectsOpen = true }
        if (targets > 0) MaterialBadge(targets.toString())
        DropdownMenu(objectsOpen, { objectsOpen = false }, Modifier.heightIn(max = 360.dp)) {
            material.objects.forEach { obj ->
                DropdownMenuItem(text = { Text(obj.label) }, leadingIcon = {
                    Checkbox(obj.id in material.targets, onCheckedChange = null)
                }, onClick = {
                    val next = if (obj.id in material.targets) material.targets - obj.id else material.targets + obj.id
                    vm.materialCommand("material.select", mapOf("objects" to next))
                })
            }
        }
    }
    IconAction(AppIcons.material("ISOLATE"), "Aislar la selección para trabajar dentro",
        selected = material.isolate, enabled = targets > 0) {
        vm.materialSettings(mapOf("isolate" to !material.isolate))
    }
    Box {
        IconAction(AppIcons.material(if (material.scope == "ALL") "ZONE_ALL" else "ZONE"),
            "Zona: " + (zone?.label ?: "objeto completo"), selected = material.scope != "ALL") { zoneOpen = true }
        DropdownMenu(zoneOpen, { zoneOpen = false }, Modifier.heightIn(max = 360.dp)) {
            material.regions.forEach { region ->
                DropdownMenuItem(text = { Text(region.label) }, trailingIcon = {
                    if (region.id == material.scope) Icon(Icons.Default.Check, null, tint = Ink.Accent)
                }, onClick = { zoneOpen = false; vm.materialSettings(mapOf("scope" to region.id)) })
            }
        }
    }
    IconAction(AppIcons.material("SAVE_ZONE"), "Guardar la selección de Edit como zona",
        enabled = targets > 0) { groupOpen = true }
    Box {
        IconAction(AppIcons.material("LIGHT"),
            "Luz: " + (material.environments.firstOrNull { it.id == material.environment }?.label ?: "estudio")) { lightOpen = true }
        DropdownMenu(lightOpen, { lightOpen = false }, Modifier.heightIn(max = 360.dp)) {
            material.environments.forEach { env ->
                DropdownMenuItem(text = { Text(env.label) }, trailingIcon = {
                    if (env.id == material.environment) Icon(Icons.Default.Check, null, tint = Ink.Accent)
                }, onClick = { lightOpen = false; vm.materialSettings(mapOf("environment" to env.id)) })
            }
        }
    }
    if (groupOpen) AlertDialog(onDismissRequest = { groupOpen = false }, title = { Text("Guardar zona de pintura") },
        text = { Column {
            Text("Guarda los vértices seleccionados en Edit. La zona incluye las caras cuyos vértices pertenecen al grupo.")
            OutlinedTextField(groupName, { groupName = it }, label = { Text("Nombre") }, singleLine = true)
        } }, confirmButton = { TextButton(enabled = groupName.isNotBlank(), onClick = {
            vm.materialCommand("material.group", mapOf("name" to groupName.trim())); groupOpen = false
        }) { Text("Guardar") } }, dismissButton = { TextButton(onClick = { groupOpen = false }) { Text("Cancelar") } })
}

/** Cuántos objetos hay debajo del icono, en la esquina, como los badges del rail. */
@Composable
private fun BoxScope.MaterialBadge(label: String) {
    Box(
        Modifier.align(Alignment.BottomEnd).padding(2.dp).size(14.dp)
            .clip(RoundedCornerShape(4.dp)).background(Ink.PanelSolid),
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = Ink.Accent, fontSize = 9.sp, fontWeight = FontWeight.Bold)
    }
}

/** Qué hace el dedo y con qué punta: lo único que cambia durante un trazo. */
@Composable
private fun MaterialToolRail(
    material: MaterialState,
    stylusOnly: Boolean,
    vm: MainViewModel,
    modifier: Modifier = Modifier,
) {
    val painting = material.interaction == "PAINT"
    ToolRail(modifier) {
        RailLabel("MODO")
        IconAction(AppIcons.material("SELECT"), "Tocar para elegir objetos", selected = material.interaction == "SELECT") {
            vm.materialSettings(mapOf("interaction" to "SELECT"))
        }
        IconAction(AppIcons.material("PAINT"), "Pintar con el material elegido",
            selected = painting && !material.erase, enabled = material.targets.isNotEmpty()) {
            vm.materialSettings(mapOf("interaction" to "PAINT", "erase" to false))
        }
        IconAction(AppIcons.material("ERASE"), "Retirar la capa pintada",
            selected = painting && material.erase, enabled = material.paintReady) {
            vm.materialSettings(mapOf("interaction" to "PAINT", "erase" to true))
        }
        IconAction(AppIcons.material("LIGHTS"), "Mover luces", selected = material.interaction == "LIGHTS") {
            vm.materialSettings(mapOf("interaction" to "LIGHTS"))
        }
        RailDivider()
        RailLabel("TRAZO")
        material.brushes.forEach { brush ->
            IconAction(AppIcons.material(brush.id), brush.label, selected = material.brush == brush.id,
                enabled = material.paintReady) {
                vm.materialSettings(mapOf("brush" to brush.id))
            }
        }
        RailDivider()
        IconAction(AppIcons.material("STYLUS"), "Solo el lápiz pinta; el dedo gira la vista",
            selected = stylusOnly, onClick = vm::toggleMaterialStylus)
    }
}

/**
 * La biblioteca responde tres preguntas distintas —de qué es, cómo está acabado y
 * qué textura tiene— y por eso son tres pestañas y no una lista interminable.
 *
 * Cada opción trae su explicación desde el servidor y se enseña la del elemento
 * elegido: el usuario no tiene que saber qué es el IOR para entender que va de
 * aire a diamante. Los ajustes finos son los mismos parámetros del shader, así que
 * quien sepa puede llegar hasta el final sin salir de aquí.
 *
 * Aplicar vive al pie del panel y no dentro de una pestaña: material, acabado y
 * grano forman una sola receta y se asignan de una vez, así que el botón tiene que
 * significar lo mismo se esté mirando donde se esté mirando.
 */
@Composable
private fun MaterialLibrary(
    material: MaterialState,
    vm: MainViewModel,
    onColor: () -> Unit,
    onImport: () -> Unit,
    onSave: () -> Unit,
    onClose: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var tab by rememberSaveable { mutableStateOf("material") }
    FloatingPanel(modifier.heightIn(max = 560.dp)) {
        Column(Modifier.width(240.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                IconAction(Icons.AutoMirrored.Filled.ArrowBack, "Cerrar biblioteca", onClick = onClose)
                Text("MATERIALES", color = Ink.Accent, fontSize = 11.sp, fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.weight(1f).padding(start = 2.dp))
            }
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                listOf("material" to "Material", "finish" to "Acabado", "grain" to "Grano").forEach { (id, label) ->
                    PillButton(label, Modifier.weight(1f), selected = tab == id) { tab = id }
                }
            }
            Column(
                Modifier.weight(1f, fill = false).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                when (tab) {
                    "finish" -> FinishTab(material, vm)
                    "grain" -> GrainTab(material, vm)
                    else -> BaseTab(material, vm, onColor, onImport, onSave)
                }
            }
            ApplyButton(
                label = if (material.scope == "ALL") "Aplicar a la selección" else "Aplicar a la zona",
                enabled = material.targets.isNotEmpty() &&
                    (material.scope == "ALL" || (material.paintReady && !material.paintBlocked)),
            ) { vm.materialCommand("material.apply") }
        }
    }
}

@Composable
private fun ColumnScope.BaseTab(
    material: MaterialState,
    vm: MainViewModel,
    onColor: () -> Unit,
    onImport: () -> Unit,
    onSave: () -> Unit,
) {
    SectionLabel("BASE")
    PresetGrid(material.presets.filter { it.category == "base" }, material.preset) {
        vm.materialSettings(mapOf("preset" to it))
    }
    SectionLabel("COLOR")
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        // Sin tinte, cada material se ve con el suyo: se puede recorrer el catálogo
        // entero sin perder el oro por haber tocado el color una vez.
        SwatchChip("Del material", parseColor(material.presets.firstOrNull { it.id == material.preset }?.color ?: material.color),
            selected = !material.tinted) { vm.materialSettings(mapOf("color" to JSONObject.NULL)) }
        SwatchChip("Tinte", parseColor(material.color), selected = material.tinted, onClick = onColor)
    }
    SectionLabel("DETALLE")
    PresetGrid(material.presets.filter { it.category == "detail" }, material.preset) { id ->
        vm.materialSettings(mapOf("preset" to id, "color" to JSONObject.NULL, "finish" to "natural", "erase" to false))
    }
    SectionLabel("BIBLIOTECA")
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        PillButton("Guardar…", Modifier.weight(1f), onClick = onSave)
        PillButton("Importar…", Modifier.weight(1f), onClick = onImport)
    }
}

@Composable
private fun ColumnScope.FinishTab(material: MaterialState, vm: MainViewModel) {
    SectionLabel("ACABADO")
    PresetGrid(material.finishes, if (material.custom) "" else material.finish) {
        vm.materialSettings(mapOf("finish" to it))
    }
    val finish = material.finishes.firstOrNull { it.id == material.finish }
    Text(
        if (material.custom) "Ajustado a mano desde ${finish?.label ?: "el acabado"}." else finish?.hint.orEmpty(),
        color = Ink.Faint, fontSize = 11.sp,
    )
    Text(surfaceSummary(material.surface), color = Ink.Accent, fontSize = 12.sp)
    SectionLabel("AJUSTE FINO")
    material.surfaceControls.forEach { control ->
        // La densidad óptica solo describe algo que deja pasar la luz: en un opaco
        // sería un mando que no hace nada visible.
        if (control.id != "ior" || (material.surface["transmission"] ?: 0f) > 0f) {
            val value = material.surface[control.id] ?: control.min
            LabeledSlider(control.label, formatSurface(control, value), value, control.min..control.max,
                control.low, control.high) {
                vm.materialSettings(mapOf("surface" to mapOf(control.id to it)))
            }
        }
    }
    if (material.custom) PillButton("Volver al acabado", Modifier.fillMaxWidth()) {
        vm.materialSettings(mapOf("finish" to material.finish))
    }
}

@Composable
private fun ColumnScope.GrainTab(material: MaterialState, vm: MainViewModel) {
    SectionLabel("TEXTURA")
    PresetGrid(material.grains.map { it.copy(color = "") }, material.grain) { vm.materialSettings(mapOf("grain" to it)) }
    Text(material.grains.firstOrNull { it.id == material.grain }?.hint.orEmpty(), color = Ink.Faint, fontSize = 11.sp)
    if (material.grain != "none") {
        LabeledSlider("Tamaño", "${material.grainScale.roundToInt()}", material.grainScale, 1f..120f, "Grande", "Fino") {
            vm.materialSettings(mapOf("grain_scale" to it))
        }
        LabeledSlider("Intensidad", "${(material.grainAmount * 100).roundToInt()} %", material.grainAmount, 0f..1f,
            "Apenas", "Marcada") { vm.materialSettings(mapOf("grain_amount" to it)) }
        LabeledSlider("Relieve", "${(material.grainRelief * 100).roundToInt()} %", material.grainRelief, 0f..1f,
            "Liso", "Rugoso") { vm.materialSettings(mapOf("grain_relief" to it)) }
        Text("La textura se tiñe con el color del material y se añade a la receta al aplicar o pintar.",
            color = Ink.Faint, fontSize = 11.sp)
    }
}

/** Traduce los cinco números del shader a la frase que describiría un ojo humano. */
internal fun surfaceSummary(surface: Map<String, Float>): String {
    if (surface.isEmpty()) return ""
    val roughness = surface["roughness"] ?: .5f
    val body = when {
        (surface["transmission"] ?: 0f) > .5f -> "Transparente"
        (surface["metallic"] ?: 0f) > .6f -> "Metal"
        else -> "No metálico"
    }
    val gloss = when {
        roughness < .15f -> "espejo"
        roughness < .35f -> "brillante"
        roughness < .6f -> "satinado"
        roughness < .85f -> "poco brillo"
        else -> "mate"
    }
    return body + " · " + gloss + if ((surface["coat"] ?: 0f) > .5f) " · barnizado" else ""
}

private fun formatSurface(control: SurfaceControl, value: Float): String =
    if (control.max > 1f) String.format(Locale.ROOT, "%.2f", value) else "${(value * 100).roundToInt()} %"

/** Los dos ajustes continuos del pincel y qué está haciendo ahora mismo. */
@Composable
private fun MaterialBrushTray(
    material: MaterialState,
    stylusOnly: Boolean,
    vm: MainViewModel,
    onColor: () -> Unit,
    modifier: Modifier = Modifier,
) {
    if (material.interaction == "LIGHTS") {
        // «Original» y el botón apagado son la respuesta a no saber si el reseteo
        // devolvió la luz a su sitio: en cuanto lo está, se dice y no hay nada que
        // restaurar. El ambiente elegido tiene su propio giro, así que 0° significa
        // el de ese ambiente, no mirar al eje X del mundo.
        val moved = material.lightRotation.roundToInt() != 0 || (material.lightEnergy * 100).roundToInt() != 100
        FloatingPanel(modifier) {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Icon(AppIcons.material("LIGHTS"), contentDescription = null, tint = Ink.Accent)
                    Text(
                        if (moved) "Luz · ${material.lightRotation.roundToInt()}° · ${(material.lightEnergy * 100).roundToInt()} %"
                        else "Luz · original del ambiente",
                        color = if (moved) Ink.OnPanel else Ink.Ok, fontSize = 13.sp,
                    )
                    PillButton("Restaurar luces", enabled = moved) {
                        vm.materialCommand("material.lighting", mapOf("phase" to "reset"))
                    }
                }
                Text("Arrastra en horizontal para girar la luz y en vertical para subirla o bajarla de intensidad. " +
                    "Blender no permite elevar el foco del ambiente. Dos dedos navegan.",
                    color = Ink.Faint, fontSize = 11.sp)
            }
        }
        return
    }
    FloatingPanel(modifier) {
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(
                Modifier.horizontalScroll(rememberScrollState()),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Row(
                    Modifier.clip(RoundedCornerShape(9.dp)).clickableNoRipple(onColor).padding(horizontal = 4.dp, vertical = 2.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Box(Modifier.size(26.dp).background(parseColor(material.color), CircleShape)
                        .border(1.dp, Ink.Divider, CircleShape))
                    Spacer(Modifier.width(8.dp))
                    Column {
                        Text(
                            material.presets.firstOrNull { it.id == material.preset }?.label ?: "Material",
                            color = if (material.erase) Ink.Warn else Ink.Accent, fontSize = 13.sp,
                        )
                        Text(surfaceSummary(material.surface), color = Ink.Faint, fontSize = 10.sp)
                    }
                }
                MaterialSlider("Tamaño", material.radius, .005f.. .25f) { vm.materialSettings(mapOf("radius" to it)) }
                MaterialSlider("Intensidad", material.strength, 0f..1f) { vm.materialSettings(mapOf("strength" to it)) }
                Text(
                    material.brushes.firstOrNull { it.id == material.brush }?.label.orEmpty(),
                    color = Ink.Muted, fontSize = 12.sp,
                )
            }
            Text(materialHint(material, stylusOnly), color = Ink.Faint, fontSize = 11.sp, maxLines = 2)
        }
    }
}

/** Una sola línea de ayuda: la del obstáculo actual, no la de todo el flujo. */
private fun materialHint(material: MaterialState, stylusOnly: Boolean): String = when {
    material.paintBlocked ->
        "El pincel admite ${material.paintLimit} caras base. Puedes aplicar materiales completos o usar una base más ligera con Subdivisión sin aplicar."
    material.targets.isEmpty() -> "Toca un objeto para elegirlo. La lista de arriba permite varios o piezas interiores."
    material.interaction == "SELECT" -> "Modo selección: el toque elige objetos. Vuelve al pincel del rail para pintar."
    !material.paintReady -> "Aplica una base a la selección para poder pintar encima."
    material.erase -> "Borrar retira la capa superior por donde pasa el pincel y deja ver lo de debajo."
    material.scope != "ALL" -> "Solo se pintan caras completas de la zona elegida; selecciónalas en Edit y guárdalas como zona."
    stylusOnly -> "Lápiz pinta · dedo gira · dos dedos navegan. La presión modula la intensidad."
    else -> "Dedo o lápiz pintan · dos dedos navegan. El tinte se conserva al cambiar de material."
}

@Composable
private fun SectionLabel(text: String) {
    Text(text, color = Ink.Faint, fontSize = 9.sp, fontWeight = FontWeight.SemiBold)
}

/** Rejilla de fichas: el color de cada material se ve antes de leer su nombre. */
@Composable
private fun PresetGrid(options: List<MaterialPreset>, selected: String, choose: (String) -> Unit) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        options.forEach { option ->
            SwatchChip(option.label, option.color.takeIf { it.isNotBlank() }?.let(::parseColor),
                option.id == selected) { choose(option.id) }
        }
    }
}

/**
 * Slider con los dos extremos escritos: el número dice cuánto y las palabras dicen
 * de qué, que es lo que falta para tocar «Densidad óptica» sin miedo.
 */
@Composable
private fun LabeledSlider(
    label: String,
    valueText: String,
    remote: Float,
    range: ClosedFloatingPointRange<Float>,
    low: String,
    high: String,
    onValue: (Float) -> Unit,
) {
    var value by remember { mutableFloatStateOf(remote.coerceIn(range)) }
    var dragging by remember { mutableStateOf(false) }
    LaunchedEffect(remote, range) { if (!dragging) value = remote.coerceIn(range) }
    Column(Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(label, color = Ink.Muted, fontSize = 11.sp)
            Text(valueText, color = Ink.OnPanel, fontSize = 11.sp)
        }
        Slider(value, onValueChange = { dragging = true; value = it }, valueRange = range,
            onValueChangeFinished = { dragging = false; onValue(value) }, modifier = Modifier.height(28.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(low, color = Ink.Faint, fontSize = 9.sp)
            Text(high, color = Ink.Faint, fontSize = 9.sp)
        }
    }
}

@Composable
private fun SwatchChip(label: String, color: Color?, selected: Boolean, onClick: () -> Unit) {
    Row(
        Modifier
            .height(32.dp)
            .clip(RoundedCornerShape(9.dp))
            .background(if (selected) Ink.Accent.copy(alpha = .22f) else Color.White.copy(alpha = .05f))
            .then(if (selected) Modifier.border(1.dp, Ink.Accent.copy(alpha = .5f), RoundedCornerShape(9.dp)) else Modifier)
            .clickableNoRipple(onClick)
            .padding(horizontal = 9.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (color != null) {
            Box(Modifier.size(12.dp).background(color, CircleShape).border(1.dp, Ink.Divider, CircleShape))
            Spacer(Modifier.width(6.dp))
        }
        Text(label, color = if (selected) Ink.Accent else Ink.Muted, fontSize = 12.sp, maxLines = 1)
    }
}

/** Aplicar sustituye el material de los objetos: pesa más que elegir una ficha. */
@Composable
private fun ApplyButton(label: String, enabled: Boolean, onClick: () -> Unit) {
    Box(
        Modifier
            .fillMaxWidth()
            .height(38.dp)
            .clip(RoundedCornerShape(10.dp))
            .background(if (enabled) Ink.Accent.copy(alpha = .22f) else Color.White.copy(alpha = .04f))
            .then(if (enabled) Modifier.border(1.dp, Ink.Accent.copy(alpha = .6f), RoundedCornerShape(10.dp)) else Modifier)
            .then(if (enabled) Modifier.clickableNoRipple(onClick) else Modifier),
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = if (enabled) Ink.Accent else Ink.Faint, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun MaterialSlider(label: String, remote: Float, range: ClosedFloatingPointRange<Float>, choose: (Float) -> Unit) {
    var value by remember(remote) { mutableFloatStateOf(remote.coerceIn(range)) }
    Column(Modifier.width(150.dp)) {
        Text("$label · ${(value * 100).roundToInt()} %", color = Ink.Muted, fontSize = 11.sp)
        Slider(value, { value = it }, valueRange = range, onValueChangeFinished = { choose(value) }, modifier = Modifier.height(30.dp))
    }
}

private fun parseColor(value: String) = runCatching { Color(android.graphics.Color.parseColor(value)) }.getOrDefault(Color.Gray)

@Composable
private fun SimpleColorDialog(initial: String, dismiss: () -> Unit, choose: (String) -> Unit) {
    val hsv = remember(initial) { FloatArray(3).also { android.graphics.Color.colorToHSV(parseColor(initial).toArgb(), it) } }
    var hue by remember { mutableFloatStateOf(hsv[0]) }
    var saturation by remember { mutableFloatStateOf(hsv[1]) }
    var brightness by remember { mutableFloatStateOf(hsv[2]) }
    val color = Color.hsv(hue, saturation, brightness)
    AlertDialog(onDismissRequest = dismiss, title = { Text("Elige un color") }, text = {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Box(Modifier.fillMaxWidth().height(50.dp).background(color))
            listOf(listOf("#FFFFFF", "#B8B8B8", "#555555", "#141414", "#805133", "#E8C29C"),
                listOf("#E84B40", "#EF8C30", "#F2D34F", "#55AD65", "#428CD9", "#925BCD")).forEach { row ->
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    row.forEach { swatch -> Box(Modifier.size(36.dp).background(parseColor(swatch), CircleShape).clickableNoRipple {
                        android.graphics.Color.colorToHSV(parseColor(swatch).toArgb(), hsv)
                        hue = hsv[0]; saturation = hsv[1]; brightness = hsv[2]
                    }) }
                }
            }
            Text("Color"); Slider(hue, { hue = it }, valueRange = 0f..359.9f)
            Text("Vivo o apagado"); Slider(saturation, { saturation = it })
            Text("Claro u oscuro"); Slider(brightness, { brightness = it })
        }
    }, confirmButton = { TextButton(onClick = { choose("#%06X".format(color.toArgb() and 0xFFFFFF)) }) { Text("Usar color") } },
        dismissButton = { TextButton(onClick = dismiss) { Text("Cancelar") } })
}

/** SAF works from Android 8 without storage permission, in every workspace. */
@Composable
fun CaptureSceneDelivery(vm: MainViewModel) {
    val png by vm.capturePng.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var launched by rememberSaveable { mutableStateOf(false) }
    val saver = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("image/png")) { uri: Uri? ->
        val encoded = png
        launched = false
        vm.clearCapture()
        if (uri != null && encoded != null) scope.launch {
            runCatching {
                withContext(Dispatchers.IO) {
                    val bytes = Base64.decode(encoded, Base64.DEFAULT)
                    context.contentResolver.openOutputStream(uri)?.use { it.write(bytes) } ?: error("No se pudo guardar la imagen")
                }
            }.onSuccess { Toast.makeText(context, "Captura guardada", Toast.LENGTH_SHORT).show() }
                .onFailure { Toast.makeText(context, "No se pudo guardar: ${it.message}", Toast.LENGTH_LONG).show() }
        }
    }
    LaunchedEffect(png) {
        if (png != null && !launched) {
            launched = true
            saver.launch("Blender-${SimpleDateFormat("yyyyMMdd-HHmmss", Locale.ROOT).format(Date())}.png")
        }
    }
}

private fun java.io.InputStream.readBytesBounded(limit: Int): ByteArray {
    val out = java.io.ByteArrayOutputStream()
    val buffer = ByteArray(4096)
    while (true) {
        val size = read(buffer)
        if (size < 0) return out.toByteArray()
        require(out.size() + size <= limit) { "El material supera 64 KiB" }
        out.write(buffer, 0, size)
    }
}
