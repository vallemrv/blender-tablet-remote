# Blender Tablet Remote — guía para agentes

Este archivo es la fuente de verdad sobre arquitectura, estado realizado y reglas de
trabajo. El 2026-08-27 el usuario dio por concluido el ciclo funcional anterior tras
validarlo en tablet y abrió una nueva serie de reparaciones desde `000`. Esa serie
(`000`–`003`) quedó implementada, probada y retirada por autorización del usuario el
2026-08-28; su estado funcional relevante está consolidado en este archivo. La serie
siguiente (`000`–`007`) entregó Plano/Suave, Loop Cut múltiple, iconos del footer,
Mirror, controles de edición proporcional, indicadores de pulsación larga, el Knife
por arrastre y la recuperación del viewport H.264. El usuario validó el conjunto en
tablet y autorizó su cierre. Sus planes se retiraron y la próxima escalada funcional
debe abrir una serie nueva desde `000`.

La primera reparación de esta serie corrige tres defectos Android: el radial resuelve
todos sus sectores con un único hit-test geométrico y `QuickAction.onClick` es el último
parámetro funcional (antes la trailing lambda de Kotlin se asignaba a `onLongClick` y
el tap quedaba vacío); Borrar aparece directamente en Edit y elige
`VERTS`/`EDGES`/`FACES` por submodo; y los campos numéricos usan un `BasicTextField`
compacto de 34 dp, pues el mínimo de 56 dp de Material3 recortaba el texto dentro de
las bandejas horizontales.

La serie `000` de esta tanda retira Recientes del menú Archivo y agrupa Duplicar/Duplicar
enlazado en una única familia del rail con chevrón, pulsación larga, variante recordada
e icono propio. Las familias multivariante de `edit_toolbar` también pintan el icono de
la variante recordada aunque la sesión esté cerrada. En Edit, el mismo botón invoca
`mesh.duplicate`: BMesh copia exclusivamente la selección efectiva de vértices,
aristas o caras y deja seleccionada la copia; nunca duplica el objeto entero. El usuario
validó esta serie en tablet el 2026-08-28 y autorizó su cierre; sus dos planes se
retiraron y su estado queda consolidado aquí.

La serie siguiente (`001`–`014`) quedó cerrada por autorización expresa del usuario el
2026-08-29 tras contrastar planes, código y pruebas. Entregó el primer punto arrastrable
de Knife con `EDGE_CENTER`; avisos de duplicado y encadenado posterior a Mover; estado
de sombreado y toggles Suave/Plano y Aislar/Ver todo; selección de camino más corto con
Ctrl; rail compacto e inspector de modificadores plegable; sondeo contextual sobre
geometría evaluada; trabajo fiable a escala milimétrica, xray y picking Edit sobre la
jaula original; unidades y steppers coherentes; Inset compatible con la costura de
Mirror y clipping de Mirror en transformaciones remotas; GRID restringido; Tweak
seleccionar/mover, con órbita cuando falla el pick y sin bandeja inferior; y Circle de
LoopTools condicionado a la disponibilidad real del add-on. Las validaciones automáticas
aplicables quedaron ejecutadas; la validación táctil pendiente se retiró del alcance al
cerrar la serie. Sus planes se eliminaron y la próxima serie vuelve a empezar en `000`.

La serie `000` corrigió Mirror Clipping durante las transformaciones remotas. El
`merge_threshold` del modificador ya no se usa para decidir qué vértices pertenecen a
la costura: solo quedan fijados los que estaban numéricamente sobre el plano; un vecino
dentro del umbral puede moverse y escalar con normalidad, y sigue sin poder cruzarlo.
El inspector Android muestra floats con la precisión de su `step`, por lo que el umbral
por defecto se ve como `0.001` y los botones −/+ cambian una milésima visible. Backend
809/809 y tests JVM/`assembleDebug` quedaron en verde.

La serie `001` impide que el menú radial interrumpa movimientos lentos. Mientras
`transform.session` o `tool.session` está activa, `InputSurface` no programa ni dispara
la pulsación larga; si la sesión se activa con el dedo apoyado, también cancela el timer
pendiente. Sin sesión, el long-click continúa disponible. Tests JVM y `assembleDebug`
quedaron en verde.

La serie `002` retira el círculo derecho de órbita durante Tweak. Aunque Tweak
usa internamente una `transform.session`, es un gesto directo que ya conserva la
navegación con dos dedos; el círculo era redundante y ocupaba viewport. Las demás
transformaciones y tools siguen mostrándolo. Tests JVM y `assembleDebug` quedaron en
verde.

