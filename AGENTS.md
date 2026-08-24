# Blender Tablet Remote — guía para agentes

Este archivo es la fuente de verdad sobre arquitectura, estado realizado y reglas de
trabajo. Los únicos planes activos son `PLAN_BACKEND.md` y `PLAN_FRONTEND.md`.

## Objetivo del producto

La tablet Android es una interfaz táctil para Blender, no un escritorio remoto.
Blender sigue siendo el motor 3D en el PC; Android muestra el viewport remoto, envía
intención y ofrece controles adaptados a dedo y stylus.

Alcance actual: Object Mode y Edit Mode. Sculpt, materiales, nodos, animación y un
puente X11 de gizmos nativos no forman parte del ciclo activo.

## Estructura real

```text
blender-backend/                    add-on Python de Blender
  blender_tablet_remote/            código instalable
  docs/protocol.md                  contrato canónico
  fixtures/v2/                      frontera estable para Android
  tests/                            aceptación headless, GUI y contrato
  tools/                            build, servidor, CLI y diagnóstico
android-client/                     única app Android real
  app/src/main/                     Kotlin + Jetpack Compose
  app/src/test/                     pruebas JVM
README.md                           entrada para humanos
PLAN_BACKEND.md                     único plan backend activo
PLAN_FRONTEND.md                    único plan Android activo
```

`android-frontend` ya no existe y no debe recrearse. El módulo Gradle es
`:android-client:app`.

## Arquitectura de ejecución

- Control: WebSocket JSON en `:8765`.
- Vídeo: HTTP MJPEG en `:8766`. Separarlo evita que un frame retrase un comando.
- El servidor WebSocket usa solo stdlib. Sus threads meten mensajes en una cola.
- `bpy` y `bmesh` solo se tocan desde el hilo principal, dentro de `bridge._pump()`.
- La tablet tiene una cámara orbital propia (`camera.py`). Nunca escribir en `rv3d`;
  solo se lee la región para proyección/contexto.
- La captura OFFSCREEN es la ruta estable. POST_PIXEL existe y está probado, pero es
  experimental y dependiente del compositor.
- El hilo principal captura píxeles; ffmpeg comprime fuera de Blender.
- Android tiene una sola capa de entrada: `ui/InputSurface.kt`.

## Backend ya implementado

- Add-on Blender 4.2+, probado principalmente con Blender 5.2 LTS.
- Autostart, keepalive, host/puertos, token opcional y panel `N > Remote`.
- Protocolo v2, capabilities, enums, unidades, respuestas y errores controlados.
- Scene/object state, archivos, recientes, primitivas, cursor/origen, undo/redo.
- Object/Edit, submodos Vertex/Edge/Face y selección SET/ADD/REMOVE/TOGGLE.
- Picking táctil visible con umbral, Box, Circle, Loop y Ring.
- Move/Rotate/Scale directos para compatibilidad y sesiones modales propietarias para
  la UI táctil: preview, ejes/planos, orientación, snap, valor, confirm/cancel.
- Sesiones modales Object/Edit reconstruidas desde matrices/BMesh originales.
- Herramientas paramétricas Extrude, Bevel, Inset y Subdivide con preview reversible.
- Snap incremental, rejilla, cursor y candidatos Vertex/Edge/Face bloqueables.
- Cámara independiente, vistas estándar, Persp/Ortho y encuadre.
- Streaming MJPEG OFFSCREEN y POST_PIXEL con fallback, métricas y configuración.

No están implementados todavía: `modifier.*`, `LOOP_CUT`, `object.hide/reveal` para
objetos, `hidden_objects`, eventos de modifiers/visibility y `transform.apply`.

## Android ya implementado

- Kotlin, Jetpack Compose, minSdk 26, compile/target SDK 36 y JDK 17.
- Pantalla de viewport dominante con chrome flotante y modo inmersivo.
- Conexión persistida, autoconexión, backoff, ping y reconexión por red/foreground.
- Cliente WebSocket v2 y decodificador MJPEG con recuperación y métricas.
- Object/Edit, selección táctil, dedo/stylus/eraser, presión, inclinación y botón pen.
- Navegación: un dedo según herramienta; dos dedos pan+zoom; tap, doble tap y long-click.
- Transformación modal con restricciones, orientación, snap, unidades y confirm/cancel.
- Bandeja paramétrica para Extrude/Bevel/Inset/Subdivide.
- Menú Archivo, Add completo, cursor/origen, vistas y conexión.
- Menú radial que primero sondea el contexto bajo el dedo.
- Catálogo `ActionId → ActionSurface` con test de cero duplicidades.

No están implementados todavía: modelos/cliente/UI de modifiers, Loop Cut, apply,
ocultar objetos y menú dinámico de objetos ocultos.

## Propiedad única de acciones

Cada acción ejecutable vive en una sola superficie visible:

- Top: archivo, estructura global, objeto, modifiers y objetos ocultos.
- Rail: modo, submodo y herramienta activa.
- Footer/bandeja: parámetros de la herramienta activa y vistas.
- Long-click radial: acciones frecuentes sobre el contexto señalado.

Los gestos pueden invocar una acción existente porque no ocupan otra superficie.
`model/Actions.kt`, `RadialMenu.kt` y `SurfaceCatalogTest` son la autoridad.

