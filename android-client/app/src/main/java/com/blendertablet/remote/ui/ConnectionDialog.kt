package com.blendertablet.remote.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.OutlinedTextField
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.blendertablet.remote.data.ConnectionSettings

/**
 * Preferencias de conexión. Se rellenan una vez y se guardan: en los arranques
 * siguientes la app conecta sola y este diálogo solo se abre a petición, tocando
 * el indicador de estado.
 *
 * El puerto del vídeo NO se pide: lo anuncia el servidor en el `hello` y la app se
 * engancha sola (§63).
 */
@Composable
fun ConnectionSettingsDialog(
    initial: ConnectionSettings,
    connecting: Boolean,
    onDismiss: () -> Unit,
    onSave: (ConnectionSettings) -> Unit,
) {
    var host by remember { mutableStateOf(initial.host) }
    var port by remember { mutableStateOf(initial.port.toString()) }
    var token by remember { mutableStateOf(initial.token) }
    var autoConnect by remember { mutableStateOf(initial.autoConnect) }

    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = Ink.PanelSolid,
        title = { Text("Conexión con Blender", color = Ink.OnPanel, fontSize = 16.sp) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    OutlinedTextField(
                        value = host,
                        onValueChange = { host = it },
                        label = { Text("Equipo") },
                        singleLine = true,
                        modifier = Modifier.weight(1f),
                    )
                    OutlinedTextField(
                        value = port,
                        onValueChange = { port = it.filter(Char::isDigit) },
                        label = { Text("Puerto") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.width(110.dp),
                    )
                }
                OutlinedTextField(
                    value = token,
                    onValueChange = { token = it },
                    label = { Text("Token (si el add-on lo pide)") },
                    singleLine = true,
                    visualTransformation = PasswordVisualTransformation(),
                    modifier = Modifier.fillMaxWidth(),
                )
                Row(
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Switch(checked = autoConnect, onCheckedChange = { autoConnect = it })
                    Text("Conectar al abrir la app", color = Ink.OnPanel, fontSize = 13.sp)
                }
                Text(
                    "Se recuerdan estos datos. Si la conexión se cae, la app reintenta sola.",
                    color = Ink.Faint,
                    fontSize = 11.sp,
                )
            }
        },
        confirmButton = {
            PillButton(
                label = if (connecting) "Conectando…" else "Guardar y conectar",
                selected = true,
                enabled = host.isNotBlank() && port.isNotBlank(),
                onClick = {
                    onSave(
                        ConnectionSettings(
                            host = host.trim(),
                            port = port.toIntOrNull() ?: ConnectionSettings.DEFAULT_PORT,
                            token = token.trim(),
                            autoConnect = autoConnect,
                        )
                    )
                },
            )
        },
        dismissButton = { PillButton("Cancelar", onClick = onDismiss) },
    )
}