La serie `003` hace Knife atómico y directo. El crash real del 2026-08-30 ocurrió
tras una ráfaga de `tool.knife_drag`, un `Anchor not on mesh surface` y el siguiente
dibujo OFFSCREEN: una preview fallida podía dejar el BMesh parcialmente partido. Knife
restaura ahora el backup ante cualquier error y retira las anclas tentativas. El primer
BEGIN→END válido crea inicio y final, por lo que un solo arrastre ya corta; la bandeja
lo explica y Android sondea a 15 Hz. Verificado con 811/811 headless y en vivo con
OFFSCREEN/H.264 más 120 UPDATE consecutivos sin caída.

La serie `004` convirtió Knife en una herramienta táctil multitrazo. BEGIN y
UPDATE solo ajustan el candidato y END fija un único punto, de modo que apoyar el lápiz
no decide una posición irreversible. «Nuevo corte» termina la línea actual y permite
empezar otra independiente dentro de la misma sesión/undo; deshacer puede retroceder
entre líneas y el estado publica trazos separados para que el overlay no los una. Esto
habilita construcciones y reducciones topológicas 4→2 sin salir de Knife. Tras el primer
feedback real se detectó que Android
confirmaba la muestra inestable de ACTION_UP y que los radios de snap eran demasiado
pequeños; la corrección confirma la última muestra DOWN/MOVE visible y amplía los radios
priorizados de vértice/centro/arista. El segundo feedback reveló que la distancia cero
de EDGE seguía robando los candidatos: ahora la prioridad es categórica VERTEX >
EDGE_CENTER > EDGE, con radios 0,080/0,070/0,042 y búsqueda en caras vecinas.
El tercer feedback descartó esa vecindad porque alcanzaba vértices posteriores y mostró
que los radios automáticos podían impedir elegir una arista. Knife limita ahora snap a
la cara visible, ofrece destino explícito Auto/Vértice/Medio/Arista y difiere toda
mutación de BMesh hasta Confirmar; durante el dibujo solo existe el overlay.
El cuarto feedback mostró que diferir también los trazos ya terminados impedía que los
nuevos se anclaran a sus vértices. «Nuevo corte» fija ahora el trazo terminado en una
preview reversible; solo el activo queda como overlay. Confirmar reconstruye todo desde
el backup, y un baseline explícito de undo mantiene Edit Mode al deshacer Knife.

La serie `005` resolvió finalmente los cortes caóticos del Knife. La causa no era
el snap: `_poke` integraba cada punto interior por separado, borraba la cara y generaba
un abanico de triángulos hacia todas sus esquinas. El motor acumula ahora los puntos
interiores hasta volver al contorno y `_split_face_with_chain` divide esa cara una sola
vez en dos n-gons que comparten exactamente la cadena dibujada. Esta solución está
validada por el usuario y no debe sustituirse por triangulación punto a punto. Su límite
conocido son cadenas interiores que atraviesan caras distintas, que aún conservan el
fallback antiguo. La deuda de contrato detectada en ese ciclo era un fixture de
capabilities anterior a los cambios ya presentes en el add-on.

El 2026-08-30 el usuario autorizó retirar los planes `000`–`005` y el diagnóstico de
Knife, incluidas las validaciones pendientes que conservaban esos documentos. El estado
funcional y las limitaciones relevantes quedan consolidados aquí. La próxima serie de
refinado y escalado empieza de nuevo en `000`.

La serie posterior `000` saneó esa deuda contractual contra el ZIP recién construido e
instalado. `capabilities.json` refleja ahora `edit_tools.version = 9`, los umbrales y
modos de snap, el commit diferido, el Knife multitrazo, sus parámetros de catálogo y
toolbar y `tool.knife_new_stroke`. El fixture de `hello.stream` ya no fija `running` ni
`port`, porque son estado y configuración de ejecución, no contrato estable. El test
añade comprobaciones explícitas de versión y Knife para impedir otro verde falso. El
contrato, headless y Android quedaron verdes. El usuario autorizó ejecutar y cerrar
este saneamiento el 2026-08-30; la siguiente serie vuelve a `000`.

La serie posterior `000` retiró por autorización del usuario toda la ruta descartada
que leía el framebuffer del viewport del PC para intentar transmitir su interfaz
nativa. Se eliminaron implementación, draw handlers, preferencias, métricas, fallback,
pruebas y documentación. GPUOffScreen es la única fuente de vídeo y usa exclusivamente
la cámara independiente de la tablet; H.264 preferido y MJPEG fallback permanecen como
transportes. Backend, GUI, contrato y Android quedaron verdes contra el ZIP reinstalado.
La próxima serie vuelve a `000`.

