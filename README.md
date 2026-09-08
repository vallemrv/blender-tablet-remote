# Blender Tablet Remote

Interfaz táctil Android para controlar Blender sin convertir la tablet en un
escritorio remoto. Blender conserva el motor 3D; la app aporta vídeo, gestos y
controles adaptados a dedo y stylus.

## Documentación

- [`AGENTS.md`](AGENTS.md): arquitectura, invariantes y reglas de trabajo.
- [`blender-backend/docs/protocol.md`](blender-backend/docs/protocol.md): contrato canónico entre ambos lados.
- [`docs/cad-workspace.md`](docs/cad-workspace.md): dibujar, restringir, arrastrar, extruir y vaciar en CAD.
- [`docs/cad-kernel-evaluation.md`](docs/cad-kernel-evaluation.md): evaluación reproducible y límites del kernel CAD.

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

El workspace CAD tiene raíles propios de geometría y restricciones: líneas,
rectángulos/cuadrados, círculos, arcos y redondeo de sketch. Permite seleccionar y
arrastrar puntos/aristas, restringirlos y extruir perfiles cerrados; el vaciado por
profundidad usa incrementos con lápiz y transparencia automática. El documento,
sus cotas y dependencias se guardan en el `.blend`. El kernel sigue siendo de malla
nativa, con un solver acotado; Object y Edit conservan su flujo habitual.

## Directorios

```text
blender-backend/   add-on de Blender, protocolo y herramientas
android-client/    aplicación Kotlin/Compose
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

El vídeo requiere `ffmpeg` en el `PATH` del PC.

## Uso

Instala el ZIP generado desde las preferencias de Blender, activa el add-on y habilita
**Arrancar con Blender** si quieres que el servidor se levante automáticamente. En la
tablet instala el APK, configura la IP del PC, puerto 8765 y token. El puerto MJPEG lo
anuncia el backend. No expongas estos puertos directamente a Internet; usa la VPN.
