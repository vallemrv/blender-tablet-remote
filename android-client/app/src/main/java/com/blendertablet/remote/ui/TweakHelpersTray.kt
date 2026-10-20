package com.blendertablet.remote.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.blendertablet.remote.model.LengthUnit
import com.blendertablet.remote.model.EditSettings
import com.blendertablet.remote.model.SelectionMode
import com.blendertablet.remote.model.SnapType
import com.blendertablet.remote.model.TransformStepUnit
import com.blendertablet.remote.model.TweakMotion
import com.blendertablet.remote.model.TweakSettings

/** Ayudas persistentes mientras Tweak está encendido, entre sus gestos breves. */
@Composable
fun TweakHelpersTray(
    settings: TweakSettings,
    selectionMode: SelectionMode,
    motions: List<TweakMotion>,
    snapTypes: List<SnapType>,
    unitScaleLength: Double,
    lengthUnit: LengthUnit,
    editSettings: EditSettings,
    proportionalRadiusStep: Double,
    onProportional: () -> Unit,
    onProportionalRadius: (Double) -> Unit,
    onProportionalFalloff: (String) -> Unit,
    onSlide: (TweakMotion) -> Unit,
    onSnapType: (SnapType) -> Unit,
    onSnapStep: (Double) -> Unit,
    onClamp: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val canSlide = selectionMode != SelectionMode.FACE && TweakMotion.SLIDE in motions
    val slide = canSlide && settings.motion == TweakMotion.SLIDE
    val effective = settings.copy(motion = if (slide) TweakMotion.SLIDE else TweakMotion.FREE)
    val snapOptions = tweakSnapOptions(snapTypes, effective.motion).filterNot { it == SnapType.NONE }
    val snap = effective.effectiveSnapType.takeIf { it in snapOptions } ?: SnapType.NONE
    val more = TrayMore(
        precision = if (snap != SnapType.INCREMENT) null else ({
            TrayOption("Paso", if (slide) "Porcentaje de la arista por cada salto." else "Distancia de cada salto del arrastre.") {
                if (slide) ScaleStepInput(settings.snapStep * 100.0, TransformStepUnit.PERCENT) { onSnapStep(it / 100.0) }
                else DistanceSnapStepInput(settings.snapStep, unitScaleLength, lengthUnit, onChange = onSnapStep)
            }
        }),
        shape = {
            TrayOption(if (slide) "Proporcional (sin GG)" else "Proporcional",
                "Mueve también los vecinos dentro del radio. GG desliza solo la selección.") {
                IconAction(AppIcons.Proportional, "Edición proporcional", selected = !slide && editSettings.proportional,
                    enabled = !slide, onClick = onProportional)
            }
            if (!slide && editSettings.proportional) {
                TrayOption("Radio", "Alcance de la influencia.") {
                    ProportionalRadiusInput(editSettings.radius, unitScaleLength, lengthUnit,
                        proportionalRadiusStep, onProportionalRadius)
                }
                TrayOption("Perfil", "Cómo cae la influencia hacia el borde del radio.") {
                    FalloffChoice(editSettings.falloff, onProportionalFalloff)
                }
            }
        },
    )
    SingleLineTray("Tweak", modifier = modifier, more = more,
        help = "Arrastra un elemento para moverlo · GG lo desliza por sus aristas · Snap ajusta el arrastre") {
        IconAction(AppIcons.TweakSlide, "GG · deslizar por aristas", selected = slide, enabled = canSlide) {
            onSlide(if (slide) TweakMotion.FREE else TweakMotion.SLIDE)
        }
        if (slide) IconAction(AppIcons.EdgeExtend, "Prolongar arista · Alt", selected = !settings.clamp, onClick = onClamp)
        if (snapOptions.isNotEmpty()) SnapControl(listOf(SnapType.NONE) + snapOptions, snap, onSnapType)
    }
}