La serie activa `000` abre la base de transformaciones paramétricas, empezando por
Mover en Object Mode. La bandeja conservará el gesto de lápiz y las restricciones
X/Y/Z, añadirá valores exactos independientes, incremento editable con unidad y una
referencia geométrica REL que no depende del pivote. Los planes propietarios son
`000_PLAN_BACKEND_TRANSFORMACIONES_PARAMETRICAS.md` y
`000_PLAN_FRONTEND_TRANSFORMACIONES_PARAMETRICAS.md`.
REL es ahora un ancla fuente de la selección: se sondea en verde, queda roja al
fijarse y se reproyecta acompañando el movimiento. Con snap geométrico, el backend
excluye los objetos móviles del destino y alinea exactamente ancla→destino, lo que
permite colocar vértice contra vértice entre objetos sin usar el pivote.
En esta bandeja el snap de posicionamiento deliberadamente solo expone destinos
exactos: VERTEX, EDGE_CENTER y FACE_CENTER (además de NONE e INCREMENT). Tanto el
sondeo del ancla fuente como el del destino comparten radios pegajosos de 0,080,
0,070 y 0,065 respectivamente; no se ofrece arista o cara arbitraria porque produciría
un punto impreciso y haría temblar la intención táctil.

El snap que condujo a esa solución es reutilizable: primero se restringen candidatos a
la cara visible del raycast para excluir geometría posterior; después se clasifican en
VERTEX, EDGE_CENTER y EDGE; el modo explícito filtra una categoría y AUTO aplica
prioridad categórica. Para que AUTO no haga inaccesible una arista, usa radios menores
de prioridad (0,035 vértice y 0,028 centro), mientras los modos forzados conservan los
radios pegajosos completos (0,080 y 0,070). EDGE mantiene 0,042. Este patrón —visibilidad,
clasificación, intención explícita y radios distintos para AUTO/forzado— debe reutilizarse
en futuros snaps táctiles.

La congelación observada después se diagnosticó en el servidor vivo: una sesión modal
retenía un `Object` RNA eliminado, `session.status()` lanzaba `ReferenceError` durante
el broadcast y la excepción desregistraba el timer `_pump`, dejando los sockets abiertos
pero sin procesar comandos ni frames. El backend ahora blinda pump/broadcast, invalida
referencias RNA desaparecidas, hace mutuamente excluyentes `transform.*` y `tool.*`, y
cierra sesiones antes de undo/redo y borrados. Android no envía `tool.nudge` para Knife
ni Bisect. La reproducción viva `transform.begin → delete` y `transform.begin → KNIFE`
mantiene el servidor operativo.

El último
ciclo cerrado entregó el **menú Edit contextual** alimentado por `edit.catalog`:
Vértice/Arista/Cara según el selector, con Bridge Edge Loops, F, P, Y, Normales y
variantes de Extrude, más la página "Atajos" del footer y el círculo de navegación
durante sesiones. El núcleo de KNIFE se entregó como sesión táctil de polilínea
(puntos por toque, overlay, bandeja con deshacer/cerrar/snap). `mesh.dissolve` está
habilitado para Vértice/Arista/Cara y se mantiene separado de Delete.
Antes cerró la reorganización de superficies:
Object/Edit salen del rail a una barra de modo horizontal propia junto al ojo
(`TOP_MODE`), la bandeja de transformación Mover/Rotar/Escalar adopta la misma
composición horizontal que `EditToolTray` (rótulo, propiedades desplazables y
descartar/confirmar fijos) y el teclado de vistas se eleva cuando una bandeja inferior
ocupa su zona. Antes cerró el **explorador de archivos**: desde el menú Archivo ya no
hay que teclear rutas del PC — "Abrir…" y "Guardar como…" abren un diálogo que navega
el disco remoto (`file.locations` con accesos DEFAULT/HOME/ROOT y volúmenes montados,
`file.browse` carpeta a carpeta con breadcrumbs opacos, `file.default_folder`
persistente, y `file.save_as` con `folder`+`name`). En el backend se resuelven aliases
(`@default`/`@home`/`@root`) y rutas relativas, y los `.blend` y directorios se exponen
como tokens opacos; en Android el parseo vive en `StateParser`
(`fileBrowse`/`fileLocations`) con fixtures y tests JVM. Las pruebas en tablet real con
dedo y Lenovo Pen ya están en curso: el conjunto funciona bien y de ese uso saldrán los
nuevos ciclos de mejoras y reparaciones. Si arranca trabajo nuevo, créese el plan
propietario correspondiente con la numeración reiniciada en `000`.

## Gestión y numeración de planes

- Un plan solo está ejecutado cuando se cumplen todos sus criterios de cierre; no basta
  con que el núcleo sea usable ni con llamar “no bloqueante” a lo que el propio plan
  exige.
- Antes de borrar planes, contrastar cada fase con `AGENTS.md`, código y pruebas. No
  fiarse del encabezado antiguo del documento si contradice ese estado.
- Si todos los planes existentes están realmente ejecutados, el agente principal puede
  borrarlos a petición del usuario. El historial funcional que siga siendo relevante se
  consolida antes en este archivo.
- Después de vaciar todos los planes, la siguiente serie vuelve a empezar en `000`, con
  archivos separados por propietario, por ejemplo `000_PLAN_BACKEND_<TEMA>.md` y
  `000_PLAN_FRONTEND_<TEMA>.md`. Dentro de una misma serie ambos comparten número.
