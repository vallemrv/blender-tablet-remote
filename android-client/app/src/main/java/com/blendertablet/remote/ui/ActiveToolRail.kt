package com.blendertablet.remote.ui

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.CallMade
import androidx.compose.material.icons.automirrored.filled.CompareArrows
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.ContentCut
import androidx.compose.material.icons.filled.CropFree
import androidx.compose.material.icons.filled.LinearScale
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.RoundedCorner
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
import androidx.compose.ui.unit.dp
import com.blendertablet.remote.MainViewModel
import com.blendertablet.remote.model.EditTool
import com.blendertablet.remote.model.EditToolbarFamily
import com.blendertablet.remote.model.EditToolbarVariant
import com.blendertablet.remote.model.ToolSession

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
            Icon(familyIcon(family, displayedVariant), description, tint = if (selected) Ink.Accent else Ink.OnPanel)
            if (hasLongClickMenu(family)) {
                Icon(
                    Icons.Default.KeyboardArrowDown,
                    "Mantén pulsado para ver variantes",
                    Modifier.align(Alignment.BottomEnd).padding(2.dp).size(13.dp),
                    tint = if (selected) Ink.Accent else Ink.Faint,
                )
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

private fun familyIcon(family: EditToolbarFamily, variant: EditToolbarVariant?): ImageVector = when {
    family.id == "EXTRUDE" && variant?.id == "ALONG_NORMALS" -> Icons.AutoMirrored.Filled.CompareArrows
    family.id == "EXTRUDE" && variant?.id == "INDIVIDUAL" -> Icons.Default.CropFree
    family.id == "EXTRUDE" -> Icons.AutoMirrored.Filled.CallMade
    family.id == "BEVEL" -> Icons.Default.RoundedCorner
    family.id == "INSET" && variant?.id == "INDIVIDUAL" -> Icons.AutoMirrored.Filled.CompareArrows
    family.id == "INSET" -> Icons.Default.CropFree
    family.id == "LOOP_CUT" -> Icons.Default.LinearScale
    family.id == "BRIDGE_EDGE_LOOPS" -> Icons.AutoMirrored.Filled.CompareArrows
    family.id == "CUT" && variant?.id == "BISECT" -> Icons.Default.LinearScale
    family.id == "CUT" -> Icons.Default.ContentCut
    else -> Icons.Default.ContentCut
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
            Icon(
                if (useLinked) Icons.AutoMirrored.Filled.CompareArrows else Icons.Default.ContentCopy,
                description,
                tint = if (enabled) Ink.OnPanel else Ink.Faint,
            )
            if (hasDuplicateLongClickMenu(inEdit)) {
                Icon(
                    Icons.Default.KeyboardArrowDown,
                    "Mantén pulsado para elegir duplicado",
                    Modifier.align(Alignment.BottomEnd).padding(2.dp).size(13.dp),
                    tint = Ink.Faint,
                )
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
