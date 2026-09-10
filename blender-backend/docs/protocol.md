# Protocolo Blender Tablet Remote — v2.0 (implementación del backend)

Este documento describe **lo que el backend implementa hoy**, no lo que nos gustaría.
Si algo aquí no coincide con el servidor, el bug está en el documento.

Transporte: **WebSocket**, marcos de **texto** con **JSON** UTF-8.
Endpoint: `ws://<host>:8765/`

La respuesta de `server.capabilities` incluye `features` estructuradas, todos los `enums` canónicos
y `units`. Distancias son Blender Units acompañadas de `scale_length`/`unit_system`,
giros son grados y escalas factores. `RELATIVE` expresa un delta desde el snapshot de
inicio; `ABSOLUTE` expresa el valor objetivo en la referencia indicada.

---

## 1. Ciclo de vida de la conexión

1. El cliente abre el WebSocket. Puede incluir el token en la query:
   `ws://10.0.0.8:8765/?token=SECRETO`
2. El servidor responde inmediatamente con `hello`:

```json
{
  "type": "hello",
  "server": "Blender Tablet Remote",
  "blender": "5.2.0 LTS",
  "auth_required": true,
  "authenticated": false,
  "stream": {
    "running": true,
    "port": 8766,
    "path": "/stream.h264",
    "format": "h264",
    "framing": "btr-h264-v1",
    "codec": "avc1.42C01F",
    "alternatives": [{"format": "mjpeg", "path": "/stream.mjpg"}],
    "resolution": [1280, 754]
  }
}
```

El bloque `stream` dice dónde está el vídeo del viewport (§10): el cliente lo saca de
aquí en vez de preguntárselo al usuario. Si `running` es `false` no hay vídeo y la UI
debe seguir siendo utilizable sin él.

`format` y `path` son la ruta preferida. Si no puede decodificarla, el cliente recorre
`alternatives` en orden. `/stream.mjpg` se conserva para clientes v2 antiguos.

3. Si `auth_required` es `true` y `authenticated` es `false`, el cliente debe autenticarse
   antes de nada (ver §2).
4. Al autenticarse, el servidor envía un evento `scene.changed` con el estado completo,
   así la tablet puede pintar la UI sin pedir nada.

El servidor manda un **ping WebSocket cada 20 s**. La librería cliente de Android debe
responder pong (OkHttp lo hace solo). Si el socket muere, reconectar y volver a §1.

---

## 2. Autenticación

Tres formas equivalentes, elige una:

| Forma | Cuándo usarla |
|---|---|
| Query del handshake `?token=...` | La más simple para la app Android |
| Mensaje `auth` | Si la librería no permite query params |
| Campo `token` en cada mensaje | Clientes sin estado (curl, scripts) |

```json
{"type": "auth", "id": "1", "token": "SECRETO"}
```

Respuesta correcta:

```json
{"type": "response", "id": "1", "ok": true, "result": {"authenticated": true}}
```

Token incorrecto: se responde con error `auth_failed` **y a continuación se cierra la
conexión** (código WebSocket 1008). Un comando enviado sin autenticar responde
`auth_required` sin cerrar.

Si el servidor no tiene token configurado, `auth_required` es `false` y todo se acepta.

---

## 3. Comandos

Petición:

```json
{
  "type": "command",
  "id": "12345",
  "command": "transform.move",
  "payload": {"x": 1.0, "y": 0.0, "z": 0.0}
}
```

- `id` — opcional pero **muy recomendable**: es lo que empareja respuesta con petición.
  Recomendado UUID. Se devuelve tal cual.
- `payload` — opcional, objeto. Si falta se asume `{}`.

Respuesta correcta:

```json
{"type": "response", "id": "12345", "ok": true, "result": { ... }}
```

Respuesta con error:

```json
{"type": "response", "id": "12345", "ok": false, "error": "No active object", "code": "command_failed"}
```

`result` puede no estar si el comando no devuelve nada. **Nunca** asumas que `result`
existe sin comprobarlo.

### Códigos de error

| `code` | Significado |
|---|---|
| `unknown_command` | El comando no existe en este servidor |
| `bad_payload` | Falta un campo o tiene el tipo equivocado |
| `not_found` | Objeto o índice inexistente |
| `wrong_mode` | El comando necesita otro modo (p. ej. `mesh.*` fuera de Edit) |
| `empty_selection` | No hay nada seleccionado sobre lo que operar |
| `wrong_selection` | El elemento tocado no pertenece al submodo de selección activo |
| `no_selection_path` | No existe un camino topológico conectado hasta el elemento tocado |
| `no_viewport` | No hay ningún VIEW_3D disponible |
| `no_undo_stack` | Blender en background: no hay pila de undo |
| `auth_required` / `auth_failed` | Ver §2 |
| `command_failed` | Error controlado genérico |
| `shared_data` | La malla tiene varios usuarios (Alt+D); aplicar deformaría al gemelo |
| `internal_error` | Excepción no prevista (hay traza en la consola de Blender) |
| `unsupported_type` | El tipo de objeto/datablock no admite la operación |

---

## 4. Convenios de unidades y ejes

- Ejes: los de Blender. **Z es arriba**, unidades de Blender (metros por defecto).
- `transform.move` / `transform.rotate` son **deltas** salvo que pases `"absolute": true`.
- `transform.scale` es un **factor multiplicativo** salvo `"absolute": true`.
- Rotaciones en **grados**. Pasa `"radians": true` si prefieres radianes.
- `space`: `"GLOBAL"` (por defecto) o `"LOCAL"`.
- `pivot`: `"INDIVIDUAL"` (cada objeto sobre su propio origen, por defecto), `"MEDIAN"`,
  `"CURSOR"`, `"WORLD"`.
- Coordenadas de pantalla (`selection.pick`): `u`, `v` normalizados 0..1 con **origen
  arriba-izquierda**, la convención de Android. El backend hace la conversión al eje Y
  invertido de Blender.
- Deltas de gesto (`dx`, `dy`): **fracción de la pantalla**, no píxeles. Arrastrar el
  ancho completo = `dx: 1.0`. Así la tablet no necesita saber la resolución remota.

### A qué objetos afecta un comando

Los comandos de transformación y de objeto siguen esta regla, en orden:

1. Si el payload trae `"objects": ["Cube", "Sphere"]`, a esos.
2. Si no, a **todos los objetos seleccionados**.
3. Si no hay selección, al objeto activo.
4. Si no hay activo → error `command_failed: No active object`.

**En Edit Mode**, `transform.*` opera sobre los **vértices seleccionados** de la malla en
edición, no sobre el objeto.

---

## 5. Catálogo de comandos

### Estado

| Comando | Payload | Devuelve |
|---|---|---|
| `scene.get_state` | `include_view` (bool, def. true), `include_objects` (bool) | estado completo |
| `scene.get_context` | — | contexto canónico, conteos y opciones válidas |
| `scene.list_objects` | — | `{objects: [{name, type, selected}]}` |
| `scene.get_object` | `name` | info del objeto |
| `scene.scale` | — | `{scale, presets[]}` — escala de trabajo activa y catálogo |
| `scene.scale_set` | `preset`: `SMALL`\|`MEDIUM`\|`LARGE`, y/o `length_unit`: `MILLIMETERS`\|`CENTIMETERS`\|`METERS` | la escala resultante |
| `server.ping` | `echo` | `{pong: true, echo}` |
| `server.capabilities` | — | versiones, lista de comandos y gestos |

#### Escala de trabajo (`scene_scale`)

Un preset **no reescala geometría**: un cubo de 2 unidades sigue midiendo 2 unidades en
los tres. Lo que cambia es cómo se mide, hasta dónde se ve y con qué paso se trabaja.

| Preset | `length_unit` | `clip_start` | `clip_end` | `snap_step` | `primitive_size` | radio proporcional / paso |
|---|---|---|---|---|---|---|
| `SMALL` | `MILLIMETERS` | 0.0005 | 5 | 0.001 | 0.01 | 0.01 / 0.001 |
| `MEDIUM` | `CENTIMETERS` | 0.01 | 100 | 0.01 | 0.5 | 0.5 / 0.05 |
| `LARGE` | `METERS` | 0.1 | 1000 | 0.1 | 2.0 | 5.0 / 0.5 |

El clipping es la razón de que esto exista. La proyección del vídeo hereda el **FOV** de
la ventana del PC pero **no su rango de profundidad**: con el clip por defecto de Blender
(0,01 m a 1000 m) el z-buffer se reparte sobre un rango 100.000 veces mayor que la pieza,
las caras próximas compiten por el mismo valor y la malla se ve rota aunque la geometría
sea correcta. Cada preset mantiene `clip_end / clip_start` en torno a 10.000, que es lo
que un z-buffer de 24 bits sostiene sin artefactos. Solo se reescribe la fila de
profundidad de la matriz heredada, así que el rayo del toque sigue coincidiendo con lo
que se ve y la ventana del PC no se toca.

Los valores de clipping del catálogo son metros y se convierten mediante
`scale_length` al aplicarlos a la cámara. El rango efectivo sigue la distancia:
`far=max(distance*4,min(clip_end,distance*100))` y
`near=max(min(clip_start,distance*.01),far/10000)`. Un preset no impone una distancia
mínima que aleje una pieza pequeña; el zoom admite distancias submilimétricas.
En ortográfica el rango de profundidad se centra en el pivote y conserva el volumen
encuadrado: el zoom cambia la ampliación sin cortar la cara delantera al acercarse.
`view.frame_selected` y `view.frame_all` ajustan los límites de los
objetos al 85 % de la vista con su orientación y proyección, sin modificar la del PC.
Si la ventana del PC está en ortográfica, se recupera su FOV equivalente antes de
construir la proyección remota para evitar aplicar dos veces su zoom.
Android ofrece «Encuadrar objeto» en el panel de vistas. En Edit y CAD los toques
consecutivos de selección son independientes: no encuadran por doble toque.
Sin selección, encuadrar toma el objeto activo o la geometría visible, sin incluir
cámaras, luces ni empties ajenos. La apertura conserva la proyección inicial del PC.

`scale_length` de la escena **no** se modifica: multiplica el tamaño del mundo y
cambiaría el significado de la geometría existente. `length_unit` sí, porque solo decide
cómo se escribe la medida. El preset viaja en `scene.get_state` como `scene_scale`. Al
abrir un `.blend`, el preset inicial se deduce de su unidad real: milímetros selecciona
`SMALL`, centímetros `MEDIUM` y metros `LARGE`. Una elección posterior del usuario se
conserva durante esa sesión. `scene_scale.scale_length` contiene siempre el valor real
del archivo para que el cliente actualice sus conversiones al cargar otra escena.

En `tool.begin`, `parameters.auto_size:true` inicializa EXTRUDE/BEVEL/INSET según
la selección efectiva (o el objeto si no define una extensión). El paso es el 1 %
de su menor dimensión útil, redondeado hacia abajo a 1/2/5 por década y limitado
por el paso del preset. Incluye escala del objeto y `scale_length`. Bisel e Inset
comienzan en dos pasos; Extruir conserva su distancia inicial. Por ejemplo, una
pieza de 1 mm empieza con paso 0,01 mm y Bisel 0,02 mm. Android solicita esta
inicialización al abrir esas herramientas; editar sus valores durante la sesión
sigue siendo exacto. Los controles de Mover/Escalar conservan su política propia.
Bisel mide el ancho en mundo incluso con escala de objeto sin aplicar, sin aplicar
esa escala al objeto. Los botones del campo Paso avanzan según el orden de magnitud
del paso actual y muestran suficientes decimales para no convertirlo visualmente en cero.
En esas tres herramientas, Paso se muestra también sin snap y su selector de unidad
gobierna todos los campos de distancia. Sus botones suman/restan ese paso. El arrastre
libre usa la misma escala de recorrido (un paso por 4 % de altura) conservando fracciones;
Incremento/Rejilla redondean en el backend.

El rail Edit contiene Extruir, Bisel, Inset, Corte de loop y Cortar. Bridge permanece
en el catálogo Malla. El radial separa Selección y Malla y conserva Duplicar y Borrar
como acciones directas; las herramientas anunciadas en el rail se excluyen del
catálogo mostrado por Android a partir de sus IDs de familia/variante.

En Mover, `NONE` conserva un arrastre continuo ligado a la vista. `INCREMENT` convierte
el recorrido en saltos táctiles deliberados: una pantalla completa recorre 40 pasos,
de modo que un incremento de 1 mm tenga una zona perceptible antes del siguiente salto.

`object.add` usa `primitive_size` para que las primitivas nazcan a la escala elegida.
Ese tamaño está en metros físicos y se convierte a unidades Blender dividiéndolo
por el `scale_length` vigente. El cubo de Pequeña mide 10 mm, el de Mediana 50 cm y
el de Grande 2 m, independientemente de la escala interna del archivo.
Cada operador de Blender nombra su tamaño distinto (`size`, `radius`, los dos radios del
toro), así que se consulta el RNA; un tamaño explícito en el payload siempre gana.

`scene.get_state` devuelve:

```json
{
  "mode": "OBJECT",
  "active_object": "Cube",
  "selected_objects": ["Cube"],
  "selection_mode": "VERTEX",
  "scene": "Scene",
  "frame": 1,
  "active": {
    "name": "Cube", "type": "MESH",
    "location": [0,0,0], "rotation_euler": [0,0,0], "scale": [1,1,1],
    "dimensions": [2,2,2], "visible": true,
    "mesh": {"vertices": 8, "edges": 12, "polygons": 6, "shade_smooth": false}
  },
  "view": {"location": [0,0,0], "rotation": [w,x,y,z], "distance": 10.0, "perspective": "PERSP"}
}
```

`mesh.shade_smooth` mira solo el primer polígono, porque este snapshot se pide a 10 Hz y
censar la malla entera en cada uno saldría caro. Existe para que el cliente pueda rotular
su interruptor de sombreado con la acción que ejecutará; en una malla con sombreado mixto
es el estado de referencia, no una garantía sobre todas las caras. Quien necesite el
valor exacto que use `object.shade`, que sí lo calcula sobre todos los polígonos.

### Objetos