- Si queda un solo criterio pendiente, no se reinicia la numeración y no se borran en
  bloque los planes. Se termina, se elimina explícitamente del alcance con autorización
  del usuario, o se traslada a un nuevo plan dejando trazabilidad.
- Cierre autorizado del 2026-08-26: se borraron todos los planes, incluido el `000`
  parcial, y esta versión se declaró finalizada. El bloqueo X/Y/Z de Extrude
  (FREE|X|Y|Z con GLOBAL|LOCAL|VIEW, solo REGION) y el roll de cámara sí quedaron
  entregados. La toolbar contractual por familias, Inset INDIVIDUAL y Bisect quedaron
  fuera de esta versión; solo volverán al alcance si el feedback futuro los prioriza.

## Objetivo del producto

La tablet Android es una interfaz táctil para Blender, no un escritorio remoto.
Blender sigue siendo el motor 3D en el PC; Android muestra el viewport remoto, envía
intención y ofrece controles adaptados a dedo y stylus.

Alcance actual: Object Mode y Edit Mode. Sculpt, materiales, nodos y animación no
forman parte del ciclo activo.

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
- GPUOffScreen es la única fuente de captura. Usa la cámara independiente de la tablet
  y no transmite el framebuffer ni la interfaz nativa del PC.
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
- Loop Cut múltiple: `tool.loop_pick(add=true)` fija el preview actual como base y
  abre otro corte sobre la topología resultante; `tool.loop_pop` vuelve al anterior.
  `loop_count` viaja en la sesión, confirmar agrupa todo en un undo y cancelar restaura
  la malla previa al primer corte. Feature `edit_tools.loop_cut.multiple/pop`.
- Catálogo contextual de Edit (`edit.catalog`, feature `edit_catalog`): acciones
  agrupadas por VERTEX/EDGE/FACE con id estable, etiqueta, requisitos, tipo de ejecución
  (DISCRETE/SESSION), variantes y parámetros tipados. Implementadas este ciclo:
  `mesh.make_edge_face` (F, crea arista/cara o rellena vía `contextual_create`),
  `mesh.bridge_loops` + sesión `BRIDGE_EDGE_LOOPS` (`twist_offset`/`merge`/`merge_factor`
  sobre `bmesh.ops.bridge_loops`), `mesh.split` (Y), `mesh.separate` (P, `bpy.ops.mesh.
  separate`), `mesh.normals_recalculate`/`mesh.normals_flip`, y variantes de
  `mesh.extrude` (`REGION`/`ALONG_NORMALS`/`INDIVIDUAL`). KNIFE es una sesión táctil
  (`tool.knife_point/pop/close`, motor geométrico en `commands/knife.py` sin
  `knife_tool` ni `bisect_plane`). `mesh.dissolve` está habilitado para
  VERTS/EDGES/FACES y se mantiene separado de Delete.
- Knife admite `tool.knife_drag` por fases BEGIN/UPDATE/END/CANCEL: mover solo sondea,
  soltar fija el candidato mostrado y reconstruye desde el backup. La cara visible es
  un destino exacto; vértice y arista usan umbrales separados sobre esa misma cara.
  `tool.status` reproyecta las anclas 3D mediante `projected_points` tras mover cámara.
- Snap incremental, rejilla, cursor y candidatos Vertex/Edge/Face bloqueables. En la
  sesión modal, `INCREMENT` cuadra el delta a múltiplos relativos del punto de partida y
  `GRID` clava la posición resultante a la rejilla mundial absoluta (un objeto que nace
  fuera de rejilla aterriza en ella); ROTATE/SCALE tratan GRID como INCREMENT.
- Las tools paramétricas anuncian snap escalar por schema y Extrude REGION admite
  candidato geométrico bloqueable mediante `tool.snap_candidate`; Android sigue el
  dedo de forma coalescida y dibuja el marcador sin acumular previews. Bevel y Bridge
  Edge Loops también publican sus controles de snap en `edit_toolbar`.
- Ajustes globales de Edit (`edit.settings`/`edit.settings_set`, feature
  `edit_settings`): edición proporcional real para MOVE/ROTATE/SCALE con radio y perfil
  de caída, preview reversible y exclusión de vértices ocultos; Auto Merge suelda al
  confirmar MOVE según el umbral configurado. Ambos usan `ToolSettings` de Blender y
  persisten entre transformaciones.
- Cámara independiente, vistas estándar, Persp/Ortho y encuadre. `camera.roll` (giro de
  rueda sobre el eje de visión) y `view.roll`/gesto `roll`, con la escena acompañando al
  dedo (`view.roll_delta` invierte el ángulo de rueda a rotación de cámara).
