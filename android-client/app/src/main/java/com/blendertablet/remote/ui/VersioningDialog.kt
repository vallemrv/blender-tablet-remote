package com.blendertablet.remote.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.blendertablet.remote.model.*
import kotlinx.coroutines.delay

@Composable
fun VersioningDialog(state: AppUiState, command: (String, Map<String, Any?>) -> Unit,
                     onDismiss: () -> Unit, onSaveAs: () -> Unit) {
    val version = state.blender.versioning
    val connected = state.connection == ConnectionStatus.CONNECTED
    val enabled = connected && !version.busy
    var accountTab by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("") }
    var pack by remember { mutableStateOf(false) }
    var server by remember(version.account.server) { mutableStateOf(version.account.server) }
    var allowHttp by remember(version.account.allowHttp) { mutableStateOf(version.account.allowHttp) }
    var accessToken by remember { mutableStateOf("") }
    var author by remember(version.account.authorName) { mutableStateOf(version.account.authorName) }
    var email by remember(version.account.authorEmail) { mutableStateOf(version.account.authorEmail) }
    var remote by remember(version.remote) { mutableStateOf(version.remote) }
    var repository by remember { mutableStateOf("") }
    var explore by remember { mutableStateOf<SceneVersion?>(null) }
    var ideaName by remember { mutableStateOf("") }
    var ideasOpen by remember { mutableStateOf(false) }
    var switchIdea by remember { mutableStateOf<VersionIdea?>(null) }
    var createRemote by remember { mutableStateOf(false) }
    var cloneRemote by remember { mutableStateOf(false) }
    LaunchedEffect(connected, state.file.path) {
        if (connected) command("status", mapOf("refresh" to true))
    }
    LaunchedEffect(connected, version.busy) {
        if (connected && version.busy) while (true) {
            delay(800);command("status", emptyMap())
        }
    }
    AlertDialog(onDismissRequest = onDismiss, containerColor = Ink.PanelSolid,
        title = { Text("Versiones · ValleTrack") },
        text = { Column(Modifier.heightIn(max = 540.dp).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                PillButton("Ideas y versiones", selected = !accountTab) { accountTab = false }
                PillButton("Cuenta y repo", selected = accountTab) { accountTab = true }
            }
            if (version.busy) {
                LinearProgressIndicator(Modifier.fillMaxWidth())
                Text(versionActionLabel(version.action), color = Ink.Accent)
                Text("Puedes cerrar este panel; la operación continuará.", fontSize = 11.sp)
            }
            version.error?.let { Text(it, color = Ink.Bad, fontSize = 12.sp) }
            version.message?.let { Text(it, color = Ink.Ok, fontSize = 12.sp) }
            if (!connected) Text("Reconectando con Blender…", color = Ink.Muted)
            if (accountTab) {
                Text("Cuenta Gitea", color = Ink.Accent)
                OutlinedTextField(server, { server = it }, label = { Text("Dirección HTTPS de Gitea") }, singleLine = true)
                if (server.startsWith("http://")) Row {
                    Checkbox(allowHttp, { allowHttp = it }, enabled = enabled)
                    Text("Permitir HTTP sin cifrado: el token viajará sin protección", fontSize = 11.sp)
                }
                OutlinedTextField(accessToken, { accessToken = it }, label = { Text(if (version.account.hasToken) "Nuevo token (opcional)" else "Token de acceso") },
                    singleLine = true, visualTransformation = PasswordVisualTransformation())
                Text("Token con lectura de usuario y escritura de repositorios. Se guarda en el PC de Blender, fuera del .blend y del repositorio. Configúralo en una red de confianza.", fontSize = 11.sp)
                if (version.account.hasToken) Text("Conectado: ${version.account.username}", color = Ink.Ok)
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    PillButton("Conectar", enabled = enabled && server.isNotBlank() && accessToken.isNotBlank()) {
                        command("connect", mapOf("server" to server.trim(), "access_token" to accessToken,
                            "author_name" to author, "author_email" to email, "allow_http" to allowHttp));accessToken = ""
                    }
                    PillButton("Olvidar cuenta", enabled = enabled && version.account.hasToken) { command("forget", emptyMap()) }
                }
                Text("Autor de las versiones", color = Ink.Accent)
                OutlinedTextField(author, { author = it }, label = { Text("Nombre") }, singleLine = true)
                OutlinedTextField(email, { email = it }, label = { Text("Correo") }, singleLine = true)
                PillButton("Guardar autor", enabled = enabled && author.isNotBlank() && '@' in email) {
                    command("identity", mapOf("author_name" to author, "author_email" to email))
                }
                HorizontalDivider()
                Text("Repositorio remoto", color = Ink.Accent)
                OutlinedTextField(remote, { remote = it }, label = { Text("URL HTTPS del repositorio .git") }, singleLine = true)
                PillButton("Abrir repo de ValleTrack", enabled = enabled && version.account.hasToken && remote.isNotBlank()) { cloneRemote = true }
                if (version.ready) {
                    PillButton("Conectar repositorio", enabled = enabled && version.account.hasToken && remote.isNotBlank()) {
                        command("link", mapOf("url" to remote.trim()))
                    }
                    OutlinedTextField(repository, { repository = it }, label = { Text("Nombre de un repositorio nuevo") }, singleLine = true)
                    PillButton("Crear repo privado", enabled = enabled && version.account.hasToken && repository.isNotBlank()) { createRemote = true }
                    Text("Los .blend usan Git LFS. Tu servidor Gitea debe tener LFS habilitado y espacio disponible.", fontSize = 11.sp)
                } else Text("Guarda una versión local para conectar su repositorio.", color = Ink.Muted)
            } else {
                Text(state.file.name, color = Ink.Accent)
                if (!state.file.saved) {
                    Text("Guarda primero el .blend para iniciar su historial.")
                    PillButton("Guardar como…", enabled = enabled, onClick = onSaveAs)
                } else {
                    Text("Guarda pasos de tu trabajo. Explora otra idea desde cualquier versión y vuelve después al recorrido que quieras.", fontSize = 11.sp)
                    OutlinedTextField(message, { message = it.take(500) }, label = { Text("Qué has cambiado") }, singleLine = true)
                    Row {
                        Checkbox(pack, { pack = it }, enabled = enabled)
                        Text("Empaquetar recursos compatibles", modifier = Modifier.padding(top = 12.dp), fontSize = 12.sp)
                    }
                    PillButton("Guardar versión local", enabled = enabled && message.isNotBlank() && version.lfsAvailable) {
                        command("commit", mapOf("message" to message, "pack_resources" to pack));message = ""
                    }
                    if (!version.lfsAvailable && !version.busy) Text("Git LFS no está disponible en el PC.", color = Ink.Muted)
                    if (version.ready) {
                        val activeIdea = version.branches.firstOrNull { it.name == version.branch }
                        val viewedIdea = version.branches.firstOrNull { it.name == version.historyBranch } ?: activeIdea
                        Text("Trabajando en: ${activeIdea?.label ?: version.branch}", color = Ink.Accent)
                        Box {
                            PillButton("Ver historial: ${viewedIdea?.label ?: version.branch}", enabled = enabled) { ideasOpen = true }
                            DropdownMenu(ideasOpen, { ideasOpen = false }) {
                                version.branches.forEach { idea ->
                                    DropdownMenuItem(text = { Text(idea.label + if (idea.active) " · actual" else "") }, onClick = {
                                        ideasOpen = false
                                        command("status", mapOf("refresh" to true, "history_branch" to idea.name))
                                    })
                                }
                            }
                        }
                        if (viewedIdea != null && !viewedIdea.active) PillButton("Continuar esta idea", enabled = enabled) { switchIdea = viewedIdea }
                        viewedIdea?.base?.let { Text("Se separa en ${it.take(8)}", fontSize = 11.sp, color = Ink.Muted) }
                        Text("${version.commits.size} pasos mostrados de este recorrido", fontSize = 11.sp)
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            PillButton("Actualizar", enabled = enabled) { command("status", mapOf("refresh" to true, "history_branch" to version.historyBranch)) }
                            PillButton("Subir", enabled = enabled && version.remote.isNotEmpty() && version.account.hasToken) { command("push", emptyMap()) }
                            PillButton("Descargar", enabled = enabled && version.remote.isNotEmpty() && version.account.hasToken) { command("pull", emptyMap()) }
                        }
                        if (version.remote.isNotEmpty()) {
                            Text(version.remote, fontSize = 11.sp, color = Ink.Muted)
                            Text("Subir incluye todas las ideas de este proyecto.", fontSize = 11.sp, color = Ink.Muted)
                        }
                        if (version.fileChanged || version.sceneDirty) Text("Hay cambios fuera de la última versión guardada.", fontSize = 11.sp)
                        version.commits.forEach { entry ->
                            HorizontalDivider()
                            Text(entry.message + if (entry.id == version.head) " · estás aquí" else "", color = if (entry.id == version.head) Ink.Accent else Ink.OnPanel)
                            Text("${entry.id.take(8)} · ${entry.date.take(16).replace('T', ' ')} · ${entry.author}", fontSize = 10.sp)
                            if (entry.parents.isNotEmpty()) Text("↑ Desde ${entry.parents.joinToString { it.take(8) }}", fontSize = 10.sp, color = Ink.Muted)
                            PillButton("Explorar desde aquí", enabled = enabled && version.branches.isNotEmpty()) { ideaName = ""; explore = entry }
                        }
                    }
                }
            }
        } },
        confirmButton = { PillButton("Cerrar", onClick = onDismiss) })
    explore?.let { entry -> AlertDialog(onDismissRequest = { explore = null }, containerColor = Ink.PanelSolid,
        title = { Text("Explorar otra idea") },
        text = { Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Partirás de «${entry.message}». Tu avance actual se guarda en su recorrido y podrás volver a él.")
            OutlinedTextField(ideaName, { ideaName = it.take(80) }, label = { Text("Nombre de la idea (opcional)") }, singleLine = true)
        } }, confirmButton = { PillButton("Explorar") {
            explore = null;command("explore", mapOf("revision" to entry.id, "label" to ideaName))
        } }, dismissButton = { PillButton("Cancelar") { explore = null } }) }
    switchIdea?.let { idea -> ConfirmDiscardDialog("Continuar ${idea.label}",
        "Se guarda tu avance actual y se abre el último paso de esta idea. Ambos recorridos se conservan.",
        "Continuar", { switchIdea = null }, { switchIdea = null;command("switch", mapOf("branch" to idea.name)) }) }
    if (cloneRemote) ConfirmDiscardDialog("Abrir repositorio de ValleTrack", "Se descargará el repositorio y se abrirá su escena. El archivo actual se guarda primero.",
        "Abrir", { cloneRemote = false }, { cloneRemote = false;command("clone", mapOf("url" to remote.trim())) })
    if (createRemote) ConfirmDiscardDialog("Crear repositorio privado", "Se creará «${repository.trim()}» en tu cuenta de Gitea.",
        "Crear", { createRemote = false }, { createRemote = false;command("create_remote", mapOf("name" to repository.trim())) })
}

internal fun versionActionLabel(action: String): String = when (action) {
    "commit" -> "Guardando versión…"; "restore", "explore", "switch", "finish_navigation" -> "Abriendo idea…"
    "connect" -> "Comprobando cuenta…"; "push" -> "Subiendo a Gitea…"; "pull" -> "Descargando versiones…"
    "clone" -> "Abriendo repositorio…"; "create_remote" -> "Creando repositorio…"; "link" -> "Conectando repositorio…"
    else -> "Actualizando ValleTrack…"
}