| Comando | Payload |
|---|---|
| `object.select` | `names[]` o `name`, `mode`: `SET`\|`ADD`\|`REMOVE`\|`TOGGLE`, `active` (bool) |
| `object.select_all` | `value` (bool) |
| `object.set_active` | `name` |
| `object.delete` | `objects[]` (opcional) |
| `object.duplicate` | `objects[]`, `linked` (bool) |
| `object.add` | `primitive`: `CUBE`\|`SPHERE`\|`CYLINDER`\|`CONE`\|`PLANE`\|`TORUS`\|`MONKEY`, `x/y/z` |
| `object.rename` | `name`, `new_name` |
| `object.hide` | `objects[]` (opcional), `unselected` (bool, Shift+H) |
| `object.reveal` | `objects[]` (opcional), `select` (bool, def. true) |
| `object.shade` | `objects[]` (opcional), `mode`: `TOGGLE`\|`FLAT`\|`SMOOTH` |

`object.hide` / `object.reveal` son la H / Alt+H de **objetos** (`obj.hide_set`). No
confundir con `selection.hide` / `selection.reveal`, que ocultan geometría en Edit.
`visible` en el estado es `not obj.hide_get()`, no el monitor del outliner.

En Edit Mode, duplicar geometría no usa `object.duplicate`: `mesh.duplicate` copia
únicamente la selección efectiva del submodo actual (vértices, aristas o caras) y deja
seleccionada la copia, equivalente a `Shift+D` antes de moverla.

### Modos

`mode.object`, `mode.edit`, `mode.toggle`, `mode.set` (`mode`: `OBJECT`, `EDIT`, `CAD`, `SCULPT` o `MATERIAL`).

### Selección

| Comando | Payload |
|---|---|
| `selection.vertex` / `.edge` / `.face` | — |
| `selection.set_mode` | `selection_mode`: `VERTEX`\|`EDGE`\|`FACE` |
| `selection.all` | `value` (bool) — en Edit Mode |
| `selection.info` | — devuelve índices seleccionados |
| `selection.elements` | `verts[]`, `edges[]`, `faces[]`, `mode` |
| `selection.pick` | `u`, `v` (0..1), `threshold`, `mode`: `SET`\|`ADD`\|`REMOVE`\|`TOGGLE` |
| `selection.tweak` | `phase`: `BEGIN`\|`UPDATE`\|`END`\|`CANCEL`; BEGIN lleva `u`,`v`, `motion`, `snap_type`, `snap_step`, `clamp`; UPDATE lleva `dx`,`dy` y `u`,`v` |
| `selection.shortest_path` | `u`, `v` (0..1), `threshold`, `extend` (bool, por defecto false) — solo Edit |
| `selection.box` | `u0`, `v0`, `u1`, `v1`, `mode` |
| `selection.circle` | `u`, `v`, `radius`, `mode` |
| `selection.more` / `selection.less` | — en Edit Mode |
| `selection.loop` / `.ring` | `edge` (opcional en Edge), `mode`; en Face usa cara activa y dirección del último toque |
| `selection.linked` | — en Edit Mode; siembra con la selección |

`mesh.delete` elimina topología. `mesh.dissolve` conserva la superficie vecina y
acepta `what: VERTS|EDGES|FACES`; son acciones distintas.

`selection.pick` es **el comando del tap**: lanza un rayo desde la cámara del viewport.
En Object Mode selecciona el objeto tocado; en Edit Mode, con oclusión real (SOLID),
solo considera elementos de la cara visible impactada y exige que vértices/aristas
estén dentro del umbral táctil normalizado (`threshold`, 0.035 por defecto). Devuelve
`{"hit": false}` si el rayo no da con nada (y deselecciona si `mode` es `SET`).

`selection.tweak` está disponible en Edit y submodos VERTEX/EDGE/FACE. BEGIN selecciona
el elemento bajo el punto inicial (conserva el grupo si ya estaba seleccionado) y
abre una transformación MOVE reversible; UPDATE
acumula deltas normalizados en el plano de la vista; END confirma un único undo y
CANCEL restaura las coordenadas originales. Un BEGIN sin impacto no abre sesión MOVE:
los UPDATE siguientes orbitan la cámara (`miss_behavior: ORBIT`) hasta END/CANCEL. Un
toque sin desplazamiento conserva la selección pero no crea un undo de movimiento.
Android distingue toque de arrastre mediante el umbral del dedo/stylus y confirma
la última muestra estable, ignorando el salto de posición de ACTION_UP. Pulsar otra
herramienta o repetir el botón Tweak permite salir; cancelar un gesto ya cerrado no
cancela la nueva transformación. La respuesta terminal incluye `active: false` y
`tweak_finished` con el ID de la sesión MOVE que acaba de cerrar; Android solo borra
su copia si coincide ese ID, sin invalidar una transformación posterior. En FACE el
movimiento siempre es FREE.

El BEGIN configura el gesto entero y esos ajustes se conservan hasta END/CANCEL:

- `motion`: `FREE` (por defecto) mueve libre en el plano de la vista; `SLIDE` restringe
  cada vértice a una de sus aristas, como el `GG` de Blender.
- `snap_type`: `NONE` (por defecto), `INCREMENT` o un destino geométrico
  (`VERTEX`, `EDGE`, `EDGE_CENTER`, `FACE`, `FACE_CENTER`).
- `snap_step`: tamaño del incremento. Con `motion: FREE` son unidades de escena; con
  `SLIDE` es la fracción del riel (`0.1` = un décimo de arista).
- `clamp` (solo `SLIDE`, por defecto `true`): impide que el vértice se salga del
  segmento; con `false` el riel extrapola más allá de sus dos extremos.

Con `motion: SLIDE`, el riel de cada vértice se elige **una sola vez**, en el primer
UPDATE que supera el umbral de arrastre: de sus aristas incidentes gana la que mejor se
alinea con la dirección del dedo **proyectada en pantalla**, no en el espacio del mundo
(si no, una arista casi paralela al eje de visión ganaría siempre por su longitud
aparente). Fijarlo así evita que el riel salte de arista a mitad de gesto. Se prefieren
las aristas cuyo otro extremo no está seleccionado; si un vértice no tiene ninguna, se
consideran todas. El factor de deslizamiento sale de proyectar el arrastre sobre ese
riel proyectado, de modo que el vértice acompaña al dedo en pantalla. La sesión publica
`motion`, `slide_clamp` y, cuando ya hay riel, `slide_factor`.

Con un destino geométrico, el UPDATE sondea bajo `u`,`v` con la misma consulta que
`transform.snap_candidate` (excluyendo la geometría que se está moviendo) y resuelve
fuente→destino: la fuente es el elemento arrastrado, así que el vértice aterriza
exactamente sobre el candidato. Sin impacto, ese UPDATE se comporta como `NONE` y sigue
el dedo. `SLIDE` y los destinos geométricos son excluyentes: deslizar por una arista ya
determina el destino, y el snap de `SLIDE` solo aplica `INCREMENT` sobre su factor.

Con shading `WIREFRAME` el pick ve a través en ambos modos. En Object Mode **cicla hacia
detrás**: si el primer objeto impactado ya está seleccionado, se avanza el origen del
rayo más allá del impacto y se repite (hasta 16 impactos), eligiendo el primero no
seleccionado. En Edit Mode los candidatos son todos los vértices/aristas no ocultos de
la malla (no solo los de la cara frontal): el tap elige el más cercano al toque en
pantalla, y con `ADD`/`TOGGLE` cicla al no seleccionado más cercano — el equivalente
táctil del Alt+click de Blender. El submodo FACE mantiene la cara impactada por el rayo.
Esta selección a través es la razón por la que wireframe activa xray siempre.

`selection.box` y `selection.circle` funcionan en ambos modos: en Edit seleccionan
elementos del submodo activo cuyo centro proyectado cae dentro de la forma; en
Object Mode seleccionan los objetos visibles cuyo centro (`matrix_world` de la
translation) cae dentro.

`selection.more` extiende la selección a los elementos adyacentes y `selection.less`
retira los que tocan algo no seleccionado, según el submodo activo (equivalente a
Ctrl+Plus / Ctrl+Minus del numpad). Solo Edit Mode (`wrong_mode` fuera).

### Transformaciones

`transform.move`, `transform.rotate`, `transform.scale`, `transform.reset`,
`transform.apply` (`objects[]?`, `location?`, `rotation?`, `scale?`).

```json
{"type":"command","id":"7","command":"transform.rotate",
 "payload":{"z":45,"pivot":"MEDIAN"}}
```

`rotate` acepta además eje/ángulo explícitos: `{"axis":[0,0,1], "angle":45}`.
`scale` acepta `{"factor": 2.0}` para escala uniforme.

`transform.reset` **borra** loc/rot/escala (deja la malla igual). `transform.apply`
**hornea** en la malla y deja el transform en identidad (Ctrl+A). Payload:
`location`, `rotation` y `scale` (bool). Hace falta al menos uno a true; si no,
`bad_payload`. Solo Object Mode (`wrong_mode` en Edit). Datos de malla compartidos
(Alt+D) responden `shared_data`.

### Malla (requieren Edit Mode)

| Comando | Payload |
|---|---|
| `mesh.extrude` | `offset` (def. 0.0), `direction` [x,y,z] opcional, `variant`: `REGION`\|`MANIFOLD`\|`ALONG_NORMALS`\|`INDIVIDUAL` |
| `mesh.inset` | `thickness` (def. 0.1), `depth`, `individual` (bool), `boundary` (bool, def. true; false conserva costuras abiertas/Mirror) |
| `mesh.bevel` | `offset` (def. 0.1), `segments` (def. 1), `profile` (0..1, def. 0.5), `miter_outer`: `SHARP`\|`PATCH`\|`ARC` (def. `SHARP`), `affect`, `clamp` |
| `mesh.subdivide` | `cuts` |
| `mesh.loop_cut` | `edge` (opcional), `cuts` (def. 1), `smoothness`, `factor`, `slide_distance` (metros, opcional), `falloff`, `even`, `flip`, `clamp` |
| `mesh.loop_probe` | `u`, `v` — sondeo read-only para colocar un corte con el toque |
| `mesh.delete` | `what`: `VERTS`\|`EDGES`\|`FACES`\|`ONLY_FACES` |
| `mesh.connect_vertices` | —; J nativo en Vértices: conecta al menos dos seleccionados y divide las caras atravesadas; un undo |
| `mesh.make_edge_face` | —; crea arista/cara en Vértice o rellena un borde cerrado en Arista |
| `mesh.separate` | —; separa la selección en un objeto nuevo |
| `mesh.split` | —; separa la selección dentro de la misma malla |
| `mesh.looptools_circle` | —; ejecuta Circle del add-on LoopTools sobre la selección |
| `mesh.normals_recalculate` | `inside` (bool, def. false) |
| `mesh.normals_flip` | — |
| `mesh.info` | — |

`mesh.extrude` con `offset: 0` (el valor por defecto) replica el flujo interactivo de
Blender: extruye sin desplazar y **deja la geometría nueva seleccionada**, para que la
tablet la arrastre después con un gesto `move`.

`variant` es `REGION` por defecto. En caras, `ALONG_NORMALS` desplaza cada vértice
nuevo según su normal y `INDIVIDUAL` crea una copia desconectada por cada cara; ambas
requieren el submodo Cara (`incompatible_selection` fuera de él). `direction` no se
combina con `ALONG_NORMALS`. Aristas y vértices sólo admiten `REGION`, que extruye
la geometría efectiva seleccionada: caras completas primero, después aristas y,
si no hay ninguna, vértices individuales. El extremo nuevo queda seleccionado para
confirmar y continuar con Escalar, conservando fija la base.
`MANIFOLD` también requiere Cara y ejecuta `mesh.extrude_manifold` nativo, con
disolución de bordes coplanares e intersección de los nuevos. Comparte los ejes,
orientación, distancia y snap de Región, dentro de la misma sesión reversible.

`mesh.loop_cut` replica el modal Ctrl+R con parámetros explícitos. `factor` es el
deslizamiento: 0 deja el corte en la mitad del anillo, ±1 lo lleva a los extremos.
Con `clamp: false` (def. true) admite hasta ±2 y extrapola más allá del borde,
siguiendo su línea. `falloff` es la forma del perfil
(`SMOOTH|SPHERE|ROOT|SHARP|LINEAR|INVERSE_SQUARE`, def. `SMOOTH`), `even` interpreta
el deslizamiento en longitud real (el corte recorre la misma distancia absoluta en
cada arista del anillo, aunque midan distinto), y `flip` lo espeja (`t → 1−t`).
Valores fuera de rango responden `bad_payload`.

La serie de cortes se desplaza conservando su separación: el factor desplaza
`factor / (cuts + 1)` de cada arista. En `even` usa longitud física uniforme.
`slide_distance` expresa metros desde la posición centrada, activa `even` y tiene
prioridad sobre `factor`. El recorrido métrico de referencia `slide_range` es la
longitud física de la arista más corta del anillo dividida entre `cuts + 1`;
incluye `matrix_world` y `scale_length`. El estado de herramienta y su preview
publican `slide_range` y `slide_distance`; `factor = slide_distance / slide_range`.
Sin esos campos Android ofrece únicamente porcentaje. Un cambio explícito de
`factor` descarta la distancia anterior; el arrastre mantiene la modalidad métrica.
Una medida inválida conserva la preview anterior. `flip` invierte el sentido visual.

`mesh.loop_probe` no toca nada: lanza el rayo del toque, toma la arista más cercana
de la cara impactada (distancia en pantalla, sin umbral: cualquier toque sobre la
malla elige algo) y proyecta el punto sobre ella. Devuelve
`{hit, object, edge, factor, ring}`, donde `factor` (−1..1) describe la posición
sondeada sobre la arista. Loop Cut usa la arista y comienza centrado, sin aplicar
ese factor del toque. Sin impacto, `{hit: false}`. Requiere
viewport (`no_viewport` en background) y Edit Mode (`wrong_mode`).

### Historial

`history.undo`, `history.redo`, `history.push` (`message`) y `history.repeat_last`.
Este último es el Shift+R remoto: repite la última acción discreta de modelado o la
última herramienta paramétrica confirmada, pero ignora selección, navegación, archivos
y sesiones incompletas. Cada repetición crea su propio paso de undo.

### Vista

| Comando | Payload |
|---|---|
| `view.orbit` | `dx`, `dy` (fracción de pantalla; 1.0 = 180°) |
| `view.pan` | `dx`, `dy` |
| `view.zoom` | `factor` (>1 acerca) o `delta` |
| `view.frame_selected` / `view.frame_all` | — |
| `view.axis` | `axis`: `FRONT`\|`BACK`\|`LEFT`\|`RIGHT`\|`TOP`\|`BOTTOM` |
| `view.perspective` | `mode`: `PERSP`\|`ORTHO`\|`TOGGLE` |
| `view.shading` | `mode`: `WIREFRAME`\|`SOLID`\|`TOGGLE` |
| `view.overlays` | `show` (bool; por defecto toggle) |
| `view.local` | `enabled` (bool; por defecto toggle) |
| `view.get` / `view.set` | `location`, `rotation` (quaternion wxyz), `distance` |