Para el trabajo pendiente:

- H/Ocultar solo en long-click.
- Revelar objetos solo en el menú top dinámico `Ocultos`.
- Revelar geometría Edit permanece en long-click.
- Modifiers solo en su inspector abierto desde top.
- Loop Cut en rail y su bandeja de parámetros.
- Aplicar transformaciones en `Objeto > Aplicar`.

## Contrato compartido

Orden obligatorio para cualquier mensaje nuevo:

1. `blender-backend/docs/protocol.md`.
2. `blender-backend/blender_tablet_remote/protocol.py` (enums/features/units).
3. Fixtures completas en `blender-backend/fixtures/v2/`.
4. `blender-backend/tests/android_contract.py`.
5. Implementación backend y parser/cliente Android.

El agente backend es propietario del protocolo y fixtures. El agente Android los lee,
no los modifica. Si algo no alcanza, informa al agente principal antes de inventar un
campo, default o nombre wire.

Los parsers Android deben ser tolerantes a servidores más nuevos, pero las fixtures y
tests deben detectar renombres y divergencias.

## Reglas backend

- Un comando tiene firma `f(payload: dict) -> dict | None` y decorador `@command`.
- Un módulo nuevo debe importarse en `commands.load_all()`.
- Usar `CommandError` con códigos estables; documentarlos.
- No llamar `bpy` desde threads de red.
- Preferir data API, matrices y `bmesh.ops`; operadores solo con override justificado.
- Una preview paramétrica siempre reconstruye desde el backup, nunca acumula.
- Una sesión confirmada crea un undo; cancel no deja residuos ni undo.
- Cargar/new `.blend` debe conservar el servidor y resetear watcher, cámara y sesiones.
- No cachear punteros Area/Region/Space entre archivos/workspaces.
- Las transformaciones directas antiguas son compatibilidad usada por CLI/tests; no
  eliminarlas solo porque Android prefiera sesiones.

## Reglas Android

- `MainViewModel` coordina UI y cliente; el JSON se parsea en `StateParser`.
- `RemoteBlenderClient` es la frontera testable; no enviar comandos desde composables.
- Toda entrada del viewport vive en `InputSurface`; no crear otra capa competidora.
- Respuestas se enrutan por el comando guardado en `pending[id]`.
- Los nudges caros se serializan/coalescen; no inundar Blender desde sliders/drag.
- No hardcodear catálogos que anuncia `server.capabilities`/`*.add_options`.
- Ocultar una capacidad si el backend no la anuncia; no dejar un botón que falle.
- Mantener objetivos táctiles amplios, estética de `Theme.kt` y viewport dominante.
- No duplicar acciones entre top, rail, footer, panel y radial.

## Separación de dos agentes

### Agente backend

Puede editar exclusivamente `blender-backend/**` y `PLAN_BACKEND.md`. Posee protocolo,
fixtures, implementación Python, CLI y tests backend. No edita `android-client/**`.

### Agente frontend

Puede editar exclusivamente `android-client/**` y `PLAN_FRONTEND.md`. Trabaja contra
fixtures congelados. No edita backend, protocolo ni fixtures.

### Archivos compartidos

`AGENTS.md`, `README.md`, planes y configuración raíz solo los modifica el agente
principal. Los agentes no borran/reformatean cambios ajenos ni regeneran artefactos en
el árbol del otro.

## Build y pruebas

```bash
# Android: Java 8 del sistema no sirve
JAVA_HOME=/home/valle/.local/opt/jdk-17.0.20+8 \
  ./gradlew --no-daemon :android-client:app:testDebugUnitTest \
  :android-client:app:assembleDebug

# Backend headless
blender --background --python blender-backend/tests/run_tests.py

# Caminos con viewport/captura/picking
blender --python blender-backend/tests/run_gui_tests.py

# Contrato (servidor separado)
blender --background --python blender-backend/tools/run_server.py -- \
  --port 8801 --token devtoken
python3 blender-backend/tests/android_contract.py --port 8801 --token devtoken

# ZIP instalable
bash blender-backend/tools/build_addon.sh
```

No congelar conteos de tests en documentación: cambian al ampliar la suite. Informar el
resultado real de cada ejecución.

## Trampas conocidas

- El objeto activo puede no estar seleccionado.
- Un timeout de `WSClient.recv()` deja ese stream de lectura inutilizable; abrir otro
  cliente si se necesita seguir.
- `snap.query` necesita VIEW_3D real; headless no cubre raycast visual.
- `history.undo/redo` no tiene pila real en background.
- `view.gizmo` y su modelo Android no tienen consumidor visual actual, pero siguen en
  protocolo y tests: son compatibilidad deliberada, no código muerto.
- `Modifiers.kt` Android contiene `clickableNoRipple`; no tiene relación con modifiers
  Blender y está ampliamente usado.
- El add-on es 0.1.0 en manifest/fuente. La app Android es 0.1.2.

## Objetivos activos

Ejecutar `PLAN_BACKEND.md` y `PLAN_FRONTEND.md` en paralelo después de congelar el
contrato. Cualquier objetivo nuevo debe incorporarse a uno de esos dos documentos o
reemplazarlos; no crear planes adicionales.
