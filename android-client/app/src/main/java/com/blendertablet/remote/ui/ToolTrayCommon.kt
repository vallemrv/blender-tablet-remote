package com.blendertablet.remote.ui

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** One shared anchor and popup, directly above the tray's More button. */
@Composable
fun ToolMoreMenu(instruction: String, content: @Composable ColumnScope.() -> Unit) {
    var open by remember { mutableStateOf(false) }
    Box {
        PillButton("⋯ Más") { open = true }
        DropdownMenu(open, onDismissRequest = { open = false }) {
            Column(Modifier.widthIn(min = 280.dp, max = 380.dp).padding(12.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                if (instruction.isNotBlank()) Text(instruction, color = Ink.Muted, fontSize = 12.sp)
                content()
            }
        }
    }
}

@Composable
fun AdvancedToolOption(help: String, content: @Composable RowScope.() -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp), content = content)
        Text(help, color = Ink.Muted, fontSize = 12.sp)
    }
}

@Composable
fun QuickToolValues(values: List<Int>, selected: Double, onValue: (Double) -> Unit) {
    values.forEach { value -> PillButton(value.toString(), selected = selected == value.toDouble()) { onValue(value.toDouble()) } }
}