`view.shading` cambia el shading del viewport que se captura (el espacio VIEW_3D real).
`WIREFRAME` activa siempre `show_xray_wireframe`, para que se vea y se pueda picar a
través. El paquete es inseparable también al togglear: `TOGGLE` solo considera
"wireframe" el estado con xray puesto — un WIREFRAME sin xray (Shift+Z en el PC, un
`.blend` guardado así) se re-arma como WIREFRAME+xray en vez de bajar a SOLID. El
estado actual viaja en `scene.get_state` como `shading` (top-level): `"WIREFRAME"` o
`"SOLID"` (`"SOLID"` si no hay viewport, p. ej. en background).
Requiere viewport (`no_viewport` en background).

`view.overlays` enciende o apaga los overlays de ese mismo espacio
(`space.overlay.show_overlays`): la rejilla del suelo, los ejes y el cage de Edit Mode,
que `draw_view3d` dibuja. Sin `show` alterna. Devuelve `{"overlays": bool}` y el estado viaja
también en `scene.get_state` como `overlays` (top-level). Requiere viewport
(`no_viewport` en background). Lo usa el botón del ojo de la tablet: ocultar los
controles deja el vídeo limpio, sin interfaz encima y sin rejilla debajo.

`selection.linked` extiende la selección a las islas conectadas (la `L` / `Ctrl+L`):
recorre por aristas desde lo ya seleccionado y se detiene en lo oculto. Sin selección
de partida responde `empty_selection`. Devuelve `selection.info` más `affected` (número
de vértices de las islas).

`view.local` aísla la selección: oculta todo objeto visible no seleccionado y recuerda
exactamente qué ocultó para restaurarlo al desactivar (el `/` de Blender). Es un
toggle si no llega `enabled`. Devuelve `{"local": bool, "hidden": [nombres]}`. Cargar
o crear un archivo desactiva el aislamiento (los objetos ocultados antes del aislamiento
siguen ocultos: nunca se tocan).

### Transformación modal

Se confirma a mano, no al soltar el dedo. Es lo que permite recolocar la mano a
mitad de un desplazamiento largo, cambiar de eje o teclear el valor exacto con la
transformación todavía viva.

| Comando | Payload |
|---|---|
| `transform.begin` | `mode`: `MOVE`\|`ROTATE`\|`SCALE`, `axes[]`/`constraint`, `orientation`, `value_mode`, `snap`, `snap_type`, `step`, `scale_step_unit`; en Edit también `proportional`, `radius`, `falloff` |
| `transform.axes` | `axes[]` — cambia la restricción en vivo |
| `transform.orientation` | `orientation` — cambia GLOBAL/LOCAL/VIEW/NORMAL sin reiniciar la sesión |
| `transform.snap` | `snap` (bool), `snap_type`, `step`, `snap_to_selection`, `scale_step_unit`; en Move no admite `GRID` ni `CURSOR` |
| `snap.query` | `u`, `v`, `snap_type`: `VERTEX`\|`EDGE`\|`EDGE_CENTER`\|`FACE`\|`FACE_CENTER`\|`CURSOR`, `threshold` |
| `transform.snap_candidate` | igual que `snap.query`, `lock` (predeterminado true) |
| `transform.reference_candidate` | `u`, `v`, `lock`, `role`: `CENTER`/`SOURCE`; `clear`; o `preset`: `SELECTION`/`OBJECT_ORIGIN`/`CURSOR` para CENTER. MOVE usa source→target; ROTATE/SCALE separan centro, fuente y destino |

El snap exacto de MOVE/ROTATE/SCALE ofrece `VERTEX`, `EDGE_CENTER` y `FACE_CENTER`. Sus radios
táctiles predeterminados para el destino son respectivamente `0.080`, `0.070` y `0.065`.
Las distancias se miden en fracciones del ancho de imagen, corrigiendo el eje vertical
por la relación de aspecto; el radio de adquisición es circular en pantalla.
El sondeo continuo aplica una histéresis común: adquiere dentro del radio de cada tipo,
conserva el candidato hasta un radio de salida mayor y solo cambia antes si el nuevo
candidato mejora claramente la distancia. Esta política también se usa en REL/Fuente,
Tweak, Extrude y Knife; `END` conserva el último candidato visual estable.
REL/Fuente usa radios de entrada separados (`VERTEX` 0.055, `FACE_CENTER` 0.050 y
`EDGE_CENTER` 0.045). Compara las tres categorías en una sola competición por distancia.
El radio de salida es `entrada * 1.55 + 0.012`; un nuevo punto debe estar dentro de su
radio de entrada y mejorar al retenido en más de `0.014`. La retención pertenece al
`id`, no a la categoría. La búsqueda incluye siluetas y mallas de aristas aunque el
rayo central no golpee una cara, y descarta candidatos ocluidos antes de elegir.
Solo atraviesa los objetos excluidos explícitamente por la sesión.
| `transform.nudge` | `dx`, `dy` — normalmente llega por el canal de gestos |
| `transform.value` | `values`: [x,y,z], `angle` en GRADOS legado, o `dimensions`: [x,y,z] finales en unidades Blender para SCALE |
| `transform.session` | Publica `values` canónico y los roles `center`, `source`, `target`; `angle` y `reference_*` quedan como derivados v2 |
| `transform.select` | Edit: `u`, `v`, `threshold`, `mode`: SET/ADD/REMOVE/TOGGLE; confirma el paso y continúa en la nueva selección |
| `transform.confirm` | — cierra con un único paso de undo |
| `transform.cancel` | — restaura las matrices originales |

`transform_modal` v4 anuncia `edit_step_selection: true`. En Edit, `transform.select`
sondea una sola vez la malla de la preview sin cambiar la selección. Si el toque elige
otra selección no vacía, confirma la transformación anterior y comienza un nuevo
baseline con la misma herramienta, ejes, orientación, snap, paso y ajustes proporcionales.
Devuelve la nueva sesión (otro `session_id`), `selection_changed` y un snapshot explícito
`state`; este snapshot es la única parte de la respuesta que actualiza la escena Android.
Los valores vuelven a 0/0°/100 % y centro/fuente/destino se recalculan o se liberan.
Un miss, una selección idéntica o vacía devuelve la misma sesión sin confirmar.
Cada cambio geométrico confirmado crea un undo; elegir sin transformar y terminar
una continuación sin cambios no generan pasos vacíos. Reset y cancelar restauran
solo el baseline actual, conservando los pasos anteriores.
Android permite elegir por toque sin snap geométrico. «Otra selección» arma la
selección explícita incluso con snap o REL activos; se desarma al cambiar de sesión.
Mientras se elige no envía nudges ni sondeos de snap. Los toques sucesivos en estas
sesiones Edit se procesan individualmente, sin encuadrar por doble toque.

En SCALE, `scale_step_unit` indica cómo interpretar `step`: `FACTOR` (predeterminado,
porcentaje dividido entre 100) o `LENGTH` (mm/cm/m convertidos a unidades Blender,
incluyendo `scale_length`). Se fija en `transform.begin`, puede cambiarse en
`transform.snap` y se publica en la sesión; omitirlo en `transform.snap` conserva
su valor. Android usa un único selector para dimensiones X/Y/Z, paso y botones.
Cada botón suma/resta la longitud elegida en su eje y convierte desde su dimensión
base; con cadena replica el factor para conservar las proporciones del baseline.
El gesto con paso métrico toma la dimensión base mayor entre los ejes activos
(o el único eje restringido) y usa un factor común. Los incrementos parten de 100 %;
los ejes excluidos permanecen a 100 %. `transform.value` en SCALE respeta el valor
exacto, incluidos los botones y Reset, sin redondearlo otra vez; el siguiente gesto
vuelve a aplicar el snap. Una dimensión base nula no admite incremento métrico.
Los valores y dimensiones SCALE admiten cero exacto para aplanar, incluso con snap.
`transform.value` también acepta `flatten_axis: X|Y|Z` exclusivamente en SCALE.
En una única petición toma los factores visibles actuales, fija a cero el eje indicado,
retira la restricción de ejes y aplica el valor exacto; mantiene la sesión y los otros
factores. Android usa este comando tanto al escribir cero como desde X=0/Y=0/Z=0,
independientemente de la cadena. Reset sigue enviando `[1,1,1]` sobre el baseline.

Snap incremental y rejilla en la sesión modal:

- `INCREMENT`: el delta se cuadra a múltiplos de `step` desde el punto de
  partida. Mover el dedo cruza cada múltiplo en vivo; no hace falta levantar y
  volver a arrastrar para dar otro salto.
- `GRID`: la posición resultante se clava a la rejilla mundial de paso `step`
  (se redondea `posición original + delta` a múltiplos de `step` en coordenadas
  de mundo). Un objeto que nazca fuera de rejilla aterriza en ella. En ROTATE y
  SCALE se comporta como INCREMENT.
| `transform.status` | — |

Cada sesión incluye UUID `session_id`, `owner` y `phase`. Solo su conexión propietaria
puede alterarla; al desconectarse se cancela. Funciona tanto en Object como en Edit y
reconstruye matrices o coordenadas BMesh desde el snapshot inicial.

`snap_to_selection` es falso al abrir cada transformación. Cuando se activa, el snap
geométrico admite también como destino el objeto seleccionado en Object Mode o los
elementos seleccionados en Edit Mode; desactivado los excluye del sondeo de destino.

En ROTATE/SCALE, `center_mode` publica `SELECTION`, `PICKED`, `OBJECT_ORIGIN` o
`CURSOR`. Los presets de centro cambian el pivote de la preview sin reiniciar la sesión.

Los marcadores de transformación se dibujan en GPUOffScreen antes de codificar cada
fotograma H.264/MJPEG. Android no los superpone de nuevo desde `transform.session`.
Centro (cruz roja), fuente (rombo ámbar), destino (círculo azul) y candidato temporal
(verde) son independientes; sus símbolos permiten distinguir posiciones coincidentes.
Se proyectan con la cámara de ese fotograma. Fuera de pantalla o detrás de la cámara
no se dibujan, pero la referencia 3D permanece fijada. Los campos de estado se conservan
para los controles; `screen` queda vacío cuando no se puede proyectar un punto fijado.
Este cambio requiere instalar APK y add-on de la misma entrega.

Al bloquear referencias sobre una preview existente, `SOURCE` se convierte al baseline
para que la transformación se aplique una sola vez. `CENTER` conserva, en cambio, la
posición visible exacta: desde ese instante es un pivote estacionario, no un punto que
deba desrotarse o desescalarse con la selección.

### Alinear caras en Object Mode

`tool.begin` con `tool: "ALIGN"` abre una sesión reversible sobre la malla activa,
o sobre `parameters.object` si se proporciona su nombre. Comparte exclusión modal,
propietario, cancelación, desconexión y confirmación con las herramientas `tool.*`.
Solo se transforma el objeto fuente. El destino debe ser otro objeto que no dependa
jerárquicamente de la fuente. Las caras se sondean sobre la geometría evaluada visible.

`tool.face_pick` recibe `u`, `v`, `role: SOURCE|TARGET` y `phase: TAP|UPDATE|END|CANCEL`.
`UPDATE` muestra un candidato; `END` fija exclusivamente ese candidato, sin raycast.
`TAP` sondea y fija en una operación. `CANCEL` descarta el candidato, conservando las
caras fijadas. Cada rol es independiente. Tras fijar fuente se arma destino. Fuente
solo sondea su objeto; destino lo excluye para acceder a la otra pieza.

Parámetros editables mediante `tool.parameter`:

| Parámetro | Valores / comportamiento |
|---|---|
| `pick_role` | `SOURCE`, `TARGET`: permite volver a elegir una cara |
| `mode` | `CONTACT` (predeterminado): centros coincidentes y normales enfrentadas; `ORIENT`: misma orientación de caras, manteniendo el origen fuente; `COPY_ROTATION`: copia la orientación mundial del objeto destino, manteniendo origen y tamaño fuente |
| `twist` | `"0"`, `"90"`, `"180"`, `"270"`, en grados alrededor de la normal destino; no se aplica en `COPY_ROTATION` |
| `gap` | Separación no negativa, en unidades Blender, a lo largo de la normal destino; solo en `CONTACT` |

La alineación orienta también una arista de cada cara para resolver el giro restante.
Usa las caras planas completas y no reescala la fuente: con caras de tamaños distintos
coinciden centros y planos, no necesariamente todos los bordes. El objeto fuente no
puede tener restricciones activas que gobiernen su transformación; una jerarquía que
no permita representar el resultado exacto produce error y conserva la preview previa.

El estado añade `input: "FACE_PAIR"`, `instruction`, `can_confirm`, `source_object`,
`target_object` y `controls[]`. Cada control usa `id`, `label`, `type`, `values`,
`labels` (etiquetas de enum), `unit`, `step`, `min` y `max`, según corresponda.
Android dibuja esos descriptores en la bandeja compartida; `unit: "length"` convierte
con `scale_length` y la unidad del preset. `tool.session` publica cambios de estado e
invalidaciones. Confirmar exige ambas caras y deja un único paso de undo; `ALIGN` no
se repite mediante `history.repeat_last` porque sus referencias son propias de la sesión.

Fuente (ámbar), destino (azul) y candidato (verde) muestran su contorno y su marcador
en el propio vídeo, reproyectados en cada frame. APK y add-on deben actualizarse juntos.

### Ajustes globales de Edit

`edit.settings` devuelve `edit_settings`; el mismo bloque también viaja en
`scene.get_state`. `edit.settings_set` cambia uno o varios valores: `proportional`
(bool), `falloff` (`SMOOTH|SPHERE|ROOT|SHARP|LINEAR|CONSTANT|INVERSE_SQUARE`),
`radius` (> 0), `auto_merge` (bool) y `merge_threshold` (>= 0). Son ajustes globales
respaldados por `ToolSettings` de Blender y se conservan entre transformaciones.
`radius` y `transform.proportional_radius` usan unidades Blender. Cambiar el preset
aplica su `proportional_radius` (metros) dividido por `scale_length`; la tablet
convierte igualmente el `proportional_radius_step` físico para sus −/+. El campo
muestra mm/cm/m según el preset y los números sin sufijo usan esa unidad.
Una sesión proporcional Edit publica además
`proportional_circle: {center:[u,v], radius}` en coordenadas normalizadas del viewport,
proyectado por la misma cámara que produce el vídeo.

