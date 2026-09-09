package com.blendertablet.remote.ui

import android.graphics.BitmapFactory
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.blendertablet.remote.data.ReferenceImages
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlin.math.roundToInt

/** Reference-board gestures stay on its card; the surrounding canvas keeps its single InputSurface. */
@Composable
fun BoxScope.ReferencePanel(modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val store = remember(context) { ReferenceImages(context.applicationContext) }
    val scope = rememberCoroutineScope()
    var images by remember { mutableStateOf(store.list()) }
    DisposableEffect(store) {
        val stopObserving = store.observe { images = it }
        onDispose { stopObserving() }
    }
    var selectedId by rememberSaveable { mutableStateOf<String?>(null) }
    var open by rememberSaveable { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var large by rememberSaveable { mutableStateOf(false) }
    var opacity by rememberSaveable { mutableFloatStateOf(1f) }
    var offset by remember { mutableStateOf(Offset.Zero) }
    val selected = images.firstOrNull { it.id == selectedId } ?: images.firstOrNull()
    var zoom by remember(selected?.id) { mutableFloatStateOf(1f) }
    var pan by remember(selected?.id) { mutableStateOf(Offset.Zero) }
    val bitmap by produceState<android.graphics.Bitmap?>(null, selected?.path) {
        value = null
        value = withContext(Dispatchers.IO) { selected?.let { BitmapFactory.decodeFile(it.path) } }
    }
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        if (uris.isNotEmpty()) scope.launch {
            busy = true
            error = null
            open = true
            try {
                for (uri in uris) {
                    try {
                        val imported = withContext(Dispatchers.IO) { store.import(uri) }
                        selectedId = imported.id
                    } catch (failure: Exception) {
                        if (failure is kotlinx.coroutines.CancellationException) throw failure
                        error = failure.message ?: "No se pudo importar la referencia"
                    }
                }
            } finally { busy = false }
        }
    }
    val config = LocalConfiguration.current
    val cardWidth = minOf(if (large) 460 else 310, config.screenWidthDp - 32).dp
    val cardHeight = minOf(if (large) 320 else 210, (config.screenHeightDp - 320).coerceAtLeast(100)).dp
    val density = LocalDensity.current
    var panelHeight by remember { mutableIntStateOf(0) }
    val horizontalLimit = with(density) { ((config.screenWidthDp.dp - cardWidth) / 2).toPx().coerceAtLeast(0f) }
    val verticalLimit = with(density) { ((config.screenHeightDp.dp - 84.dp).toPx() - panelHeight).coerceAtLeast(0f) }
    LaunchedEffect(horizontalLimit, verticalLimit) {
        offset = Offset(offset.x.coerceIn(-horizontalLimit, horizontalLimit), offset.y.coerceIn(0f, verticalLimit))
    }
    Column(modifier.offset { IntOffset(offset.x.roundToInt(), offset.y.roundToInt()) }.onSizeChanged { panelHeight = it.height }, horizontalAlignment = Alignment.CenterHorizontally) {
        if (!open) FloatingPanel {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconAction(AppIcons.Reference, "Abrir imágenes de referencia") { open = true }
                PillButton("Referencias") { open = true }
            }
        } else FloatingPanel(Modifier.width(cardWidth)) {
            Column(Modifier.padding(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text("Referencias · mover", color = Ink.OnPanel, fontSize = 12.sp,
                        modifier = Modifier.weight(1f).height(40.dp).wrapContentHeight().pointerInput(horizontalLimit, verticalLimit) {
                            detectDragGestures { change, drag ->
                                change.consume()
                                offset = Offset((offset.x + drag.x).coerceIn(-horizontalLimit, horizontalLimit),
                                    (offset.y + drag.y).coerceIn(0f, verticalLimit))
                            }
                        })
                    PillButton("Ocultar") { open = false }
                }
                Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    PillButton(if (busy) "Cargando…" else "+ Imagen", enabled = !busy) { launcher.launch(arrayOf("image/*")) }
                    PillButton(if (large) "Compacta" else "Ampliar") { large = !large }
                    if (selected != null) PillButton("Quitar", enabled = !busy) {
                        scope.launch {
                            busy = true
                            try {
                                withContext(Dispatchers.IO) { store.remove(selected) }
                            } catch (failure: Exception) {
                                if (failure is kotlinx.coroutines.CancellationException) throw failure
                                error = failure.message
                            } finally { busy = false }
                        }
                    }
                }
                if (images.size > 1) Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    images.forEachIndexed { index, image ->
                        key(image.id) { PillButton("${index + 1}", selected = image.id == selected?.id) { selectedId = image.id } }
                    }
                }
                Box(Modifier.fillMaxWidth().height(cardHeight).clipToBounds().background(Ink.Background)
                    .pointerInput(selected?.id) {
                        detectTransformGestures { _, drag, scale, _ ->
                            zoom = (zoom * scale).coerceIn(1f, 8f)
                            val maxX = size.width * (zoom - 1f) / 2f
                            val maxY = size.height * (zoom - 1f) / 2f
                            pan = Offset((pan.x + drag.x).coerceIn(-maxX, maxX), (pan.y + drag.y).coerceIn(-maxY, maxY))
                        }
                    }, contentAlignment = Alignment.Center) {
                    bitmap?.let { image ->
                        Image(image.asImageBitmap(), selected?.name, contentScale = ContentScale.Fit,
                            modifier = Modifier.fillMaxSize().graphicsLayer {
                                scaleX = zoom; scaleY = zoom; translationX = pan.x; translationY = pan.y; alpha = opacity
                            })
                    } ?: Text(if (selected == null) "Añade fotos o dibujos desde la tablet" else "Cargando imagen…",
                        color = Ink.Muted, fontSize = 12.sp, modifier = Modifier.padding(16.dp))
                }
                if (selected != null) {
                    Text(selected.name, color = Ink.Muted, fontSize = 11.sp, maxLines = 1)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        IconAction(AppIcons.Reset, "Encuadrar referencia") { zoom = 1f; pan = Offset.Zero; opacity = 1f }
                        Text("Opacidad", color = Ink.Muted, fontSize = 11.sp)
                        Slider(opacity, { opacity = it }, valueRange = .15f..1f, modifier = Modifier.weight(1f))
                    }
                }
                error?.let { Text(it, color = MaterialTheme.colorScheme.error, fontSize = 11.sp) }
            }
        }
    }
}
