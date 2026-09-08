package com.blendertablet.remote.ui

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.blendertablet.remote.model.LengthUnit
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
    FloatingPanel(modifier) {
        Row(
            modifier = Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text("TWEAK", color = Ink.Accent, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
            PillButton("GG", selected = slide, enabled = canSlide) {
                onSlide(if (slide) TweakMotion.FREE else TweakMotion.SLIDE)
            }
            if (slide) {
                PillButton("Limitar a arista", selected = settings.clamp, onClick = onClamp)
            }
            if (snapOptions.isNotEmpty()) {
                PillButton("Snap", selected = snap != SnapType.NONE) {
                    onSnapType(if (snap != SnapType.NONE) SnapType.NONE
                        else snapOptions.firstOrNull { it == SnapType.INCREMENT } ?: snapOptions.first())
                }
                if (snap != SnapType.NONE) {
                    SnapControl(snapOptions, snap, onSnapType)
                    if (snap == SnapType.INCREMENT) {
                        if (slide) {
                            ScaleStepInput(settings.snapStep * 100.0, TransformStepUnit.PERCENT) {
                                onSnapStep(it / 100.0)
                            }
                        } else {
                            DistanceSnapStepInput(settings.snapStep, unitScaleLength, lengthUnit, onChange = onSnapStep)
                        }
                    }
                }
            }
        }
    }
}
