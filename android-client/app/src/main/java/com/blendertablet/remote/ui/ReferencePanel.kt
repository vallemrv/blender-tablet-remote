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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.foundation.verticalScroll
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.blendertablet.remote.data.ReferenceImage
import com.blendertablet.remote.data.ReferenceImages
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlin.math.roundToInt

/** Reference-board gestures stay on its card; the surrounding canvas keeps its single InputSurface. */
@Composable
fun ReferencePanel(
    modifier: Modifier = Modifier,
    boardId: String,
    /** Copia la imagen elegida a la escena como Imagen de referencia; null si el servidor no lo admite. */
    onSendToBlender: ((ReferenceImage, Float) -> Unit)? = null,
    onDismiss: () -> Unit,
) {
    val context = LocalContext.current
    val store = remember(context) { ReferenceImages(context.applicationContext) }
    val scope = rememberCoroutineScope()
    var images by remember(boardId) { mutableStateOf(store.list(boardId)) }
    var previous by remember { mutableStateOf(store.previous()) }
    val currentBoard by rememberUpdatedState(boardId)
    DisposableEffect(store, boardId) {
        val stopObserving = store.observe { images = store.list(boardId); previous = store.previous() }
        onDispose { stopObserving() }
    }
    var selectedId by rememberSaveable(boardId) { mutableStateOf<String?>(null) }
    var pickerBoard by rememberSaveable { mutableStateOf<String?>(null) }
    var previousOpen by remember(boardId) { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var error by remember(boardId) { mutableStateOf<String?>(null) }
    var large by rememberSaveable { mutableStateOf(false) }
    var opacity by rememberSaveable { mutableFloatStateOf(1f) }
    var offsetX by rememberSaveable { mutableFloatStateOf(Float.NaN) }
    var offsetY by rememberSaveable { mutableFloatStateOf(Float.NaN) }
    val selected = images.firstOrNull { it.id == selectedId } ?: images.firstOrNull()
    var zoom by remember(selected?.id) { mutableFloatStateOf(1f) }
    var pan by remember(selected?.id) { mutableStateOf(Offset.Zero) }
    val bitmap by produceState<android.graphics.Bitmap?>(null, selected?.path) {
        value = null
        value = withContext(Dispatchers.IO) { selected?.let { BitmapFactory.decodeFile(it.path) } }
    }
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        val targetBoard = pickerBoard
        pickerBoard = null
        if (uris.isNotEmpty() && !targetBoard.isNullOrBlank()) scope.launch {
            busy = true
            error = null
            try {
                for (uri in uris) {
                    try {
                        val imported = withContext(Dispatchers.IO) { store.import(uri, targetBoard) }
                        if (currentBoard == targetBoard) selectedId = imported.id
                    } catch (failure: Exception) {
                        if (failure is kotlinx.coroutines.CancellationException) throw failure
                        error = failure.message ?: "No se pudo importar la referencia"
                    }
                }
            } finally { busy = false }
        }
    }
    val density = LocalDensity.current
    BoxWithConstraints(modifier.fillMaxSize()) {
        val cardWidth = minOf(if (large) 460.dp else 310.dp, maxWidth)
        val cardHeight = minOf(if (large) 320.dp else 210.dp,
            (maxHeight - if (selected != null) 254.dp else 180.dp).coerceAtLeast(32.dp))
        val widthPx = constraints.maxWidth.toFloat()
        val heightPx = constraints.maxHeight.toFloat()
        var panelSize by remember { mutableStateOf(androidx.compose.ui.unit.IntSize.Zero) }
        val position = referencePanelPosition(
            if (offsetX.isNaN()) widthPx - with(density) { cardWidth.toPx() } else offsetX,
            if (offsetY.isNaN()) with(density) { 142.dp.toPx() } else offsetY,
            widthPx, heightPx, panelSize.width.toFloat(), panelSize.height.toFloat())
        LaunchedEffect(widthPx, heightPx, panelSize) {
            if (panelSize.width > 0 && panelSize.height > 0) {
                offsetX = position.first; offsetY = position.second
            }
        }
        Column(Modifier.offset { IntOffset(position.first.roundToInt(), position.second.roundToInt()) }
            .width(cardWidth).heightIn(max = maxHeight).onSizeChanged { panelSize = it }
            // Participa en el hit-test incluso en huecos transparentes. No consume
            // el slop de los hijos: consumir en Final cancelaría el arrastre y el zoom.
            .pointerInput(Unit) {
                awaitPointerEventScope { while (true) { awaitPointerEvent() } }
            }.verticalScroll(rememberScrollState()), horizontalAlignment = Alignment.CenterHorizontally) {
            // Con opacidad completa tapa también los controles tras los márgenes de la imagen.
            FloatingPanel(Modifier.width(cardWidth)) {
                Column(Modifier.padding(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Text("Referencias · mover", color = Ink.OnPanel, fontSize = 12.sp,
                            modifier = Modifier.weight(1f).height(40.dp).wrapContentHeight()
                                .pointerInput(widthPx, heightPx, panelSize) {
                                    detectDragGestures { change, drag ->
                                        change.consume()
                                        val next = referencePanelPosition(
                                            (if (offsetX.isNaN()) position.first else offsetX) + drag.x,
                                            (if (offsetY.isNaN()) position.second else offsetY) + drag.y,
                                            widthPx, heightPx, panelSize.width.toFloat(), panelSize.height.toFloat())
                                        offsetX = next.first; offsetY = next.second
                                    }
                                })
                        IconAction(AppIcons.Cancel, "Cerrar referencias", onClick = onDismiss)
                    }
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        IconAction(AppIcons.Add, if (busy) "Cargando imágenes" else "Añadir imágenes", enabled = !busy && boardId.isNotBlank()) {
                            pickerBoard = boardId
                            launcher.launch(arrayOf("image/*"))
                        }
                        IconAction(AppIcons.Delete, "Quitar imagen del tablero", enabled = !busy && selected != null) {
                            val target = selected ?: return@IconAction
                            val targetBoard = boardId
                            scope.launch {
                                busy = true
                                try { withContext(Dispatchers.IO) { store.remove(targetBoard, target) } }
                                catch (failure: Exception) {
                                    if (failure is kotlinx.coroutines.CancellationException) throw failure
                                    error = failure.message
                                } finally { busy = false }
                            }
                        }
                        IconAction(AppIcons.Frame, if (large) "Tamaño compacto" else "Ampliar tablero", selected = large) { large = !large }
                        Box {
                            IconAction(AppIcons.More, "Más opciones de referencias") { previousOpen = !previousOpen }
                            DropdownMenu(expanded = previousOpen, onDismissRequest = { previousOpen = false }) {
                                if (selected != null && onSendToBlender != null) DropdownMenuItem(text = { Text("Enviar imagen a Blender") }, enabled = !busy,
                                    onClick = { previousOpen = false; onSendToBlender(selected, opacity) })
                                if (previous.isNotEmpty()) {
                                    Text("Recuperar imágenes anteriores", Modifier.padding(12.dp), fontSize = 12.sp)
                                    previous.forEach { image ->
                                        DropdownMenuItem(text = { Text(image.name, maxLines = 1) }, enabled = !busy && boardId.isNotBlank(), onClick = {
                                            previousOpen = false
                                            val targetBoard = boardId
                                            scope.launch {
                                                busy = true
                                                try {
                                                    withContext(Dispatchers.IO) { store.recover(targetBoard, image) }
                                                    if (currentBoard == targetBoard) selectedId = image.id
                                                } catch (failure: Exception) {
                                                    if (failure is kotlinx.coroutines.CancellationException) throw failure
                                                    error = failure.message
                                                } finally { busy = false }
                                            }
                                        })
                                    }
                                }
                                if (previous.isEmpty() && (selected == null || onSendToBlender == null)) {
                                    Text("Cada escena conserva su propio tablero.", Modifier.padding(12.dp), fontSize = 12.sp)
                                }
                            }
                        }
                    }
                    if (images.size > 1) Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        images.forEachIndexed { index, image ->
                            key(image.id) { PillButton("${index + 1}", selected = image.id == selected?.id) { selectedId = image.id } }
                        }
                    }
                }
            }
            Box(Modifier.width(cardWidth).height(cardHeight).background(Ink.Background.copy(alpha = opacity)).clipToBounds()
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
                } ?: Text(if (boardId.isBlank()) "Conecta con Blender para abrir el tablero de la escena"
                    else if (busy) "Cargando imágenes…" else if (selected == null) "Añade fotos o dibujos con +" else "Cargando imagen…",
                    color = Ink.Muted, fontSize = 12.sp, modifier = Modifier.background(Ink.Panel).padding(16.dp))
            }
            if (selected != null || error != null) FloatingPanel(Modifier.width(cardWidth)) {
                Column(Modifier.padding(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    if (selected != null) {
                        Text(selected.name, color = Ink.Muted, fontSize = 11.sp, maxLines = 1)
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            IconAction(AppIcons.Reset, "Restablecer referencia") { zoom = 1f; pan = Offset.Zero; opacity = 1f }
                            Text("Opacidad", color = Ink.Muted, fontSize = 11.sp)
                            Slider(opacity, { opacity = it }, valueRange = .15f..1f, modifier = Modifier.weight(1f))
                        }
                    }
                    error?.let { Text(it, color = MaterialTheme.colorScheme.error, fontSize = 11.sp) }
                }
            }
        }
    }
}