Con una transformación Edit activa, `edit.settings_set` actualiza radio, perfil o
activación sobre el baseline original sin reiniciarla ni cambiar sus valores,
referencias o `session_id`. La respuesta incluye la sesión actualizada en `transform`,
además del snapshot de escena. Reducir el radio restaura los vértices que salen de la
influencia; cambiar ajustes no añade undo y confirmar mantiene un único paso.

La edición proporcional afecta a los vértices visibles dentro del radio durante
MOVE/ROTATE/SCALE, con peso según el perfil elegido; cancelar restaura todas las
coordenadas originales. Auto Merge se aplica al confirmar un MOVE en Edit Mode:
los vértices seleccionados que queden a `merge_threshold` de geometría estacionaria
se sueldan dentro del mismo paso de undo de la sesión.

Arrastre de un dedo (`gesture` `rotate`/`scale`, en modal o en la ruta legacy sin
sesión abierta): `dx` horizontal maneja ambos — dedo a la derecha gira en sentido
horario visto en pantalla y agranda; a la izquierda, antihorario y encoge. `move`,
`orbit`, `pan`, `zoom` y `roll` no cambiaron.

### Herramientas paramétricas de Edit Mode

`tool.begin` (`tool`: `EXTRUDE|BEVEL|INSET|SUBDIVIDE|LOOP_CUT|BRIDGE_EDGE_LOOPS|KNIFE|BISECT`,
`parameters`), `tool.parameter`, `tool.nudge`, `tool.confirm`, `tool.cancel` y
`tool.status` forman una sesión propietaria. Cada preview se reconstruye desde una
copia BMesh inicial; cancelar restaura exactamente la topología y confirmar crea un
único paso de undo.

`LOOP_CUT` y `BISECT` son herramientas de entrada por viewport: `tool.begin` puede
dejarlas **armadas** (`active: false, armed: true, phase: "ARMED"`) en vez de fallar,
cuando todavía no hay con qué construir la geometría (`LOOP_CUT` sin `edge` ni arista
seleccionada; `BISECT` siempre arma). Armada, la herramienta no tiene backup ni
preview — el primer toque/arrastre en el viewport (`tool.loop_pick` o
`tool.drag_line`) es quien crea el backup y pasa a `ACTIVE`. `tool.status` refleja
`armed`/`phase` en todo momento; `tool.cancel` en `ARMED` simplemente desarma
(`phase: "CANCELLED"`, sin geometría que restaurar). Activar otra familia o variante
mientras algo está armado o activo lo cancela/restaura primero: nunca confirma
geometría implícitamente.

`LOOP_CUT` corta el anillo de la arista semilla (`edge` o la seleccionada). El
parámetro primario de `tool.nudge` es `factor` (deslizamiento; ±0.999, o ±1.999 si la
sesión lleva `clamp: false`). No es `mesh.subdivide` (eso corta la selección) ni
`selection.loop`.

`tool.loop_pick` (`u`, `v`, `add` opcional) coloca (desde `ARMED`) o re-ubica (con sesión `ACTIVE`) el
corte de `LOOP_CUT`: restaura la copia original si la había, sondea con la semántica
de `mesh.loop_probe` (los índices de `edge` son de la malla original, no del preview)
y fija `edge` y reinicia `factor` a 0 (centro), descartando la distancia anterior.
La posición del dedo nunca desplaza el primer corte. Responde con el estado de la
sesión más `pick`. Sin sesión activa ni armada responde `no_session`; con sesión
activa de otra tool, `wrong_tool`. Sin impacto bajo el dedo, `ARMED` se queda como
estaba y `ACTIVE` conserva el corte anterior.

Con `add: true`, el preview actual se fija como base acumulada y el toque crea otro
Loop Cut sobre la topología resultante. El estado publica `loop_count`. Todos los
cortes se confirman con un solo undo y cancelar restaura la malla anterior a la sesión.
`tool.loop_pop` descarta el corte activo y vuelve al anterior para editarlo; sin
historial responde `empty_history`.

La feature `edit_tools.loop_cut` anuncia `pick`, `probe`, `falloff`, `even`, `flip`,
`multiple`, `pop`, `centered_pick`, `distance` y
`clamp`; un cliente debe usar el flujo de colocación por toque solo si `pick` está
anunciado.

Extruir, Inset y Bisel comparten el paso métrico editable de snap. Android convierte
mm/cm/m según `scale_length` y, con Incremento/Rejilla, traduce el 4 % de arrastre
vertical a un paso. El backend conserva el acumulador continuo pero publica en
`parameters` el valor de la preview redondeada. `tool.snap_candidate` actualiza la
preview de Extrude REGION/MANIFOLD también con `lock: false`; respeta su eje y convierte el
destino de mundo al espacio local del objeto antes de extruir. Extruir muestra Paso
con botones −/+ también sin snap; cada pulsación cambia `snap_step` en una unidad
de la unidad métrica elegida (mínimo 0.001). Editar solo el paso conserva la distancia
y la preview actuales; el siguiente gesto usa el nuevo paso.
Distancia tiene sus propios −/+ que suman/restan el paso vigente. Una edición de
`offset` se aplica exactamente, sin cuantizar otra vez por snap; el siguiente
`tool.nudge` vuelve al incremento gestual. Cada pareja de botones mantiene el valor
local pendiente para que las pulsaciones rápidas no dependan de la latencia.
La edición de `offset` descarta el candidato geométrico anterior para aplicar el valor
paramétrico. Su campo Distancia muestra unidades y acepta cantidades con o sin sufijo
(en este último caso usa la unidad del preset).
Extrude Región mueve y selecciona únicamente los vértices nuevos: las conexiones
con la base no incluyen sus vértices originales en el desplazamiento ni la selección.

Extrude «A toque» se activa con `tool.begin`, `tool: EXTRUDE` y
`parameters: {variant: CURSOR, rotate_source: true}`. El rail anuncia la variante
`CURSOR` con entrada `REPEAT_TAP`. Permanece `armed: true`, `active: false` y no
crea geometría hasta recibir `tool.extrude_cursor` con `u`, `v` normalizados.
Cada toque extruye hacia el punto de la vista a la profundidad del centro de la
selección; sin selección crea un vértice a la profundidad del cursor 3D. Se usa la
cámara remota, sin modificar `rv3d`, tanto en perspectiva como en ortográfica.
`rotate_source` (bool, true) reparte el giro entre la selección de origen y el extremo
nuevo; false conserva el origen y orienta solo el extremo. Se edita con
`tool.parameter` y se describe en `controls`. No utiliza snap en esta variante.
Cada toque válido confirma un tramo con un undo y devuelve el estado armado con
`result: {changed, position?}`. Tocar el centro actual no duplica geometría ni crea
undo. Un error restaura ese tramo; salir con `tool.cancel`, cambiar de herramienta
o desconectar conserva los tramos ya confirmados. Undo cierra primero la herramienta.
Android captura cada contacto completo: DOWN inicia, MOVE actualiza el destino y
UP confirma la última posición estable, sin tomar las coordenadas de liberación.
Deslizar no descarta el toque; un segundo dedo, cancelar o cambiar de herramienta
descarta el contacto pendiente. Dos dedos navegan y no muestra confirmación por tramo.
La extrusión usa la selección efectiva: seleccionar vértices que forman aristas o
caras produce su extrusión conectada, sin cambiar el selector Vértices/Aristas/Caras.

`REVOLVE` y `SWEEP` se anuncian en `edit_tools` v11 y en el catálogo contextual,
sin añadir botones al rail. Ambas usan `tool.begin/parameter/confirm/cancel` y
publican `input: PARAMETERS`, `instruction` y `controls`; no admiten `tool.nudge`.
El componente común representa controles `int`, `float`, `enum` y `bool`.

- `REVOLVE` (Revolución): selección de vértices/aristas/caras; `angle` en grados
  (−360..360, defecto 360), `steps` (1..256, defecto 32; mínimo 3 para una vuelta),
  `axis` global (`X|Y|Z`, defecto Z), `center_x/y/z` en unidades Blender (inicialmente
  cursor 3D), `merge` (true) une la costura de una vuelta completa. Los puntos sobre
  el eje se sueldan. El cálculo conserva el radio físico con escalas no uniformes.
- `SWEEP` (Barrido / Marco): una cadena o loop conectado, plano, sin ramificaciones
  ni caras, seleccionado en Vértices o Aristas. Genera un perfil rectangular centrado
  en el recorrido, con `width` y `depth` positivos en unidades Blender; sus valores
  iniciales son 0.05 m y 0.1 m convertidos según `scale_length`. `caps` (true) tapa
  los extremos de cadenas abiertas. Las esquinas comparten ingletes. Sustituye el
  contorno seleccionado y conserva las aristas externas no seleccionadas. Esta
  primera variante admite un perfil rectangular, no perfiles arbitrarios.

Los controles de longitud usan la unidad del preset; cambiar cualquier parámetro
reconstruye desde el baseline. Un error conserva la última preview válida; Cancelar
restaura el perfil/recorrido inicial y Confirmar registra un único undo.

Knife coloca puntos con `tool.knife_drag` (`phase` `BEGIN|UPDATE|END|CANCEL`, `u`,`v`).
BEGIN y UPDATE solo mueven el candidato sin mutar la malla; END fija exactamente un
punto. Dos puntos forman el primer segmento y los siguientes continúan el trazo.
`tool.knife_new_stroke` termina el trazo actual y abre otro independiente dentro de la
misma sesión y del mismo undo, lo que permite conexiones convergentes como 4→2. El
estado publica `strokes`/`projected_strokes` para los trazos terminados y conserva
`points`/`projected_points` para el activo. Si una reconstrucción falla, la operación revierte tanto las
anclas tentativas como cualquier mutación parcial del BMesh antes de responder el error.
La cara visible es un destino exacto y el snap
puede resolver `VERTEX`, `EDGE_CENTER` o `EDGE` (punto más cercano de la arista) dentro
de umbrales táctiles deliberadamente pegajosos (0,080/0,070/0,042 del viewport,
respectivamente, en fracciones del ancho y con corrección de aspecto). Los puntos
discretos compiten por distancia con la política común de histéresis; una arista no
puede robar el snap a un vértice o centro adquirible por tener distancia cero.
En `AUTO`, las zonas prioritarias de vértice y centro se reducen a 0,035 y 0,028 para
dejar accesible el cuerpo de la arista. Los radios grandes 0,080/0,070 se conservan al
forzar `VERTEX` o `EDGE_CENTER`, donde la intención ya no es ambigua.
La búsqueda usa el BMesh vivo, incluidos los vértices creados por trazos terminados,
y filtra oclusión antes de competir; admite también la silueta sin impacto del rayo
central. `tool.parameter` acepta `snap` y `snap_mode` (`AUTO|VERTEX|EDGE_CENTER|EDGE`).
Cada segmento debe recorrer la superficie: para cambiar de plano hay que marcar el
borde. Un segmento que cruza el volumen se rechaza sin modificar las caras ni los
trazos anteriores. Las cadenas interiores dividen solo la cara recorrida en n-gons,
también si es cóncava; no se integran puntos mediante abanicos de triángulos.
El cliente confirma la última muestra estable anterior a ACTION_UP,
evitando el salto que aparece al levantar el lápiz. `tool.status` publica
`projected_points` y `snap_candidate`
reproyectados con la cámara actual. La feature `edit_tools.knife` anuncia
`point_on_release`, `multiple_strokes` y `new_stroke`; `tool.knife_point` permanece como compatibilidad para clientes v2
anteriores.

La sesión avanzada mantiene el trazo activo solo como overlay. «Nuevo corte» lo fija en
una preview reversible, de modo que el siguiente trazo puede snapear contra los vértices
que acaba de crear; Confirmar reconstruye todos los trazos desde el backup y los agrupa
en un solo undo. Si cualquiera falla se revierte el backup completo. `snap_mode` permite elegir
`AUTO`, `VERTEX`, `EDGE_CENTER` o `EDGE`; solo se consideran elementos pertenecientes a
la cara visible alcanzada por el raycast, nunca vecinos ocultos por conectividad.
Antes de aplicar Knife se crea un estado base explícito de undo en Edit Mode; así un
único Deshacer elimina el conjunto sin expulsar al usuario a Object Mode.

`BISECT` corta con un plano infinito cuya traza en pantalla es la línea que arrastra
el dedo (`tool.drag_line`, `start`/`end`: `[u, v]` normalizados). El plano contiene la
dirección de ese arrastre y la de visión (profundidad), así que se ve como una línea
recta que cruza toda la pantalla; su posición perpendicular la fija el punto medio de
la línea, con snap opcional a vértice/arista (parámetro `snap`, activado por
defecto) igual que Knife. `tool.drag_line` en `ARMED` crea el backup y activa la
sesión con ese plano; en `ACTIVE` reconstruye desde el backup con el plano nuevo, sin
acumular cortes. Un arrastre que no cruza geometría responde `topology_incompatible`
y la tool vuelve a `ARMED` (no se pierde la elección de Cut). Parámetros:
`clear_inner`, `clear_outer` y `fill` (bool, todos `false` por defecto). No se nudea
(`tool.nudge` responde `wrong_tool`); confirmar sin línea dibujada responde
`empty_selection`. La feature `edit_tools.bisect` anuncia `drag_line`, `snap`,
`clear_inner`, `clear_outer` y `fill`.

Snap real de incremento/rejilla en parámetros escalares de sesión: `EXTRUDE.offset`,
`BEVEL.offset`, `INSET.thickness`, `LOOP_CUT.factor` y
`BRIDGE_EDGE_LOOPS.merge_factor` aceptan `snap_type` (`NONE`\|`INCREMENT`\|`GRID`,
`GRID` se trata como `INCREMENT` igual que en `transform_modal`) y `snap_step`
(paso, por defecto `0.1`). Cuadran el valor antes de aplicar el corte, así que cambian
el resultado geométrico real, no solo lo que se enseña. `INSET` e `EXTRUDE` también
aceptan `variant` (`REGION`\|`INDIVIDUAL` para Inset; `REGION`\|`MANIFOLD`\|`ALONG_NORMALS`\|`INDIVIDUAL`
para Extrude) como parámetro de sesión — cambiarlo reconstruye desde el backup, no
acumula. Los pasos de Extrude/Bevel/Inset son distancias en Blender Units (la UI los
presenta en cm/m usando `units.scale_length`); Loop Cut y merge son factores
adimensionales. En escalares `GRID` equivale a `INCREMENT`.

