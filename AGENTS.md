# Blender Tablet Remote — guía de trabajo

## Objetivo

La tablet Android es una interfaz táctil para Blender, no un escritorio remoto.
Blender conserva el motor 3D; Android muestra una cámara remota y envía intención
adaptada a dedo y stylus. El alcance actual es Object Mode y Edit Mode.

## Estructura

```text
blender-backend/
  blender_tablet_remote/   add-on Python instalable
  docs/protocol.md         contrato de red
  tools/                   build, instalación, servidor y diagnóstico
android-client/
  app/src/main/            aplicación Kotlin/Jetpack Compose
README.md                  entrada general
```

No existe `android-frontend`. El módulo Android es `:android-client:app`.

## Arquitectura de ejecución

- Control WebSocket JSON v2 en `:8765`.
- Vídeo HTTP en `:8766`: H.264 preferido y MJPEG como fallback.
- GPUOffScreen es la única fuente de vídeo y usa la cámara independiente de la tablet.
- Los threads de red solo encolan mensajes; `bpy` y `bmesh` se usan exclusivamente
  en el hilo principal mediante `bridge._pump()`.
- Android tiene una única superficie de entrada en `ui/InputSurface.kt`.
- H.264 se decodifica sobre una `Surface`; MJPEG se decodifica a Bitmap.
- El contrato canónico está en `blender-backend/docs/protocol.md`.

## Capacidades principales

- Conexión, reconexión, estado de escena, objetos, archivos, undo y redo.
- Explorador remoto de archivos con ubicaciones y tokens opacos.
- Object/Edit y selección Vertex/Edge/Face.
- Picking, Box, Circle, Loop, Ring, shortest path y Tweak.
- Navegación orbital, vistas, cámara remota, wireframe y xray.
- Move/Rotate/Scale con sesiones reversibles, restricciones, orientación, valores,
  unidades, snap, referencias geométricas y edición proporcional.
- Herramientas Edit paramétricas: Extrude, Bevel, Inset, Subdivide, Loop Cut, Bridge,
  Knife y Bisect.
- Catálogo contextual Edit, modificadores, sombreado, aislamiento y escala de trabajo.
- H.264 preferido con fallback MJPEG.

## Invariantes técnicos

- Una sesión modal siempre reconstruye su preview desde el baseline original y produce
  un único paso de undo al confirmar.
- `ACTION_UP` confirma el último candidato visual estable; no repite el raycast.
- Un punto sondeado sobre una preview debe convertirse al baseline antes de persistirlo,
  salvo un centro de Rotate/Scale que deba permanecer estacionario.
- Las sesiones `transform.*` y `tool.*` son mutuamente excluyentes.
- Undo, redo y borrados cierran primero cualquier sesión activa.
- Las referencias RNA inválidas nunca deben detener el pump ni el broadcast.
- Knife acumula puntos interiores y divide una cara una sola vez en dos n-gons. No se
  sustituye por triangulación punto a punto.
- El snap táctil filtra primero por geometría visible y después clasifica el candidato.
- Un preset de escala de trabajo nunca reescala geometría ni modifica `scale_length`.
- Al abrir una escena, el preset mostrado se deduce de su `length_unit`; nunca se
  anuncia Mediana por defecto si el `.blend` está en milímetros o metros.
- La cámara remota no escribe en `rv3d`.

## Sistema de trabajo

- No se crean planes de trabajo.
- Solo existe una incidencia activa.
- Cada cambio debe ser pequeño y centrado en el comportamiento comunicado.
- No se aprovecha una reparación para rediseñar o corregir asuntos adyacentes.
- Cuando el usuario comunica un fallo distinto después de recibir una entrega, la
  incidencia anterior se considera aceptada salvo que diga expresamente que continúa.
- Una incidencia aceptada se consolida y se commitea antes de comenzar la siguiente.
- El código diagnóstico temporal se retira al cerrar.
- No se mantienen caminos antiguo y nuevo para una misma función.
- Las decisiones duraderas se resumen aquí; Git conserva el historial.
- APK y ZIP se compilan desde el mismo estado cuando cambia el contrato entre ambos.
- Las entregas Android se envían al usuario por Telegram cuando lo solicite.

## Criterio de diseño escalable

- El rail es una superficie limitada para herramientas gestuales frecuentes, no un
  catálogo completo.
- Mover/Rotar/Escalar viven en el rail desplegable de tools; en Edit añade Tweak.
- Duplicar vive en el radial. En Object conserva normal/enlazado y en Edit duplica la
  selección efectiva.
- Debajo del ojo hay un selector horizontal Object/Edit/Sculpt. Sculpt y el menú superior
  Layouts son por ahora únicamente presencia visual y no envían comandos.
- El panel de modificadores queda limitado entre ese selector de modos y el selector
  inferior de vistas/atajos, sin invadir ninguno de los dos.
- Pequeña/Mediana/Grande son la única elección de escala visible y fijan respectivamente
  `mm`/`cm`/`m`; no existe un selector de unidad independiente en Android.
- La cabecera muestra preset y unidad activos cuando Blender está conectado, por ejemplo
  `Conectado · Mediana · cm`.
- Los comandos discretos viven en menús contextuales.
- Los parámetros viven en una bandeja común.
- Las nuevas herramientas deben describirse mediante catálogo/esquema siempre que sea
  posible, evitando nuevas ramas específicas en Compose.
- Los componentes compartidos poseen disposición, estado, unidades y ciclo de sesión;
  Blender conserva únicamente la lógica geométrica específica.
- Mover usa un único `MovementControls` en Object y Edit sobre la misma sesión modal.
- El selector `mm`/`cm`/`m` junto a X/Y/Z gobierna tanto los valores escritos y
  mostrados como el paso, los botones y el snap de Mover.
- Android renueva `unitScaleLength` desde cada `scene_scale`; cargar otro `.blend` no
  conserva la conversión métrica de la conexión anterior.
- El selector y los pasos de snap viven en `ui/SnapControl.kt`; las bandejas declaran
  opciones y reciben valores, pero no vuelven a implementar su interfaz.
- El sondeo geométrico del backend permanece centralizado en `commands/snap.py`.
- La iconografía se resuelve por intención desde `ui/Iconography.kt`; las pantallas no
  eligen símbolos ni mantienen tablas de iconos propias.

## Compilación

```bash
export JAVA_HOME=/home/valle/.local/opt/jdk-17.0.20+8
export PATH="$JAVA_HOME/bin:$PATH"
./gradlew :android-client:app:assembleDebug

bash blender-backend/tools/build_addon.sh
```

Antes de entregar, revisar el diff, compilar ambos artefactos afectados y comprobar que
no quedan archivos o referencias temporales.