- `view.shading` (WIREFRAME/SOLID/TOGGLE; el wireframe activa xray y el pick cicla hacia
  detrás), `view.local` (aísla la selección ocultando el resto, el `/` de Blender) y
  `selection.more`/`selection.less` (crecer/decrecer adyacencias en Edit). `selection.box`
  y `selection.circle` operan en ambos modos: centros proyectados (object) o elementos
  del submodo (edit). El estado viaja como `shading` (top-level) y las capabilities
  anuncian `view.shading`, `view.local_view`, `selection.grow` y `selection.shapes`.
- Streaming H.264 preferido y MJPEG fallback desde una única captura GPUOffScreen.
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
- `commands/modifiers.py`: pila no destructiva SUBSURF, ARRAY, BEVEL, SOLIDIFY,
  BOOLEAN y MIRROR sobre datablock API (`add/remove/move/set/toggle/apply`), con
  `modifier.add_options` describiendo cada parámetro por tipo/rango/enum/filtro.
  Mirror expone ejes, bisect/flip por eje, clipping, merge/umbral y objeto espejo
  opcional; los `modifier.set` parciales conservan los parámetros no enviados.
- `object.hide` / `object.reveal` (H / Alt+H de objetos vía `hide_set/hide_get`,
  distintos de `selection.hide/reveal` en Edit) y `transform.apply` (hornea T/R/S sin
  confundirse con `transform.reset`, con `shared_data` para mallas Alt+D).
- `object.shade` alterna o fija `FLAT`/`SMOOTH` sobre las caras de objetos MESH, con
  capability `object_shading`, targets explícitos y un único paso de undo.
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
- Navegación: un dedo según herramienta; dos dedos pan+zoom y **roll** (giro de rueda
  sobre el eje de visión local, `Gesture.ROLL` + `camera.roll`/`view.roll`); tap, doble
  tap y long-click. El ángulo de la rueda se envía en radianes y la escena acompaña al
  dedo (rueda horaria -> escena horaria).
- Feedback táctil local de tap (círculo + haptic) en `InputSurface` mientras se espera
  la respuesta remota del picking.
- Transformación modal con restricciones, orientación (desplegable de tipos de snap
  válidos por modo), unidades y confirm/cancel.
- En Edit Mode, `Prop` y `Merge` viven junto a Wireframe. La bandeja de transformación
  los representa mediante iconos de influencia y unión. La bandeja de transformación
  expone radio editable (incluidas unidades), ajustes −/+ y perfil cuando la edición proporcional está activa; el estado procede
  del servidor y se conserva globalmente entre movimientos.
- Bandeja paramétrica para Extrude/Bevel/Inset/Subdivide/Loop Cut (`EditToolTray`), en
  una franja horizontal desplazable (no apilada en vertical): rótulo a la izquierda,
  parámetros en fila y descartar/confirmar fijos a la derecha.
- Las familias del rail con más de una variante habilitada muestran un chevrón en la
  esquina para anunciar su menú de pulsación larga; las herramientas simples no.
- Loop Cut táctil: sin arista elegida, el rail arma `loopCutAwaitingTap` y el PRÓXIMO
  toque en la malla coloca el corte (`mesh.loop_probe` → `tool.begin` con `edge`+`factor`),
  y con sesión abierta el toque re-ubica (`tool.loop_pick`). La bandeja ofrece un
  stepper numérico "Posición" 0-100% (↔ `factor`, con `−`/`+` y valor editable; el
  arrastre fino sigue siendo deslizar el lápiz por el viewport, que alimenta
  `tool.nudge`), steppers de cortes/suavidad, botón ciclado de perfil (`LoopFalloff`) y
  toggles Uniforme/Invertir/Fijar (`ToolSession.parameters` pasó a `Map<String, Any?>`
  para conservar bools y string). Con `loopCutPick` no anunciado se conserva el flujo
  legacy (seleccionar arista y esperar el snapshot).
- Con una sesión Loop Cut activa, Mayús (modificador ADD) + toque acumula otro loop.
  La bandeja muestra el número de loops y ofrece “Deshacer último”; el toque normal
  conserva su función de recolocar el corte activo.
- Menú Edit contextual gobernado por el catálogo (`EditCatalog` en `StateParser`): el
  long-click en Edit abre Vértice, Arista o Cara según `selectionMode`, con las acciones
  anunciadas, sus variantes (Extrude) y su ejecución (DISCRETE → `editCatalogCommand`;
  SESSION → `tool.begin`). Bridge Edge Loops se reconcilia como sesión (`EditTool.
  BRIDGE_EDGE_LOOPS`, bandeja con desfase/fusión/toggle "Fusionar") y KNIFE/DISSOLVE
  quedan ocultos por el catálogo. El rail histórico de herramientas solo aparece si el
  servidor no anuncia el catálogo.
- Página "Atajos" de `ViewFooter` (solo Edit): F, P, Y y Normales (Exterior/Interior/
  Voltear), además de la página de Vistas existente. Las páginas se alternan con
  iconos de Vista y Herramientas, no con las letras V/E que se confundían con teclas.