Inset REGION acepta además `boundary` (def. `true`), equivalente a Boundary de
Blender. Con `false`, los bordes abiertos no se desplazan: una costura sobre el plano
de un modificador Mirror permanece pegada al espejo durante el inset.

Extrude `REGION` y `MANIFOLD` admiten snap geométrico. Durante el arrastre el cliente llama
`tool.snap_candidate` con `u`, `v`, `snap_type` (`VERTEX|EDGE|EDGE_CENTER|FACE|FACE_CENTER|CURSOR`),
`threshold` y `lock`. `tool.status` publica `snap_type`, `snap_step` y
`snap_candidate` (o null), cuya forma común es
`{hit,snap_type,id,object?,element?,position:[x,y,z],screen:[u,v],distance}`.
`position` está en mundo y `screen` normalizado arriba-izquierda para el icono local.
Cada candidato reconstruye la preview desde el backup inicial.

### Catálogo contextual de Edit

`server.capabilities.features.edit_catalog` (versión 1) es el único catálogo para el
menú contextual nuevo de Edit. Sus grupos `VERTEX`, `EDGE` y `FACE` se eligen desde el
selector de submodo; el cliente no debe combinar los tres ni reconstruir una lista
local de herramientas. Si la feature no existe o sus grupos están vacíos debe conservar
la interfaz legacy.

Cada entrada tiene esta forma:

```json
{
  "id": "EXTRUDE", "label": "Extruir", "enabled": true,
  "execution": "SESSION", "command": "tool.begin",
  "requirements": {
    "mode": "EDIT", "selection_modes": ["FACE"],
    "selection": {"faces": {"min": 1}}
  },
  "variants": [{"id": "REGION", "label": "Región", "enabled": true}],
  "parameters": [{"id": "offset", "label": "Desplazamiento", "type": "float", "default": 0.0}]
}
```

`id` es la intención wire estable; `label` es texto presentado al usuario;
`execution` es `DISCRETE` o `SESSION`. `command`, cuando existe, es el comando que la
acción habilitada invoca y `payload` son sus campos fijos (por ejemplo `tool` para una
sesión o `inside` para recalcular normales). Las acciones `SESSION` existentes se
inician con `tool.begin`; los parámetros editables se mandan como `parameters`.
`requirements.selection` declara mínimos de `verts`, `edges` o `faces`: permite
ocultar o desactivar pronto, pero no sustituye la validación de topología del comando.
Los parámetros son tipados (`int`, `float`, `bool` o `enum`) y pueden incluir
`default`, `min`, `max`, `step` y `values`.

El primer conjunto congelado incluye las operaciones ya disponibles (Loop/Ring,
Extrude, Bevel, Inset, Subdivide, Loop Cut, Delete y Hide/Reveal), y los IDs nuevos
`BRIDGE_EDGE_LOOPS`, `MAKE_EDGE_FACE`, `KNIFE`, `SEPARATE`, `SPLIT`,
`RECALCULATE_NORMALS_OUTSIDE`, `RECALCULATE_NORMALS_INSIDE` y `FLIP_NORMALS`.
`DISSOLVE` se anuncia habilitado en Vértice/Arista/Cara mediante `mesh.dissolve`,
separado de `DELETE`. Una app no debe enviar un wire para una entrada deshabilitada.
`BRIDGE_EDGE_LOOPS` es una sesión de Arista: requiere exactamente dos loops cerrados
disjuntos de igual longitud. Sus parámetros son `twist_offset` (int, 0), `merge`
(bool, false) y `merge_factor` (float, 0..1, 0). La preview se reconstruye desde el
backup igual que las demás sesiones y el catálogo fija el mínimo rápido de seis aristas;
el backend valida la topología completa.
Extrude anuncia `REGION` en los tres grupos; `MANIFOLD`, `ALONG_NORMALS` e `INDIVIDUAL` sólo se
habilitan en Cara. El cliente debe respetar `enabled` y no deducir compatibilidades.

`LOOPTOOLS_CIRCLE` es una entrada condicional de los grupos VERTEX y EDGE. El servidor
la añade al `edit_catalog.groups` vivo únicamente cuando el operador oficial
`mesh.looptools_circle` está registrado (LoopTools instalado y habilitado). Si el
operador no existe, la entrada no se envía y el cliente no la muestra. Requiere al
menos tres vértices seleccionados y no tiene una aproximación geométrica propia del
servidor. La regla estable se declara en `edit_catalog.conditional_actions` con
`availability: "OPERATOR_REGISTERED"`; Android solo representa las acciones que estén
materializadas en `groups`.

La llamada remota a LoopTools desactiva el undo implícito del operador y registra
explícitamente un único paso después de finalizar. Undo restaura el estado anterior
a Círculo sin eliminar el Loop Cut confirmado previamente; redo recupera Círculo.

### Barra de tools activas de Edit (`edit_toolbar`)

`server.capabilities.features.edit_toolbar` (versión 2) es la feature para la barra
izquierda de Edit Mode con la lógica agrupada de Blender: herramienta activa con
variantes, no una lista de acciones discretas. Convive con `edit_catalog` (que no
cambia) — un cliente sin soporte de `edit_toolbar` sigue usando el catálogo legacy.

`families` es una lista ordenada y contractual: `EXTRUDE`, `BEVEL`, `INSET`, `LOOP_CUT`,
`BRIDGE_EDGE_LOOPS`, `CUT`. Bevel y Bridge Edge Loops (versión 2) son familias de una
sola variante, igual que Loop Cut: sin elección real de variante, solo aportan el
selector de snap y el icono en la barra en vez de vivir escondidos en el catálogo
contextual.

Bevel publica además de ancho y segmentos los dos parámetros que deciden la forma de la
esquina: `profile` (0..1; `0.5` es el arco circular, por debajo la hunde y `1.0` la
remata en pico) y `miter_outer` (`SHARP` corta la esquina en ángulo, `PATCH` la rellena
con una cara y `ARC` la redondea). Se anuncian también en
`edit_tools.bevel` (`profile`, `miter_outer`) para un cliente que no lea el toolbar.
Cada familia tiene esta forma:

```json
{
  "id": "EXTRUDE", "label": "Extrude", "default_variant": "REGION",
  "execution": "SESSION", "command": "tool.begin", "payload": {"tool": "EXTRUDE"},
  "input": "PARAMETRIC",
  "requirements": {"mode": "EDIT"},
  "variants": [
    {"id": "REGION", "label": "Región", "enabled": true,
     "requirements": {"mode": "EDIT", "selection_modes": ["VERTEX", "EDGE", "FACE"], "selection": {"verts": {"min": 1}}}}
  ],
  "parameters": [{"id": "offset", "label": "Desplazamiento", "type": "float", "default": 0.0}]
}
```

- `default_variant` es la variante que arma un tap sin variante recordada.
- Extrude distingue las variantes por icono y muestra su nombre en la bandeja.
  Las variantes incompatibles con el submodo quedan deshabilitadas; el backend
  rechaza ese cambio antes de cerrar la preview anterior. Los borradores de la
  bandeja se reinician con el `session_id` de la sesión nueva.
- `input` describe qué alimenta la sesión una vez armada: `PARAMETRIC` (los
  parámetros ya bastan, como Extrude/Inset), `VIEWPORT_TAP` (Loop Cut: el primer
  toque en el viewport la activa vía `tool.loop_pick`), `VIEWPORT_DRAG_SEGMENTS` (Knife:
  `tool.knife_drag` por fases) o `VIEWPORT_DRAG_LINE` (Bisect: un arrastre completo
  vía `tool.drag_line`). Puede repetirse por variante si difiere del de la familia
  (es el caso de `CUT`).
- `payload` son los campos fijos que hay que enviar junto a `parameters` al invocar
  `command`; una variante puede traer su propio `payload` que se funde sobre el de
  la familia (p. ej. `CUT` no fija `tool` a nivel de familia porque cada variante usa
  uno distinto: `{"tool": "KNIFE"}` o `{"tool": "BISECT"}`).
- `parameters` a nivel de familia son los compartidos por todas sus variantes
  (Extrude expone `offset`/`constraint`/`orientation`/`snap_type`/`snap_step` con
  `applies_to` marcando qué variantes los usan, igual que en `edit_catalog`); una
  variante puede añadir los suyos propios (Knife trae `snap`; Bisect trae
  `clear_inner`/`clear_outer`/`fill`/`snap`).
- `variants[].requirements`, cuando existen, se evalúan igual que en `edit_catalog`:
  mínimos para habilitar el botón, no una promesa de topología válida.

`CUT` agrupa `KNIFE` y `BISECT` en un único slot de la barra: tap arma la variante
recordada (o `KNIFE` por defecto), pulsación larga cambia de variante sin confirmar
la sesión anterior. `LOOP_CUT` tiene una sola variante (`LOOP_CUT`) porque su entrada
es el toque, no una elección de submodo.

Familia o variante nueva cancela/restaura lo anterior (ver estados `ARMED`/`ACTIVE`
más arriba): nunca hay confirmación implícita al cambiar de herramienta.

### Modificadores

Pila no destructiva del objeto activo. No confundir `modifier.add type=BEVEL` con
`mesh.bevel` / `tool` `BEVEL`, que destruyen la malla.

| Comando | Payload |
|---|---|
| `modifier.add_options` | `object?` — catálogo con descriptores tipados |
| `modifier.add` | `object?`, `type`: `SUBSURF`\|`MULTIRES`\|`ARRAY`\|`BEVEL`\|`SOLIDIFY`\|`BOOLEAN`\|`MIRROR`, `name?`, `parameters?` |
| `modifier.remove` | `object?`, `name` |
| `modifier.move` | `object?`, `name`, `index` |
| `modifier.set` | `object?`, `name`, `parameters{}` |
| `modifier.toggle` | `object?`, `name`, `viewport?`, `render?` |
| `modifier.apply` | `object?`, `name` — Object Mode; Edit → `wrong_mode` |

Tipos y parámetros:

| Tipo | Parámetros | Defaults |
|---|---|---|
| `SUBSURF` | `levels`, `render_levels`, `subdivision_type` (`CATMULL_CLARK`\|`SIMPLE`) | 1, 2, `CATMULL_CLARK` |
| `MULTIRES` | `levels`, `sculpt_levels`, `render_levels`; `total_levels` de solo lectura; acción `subdivide:true` | Se crea con un nivel nativo; no duplica uno existente |
| `ARRAY` | `count`, `relative_offset` `[x,y,z]`, `use_merge`, `merge_threshold` | 2, `[1,0,0]`, false, 0.01 |
| `BEVEL` | `width`, `segments`, `affect` (`EDGES`\|`VERTICES`), `limit_method` (`NONE`\|`ANGLE`), `angle_limit` (grados), `profile` | 0.1, 1, `EDGES`, `ANGLE`, 30, 0.5 |
| `SOLIDIFY` | `thickness`, `offset`, `use_even_offset`, `use_rim` | 0.1, −1, true, true |
| `BOOLEAN` | `operation` (`DIFFERENCE`\|`UNION`\|`INTERSECT`), `object` (nombre), `solver` (`EXACT`\|`FAST`) | `DIFFERENCE`, ninguno, `EXACT` |
| `MIRROR` | `use_axis_x/y/z`, `use_bisect_x/y/z`, `use_bisect_flip_x/y/z`, `use_clip`, `use_merge`, `merge_threshold`, `mirror_object` | X, sin bisect/flip, false, true, 0.001, ninguno |

Boolean apunta a otro objeto. Sin operando se añade vacío. Operando inexistente →
`not_found`. Operando = el propio objeto o no-malla → `bad_payload`. Si el cortador
desaparece, el estado lleva `"object": null`.

Mirror usa el origen del propio objeto mientras `mirror_object` sea nulo. El objeto
espejo puede ser de cualquier tipo, pero no puede ser el objeto modificado. Los cambios
de un único eje son parciales y conservan el resto de parámetros del modificador.

`object_info` incluye `modifiers[]`:

```json
{"name": "Subdivision", "type": "SUBSURF", "show_viewport": true, "show_render": true,
 "parameters": {"levels": 2, "render_levels": 2, "subdivision_type": "CATMULL_CLARK"}}
```

Cambios de pila emiten `modifiers.changed`. Cambios de H emiten `visibility.changed`.
Todos los comandos de pila responden `{object, modifiers}`; `modifier.add` incluye
además `modifier`, el nombre real asignado por Blender. La identidad estable es siempre
el par `(object, name)`, nunca un índice ni un nombre global. `modifier.add_options`
describe cada parámetro con `type`, `default` y, según corresponda, `min/max/step`,
`values` o `object_filter`. `unsupported_type` se usa para tipos no compatibles.

La feature `modifiers` versión 3 incorpora `label`, `read_only`, `max_parameter`
y `type:"action"`. Android excluye acciones y campos de solo lectura de los
defaults enviados al crear. `max_parameter:"total_levels"` limita los selectores
Multires a los niveles nativos existentes. La acción Subdividir envía
`modifier.set {name,parameters:{subdivide:true}}`, crea un nivel y actualiza Vista
y Escultura. Se admiten hasta seis niveles; sus cambios usan un undo por operación.
El panel Object y `sculpt.multires` comparten la operación nativa. Dyntopo y
Multires siguen siendo excluyentes y los demás modificadores se conservan.

El estado completo contiene `hidden_objects:[{name,type}]`, enumerado desde el view
layer, y `active.modifiers[]`. `visibility.changed` lleva exactamente
`{hidden_objects}`. Hide/reveal responden además con `hidden_objects`,
`selected_objects` y `active_object`. Ambos son exclusivos de Object Mode.

## Estado real de esta entrega

Listo: contrato v2 y fixtures, contexto semántico a 10 Hz, sesiones propietarias,
Move/Rotate/Scale modales en Object/Edit, previews paramétricos de Extrude/Bevel/Inset/
Subdivide, selección SET/ADD/REMOVE/TOGGLE con elementos ocultos excluidos, proyección
PERSP/ORTHO real y captura OFFSCREEN predeterminada.

El snap geométrico usa primero el raycast visible, devuelve un identificador estable
durante la escena y conserva el candidato bloqueado hasta confirmar o cancelar. Box,
Circle, Loop y Ring forman parte del contrato estable. GPUOffScreen conserva la cámara
independiente y se ha validado con Blender cubierto, en otro escritorio y minimizado
en X11/KDE. No se captura el framebuffer de la ventana ni la interfaz nativa del PC.

