# Blender Tablet Remote — guía para agentes

Este archivo es la fuente de verdad sobre arquitectura, estado realizado y reglas de
trabajo. No hay ningún plan activo ni planes en el repo: cada ciclo cerrado borra su
`PLAN_BACKEND.md`/`PLAN_FRONTEND.md`. El último ciclo cerró el **explorador de archivos**:
desde el menú Archivo ya no hay que teclear rutas del PC — "Abrir…" y "Guardar como…"
abren un diálogo que navega el disco remoto (`file.locations` con accesos DEFAULT/HOME/
ROOT y volúmenes montados, `file.browse` carpeta a carpeta con breadcrumbs opacos,
`file.default_folder` persistente, y `file.save_as` con `folder`+`name`). En el backend
se resuelven aliases (`@default`/`@home`/`@root`) y rutas relativas, y los `.blend` y
directorios se exponen como tokens opacos; en Android el parseo vive en `StateParser`
(`fileBrowse`/`fileLocations`) con fixtures y tests JVM. Queda pendiente, sin plan
asociado, el smoke manual en tablet real (dedo y Lenovo Pen) de H.264, de las mejoras
de rendimiento, del menú contextual, de la barra de tools y del propio explorador — no
se ha podido validar en hardware físico todavía. Si arranca trabajo nuevo, créese un
`PLAN_BACKEND.md`/`PLAN_FRONTEND.md` con el mismo formato de propiedad por directorio y
bórrese al cerrarlo: no dejar planes completados en el repo.

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
```

`android-frontend` ya no existe y no debe recrearse. El módulo Gradle es
`:android-client:app`.

## Arquitectura de ejecución

- Control: WebSocket JSON en `:8765`.
- Vídeo: HTTP en `:8766`, H.264 (`/stream.h264`, framing `btr-h264-v1`) como ruta
  preferida y MJPEG (`/stream.mjpg`) como fallback negociado si el cliente o el decoder
  no lo soportan. Separado del WebSocket para que un frame nunca retrase un comando.
- El servidor WebSocket usa solo stdlib. Sus threads meten mensajes en una cola.
- `bpy` y `bmesh` solo se tocan desde el hilo principal, dentro de `bridge._pump()`.
- La tablet tiene una cámara orbital propia (`camera.py`). Nunca escribir en `rv3d`;
  solo se lee la región para proyección/contexto. Sus matrices se cachean una vez por
  frame (`camera.begin_frame`), no se recalculan en cada `project`/`ray`.
- La captura OFFSCREEN es la ruta estable. POST_PIXEL existe y está probado, pero es
  experimental y dependiente del compositor.
- El hilo principal captura píxeles; ffmpeg (libx264 o mjpeg según la ruta) comprime
  fuera de Blender. Cada encoder arranca solo si su ruta tiene demanda.
- Android tiene una sola capa de entrada: `ui/InputSurface.kt`. El vídeo H.264 se
  decodifica sobre una `Surface` (`H264SurfaceDecoder`/`VideoSurface`), fuera del
  camino Bitmap/StateFlow/Compose; MJPEG sigue decodificando a Bitmap.

## Backend ya implementado

- Add-on Blender 4.2+, probado principalmente con Blender 5.2 LTS.
- Autostart, keepalive, host/puertos, token opcional y panel `N > Remote`.
- Protocolo v2, capabilities, enums, unidades, respuestas y errores controlados.
- Scene/object state, archivos, recientes, primitivas, cursor/origen, undo/redo.
- Explorador de archivos: `file.locations` (accesos DEFAULT/HOME/ROOT y volúmenes
  montados), `file.browse` (una carpeta por petición, breadcrumbs opacos, solo
  `DIRECTORY` y `BLEND`), `file.default_folder` persistente en la config propia del
  add-on, y `file.save_as` con `folder`+`name` (además del `path` legado). Alias
  `@default`/`@home`/`@root` y rutas relativas resueltas contra la carpeta por defecto;
  `name` valida basename (sin separadores, sin traversal). Feature `files.browse`.
- Object/Edit, submodos Vertex/Edge/Face y selección SET/ADD/REMOVE/TOGGLE.
- Picking táctil visible con umbral, Box, Circle, Loop y Ring.
- Move/Rotate/Scale directos para compatibilidad y sesiones modales propietarias para
  la UI táctil: preview, ejes/planos, orientación, snap, valor, confirm/cancel.
- Sesiones modales Object/Edit reconstruidas desde matrices/BMesh originales.
- Herramientas paramétricas Extrude, Bevel, Inset, Subdivide y Loop Cut (`tool.*`) con
  preview reversible desde una copia BMesh; nunca acumulan sobre la anterior.
- Loop Cut interactivo: `mesh.loop_cut` gana `falloff` (`SMOOTH|SPHERE|ROOT|SHARP|
  LINEAR|INVERSE_SQUARE`), `even`, `flip` y `clamp` (def. true; con false el `factor`
  admite ±2 y extrapola el borde). El anillo se orienta de forma coherente antes de
  deslizar (`_oriented_ring_segments`), sin lo cual un factor positivo subía el corte
  en una columna y lo bajaba en la vecina. `mesh.loop_probe` (read-only) devuelve
  `{hit, edge, factor, ring}` para colocar el corte tocando la malla; `tool.loop_pick`
  re-ubica una sesión LOOP_CUT activa (restaura la copia original antes de sondear: los
  índices de `edge` son de la malla original, no del preview). Feature
  `edit_tools.loop_cut` con `pick/probe/falloff/even/flip/clamp`.
- Snap incremental, rejilla, cursor y candidatos Vertex/Edge/Face bloqueables. En la
  sesión modal, `INCREMENT` cuadra el delta a múltiplos relativos del punto de partida y
  `GRID` clava la posición resultante a la rejilla mundial absoluta (un objeto que nace
  fuera de rejilla aterriza en ella); ROTATE/SCALE tratan GRID como INCREMENT.
- Cámara independiente, vistas estándar, Persp/Ortho y encuadre.
- `view.shading` (WIREFRAME/SOLID/TOGGLE; el wireframe activa xray y el pick cicla hacia
  detrás), `view.local` (aísla la selección ocultando el resto, el `/` de Blender) y
  `selection.more`/`selection.less` (crecer/decrecer adyacencias en Edit). `selection.box`
  y `selection.circle` operan en ambos modos: centros proyectados (object) o elementos
  del submodo (edit). El estado viaja como `shading` (top-level) y las capabilities
  anuncian `view.shading`, `view.local_view`, `selection.grow` y `selection.shapes`.
- Streaming MJPEG OFFSCREEN y POST_PIXEL con fallback, métricas y configuración.
- Captura forzada tras comandos discretos (`bridge.IMMEDIATE_FRAME_COMMANDS` +
  `capture.request_frame()`): selección, `object.select` y `transform.begin/confirm/
  cancel` no esperan al siguiente hueco de fps para reflejarse en el vídeo. Los gestos
  continuos quedan fuera a propósito.
- `streaming/frames.py`: MJPEG lee latest-wins y H.264 lee de una cola propia por cliente
  (`subscribe()`). No es simetría rota por capricho: con latest-wins, perder un access
  unit obliga a esperar al siguiente keyframe, lo que hace perder más y se realimenta.
  Medido antes de la cola: encoder produciendo 19 AU/s y cliente recibiendo 7,6 (61 %
  descartado, 10 saltos de secuencia en 10 s); después, 17,8 de 17,5 y cero saltos. Al
  tocar el streaming, medir esto y no solo el MJPEG: el fallo era invisible por MJPEG.
- `screen.py`: mientras hay clientes conectados impide que la pantalla del PC se apague
  (`xset`, X11), la enciende si ya estaba apagada y restaura el ahorro de energía tal cual
  al parar. Con un latido de 30 s por si el gestor de energía del escritorio la apaga por
  detrás. No es cosmético: con la pantalla apagada Blender se bloquea al redibujar y el
  add-on baja a 1,2 fps (ver Trampas conocidas). Sin `DISPLAY`/`xset` no hace nada.
- `commands/modifiers.py`: pila no destructiva SUBSURF, ARRAY, BEVEL, SOLIDIFY y
  BOOLEAN sobre datablock API (`add/remove/move/set/toggle/apply`), con
  `modifier.add_options` describiendo cada parámetro por tipo/rango/enum/filtro.
- `object.hide` / `object.reveal` (H / Alt+H de objetos vía `hide_set/hide_get`,
  distintos de `selection.hide/reveal` en Edit) y `transform.apply` (hornea T/R/S sin
  confundirse con `transform.reset`, con `shared_data` para mallas Alt+D).
- Estado y eventos ricos: `active.modifiers[]`, `hidden_objects:[{name,type}]`,
  `modifiers.changed`, `visibility.changed`.
- `context_snapshot()` usa `Mesh.total_vert_sel/edge_sel/face_sel` (O(1)) en vez de
  recorrer el bmesh completo, y `StateWatcher` cachea el resultado por firma barata:
  antes dominaba el hilo principal en mallas grandes y volvía tirones la selección, el
  escalado y el vídeo a la vez.
- `streaming/h264.py`: encoder libx264 (preset ultrafast, tune zerolatency, GOP corto,
  sin B-frames), framing binario `btr-h264-v1` por access unit con secuencia/timestamp,
  endpoint `/stream.h264` y negociación en `hello.stream`/`stream.configure`. MJPEG
  sigue operativo como fallback si el cliente no anuncia soporte H.264.
- Ronda de eficiencia con perfilado antes/después: caché de matrices de cámara por
  frame (`camera.begin_frame`, elimina 5-10 allocations por `project`/`ray`), firma de
  selección O(1) en sesiones modales (`modal.require` pasa de recorrer el bmesh a
  ~2 µs/llamada), inversa de `matrix_world` cacheada por sesión en vez de por nudge, y
  `mesh.loop_cut` sin reconstruir sets de la malla completa en cada preview. Verificado
  sin regresión: 391 tests headless y 42 GUI en verde.

## Android ya implementado

- Kotlin, Jetpack Compose, minSdk 26, compile/target SDK 36 y JDK 17.
- Pantalla de viewport dominante con chrome flotante y modo inmersivo.
- Conexión persistida, autoconexión, backoff, ping y reconexión por red/foreground.
- Cliente WebSocket v2 y decodificador MJPEG con recuperación y métricas.
- `RefreshPolicy.shouldRequestSceneSnapshot()`: durante una sesión modal/tool activa o
  con un `selection.pick` en vuelo no se pide `scene.get_state` extra en cada
  `scene.changed`; el vídeo y `transform.session` ya son el feedback en vivo.
  `requestState()` además deduplica peticiones en vuelo (`stateRequestInFlight`).
- Object/Edit, selección táctil, dedo/stylus/eraser, presión, inclinación y botón pen.
- Navegación: un dedo según herramienta; dos dedos pan+zoom; tap, doble tap y long-click.
- Feedback táctil local de tap (círculo + haptic) en `InputSurface` mientras se espera
  la respuesta remota del picking.
- Transformación modal con restricciones, orientación (desplegable de tipos de snap
  válidos por modo), unidades y confirm/cancel.
- Bandeja paramétrica para Extrude/Bevel/Inset/Subdivide/Loop Cut (`EditToolTray`), en
  una franja horizontal desplazable (no apilada en vertical): rótulo a la izquierda,
  parámetros en fila y descartar/confirmar fijos a la derecha.
- Loop Cut táctil: sin arista elegida, el rail arma `loopCutAwaitingTap` y el PRÓXIMO
  toque en la malla coloca el corte (`mesh.loop_probe` → `tool.begin` con `edge`+`factor`),
  y con sesión abierta el toque re-ubica (`tool.loop_pick`). La bandeja ofrece un
  stepper numérico "Posición" 0-100% (↔ `factor`, con `−`/`+` y valor editable; el
  arrastre fino sigue siendo deslizar el lápiz por el viewport, que alimenta
  `tool.nudge`), steppers de cortes/suavidad, botón ciclado de perfil (`LoopFalloff`) y
  toggles Uniforme/Invertir/Fijar (`ToolSession.parameters` pasó a `Map<String, Any?>`
  para conservar bools y string). Con `loopCutPick` no anunciado se conserva el flujo
  legacy (seleccionar arista y esperar el snapshot).
- `ui/ModifierPanel.kt`: inspector schema-driven desde `modifier.add_options` (add,
  parámetros tipados, viewport/render, reorder, apply, remove; Boolean con picker de
  objeto MESH excluyendo el activo).
- Menú `Ocultos` dinámico en `MenuBar.kt` (top, tras Objeto): una fila por objeto
  oculto, revela individual o "Mostrar todos", desaparece el anchor si la lista queda
  vacía.
- `HIDE_OBJECT`/`HIDE_GEOMETRY`/`REVEAL_GEOMETRY`/`APPLY_TRANSFORMS`/
  `APPLY_LOCATION/ROTATION/SCALE`/`ADD_OBJECT` en `ActionSurface.RADIAL`;
  `SHOW_HIDDEN_OBJECT`/`SHOW_ALL_HIDDEN_OBJECTS` en `TOP_DYNAMIC`; acciones de modifier en
  `ActionSurface.MODIFIER_PANEL`; `TOOL_LOOP_CUT` en `RAIL`. Los IDs ambiguos
  `HIDE_SELECTION`/`REVEAL_SELECTION` ya no existen.
- Menú Archivo, cursor/origen, vistas y conexión. El catálogo Add ya no está en el
  menú Objeto del top: vive en el long-click.
- Explorador de archivos (`ui/FileBrowserDialog.kt`): "Abrir…" y "Guardar como…" abren
  un diálogo que navega el disco del PC. Accesos DEFAULT/HOME/ROOT, breadcrumbs clicables,
  lista de carpetas y `.blend`, nombre editable al guardar y botón para fijar la carpeta
  por defecto. Los paths son tokens opacos (`StateParser.fileBrowse`/`fileLocations` con
  fixtures `file.browse.json`/`file.locations.json`). Sustituye al antiguo `SaveAsDialog`
  de escribir la ruta a mano; el botón se oculta si el backend no anuncia `files.browse`.
- Menú del long-click que primero sondea el contexto bajo el dedo. En Object Mode es
  un menú contextual flotante (`ContextSheet.kt`): lista anclada al punto tocado con
  navegación por niveles y X de cierre, cuyo primer nivel en el vacío ofrece
  "Agregar" con el catálogo completo por categorías. En Edit Mode sigue siendo el
  anillo radial (`QuickMenu.kt`), que ahí gana con pocas acciones frecuentes.
- Catálogo `ActionId → ActionSurface` con test de cero duplicidades (`SurfaceCatalogTest`).
- `H264ViewportStream`/`H264SurfaceDecoder`/`H264Framing`/`H264DecoderPolicy`: consumo
  del stream H.264 anunciado en `hello.stream`, `MediaCodec` sobre `Surface`
  (`VideoSurface`), descarte de access units obsoletas y resincronización en keyframe
  tras reconexión/error; cae a MJPEG si el servidor o el decoder no lo soportan.
- Ronda de eficiencia: `BitmapPool` RGB_565 + `inBitmap` en el decodificador MJPEG (sin
  `recycle()` de un bitmap en uso), `InputDebug` fuera de `AppUiState` para que un toque
  no recomponga todo `Workspace`, `ViewportLayer` sin parámetros que no usa en su rama
  caliente, `distinctUntilChanged` en `uiState` e IDs de comando cortos en vez de UUID.
  Verificado sin regresión: 75 tests JVM en verde y `assembleDebug` correcto.
- Menú contextual flotante (`ContextSheet.kt`) para el long-click en Object Mode y
  mudanza del catálogo Add del menú Objeto del top al vacío del long-click (primera
  entrada, con subniveles por categoría). `ADD_OBJECT` pasó de `TOP` a `RADIAL` en
  `SurfaceCatalog`, con test que fija que solo aparece en el vacío de Object Mode.
  Verificado: 76 tests JVM en verde y `assembleDebug` correcto.
- Barra superior de tools (`ui/TopToolbar.kt`) junto al ojo: wireframe (`view.shading`
  TOGGLE, pintado desde `state.blender.view.shading`), modificadores Mayús/Ctrl/Alt (fijan
  `selection.pick`/box/circle a TOGGLE/ADD/REMOVE) y undo/redo, movidos desde el rail. En
  Edit Mode, a la derecha de la misma barra, los submodos vértice/arista/cara para cambiar de
  selección sin abrir el rail. Cada botón se oculta si el backend no anuncia su
  capability (`view.shading`).
- Selección por caja B y círculo C en el long-click (`RADIAL`): arman el arrastre por
  forma (`ShapeTool` + overlay en `InputSurface`) y envían `selection.box`/`circle`.
  Salieron de la barra superior por decisión del usuario. En el anillo Edit sustituyen a
  `SELECT_INVERT` para no pasarse del tope de 8.
- Toast de error auto-descarta a los ~5 s: `client.clearError()` + `LaunchedEffect`
  sobre `state.error`.
- Teclado de vistas (`ViewFooter.kt`): 9 gira 180° (ya no duplica al 7), 5 enseña el
  estado real de la proyección (resaltado solo en ORTHO), `/` aísla la selección
  (`view.local`) y `+`/`−` crecen/decrecen la selección (`selection.more`/`less`,
  activos solo en Edit). El encuadre salió del teclado (queda como doble toque).
- `SelectionOp`/`ShapeTool` en `AppUiState`; el parser lee `shading` (top-level) y las
  capabilities `view.shading`/`local_view`/`selection.grow`/`shapes`. `updateState`
  conserva vista/shading/gizmo en los snapshots sin vista (pick/box/circle/more/less),
  que no traen ni `view` ni `shading`.

## Propiedad única de acciones

Cada acción ejecutable vive en una sola superficie visible:

- Top: archivo, estructura global, objeto (sin Add), modifiers y objetos ocultos.
- Barra superior de tools (`TOP_TOOLS`, junto al ojo): wireframe, Mayús/Ctrl/Alt, undo/redo
  y, en Edit, el submodo de selección.
- Rail: modo y herramienta activa.
- Footer/bandeja: parámetros de la herramienta activa.
- Footer de vistas (`FOOTER_VIEWS`): navegación, proyección, aislar y crecer/decrecer.
- Long-click: acciones frecuentes sobre el contexto señalado, la selección por forma
  (B/C) y el catálogo Add completo cuando se pulsa el vacío en Object Mode. En Object
  Mode se pinta como menú contextual flotante y en Edit como anillo radial.

Los gestos pueden invocar una acción existente porque no ocupan otra superficie.
`model/Actions.kt`, `model/RadialMenu.kt` y `SurfaceCatalogTest` son la autoridad.

Estado actual de las superficies añadidas en el último ciclo:

- Ocultar objeto/geometría y revelar geometría Edit: solo long-click (`RADIAL`).
- Revelar objetos: solo en el menú top dinámico `Ocultos`, nunca en radial.
- Modifiers: solo en su inspector (`ModifierPanel.kt`), abierto desde el anchor top
  `Modificadores`.
- Loop Cut: rail + bandeja de parámetros de `EditToolTray`.
- Aplicar transformaciones (`APPLY_TRANSFORMS`/`APPLY_LOCATION`/`APPLY_ROTATION`/
  `APPLY_SCALE`): viven en `RADIAL`, no en `Objeto > Aplicar` del top como se planeó
  originalmente; es una decisión de UI posterior al plan, no una divergencia a corregir.
- Agregar objetos (`ADD_OBJECT`): solo en el menú contextual flotante del long-click
  (Object Mode, vacío), con el catálogo por categorías y X de cierre. Ya no está en
  el menú Objeto del top.
- Submodo de selección (`SEL_VERTEX`/`SEL_EDGE`/`SEL_FACE`): solo en la barra superior
  de tools (`TOP_TOOLS`), visible en Edit Mode; ya no está en el rail.
- Deshacer/rehacer (`UNDO`/`REDO`): solo en `TOP_TOOLS`, fuera del rail.
- Wireframe (`VIEW_SHADING`): solo en `TOP_TOOLS`. Ctrl/Alt son modificadores locales,
  no acciones del catálogo.
- Caja (`TOOL_BOX`) y círculo (`TOOL_CIRCLE`): solo en `RADIAL` (long-click), en el
  vacío de Object Mode y en el anillo Edit. Ya no están en `TOP_TOOLS`; en Edit
  sustituyen a `SELECT_INVERT`, que sale del anillo para no pasarse del tope de 8.
- Aislar selección (`VIEW_LOCAL`) y crecer/decrecer (`SELECT_MORE`/`SELECT_LESS`): solo
  en el footer de vistas (`FOOTER_VIEWS`). `VIEW_FRAME_SELECTED` salió del catálogo: el
  encuadre de selección es el gesto de doble toque.

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
- Mutar datos desde el timer no actualiza el depsgraph; el vídeo se dibuja del evaluado.
  Si aparece otra ruta de captura, sincronizarlo antes de dibujar (ver Trampas).
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

Puede editar exclusivamente `blender-backend/**` (y `PLAN_BACKEND.md`, si existe un
ciclo abierto). Posee protocolo, fixtures, implementación Python, CLI y tests backend.
No edita `android-client/**`.

### Agente frontend

Puede editar exclusivamente `android-client/**` (y `PLAN_FRONTEND.md`, si existe un
ciclo abierto). Trabaja contra fixtures congelados. No edita backend, protocolo ni
fixtures.

### Archivos compartidos

`AGENTS.md`, `README.md` y configuración raíz solo los modifica el agente principal.
Los agentes no borran/reformatean cambios ajenos ni regeneran artefactos en el árbol
del otro.

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

## El viewport lento (resuelto el 2026-08-25)

El "mítico fallo de los 4 segundos" —seleccionar y transformar con retardo enorme
mientras orbitar iba perfecto— eran **tres causas independientes**, no una. Verificado en
tablet real: ahora va fluido. Si vuelve a aparecer, comprobar en este orden:

1. **Pantalla del PC apagada** (la gorda). `xset -q | grep "Monitor is"`. Bloquea el bucle
   de eventos de Blender entero. Lo previene `screen.py`. Detalle y medidas en Trampas.
2. **El servidor descartaba el 61 % de los AUs de H.264**, por usar un buffer latest-wins
   con un códec que no tolera perder frames sueltos. Arreglado con cola por cliente en
   `streaming/frames.py`. Medir siempre H.264, no MJPEG: por MJPEG esto es invisible.
3. **Depsgraph sin evaluar** antes de `draw_view3d` (`streaming/capture.py`). Real, pero
   cuesta ms, no segundos: no es la explicación de un retardo grande.

Aparte, el sentido de giro de `camera.orbit` se invirtió varias veces por medirlo desde
vistas equivocadas; re-medido y verificado con un test de regresión independiente de la
vista. Ver Trampas.

Lección de método: los tres se diagnosticaron **midiendo contra el servidor vivo** con
`tools/wsclient.py` y consumiendo `/stream.h264` y `/stats.json`, sin tocar la instalación
del usuario. Es mucho más rápido que leer código, y evita atribuir un síntoma al último
cambio que se tocó, que fue el error inicial de esta sesión.

## Trampas conocidas

- El objeto activo puede no estar seleccionado.
- Un timeout de `WSClient.recv()` deja ese stream de lectura inutilizable; abrir otro
  cliente si se necesita seguir. En Python 3.14 además un timeout envenena el
  `makefile` del socket ("cannot read from timed out object"), así que `drain_events`
  rehace el reader tras su timeout interno (no se fía del estado del buffered reader).
- `snap.query` necesita VIEW_3D real; headless no cubre raycast visual.
- `history.undo/redo` no tiene pila real en background.
- No cachear `find_view3d` por `as_pointer()` entre archivos: tras cargar otro `.blend`,
  Blender reutiliza las direcciones de los structs liberados y `as_pointer()` da falsos
  positivos, devolviendo una región caducada (probado: "Region not found in area or
  screen"). Documentado en `bpy_utils.find_view3d`; un intento de cachear por puntero
  se revirtió por esto.
- **El retardo de ~4 s al seleccionar/transformar mientras orbitar va fluido casi siempre
  es la PANTALLA DEL PC APAGADA (DPMS), no el add-on.** Con el monitor en DPMS off, el
  redibujo de la ventana de Blender se bloquea, y con él todo su bucle de eventos: los
  `bpy.app.timers` dejan de correr, así que `_pump()` no drena comandos ni captura vídeo.
  Solo se dispara cuando algo MUTA la escena (que es lo que obliga a Blender a redibujar);
  orbitar/panear/zoom no mutan nada en Blender —solo la cámara virtual de `camera.py`— y
  por eso siguen yendo perfectos. Medido el 2026-08-25 sobre la instalación real, con un
  cubo de 8 vértices y sin modificadores, alternando `xset dpms force on/off`:

  | pantalla | stream | latencia de comando |
  |---|---|---|
  | apagada  |  1,2 fps |  783 ms |
  | encendida| 19,3 fps |   21 ms |
  | apagada  |  1,2 fps |  693 ms |

  Reproducible a voluntad y determinista. Cómo confirmarlo en un minuto: `xset -q | grep
  "Monitor is"`. Diagnóstico diferencial antes de tocar código: la captura sigue costando
  6-37 ms (`/stats.json` → `last_cost_ms`), Blender está al 7-16 % de CPU y la GPU al 1 %,
  o sea que **no está trabajando: está bloqueado esperando el swap de buffers**. Si el
  perfil es ese, no busques el fallo en el add-on. Esto explica por qué el fallo "vuelve"
  tras cambios de código sin relación y por qué a veces "se arregla solo": depende de si
  la pantalla estaba encendida al probar. Desde entonces lo previene `screen.py`, que
  mantiene la pantalla despierta mientras haya clientes; si vuelve a aparecer, comprobar
  primero que esa inhibición sigue viva (`xset -q`) antes de sospechar de otra cosa.
- `gpu.types.GPUOffScreen.draw_view3d` dibuja el depsgraph EVALUADO y no lo evalúa: usa
  el que encuentre. Todo lo que el add-on muta desde el timer (`select_set`,
  `matrix_world`, `bmesh`) lo marca sucio pero no lo actualiza. Comprobado en
  `blender -b`: tras asignar `matrix_world`, `obj.evaluated_get(dg)` sigue devolviendo la
  matriz anterior hasta llamar a `view_layer.update()`; en Edit Mode pasa igual con el
  cage evaluado, que es lo que se dibuja, y `bmesh.update_edit_mesh` tampoco lo
  actualiza. Quien lo repara de forma incidental es cualquier `bpy.ops` (p. ej. el
  `undo_push` de `transform.confirm`) o un redibujo de la propia ventana de Blender, y
  ahí está el peligro: la frescura del vídeo acaba dependiendo de si el PC está
  redibujando, no del add-on. `ViewportCapture._grab_offscreen` lo sincroniza con
  `bpy.context.evaluated_depsgraph_get()`; no quitar esa llamada. En POST_PIXEL no hace
  falta: ahí dibuja Blender.
  OJO con atribuirle a esto el retardo de 4 s: se le atribuyó el 2026-08-25 y era falso.
  Medido después, la captura cuesta 6-37 ms con o sin la llamada, y el retardo real venía
  de la pantalla apagada (entrada anterior). La sincronización sigue siendo correcta y se
  queda —evita depender de que el PC redibuje—, pero no es la explicación de ese síntoma.
  Ojo al escribir tests para esto: el bloque `[10]` de `run_gui_tests.py` se ejecutó con
  la llamada desactivada y siguió en verde, porque con la ventana de Blender visible es
  Blender quien evalúa por su cuenta y enmascara el fallo. No hay prueba automática que
  lo distinga; solo se reproduce en el escenario real, con el PC sin redibujar.
- La suite GUI no está al 100 %: `el fotograma cambia al orbitar` (bloque `[9]`,
  POST_PIXEL) falla devolviendo dos fotogramas idénticos byte a byte. Reproducido en
  tres ejecuciones seguidas, con y sin cambios en la captura, así que no es una
  regresión del ciclo del depsgraph. Encaja con que POST_PIXEL publique el framebuffer
  de la ventana del PC, que no se mueve cuando la cámara que orbita es la de la tablet.
  Sin diagnosticar a fondo.
- El sentido de giro de `camera.orbit` NO se puede medir sobre un punto proyectado
  desde una vista de eje: es un turntable sobre el Z GLOBAL, y su sentido EN PANTALLA
  depende de la vista (desde FRONT/BACK se invierte respecto a la vista por defecto,
  porque el "derecha" de pantalla cambia de lado; desde la cenital el desplazamiento
  lateral es cero). Se invirtió el signo DOS veces por medirlo desde esas vistas. El
  signo actual (`-dx`, `-dy`) es el que hace que la escena acompañe al dedo en la vista
  por defecto, y se comprueba de forma INDEPENDIENTE de la vista midiendo la rotación
  RELATIVA de la cámara: `dx>0` debe girarla sobre el Z global en sentido horario (eje Z
  negativo) y `dy>0` sobre el eje derecha de la cámara. Hay test de regresión en
  `run_gui_tests.py` (`[13] Signo del giro de cámara`). Android manda `dx>0` a la derecha
  y `dy>0` hacia abajo, sin invertir nada (`InputSurface.handleSingle`); el signo se
  decide entero en el backend.
- `view.gizmo` y su modelo Android no tienen consumidor visual actual, pero siguen en
  protocolo y tests: son compatibilidad deliberada, no código muerto.
- `Modifiers.kt` Android contiene `clickableNoRipple`; no tiene relación con modifiers
  Blender y está ampliamente usado.
- El add-on es 0.1.0 en manifest/fuente. La app Android es 0.1.2.

## Objetivos activos

Ninguno. Los ciclos recientes están completos en código y tests: 434 tests headless +
73/74 GUI (el fallo restante es el de POST_PIXEL, preexistente y sin diagnosticar) +
199/200 contrato (el fallo restante es ambiental, `hello.stream.running` en Blender
`--background` sin GPU) en backend, 84 tests JVM + `assembleDebug` en Android. Pendiente
sin plan asociado: smoke manual en tablet real con dedo y Lenovo Pen para validar H.264,
las mejoras de rendimiento, el menú contextual, la nueva barra de tools, el Loop Cut
interactivo y el explorador de archivos en condiciones reales. Cualquier objetivo nuevo
se documenta en un `PLAN_BACKEND.md`/`PLAN_FRONTEND.md` creado para ese ciclo y se borra
al cerrarlo.
