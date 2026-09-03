package com.blendertablet.remote.ui

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.CallMade
import androidx.compose.material.icons.automirrored.filled.CompareArrows
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.ContentCut
import androidx.compose.material.icons.filled.CropFree
import androidx.compose.material.icons.filled.AspectRatio
import androidx.compose.material.icons.filled.GridOn
import androidx.compose.material.icons.filled.OpenWith
import androidx.compose.material.icons.filled.RoundedCorner
import androidx.compose.material.icons.filled.TouchApp
import androidx.compose.material.icons.filled.ViewWeek
import androidx.compose.material.icons.automirrored.filled.RotateRight
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.blendertablet.remote.MainViewModel
import com.blendertablet.remote.model.ActiveTool
import com.blendertablet.remote.model.AppUiState
import com.blendertablet.remote.model.BlenderMode
import com.blendertablet.remote.model.EditTool
import com.blendertablet.remote.model.EditToolbarFamily
import com.blendertablet.remote.model.EditToolbarVariant
import com.blendertablet.remote.model.SnapType
import com.blendertablet.remote.model.SelectionMode
import com.blendertablet.remote.model.ToolSession
import com.blendertablet.remote.model.TransformSession
import com.blendertablet.remote.model.TransformMode
import com.blendertablet.remote.model.TweakMotion
import com.blendertablet.remote.model.TweakSettings

/**
 * Rail permanente de manipulación, junto al menú Archivo.
 *
 * Su tamaño no depende del catálogo de herramientas: Object muestra siempre las tres
 * transformaciones y Edit añade Tweak. No tiene estado abierto/cerrado.
 */
@Composable
fun TransformToolRail(
    state: AppUiState,
    session: TransformSession,
    vm: MainViewModel,
    modifier: Modifier = Modifier,
) {
    val editable = state.blender.activeObject != null
    val inEdit = state.blender.mode == BlenderMode.EDIT

    FloatingPanel(modifier) {
        Row {
            IconAction(
                Icons.Default.OpenWith, "Mover",
                selected = session.active && session.mode == TransformMode.MOVE,
                enabled = editable,
                onClick = { vm.transformBegin(TransformMode.MOVE) },
            )
            IconAction(
                Icons.AutoMirrored.Filled.RotateRight, "Rotar",
                selected = session.active && session.mode == TransformMode.ROTATE,
                enabled = editable,
                onClick = { vm.transformBegin(TransformMode.ROTATE) },
            )
            IconAction(
                Icons.Default.AspectRatio, "Escalar",
                selected = session.active && session.mode == TransformMode.SCALE,
                enabled = editable,
                onClick = { vm.transformBegin(TransformMode.SCALE) },
            )
            if (inEdit && state.blender.features.selectionTweak) {
                TweakToolButton(
                    settings = state.tweak,
                    motions = state.blender.features.tweakMotions,
                    snapTypes = state.blender.features.tweakSnapTypes,
                    selected = state.activeTool == ActiveTool.TWEAK,
                    enabled = state.blender.selectionMode != SelectionMode.FACE,
                    vm = vm,
                )
            }
        }
    }
}

/**
 * Barra izquierda de tools activas de Edit Mode (`edit_toolbar`, F1).
 *
 * Cada familia es un botón: tap arma la variante recordada (o la del servidor por
 * defecto); pulsación larga abre un selector compacto anclado al botón que cambia de
 * variante sin confirmar la sesión anterior (B1: activar otra cancela/restaura la
 * incompatible, nunca confirma implícitamente). El botón queda marcado mientras la
 * familia está armada o tiene sesión, tanto si la activó el rail como si la reabrió
 * el usuario desde otro sitio.
 */