Todos menos `confirm`/`cancel` devuelven el estado de la sesión:

```json
{"active": true, "mode": "MOVE", "axes": ["X"], "snap": true, "step": 0.01,
 "values": [1.23, 0.0, 0.0], "angle": 0.0, "objects": ["Cube"]}
```

`values` va en metros (MOVE) o en factor (SCALE); `angle` **siempre en grados**, que
es lo que se enseña. `step` viaja en unidades de Blender: metros y radianes.

El mismo estado se difunde como evento `transform.session` a 10 Hz mientras hay una
sesión abierta. Ese es el marcador que se lee al arrastrar: responder a cada gesto
saturaría el canal de vuelta, que es justo lo que evita que los gestos lleven id.

Con una sesión abierta, los gestos `move`/`rotate`/`scale` la alimentan en vez de
transformar directamente, y **la fase `end` ya no cierra el paso de undo**. El modo lo
manda `transform.begin`, no el nombre del gesto.

Recalcular siempre desde las matrices guardadas en `begin` (en vez de acumular sobre
lo ya aplicado) es lo que hace que el snap y la entrada numérica salgan exactos y que
cambiar de eje no deje residuo del anterior.

Solo Object Mode: en Edit responde `wrong_mode`.

### Añadir objetos

`object.add` con `primitive` es el menú Add de Blender: mallas, curvas, superficies,
metaballs, texto, vacíos, luces y cámara. `object.add_options` devuelve el catálogo
completo agrupado por categoría (`{categories: {MESH: [...], CURVE: [...]}}`); el enum
`AddObject` del cliente Android es un espejo de esas claves y ambos lados deben
mantenerse alineados al ampliar el catálogo.

**Sin `x`/`y`/`z` explícitos se añade en el cursor 3D**, como Blender. Con ellos manda
el payload.

En Edit Mode solo se admiten mallas (se fusionan con la que se edita); el resto
responde `wrong_mode`, porque crearía un objeto nuevo.

### Cursor 3D y origen

Equivalente al menú Shift+S de Blender. Los `snap.cursor_*` devuelven
`{cursor: [x, y, z]}`; los que mueven objetos devuelven un snapshot del estado.

| Comando | Payload |
|---|---|
| `snap.info` | — devuelve `cursor` y `rotation` |
| `snap.cursor_set` | `x`, `y`, `z` (o `vector`) |
| `snap.cursor_to_world` | — |
| `snap.cursor_to_selected` | — |
| `snap.cursor_to_active` | — |
| `snap.cursor_to_grid` | `step` (def. 1.0) |
| `snap.selected_to_cursor` | `keep_offset` (bool), `objects[]` |
| `snap.selected_to_grid` | `step`, `objects[]` |
| `snap.origin_to_cursor` | — |
| `snap.origin_to_geometry` | `center`: `MEDIAN`\|`BOUNDS` |
| `snap.origin_to_center_of_mass` | — |

El cliente los agrupa en tres submenús (`SnapGroup`): cursor, snap de selección y
establecer origen.

`snap.cursor_to_selected` mira el modo: en Edit Mode usa la mediana de los vértices
seleccionados, en Object Mode la de los orígenes. Los que mueven objetos u orígenes
exigen Object Mode y responden `wrong_mode` en Edit.

### Archivo

| Comando | Payload |
|---|---|
| `file.info` | — |
| `file.new` | `empty` (bool): escena vacía en vez del archivo de inicio |
| `file.open` | `path` |
| `file.save` | — falla con `no_path` si nunca se ha guardado |
| `file.save_as` | `folder`, `name`; por compatibilidad también `path` completo |
| `file.recent` | `limit` (1..50, def. 12) |
| `file.locations` | — |
| `file.browse` | `path` (opcional; por defecto la carpeta configurada) |
| `file.default_folder` | `path` |

`file.info` y las operaciones que terminan bien devuelven
`{name, path, saved, dirty}`. `saved: false` significa "nunca se ha guardado", así que
el cliente debe pedir nombre y usar `file.save_as` en vez de `file.save`.

`file.recent` devuelve `{files: [{name, path, folder, exists}]}` leyendo el
`recent-files.txt` de Blender. `exists: false` marca un reciente que se movió o borró:
se manda igual para poder enseñarlo en gris en vez de fallar al abrirlo.

`file.locations` devuelve `{default_folder, locations: [{id, label, path}]}`. Siempre
incluye `DEFAULT`, `HOME` y `ROOT`, y añade los volúmenes montados que el sistema pueda
enumerar sin error. Los paths son canónicos y los lugares duplicados se eliminan.

`file.browse` devuelve
`{path, parent, breadcrumbs: [{name, path}], default_folder, entries: [{name, path, type}]}`.
Los breadcrumbs los construye el servidor: Android trata cada `path` como token opaco
y no intenta separar rutas POSIX o Windows. `type` es
`DIRECTORY` o `BLEND`; no se exponen otros ficheros. Las carpetas se ordenan antes que
los `.blend`, ambas sin distinguir mayúsculas. No se sigue una búsqueda recursiva: el
cliente navega una carpeta por petición, evitando bloquear el hilo principal en árboles
o unidades de red grandes.

En `file.browse`, `file.open`, `file.save_as` y `file.default_folder`, una ruta relativa
se resuelve contra la carpeta predeterminada. También se aceptan los aliases
`@default`, `@home` y `@root`, solos o seguidos de `/...`; el backend los traduce y
siempre responde con rutas absolutas. La carpeta predeterminada se guarda en la
configuración propia del add-on y sobrevive a reinicios de Blender. Si aún no se ha
configurado usa el directorio del `.blend` abierto y, si no existe, el home del usuario.

Para guardar desde el explorador, el cliente debe enviar
`file.save_as {folder: <path opaco devuelto por el backend>, name: "escena"}`. El
backend une ambos componentes y añade `.blend` si falta; Android no concatena rutas.
`name` debe ser un basename no vacío: `.`, `..`, NUL y separadores `/` o `\\` responden
`bad_payload`. Enviar simultáneamente `path` y `folder`/`name` también es inválido. El
payload histórico `{path}` sigue admitido para clientes anteriores.

Errores de archivo estables: `not_found`, `not_directory`, `not_blend`,
`access_denied`, `io_error` y `bad_payload`. `file.open` solo admite ficheros `.blend`; guardar añade
la extensión como antes. El explorador no es un sandbox: un usuario autenticado puede
navegar y guardar en cualquier carpeta a la que el proceso de Blender tenga acceso.

Cargar un `.blend` **no corta la sesión**: el timer del puente está registrado con
`persistent=True` y la captura de vídeo resuelve el viewport en cada fotograma en vez
de cachearlo. Lo que sí se reinicia es el estado interno del add-on (cámara, gestos y
watcher), que apuntaba a datos del archivo anterior.

---

## 6. Gestos (alta frecuencia)

Un arrastre genera cientos de eventos por segundo. **No los mandes como comandos.**
Usa mensajes `gesture`, que el servidor agrupa (coalescing) y aplica una sola vez por
tick del hilo principal:

```json
{"type": "gesture", "gesture": "orbit", "phase": "begin"}
{"type": "gesture", "gesture": "orbit", "phase": "update", "dx": 0.02, "dy": -0.03}
{"type": "gesture", "gesture": "orbit", "phase": "update", "dx": 0.01, "dy": -0.01}
{"type": "gesture", "gesture": "orbit", "phase": "end"}
```

- `gesture`: `orbit`, `pan`, `zoom`, `move`, `rotate`, `scale`.
- `phase`: `begin`, `update`, `end`, `cancel`.
- Campos: `dx`, `dy` (se **suman**), `factor` (se **multiplica**, para `zoom` y `scale`).
- Opciones fijadas en el `begin`: `space`, `pivot`, `axis` (`"X"|"Y"|"Z"` para restringir).

Los `update` **no reciben respuesta** — es intencionado, evita el tráfico de vuelta.
Solo se responde si el mensaje es inválido. Si necesitas confirmar el resultado, pide
`scene.get_state` tras el `end`.

Los gestos de transformación (`move`, `rotate`, `scale`) generan **un único paso de
undo** al recibir el `end`. Un `cancel` descarta lo pendiente sin cerrar el paso.

Un `update` sin `begin` previo abre sesión implícita: si la tablet se reconecta a mitad
de un arrastre, no se pierde.

`move` traduce el arrastre al plano de la vista actual (derecha/arriba de la cámara),
que es lo que espera el dedo. `rotate` gira alrededor del eje de visión.

---

## 7. Eventos del servidor

Sin `id`, llegan cuando Blender cambia (por la tablet **o por el teclado del PC**).
Se muestrean a 10 Hz.

```json
{"type": "event", "event": "selection.changed", "payload": {"objects": ["Cube"], "object": "Cube"}}
```

| Evento | Payload |
|---|---|
| `scene.changed` | estado completo (al conectar) u `{object_count}` |
| `selection.changed` | `{objects: [], object}` |
| `active_object.changed` | `{object}` |
| `mode.changed` | `{mode}` |
| `selection_mode.changed` | `{selection_mode}` |

## 8. Otros mensajes

`{"type": "ping", "id": "x"}` → `{"type": "pong", "id": "x"}` (a nivel de aplicación,
independiente del ping del propio WebSocket; útil para medir latencia).

---

## 9. Notas para el cliente Android

- Manda `id` en todo comando y resuelve las respuestas por `id`: los eventos pueden
  colarse entre tu petición y tu respuesta.
- Trata `hello` como señal de "conectado"; no pintes la UI como conectada solo porque el
  socket abrió.
- El estado de la UI (modo, vertex/edge/face, objeto activo) debe venir de los **eventos**,
  no de suponer que tu comando funcionó: el usuario puede tocar el PC a la vez.
- Un `response` con `ok: false` no es motivo para desconectar. `auth_failed` sí.

---

## 10. Restricciones y valores exactos

Para mover por un eje se usa el gesto normal con `axis`, que el servidor lee en la
fase `begin`:

```json
{"type": "gesture", "gesture": "move", "phase": "begin", "axis": "X"}
```

Para valores exactos, `transform.move` / `rotate` / `scale` aceptan `absolute: true`,
que asigna en vez de sumar. `rotate` espera **radianes**.

---

## 11. Vídeo del viewport (H.264 preferido, MJPEG fallback)

Canal aparte del WebSocket, en su propio puerto (8766 por defecto). Va separado a
propósito: un fotograma perdido no debe retrasar un comando, ni al revés.

| Ruta | Qué devuelve |
|---|---|
| `/stream.h264` | access units H.264 Annex B en framing binario `btr-h264-v1` |
| `/stream.mjpg` | `multipart/x-mixed-replace; boundary=btrframe`, el flujo continuo |
| `/frame.jpg` | un único fotograma, para depurar con `curl` |
| `/stats.json` | métricas de captura y codificación |
| `/` | página de prueba: abre esto en el navegador del PC para verificar el vídeo sin la tablet |

Si hay token, va en la query: `http://10.0.0.8:8766/stream.mjpg?token=SECRETO`.

La tubería privada de ffmpeg utiliza paquetes FLV con longitud explícita para
publicar cada fotograma H.264 completo sin esperar al AUD del siguiente. El lector
convierte los NAL a Annex B y conserva SPS/PPS en cada keyframe; metadatos y
configuración no consumen timestamps de captura. FLV no se transmite a Android.
Los NAL se localizan con búsquedas nativas de bytes, sin recorridos Python por byte.
La espera del pump se acota por
el próximo vencimiento de captura, descontando el tiempo de dibujo ya consumido.
Sin espectadores se conserva la cadencia de control. Estas optimizaciones no
cambian resolución, calidad, códec ni el framing de red.

### Framing H.264 `btr-h264-v1`

La respuesta es `application/x-btr-h264`, sin muxer. Cada registro contiene una
access unit completa de un fotograma, lista para encolarla en
Android `MediaCodec`. Todos los enteros son big-endian:

| Offset | Tamaño | Campo |
|---:|---:|---|
| 0 | 4 | magic ASCII `BTRH` |
| 4 | 1 | versión (`1`) |
| 5 | 1 | flags: bit 0 `CONFIG`, bit 1 `KEYFRAME` |
| 6 | 2 | tamaño de cabecera (`32`) |
| 8 | 4 | secuencia unsigned |
| 12 | 8 | timestamp de captura, microsegundos Unix |
| 20 | 4 | bytes de payload |
| 24 | 4 | anchura |
| 28 | 4 | altura |
| 32 | N | access unit H.264 Annex B (start codes incluidos) |

El encoder usa baseline, cero B-frames/lookahead, AUD y un GOP corto de 4–6 frames,
repitiendo SPS/PPS en cada IDR. `CONFIG` indica que el payload contiene SPS/PPS;
`KEYFRAME`, un IDR. Si el emisor descarta AUs por backpressure, no entrega más deltas
y espera al siguiente registro `CONFIG|KEYFRAME` (como máximo un GOP).
Tras conectar, el servidor espera el próximo keyframe: nunca empieza por un delta
indecodificable. Ante backpressure salta al access unit más reciente; no acumula cola.

Cada parte del multipart lleva dos cabeceras propias además de `Content-Length`:

```
--btrframe
Content-Type: image/jpeg
Content-Length: 27094
X-Timestamp: 1787416962.539
X-Frame: 45
```

`X-Timestamp` es el reloj del PC al capturar. Como no está sincronizado con el de la
tablet, **no sirve como latencia absoluta**; el cliente resta el mínimo desfase
observado para estimar cuánto se degrada respecto al mejor caso.

Fíate de `Content-Length` para trocear el flujo: un JPEG puede contener la secuencia
del separador por casualidad.

Ajustes en caliente con `stream.configure` (`enabled`, `fps`, `max_width`, `quality`),
que devuelve el mismo bloque que `stream.info`.

### Rendimiento y por qué está montado así

El servidor solo captura si hay alguien mirando. La captura GPU ocurre en el hilo
principal de Blender (~14 ms) y **la compresión no**: se delega a un `ffmpeg` externo.
Comprimir dentro de Blender, escribiendo en un datablock `bpy.data.images`, hunde su
bucle de eventos de ~48 Hz a 1 Hz, lo que además dejaría los comandos con un segundo
de retraso. Medido en `streaming/encoder.py`.

Referencia con la implementación actual, a 1280×754: **19 fps, 27 KB/frame, 4,1 Mbit/s**,
con Blender a 53 Hz.

