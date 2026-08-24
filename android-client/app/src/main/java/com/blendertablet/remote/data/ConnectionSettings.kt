package com.blendertablet.remote.data

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Datos de conexión al PC. Se introducen una vez y se recuerdan: la app no debe
 * volver a preguntarlos en cada arranque ni en cada rotación (§41).
 */
data class ConnectionSettings(
    val host: String = "",
    val port: Int = DEFAULT_PORT,
    val token: String = "",
    /** Al abrir la app se conecta sola sin pasar por el diálogo. */
    val autoConnect: Boolean = true,
) {
    /** Sin host no hay nada que intentar: es lo único que no tiene valor por defecto. */
    val isComplete: Boolean get() = host.isNotBlank() && port in 1..65535

    companion object {
        const val DEFAULT_PORT = 8765
    }
}

/**
 * Persistencia de [ConnectionSettings].
 *
 * El token se guarda en claro junto al resto: el servidor vive en la LAN o dentro
 * de WireGuard y el token solo evita conexiones accidentales, no es una credencial
 * con valor fuera del equipo.
 */
class ConnectionPreferences(context: Context) {
    private val prefs = context.getSharedPreferences(NAME, Context.MODE_PRIVATE)
    private val _settings = MutableStateFlow(read())
    val settings: StateFlow<ConnectionSettings> = _settings.asStateFlow()

    val current: ConnectionSettings get() = _settings.value

    fun save(settings: ConnectionSettings) {
        prefs.edit()
            .putString(KEY_HOST, settings.host)
            .putInt(KEY_PORT, settings.port)
            .putString(KEY_TOKEN, settings.token)
            .putBoolean(KEY_AUTO_CONNECT, settings.autoConnect)
            .apply()
        _settings.value = settings
    }

    private fun read() = ConnectionSettings(
        host = prefs.getString(KEY_HOST, "") ?: "",
        port = prefs.getInt(KEY_PORT, ConnectionSettings.DEFAULT_PORT),
        token = prefs.getString(KEY_TOKEN, "") ?: "",
        autoConnect = prefs.getBoolean(KEY_AUTO_CONNECT, true),
    )

    private companion object {
        // Mismo fichero y mismas claves que la versión anterior: quien ya tenía
        // host y puerto guardados no los pierde al actualizar.
        const val NAME = "connection"
        const val KEY_HOST = "host"
        const val KEY_PORT = "port"
        const val KEY_TOKEN = "token"
        const val KEY_AUTO_CONNECT = "auto_connect"
    }
}
