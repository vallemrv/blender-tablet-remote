# Blender Tablet Remote

Interfaz táctil Android para controlar Blender sin convertir la tablet en un
escritorio remoto. Blender conserva el motor 3D; la app aporta vídeo, gestos y
controles adaptados a dedo y stylus.

## Estado y documentación

- [`AGENTS.md`](AGENTS.md): arquitectura, funcionalidades ya construidas y reglas de trabajo.
- [`PLAN_BACKEND.md`](PLAN_BACKEND.md): único plan activo del add-on Python.
- [`PLAN_FRONTEND.md`](PLAN_FRONTEND.md): único plan activo de la app Android.
- [`blender-backend/docs/protocol.md`](blender-backend/docs/protocol.md): contrato canónico entre ambos lados.

Los planes están separados por propiedad de directorios para permitir que dos agentes
trabajen a la vez sin editar los mismos archivos. Los cambios compartidos empiezan por
el protocolo y se coordinan como indica `AGENTS.md`.

## Arquitectura

```text
Tablet Android                         PC
Jetpack Compose -- WebSocket :8765 --> Blender + add-on
viewport MJPEG  <-- HTTP :8766 ------- captura GPU + ffmpeg
```

Hay dos canales para que un fotograma lento nunca bloquee una orden. La app mantiene
una interfaz de viewport completo, reconexión automática, selección táctil/stylus,
navegación, transformaciones modales, modelado Edit Mode, menús de archivo/objetos y
entrada de valores con unidades. El inventario preciso está en `AGENTS.md`.

## Directorios

```text
blender-backend/   add-on de Blender, protocolo, herramientas y pruebas
android-client/    aplicación Kotlin/Compose y pruebas JVM
```

## Compilar

```bash
# Android requiere JDK 17
export JAVA_HOME=/home/valle/.local/opt/jdk-17.0.20+8
export PATH="$JAVA_HOME/bin:$PATH"
./gradlew :android-client:app:assembleDebug

# Add-on instalable
bash blender-backend/tools/build_addon.sh
```

## Verificar

```bash
blender --background --python blender-backend/tests/run_tests.py
blender --python blender-backend/tests/run_gui_tests.py
./gradlew :android-client:app:testDebugUnitTest
```

Las pruebas con ventana son necesarias para rutas que dependen de un `VIEW_3D` real,
como selección por raycast y navegación. El vídeo requiere `ffmpeg` en el `PATH` del PC.

## Uso

Instala el ZIP generado desde las preferencias de Blender, activa el add-on y habilita
**Arrancar con Blender** si quieres que el servidor se levante automáticamente. En la
tablet instala el APK, configura la IP del PC, puerto 8765 y token. El puerto MJPEG lo
anuncia el backend. No expongas estos puertos directamente a Internet; usa la VPN.