MJPEG permanece como fallback. H.264/libx264 es la ruta preferida por su menor ancho
de banda y configuración de latencia interactiva.

## CAD paramétrico — versión 1 extendida: sketch y vaciado

`features.cad` anuncia `version:1`, `planes:[XY,XZ,YZ]`,
`entities:[LINE,RECTANGLE,SQUARE,CIRCLE,ARC]`, `features:[EXTRUDE,CUT]`,
`sketch_editing:true`, `fillet:true`, `length_unit:METERS` y `constraints` con
`COINCIDENT,HORIZONTAL,VERTICAL,PARALLEL,PERPENDICULAR,TANGENT,EQUAL,DISTANCE,RADIUS,FIX,MIDPOINT,SYMMETRIC`.
También anuncia `construction`, `datum_planes`, `bodies`, `origin`, `mesh_copy`,
`smart_cursor`, `selection_delete`, `editable_dimensions` y `fillet_remove`.
Las extensiones se negocian por capabilities; se instala el APK junto con el ZIP.
`mode.set {mode:CAD}` activa el espacio CAD (Blender permanece en Object).
OBJECT/EDIT salen de CAD y cancelan cualquier preview. Los objetos evaluados CAD
requieren `cad.convert` antes de Edit. El documento JSON versionado vive en la
escena del `.blend`; sus identificadores no dependen de índices de malla.

Todos los comandos `cad.*` devuelven el estado completo; `cad.state` también es
un evento emitido al cambiar documento, sesión o proyección de la cámara:

```json
{"version":1,"workspace":true,"document":{"version":1,"revision":3,"id":"doc_uuid","sketches":[{"id":"sketch_uuid","name":"Sketch 1","plane":"XY","entities":[{"id":"entity_uuid","type":"RECTANGLE","x":0,"y":0,"width":0.08,"height":0.045}],"profiles":[{"id":"profile_entity_uuid","entity_id":"entity_uuid","label":"Rectángulo"}]}],"features":[]},"active_sketch_id":"sketch_uuid","selection":{"kind":"ENTITY","id":"entity_uuid"},"session":{"active":false,"id":null,"operation":null,"depth":null,"can_confirm":false},"overlay":[{"id":"entity_uuid","points":[[0.4,0.4],[0.6,0.4],[0.6,0.6],[0.4,0.6]],"closed":true,"selected":true}],"error":null}
```

Las longitudes CAD son **metros**, independientes de `scene.scale_length`.
Android convierte únicamente la representación mm/cm/m. LINE contiene
`x,y,x2,y2`; RECTANGLE `x,y,width,height` (esquina mínima); CIRCLE `x,y,diameter`
(centro); ARC `x,y,radius,start,sweep` (centro, radio y ángulos en grados).
SQUARE es una intención de creación: persiste RECTANGLE con igualdad entre lados.
El sketch guarda `offset` en metros y opcionalmente `support_id` de una feature;
el soporte actualiza el plano/offset desde su cara superior. Las coordenadas están
en el plano local del sketch. La normal positiva
es +Z para XY, −Y para XZ y +X para YZ.

| Comando | Payload | Efecto |
| --- | --- | --- |
| `cad.state` | `{}` | Consulta documento y preview |
| `cad.sketch.create` | `{plane:"XY",offset?,body_id?}` o `{support_id}`, `{plane_id}`, `{reference_sketch_id}` | Crea y activa boceto; reutiliza planos sin duplicar geometría |
| `cad.sketch.activate` | `{sketch_id}` | Edita sketch existente, encuadra su plano |
| `cad.sketch.finish` | `{}` | Sale del dibujo conservando perfiles seleccionables |
| `cad.select` | `{kind:"ENTITY\|PROFILE\|FEATURE",id,part?,additive?}` o `{u,v,additive?}` | Selección de puntos/aristas o perfiles; aditiva alterna pertenencia |
| `cad.entity.begin` | `{type:"LINE\|RECTANGLE\|SQUARE\|CIRCLE\|ARC",u,v}` | Inicia dibujo reversible |
| `cad.entity.update` | `{u,v}` | Actualiza extremo desde baseline |
| `cad.entity.set` | `{entity_id,values:{width?,height?,diameter?,radius?,start?,sweep?,length?,x?,y?,x2?,y2?}}` | Edita dimensiones y reconstruye dependientes |
| `cad.entity.delete` | `{entity_id}` o `{}` | Borra una figura completa o la selección de puntos/aristas/figuras en un undo; protege perfiles usados |
| `cad.extrude.begin` | `{profile_id,depth,operation:"EXTRUDE\|CUT",target_id?}` | Preview aditiva o sustractiva; CUT exige destino |
| `cad.extrude.update` | `{depth}` o `{gesture,baseline_depth}` | Cota exacta o delta vertical desde inicio del gesto, positivo hacia arriba |
| `cad.session.confirm` | `{}` | Confirma candidato estable, un undo |
| `cad.session.cancel` | `{}` | Restaura documento y geometría originales |
| `cad.feature.set` | `{feature_id,depth?,enabled?}` | Edita o suprime feature |
| `cad.feature.delete` | `{feature_id}` | Borra feature y resultado |
| `cad.convert` | `{feature_id}` | Crea una copia de malla seleccionada y sale a Object; conserva documento y operaciones, incluidos dependientes |
| `cad.settings` | `{step?,increment?,construction?,show_scene?}` | Paso métrico positivo y snap, sin undo ni cambio geométrico |
| `cad.drag.begin` | `{u,v}` | Sondea y conserva selección previa; prepara arrastre del grupo si cubre el elemento, sin cambiar selección todavía |
| `cad.drag.update` | `{u,v}` | Reconstruye y resuelve restricciones desde baseline |
| `cad.drag.end` | `{}` | Sin UPDATE alterna el elemento sondeado en BEGIN; con arrastre confirma el último candidato. Nunca vuelve a sondear |
| `cad.select_all` | `{action:"SELECT\|DESELECT"}` | Selecciona todas las figuras del boceto (también construcción, nunca origen) o limpia la selección, sin undo |
| `cad.constraint.add` | `{type,value?,refs?}` | Restringe selección o referencias explícitas del boceto activo; una cota equivalente se actualiza conservando ID |
| `cad.constraint.set` | `{constraint_id,value,sketch_id?}` | Cambia la cota canónica y resuelve dependientes; Radio de redondeo ajusta su contacto |
| `cad.constraint.delete` | `{constraint_id,sketch_id?}` | Elimina una restricción del sketch activo |
| `cad.fillet` | `{radius}` | Redondea dos líneas conectadas, una esquina de rectángulo o dos lados contiguos; conserva restricciones y operaciones dependientes |
| `cad.fillet.remove` | `{entity_id}` | Quita un redondeo, extiende los lados hasta la esquina y remapea el perfil usado por sólidos, con un undo |
| `cad.sketch.delete` | `{sketch_id}` | Elimina un boceto sin operaciones dependientes |
| `cad.sketch.visibility` | `{sketch_id,visible}` | Muestra/oculta el overlay; el boceto activo siempre se ve |
| `cad.entity.construction` | `{construction}` | Cambia las figuras seleccionadas a auxiliares o perfiles; rechaza romper una operación dependiente |
| `cad.body.create` | `{}` | Crea y activa otro cuerpo independiente |
| `cad.body.activate` | `{body_id}` | Elige el cuerpo de los nuevos bocetos, sin undo |
| `cad.plane.create` | `{base?,translation?,rotation?,reference_sketch_id?,support_id?}` o `{u,v}` | Plano persistente; posición en metros y ángulos locales XYZ en grados; un toque usa una cara plana visible |
| `cad.plane.set` | `{plane_id,translation?,rotation?}` | Ajusta el plano y reconstruye bocetos/sólidos dependientes |


`selection.items` contiene `{kind,id,part}`; `selection.kind/id/part` conserva el
último elemento para el inspector. Roles: LINE START/END/BODY; RECTANGLE P0..P3 y
EDGE0..EDGE3/BODY; CIRCLE CENTER/RIM/BODY; ARC CENTER/START/END/BODY. El sondeo da
prioridad a puntos dentro de su radio, corrige el aspecto y luego prueba aristas.
`overlay[].handles` contiene `{part,point:[u,v],selected}`; `selected_parts` enumera
los roles seleccionados. Los perfiles de cadenas usan IDs derivados de sus miembros,
nunca de índices evaluados. La línea adquiere extremos mediante la política común
de `commands/snap.py` y guarda restricciones COINCIDENT al confirmar.

El cursor CAD único envía BEGIN al bajar y UPDATE solo al superar el umbral táctil.
La primera muestra que cruza el umbral se envía inmediatamente; las siguientes
respetan la cadencia de entrada. Un arrastre limitado por restricciones sigue siendo
arrastre aunque no produzca geometría nueva: END no lo convierte en deselección.
Un toque vacío limpia la selección; arrastrar vacío la conserva. Cancelar o navegar
con dos dedos restaura también la selección anterior. Una referencia BODY cubre
los puntos/lados de su figura al adquirir el grupo; un lado cubre sus extremos.
`cad.select` aditivo desde el árbol usa la misma política de alternar pertenencia.

Borrar un lado de rectángulo conserva los lados restantes como líneas con sus
referencias y restricciones válidas. Una esquina retira sus dos lados incidentes.
En líneas, arcos y círculos no se persisten primitivas sin sus puntos definitorios:
el borrado de un punto retira su primitiva. Se limpian solo las restricciones que
pierden alguna referencia. Un perfil de una operación no puede quedar abierto o
inexistente: se rechaza la transacción (`cad_dependency`) sin borrar dependientes.

Las entidades públicas anuncian `dimensions:[{field,label,constraint_type,
value_factor,refs:[{id,part}],constraint_ids:[]}]`, `is_square` e `is_fillet`.
`constraint_ids` vacío significa medida libre; si tiene IDs, editar el campo
mediante `cad.entity.set` actualiza esa cota en lugar de imponer un valor paralelo.
Diámetro usa `value_factor:0.5` para su restricción RADIUS; los demás usan 1.
LINE publica `length` derivada y admite editarla. El cuadrado solo anuncia Lado.
Coordenadas y ángulos siguen siendo parámetros geométricos; FIX continúa imponiendo
su bloqueo, no se desactiva implícitamente al editar una cota.

`dimension_options:{DISTANCE?:{value,constraint_id?},RADIUS?:{value,constraint_id?}}`
describe las cotas disponibles para la selección con su medida actual. Android
abre la existente si tiene ID. Se normalizan lados opuestos de rectángulos,
mediciones equivalentes por extremos y cantidades enlazadas por EQUAL. Los
duplicados antiguos tienen un solo control público y se fusionan en almacenamiento
al editar/eliminar. No se anuncia detección general de redundancia algebraica.

Los redondeos se reconocen por sus coincidencias y tangencias con dos líneas, sin
requerir metadatos nuevos en archivos anteriores. Radio y el campo numérico usan
la misma cota; eliminar RADIUS libera la medida sin quitar el arco. Quitar el
redondeo es la operación explícita `cad.fillet.remove`, que conserva las otras
reglas y las dependencias. DISTANCE de un lado y EQUAL de longitudes se evalúan
hasta las esquinas virtuales cuando el lado participa en un redondeo. El sondeo,
el trazo visible y las distancias entre puntos explícitos siguen usando los puntos
reales; no se persisten coordenadas de pantalla ni referencias RNA.

Cada sketch contiene `constraints:[{id,type,refs:[{id,part}],value?,values?}]`.
FIX guarda `points:{rol:[x,y]}` para los puntos/los extremos de una arista,
y `values` únicamente al seleccionar la figura completa. Una selección múltiple
crea una fijación por referencia dentro de un único undo. El origen reservado
`{id:"ORIGIN",part:"POINT"}` existe en cada boceto, es siempre (0,0) y nunca es un
parámetro del solver. MIDPOINT recibe punto + lado (en cualquier orden al crear);
SYMMETRIC recibe tres puntos, con el centro en último lugar. COINCIDENT admite el
origen. La construcción participa en las restricciones y queda fuera de perfiles.
`overlay` anuncia `construction` para líneas discontinuas y `label`, `label_point`,
`label_offset` para cotas/etiquetas; las entradas `kind:DIMENSION` no son seleccionables.
Las medidas del overlay usan la unidad de escena. El panel Android filtra por IDs
y roles compartidos con la selección, incluidos extremos de aristas.
El solver admite 300 parámetros y resuelve el conjunto completo; una cota escrita
es exacta y el arrastre proyecta el objetivo sobre la libertad permitida. Los
conflictos devuelven `cad_constraint_conflict`, sin cambiar la escena persistente.
No se anuncia un conteo de grados de libertad de un solver general.

`step` e `increment` pertenecen al estado CAD, separados del documento. Un gesto
recorre `gesture / 0.04 * step`; Incremento lo redondea a pasos enteros. La
profundidad permanece positiva (mínimo 1e-7 m). CUT extruye en dirección negativa
desde el plano del sketch y resta su volumen de `target_id`; al evaluar oculta el
resultado previo consumido. No admite borrar soportes con dependientes; crear una copia de malla sí los conserva.
La preview CUT anuncia `session.transparent:true`; solo la captura GPU usa rayos X
al 35 %, restaurando el sombreado inmediatamente incluso si falla el render.

Los comandos de dimensión y feature son transacciones discretas con un undo. Una
sesión conserva propietario; desconexión, undo/redo, cambio de archivo, cambio de
modo o nueva transformación descartan su preview. Confirmar nunca repite raycast.
La selección de un perfil exterior extruye su región con contornos interiores
como huecos. Contornos abiertos no se pueden extruir; intersecciones/tangencias y
valores no finitos o degenerados producen errores explícitos sin perder la última
geometría válida. El kernel V1 genera malla nativa; no anuncia STEP, BREP ni solver
general. Rectángulos conservan lados horizontales/verticales y círculos diámetro.
La malla materializada tiene quads: perímetro ordenado para extrusiones simples;
para huecos/booleanos, parches convexos con centros y puntos medios compartidos.
Se conserva la frontera sin grietas y los parches cóncavos se descomponen antes.
Esta malla de presentación/exportación no es el operando de las operaciones
siguientes, que usan la evaluación compacta del kernel para evitar crecimiento
exponencial al encadenar vaciados.