- Círculo de navegación derecho (`NavigationOrbitLayout`): visible solo con sesión activa;
  un `DOWN` dentro captura ORBIT sin alimentar la tool, y fuera conserva el nudge.
- Knife táctil: sesión `tool.knife_drag/pop/close` por segmentos de arrastre, overlay de la
  polilínea reproyectado desde anclas 3D por `tool.status` y bandeja `KnifeTray`
  (contador, Deshacer punto, Cerrar, Snap, Descartar/Confirmar). `tool.knife_point`
  permanece en backend solo para clientes antiguos; `ToolSession` expone `points`,
  `projectedPoints`, candidato y `closed`. Los UPDATE se coalescen latest-wins.
- `ui/ModifierPanel.kt`: inspector schema-driven desde `modifier.add_options` (add,
  parámetros tipados, viewport/render, reorder, apply, remove; Boolean con picker de
  objeto MESH y Mirror con objeto de cualquier tipo, ambos excluyendo el activo). La lista de objetos para el operando viene de
  `scene.list_objects`, que `openModifiers()` pide al abrir el inspector: el snapshot
  de 10 Hz no la lleva para no engordarlo.
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
  En `onStop` se detienen transporte y codec conservando el endpoint; `onResume` y
  `surfaceChanged` crean una sesión limpia que espera un keyframe. Los callbacks de
  destrucción identifican su Surface y una generación impide que el transporte viejo
  entregue access units a la nueva.
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
- Barra de modo (`TOP_MODE`, junto a las tools del top): Object/Edit en un panel propio.
  Salieron del rail, que queda dedicado a herramientas y utilidades. `SurfaceCatalogTest`
  fija que `MODE_OBJECT`/`MODE_EDIT` viven una sola vez y solo en `TOP_MODE`.
- Barra superior de tools (`ui/TopToolbar.kt`) junto al ojo: wireframe (`view.shading`
  TOGGLE, pintado desde `state.blender.view.shading`), modificadores Mayús/Ctrl/Alt (fijan
  `selection.pick`/box/circle a TOGGLE/ADD/REMOVE) y undo/redo, movidos desde el rail. En
  Edit Mode, a la derecha de la misma barra, los submodos vértice/arista/cara para cambiar de
  selección sin abrir el rail. Cada botón se oculta si el backend no anuncia su
  capability (`view.shading`).
- `TransformBar` horizontal: la bandeja de Mover/Rotar/Escalar adopta la composición de
  `EditToolTray` — rótulo del modo a la izquierda, propiedades (valores, restricción,
  orientación, snap, paso, valor exacto, candidato) en una fila desplazable y
  Descartar/Confirmar fijos a la derecha. La herramienta la elige el rail; la bandeja
  solo lleva su sesión.
- Selección por caja B y círculo C en el long-click (`RADIAL`): arman el arrastre por
  forma (`ShapeTool` + overlay en `InputSurface`) y envían `selection.box`/`circle`.
  Salieron de la barra superior por decisión del usuario. En el anillo Edit sustituyen a
  `SELECT_INVERT` para no pasarse del tope de 8.
- Borrar y Disolver son intenciones distintas en el menú Edit contextual; Disolver usa
  `mesh.dissolve` para Vértice/Arista/Cara y nunca emula la operación con `ONLY_FACES`.
- Toast de error auto-descarta a los ~5 s: `client.clearError()` + `LaunchedEffect`
  sobre `state.error`.
- Teclado de vistas (`ViewFooter.kt`): 9 gira 180° (ya no duplica al 7), 5 enseña el
  estado real de la proyección (resaltado solo en ORTHO), `/` aísla la selección
  (`view.local`) y `+`/`−` crecen/decrecen la selección (`selection.more`/`less`,
  activos solo en Edit). El encuadre salió del teclado (queda como doble toque). Se
  eleva (`Metrics.TrayInset`, con transición) cuando una bandeja horizontal inferior
  ocupa su zona; la señal es la función pura `bottomTrayVisible`.
- `SelectionOp`/`ShapeTool` en `AppUiState`; el parser lee `shading` (top-level) y las
  capabilities `view.shading`/`local_view`/`selection.grow`/`shapes`. `updateState`
  conserva vista/shading en los snapshots sin vista (pick/box/circle/more/less),
  que no traen ni `view` ni `shading`.

## Propiedad única de acciones

Cada acción ejecutable vive en una sola superficie visible:

- Top: archivo, estructura global, objeto (sin Add), modifiers y objetos ocultos.
- Barra de modo (`TOP_MODE`, junto al ojo): Object/Edit, en su propio panel.
- Barra superior de tools (`TOP_TOOLS`, junto al ojo): wireframe, Mayús/Ctrl/Alt, undo/redo
  y, en Edit, el submodo de selección.
