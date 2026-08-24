# Cliente Android de Blender Tablet Remote

Aplicación Kotlin y Jetpack Compose para tablets Android. Muestra el viewport MJPEG,
envía órdenes por WebSocket y adapta la interacción a dedo, stylus y ratón.

Consulta [`../AGENTS.md`](../AGENTS.md) para el estado real, [`../PLAN_FRONTEND.md`](../PLAN_FRONTEND.md)
para el trabajo pendiente y [`../blender-backend/docs/protocol.md`](../blender-backend/docs/protocol.md)
para el contrato de red.

## Abrir y compilar

Abre la raíz del repositorio en Android Studio. El módulo ejecutable es
`android-client.app`, requiere SDK Android 36, API mínima 26 y JDK 17.

```bash
export JAVA_HOME=/home/valle/.local/opt/jdk-17.0.20+8
export PATH="$JAVA_HOME/bin:$PATH"
./gradlew :android-client:app:assembleDebug
./gradlew :android-client:app:testDebugUnitTest
```

El APK queda en `app/build/outputs/apk/debug/app-debug.apk`.

## Conexión

Configura host, puerto 8765 y token desde la app. El backend anuncia el endpoint del
vídeo y la app reconecta ambos canales automáticamente. El tráfico no usa TLS porque
está diseñado para una VPN WireGuard o una LAN confiable; no publiques el servidor en
Internet.