`document.revision` aumenta con cada transacción confirmada y vuelve al valor
correspondiente al usar undo/redo. `session.depth` describe la preview de EXTRUDE/CUT y
`session.can_confirm` exige un candidato no degenerado. Una cadena cerrada de
líneas/arcos no ramificada forma un perfil; las redes cruzadas no se subdividen
en regiones implícitas. Los vaciados sin intersección o que eliminan todo el
sólido se rechazan conservando el último resultado válido.

CAD V1 aísla temporalmente la vista usando `hide_set`, como `view.local`, con su
propio conjunto de objetos restaurables. `isolated:true` lo anuncia a Android.
Solo oculta objetos ajenos que estaban visibles, conserva los previamente ocultos
y no altera el registro del aislamiento Object. Salir de CAD, desconectar su
propietario o detener el servidor restaura la visibilidad. Guardar y los puntos de
undo registran la visibilidad original; al terminar se reaplica la vista CAD. Los
handlers de guardado cubren también Guardar desde Blender. Convertir a malla sale
de CAD y deja seleccionada una copia con datos propios. El original conserva su
protección CAD y el árbol no pierde ninguna operación. `show_scene:true` permite
ver referencias ajenas durante la elección de planos sin borrar sus flags previos.

`document.planes` contiene `{id,name,base,translation:[x,y,z],rotation:[rx,ry,rz]}`
con referencia opcional a `reference_sketch_id`, `support_id` o `face_frame`.
La evaluación produce una base ortonormal `{origin,x,y,normal}` en metros.
Un boceto con `plane_id` sigue ese plano; los planos relativos a otro boceto o a
una cara superior siguen a su soporte. Una cara elegida por toque guarda su marco
en ese instante, sin persistir índices de polígonos ni prometer seguimiento de
cambios topológicos posteriores. Se rechazan ciclos de referencias.
`document.bodies` contiene `{id,name}`; bocetos y operaciones llevan `body_id`.
Los documentos anteriores se normalizan a un cuerpo inicial al leerlos.
`active_body_id`, `construction` y `show_scene` son estado del workspace.

Mientras `active_sketch_id` esté activo, la cámara remota permanece ortogonal al
boceto: orbit se traduce a pan, roll/vistas de eje no cambian orientación y la
perspectiva permanece ORTHO. Zoom/pan siguen funcionando y no escriben en `rv3d`.

Al entrar en CAD con un documento existente se encuadra su sketch activo válido
o el primero, sin activar la edición. Repetir CAD mientras ya está abierto conserva
la vista. Solo cambia la cámara remota; `rv3d` permanece intacto.

## Escultura y presión del lápiz

`mode.set {mode:"SCULPT"}` activa Sculpt nativo sobre la malla activa. Los resultados
CAD requieren conversión explícita a malla. El estado completo incluye `sculpt`;
el cliente habilita la entrada al modo solo cuando `sculpt.available` es verdadero.
Requiere una ventana 3D y Blender 4.4 o posterior; la validación de esta entrega
se realiza en Blender 5.2.1. No hay escultura simulada en background.

```json
{"sculpt":{"available":true,"active":true,"brush":"DRAW","radius":0.04,"strength":0.5,"pressure_strength":true,"pressure_size":false,"symmetry":{"x":true,"y":false,"z":false},"dyntopo":{"enabled":false,"detail":12},"multires":{"name":"","level":0,"total_levels":0},"brushes":[{"id":"DRAW","label":"Dibujar","icon":"DRAW"}]}}
```

El catálogo incluye DRAW, CLAY, INFLATE, CREASE, FLATTEN, GRAB, SMOOTH, MASK y PINCH.
Android usa sus IDs, etiquetas e intención de icono. `radius` es una fracción de
la **altura del vídeo**, no píxeles de la tablet ni unidades de la escena.
`sculpt.radius_meters` añade el radio aproximado en metros sobre el plano del pivote;
puede ser null sin viewport. Android lo muestra con `≈` en la unidad de trabajo y
conserva `radius` como parámetro de tamaño en pantalla. No se trata de una cota exacta
sobre todas las profundidades de una superficie perspectiva.
El pincel nativo calcula el radio desde píxeles (`use_locked_size:VIEW`), evitando
el mínimo de 0,001 unidades de `unprojected_size`. La adaptación temporal del
objeto a la vista nativa incluye su profundidad/escala de proyección y restaura
su matriz al salir; no reescala la malla persistente ni escribe en `rv3d`.

| Comando | Payload | Resultado |
|---|---|---|
| `sculpt.settings` | `{brush?,radius?,strength?,pressure_strength?,pressure_size?,symmetry?:{x?,y?,z?}}` | Ajustes parciales; radio 0.002–0.3, fuerza 0–1 |
| `sculpt.stroke` | `{phase,stroke_id,points?,smooth?,invert?}` | Preview nativa o cierre del trazo identificado |
| `sculpt.dyntopo` | `{enabled?,detail?}` | Dyntopo nativo, detalle relativo entre 1 y 40 px |
| `sculpt.multires` | `{action:"add\|subdivide\|level",level?}` | Crear con un nivel, subdividir o elegir nivel existente |
| `sculpt.mask` | `{action:"clear\|invert"}` | Limpiar o invertir máscara nativa |

Todos devuelven `result.sculpt`. `mode.set` también lo devuelve al entrar y Android
lo aplica inmediatamente, sin depender de un refresco de escena posterior.
Multires y Dyntopo son excluyentes: se rechaza la operación incompatible sin
eliminar el otro sistema. Multires permite hasta seis niveles desde la tablet.

Cada `points` contiene como máximo 128 muestras `{u,v,pressure,time}`. `u/v` se
normalizan al rectángulo del vídeo, con origen arriba a la izquierda; `pressure`
está entre 0 y 1 y `time` son segundos desde el inicio. Android conserva las
muestras históricas de MotionEvent, incluida su presión; un cero no se sustituye
por fuerza máxima. Para dedo, cuyo valor no representa fuerza física del lápiz,
se utiliza presión 1. El backend limita cada trazo a 4096 muestras de superficie.
En los pinceles por aplicaciones, estas muestras se convierten a aplicaciones
separadas por el espaciado nativo del pincel. Se integra el recorrido entre paquetes,
se corrige el aspecto de pantalla y se interpola la presión. El extremo provisional
solo pertenece a la preview actual; no se añade otra aplicación permanente por cada
UPDATE. Grab conserva su recorrido completo. Una primera muestra de presión cero
no inicia una aplicación: la primera positiva fija el inicio real.
Si otro lote supera ese límite, confirma la última preview aceptada y devuelve
`limit_reached:true` con `message`. Android muestra el aviso, descarta las muestras
pendientes de ese ID y espera a que se levante el lápiz para iniciar otro trazo.

Las fases son `begin/update/end/cancel`. `stroke_id` identifica el trazo y el
servidor asocia su propietario a la conexión, sin confiar en IDs de cliente del
payload. Las fases atrasadas de otro trazo o propietario no lo modifican.
`smooth` e `invert` se fijan al comenzar. `end` confirma lo ya aplicado: ignora
coordenadas de liberación y no repite el sondeo. `cancel` restaura la preview;
desconexión, cambio de intención y guardar también la cierran. Transform, tool,
CAD y escultura comparten exclusión de sesiones.

El backend reconstruye el trazo acumulado mediante el pincel nativo y su undo,
conservando un paso por trazo confirmado. Entrar en Sculpt crea el baseline
nativo de modo que Blender necesita para inicializar su historial. Android
mantiene una única petición de trazo en vuelo, agrupa muestras pendientes y
ordena el cierre antes de navegación u otras operaciones. Un fallo descarta las
muestras pendientes de ese trazo y envía cancelación antes de continuar.

Multires y Dyntopo conservan sus desplazamientos/topología en un respaldo nativo privado
durante el trazo y lo retira al cerrar; el cierre confirmado se consolida en undo
global. Esto evita depender de la compresión asíncrona del undo de grids nativo.
Los materiales existentes se reutilizan. Para esculpir Multires, la malla debe
tener un solo usuario; un duplicado normal crea una copia independiente.

`Solo lápiz` es el valor inicial de Android: un dedo orbita y dos desplazan/zoom.
Puede habilitarse `Lápiz + dedo`. El botón principal del lápiz suaviza durante el
trazo; borrador/botón secundario invierten. Los eventos de cancelación y rechazo
de palma cancelan el trazo; no lo confirman. El círculo local comunica radio y
posición del lápiz; la geometría y la máscara se ven en GPUOffScreen.

Las imágenes de **Referencias** son copias privadas de la tablet y no amplían el
protocolo ni se insertan en el documento CAD o `.blend`. Véanse las guías
[de escultura](../../docs/sculpt-workspace.md) y
[de referencias](../../docs/reference-images.md).

## Materiales y captura de escena (v1)

`features.materials` anuncia `{version:1, recipe_format:"tablet-material",
recipe_version:1, paint:"UV_MASK", mask_size:1024, max_layers:8, max_objects:16}`.
`features.scene_capture` anuncia `{version:1, mime:"image/png", camera:"TABLET",
overlays:false}`. Se añade `MATERIAL` a `enums.mode`; el modo nativo de Blender
continúa siendo Object. El snapshot de escena incluye `material` y anuncia
`mode: "MATERIAL"` durante el workspace.

| Comando | Payload | Resultado |
|---|---|---|
| `mode.set` | `{mode:"MATERIAL"}` | Aísla la selección actual de 1–16 mallas; `{mode,material}` |
| `material.state` | `{}` | `{material: estado}` |
| `material.catalog` | `{}` | `{format,version,presets:[recetas completas]}` |
| `material.import` | `{recipe: receta}` | Guarda/actualiza un preset personalizado en la escena; `{material}`; un undo |
| `material.settings` | Campos opcionales descritos debajo | Configura el siguiente pincel/aplicación; `{material}`; no cambia la base |
| `material.apply` | `{}` | Asigna la receta/color/acabado a todo el grupo; `{material}`; un undo |
| `material.stroke` | `{phase,stroke_id,points}` | `{finished:bool}`; fases `begin/update/end/cancel` |
| `scene.capture` | `{}` | `{mime:"image/png",width,height,png_base64}` |

Estado `material`: `available`, `active`, `targets` (nombres fijados al entrar),
`preset`, `color`, `finish`, `erase`, `radius`, `strength`, `environment`,
`paint_ready`, `presets:[{id,label,color}]`, `finishes:[{id,label}]`,
`environments:[{id,label}]`. Se recibe desde `scene.get_state` y los snapshots
`scene.changed`; las respuestas de `material.stroke` no se interpretan como escenas.

Settings: `preset` (ID del catálogo), `color` (`#RRGGBB` sRGB), `finish`
(`natural/polished/worn`), `erase` (booleano), `radius` (0,005–0,25, fracción de
altura del vídeo), `strength` (0–1), `environment` (`studio/day/warm/soft`). Elegir
preset restaura su color y el acabado Natural. Se validan todos los campos antes
de cambiar el estado. Importar selecciona el nuevo preset y su color.

Cada muestra lleva `{u,v,pressure}` normalizados en `[0,1]`, origen arriba a la izquierda.
Hasta 128 muestras por petición; los campos de tiempo enviados por Android se ignoran
porque el orden ya lo fija el canal. `stroke_id` es un texto de 1–80 caracteres.
`begin` abre un baseline; `update` prolonga el recorrido; `end` no sondea ni pinta
puntos adicionales y confirma lo visible. `cancel`, desconexión, guardado o una
intención incompatible restauran la preview. Un trazo sin cambios no crea undo.

La sesión tiene propietario y no admite mutaciones de otro cliente. Las sesiones
transform/tool/CAD/Sculpt son excluyentes con la pintura. Android reutiliza la cola
ordenada de trazos con una petición en vuelo: recuperarse de un error de
`material.stroke` envía `material.stroke/cancel`, nunca `sculpt.stroke`.

La máscara se proyecta contra las posiciones de la superficie evaluada y la
profundidad de GPUOffScreen con la cámara remota. Workbench proporciona esa
profundidad en una captura auxiliar; Eevee proporciona el color. Los cambios de
sombreado/visibilidad se restauran incluso ante errores. No se escribe `rv3d`.
Las UV privadas no sustituyen las UV del artista. Materiales e imágenes confirmados
son inmutables entre pasos de undo; cada nueva preview usa copias propias. Las
imágenes se empaquetan antes de confirmar. Repetir un material en la capa superior
continúa su máscara; cambiarlo crea otra capa (hasta ocho).

`scene.capture` se ejecuta en el pump, usa la misma cámara y resolución del vídeo,
y devuelve un PNG sin overlays o marcadores adicionales. No necesita consumidores
HTTP ni cambia el transporte activo. Conserva las previews. Android guarda el PNG
mediante su selector de documentos. Una captura dentro de un workspace aislado
incluye ese aislamiento, como la imagen de la tablet.

Especificación replicable, esquema y ejemplos de recetas:
[`docs/material-recipe-v1.md`](../../docs/material-recipe-v1.md).
Guía y límites de pintura: [`docs/material-workspace.md`](../../docs/material-workspace.md).


## Recuperación del workspace tras reconectar

`features.workspace_resume:true` anuncia `server.resume {session_key}`. Android
persiste una clave aleatoria privada (24–80 caracteres alfanuméricos, `_` o `-`)
y la registra después de recibir capabilities en cada conexión autenticada.
El comando devuelve un snapshot de escena y `restored:boolean`.
Al perder el socket se cancelan todas las previews y se restaura la visibilidad,
conservando hasta 16 estados de workspace en memoria. La misma instalación puede
recuperar CAD (boceto, cuerpo, selección confirmada, cámara y ajustes) o Materiales
(objetos y pincel) si sigue siendo la misma escena y ningún workspace ajeno está
activo. Los modos nativos Object/Edit/Sculpt ya sobreviven a la desconexión.
La carga de otro archivo invalida los estados. La clave no sustituye al token de
autenticación ni se guarda en el `.blend`.

En Materiales, `material.settings` conserva tinte y acabado cuando se omiten,
incluso si cambia `preset`. Cada preset del estado anuncia `category:base|detail`.
Óxido, Suciedad y Arañazos son recetas para detalle; el selector configura también
su color explícito y acabado natural en el mismo gesto. Elegirlos no sustituye
la base; únicamente `material.apply` aplica a todo. El cálculo de pintura usa
proyección/visibilidad por trazo y un índice de teselas; el atlas se reutiliza por
identidad de geometría/UV evaluadas, invalidándose tras editar la malla en el PC.
La profundidad se reutiliza con cámara y geometría idénticas; cambia al navegar
o editar, y permanece fija durante el trazo cuya cámara también es fija.