- Rail: herramienta activa y utilidades (duplicar, diagnóstico); el modo ya no está aquí.
- Footer/bandeja: parámetros de la herramienta activa.
- Footer de vistas (`FOOTER_VIEWS`): navegación, proyección y crecer/decrecer.
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
- Aislar selección (`VIEW_LOCAL`): solo en el long-click de Object Mode, como
  `/ Aislar selección`, junto a Ocultar objeto y en sustitución de Seleccionar todo /
  Deseleccionar. Crecer/decrecer (`SELECT_MORE`/`SELECT_LESS`) permanece en el footer
  de vistas (`FOOTER_VIEWS`). `VIEW_FRAME_SELECTED` salió del catálogo: el encuadre de
  selección es el gesto de doble toque.
- Plano/Suave (`SHADE_OBJECT`): solo en el long-click sobre un objeto seleccionado de
  Object Mode y únicamente cuando el servidor anuncia `object_shading`.

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

Puede editar exclusivamente `blender-backend/**` (y el archivo numerado
`*_PLAN_BACKEND_*.md` del ciclo abierto). Posee protocolo, fixtures, implementación Python, CLI y tests backend.
No edita `android-client/**`.

### Agente frontend

Puede editar exclusivamente `android-client/**` (y el archivo numerado
`*_PLAN_FRONTEND_*.md` del ciclo abierto). Trabaja contra fixtures congelados. No edita backend, protocolo ni
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
vistas equivocadas; re-medido con el vector FORWARD y corregido pasando el yaw al eje
vertical local de la cámara. Ver Trampas.

Lección de método: los tres se diagnosticaron **midiendo contra el servidor vivo** con
`tools/wsclient.py` y consumiendo `/stream.h264` y `/stats.json`, sin tocar la instalación
del usuario. Es mucho más rápido que leer código, y evita atribuir un síntoma al último
cambio que se tocó, que fue el error inicial de esta sesión.

## Trampas conocidas

- El objeto activo puede no estar seleccionado.
- En Kotlin las propiedades se inicializan en orden textual. No lanzar desde `init` un
  `collect` de `StateFlow` que use una propiedad declarada más abajo: con
  `Dispatchers.Main.immediate`, el flow puede emitir durante el constructor y acceder
  al campo antes de inicializarlo, cerrando la app incluso sin Wi-Fi. Ocurrió con
  `_knifeScreenPoints`; todo estado usado por `init` debe declararse antes del bloque.
- Un `assembleDebug` y los tests JVM no detectan necesariamente un crash de construcción
  de `MainViewModel` si ninguna prueba instancia el ViewModel Android real. Ante cierre
  inmediato, probar primero sin Wi-Fi: si también falla, auditar inicialización y
  composición local antes de culpar al handshake o al backend.
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
  `bpy.context.evaluated_depsgraph_get()`; no quitar esa llamada.
  OJO con atribuirle a esto el retardo de 4 s: se le atribuyó el 2026-08-25 y era falso.
  Medido después, la captura cuesta 6-37 ms con o sin la llamada, y el retardo real venía
  de la pantalla apagada (entrada anterior). La sincronización sigue siendo correcta y se
  queda —evita depender de que el PC redibuje—, pero no es la explicación de ese síntoma.
  Ojo al escribir tests para esto: el bloque `[10]` de `run_gui_tests.py` se ejecutó con
  la llamada desactivada y siguió en verde, porque con la ventana de Blender visible es
  Blender quien evalúa por su cuenta y enmascara el fallo. No hay prueba automática que
  lo distinga; solo se reproduce en el escenario real, con el PC sin redibujar.
- El sentido de giro de `camera.orbit` NO se puede medir sobre un punto proyectado
  desde una vista de eje: depende de la vista y ya causó inversiones erróneas. Se mide
  con el vector FORWARD de la cámara o la rotación RELATIVA. El yaw es sobre el eje
  vertical LOCAL (`rotation @ (0,1,0)`, el "arriba" de pantalla), con signo `-dx`
  (dedo a la derecha => escena a la derecha, consistente en DEFAULT/FRONT/BACK/RIGHT/
  LEFT/TOP/BOTTOM); el pitch sigue sobre el eje derecho local con `-dy`. Antes era
  yaw sobre el Z GLOBAL, que se invertía al mirar desde abajo o desde atrás (y no
  movía nada en la cenital). Hay tests de regresión en `run_gui_tests.py`
  (`[13] Signo del giro de cámara` y `[14] Giro horizontal consistente desde BACK y
  BOTTOM`). Android manda `dx>0` a la derecha y `dy>0` hacia abajo, sin invertir nada
  (`InputSurface.handleSingle`); el signo se decide entero en el backend. El `+dx`
  inicial conservaba la orientación al invertir la cámara, pero las pruebas en tablet
  real demostraron que el sentido era siempre el contrario; por eso se corrigió a
  `-dx` sin cambiar el eje local.
