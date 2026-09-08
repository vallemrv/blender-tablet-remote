package com.blendertablet.remote.ui

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.blendertablet.remote.MainViewModel
import com.blendertablet.remote.model.EditTool
import com.blendertablet.remote.model.EditToolbarFamily
import com.blendertablet.remote.model.EditToolbarVariant
import com.blendertablet.remote.model.ToolSession
import com.blendertablet.remote.model.SelectionMode

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
    selectionMode: SelectionMode,
    vm: MainViewModel,
) {
    for (family in families) {
        FamilyToolButton(family, toolSession, rememberedVariants[family.id], selectionMode, vm)
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun FamilyToolButton(
    family: EditToolbarFamily,
    toolSession: ToolSession,
    rememberedVariant: String?,
    selectionMode: SelectionMode,
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
            Icon(AppIcons.toolbarVariant(family.id, displayedVariant?.id), description, tint = if (selected) Ink.Accent else Ink.OnPanel)
            if (hasLongClickMenu(family)) {
                VariantBadge(variantBadge(family.id, displayedVariant?.id), selected)
            }
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            for (variant in enabledVariants) {
                DropdownMenuItem(
                    text = { Text(variant.label) },
                    leadingIcon = {
                        Icon(AppIcons.toolbarVariant(family.id, variant.id), null)
                    },
                    trailingIcon = {
                        if (variant.id == displayedVariant?.id) Icon(Icons.Default.Check, null, tint = Ink.Accent)
                    },
                    enabled = variant.availableIn(selectionMode),
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

/** Tweak es una única herramienta; sus ayudas viven en la bandeja inferior. */
@Composable
fun TweakToolButton(selected: Boolean, enabled: Boolean, vm: MainViewModel) {
    IconAction(AppIcons.Tweak, "Tweak", selected = selected, enabled = enabled) {
        if (selected) vm.selectTool() else vm.activateTweak()
    }
}

internal fun displayedVariantOf(
    family: EditToolbarFamily,
    active: EditToolbarVariant?,
    rememberedId: String?,
): EditToolbarVariant? = active
    ?: family.variants.firstOrNull { it.id == rememberedId && it.enabled }
    ?: family.variants.firstOrNull { it.id == family.defaultVariant && it.enabled }
    ?: family.variants.firstOrNull { it.enabled }

/**
 * Qué variante de esta familia está armada/activa ahora mismo, si alguna.
 *
 * Primero se filtra por la tool wire de la sesión: para `CUT` eso ya distingue Knife
 * de Bisect (tools distintas). Si varias variantes comparten tool (Extrude/Inset,
 * todas `tool.begin` con el mismo `tool`), se desempata por el parámetro `variant`
 * que [MainViewModel.activateToolbarFamily] siempre manda.
 */
internal fun activeVariantOf(family: EditToolbarFamily, session: ToolSession): EditToolbarVariant? {
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