@Composable
fun ToolbarFamilyButtons(
    families: List<EditToolbarFamily>,
    toolSession: ToolSession,
    rememberedVariants: Map<String, String>,
    vm: MainViewModel,
) {
    for (family in families) {
        FamilyToolButton(family, toolSession, rememberedVariants[family.id], vm)
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun FamilyToolButton(
    family: EditToolbarFamily,
    toolSession: ToolSession,
    rememberedVariant: String?,
    vm: MainViewModel,
) {
    var expanded by remember { mutableStateOf(false) }
    val activeVariant = activeVariantOf(family, toolSession)
    val selected = activeVariant != null
    val enabledVariants = family.variants.filter { it.enabled }
    val displayedVariant = displayedVariantOf(family, activeVariant, rememberedVariant)
    val description = displayedVariant?.let { "${family.label}: ${it.label}" } ?: family.label

    Box {
        Box(
            Modifier
                .size(Metrics.Touch)
                .clip(RoundedCornerShape(10.dp))
                .background(if (selected) Ink.Accent.copy(alpha = .22f) else Color.Transparent)
                .combinedClickable(
                    interactionSource = remember { MutableInteractionSource() },
                    indication = null,
                    onClick = { vm.activateToolbarFamily(family) },
                    onLongClick = { if (enabledVariants.size > 1) expanded = true },
                ),
            contentAlignment = Alignment.Center,
        ) {
            Icon(familyIcon(family), description, tint = if (selected) Ink.Accent else Ink.OnPanel)
            if (hasLongClickMenu(family)) {
                VariantBadge(variantBadge(family.id, displayedVariant?.id), selected)
            }
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            for (variant in enabledVariants) {
                DropdownMenuItem(
                    text = { Text(variant.label) },
                    leadingIcon = {
                        if (variant.id == displayedVariant?.id) Icon(Icons.Default.Check, null, tint = Ink.Accent)
                    },
                    onClick = {
                        expanded = false
                        vm.activateToolbarFamily(family, variant.id)
                    },
                )
            }
        }
    }
}

internal fun hasLongClickMenu(family: EditToolbarFamily): Boolean =
    family.variants.count { it.enabled } > 1

/**
 * Destinos de snap que se ofrecen en Tweak, en orden estable.
 *
 * Se cruzan los que anuncia el servidor con los que esta interfaz considera exactos
 * (misma decisión que la bandeja de transformación: nada de arista o cara arbitraria,
 * que dan un punto impreciso). Con SLIDE solo quedan los escalares: deslizar por una
 * arista ya decide el destino.
 */
/**
 * Botón de Tweak: tap lo arma, pulsación larga elige cómo se mueve y a qué se pega.
 *
 * Los ajustes viven aquí y no en una bandeja inferior porque Tweak es un gesto de un
 * solo arrastre: cuando la bandeja aparecería el movimiento ya habría terminado. Por
 * eso tampoco muestra bandeja durante la sesión (ver `bottomTrayVisible`).
 */
@OptIn(ExperimentalFoundationApi::class)
@Composable
fun TweakToolButton(
    settings: TweakSettings,
    motions: List<TweakMotion>,
    snapTypes: List<SnapType>,
    selected: Boolean,
    enabled: Boolean,
    vm: MainViewModel,
) {
    var expanded by remember { mutableStateOf(false) }
    val snapOptions = tweakSnapOptions(snapTypes, settings.motion)
    val snap = settings.effectiveSnapType
    val configurable = motions.size > 1 || snapOptions.size > 1
    val description = "Tweak · ${settings.motion.label}" +
        if (snap != SnapType.NONE) " · ${snap.label}" else ""

    Box {
        Box(
            Modifier
                .size(Metrics.Touch)
                .clip(RoundedCornerShape(10.dp))
                .background(if (selected) Ink.Accent.copy(alpha = .22f) else Color.Transparent)
                .combinedClickable(
                    enabled = enabled,
                    interactionSource = remember { MutableInteractionSource() },
                    indication = null,
                    onClick = { vm.activateTweak() },
                    onLongClick = { if (configurable) expanded = true },
                ),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                Icons.Default.TouchApp, description,
                tint = if (!enabled) Ink.Faint else if (selected) Ink.Accent else Ink.OnPanel,
            )
            // El badge dice el movimiento con su inicial y avisa del snap con el color:
            // dos ajustes en una esquina de 14 dp no caben como texto.
            if (configurable) {
                VariantBadge(
                    if (settings.motion == TweakMotion.SLIDE) "A" else "L",
                    selected = snap != SnapType.NONE,
                )
            }
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            MenuHeader("Movimiento")
            for (motion in motions) {
                DropdownMenuItem(
                    text = { Text(motion.label) },
                    leadingIcon = {
                        if (motion == settings.motion) Icon(Icons.Default.Check, null, tint = Ink.Accent)
                    },
                    onClick = {
                        expanded = false
                        vm.setTweakMotion(motion)
                    },
                )
            }
            if (settings.motion == TweakMotion.SLIDE) {
                DropdownMenuItem(
                    text = { Text("Sin salir de la arista") },
                    leadingIcon = {
                        if (settings.clamp) Icon(Icons.Default.Check, null, tint = Ink.Accent)
                    },
                    onClick = {
                        expanded = false
                        vm.toggleTweakClamp()
                    },
                )
            }
            if (snapOptions.size > 1) {
                MenuHeader("Snap")
                for (option in snapOptions) {
                    DropdownMenuItem(
                        text = { Text(option.label) },
                        leadingIcon = {
                            if (option == snap) Icon(Icons.Default.Check, null, tint = Ink.Accent)
                        },
                        onClick = {
                            expanded = false
                            vm.setTweakSnapType(option)
                        },
                    )
                }
                if (snap == SnapType.INCREMENT) {
                    MenuHeader("Paso")
                    for ((label, step) in tweakSnapSteps(settings.motion)) {
                        DropdownMenuItem(
                            text = { Text(label) },
                            leadingIcon = {
                                if (kotlin.math.abs(settings.snapStep - step) < 1e-9) {
                                    Icon(Icons.Default.Check, null, tint = Ink.Accent)
                                }
                            },
                            onClick = {
                                expanded = false
                                vm.setTweakSnapStep(step)
                            },
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun MenuHeader(label: String) {
    Text(
        label.uppercase(),
        color = Ink.Faint,
        fontSize = 10.sp,
        fontWeight = FontWeight.SemiBold,
        modifier = Modifier.padding(start = 12.dp, top = 8.dp, bottom = 2.dp),
    )
}

internal fun displayedVariantOf(
    family: EditToolbarFamily,
    active: EditToolbarVariant?,
    rememberedId: String?,
): EditToolbarVariant? = active
    ?: family.variants.firstOrNull { it.id == rememberedId && it.enabled }
    ?: family.variants.firstOrNull { it.id == family.defaultVariant && it.enabled }
    ?: family.variants.firstOrNull { it.enabled }

internal fun hasDuplicateLongClickMenu(inEdit: Boolean): Boolean = !inEdit

/**
 * Qué variante de esta familia está armada/activa ahora mismo, si alguna.
 *
 * Primero se filtra por la tool wire de la sesión: para `CUT` eso ya distingue Knife
 * de Bisect (tools distintas). Si varias variantes comparten tool (Extrude/Inset,
 * todas `tool.begin` con el mismo `tool`), se desempata por el parámetro `variant`
 * que [MainViewModel.activateToolbarFamily] siempre manda.
 */
private fun activeVariantOf(family: EditToolbarFamily, session: ToolSession): EditToolbarVariant? {
    if (!session.armed && !session.active) return null
    val candidates = family.variants.filter { variant ->
        val wire = (variant.payload["tool"] as? String) ?: (family.payload["tool"] as? String) ?: family.id
        EditTool.fromWire(wire) == session.tool
    }
    if (candidates.size <= 1) return candidates.firstOrNull()
    val variantParam = session.parameters["variant"] as? String
    return candidates.firstOrNull { it.id == variantParam } ?: candidates.first()
}

/**
 * Un icono por familia y **nunca compartido entre familias**.
 *
 * Antes la variante también cambiaba el icono, y el resultado era que Extrude a lo
 * largo de normales, Inset individual y Bridge se dibujaban los tres con la misma
 * flecha doble, e Inset compartía cuadro con Extrude individual: el rail decía la
 * variante a costa de no decir la herramienta. Ahora el icono identifica la familia y
 * la variante se lee en [VariantBadge].
 */
private fun familyIcon(family: EditToolbarFamily): ImageVector = when (family.id) {
    "EXTRUDE" -> Icons.AutoMirrored.Filled.CallMade
    "BEVEL" -> Icons.Default.RoundedCorner
    "INSET" -> Icons.Default.CropFree
    "LOOP_CUT" -> Icons.Default.ViewWeek
    "BRIDGE_EDGE_LOOPS" -> Icons.AutoMirrored.Filled.CompareArrows
    "SUBDIVIDE" -> Icons.Default.GridOn
    "CUT" -> Icons.Default.ContentCut
    else -> Icons.Default.Build
}

/**
 * Etiqueta corta de la variante armada, para la esquina del botón.
 *
 * Sustituye al chevrón, que era idéntico en todas las familias: anunciaba que había
 * menú pero no cuál de los modos estaba puesto, justo lo que hay que saber de un
 * vistazo. Devolver el badge sigue implicando que hay menú, porque solo se pinta en
 * familias con más de una variante.
 */
internal fun variantBadge(familyId: String, variantId: String?): String = when {
    variantId == null -> "·"
    familyId == "EXTRUDE" && variantId == "ALONG_NORMALS" -> "N"
    variantId == "REGION" -> "R"
    variantId == "INDIVIDUAL" -> "I"
    variantId == "KNIFE" -> "K"
    variantId == "BISECT" -> "B"
    else -> variantId.take(1).uppercase()
}

@Composable
private fun BoxScope.VariantBadge(label: String, selected: Boolean) {
    val color = if (selected) Ink.Accent else Ink.Muted
    Box(
        Modifier
            .align(Alignment.BottomEnd)
            .padding(2.dp)
            .size(14.dp)
            .clip(RoundedCornerShape(4.dp))
            .background(Ink.PanelSolid),
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = color, fontSize = 9.sp, fontWeight = FontWeight.Bold)
    }
}

/** Familia discreta Duplicar: tap ejecuta la recordada; long-click elige y ejecuta. */
@OptIn(ExperimentalFoundationApi::class)
@Composable
fun DuplicateFamilyButton(inEdit: Boolean, linked: Boolean, enabled: Boolean, vm: MainViewModel) {
    var expanded by remember { mutableStateOf(false) }
    val useLinked = linked && !inEdit
    val description = if (useLinked) "Duplicar enlazado" else if (inEdit) "Duplicar selección" else "Duplicar"
    Box {
        Box(
            Modifier
                .size(Metrics.Touch)
                .clip(RoundedCornerShape(10.dp))
                .combinedClickable(
                    enabled = enabled,
                    interactionSource = remember { MutableInteractionSource() },
                    indication = null,
                    onClick = { vm.runDuplicateVariant(useLinked) },
                    onLongClick = { if (hasDuplicateLongClickMenu(inEdit)) expanded = true },
                ),
            contentAlignment = Alignment.Center,
        ) {
            // Duplicar conserva su icono en las dos variantes: la flecha doble que
            // usaba para "enlazado" es la de Bridge, y dos utilidades distintas del
            // mismo rail no pueden dibujarse igual. El enlace lo dice el badge.
            Icon(
                Icons.Default.ContentCopy,
                description,
                tint = if (enabled) Ink.OnPanel else Ink.Faint,
            )
            if (hasDuplicateLongClickMenu(inEdit)) {
                VariantBadge(if (useLinked) "L" else "D", selected = useLinked)
            }
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            listOf(false to "Duplicar", true to "Duplicar enlazado").forEach { (variant, label) ->
                DropdownMenuItem(
                    text = { Text(label) },
                    leadingIcon = { if (variant == linked) Icon(Icons.Default.Check, null, tint = Ink.Accent) },
                    onClick = {
                        expanded = false
                        vm.runDuplicateVariant(variant)
                    },
                )
            }
        }
    }
}
