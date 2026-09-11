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
    var groupOpen by remember { mutableStateOf(false) }
    var groupName by remember { mutableStateOf("Zona de pintura") }
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
    // La biblioteca arranca bajo el rail de modos (igual que el inspector de
    // modificadores) y la barra de contexto termina antes de él: los tres comparten
    // la franja superior y ninguno puede taparse con otro.
    val screen = LocalConfiguration.current
    val railHeight = (screen.screenHeightDp - 260).coerceAtLeast(120).dp
    val libraryHeight = (screen.screenHeightDp - 266).coerceAtLeast(180).dp
    val contextWidth = (screen.screenWidthDp - 320).coerceAtLeast(240).dp

    MaterialContextBar(
        material = material,
        vm = vm,
        libraryOpen = libraryOpen,
        onLibrary = { libraryOpen = !libraryOpen },
        onSaveGroup = { groupOpen = true },
        modifier = Modifier
            .align(Alignment.TopStart)
            .padding(start = Metrics.EdgeMargin, top = 76.dp)
            .widthIn(max = contextWidth),
    )

    MaterialToolRail(
        material = material,
        stylusOnly = state.materialStylusOnly,
        vm = vm,
        modifier = Modifier
            .align(Alignment.CenterStart)
            .padding(start = Metrics.EdgeMargin)
            .heightIn(max = railHeight),
    )

    if (libraryOpen) MaterialLibrary(
        material = material,
        vm = vm,
        onColor = { colorsOpen = true },
        onImport = { importer.launch(arrayOf("application/json", "text/plain", "application/octet-stream")) },
        onSave = {
            saveName = material.presets.firstOrNull { it.id == material.preset }?.label.orEmpty()
            saveOpen = true
        },
        modifier = Modifier
            .align(Alignment.TopEnd)
            .padding(top = 142.dp, end = Metrics.EdgeMargin)
            .heightIn(max = libraryHeight),
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
    if (groupOpen) AlertDialog(onDismissRequest = { groupOpen = false }, title = { Text("Guardar zona de pintura") },
        text = { Column {
            Text("Guarda los vértices seleccionados en Edit. La zona incluye las caras cuyos vértices pertenecen al grupo.")
            OutlinedTextField(groupName, { groupName = it }, label = { Text("Nombre") }, singleLine = true)
        } }, confirmButton = { TextButton(enabled = groupName.isNotBlank(), onClick = {
            vm.materialCommand("material.group", mapOf("name" to groupName.trim())); groupOpen = false
        }) { Text("Guardar") } }, dismissButton = { TextButton(onClick = { groupOpen = false }) { Text("Cancelar") } })
}

/** Sobre qué se pinta: objetos, aislamiento, zona y ambiente de comprobación. */
@Composable
private fun MaterialContextBar(
    material: MaterialState,
    vm: MainViewModel,
    libraryOpen: Boolean,
    onLibrary: () -> Unit,
    onSaveGroup: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var objectsOpen by remember { mutableStateOf(false) }
    val targets = material.targets.size
    FloatingPanel(modifier) {
        Row(
            Modifier.horizontalScroll(rememberScrollState()),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Box {
                PillButton(
                    when (targets) {
                        0 -> "Sin objetos"
                        1 -> material.objects.firstOrNull { it.id == material.targets.first() }?.label ?: "1 objeto"
                        else -> "$targets objetos"
                    },
                    selected = targets > 0,
                ) { objectsOpen = true }
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
            RailSeparator()
            MaterialPicker("Zona", material.regions, material.scope) { vm.materialSettings(mapOf("scope" to it)) }
            IconAction(AppIcons.material("SAVE_ZONE"), "Guardar la selección de Edit como zona", enabled = targets > 0,
                onClick = onSaveGroup)
            RailSeparator()
            MaterialPicker("Luz", material.environments, material.environment) { vm.materialSettings(mapOf("environment" to it)) }
            IconAction(AppIcons.materials, "Biblioteca de materiales", selected = libraryOpen, onClick = onLibrary)
        }
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
        IconAction(AppIcons.material("SELECT"), "Tocar para elegir objetos", selected = !painting) {
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
 */
@Composable
private fun MaterialLibrary(
    material: MaterialState,
    vm: MainViewModel,
    onColor: () -> Unit,
    onImport: () -> Unit,
    onSave: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var tab by rememberSaveable { mutableStateOf("material") }
    FloatingPanel(modifier) {
        Column(Modifier.width(240.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                listOf("material" to "Material", "finish" to "Acabado", "grain" to "Grano").forEach { (id, label) ->
                    PillButton(label, Modifier.weight(1f), selected = tab == id) { tab = id }
                }
            }
            Column(
                Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                when (tab) {
                    "finish" -> FinishTab(material, vm)
                    "grain" -> GrainTab(material, vm)
                    else -> BaseTab(material, vm, onColor, onImport, onSave)
                }
            }
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
    val applyEnabled = material.targets.isNotEmpty() &&
        (material.scope == "ALL" || (material.paintReady && !material.paintBlocked))
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
    ApplyButton(
        label = if (material.scope == "ALL") "Aplicar a la selección" else "Aplicar a la zona",
        enabled = applyEnabled,
    ) { vm.materialCommand("material.apply") }
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

/** Separador vertical entre grupos de una barra horizontal. */
@Composable
private fun RailSeparator() {
    Box(Modifier.padding(horizontal = 2.dp).width(1.dp).height(22.dp).background(Ink.Divider))
}

@Composable
private fun MaterialPicker(label: String, options: List<MaterialPreset>, selected: String, choose: (String) -> Unit) {
    var open by remember { mutableStateOf(false) }
    Box {
        PillButton("$label · ${options.find { it.id == selected }?.label ?: "Elegir"}") { open = true }
        DropdownMenu(open, { open = false }, Modifier.heightIn(max = 360.dp)) {
            options.forEach { option ->
                DropdownMenuItem(text = { Text(option.label) }, onClick = { open = false; choose(option.id) })
            }
        }
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
