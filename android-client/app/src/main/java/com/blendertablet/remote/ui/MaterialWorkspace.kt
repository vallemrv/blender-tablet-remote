package com.blendertablet.remote.ui

import android.net.Uri
import android.util.Base64
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.blendertablet.remote.MainViewModel
import com.blendertablet.remote.model.AppUiState
import com.blendertablet.remote.model.MaterialPreset
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.roundToInt

@Composable
fun BoxScope.MaterialWorkspace(state: AppUiState, vm: MainViewModel) {
    val material = state.blender.material
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var colorsOpen by rememberSaveable { mutableStateOf(false) }
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
    FloatingPanel(Modifier.align(Alignment.BottomCenter).fillMaxWidth().padding(Metrics.EdgeMargin)) {
        Column(Modifier.padding(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(Modifier.horizontalScroll(rememberScrollState()), verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Materiales · ${material.targets.size} objeto${if (material.targets.size == 1) "" else "s"}", color = Ink.Muted, fontSize = 12.sp)
                MaterialPicker("1 · Base", material.presets.filter { it.category == "base" }, material.preset) { vm.materialSettings(mapOf("preset" to it)) }
                Box(Modifier.size(32.dp).background(parseColor(material.color), CircleShape)
                    .border(1.dp, Ink.OnPanel, CircleShape).clickable { colorsOpen = true })
                PillButton("2 · Tinte") { colorsOpen = true }
                MaterialPicker("3 · Acabado", material.finishes, material.finish) { vm.materialSettings(mapOf("finish" to it)) }
                PillButton("Aplicar a todo") { vm.materialCommand("material.apply") }
                MaterialPicker("Ambiente", material.environments, material.environment) { vm.materialSettings(mapOf("environment" to it)) }
                PillButton("Importar material…") { importer.launch(arrayOf("application/json", "text/plain", "application/octet-stream")) }
            }
            Text("El tinte se conserva al cambiar de base. Aplicar a todo sustituye la base; pinta los detalles con el lápiz.", color = Ink.Faint, fontSize = 11.sp)
            Row(Modifier.horizontalScroll(rememberScrollState()), verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                MaterialPicker("4 · Detalle", material.presets.filter { it.category == "detail" }, material.preset) { id ->
                    val detail = material.presets.first { it.id == id }
                    vm.materialSettings(mapOf("preset" to id, "color" to detail.color, "finish" to "natural", "erase" to false))
                }
                Text(if (material.paintReady) "Pincel · ${material.presets.find { it.id == material.preset }?.label.orEmpty()}" else "Aplica una base para pintar", color = Ink.Muted, fontSize = 12.sp)
                PillButton("Borrar pintura", selected = material.erase, enabled = material.paintReady) { vm.materialSettings(mapOf("erase" to !material.erase)) }
                MaterialSlider("Tamaño del pincel", material.radius, .005f.. .25f) { vm.materialSettings(mapOf("radius" to it)) }
                MaterialSlider("Intensidad", material.strength, 0f..1f) { vm.materialSettings(mapOf("strength" to it)) }
                PillButton("Solo lápiz", selected = state.materialStylusOnly, onClick = vm::toggleMaterialStylus)
                Text(if (state.materialStylusOnly) "Lápiz pinta · dedo gira · dos dedos navegan" else "Dedo o lápiz pintan · dos dedos navegan", color = Ink.Faint, fontSize = 11.sp)
            }
        }
    }
    if (colorsOpen) SimpleColorDialog(material.color, { colorsOpen = false }) {
        vm.materialSettings(mapOf("color" to it)); colorsOpen = false
    }
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
    Column(Modifier.width(156.dp)) {
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
                    row.forEach { swatch -> Box(Modifier.size(36.dp).background(parseColor(swatch), CircleShape).clickable {
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
