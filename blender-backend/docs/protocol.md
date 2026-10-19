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
| `scene.scale_set` | Retirado: la escala se elige en `file.new` | error `scene_scale_locked` |
| `server.ping` | `echo` | `{pong: true, echo}` |
| `server.capabilities` | — | versiones, lista de comandos y gestos |

#### Escala de trabajo (`scene_scale`)

Un preset **no reescala geometría**: un cubo de 2 unidades sigue midiendo 2 unidades en
los tres. Lo que cambia es cómo se mide, hasta dónde se ve y con qué paso se trabaja.

| Preset | `length_unit` | `clip_start` | `clip_end` | `snap_step` | `primitive_size` | radio proporcional / paso |
|---|---|---|---|---|---|---|
| `SMALL` | `MILLIMETERS` | 0.0005 | 5 | 0.001 | 0.01 | 0.01 / 0.001 |
| `MEDIUM` | `CENTIMETERS` | 0.01 | 100 | 0.01 | 0.5 | 0.5 / 0.05 |
| `LARGE` | `METERS` | 0.1 | 1000 | 0.1 | 1.0 | 5.0 / 0.5 |

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
crear una escena, `file.new` exige `preset:SMALL|MEDIUM|LARGE` y lo guarda en la
propiedad de escena `btr_scene_scale` del `.blend`. No se puede cambiar con
`scene.scale_set`: responde `scene_scale_locked` sin modificar nada. Abrir un archivo
conserva ese preset; archivos anteriores sin propiedad se interpretan por su unidad
real (mm/cm/m). `scene_scale.scene_id` identifica proceso y escena: Android adopta
los pasos iniciales al cambiar de identidad y conserva ajustes al reconectar a la misma.
CAD también inicia su paso desde el preset. `scene_scale.scale_length` contiene siempre el valor real
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

Sobre un cuerpo CAD, `object.duplicate` crea siempre una copia de malla independiente,
incluido si llega `linked:true`: conserva los modificadores y elimina la propiedad
paramétrica. Comparte la copia con `cad.convert`, deja seleccionado el resultado en
Object y oculta el cuerpo original fuera de CAD para evitar solapes. Al volver a CAD
se muestra temporalmente el original y se oculta la copia. El documento se conserva,
y copiar más ocultar el original forman un único undo. Para objetos ordinarios,
`linked:true` sigue compartiendo la malla como Alt+D.

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
`{"hit": false}` si el rayo no da con nada (y deselecciona si `mode` es `SET`). En Edit
el rayo solo considera la jaula del objeto editado, de modo que otro objeto detrás
cuenta como vacío, y un vacío con `TOGGLE` también deselecciona todo: Android envía
`TOGGLE` en el toque sin modificador para acumular sin Mayús.
`selection.paint` recibe `phase:BEGIN|UPDATE|END|CANCEL`, `stroke_id`, `u0/v0`,
`u1/v1` y `radius` (fracción de ancho del vídeo). Pinta en Object o Edit de mallas/curvas:
invierte cada objeto/elemento una vez por trazo respecto a la selección inicial.
El radio corrige el aspecto, UPDATE barre el segmento y END no vuelve a sondear.
Cancelación/desconexión restaura; confirmar crea un undo si hubo elementos afectados.
La identidad y el propietario descartan eventos atrasados. Devuelve snapshot y `paint_active`.

En Object, mallas sin caras y curvas sin superficie también admiten selección por
proximidad al contorno evaluado, con `threshold` y oclusión mediante el sondeo común.
Respeta visibilidad y bloqueo; no rellena el centro para convertirlo en superficie.
En Edit, el sondeo de malla incluye vértices y aristas sin caras. En curvas retorna
`element:curve`, `control:[spline_index,point_index,POINT|LEFT|RIGHT]` y `location`.
Los puntos y tiradores usan `transform.*` sobre un baseline de curva, sin modificar
la matriz del objeto ni convertir a malla. `transform.select` también continúa entre
controles. Cancelar restaura coordenadas y tipos de tirador; confirmar crea un undo.

En Object también sondea el rectángulo visible de las referencias nativas (Empty
IMAGE), con aspecto de imagen/píxel, offset y transformación. Respeta ocultación,
bloqueo, perspectiva/ortográfica, lados visibles, vista alineada y profundidad
FRONT/DEFAULT/BACK frente a las mallas. Usa la cámara de la tablet, sin geometría
auxiliar; no añade referencias al sondeo de Edit ni cambia el formato de respuesta.

`reference.add` (`reference_images`) copia una imagen del tablero de la tablet a la
escena: `format` png/jpg, `data` en base64 (≤ 6 MB decodificados), `name` y `opacity`
(0–1]. Crea un Empty de imagen como Añadir → Imagen → Referencia, con la imagen
empaquetada en el `.blend`, en el pivote de la cámara de la tablet, mirando hacia ella
y ocupando el 80 % de la altura visible. En Object queda seleccionado y activo; en
otros modos no cambia el objeto activo. Un único undo; responde con el snapshot y
los nombres `reference`/`image`.

`outliner.list` (`outliner.version:1`) devuelve `objects` para toda la escena:
`id`, `name`, `type`, `selected`, `active`, `hidden` (restricción propia), `visible`
(visibilidad efectiva), `locked` (`hide_select`), `in_view_layer`, `editable`,
`parent` y `collections`. `outliner.changed` publica la misma lista cuando cambia.
`outliner.action` recibe `object_id` y `action`: SELECT, RENAME (`name`), VISIBLE
o LOCK (`value` booleano). Las mutaciones usan un undo; SELECT no crea uno.
Bloquear deselecciona el objeto y despeja el activo si es necesario. Desbloquear no
lo selecciona automáticamente. Mostrar conserva el bloqueo y las colecciones.
`outliner.move` recibe `object_id` y `transform` con los ajustes habituales de
Mover (axes, step, snap, snap_type, orientation, value_mode). Valida identidad,
modo, visibilidad y bloqueo; selecciona solo ese objeto y llama al mismo
`transform.begin` con MOVE y el propietario de conexión. Fallar restaura selección;
éxito devuelve `state`, `objects` y `transform` (estado modal). Actualizar, confirmar
y cancelar siguen usando `transform.*`; iniciar no crea undo. Las acciones rechazan
sesiones activas y otros workspaces sin modificar su estado.

Con `outliner.collections:true`, listados, respuestas y `outliner.changed` añaden
`collections`: `id`, `name`, `path`, `root`, `parents`, `count` (objetos directos)
y `editable`. Se incluyen colecciones vacías y la raíz de la escena. Cada objeto
añade `collection_ids` a sus nombres de colección. Los padres múltiples conservan
la misma identidad; `path` es una ruta de presentación, no una dirección de escritura.
La raíz se presenta como `/`; Android dibuja nombres simples en un árbol plegable
derivado de `parents`, con objetos bajo sus colecciones. La búsqueda revela las
ramas coincidentes incluso si estaban plegadas.
`outliner.collection` recibe `action:CREATE`, `name`, `parent_id` opcional (raíz si
se omite) y `object_ids` opcionales para moverlos a la nueva colección; responde
también `created_collection:{id,name}`. `action:MOVE_OBJECTS` recibe `collection_id`
y una lista no vacía de `object_ids`. Primero enlaza el destino y después retira
las pertenencias anteriores de la escena actual, conservando las externas, matrices,
datos y parentesco. Colecciones enlazadas de origen/destino no son editables.
IDs obsoletos se rechazan antes de cualquier cambio. Crear y mover el lote forman
un único undo; mover a la única colección actual no crea undo vacío.
`action:RENAME` recibe `collection_id` y `name` (1–63 bytes UTF-8 tras quitar
espacios externos). Renombra la colección nativa en un undo, conserva identidad y
pertenencias, y devuelve el listado actualizado. Rechaza la raíz, colecciones
enlazadas e IDs obsoletos; repetir el nombre actual no crea undo.

Campos numéricos con `unit:count` aceptan solo enteros. `circle_vertices`, en la
sección Círculo, cambia entre 3 y 4096 vértices de un anillo regular sin caras;
conserva radio/marco y no se ofrece sobre geometría deformada o datos personalizados.
`curve_resolution`, en Curva, expone la resolución nativa con sus límites RNA.
Ambos cambios separan los datos enlazados del activo y crean un solo undo.

`object.properties` (`object_properties.version:1`) recibe `object_id`, `revision`
y `values` con únicamente los campos modificados. `active.properties` publica la
identidad efímera (proceso/escena/objeto), revisión de valores/esquema, nombre,
`fields` (`id`, `label`, `group`, `type:number|bool|enum`, `unit`, `read_only`,
límites y `choices`) y `values`. Las longitudes son metros; la opacidad es 0–1 y
`rotation_x/y/z` son grados (`unit:angle`). La rotación conserva el modo nativo.
Posición es local al padre si existe; dimensiones y tamaño de Empty usan la
semántica nativa de Blender. Las imágenes añaden ortográfica, perspectiva,
solo vista alineada, profundidad y caras visibles. Los ejes bloqueados y tamaños
sin extensión no son editables. El lote se valida entero antes de escribir;
error revierte valores, éxito crea un único undo si hubo cambios y devuelve escena.
Una identidad o revisión obsoleta se rechaza sin modificar nada. Es exclusivo con
sesiones activas y solo se ofrece en Object fuera de los workspaces CAD/Materiales.
`object.properties_changed` solicita refrescar el snapshot ante cambios desde el PC.
Android aplica los valores válidos inmediatamente con una petición en vuelo y
coalescencia de valores pendientes. Vacíos y expresiones incompletas permanecen
locales; no hay Cancelar/Confirmar. Cada envío usa la revisión recién recibida.
`request_token` correlaciona
la respuesta en el cliente y no es parte del documento ni de la identidad del objeto.