- El snap del Knife no puede desempatarse solo por distancia: cuando el toque entra
  perpendicular a una arista, su punto más cercano **es** el centro y las dos distancias
  solo se separan por ruido de coma flotante, así que `EDGE` ganaba siempre y
  `EDGE_CENTER` no se anunciaba nunca. En `_knife_candidate` el empate práctico
  (<= 1e-3 en pantalla) lo gana el snap más específico: vértice, centro, arista.
- `file.recent` sigue en backend, protocolo y tests, pero Android ya no lo consume: al
  retirar "Abrir reciente" del menú Archivo se eliminó todo su lado cliente
  (`RecentFile`, `AppUiState.recentFiles`, `requestRecentFiles`, `updateRecentFiles`).
  No volver a añadir ese estado sin una superficie que lo pinte.
- `Modifiers.kt` Android contiene `clickableNoRipple`; no tiene relación con modifiers
  Blender y está ampliamente usado.
- El add-on es 0.1.0 en manifest/fuente. La app Android es 0.1.2.

## Objetivos activos

No hay una serie activa. El próximo trabajo de refinado y escalado debe abrir planes
propietarios nuevos desde `000`.

`005` (backend): el motor del Knife ya no trianguliza. Un punto puesto dentro de una cara
la borraba y la sustituía por un abanico de triángulos hacia todas sus esquinas
(`_poke`), que es de donde salían las diagonales que el usuario nunca dibujó. Ahora los
puntos interiores se acumulan hasta que el trazo vuelve al contorno y la cara se parte en
**dos n-gons** siguiendo la cadena. Solo aplica cuando entrada y salida caen en la misma
cara; encadenar interiores de caras distintas sigue usando `_poke`.

**Aviso de método:** el contrato se mide contra el add-on instalado, no contra el repo.
Construir y reinstalar el ZIP antes de fiarse de un contrato en verde. Sus fixtures
deben contener campos normativos; estado dinámico como el puerto o si el stream pudo
arrancar se prueba por separado.

## Entrega obligatoria de cambios

Por instrucción permanente del usuario desde el 2026-08-30, todo cambio funcional debe
terminar con: APK actualizado enviado por Telegram, ZIP del add-on reconstruido,
reinstalación limpia del add-on y reinicio de Blender, aunque el cambio sea solo Android.
Antes de entregar, comprobar proceso, puertos `8765`/`8766` y que la copia instalada
contiene el código nuevo.

La única incidencia no resuelta de la serie cerrada es el segfault OFFSCREEN observado
el 2026-08-28 durante una prueba táctil de Knife. La traza fue `_pump` →
`capture.tick` → `_grab_offscreen`/`draw_view3d`, con `libtbb` durante evaluación
paralela. Blender informó `bpy.ops.object.editmode_toggle()`, operación que no usa el
backend (`mode_set`), por lo que el cambio de modo vino de la ventana del usuario. No
reprodujeron ni doce rondas de cambio de modo desde tablet con Knife y stream activos,
ni un Tab externo desde timer seguido de arrastres: las sesiones inválidas respondieron
con error limpio y no tocaron un BMesh muerto. Si reaparece, conservar el crash dump y
diagnosticar sobre GPUOffScreen sin sustituir la fuente de captura por el viewport del
PC.

El ciclo backend de la órbita invertida cerró: `camera.orbit` ahora hace el yaw sobre el
eje vertical LOCAL de la cámara (no el Z global), de modo que el arrastre horizontal
acompaña al dedo también desde debajo o desde atrás; ver las trampas conocidas.

El menú Edit ya es un menú contextual alimentado por el catálogo backend (`edit.catalog`,
feature `edit_catalog`) y gobernado por el selector superior: abre Vértice, Arista o Cara
según el submodo activo, nunca las tres categorías a la vez. Entregado en este ciclo:
Bridge Edge Loops (sesión paramétrica), F (crear arista/cara o rellenar), P (separar a
objeto), Y (split), recalcular/voltear normales y variantes de Extrude (Región / a lo
largo de normales / Individual). En el footer de vistas, la página "Atajos" (solo Edit)
ofrece F, P, Y y Normales. El círculo de navegación derecho aparece durante una sesión
activa para orbitar sin alimentar la tool. El núcleo de KNIFE está entregado como sesión
táctil de polilínea (puntos por toque, overlay, bandeja con deshacer/cerrar/snap).
Disolver está habilitado para Vértice/Arista/Cara y separado de Delete. Bisect también
está implementado; hover anticipado y eraser no forman parte de la versión cerrada. El
bloqueo X/Y/Z de Extrude sí está implementado.

Los resultados de pruebas de cierre se registran en el commit de la versión, no como
conteos congelados en esta guía. El smoke y cualquier incidencia observada en tablet
real serán la entrada del siguiente ciclo.