`gizmo.set` (`enabled`) y `gizmo.drag` (`phase` BEGIN/UPDATE/END/CANCEL, `u`, `v`,
`dx`, `dy`) forman el manipulador sobre la selección (`transform_modal.gizmo`). Con
`enabled` y sin otra sesión, GPUOffScreen dibuja en el centro de la selección flechas
(mover por eje), cajas (escalar por eje), anillos (rotar; se ocultan vistos de canto),
un aro blanco (escalar todo) y un círculo central (mover libre en la vista). BEGIN
sondea esas asas con la cámara de la tablet; si toca una abre la sesión `transform`
habitual con ese modo y eje (`snap_type` NONE/INCREMENT y `steps` {MOVE, ROTATE,
SCALE}, `scale_step_unit`). UPDATE sigue al dedo con el punto absoluto: el eje
proyectado, el ángulo alrededor del centro o la razón de distancias. END confirma un
único undo y devuelve `gizmo_finished` con el `session_id`; sin cambios cancela sin
undo. Un BEGIN sin asa no abre sesión y los UPDATE orbitan (`miss_behavior: ORBIT`).

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
factores. Android usa este comando al escribir y confirmar cero en el campo de un eje;
no ofrece botones X=0/Y=0/Z=0 separados,
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
| `modifier.add` | `object?`, `type`: `SUBSURF`\|`MULTIRES`\|`ARRAY`\|`BEVEL`\|`SOLIDIFY`\|`BOOLEAN`\|`MIRROR`\|`SIMPLE_DEFORM`\|`LATTICE`, `name?`, `parameters?` |
| `modifier.remove` | `object?`, `name` |
| `modifier.move` | `object?`, `name`, `index` |
| `modifier.set` | `object?`, `name`, `parameters{}` |
| `modifier.toggle` | `object?`, `name`, `viewport?`, `render?`, `editmode?` |
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
{"name": "Subdivision", "type": "SUBSURF", "show_viewport": true, "show_render": true, "show_in_editmode": true,
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

Los descriptores numéricos admiten `editable:true` (por defecto false) y `unit`.
Bisel lo anuncia para `width`, `segments`, `angle_limit` y `profile`. `width`
usa `unit:"LENGTH"`: en la red conserva unidades Blender; Android muestra la unidad
del preset y convierte mediante `scale_length`. `angle_limit` usa `unit:"ANGLE"`
y conserva grados tanto en la red como en pantalla. Confirmar un borrador válido
envía un único `modifier.set`, sin cuantizar al `step`; vacío, valores no finitos
o fuera del rango no se envían. Los demás controles conservan su presentación.

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
| `file.new` | `preset` obligatorio: `SMALL`\|`MEDIUM`\|`LARGE`; `empty` (bool): escena vacía en vez del cubo inicial ajustado al preset |
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

Durante un boceto CAD, un gesto `orbit` es un vistazo: `begin` guarda la vista del
plano, los `update` orbitan en perspectiva y `end`/`cancel`/desconexión la restauran
en ortográfica. Un `view.orbit` suelto sigue desplazando el plano sin inclinarlo.

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
Tras conectar, el servidor espera SPS/PPS + IDR: nunca empieza por un delta
indecodificable. Cada cliente conserva una cola de hasta 60 AUs para absorber ráfagas;
si se llena o supera 250 ms, abandona el GOP y espera un IDR fresco. Una escritura
TCP bloqueada durante un segundo cierra ese cliente y retira su demanda de captura.
Android crea un decoder por conexión, invalida el trabajo anterior por generación y
limita su cola a seis AUs/150 ms antes del hilo de MediaCodec. Un salto de secuencia
o saturación vacía el codec y espera otro IDR; solo se omiten salidas ya decodificadas
al presentar la más reciente. La salida se drena también entre paquetes. Al pasar a
segundo plano se cancelan los HTTP de ambos formatos; al volver se reintenta H.264,
recreando su Surface si se había activado MJPEG. El framing y sus flags no cambian.

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

## CAD paramétrico — versión 2 extendida: sketch y vaciado

`features.cad` anuncia `version:2`, `planes:[XY,XZ,YZ]`,
`entities:[LINE,RECTANGLE,CIRCLE,ARC,NGON,SLOT,GEAR,POLYGON]`, `features:[EXTRUDE,CUT,LOFT,HELIX,MIRROR]` (más FILLET/CHAMFER en la pila vía `cad.finish.*`),
`sketch_editing:true`, `fillet:true`, `length_unit:METERS` y `constraints` con
`COINCIDENT,POINT_ON_LINE,HORIZONTAL,VERTICAL,PARALLEL,COLLINEAR,PERPENDICULAR,TANGENT,EQUAL,DISTANCE,DISTANCE_X,DISTANCE_Y,RADIUS,FIX,MIDPOINT,SYMMETRIC,SYMMETRIC_LINE`
(`ANGLE` y `EQUAL_ANGLE` existen en el documento, pero no se anuncian en el rail).
`cad.constraint.add` acepta una o varias referencias para `HORIZONTAL`/`VERTICAL`
(`LINE/BODY` o `RECTANGLE|NGON/EDGEi`). Persiste una regla individual por referencia,
sin duplicados, y resuelve el grupo en una transacción y un undo. Una referencia
inválida o un conflicto rechaza la petición completa.
`POINT_ON_LINE` recibe dos referencias de figuras distintas del mismo croquis:
un punto y una recta (`LINE/BODY`, `RECTANGLE|NGON/EDGEi` o `SLOT/AXIS`). Acepta
cualquier orden de selección y persiste `refs:[punto,recta]`. Su único residual
es la distancia perpendicular firmada; no limita la posición al segmento visible
ni fija la guía. Usa `cad.constraint.add/delete` y el solver/undo comunes.
`COLLINEAR` usa dos referencias de línea/lado del mismo croquis: ambos segmentos
pertenecen a la misma recta infinita, con longitudes y posiciones longitudinales
independientes. No une extremos ni fija la referencia; respeta FIX y las cotas.
`TANGENT` acepta línea–arco/círculo y dos arcos/círculos distintos del mismo boceto.
Con dos curvas, `cad.constraint.add` persiste `mode:EXTERNAL|INTERNAL`, elegido
por cercanía al contacto inicial: distancia entre centros igual a la suma o a la
diferencia absoluta de radios. Sin `mode` se interpreta `EXTERNAL`; la tangencia
línea–curva conserva su comportamiento. Las coincidencias de extremos son reglas
separadas. Guardar/cargar y editar radios conservan el modo; los conflictos no
modifican el documento ni crean undo. Android habilita Tangente para dos figuras
completas distintas (`BODY`), no para centros/extremos ni para dos líneas.
Al añadir la tangencia entre curvas, los radios de las dos seleccionadas son
objetivos exactos de esa edición: el solver desplaza los centros libres y ajusta
los extremos coincidentes. No se persisten restricciones RADIUS adicionales.
También anuncia `construction`, `datum_planes`, `bodies`, `origin`, `mesh_copy`,
`smart_cursor`, `selection_delete`, `editable_dimensions`, `fillet_remove`,
`solid_selection`, `face_sketch`, `project_reference` y `history_order`.
Las extensiones se negocian por capabilities; se instala el APK junto con el ZIP.
`offset_entities:[SLOT,CIRCLE,RECTANGLE]` y `feature_mirror:true` habilitan las
acciones contextuales nuevas. `SLOT.radius` público = `width/2`; `cad.entity.set`
acepta `radius` o `width`, actualizando la misma cota RADIUS. El esquema `dimensions`
puede anunciar `lockable:false` para un campo editable sin candado independiente.

`cad.entity.offset {entity_id,thickness,side:OUTWARD|INWARD}` crea una figura del
mismo croquis y una regla persistente interna `OFFSET {refs:[fuente,derivada],value,side}`.
`value` es grosor positivo en metros. Las referencias son BODY; no se permite más
de un padre ni ciclos. El solver mantiene la separación normal constante; la
derivada publica `offset` y una medida Grosor. `cad.entity.set {values:{offset}}`
o `cad.constraint.set` editan el grosor manteniendo la fuente. Un fallo conserva el
documento y el historial. No se anuncia OFFSET como restricción genérica del rail.

`cad.feature.mirror {feature_id,plane:XY|XZ|YZ,offset:0}` crea un nodo `type:MIRROR`
con `mirror:{source_id,plane,offset}` y `operation:EXTRUDE|CUT`. Plane/offset se
editan con `cad.feature.set`; el resto se hereda del original (perfil, profundidad,
extent). Refleja el operando antes de unir/restar sobre el resultado acumulado.
Fuente y espejo pertenecen al mismo cuerpo; la fuente debe ser anterior, estar
activa al crear y no ser otra simetría. Su desactivación oculta ambos resultados.
La fuente con dependientes no se puede borrar. MIRROR tiene un tipo propio para
que complementos antiguos lo rechacen en vez de evaluarlo como otra extrusión.

Carcasa se anuncia como `SHELL` en `features.cad.features`. Su nodo guarda
`{id,type:"SHELL",name,order,sketch_id:null,body_id,enabled,faces:[{origin,normal}],thickness,side}`.
`faces` contiene entre 1 y 200 caras planas abiertas; sus puntos interiores y normales
están en el espacio local del documento, en metros (inversa de `matrix_world` para
puntos, transpuesta para normales, y `scale_length` para longitudes). No guarda
índices. Si el centro de una cara cae en un hueco, se usa un punto interior de su
triangulación. La referencia se empareja por normal exterior y contención del punto;
si cambia la altura, admite una única cara paralela que contenga la proyección.
Sin coincidencia o con ambigüedad devuelve `cad_reference_missing`.

`thickness` es positivo en metros; `side` es `INSIDE` (por defecto) o `OUTSIDE`.
OpenCascade usa MakeThickSolidByJoin y verifica cierre, volumen y el espesor real
del hueco interior. Si falta OCP devuelve `cad_kernel_missing`, con la instrucción
de ejecutar `blender-backend/tools/install_occt.sh`, sin cambiar el documento.
La sesión publica `operation:SHELL`, `thickness`, `side`, `face_count`, `can_confirm`
y `error`. Un grosor inviable deja `candidate:null`, conserva los campos, no crea
undo y confirmar no cierra esa sesión inválida. Una actualización válida rehabilita
la confirmación. Cancelar, guardar o desconectar restaura el baseline.
Cada actualización reconstruye desde ese baseline; la barra de retroceso determina
la inserción del nodo y confirmar avanza hasta él. No tiene croquis fuente ni sirve
como apoyo de un plano; se usa Boceto en cara para la superficie resultante.
Android serializa sus comandos y conserva cambios de lado entre muestras de grosor;
solo reemplaza actualizaciones pendientes de Carcasa con los mismos campos.

Hasta cara (`extent:TO_FACE`) termina una Extrusión/Vaciado en el plano de una cara
plana del sólido, sondeada una sola vez en el toque `u,v` mediante `commands/snap.py`.
El nodo guarda `to_face:{origin,normal}` en metros (marco capturado, sin índices
evaluados ni asociación topológica). Cada pared sigue la normal del croquis hasta ese
plano, así que la tapa lejana puede quedar inclinada; el sentido lo decide la cara.
Todo el perfil debe quedar a un lado del plano y no ser paralelo a la dirección:
si no, se rechaza sin cambios. `depth` conserva el recorrido en el origen del croquis
(solo informativo). La simetría copia `to_face` y lo refleja con el operando. Una
extrusión hasta cara no sirve de apoyo de bocetos; `ONE`/`BOTH` o una `depth`
escrita retiran la cara.
Perforar todo (`extent:THROUGH_ALL`, solo CUT) atraviesa el cuerpo acumulado
a ambos lados del croquis siguiendo su normal. Cada evaluación calcula el alcance
desde los límites del sólido anterior, con margen: no persiste una profundidad
artificial ni depende del grosor inicial. Respeta perfiles completos, huecos y
simetrías; no crea una tapa de fondo. `depth` conserva la última cota manual para
volver a `ONE`/`BOTH`. Los gestos y `settle` no alteran un corte pasante; una
`depth` explícita sin `extent` vuelve a `ONE`. El fantasma usa el mismo cuerpo
anterior y el cambio se confirma/cancela con el ciclo de sesión habitual.
Una operación pasante no sirve como apoyo de plano: se usa Boceto en cara.

Las magnitudes y planos usan los metros/ejes del documento CAD; las matrices de
colocación del objeto Blender siguen aplicándose al resultado completo.
`mode.set {mode:CAD}` activa el espacio CAD (Blender permanece en Object).
OBJECT/EDIT salen de CAD y cancelan cualquier preview. Los objetos evaluados CAD
requieren `cad.convert` antes de Edit. El documento JSON versionado vive en la
escena del `.blend`; sus identificadores no dependen de índices de malla.

Cada cuerpo materializa un objeto único con `btr_cad_body_id` y la operación final
visible en `btr_cad_feature_id`. Sus operaciones se evalúan por orden de historial:
EXTRUDE une al resultado anterior y CUT resta de él, con un destino válido del
mismo cuerpo. La barra de historial modifica el resultado del objeto, sin publicar
objetos independientes por paso. Nuevo cuerpo inicia otra pieza. La caché de evaluación
incluye fuente/plano/profundidad/predecesor; los datos GPU y de selección se invalidan
ante cambios reales de malla, transformación o unidades.

Todos los comandos `cad.*` devuelven el estado completo; `cad.state` también es
un evento emitido al cambiar documento, sesión o proyección de la cámara:

```json
{"version":1,"workspace":true,"document":{"version":1,"revision":3,"id":"doc_uuid","sketches":[{"id":"sketch_uuid","name":"Sketch 1","plane":"XY","entities":[{"id":"entity_uuid","type":"RECTANGLE","x":0,"y":0,"width":0.08,"height":0.045}],"profiles":[{"id":"profile_entity_uuid","entity_id":"entity_uuid","label":"Rectángulo"}]}],"features":[]},"active_sketch_id":"sketch_uuid","selection":{"kind":"ENTITY","id":"entity_uuid"},"session":{"active":false,"id":null,"operation":null,"depth":null,"can_confirm":false},"overlay":[{"id":"entity_uuid","points":[[0.4,0.4],[0.6,0.4],[0.6,0.6],[0.4,0.6]],"closed":true,"selected":true}],"error":null}
```

Las longitudes CAD son **metros**, independientes de `scene.scale_length`.
Android convierte únicamente la representación mm/cm/m. LINE contiene
`x,y,x2,y2`; RECTANGLE `x,y,width,height` (esquina mínima); CIRCLE `x,y,diameter`
(centro); ARC `x,y,radius,start,sweep` (centro, radio y ángulos en grados).
Un cuadrado es un RECTANGLE con igualdad entre dos lados contiguos (no hay tipo propio).
El sketch guarda `offset` en metros y opcionalmente `support_id` de una feature;
el soporte actualiza el plano/offset desde su cara superior. Las coordenadas están
en el plano local del sketch. La normal positiva
es +Z para XY, −Y para XZ y +X para YZ.

| Comando | Payload | Efecto |
| --- | --- | --- |
| `cad.state` | `{}` | Consulta documento y preview |
| `cad.sketch.create` | `{plane:"XY",offset?,body_id?}` o `{support_id}`, `{plane_id}`, `{reference_sketch_id}` | Crea y activa boceto; reutiliza planos sin duplicar geometría |
| `cad.sketch.activate` | `{sketch_id}` | Edita sketch existente, encuadra su plano |
| `cad.sketch.rename` | `{sketch_id,name}` | Nombre de 1–80 caracteres; conserva IDs y geometría, un undo |
| `cad.sketch.finish` | `{}` | Sale del dibujo conservando perfiles seleccionables |
| `cad.select` | `{kind:"ENTITY\\|PROFILE\\|SKETCH\\|FEATURE",id,part?,additive?}` o `{u,v,additive?}` | Geometría de boceto, perfil individual, croquis completo o feature; aditiva alterna pertenencia |
| `cad.entity.begin` | `{type:"POINT\|LINE\|RECTANGLE\|CIRCLE\|ARC\|NGON\|SLOT\|GEAR\|POLYGON",u,v,sides?,teeth?,pressure?}` | Inicia dibujo reversible; POINT ya tiene candidato al bajar, UPDATE mueve ese único punto y confirmar consume la última preview. `sides` (3–32, def. 6) solo en NGON; `teeth` (6–150, def. 20) y `pressure` (14.5/20/25°, def. 20) solo en GEAR |
| `cad.entity.update` | `{u,v}` | Actualiza extremo desde baseline; con `increment` el inicio cae en la rejilla del paso (o en un punto existente, con coincidencia) y tamaño/radio se redondean al paso |
| `cad.polygon.begin` | `{u,v}` | Inicia o continúa la cadena de un polígono irregular; el primer vértice admite snap de extremos |
| `cad.polygon.update` | `{u,v}` | Tramo provisional desde el último vértice, con snap a extremos incluidos los de la propia cadena |
| `cad.polygon.segment` | `{u,v}` | Consolida un vértice por trazo o toque; si el extremo es el punto inicial con tres o más vértices, cierra y confirma con un único undo |
| `cad.polygon.close` | `{}` | Cierra la cadena con el segmento final y confirma; con menos de tres vértices responde error y conserva la sesión |
| `cad.entity.set` | `{entity_id,values:{width?,height?,diameter?,radius?,start?,sweep?,length?,flats?,angle?,sides?,module?,teeth?,pressure?,x?,y?,x2?,y2?},constrain?:bool}` | Edita dimensiones y reconstruye dependientes; `constrain:true` acota las medidas editadas que ofrecen candado |
| `cad.entity.delete` | `{entity_id}` o `{}` | Borra una figura completa o la selección de puntos/aristas/figuras en un undo; protege perfiles usados |
| `cad.shell.begin` | `{thickness?,side?:"INSIDE\|OUTSIDE"}` | Carcasa sobre las caras planas seleccionadas del mismo cuerpo, en CAD 3D. Grosor inicial 0,002 m, lado INSIDE; requiere OpenCascade |
| `cad.shell.update` | `{thickness?,side?}` o `{gesture,baseline_thickness}` | Actualiza la preview desde el baseline; comparte el paso y snap de acabados. Confirma/cancela mediante `cad.session.*` |
| `cad.extrude.begin` | `{profile_id?,sketch_id?,depth,operation:"EXTRUDE\\|CUT",target_id?,extent?}` | Un perfil o el croquis completo; contornos exteriores como volumen e interiores como huecos. CUT exige destino. `extent` es `ONE` (defecto), `BOTH` o `THROUGH_ALL` (solo CUT); en EXTRUDE, `BOTH` es simetría a los dos lados del croquis |
| `cad.finish.begin` | `{operation:"FILLET\|CHAMFER",width?,segments?}` | Redondea/achaflana las aristas seleccionadas del sólido (`surface` en EDGE, un mismo cuerpo) como nuevo nodo de la pila; preview reversible |
| `cad.finish.update` | `{width}` o `{gesture,baseline_width}` o `{segments}` | Ancho exacto o delta vertical (un paso por 4 % de altura); segmentos 1–16, chaflán siempre 1. Confirmar/cancelar con `cad.session.*`; el estado de sesión publica `width` y `segments` |
| `cad.extrude.update` | `{depth}` o `{gesture,baseline_depth}` o `{gesture_u,gesture_v,u?,v?,baseline_depth}` o `{settle}` o `{extent}` o `{extent:"TO_FACE",u,v}` | Cota exacta, también negativa en EXTRUDE (sentido contrario a la normal del plano). El gesto de lápiz sigue esa normal en pantalla y no rehace el booleano; `settle` al soltar asienta el sólido. En CUT, `extent` cambia una o dos direcciones o `THROUGH_ALL` sin confirmar. `TO_FACE` con `u,v` sondea una vez la cara plana tocada (ver «Hasta cara») |
| `cad.session.confirm` | `{}` | Confirma candidato estable, un undo |
| `cad.session.cancel` | `{}` | Restaura documento y geometría originales |
| `cad.feature.set` | `{feature_id,depth?,enabled?,extent?,u?,v?,width?,segments?,thickness?,side?}` | Edita o suprime feature. `extent` en EXTRUDE/CUT: `ONE`, `BOTH`, `TO_FACE` (con `u,v` de la cara) o `THROUGH_ALL` (solo CUT); una `depth` escrita sustituye el límite automático; `width`/`segments` solo en FILLET/CHAMFER; `thickness`/`side` solo en SHELL |
| `cad.feature.delete` | `{feature_id}` | Borra feature y resultado |
| `cad.convert` | `{body_id}` o `{feature_id}` | Copia el cuerpo completo como malla independiente con sus modificadores, sale a Object y conserva el documento; el original queda oculto fuera de CAD |
| `cad.settings` | `{step?,increment?,construction?,show_scene?,section?}` | Paso métrico positivo y snap, sin undo ni cambio geométrico. `section` corta el vídeo por el plano del boceto abierto (ver «Vista en sección») |
| `cad.drag.begin` | `{u,v}` | Sondea y conserva selección previa; prepara arrastre del grupo si cubre el elemento, sin cambiar selección todavía |
| `cad.drag.update` | `{u,v}` | Reconstruye y resuelve geometría desde baseline; sobre una cota solo mueve su rótulo en el plano, sin snap, solver ni evaluación del sólido |
| `cad.drag.end` | `{}` | Sin UPDATE alterna el elemento sondeado en BEGIN; con arrastre confirma el último candidato. Nunca vuelve a sondear |
| `cad.points.weld` | `{}` | Une los puntos seleccionados mediante coincidencias persistentes; conserva el último punto (el origen manda si está incluido), resuelve restricciones y crea un único undo |
| `cad.points.midpoint` | `{}` | Crea un POINT auxiliar en el medio de una arista recta seleccionada o entre dos puntos distintos; persiste MIDPOINT y un undo. Selecciona el nuevo punto para continuar subdividiendo con un extremo |
| `cad.select_all` | `{action:"SELECT\\|DESELECT",sketch_id?}` | En boceto selecciona figuras (también construcción, nunca origen). En 3D selecciona el croquis indicado como SKETCH. DESELECT limpia; sin undo |
| `cad.constraint.add` | `{type,value?,refs?}` | Restringe selección o referencias explícitas del boceto activo; una cota equivalente se actualiza conservando ID. `DISTANCE` con `value:0` entre dos puntos crea `COINCIDENT`. Sin `refs`, vacía la selección al terminar |
| `cad.constraint.set` | `{constraint_id,value,sketch_id?}` | Cambia la cota canónica y resuelve dependientes; Radio de redondeo ajusta su contacto. Vacía la selección al terminar |
| `cad.constraint.delete` | `{constraint_id,sketch_id?}` | Elimina una restricción del sketch activo |
| `cad.fillet` | `{radius}` | Redondea cada esquina de la selección (rectángulo entero, varias esquinas, extremos de línea o líneas unidas) con un radio compartido; conserva restricciones y operaciones dependientes |
| `cad.fillet.remove` | `{entity_id}` | Quita un redondeo, extiende los lados hasta la esquina y remapea el perfil usado por sólidos, con un undo |
| `cad.sketch.delete` | `{sketch_id}` | Elimina un boceto sin operaciones dependientes |
| `cad.loft.create` | `{from_profile_id\|from_sketch_id,to_profile_id\|to_sketch_id}` | Solevado `LOFT`: une un contorno exterior sin huecos de cada croquis (un croquis debe tener un único contorno) con paredes regladas, unido al cuerpo del primero; un undo. Planos coincidentes se rechazan |
| `cad.sweep.create` | `{profile_id\|sketch_id,path_sketch_id}` | Barrido `SWEEP`: lleva un contorno cerrado (huecos incluidos: un anillo da un tubo) por la cadena abierta de líneas y arcos no constructivos de otro croquis, unido al cuerpo del perfil; un undo. El perfil conserva su posición relativa al inicio del recorrido y gira por transporte paralelo de la tangente (exacta en los extremos, bisectriz en cada vértice, estirada a lo ancho del giro). Se rechazan recorridos cerrados, ramificados o con otras figuras, perfiles paralelos a la tangente inicial y perfiles mayores que la curvatura. Es asociativo: editar cualquiera de los dos croquis lo reevalúa; el croquis del recorrido queda consumido y no se borra mientras exista |
| `cad.helix.create` | `{profile_id\|sketch_id,axis?,pitch?,turns?,hand?}` | Barrido helicoidal `HELIX` de un contorno sin huecos alrededor de un eje del croquis (`X`, `Y` por el origen o el id de una línea); `pitch` m/vuelta (por defecto 1,25× la altura del perfil), `turns` (≤200, def. 5), `hand` `RIGHT\|LEFT`. Se suma al cuerpo; un undo. `cad.feature.set` edita `pitch/turns/hand/axis` |
| `cad.sketch.copy` | `{sketch_id,offset}` | Copia el croquis a un plano implícito paralelo, `offset` metros por su normal; un undo y selecciona la copia (`SKETCH`). La separación se edita con `cad.plane.set` (`translation[2]`) |
| `cad.sketch.visibility` | `{sketch_id,visible}` | Muestra/oculta el overlay; el boceto activo siempre se ve |
| `cad.entity.construction` | `{construction}` | Cambia las figuras seleccionadas a auxiliares o perfiles; rechaza romper una operación dependiente |
| `cad.body.create` | `{}` | Crea y activa otro cuerpo independiente |
| `cad.body.activate` | `{body_id}` | Elige el cuerpo de los nuevos bocetos, sin undo |
| `cad.plane.create` | `{base?,translation?,rotation?,reference_sketch_id?,support_id?,start_sketch?}` | Plano persistente en metros y grados locales XYZ. start_sketch crea y activa también su croquis en el mismo undo |
| `cad.plane.set` | `{plane_id,translation?,rotation?}` | Ajusta el plano y reconstruye bocetos/sólidos dependientes |
| `cad.revolve.create` | `{profile_id\|sketch_id,axis?,angle?}` | Revolución (`REVOLVE`) de un contorno sin huecos alrededor de `X`/`Y` del croquis o de una línea suya; `angle` en grados (0–360, por defecto 360). Puede apoyarse en el eje, no cruzarlo. Se suma al cuerpo con un undo; `cad.feature.set` edita `angle` y `axis` |
| `cad.plane.begin` | `{base:"XY"\|"XZ"\|"YZ"\|"FACE"\|"EDGE"}` o `{plane_id}` | Abre la sesión `PLANE`: preview del plano dibujada en la captura, sin tocar el documento. FACE usa la cara resaltada (sin otro raycast); EDGE usa la única arista recta resaltada: X sigue la arista, el plano empieza enrasado con una cara contigua y `tilt[0]` lo gira alrededor de ella. `plane_id` recoloca un plano guardado |
| `cad.plane.purge` | `{}` | Borra todos los planos que no usa ningún boceto, con un undo; `nothing_to_purge` si no hay ninguno |
| `cad.plane.update` | `{base?,offset?,tilt?[2],shift?[2]}` o `{grab_u,grab_v}` o `{gesture_u,gesture_v,u,v,baseline_offset?}` o `{release}` | `offset` en metros por la normal ya inclinada, `tilt` en grados sobre los ejes X/Y del plano, `shift` en metros dentro del plano base. `grab` sondea una vez la flecha bajo el lápiz (mitad exterior de X/Y/N dibujadas en GPUOffScreen; fuera de ellas, N) y fija su inicio; el gesto arrastra ese valor 1:1 bajo la punta, en pasos con Incremento: X/Y cambian `shift` por su dirección real en el mundo (también inclinado) y N la separación. `release` suelta la flecha. `session.plane` publica `{base,plane_id,offset,tilt,shift,positive_label,negative_label}`; `cad.session.confirm` crea plano y croquis activo en un undo (o aplica la posición del guardado) |
| `cad.surface.mode` | `{mode:"PROFILE\|FACE\|EDGE\|VERTEX"}` | Elige selección del boceto/perfiles o referencias del sólido, sin undo |
| `cad.surface.select` | `{u,v}` | Alterna una referencia visible; en boceto acumula puntos/aristas/caras de distintos objetos para proyectarlos juntos y un miss conserva la selección; en 3D conserva dos para medir o varias aristas del mismo objeto para acabado |
| `cad.surface.clear` | `{}` | Limpia las referencias transitorias |
| `cad.sketch.on_face` | `{offset?}` | Crea un boceto en la cara plana resaltada, sin repetir sondeo y con un undo; `offset` (m) lo separa por la normal: positivo hacia fuera |
| `cad.reference.project` | `{}` | Copia las referencias seleccionadas a construcción fija en el boceto activo |
| `cad.reference.close` | `{}` | Convierte las curvas proyectadas seleccionadas (o todas sin selección) en perfiles cerrados. Une extremos próximos hasta el Paso CAD, conserva centro/radio de los arcos, actualiza sus FIX y añade coincidencias; una transacción y undo. Huecos mayores, ramificaciones, cruces o conflictos rechazan todo |
| `cad.view.solid` | `{}` | Sale del plano de boceto, restaura la vista 3D orbital y encuadra |



`selection.items` contiene `{kind,id,part}`; `selection.kind/id/part` conserva el
último elemento para el inspector. Roles: LINE START/END/BODY; RECTANGLE P0..P3 y
EDGE0..EDGE3/BODY; CIRCLE CENTER/RIM/BODY; ARC CENTER/START/END/BODY y CORNER
solo en redondeos. CORNER es la intersección de los lados rectos prolongados,
derivada sin añadir geometría al perfil. Participa en selección, snap, arrastre,
cotas y simetría; se reconoce también en documentos anteriores. Redondear remapea
las referencias a la esquina original a CORNER; quitar el redondeo las devuelve
al extremo de línea restaurado, incluidas las fijaciones de puntos. El sondeo da
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
Al confirmar campos de medidas, Android envía `constrain:true`: crea o reutiliza
sus cotas en la misma transacción y undo, y sus `constraint_ids` marcan los candados.
No acota campos no editados, coordenadas, ángulos ni parámetros discretos. Un
conflicto rechaza valores y cotas juntos. Omitir el flag conserva la edición libre.
CIRCLE publica `radius=diameter/2` y describe Radio con `value_factor:1` para RADIUS.
`cad.entity.set` admite radio o diámetro y actualiza la misma cota; si se envían ambos,
deben coincidir. El documento conserva `diameter` como parámetro canónico. La bandeja
muestra Radio también durante la preview de dibujo, sin convertirla en otra sesión.
LINE publica `length` derivada y admite editarla. El cuadrado solo anuncia Lado.
Coordenadas y ángulos siguen siendo parámetros geométricos; FIX continúa imponiendo
su bloqueo, no se desactiva implícitamente al editar una cota.

Los handles del overlay admiten `intent:POINT|ANGLE`. En un arco ordinario seleccionado,
END anuncia ANGLE y se dibuja como rombo. `cad.drag.begin` lo adquiere para editar solo
el arco aunque su BODY pertenezca a un grupo. El arrastre conserva centro, radio e
inicio y varía `sweep` dentro de su signo y rango válido, respetando restricciones.
Cada UPDATE reconstruye desde baseline; END no sondea otra posición y crea un undo
solo si cambió el arco. Cancelar recupera también la selección anterior. Los redondeos
no anuncian este tirador. Al terminar de dibujar un arco Android vuelve al cursor.

Soldar admite dos o más puntos distintos: START/END de líneas o arcos, P0–P3 de
rectángulos y ORIGIN/POINT. No acepta figuras completas ni centro/borde de círculo.
La coincidencia permanece al editar después y permite cerrar perfiles; un conflicto
no cambia documento ni selección. Coincidencias directas o transitivas existentes
no se duplican y repetir una soldadura ya hecha no crea undo.

`dimension_options:{DISTANCE?:{value,constraint_id?},DISTANCE_X?:{value,constraint_id?},DISTANCE_Y?:{value,constraint_id?},RADIUS?:{value,constraint_id?}}`
describe las cotas disponibles para la selección con su medida actual. Android
abre la existente si tiene ID. Se normalizan lados opuestos de rectángulos,
mediciones equivalentes por extremos y cantidades enlazadas por EQUAL. Los
duplicados antiguos tienen un solo control público y se fusionan en almacenamiento
al editar/eliminar. No se anuncia detección general de redundancia algebraica.

DISTANCE_X/Y usan la separación absoluta sobre los ejes locales del boceto entre
dos puntos, o entre extremos de una línea/lado. Aceptan cero y no se fusionan con
DISTANCE ni entre sí. Su overlay añade H/V a la medida en la unidad activa.
EQUAL acepta dos o más medidas compatibles en `cad.constraint.add`; conserva
inicialmente la primera, persiste parejas de igualdad y mantiene las cotas existentes.
El tamaño sigue libre si ninguna cota lo fija. SYMMETRIC conserva sus tres referencias:
los primeros dos puntos deben quedar equidistantes del tercero, que es su centro.
SYMMETRIC_LINE conserva sus tres referencias: los primeros dos puntos deben quedar
a la misma distancia de una tercera referencia de línea (o lado), con el segmento
que los une perpendicular a ella. Sirve para simetría horizontal, vertical o
diagonal según la orientación de esa línea; si el eje no debe moverse, fíjalo antes.

Los redondeos se reconocen por sus coincidencias y tangencias con dos líneas, sin
requerir metadatos nuevos en archivos anteriores. Radio y el campo numérico usan
la misma cota; eliminar RADIUS libera la medida sin quitar el arco. Quitar el
redondeo es la operación explícita `cad.fillet.remove`, que conserva las otras
reglas y las dependencias. DISTANCE de un lado y EQUAL de longitudes se evalúan
hasta las esquinas virtuales cuando el lado participa en un redondeo. El sondeo,
el trazo visible y las distancias entre puntos explícitos siguen usando los puntos
reales; no se persisten coordenadas de pantalla ni referencias RNA.

`ANGLE` con dos referencias rectas (`LINE/BODY`, `RECTANGLE|NGON/EDGEi`, `SLOT/AXIS`)
es el ángulo entre ellas en grados (0–180): cada segmento se orienta desde la
intersección de ambas rectas hacia su extremo más lejano (ángulo interior en una
esquina). Se anuncia en `constraints` y en `dimension_options.ANGLE` para dos líneas.
Con una sola referencia, `ANGLE` es una cota de un `ARC/BODY`; solo los arcos que no son redondeos la describen: `value` en grados,
magnitud del barrido (0,01–360), independiente del sentido de dibujo; `add/set`
aceptan un valor negativo y guardan su valor absoluto. No se anuncia en
`constraints` ni en `dimension_options`: el esquema `dimensions` del arco describe
`sweep` con `constraint_type:ANGLE`, y su candado o `cad.entity.set` con
`constrain:true` la crea. El overlay la rotula `∠ N°`.

`EQUAL` entre dos o más `ARC` añade, respecto al primero, `EQUAL` (radio) y, si
ninguno es un redondeo, `EQUAL_ANGLE` (magnitud del barrido), sin duplicar parejas; ambas
cantidades se agrupan como las igualdades de longitud, así una sola cota RADIUS y
una sola ANGLE gobiernan el grupo. `cad.entity.set` sobre un arco acepta
`equal_ids` (otros arcos del mismo croquis): añade esas igualdades y aplica los
valores/cotas en la misma transacción y undo; otro tipo se rechaza sin cambios.

Cada sketch contiene `constraints:[{id,type,refs:[{id,part}],value?,values?}]`.
FIX guarda `points:{rol:[x,y]}` para los puntos/los extremos de una arista,
y `values` únicamente al seleccionar la figura completa. Una selección múltiple
crea una fijación por referencia dentro de un único undo. El origen reservado
`{id:"ORIGIN",part:"POINT"}` existe en cada boceto, es siempre (0,0) y nunca es un
parámetro del solver. MIDPOINT recibe punto + lado (en cualquier orden al crear)
o tres puntos, con el punto medio en último lugar;
SYMMETRIC recibe tres puntos, con el centro en último lugar. COINCIDENT admite el
origen. SYMMETRIC_LINE recibe dos puntos y una línea/lado como eje, en ese orden.
La construcción participa en las restricciones y queda fuera de perfiles.
`features.cad.entities` incluye POINT y `midpoint_points:true` anuncia la creación
de puntos medios. Los POINT dibujados son auxiliares libres, admiten restricciones,
arrastre y snap, y nunca forman perfiles, aunque se retire Construcción. Los puntos
proyectados conservan sus referencias fijas. Un mismo punto admite MIDPOINT con
varias aristas: sus centros quedan relacionados al resolver el boceto.
`overlay` anuncia `construction` para líneas discontinuas y `label`, `label_point`,
`label_offset` para etiquetas de geometría. Las cotas (reglas con `value`) publican
`kind:DIMENSION`, `label_point`, `label_box:[left,top,right,bottom]`,
`dimension_lines:[[[u1,v1],[u2,v2]],...]` y `arrows:[[[u,v],[towards_u,towards_v]],...]`.
Cada flecha tiene su punta en el primer punto y su base orientada hacia el segundo;
todas las coordenadas son normalizadas respecto al vídeo. `label_box` es la zona
táctil (mayor que la píldora que dibuja Android, centrada en `label_point`).
Las reglas sin valor solo se publican como `kind:CONSTRAINT` con `label`/`label_point`
cuando tocan una entidad seleccionada; no tienen caja ni se pueden seleccionar.
`cad.select {kind:"CONSTRAINT",id}` o tocar una cota selecciona solo esa cota,
incluso con `additive:true`; una regla sin valor responde `bad_payload`. Otra cota
sustituye la selección; no se mezcla con entidades. El arrastre usa `cad.drag.*` y
persiste `constraints[].label_position:[x,y]` en metros del boceto. Mover la etiqueta
no cambia `value`, entidades ni restricciones geométricas. END confirma la última
posición, con un undo; cancelar o desconectar restaura baseline/selección. Un toque
sin arrastre no crea undo.
Las medidas del overlay usan la unidad de escena. El panel Android filtra por IDs
y roles compartidos con la selección, incluidos extremos de aristas.
El solver admite 300 parámetros y resuelve el conjunto completo; una cota escrita
es exacta y el arrastre proyecta el objetivo sobre la libertad permitida. Los
conflictos devuelven `cad_constraint_conflict`, sin cambiar la escena persistente.
No se anuncia un conteo de grados de libertad de un solver general.

`step` e `increment` pertenecen al estado CAD, separados del documento. Con `u,v`
el lápiz sigue la normal 1:1: cada posición se proyecta al punto de la recta normal
(por el centro del perfil) más cercano a su rayo, y la diferencia en metros suma a
`baseline_depth`. Sin `u,v`, o con la normal apuntando a la cámara, un gesto recorre
`gesture / 0.04 * step`. Incremento lo redondea a pasos enteros también durante el trazo. La
profundidad permanece positiva (mínimo 1e-7 m). CUT extruye en dirección negativa
desde el plano del sketch y resta su volumen de `target_id`; al evaluar oculta el
resultado previo consumido. No admite borrar soportes con dependientes; crear una copia de malla sí los conserva.
La preview CUT anuncia `session.transparent:true`: la captura GPU dibuja solo el
volumen retirado como un fantasma translúcido visible a través del sólido, que
conserva su sombreado opaco. No usa rayos X ni modifica el sombreado del viewport;
el lápiz no crea un prisma opaco para el vaciado.

Los comandos de dimensión y feature son transacciones discretas con un undo. Una
sesión conserva propietario; desconexión, undo/redo, cambio de archivo, cambio de
modo o nueva transformación descartan su preview. Confirmar nunca repite raycast.
La selección de un perfil exterior extruye su región con contornos interiores
como huecos. Contornos abiertos no se pueden extruir; intersecciones/tangencias y
valores no finitos o degenerados producen errores explícitos sin perder la última
geometría válida. El kernel V1 genera malla nativa; no anuncia STEP, BREP ni solver
general. Rectángulos conservan lados horizontales/verticales y círculos diámetro.
El cuerpo CAD materializa la malla compacta del kernel. La copia editable
(`cad.convert` o duplicar una pieza CAD) intenta limpiar coincidencias numéricas,
degenerados y divisiones coplanares sin forzar quads. Si esa limpieza no conserva
el sólido, crea una copia independiente de la malla original disponible, con sus
atributos y modificadores, para edición manual. No publica una limpieza parcial
ni exige topología mejorada para salir a Object y permitir Edit. El original y
su documento paramétrico permanecen intactos.
Esta malla de edición/exportación no es el operando de las operaciones
siguientes, que usan la evaluación compacta del kernel para evitar crecimiento
exponencial al encadenar vaciados.

La respuesta de una operación CAD puede quedar pendiente mientras un proceso
Blender auxiliar calcula su snapshot. El servidor sigue procesando vídeo, navegación
y consultas; publica el resultado y responde con el mismo `id` al terminar. No es un
acuse anticipado. Android serializa comandos CAD y conserva solo la última muestra
absoluta pendiente (`cad.extrude.update`, `cad.finish.update`, `cad.drag.update`,
`cad.entity.update`, `cad.polygon.update`), sin atravesar fronteras begin/settle/end.
La navegación no espera a la evaluación. Cancelar, guardar, cambiar de modo, undo,
redo o desconectar invalidan el cálculo pendiente; su respuesta es `cad_cancelled`
y no se confirma una muestra anterior. Otra mutación concurrente devuelve `cad_busy`;
otro propietario no puede cancelar la operación (`session_owned`). Un fallo o tiempo
límite del proceso auxiliar devuelve `cad_worker_failed` y conserva el último sólido
publicado. No cambia el formato del documento, las longitudes ni los IDs de selección.

`document.revision` aumenta con cada transacción confirmada y vuelve al valor
correspondiente al usar undo/redo. `session.depth` y `session.extent` (`ONE`, `BOTH`, `TO_FACE` o `THROUGH_ALL`) describen la preview de EXTRUDE/CUT y
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
`active_body_id`, `construction`, `show_scene` y `section` son estado del workspace.

### Vista en sección

Con `section:true` y un boceto abierto, el vídeo retira lo que queda entre la cámara
y el plano del croquis: el plano cercano de la cámara remota se apoya en él (con un
margen mínimo hacia la cámara). Solo actúa mientras la vista lo mira de frente; el
vistazo en perspectiva lo ignora. No escribe en `rv3d`, no cambia la escena ni crea
undo, y la selección de referencias del sólido ignora la parte retirada.

Mientras `active_sketch_id` esté activo, la cámara remota permanece ortogonal al
boceto: orbit se traduce a pan y las vistas de eje no cambian orientación. El
roll de dos dedos y `cad.view.roll` giran esa vista sobre la normal y se quedan;
`cad.view.align` la endereza conservando distancia de zoom, posición desplazada y
proyección; no vuelve a encuadrar el croquis. La proyección es ORTHO por defecto;
`view.perspective` elige PERSP u ORTHO sin cambiar la orientación y la elección se
conserva al enderezar, girar y reabrir bocetos.
Zoom/pan siguen funcionando y no escriben en `rv3d`.

Al entrar en CAD se conserva la edición del boceto activo si existe; en caso
contrario se encuadra el resultado en 3D, sin activar la edición. Repetir CAD mientras ya está abierto conserva
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

## Materiales (v2) y captura de escena (v1)

`features.materials` anuncia `{version:2, editable_layers:true, paint_kinds:["COLOR","MATERIAL"], recipe_format:"tablet-material",
recipe_version:1, paint:"UV_MASK", mask_size:1024, max_layers:8, max_objects:16}`.
`features.scene_capture` anuncia `{version:1, mime:"image/png", camera:"TABLET",
overlays:false}`. Se añade `MATERIAL` a `enums.mode`; el modo nativo de Blender
continúa siendo Object. El snapshot de escena incluye `material` y anuncia
`mode: "MATERIAL"` durante el workspace.

| Comando | Payload | Resultado |
|---|---|---|
| `mode.set` | `{mode:"MATERIAL"}` | Toma la selección actual de 1–16 mallas y muestra la escena; `{mode,material}` |
| `material.state` | `{}` | `{material: estado}` |
| `material.catalog` | `{}` | `{format,version,presets:[recetas completas]}` |
| `material.import` | `{recipe: receta}` | Guarda/actualiza un preset personalizado en la escena; `{material}`; un undo |
| `material.save` | `{label}` | Guarda la apariencia actual (receta, color, acabado, ajustes y grano) como preset propio con ID derivado del nombre; lo selecciona; `{material}`; un undo |
| `material.settings` | Campos opcionales descritos debajo | Configura el siguiente pincel/aplicación; `{material}`; no cambia la base |
| `material.apply` | `{}` | Asigna la receta/color/acabado a los objetos o zona seleccionados; `{material}`; un undo |
| `material.select` | `{objects:[nombres]}` o `{u,v,additive?:bool}` | Cambia la selección sin salir ni crear undo; lista vacía permitida; `{material}` |
| `material.group` | `{name}` | Guarda los vértices seleccionados en Edit como grupo en cada objeto; no sobrescribe grupos; un undo; `{material}` |
| `material.layer` | `{action:"new"\|"select"\|"set"\|"delete",layer_id?,visible?,opacity?,label?}` | `{material}`; un solo objeto; select/new sin undo, set/delete un undo |
| `material.stroke` | `{phase,stroke_id,points}` | `{finished:bool,material?:estado}`; estado al cerrar; fases `begin/update/end/cancel` |
| `material.lighting` | `{phase,gesture_id?,rotation?,energy?}` | `{material}`; giro e intensidad de la iluminación en `begin/update/end/cancel`, o `reset` sin ID; no crea undo |
| `scene.capture` | `{}` | `{mime:"image/png",width,height,png_base64}` |

Estado `material`: `available`, `active`, `targets` (nombres seleccionados),
`preset`, `color` (color efectivo), `tinted` (hay tinte propio en vez del color del
material), `finish`, `custom` (hay ajustes sueltos encima del acabado),
`surface:{roughness,metallic,transmission,ior,coat}` (valores efectivos),
`surface_controls:[{id,label,low,high,min,max}]` (etiquetas de los extremos),
`grain`, `grain_scale`, `grain_amount`, `grain_relief`, `grains:[{id,label,hint}]`,
`erase`, `radius`, `strength`, `environment`, `light_rotation` (desplazamiento en grados respecto al ambiente, −180 a <180),
`light_energy` (factor sobre la intensidad del ambiente, 0,2–3),
`paint_ready`, `presets:[{id,label,color}]`, `finishes:[{id,label,hint}]`,
`environments:[{id,label}]`, `objects:[{id,label}]` (mallas visibles de la escena),
`interaction:SELECT|PAINT|LIGHTS`, `isolate`, `brush:ROUND|AIRBRUSH|SPRAY`, `brushes:[{id,label}]`,
`scope:ALL|SELECTED|GROUP:<nombre>`, `regions:[{id,label}]`, `paint_limit:20000`,
`paint_blocked` (alguna selección supera el límite de caras base). Se recibe desde `scene.get_state` y los snapshots
`scene.changed`; las respuestas de `material.stroke` no se interpretan como escenas.

El estado incluye `paint_kind:COLOR|MATERIAL` (inicial COLOR), `active_layer` (ID o null),
`layers_editable` (un solo objeto) y `layers:[{id,label,kind,color,visible,opacity}]`,
en orden de abajo arriba. `material.layer select` elige dónde pintar/borrar sin cambiar
el contenido; `new` fuerza una capa nueva al siguiente trazo. `set` acepta visible
booleano, opacity 0–1 y label de 1–48 caracteres. `delete` retira solo esa capa.
Las capas ocultas no se pintan. Cambiar receta/color/intención deja de apuntar a la capa
anterior. Color modifica solo Base Color de los shaders inferiores, manteniendo sus
conexiones de acabado y relieve. Material mezcla la receta completa. Selección múltiple
conserva el pincel por objeto; editar la pila requiere seleccionar uno solo.

El atlas nuevo usa islas Smart Project y margen de filtrado; conserva UV existentes,
selección y modo mediante una copia temporal. Las máscaras antiguas mantienen su atlas.
Aplicar una base completa descarta la pintura y su UV privada; las siguientes pinceladas
crean el nuevo atlas. Fuentes, máscaras e IDs de capa persisten en `.blend` y undo.

Settings: `paint_kind` (COLOR/MATERIAL), `preset` (ID del catálogo), `color` (`#RRGGBB` sRGB, o `null` para usar el
color propio del material), `finish`
(`natural/polished/satin/matte/worn/metal/varnish/translucent`), `surface`
(subconjunto de `{roughness,metallic,transmission,coat}` 0–1 e `ior` 1–3),
`grain` (`none/noise/wood/bands/cells`), `grain_scale` (1–200), `grain_amount` (0–1),
`grain_relief` (0–1), `erase` (booleano), `radius` (0,005–0,25, fracción de
altura del vídeo), `strength` (0–1), `environment` (`studio/day/warm/soft`). Elegir
preset conserva el tinte, el acabado y los ajustes si no se envían explícitamente.
También admite `interaction`, `isolate`, `brush` y `scope` descritos arriba. Se validan
todos los campos antes de cambiar el estado. Importar selecciona el nuevo preset con
su propio color, sin tinte ni ajustes heredados.

El cursor `LIGHTS` gira horizontalmente el ambiente HDR de Material Preview; un
ancho de vídeo equivale a 360°. El eje vertical cambia la intensidad y no la
elevación: `View3DShading` solo expone `studiolight_rotate_z`, así que el foco del
ambiente no se puede subir ni bajar. `material.lighting` requiere el propietario del
workspace, incluso sin objetos seleccionados. `begin` fija un baseline con un ID
de 1–80 caracteres; `update.rotation` es el desplazamiento total en grados desde
ese inicio (finito, ±360 000) y `update.energy` el desplazamiento vertical en
fracciones de alto (±8), aplicado como `baseline · e^(1,1·energy)` y recortado a
0,2–3: la pantalla completa cubre el rango y subir y bajar lo mismo se compensa.
`end` confirma la última preview sin volver a aplicar
el valor; `cancel` la restaura. IDs obsoletos no alteran otro gesto. `reset` devuelve
el ambiente actual a su orientación e intensidad originales y conserva el cursor.
Cambiar ambiente también reinicia giro e intensidad. Navegar, cambiar ajustes, guardar, deshacer o desconectar
cancela el giro en curso; reconectar recupera el último confirmado. La iluminación
solo se altera dentro de GPUOffScreen y no escribe en `rv3d`, objetos ni `.blend`.
Las respuestas de este comando actualizan `material` sin pedir otra escena por muestra.

La apariencia se compone en un orden fijo: receta del catálogo, después el acabado
—que escribe solo los parámetros que define— y después los ajustes sueltos de
`surface`. Enviar `finish` descarta esos ajustes (elegir un acabado es empezar desde
él); enviar `surface` los mantiene sobre el acabado vigente y marca `custom`. El
grano añade una capa de textura teñida con el color efectivo, sin modificar la receta
del catálogo y respetando el límite de ocho capas.

Por defecto se ve toda la escena visible; `isolate` solo oculta los demás objetos
durante la captura. Se puede elegir una pieza interior desde la lista, aislarla,
pintar y volver a mostrar el conjunto. La profundidad incluye todos los oclusores
visibles. Seleccionar o cambiar ajustes cancela antes cualquier trazo activo.

`SELECTED` limita a caras seleccionadas en Edit. `GROUP:<nombre>` incluye caras
cuyos vértices pertenecen al grupo con peso positivo. La zona se propaga por
modificadores mediante un atributo de caras temporal; no persiste índices evaluados.
Aplicar a una zona rellena su máscara completa, incluidas caras ocultas; el pincel
solo pinta la parte visible. Una zona vacía falla sin cambios. Requiere una base
aplicada al objeto completo. Guardar grupos separa mallas compartidas.

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

En Materiales, `material.settings` conserva tinte, acabado y ajustes cuando se omiten,
incluso si cambia `preset`. Sin tinte (`tinted:false`) cada material se compila con su
propio color, de modo que recorrer el catálogo no arrastra el color del anterior.
Cada preset del estado anuncia `category:base|detail`.
Óxido, Suciedad y Arañazos son recetas para detalle; el selector devuelve el color al
del material (`color:null`) y el acabado a natural en el mismo gesto. Elegirlos no sustituye
la base; únicamente `material.apply` aplica a todo. El cálculo de pintura usa
proyección/visibilidad por trazo y un índice de teselas; el atlas se reutiliza por
identidad de geometría/UV evaluadas, invalidándose tras editar la malla en el PC.
La profundidad se reutiliza con cámara y geometría idénticas; cambia al navegar
o editar, y permanece fija durante el trazo cuya cámara también es fija.


## Referencias de sólidos y navegación CAD

`cad.state.surface` contiene `mode`, `selection:[{id,kind,object,feature_id?,planar}]`,
`measurements:[{label,value,unit}]`, `can_sketch` y `can_edge_plane` (una única
arista recta, base de `cad.plane.begin` con `EDGE`). Las unidades de medida son
`LENGTH` (metros), `AREA` (m²) y `ANGLE` (grados). No son órdenes para reescalar
la malla; miden la geometría seleccionada. Una tercera referencia inicia otra pareja.
Todas las referencias seleccionadas se resaltan en azul dentro de GPUOffScreen.
La captura limpia excluye estos marcadores.

En CAD 3D, EDGE une regiones contiguas con tangente analítica continua en un
contorno. Todos sus tramos comparten ID, medida y resaltado; no cruza esquinas ni
bifurcaciones ambiguas. En un boceto, la proyección conserva las aristas de diseño
individuales. Los modificadores propagan también la agrupación del contorno.

`cad.finish.begin/update` conserva la sesión ante `cad_finish_invalid`: publica
el ancho solicitado, `can_confirm:false` y la explicación en `cad.state.error`.
Reducirlo puede recuperar una preview válida sin repetir la selección. No persiste
el candidato inválido ni confirma una preview anterior; cancelar restaura el
baseline. Una referencia inexistente sigue siendo un error que impide iniciar.

El sondeo de `commands/snap.py` usa malla evaluada y oclusión común. Las referencias
de origen agrupan parches coplanares conectados y fragmentos collineales de aristas,
omitiendo aristas internas coplanares. Con modificadores, etiquetas transitorias
FACE/EDGE propagan esas referencias a la geometría evaluada: Subdivisión conserva
seis caras y doce aristas seleccionables en un cubo, sin seleccionar sus divisiones
internas. El resaltado sigue la forma evaluada. En cuerpos CAD cuya pila visible
solo tiene Bisel/Subdivisión, las medidas, vértices y planos se toman de la geometría
de diseño previa al acabado; una cara de diseño plana conserva `can_sketch` aunque
el acabado la redondee. Los puntos se comprueban contra el cuerpo de diseño y los
otros oclusores visibles. En otras pilas se conserva la referencia evaluada. Las
etiquetas se retiran siempre.
Los datos evaluados solo se retienen en memoria, validados contra geometría base,
geometría evaluada y matriz del objeto. No se guardan sus índices en CAD.
Si la geometría cambia, las referencias se invalidan antes de crear un boceto.
`cad.sketch.on_face` consume el marco elegido; no hace otro raycast. La cara superior
CAD se vincula a su operación; otras caras conservan un marco capturado. Los planos
implícitos sin otros usuarios se retiran al borrar su boceto.

`cad.reference.project` deja caer las aristas elegidas sobre el plano del boceto
activo, aunque estén a otra altura, y crea LINE o CIRCLE `construction:true,reference:true` con FIX.
Se descartan proyecciones degeneradas y se respeta el límite del solver. Es una
copia estática que permite cotas contra geometría existente, no asociación BREP.
`features.cad.reference_profile:true` anuncia `cad.reference.close`. Este cierre
explícito transforma las curvas proyectadas en perfiles sin cambiar sus IDs ni el
cuerpo de origen; los arcos conservan sus círculos de soporte y se ajustan los
extremos de las líneas. La distancia máxima de unión es el Paso CAD en metros.

El documento público añade `history:[{id,kind,name,body_id,sketch_id?}]` en orden de
creación. `kind` es SKETCH o FEATURE. Los nodos persistentes usan `order`; documentos
anteriores se normalizan sin cambiar IDs. Android presenta esa secuencia como una pila
de operaciones: tocar un nodo mueve la barra de retroceso a ese punto y muestra el
modelo tal como estaba justo después de él; los nodos posteriores quedan atenuados.
`cad.history.rollback {node_id|null}` fija la barra y `null` restituye el modelo
completo; el estado la anuncia en `rollback_id`. El estado CAD incluye también
`kernel:{id:"OCCT",label:"OpenCascade"}`. Las capacidades anuncian
`features.cad.kernel:"OCCT"` y `kernel_required:true`. OCP es obligatorio: si falta
o no se puede cargar, devuelve `cad_kernel_missing` con un mensaje de instalación
mediante `blender-backend/tools/install_occt.sh`; no hay fallback ni selector de
motor. El worker recibe `occt_path` y no recibe un campo de elección de motor.
La navegación por la pila no crea
undo. El rebuild solo evalúa las operaciones hasta la barra: las demás conservan su
objeto oculto, sus bocetos dejan de proyectarse y seleccionarlas, activarlas,
editarlas o borrarlas responde `cad_rollback`. Crear un boceto u operación con la
vista atrás lo inserta justo después del nodo de la barra renumerando la pila; al
confirmar, la barra avanza para incluirlo y el usuario ve el resultado. Salir del
workspace o reconectar devuelve la barra al modelo completo. La visibilidad automática
oculta bocetos consumidos; `cad.sketch.visibility` guarda `visibility_explicit:true`
para respetar la decisión del usuario. Finalizar boceto no crea undo ni modifica
`rv3d`; restaura una vista 3D y selecciona el perfil nuevo pendiente o el último
resultado visible. La preview de Extruir/Vaciar se presenta también en 3D, conservando
los gestos de profundidad y navegación.


En Materiales/Texturas, `view.shading {mode:WIREFRAME|TOGGLE}` se normaliza a
`SOLID`; Android no ofrece ese control. La captura también normaliza un Wireframe
preexistente o activado desde el PC antes de tomar el estado que restaurará.
El resultado conserva Solid, evitando el ciclo Wireframe/Material entre frames.
Fuera de Materiales, `view.shading` conserva su comportamiento habitual.

### Taladro y bandeja por esquema

`cad.hole.begin {sketch_id,size?,kind?,point_ids?,depth?,extent?,tolerance?,insert_diameter?,insert_depth?}`
crea preview `HOLE`. `kind`: THROUGH/COUNTERBORE/COUNTERSINK/NUT/INSERT; métricas
M2/M2.5/M3/M4/M5/M6. `point_ids:null` usa todos los POINT y centros de CIRCLE.
`extent`: ONE/THROUGH_ALL; longitudes en metros, holgura diametral. INSERT usa su
profundidad propia. `cad.operation.update` modifica los mismos campos de la sesión;
`cad.session.confirm/cancel` la cierra y `cad.feature.set` edita el nodo confirmado.
El estado publica `operation_controls:{id,type,label,fields}`; cada campo describe
key/label/type/value y, según tipo, options/step/min/max/unit. Tipos: NUMBER, ENUM,
MULTI, BOOL, ACTION. Una preview inválida conserva los controles y no confirma.

### Patrón de operaciones

`cad.pattern.begin {source_ids,kind?,count?,spacing?,direction?,direction2?,count2?,spacing2?,symmetric?,axis?,axis_origin?,angle?}`
inicia PATTERN. LINEAR admite ejes X/Y/Z o segmentos capturados; CIRCULAR admite
eje X/Y/Z por axis_origin o marco {origin,normal}. Número es 2–100 e incluye la
fuente; el ángulo parcial incluye extremos y 360° excluye la copia coincidente.
`cad.operation.update` / `cad.feature.set` aceptan esos campos y `pick_direction`,
`pick_direction2`, `pick_axis` o `pick_cylinder` con u/v para capturar la referencia
visible en metros locales. `source_ids` admite EXTRUDE/CUT/HOLE anteriores y del
mismo cuerpo; ninguna fuente puede ser patrón o simetría. MULTI con all_null:false
envía todos los IDs explícitos al elegir Todos. Desactivar una fuente suprime el
patrón; borrarla con dependientes responde cad_dependency.

### Combinar cuerpos

`cad.combine.begin {body_id,tool_body_id? | u,v,operation?,clearance?,keep_tool?}`
inicia COMBINE. `operation`: CUT/UNION/INTERSECT; clearance≥0 en metros, solo CUT;
keep_tool es booleano. El nodo guarda además tool_transform, una matriz afín con
traslación en metros que captura la colocación relativa. `cad.operation.update` y
`cad.feature.set` editan los campos; `pick_tool_body:true,u,v` cambia la herramienta.
Se evalúan ambos cuerpos en el punto de la pila, no con su resultado futuro.
keep_tool:false oculta su objeto sin eliminar el documento. Ciclos entre cuerpos
y borrado de una herramienta usada responden cad_dependency.

### CAD SPLIT

Capacidad `cad.features: SPLIT`. `cad.plane.begin` acepta `split_body_id` y
`keep: BOTH|ABOVE|BELOW` (BOTH inicial); `base` y `plane_id` son los del colocador.
`cad.plane.update` conserva offset/tilt/shift/gestos y admite `keep`.
La sesión es `SPLIT`, publica `session.plane` y `operation_controls`; el plano
se dibuja en GPUOffScreen. Confirmar/cancelar usan `cad.session.*`.

Nodo: `{id,type:SPLIT,name,order,body_id,sketch_id:null,enabled,plane,offset,keep}`.
`plane` es un ID de plano guardado o `{origin,normal}` en metros; `offset` sigue
su normal. BOTH añade `derived_body_id` y un cuerpo con
`source:{feature_id,side:ABOVE}`. El cuerpo inicial conserva BELOW; el derivado
arranca desde ABOVE y admite su propia pila. El evaluador publica su tip inicial
como el SPLIT fuente, y conserva internamente su sólido inicial por ID de cuerpo.
La caché incluye el marco resuelto. La barra anterior al corte oculta al derivado.
`cad.feature.set` edita `offset`, `keep` y `enabled`; eliminar dependencias o
retirar una mitad con operaciones falla con `cad_dependency`.

Vaciar una mitad derivada sin operaciones propias usa `cad.extrude.begin` con
`target_id` del SPLIT fuente y `target_body_id` de esa mitad. El backend comprueba
su asociación y conserva el target_id real como dependencia; no persiste IDs de
operaciones ficticias. Sin target_body_id se mantiene el destino habitual.
### CAD sketch trim

Flag `cad.entity_trim: true`. `cad.entity.trim` admite `phase: BEGIN|UPDATE|END|CANCEL`
y `u,v` normalizados en BEGIN/UPDATE. Sin phase equivale a `TAP` (acción completa).
La sesión `TRIM` posee owner/ID, conserva el documento baseline y publica el tramo
candidato en `overlay` (`kind:TRIM`, puntos proyectados, selected:true).
BEGIN/UPDATE no mutan el documento; END consume el último candidato y crea un
undo. CANCEL, desconexión y guardar descartan el candidato; un miss no crea undo.
`cad.session.confirm/cancel` también cierran la sesión. END no vuelve a sondear.
Las coordenadas del overlay nunca se persisten como geometría.

`LINE/ARC` producen hasta dos fragmentos; `CIRCLE` se convierte en `ARC` y
`RECTANGLE` en líneas. NGON/SLOT/GEAR dan un error explícito. Los cutters son las
figuras no constructivas LINE/ARC/CIRCLE/RECTANGLE. Las reglas de extremos
supervivientes se remapean; los nuevos extremos contra rectas reciben
POINT_ON_LINE. Contra curvas quedan libres. Perfiles usados, ejes y centros de
Taladro quedan protegidos con `cad_dependency`; no se borra una operación como
consecuencia de recortar su boceto.

### Vaciar elementos seleccionados de un boceto

`cad.selected_cut: true` anuncia el vaciado de una selección del croquis.
`cad.extrude.begin` acepta `operation:CUT`, `sketch_id` y `entity_ids:[id,…]`,
además de destino/profundidad/extensión habituales. La lista debe ser explícita,
no vacía, sin duplicados y pertenecer a ese boceto. No admite puntos ni
construcción; líneas/arcos deben formar contornos cerrados completos.
La selección puede iniciarse mientras se edita el boceto y abre la misma preview
3D de Vaciar. Confirmar/cancelar conservan el ciclo de `cad.session.*`.

El nodo CUT persiste `profile_id:profile_<sketch_id>` junto a `entity_ids`. Su
geometría se resuelve desde esos IDs, sin copiar entidades al documento ni incluir
los contornos no seleccionados. Un círculo elegido aisladamente produce un disco,
aunque haya otros círculos dentro sin seleccionar; seleccionar ambos contornos
conserva la semántica de región con hueco. La lista también limita el prisma del
lápiz, el fantasma, Hasta cara, Perforar todo y los operandos de Simetría/Patrón.
Las cotas originales siguen gobernando el resultado. Borrar/abrir elementos usados
se rechaza atómicamente; los elementos no usados no se protegen por este vaciado.
Sin `entity_ids`, los perfiles individuales y el boceto completo conservan su
comportamiento anterior. Una lista vacía nunca equivale al boceto completo.

### Edición de croquis con sólido diferido

El documento puede incluir `deferred_sketch_id`: sus dibujos y restricciones ya
están validados y guardados, mientras el objeto publicado sigue siendo la última
evaluación válida. La validación geométrica de perfiles usados de ese croquis se
pospone hasta cerrar la edición; un contorno puede estar abierto temporalmente.
`cad.state.sketch_pending` informa de ese estado. No cambia los IDs de operaciones
ni añade una segunda fuente de geometría.

`cad.sketch.finish` ahora puede suspenderse durante la evaluación del worker.
Evalúa solo hasta `rollback_id`, nunca las operaciones posteriores al puntero.
Retira el marcador tras evaluar/publicar correctamente y registra la actualización
del sólido en undo. Un error conserva el documento pendiente. Si
procede de una operación, `sketch_failure:{feature_id,name,type}` la identifica y
`sketch_review:true` sale a la pila con esa operación seleccionada; la tablet abre
la pila y muestra la última pieza válida. La barra se detiene en el nodo que falla,
también al avanzar después de cerrar el croquis. `cad.history.rollback` fija el
límite solicitado antes de finalizar un croquis pendiente y evalúa ese prefijo;
retroceder permite recuperar una vista válida. Los comandos habituales
`cad.feature.set/delete` corrigen hasta la barra: borrar el nodo de la barra la
sitúa en su predecesor y no evalúa pasos futuros. Las correcciones tienen undo;
solo un avance explícito alcanza las operaciones posteriores. La posición de la
barra se conserva al desconectar/reentrar en CAD. No se borra ni desactiva nada
automáticamente. Un error del propio croquis mantiene su edición.
La capacidad `cad.sketch_failure_recovery` anuncia este comportamiento.
Abrir otro boceto, Vista 3D, operaciones de sólido y salir de CAD
resuelven también la edición pendiente. Guardar conserva el marcador y el sólido
congelado; al cargar y entrar en CAD se reabre el croquis pendiente. Los handlers
de guardado/carga no ejecutan OpenCascade.

### Redondeo arco–línea

`cad.fillet_arc_line:true` amplía `cad.fillet {radius}` a selecciones LINE+ARC
con extremo compartido, además de los casos LINE+LINE/RECTANGLE existentes.
Los extremos explícitos identifican la unión; seleccionar las dos figuras completas
procesa sus uniones comunes. El radio sigue en metros.

El arco nuevo guarda `fillet_kind:ARC_LINE` para distinguirlo del original.
Sus fuentes se reconocen por las coincidencias y tangencias por ID/START/END
existentes (LINE en START, ARC en END), con modo INTERNAL/EXTERNAL
para la tangencia entre los arcos. No guarda puntos de malla ni píxeles. Sus
propiedades usan `is_fillet`, Radio y `cad.fillet.remove` existentes; `CORNER` es
la intersección virtual de la recta y el círculo originales. La inferencia de
redondeos LINE+LINE de archivos antiguos permanece intacta.

### Vaciado que todavía no alcanza material

`cad.extrude.begin/update` con CUT conserva la sesión si OpenCascade devuelve
`cad_cut_miss` para el nodo nuevo. El estado contiene `session.active:true`,
`can_confirm:false`, la profundidad solicitada y una explicación en `error`.
No persiste una operación vacía ni altera el sólido previo; se pueden ajustar
profundidad, `TO_FACE` o `THROUGH_ALL`. Una preview que sí corta habilita Confirmar
y limpia el error. Retroceder a una profundidad vacía restaura el sólido inicial
y deshabilita Confirmar; confirmar ese estado no cancela ni crea undo. Los errores
de otras operaciones y los sólidos inválidos siguen propagándose.

### Selección de varios perfiles mostrados

`cad.profile_multiselect:true` habilita toques aditivos de perfiles en la vista 3D.
`cad.select {u,v,additive:true}` acumula/alterna perfiles del mismo boceto; otro
boceto reemplaza el grupo, un miss lo limpia y seleccionar SKETCH/FEATURE lo
sustituye. `selection.items` contiene todos los PROFILE elegidos; el overlay los
resalta juntos. La selección no abre el editor ni cambia el documento.

`cad.extrude.begin {operation:"CUT",profile_ids:[...],target_id,depth}` resuelve
los perfiles a entidades originales, incluidos los miembros de cadenas cerradas.
Persiste el mismo `entity_ids` de Vaciar selección, sin copiar el croquis. Rechaza
listas vacías, duplicados, perfiles de distintos bocetos y mezclar `profile_ids`
con `sketch_id`, `profile_id` o `entity_ids`. Un único perfil y el boceto completo
mantienen sus entradas existentes. Android anuncia el recuento y no permite
aplicar herramientas de perfil único al último elemento de un grupo.

### Deformación simple

`modifier.add {type:"SIMPLE_DEFORM"}` añade el modificador nativo, inicialmente
TWIST sobre Z con 45°. `modifier.set` admite `deform_method` (TWIST/BEND/TAPER/STRETCH),
`deform_axis` (X/Y/Z), `angle` en grados para TWIST/BEND, `factor` para TAPER/STRETCH,
`limit_lower/limit_upper` entre 0 y 1 ordenados, `lock_x/y/z` y `origin` (nombre de
otro objeto o null). Ángulo y factor comparten almacenamiento en Blender: solo se
escribe la cantidad activa. Validar un cambio precede a cualquier modificación.
Se integra con mover en pila, activar, aplicar, borrar y undo existentes.

Los descriptores de modificadores admiten `value_labels` (valor → texto) y
`visible_when` (parámetro → lista de valores admitidos, todas las condiciones).
Android usa estos metadatos para elegir ángulo/factor y traducir métodos sin
ramas de interfaz propias de Simple Deform. Los campos sin condiciones siguen
siempre visibles; los valores enviados siguen siendo los identificadores nativos.

### Grupos de vértices

`active.vertex_groups:[{name,locked}]`, `active.active_vertex_group` y
`active.vertex_groups_available` describen los grupos del objeto activo.
`vertex_groups.changed` provoca un nuevo snapshot al crear/renombrar/borrar grupos
fuera de la tablet. No se transmiten los pesos completos en cada actualización.

- `vertex_group.create {name,object?}` crea un grupo vacío.
- `vertex_group.rename {name,new_name,object?}` conserva pesos y referencias en modificadores.
- `vertex_group.delete {name,object?}` borra el grupo y limpia esas referencias.
- `vertex_group.edit {name,action,weight?,object?}` requiere Edit. ASSIGN reemplaza
  el peso de los vértices seleccionados (0–1, cero válido); REMOVE quita su pertenencia.
  SELECT reemplaza la selección por los miembros visibles y activa Vértices;
  DESELECT retira esos miembros de la selección. Las coordenadas permanecen intactas.

`object` es una comprobación del objeto activo, no un selector de otro objeto.
Cada comando devuelve un snapshot de escena y tiene undo nativo. Se rechazan
pesos inválidos, asignación a grupos bloqueados, escenas CAD sin convertir y
herramientas modales activas. Los pesos se escriben en el BMesh vivo sin salir de Edit.

SIMPLE_DEFORM admite `vertex_group` (nombre o cadena vacía para todo el objeto) e
`invert_vertex_group`. El campo por esquema de tipo `vertex_group` usa los nombres
del objeto activo; el backend valida su existencia antes de modificar el nativo.

`vertex_group.create {name,assign_selection:true,weight?:1}` guarda directamente
la selección como grupo. `material.group {name,weight?:1}` delega en el mismo
servicio para todos los objetos de pintura y activa `GROUP:<name>`. La validación
de nombres, pesos y selección es compartida; un fallo de validación en un objeto
no crea grupos en ninguno. Android reutiliza el diálogo Guardar selección como
grupo en los dos contextos. `create` sin `assign_selection` conserva la creación
explícita de un grupo vacío para clientes existentes.

### Catálogo buscable y propiedades RNA de Lattice

Cada tipo de `modifier.add_options.types` anuncia `label`; Android busca tanto
ese nombre como el identificador nativo, ignorando mayúsculas/acentos. `LATTICE`
anuncia `source:"RNA"`: sus campos escalares, booleanos, grupo y objeto se generan
desde `bpy.types.LatticeModifier.bl_rna`. El adaptador restringe `object` a LATTICE
y aporta nombres localizados. La lectura, validación y escritura comparten el
mismo camino RNA; valida todos los parámetros antes de modificar el nativo.

`modifier.set {name,parameters:{create_cage:true}}` crea y vincula una jaula 4×4×4
ajustada a los límites evaluados del objeto, con su transformación y sin deformar
inicialmente. Rechaza una segunda jaula y no mezcla esta acción con parámetros.
Es una acción con undo, no una propiedad RNA. Aplicar/borrar el modificador no
borra la jaula. Mover sus puntos desde la tablet no forma parte de este cambio.

La reflexión no convierte todos los 83 tipos nativos de esta versión de Blender
en modificadores soportados: se mantiene el catálogo probado. RNA no proporciona
por sí solo disposición, condiciones de visibilidad, operaciones de creación/
subdivisión/bake ni interfaces dinámicas de sockets. La arquitectura admite nuevos
tipos mediante metadatos y adaptadores, sin otra bandeja Compose por modificador.

### ValleTrack / Gitea

`features.versioning:{version:1,provider:"ValleTrack",gitea:true,lfs:true,ideas:true}` habilita
Archivo → Versiones. `versioning.status {refresh?:true}` devuelve el estado; con
refresh inicia una consulta I/O. `versioning.action` admite `action`:

- `commit {message,pack_resources?:false}` guarda el `.blend` en el pump y crea una versión Git/LFS.
- `explore {revision,label?:""}` guarda el avance del recorrido actual y abre una nueva idea que parte exactamente del commit elegido.
- `switch {branch}` guarda el avance actual y continúa el último commit de una idea existente.
- `restore {revision}` se resuelve como `explore` para clientes anteriores; no mantiene otra implementación.
- `connect {server,access_token,author_name?,author_email?,allow_http?:false}` valida `/api/v1/user` y guarda la cuenta privada.
- `identity {author_name,author_email}` establece autor local; `forget` elimina el token.
- `link {url}` conecta un repositorio de la misma instancia Gitea.
- `create_remote {name}` crea explícitamente un repositorio privado de la cuenta.
- `push`, `pull`: sincronizan todas las ideas. Push es atómico; pull valida divergencias antes de avanzar referencias locales. Nunca fuerzan ni mezclan un conflicto binario.
- `clone {url}` descarga un repositorio de esta integración y abre `model.blend`.

Las respuestas son estados inmediatos `{available,busy,action,source,repo_id,
ready,local_path,branch,remote,lfs_available,scene_dirty,file_changed,ahead,behind,
account,commits,message,error}`. `account` contiene servidor, usuario, autor y
`has_token`, nunca el secreto. `commits` contiene `{id,date,message,author,parents}` del recorrido inspeccionado.
`branches:[{name,tip,label,active,base}]` enumera las ideas; `head`, `branch` y
`primary_branch` identifican el estado activo. `history_branch` identifica el
historial mostrado y puede cambiarse con `versioning.status {refresh:true,
history_branch}` sin cargar otra escena. Se muestran hasta 100 pasos por recorrido.
El evento `versioning.changed` y las consultas sin refresh actualizan el progreso.
El cliente refresca también archivo/escena al completar una acción. Las versiones
usan el mismo proyecto al Guardar como (ID en la escena), y un almacenamiento
independiente del Git del directorio donde vive el archivo de trabajo.


### Coherencia de superficies y selección (octubre 2026)

Android usa siempre selección múltiple, sin conmutador: `TOGGLE` en Objeto y
Edición y `additive:true` en Materiales/CAD. Tocar añade o quita lo tocado; un
toque vacío limpia toda la selección, también en boceto y referencias CAD. El
fin de un gesto de cursor usa el último candidato y no repite el sondeo.
`transform.select` permite vaciar: confirma el paso estable si cambió geometría,
limpia la selección y cierra la sesión; sin cambios no crea un undo vacío.
«Camino» es una acción independiente de Edit. Caja/Círculo/Pintar conservan sus
operaciones de región; un trazo de pintura vacío no se interpreta como un toque.
`cad.select_all` acepta también `INVERT` y `selection.box` / `selection.circle` seleccionan por
región en el contexto CAD. Pintar conserva un baseline y alterna cada referencia
una vez por trazo; cancelar lo restaura. Las restricciones geométricas se crean
en el rail y las cotas desde las medidas de la bandeja; su candado alterna la cota.

`cad.view.frame {}` encuadra el boceto abierto o la pieza CAD activa con la cámara
remota. `cad.entity.delete {profile_ids:[...]}` elimina los contornos seleccionados
del mismo boceto y valida sus dependencias antes de guardar. No modifica otros perfiles.
`view.local {enabled,objects?:[nombres]}` permite aislar el objeto tocado sin cambiar
la selección. CAD comienza mostrando la escena: `cad.settings {show_scene:false}`
aísla la pieza activa y `true` restaura la visibilidad previa. La entrada en CAD
por sí sola ya no aísla; la acción vive en el radial, como en los demás modos.


### Seleccionar similares

`selection.similar {type, threshold?:0.01}` añade a la selección de Edit los
vértices, aristas o caras coincidentes con el criterio nativo de Blender.
`threshold` está entre 0 y 1 y usa la tolerancia nativa de ese criterio.
`edit_catalog.groups[modo]` anuncia `SELECT_SIMILAR` y sus variantes; cada ID
se envía como `type`. El backend rechaza criterios de otro submodo, selección
vacía y sesiones activas. Conserva geometría y ocultos; un cambio de selección
crea un undo. Android lo ofrece únicamente en el rail de selección, junto a
Loop/Ring/Enlazado. Camino más corto usa un icono, sin abreviatura visible.


### Cierre de herramientas y primer Corte de loop

`tool.begin {tool:"LOOP_CUT",parameters:{...}}` sin `edge` deselecciona y devuelve
`armed:true, active:false`; el primer `tool.loop_pick` válido crea la preview
centrada. Android utiliza ese flujo sin sondeos de selección diferidos. Los
clientes que ya conocen una arista pueden seguir enviando `edge` explícito.
`tool.parameter` con `factor` o `slide_distance` conserva el número exacto aunque
el gesto tenga snap por incremento. `tool.nudge` continúa aplicando ese snap.
`tool.cancel` y `transform.cancel` sin sesión son cierres idempotentes.
Android invalida respuestas, nudges y sondeos pendientes al cerrar/cambiar
herramienta, cambiar modo y pasar a segundo plano; errores de sesión vuelven a
un estado local inactivo y solicitan un snapshot nuevo.

`mesh.looptools_space {}` usa Espaciado del add-on LoopTools nativo, con dos o
más vértices elegidos en Vertex/Edge. `mesh.looptools_circle {}` requiere tres.
Ambos se anuncian condicionalmente en `edit_catalog` y registran un undo propio.
Android los agrupa en radial → Malla → LoopTools.


### Bandejas compactas de herramientas

Los controles de `tool.status.controls` pueden anunciar `primary:bool` y
`help:string`. Android muestra como máximo tres controles principales por esquema
(más el acceso a Más); si un servidor anterior no indica ninguno usa el primero.
El panel Más contiene el resto, con la explicación publicada. Los controles
numéricos comparten editor de expresiones y unidades, sin selector de unidad.
El inventario `toolTrayContents` limita a cinco grupos la fila de cada herramienta.

La posición de Loop Cut se muestra como porcentaje desde el centro (`0 %` es
`factor:0`); introducir una longitud se convierte por `slide_range` métrico.
`tool.parameter` conserva números exactos para Extruir/Bisel/Inset y posición de
fusión de Bridge incluso con snap. El nudge usa el snap; en Bridge fusionado mueve
`merge_factor` y, sin fusión, `twist_offset`. `primary` no cambia la geometría ni
la semántica del contrato de confirmación/cancelación.
