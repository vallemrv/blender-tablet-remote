# Blender Tablet Remote — guía de trabajo

## Objetivo

La tablet Android es una interfaz táctil para Blender, no un escritorio remoto.
Blender conserva el motor 3D; Android muestra una cámara remota y envía intención
adaptada a dedo y stylus. El alcance actual es Object Mode, Edit Mode, Sculpt
(`docs/sculpt-workspace.md`), CAD paramétrico (`docs/cad-workspace.md`) y Materiales
(`docs/material-workspace.md`).

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
  en el hilo principal de cada proceso. El proceso interactivo publica mediante
  `bridge._pump()`; CAD evalúa snapshots en un Blender auxiliar aislado, sin abrir
  la escena del usuario ni compartir referencias RNA.
- Android tiene una única superficie de entrada en `ui/InputSurface.kt`.
- Tweak en Edit selecciona y arrastra vértices, aristas o caras con un gesto; conserva
  el grupo al tocar un elemento seleccionado. Un toque sin arrastre no mueve ni crea
  undo. Otra herramienta o repetir su botón desactiva Tweak; sus eventos pendientes
  nunca modifican una transformación posterior. En caras usa movimiento libre.
- H.264 se decodifica sobre una `Surface`; MJPEG se decodifica a Bitmap.
- Cada conexión H.264 crea un decoder nuevo y empieza en SPS/PPS + IDR, incluso
  con la misma resolución. Las generaciones invalidan paquetes, callbacks y
  reintentos anteriores. La cola Android se limita antes del Handler (seis AUs,
  150 ms); una pérdida descarta el GOP y vacía el codec hasta otro IDR. Se decodifican
  las referencias y se presenta solo la salida más reciente, sin esperar otro paquete.
  Al volver de segundo plano se recrea la Surface si hubo fallback; recibir dimensiones
  no significa haber decodificado. Pausar/cerrar cancela también el HTTP de MJPEG.
  El servidor conserva las ráfagas H.264 pero abandona colas de más de 250 ms hasta
  un IDR fresco; una escritura bloqueada un segundo retira al cliente suspendido.
- Leer el estado CAD reutiliza el JSON ya validado y su documento público mientras
  sean idénticos. Cada lector recibe copias independientes; el contenido completo,
  no solo la revisión, invalida previews. Cambio de escena/undo/carga invalida por
  identidad y JSON. La caché nunca guarda RNA ni overlays dependientes de la cámara.
- H.264 usa longitudes de paquetes FLV solo en la tubería privada de ffmpeg para
  publicar cada AU completo sin esperar al siguiente fotograma; Android sigue
  recibiendo Annex B con SPS/PPS en cada keyframe. Configuración/metadatos no
  consumen marcas de captura. Los NAL se localizan con búsquedas nativas de bytes,
  sin recorridos Python por byte. El pump respeta el próximo vencimiento de captura descontando el tiempo
  de dibujo; sin vídeo conserva la cadencia de control. No se descartan AUs por ello.
- El contrato canónico está en `blender-backend/docs/protocol.md`.

## Capacidades principales

- Conexión, reconexión, estado de escena, objetos, archivos, undo y redo.
- Explorador remoto de archivos con ubicaciones y tokens opacos.
- Object/Edit y selección Vertex/Edge/Face.
- Sculpt nativo: nueve pinceles esenciales, suavizado/inversión, presión, simetría,
  máscaras, Dyntopo y Multires. Referencias de imágenes persistentes en la tablet.
- Picking, Box, Circle, Loop, Ring, shortest path y Tweak.
- Navegación orbital, vistas, cámara remota, wireframe y xray.
- Move/Rotate/Scale con sesiones reversibles, restricciones, orientación, valores,
  unidades, snap, referencias geométricas y edición proporcional.
- Herramientas Edit paramétricas: Extrude, Bevel, Inset, Subdivide, Loop Cut, Bridge,
  Knife y Bisect.
- Catálogo contextual Edit, modificadores, sombreado, aislamiento y escala de trabajo.
- Alinear caras en Object: contacto entre caras, orientación de caras y copia de
  rotación del objeto destino, con preview reversible.
- H.264 preferido con fallback MJPEG.
- CAD v1: planos XY/XZ/YZ y cara superior asociativa, líneas, rectángulos (cuadrado =
  rectángulo con Igualdad), polígonos regulares (`NGON`), ranuras (`SLOT`), engranajes (`GEAR`),
  círculos, arcos, polígonos irregulares, redondeo de sketch, selección de puntos/aristas
  y restricciones.
  Extrusión de perfiles cerrados, vaciado por profundidad con incrementos y redondeo/chaflán
  de varias aristas del sólido. Documento JSON
  persistente en `.blend`, árbol, preview reversible y conversión explícita a malla.

## Invariantes técnicos

- Una sesión modal siempre reconstruye su preview desde el baseline original y produce
  un único paso de undo al confirmar.
- `ACTION_UP` confirma el último candidato visual estable; no repite el raycast.
- Un punto sondeado sobre una preview debe convertirse al baseline antes de persistirlo,
  salvo un centro de Rotate/Scale que deba permanecer estacionario.
- Las sesiones `transform.*` y `tool.*` son mutuamente excluyentes.
- Undo, redo y borrados cierran primero cualquier sesión activa.
- Círculo de LoopTools ejecutado desde el pump registra explícitamente un undo;
  deshacerlo conserva los Loop Cut ya confirmados.
- El toque de Loop Cut elige el anillo y crea el corte a mitad de arista (Posición 0 %); cada nuevo
  corte comienza sin desplazamiento. La bandeja permite porcentaje o mm/cm/m desde
  el centro; mantener pulsada la Posición vuelve al centro. Las medidas físicas incluyen la escala del
  objeto y de escena; los cortes múltiples conservan su espaciado al desplazarse.
- El toque de Loop Cut sondea la jaula viva del BMesh (no la malla evaluada, cuyos
  índices cambian con Mirror/bisect u otros modificadores); otros objetos solo ocluyen.
- Con Corte de loop armado o activo, el lápiz que flota (sin tocar) envía
  `tool.loop_hover` ~15 veces por segundo: Blender sondea igual que el toque y dibuja
  en GPUOffScreen el corte central del anillo en amarillo. No cambia malla, selección
  ni undo; alejar el lápiz, tocar, cerrar o desarmar retiran la preselección.
- Activar Corte de loop deselecciona la malla y solo arma la herramienta. El
  primer corte exige un toque válido en el visor; nunca usa una selección previa.
  Deslizar sobre Posición acumula pasos de 1 % sobre el valor local pendiente. La
  escritura y el deslizamiento envían posición exacta incluso con Incremento; el arrastre conserva
  el snap y el paso métrico fino se adapta al recorrido del corte.
- Al cambiar herramienta/modo, cancelar o pasar a segundo plano, Android retira
  las respuestas y colas de la interacción anterior. Cierra también herramientas
  armadas y aperturas todavía en vuelo. Los cierres sin sesión son idempotentes;
  un inicio fallido vuelve a Seleccionar y no mantiene entradas de una preview.
- LoopTools nativo ofrece Círculo y Espaciar en radial → Malla → LoopTools,
  solo con vértices/aristas y cuando el add-on está habilitado. Cada operación
  registra un undo explícito; Círculo conserva los cortes previos al deshacer.
- El campo de posición de Loop Cut permite un borrador vacío en % y mm/cm/m;
  las actualizaciones remotas no lo rellenan mientras se escribe. Vacío no envía valor.
- Las referencias RNA inválidas nunca deben detener el pump ni el broadcast.
- El explorador identifica cada fila por nombre y ruta: varios enlaces simbólicos
  pueden compartir un destino canónico sin ser la misma entrada de la lista.
  Guardar como ofrece Nueva carpeta (icono carpeta +); crea un solo hijo del destino
  visible, entra en él y conserva el nombre del archivo. Rechaza rutas y colisiones,
  muestra errores dentro del diálogo y no repite solicitudes pendientes. Respuestas
  de exploraciones anteriores no sustituyen la carpeta recién creada.
- Knife acumula puntos interiores y divide una cara una sola vez en dos n-gons. No se
  sustituye por triangulación punto a punto. Sondea el BMesh vivo y admite n-gons
  cóncavos de cortes previos; cada segmento recorre la superficie y nunca el volumen.
  Sus tolerancias de distancia son relativas al tamaño de la malla (1e-5): en piezas
  milimétricas grandes el error float32 del sondeo superaba la tolerancia absoluta y
  ningún trazo cortaba. Las fracciones a lo largo del segmento siguen siendo 1e-6.
  Su snap Auto prefiere el vértice cercano y si no el punto de la arista bajo el dedo;
  el centro de arista solo gana casi encima (1 % del ancho), para dirigir el corte.
- El cierre de Tweak identifica `tweak_finished`; Android retira únicamente esa
  sesión MOVE interna y conserva cualquier transformación posterior.
- Las respuestas UPDATE de Tweak describen una transformación (`mode: MOVE`), no
  una escena. Android solo actualiza la escena desde sus snapshots explícitos;
  el arrastre nunca cambia el selector Edit/Object ni cancela su propia entrada.
- El snap táctil filtra primero por geometría visible y después clasifica el candidato.
- El snap de Knife comprueba primero la oclusión propia con el BVH del BMesh vivo.
  Ordena candidatos por distancia y consulta la escena solo hasta encontrar el
  competidor visible más cercano, además del candidato retenido. Conserva la
  política pegajosa común, la prioridad de puntos sobre aristas y END sin raycast;
  no cambia el snap de Mover ni mantiene cachés de geometría entre actualizaciones.
- Mover sin snap sigue al dedo continuamente; con Incremento avanza en saltos táctiles
  perceptibles y no reutiliza la misma sensibilidad del movimiento libre.
- Un preset de escala de trabajo nunca reescala geometría ni modifica `scale_length`.
- La rejilla adopta el paso físico del preset al crear la escena, cargar y arrancar.
  Se aplica sobre `area.spaces.active.overlay` y la conversión nativa de
  `grid_scale_unit` evita dividir dos veces por `scale_length`. Durante GPUOffScreen
  su alcance usa el clipping y la distancia de la cámara de la tablet; restaura
  siempre `space.clip_end` del PC y nunca modifica `rv3d`.
- Al crear primitivas, `primitive_size` expresa metros y se divide por el
  `scale_length` vigente antes de llamar a Blender. El cubo de Pequeña mide 10 mm,
  también en archivos donde una unidad Blender equivale a un milímetro. El cubo
  de Mediana mide 50 cm y el de Grande 1 m. Nueva escena crea ese mismo cubo
  desde cero, sin heredar geometría del archivo de inicio, y deja margen de vista
  para ver la rejilla; Encuadrar/doble toque conserva el 85 %.
- Al abrir una escena, el preset mostrado se deduce de su `length_unit`; nunca se
  anuncia Mediana por defecto si el `.blend` está en milímetros o metros.
- Rotar y Escalar recuerdan el centro de Referencias entre operaciones y reinicios
  de Android. Cursor 3D y Origen del objeto se resuelven al iniciar cada operación;
  Punto medio usa la selección vigente. Un punto señalado conserva coordenadas
  mundiales y solo se reutiliza en la misma escena. Cambiar la selección durante
  una transformación Edit conserva también esa intención. Mover y los cierres de
  sesión nunca sobrescriben el centro elegido, tampoco si se confirma antes del ACK.
  Señalar punto mantiene el centro anterior hasta fijar otro candidato válido.
  Orígenes individuales rota/escala
  cada objeto alrededor de su origen; en Edición usa los operadores nativos para
  los centros de vértices, aristas, caras y curvas. Cada preview restaura primero
  su baseline completo, sin undo intermedio ni cambios persistentes en el pivote
  del PC. Individuales ofrece Libre/Incremento y no una fuente geométrica común.
- La cámara remota no escribe en `rv3d`.
- El zoom ortográfico conserva la profundidad alrededor del pivote: acercarse no
  recorta la cara delantera al atravesar la posición nominal de la cámara. El doble
  toque en Object y el botón Encuadrar encuadran los límites del objeto al 85 % de la vista según orientación y
  proyección reales, también si el PC está en ortográfica.
- CAD → radial → Crear malla del dibujo copia las figuras seleccionadas del mismo
  boceto, o el boceto sin construcción si no hay selección, como un objeto de
  vértices/aristas sin caras. Círculos y arcos permiten resolución (64 por vuelta,
  3–4096); líneas, rectángulos y polígonos conservan sus puntos. La UI oculta
  resolución si no hay curvas. Conserva plano, medidas y JSON CAD; sale a Objeto
  con la copia seleccionada, sin etiquetas paramétricas, y crea un undo. Revisión
  e identidad validan el diálogo. No evalúa sólidos ni finaliza un croquis pendiente.
- En Edición, el rail izquierdo EDITAR ofrece Spin · Revolución con la operación
  nativa existente: ángulo, pasos, eje y centro inicial en el cursor 3D. Se anuncia
  como familia REVOLVE de `edit_toolbar`, para vértices/aristas/caras; el filtro
  común evita duplicarlo en radial → Malla. El rail no envía centros por defecto
  que sustituyan el cursor 3D.
- F2 es una herramienta continua de cuadriláteros del rail izquierdo de Edición,
  construida con BMesh y sin depender del add-on externo. Tocar vértices alterna
  selección; tocar una arista elige sus extremos. Tocar fuera con una esquina
  válida añade un vértice, con dos vértices/arista añade dos y con tres añade uno:
  siempre una cara de cuatro vértices. El mismo gesto coloca los vértices nuevos
  hasta soltar; después quedan seleccionados esos vértices, o su arista frontal
  en submodo Aristas. Tocar el cuarto vértice completa automáticamente la cara;
  si ya existe, extiende su arista de borde más cercana al toque con un quad nuevo.
  Con una arista cuyos extremos ya salen por aristas libres hacia dos vértices de
  enfrente (fuera de su cara), F2 solo crea la arista frontal y la cara, sin vértices
  nuevos; el toque elige el lado si hay varios y queda seleccionada esa arista.
  Un gesto que empieza sobre un vértice y recorre más de 0,012 de alto de vídeo lo
  mueve en el plano de la vista (Tweak dentro de F2): parte del baseline, conserva la
  selección previa, no crea caras y registra un undo al soltar; cancelar lo restaura.
  Un toque corto sobre el vértice sigue alternando su selección.
  Cada gesto congela su intención al comenzar. UP confirma el último candidato
  válido sin raycast ni nuevo movimiento, con un undo por cara. Una preview
  degenerada conserva la última válida. Repetir el botón o × desarma; dos dedos,
  navegador, cambio de herramienta, desconexión y guardado restauran el baseline
  pendiente. IDs y propietario impiden cierres atrasados/ajenos. No abre un modal
  de transformación del PC ni modifica rv3d.
- CAD es un workspace; Blender permanece en Object. Sus longitudes son metros y
  se convierten a unidades Blender al materializar. IDs y revisión pertenecen al
  documento; la malla evaluada no es la fuente ni admite Edit sin conversión explícita.
- Las previews CAD también son excluyentes con `transform.*` y `tool.*`; confirmación
  crea un undo, cancelación/desconexión restaura y guardar descarta la preview.
- CAD usa la misma entrada y vídeo. El overlay de sketches se proyecta en backend
  y se dibuja en el rectángulo del vídeo en Android; no persiste píxeles como geometría.
- La acción Aislar del radial CAD aísla temporalmente la pieza elegida y restaura
  la visibilidad previa al desactivarla o salir. Los `.blend` y estados de undo conservan la visibilidad de la escena.
- La migración CAD ha terminado: OpenCascade (`cad/occt.py`) es el único motor
  de sólidos y OCP es obligatorio. Vive en un directorio privado
  (`~/.local/share/blender-tablet-remote/occt`, `tools/install_occt.sh`) y solo lo
  carga el proceso evaluador. Si falta o no puede cargar, CAD devuelve
  `cad_kernel_missing` con la instrucción de ejecutar ese instalador; nunca recurre
  a malla. No hay selector «Motor CAD» ni variable de entorno para elegir motor.
  Construye sólidos BREP exactos (barrido por tramos extruidos/revolucionados,
  helicoidal con pipe binormal, solevado, redondeo/chaflán y carcasa) y publica mallas
  en metros para visualización: caras planas sin huecos como polígonos, curvas en
  triángulos. La malla evaluada nunca sustituye al documento como fuente.
  Los booleanos prueban primero una tolerancia difusa de 1e-5 de la pieza, porque
  los documentos traen ruido micrométrico; el exacto y otra mayor son reservas.
  Las caras coplanares se unifican solo si el resultado sigue siendo válido; si
  la limpieza invalida una unión o un redondeo/chaflán válido se conserva el BREP
  previo. Los acabados nunca aceptan un resultado nativo inválido como reserva. Las aristas
  se emparejan por geometría (rectas sobre su recta infinita con solape).
  Si un redondeo falla al encontrarse con otro radio, admite un único reintento
  sobre una copia BREP con caras unificadas y topología reparada dentro de la
  tolerancia geométrica. Valida el sólido y limita el cambio de volumen; nunca
  reduce el radio solicitado ni modifica el predecesor guardado en caché.
  `cad/evaluation.py` y las operaciones de sólido de malla están retirados.
  `cad/kernel.py` conserva utilidades geométricas compartidas y `ExtrusionPreviewCache`,
  el prisma ligero del lápiz; no evalúa la pila ni ofrece un motor alternativo.
  `cad/jobs.py` despacha snapshots al evaluador OpenCascade o al solver NumPy.
  Todas las pruebas CAD se ejecutan con OpenCascade, sin selector. Cada herramienta
  nueva implementa su geometría de sólido únicamente en `cad/occt.py`; queda sin
  efecto la regla 5 de dos kernels del encargo `tareas-codex-cad-impresion3d.md`.
  El solver NumPy mantiene las restricciones anunciadas y hasta 300 parámetros.
  No se anuncia STEP ni el solver completo de FreeCAD. La evaluación histórica de
  alternativas está en `docs/cad-kernel-evaluation.md`.

## Sistema de trabajo

- No se crean planes de trabajo.
- Solo existe una incidencia activa.
- Encargos por lotes: cuando el usuario (o otro bot de Valle en su nombre) entrega un
  documento de encargo con varios puntos y pide hacerlo todo, se implementan todos en la
  misma entrega, sin pedir aceptación entre puntos. En ese caso no aplican «una
  incidencia activa» ni «no rediseñar asuntos adyacentes» para lo que el documento
  describe; sí un commit por punto, tests en verde y un único APK al final.
- Estado de encargos (2026-10-20): no hay ningún encargo por lotes vigente. Entregados:
  `~/proyectos/tareas-codex-cad-impresion3d.md` (las 6 herramientas CAD),
  `~/proyectos/tareas-ui-coherencia-blender.md` (A–E, 19-10),
  `~/proyectos/tareas-ui-bandejas-blender.md` (0.1.7) y
  `~/proyectos/tareas-ui-bandejas-calmadas-blender.md` (bandejas tranquilas para lápiz,
  0.1.18). Pendiente del usuario: probar en la tablet las bandejas tranquilas. Al recibir un encargo nuevo, anotarlo aquí
  y moverlo a entregados al cerrarlo. La ficha de la wiki es
  `~/wiki-proyectos/proyectos/blender-remoto.md`.
- Cada cambio debe ser pequeño y centrado en el comportamiento comunicado.
- No se aprovecha una reparación para rediseñar o corregir asuntos adyacentes.
- Cuando el usuario comunica un fallo distinto después de recibir una entrega, la
  incidencia anterior se considera aceptada salvo que diga expresamente que continúa.
- Una incidencia aceptada se consolida y se commitea antes de comenzar la siguiente.
- El código diagnóstico temporal se retira al cerrar.
- No se mantienen caminos antiguo y nuevo para una misma función.
- Las decisiones duraderas se resumen aquí; Git conserva el historial.
- APK y ZIP se compilan desde el mismo estado cuando cambia el contrato entre ambos.
- Cada entrega Android incluye automáticamente el APK por el chat de Valle Bots.
  En Blender remoto no se usa Telegram, salvo petición explícita posterior del usuario.
- El add-on se instala en este Manjaro: el agente instala la versión entregada y
  reinicia Blender, guardando antes y reabriendo la escena actual. Esta tarea ya
  está autorizada; no se delega al usuario ni se pide confirmación de nuevo.
  El usuario instala únicamente el APK en su tablet.
- Después de reiniciar, se verifica que `scene.get_state` incluya `view` y que
  llegue un fotograma real; abrir los puertos no basta. No guardar una escena con
  la consola temporal sustituyendo su vista 3D. En despliegues se usa el protocolo
  para guardar, sin enviar teclas a una pantalla bloqueada.

## Criterio de diseño escalable

### Coherencia de los cuatro bordes

La interfaz comparte una estructura estable entre Object, Edit, CAD, Sculpt y
Materiales. El contexto decide qué acciones se muestran, pero no inventa otra
disposición ni otra forma de manejar el mismo control. Estas reglas guían las
nuevas superficies y la adaptación gradual de las existentes.

| Zona | Responsabilidad |
| --- | --- |
| Rail izquierdo | Herramientas de uso frecuente que cambian la intención del gesto: seleccionar, mover, rotar, escalar, Tweak y herramientas propias del modo. Permanece abierto; admite desplazamiento vertical cuando haga falta. |
| Rail derecho | Columna común SELECCIÓN (RESTRICCIONES geométricas dentro del boceto CAD) y acceso a inspectores contextuales: modificadores, pila CAD, biblioteca de materiales y sus propiedades. Comparten posición, márgenes, apertura y cierre; respetan el selector de modos y el pie de vistas. |
| Barra superior (top) | Archivo, Escena, Outliner, conexión y Diagnóstico a la izquierda; Wireframe, Deshacer, Rehacer y Ojo a la derecha. El selector de modos conserva su lugar bajo el ojo y deja CAD siempre al final. |
| Barra inferior (bottom) | Parámetros de la herramienta activa o propiedades del objeto seleccionado. Una fila fija sin scroll (`SingleLineTray`): valor principal o X/Y/Z, 1–2 iconos y «⋯ Más» con Precisión · Referencia · Forma. |

- Una acción conserva nombre, icono y comportamiento en todos sus accesos. Se
  obtiene el símbolo por intención desde `AppIcons`; una intención distinta debe
  ser reconocible por su forma, no solo por su color. Las ayudas al acercar el
  lápiz explican el propósito sin activar la acción.
- No duplicar una acción entre rail y bandeja dentro del mismo contexto. Los
  catálogos completos y las operaciones menos frecuentes viven en menús o
  inspectores; el viewport debe seguir siendo la superficie principal.
- Las cuatro zonas usan los componentes, tamaños táctiles, espaciado, tipografía,
  colores de eje y estados activo/deshabilitado del sistema común. No crear
  botones o campos parecidos a mano para cada herramienta o workspace.
- En bottom, el título es breve y no envuelve. Las secciones de propiedades se
  eligen con un desplegable y muestran únicamente sus campos; no mezclar todas
  las secciones como pestañas más controles en la misma fila.
- Bandejas tranquilas (encargo 2026-10-20, sustituye a la fila desplazable anterior):
  - Icono = acción o interruptor, de `AppIcons`, sin texto pegado; texto = solo
    números, unidades y el título. Un estado con varias opciones es el icono de la
    opción activa (`ChoiceIcon`): perfil de caída, esquinas, orientación y snap. La
    restricción usa los botones Libre · X · Y · Z siempre visibles (`AxisConstraintButtons`,
    por petición del usuario): tocar un eje lo deja solo (otra vez, Libre) y mantenerlo
    bloquea los otros dos, como Shift+Z en Blender (mantener Z = plano XY). No hay pastillas
    «etiqueta: valor». Color = estado (acento activo, gris inactivo; ejes R/V/A).
  - Todo control táctil mide 48 dp (`Metrics.Touch`): iconos, campos, pasos, ×/✓.
  - Fila fija sin scroll: `[Nombre] [valor/ejes] [icono][icono] [⋯] … [×][✓]`.
    `TrayRow` mide antes nombre, Más y salidas, que nunca se desplazan.
    «⋯ Más» (`TrayMore`) es un panel vertical sobre la bandeja con los grupos fijos
    Precisión (snap, paso, unidad), Referencia (centro, orientación, fuente, propio,
    otra selección, destino, ejes) y Forma (proporcional, radio, perfil y opciones
    propias); cada opción (`TrayOption`) tiene nombre, control y una frase.
  - Números (`ScrubNumber`): deslizar en horizontal avanza pasos enteros del paso o
    snap activo (14 dp por paso, el primero al superar el umbral táctil); tocar
    escribe con cuentas; mantener restablece al neutro (0, 0°, 100 %, centro) si lo
    hay. El nombre corto y la unidad van dentro del campo. Confirmar suelta el foco.
    Ningún número de la app tiene botones `−/+`: pasos de «⋯ Más», modificadores,
    grupos de vértices y diálogos también se deslizan (`ScrubNumber`, `ScrubRow`).
    El puerto de conexión solo se escribe.
  - Bajo la fila: un aviso de bloqueo/error (siempre), un estado vivo (medidas,
    candidato de snap, qué señalar; siempre) y la ayuda solo las tres primeras
    apariciones de cada bandeja (`TrayHints`); después queda en el hover del título
    y en la cabecera de Más. Las propiedades inmediatas no muestran salidas; las
    previews mantienen Cancelar/Confirmar fijos. Los paneles vecinos reservan la
    altura medida de cada bandeja (Edit, Tweak, Escultura y Materiales incluidos).

- La selección múltiple está siempre activa en Objeto, Edición, Materiales y CAD,
  sin conmutador «＋ Añadir»: tocar añade, tocar un elemento seleccionado lo quita
  y tocar el vacío deselecciona todo. En una transformación Edit, vaciar confirma
  el paso visual estable y cierra la sesión, sin crear undo si no hubo movimiento.
  El doble toque de Edit conserva loop/enlazado; «Camino» arma el siguiente toque
  de camino más corto. Caja, Círculo, Pintar, Todo/Ninguno, Invertir,
  Loop/Ring/Enlazado, Similares y Crecer/Decrecer solo viven en el rail derecho.
  Camino usa su icono de recorrido, sin pastilla de texto. Loop y Ring se ofrecen
  en Aristas/Caras y permanecen visibles, deshabilitados si falta selección.
  Similares abre criterios nativos por submodo (conectividad, longitud/dirección,
  área/material/normal, etc.), anunciados por el backend; añade coincidencias,
  respeta ocultos y registra un undo solo si cambia la selección. Seleccionar
  también se activa desde ese rail; el radial nunca selecciona.
  Pintar selección mantiene visible el navegador azul de órbita. Su zona captura
  el gesto antes de comenzar el trazo, no cambia la selección y deja Pintar activo
  para continuar desde la nueva perspectiva.
- Escena → Cursor 3D → A la selección coloca el cursor en la selección de Edit.
  Escena → Snap selección → Al cursor envía los vértices o puntos/tiradores de
  curva elegidos al cursor con el operador nativo, conservando la matriz del
  objeto y los elementos no seleccionados. Cierra previews primero y crea un
  undo. En Objeto mantiene el movimiento de los objetos completos.
- El radial concentra Ocultar, Aislar, Duplicar, Renombrar y Borrar según contexto;
  en CAD también Soldar. Outliner conserva su ojo. Las listas CAD seleccionan;
  las restricciones se ven y borran en la pila. El rail de boceto crea solo
  restricciones geométricas; las cotas (incluidas entre dos elementos) nacen de
  la bandeja. El candado alterna la cota y Fijar punto usa una chincheta.
- Nuevo plano, Editar y Finalizar boceto pertenecen al rail izquierdo CAD. El pie
  de vistas permanece en el boceto con Girar 90°, Enderezar, proyección y Encuadrar.
  CAD no aísla automáticamente: Aislar del radial conserva/restaura la visibilidad.
- Proporcional vive en «⋯ Más» · Forma de Tweak/Transformar; Auto Merge y Manipulador en
  el rail derecho. Los atajos Edit no repiten Cuchillo ni acciones del radial.
- Los rails izquierdos comparten centrado vertical y cabeceras contextuales:
  HERRAMIENTA/EDITAR, PINCEL, MODO/TRAZO y CROQUIS/OPERACIONES. Referencias se
  abre desde un icono a la derecha, bajo los modos, con los márgenes del inspector.
  Su ajuste local se llama Restablecer, sin confundirse con Encuadrar la escena.
  El tablero abierto es la última capa del workspace, por encima de rails,
  inspectores, menús y avisos; sus zonas transparentes también capturan sus gestos.
  Se arrastra por la cabecera a toda el área útil, limitado solo por el tamaño real
  de la ventana y la pantalla. El acceso cerrado no aparece sobre una pila CAD o
  panel de modificadores abierto.
- Todos los modos usan iconos y nombres españoles: Objeto, Edición, Materiales,
  Escultura y CAD al final. Dentro de CAD se conserva el selector completo;
  los modos incompatibles con la pieza paramétrica permanecen deshabilitados.
- La bandeja CAD usa SingleLineTray y TrayExits: la fila lleva medidas deslizables,
  candados de cota (glifo propio `DIMENSION_LOCK`, distinto del candado del Outliner)
  e iconos de acabado. Extensión, Hasta cara, Sentido, Lado, Medida radio/diámetro,
  ejes, Destino, Planos guardados, Inclinar/Mover del plano, tipo de cota, Snap y
  Paso viven en «⋯ Más». Los errores son el aviso fijo y las medidas el estado;
  la ayuda contextual sigue en el hover del título. Finalizar boceto y Aplicar
  modificador tienen iconos propios distintos de Confirmar.

- Las bandejas Edit conservan su reparto de controles directos con el lenguaje de
  las bandejas tranquilas: números deslizables e interruptores con dibujo propio
  (`AppIcons.trayToggle`); Snap y Paso siguen en Más · Precisión. `toolTrayContents`
  es el inventario que dibuja y prueba los controles, sin listas paralelas.
  Se mantienen los editores exactos con unidades/cuentas y protección del borrador.
- Loop Cut muestra cortes, posición desde el centro, Seguir la arista, No salir
  de la cara y Suavidad; Perfil solo con Suavidad e Invertir solo con Seguir la
  arista. Bisel muestra Perfil solo con varios segmentos. Extruir muestra orientación
  solo con eje restringido. Inset y Bridge recuperan sus parámetros directos.
- Las herramientas por esquema muestran en la fila números, ejes X/Y/Z (trípode),
  enums de valores numéricos e interruptores con dibujo propio (`SchemaIconControls`);
  las opciones sin dibujo pasan a Más · Forma. Conservan ayuda, etiquetas y rangos.
- Se recuerdan valores confirmados por herramienta/variante, convirtiendo las
  longitudes a metros al guardar preferencias. No se recuerdan IDs, referencias,
  caras elegidas ni la posición de Loop Cut: un nuevo corte empieza centrado.

### Distribución y comportamiento por contexto

- El rail es una superficie limitada para herramientas gestuales frecuentes, no un
  catálogo completo.
- Una acción no se duplica entre el rail lateral y la bandeja inferior en el mismo
  contexto. Se prioriza el espacio de dibujo y el acceso táctil en la tablet.
- El rail de tools permanece siempre abierto, sin botón de cierre ni estado plegado.
  Mover/Rotar/Escalar viven ahí; en Edit añade Tweak.
- Tweak marca únicamente su botón, aunque use una sesión MOVE interna. Mientras está
  encendido muestra ayudas en la bandeja inferior: GG y Snap activables, con paso
  editable para Incremento. GG solo admite vértices/aristas; en caras sigue libre.
  Las ayudas modifican el gesto sin activar otra herramienta ni reabrir Tweak;
  no hay un menú alternativo de ajustes por pulsación larga en su botón.
- Tweak libre hereda la edición proporcional, su radio y perfil desde los ajustes
  de Edit. Su bandeja ofrece Proporcional/Radio/Perfil mediante el mismo campo
  métrico de radio de las transformaciones. Cambiar la influencia conserva el
  arrastre y cancelar restaura también los vecinos; confirmar crea un solo undo.
  GG conserva el deslizamiento de la selección por aristas y no aplica proporcional;
  la bandeja muestra «Proporcional (sin GG)» deshabilitado mientras GG está activo.
- Duplicar vive en el radial. Abre un selector Mover/Rotar y, en Objeto, copia
  enlazada. Recuerda ambas opciones entre aperturas de la app; Edición duplica la
  selección efectiva sin alterar la preferencia enlazada de Objeto. Solo inicia
  la transformación elegida tras confirmar el servidor que creó la copia. Cambiar
  de interacción retira las respuestas pendientes, incluso en las colas de transporte.
  Cancelar la transformación conserva la copia; duplicar y colocar tienen undo propio.
- En Object, el radial agrupa Alinear caras y las acciones de origen bajo Colocar,
  conservando el límite de ocho sectores y el acceso a Borrar. Con un objeto
  seleccionado también ofrece Colocar y Aplicar (Posición/Rotación/Escala/Todas)
  al pulsar el vacío, incluido el centro de un círculo sin caras; su disponibilidad
  no depende de acertar el contorno.
- Alinear caras pertenece a `tool.*`: mueve únicamente el objeto fuente, conserva
  tamaño, fija el destino y reconstruye desde su matriz inicial. Contacto enfrenta
  normales y hace coincidir centros; orientar y copiar rotación conservan el origen
  de la fuente. Confirmar crea un undo; cancelar o desconectar restaura la matriz.
- Sus controles se describen en el estado de herramienta y se dibujan en la bandeja
  común. Las caras fuente/destino y el candidato se dibujan en GPUOffScreen. Navegar
  con dos dedos cancela el sondeo temporal, sin fijar otra cara.
- Debajo del ojo hay un selector horizontal de modos; CAD solo aparece
  si el backend lo anuncia. Sculpt se habilita según `sculpt.available` sobre mallas;
  Layouts se ha retirado. CAD permanece siempre al final del selector; dentro de
  CAD se muestran también los otros modos, con su disponibilidad contextual.
- Sculpt usa pinceles nativos y la cámara remota; nunca escribe en `rv3d`.
  Radio se expresa como fracción de altura del vídeo. La presión real e histórica
  del lápiz gobierna fuerza/radio por separado; cero conserva cero. Solo lápiz es
  el valor inicial, un dedo orbita y dos dedos navegan. Cancelación/palma restaura
  el trazo; UP confirma la última muestra estable sin volver a sondear.
  El tamaño nativo se calcula en pantalla, evitando el mínimo RNA de 0,001 unidades
  de tamaño en mundo. La adaptación de la vista mantiene los trazos fuera del
  near plane del PC y restaura siempre la matriz original del objeto.
- La rejilla y sus ejes se ocultan solo durante la captura Sculpt, conservando
  los demás overlays. Fuera de Sculpt se recuperan sus flags originales, también
  si antes estaban desactivados; guardar y el viewport del PC conservan el estado.
- Invertir y borrar la máscara viven en el menú Malla de Sculpt, sin pulsación
  larga del pincel. Ambas acciones usan el undo nativo.
- La bandeja Sculpt muestra Radio y Fuerza deslizables, Suavizar e Invertir; en
  «⋯ Más» quedan Presión y Solo lápiz (Precisión), Simetría (Referencia) y el
  detalle de Dyntopo cuando está activo, o el nivel Multires y Subdividir cuando
  existe, junto al acceso a Detalle de la malla (Forma).
  Comparte esos controles con Malla. Elegir nivel solo recorre los creados;
  Subdividir añade uno y se deshabilita al llegar a seis, sin salir de Sculpt.
- En Sculpt sobre malla ordinaria, la superficie sólida se invalida tras aplicar,
  cancelar o deshacer el trazo: cambiar coordenadas no basta para refrescar el
  buffer sólido del offscreen. No se llama a `Mesh.update()` sobre la malla base
  de Dyntopo/Multires, cuyo estado vivo pertenece a BMesh/rejillas nativas.
- GPUOffScreen dibuja Multires a su nivel de Escultura, incluidos los desplazamientos
  vivos. Durante la captura se materializan las rejillas nativas como malla evaluada
  mediante `use_sculpt_base_mesh`; el flag original y las rejillas de Sculpt se
  restauran siempre al terminar, también ante errores. No cambia de modo, no aplica
  el modificador y no modifica los niveles de Vista/Escultura/Render ni `rv3d`.
- El historial de lápiz de los pinceles por aplicaciones se remuestrea según su
  espaciado nativo, con corrección de aspecto y presión interpolada. El extremo
  provisional se sustituye entre UPDATE y no se acumula como otra aplicación
  por paquete. Grab conserva su recorrido. END confirma lo ya dibujado.
- El círculo Sculpt tiene su propio contorno opaco con borde negro; nunca comparte
  el Paint que se desvanece tras un toque de selección. Conserva el radio relativo
  al vídeo y la presión de tamaño tanto al pintar como al aproximar el lápiz.
  Su color representa la intención: Suavizar azul, Invertir naranja, Máscara violeta
  y normal blanco, con prioridad en ese orden. Incluye el pincel Suavizar y los
  modificadores de la bandeja/lápiz, también durante hover; durante el trazo conserva
  los modificadores del lápiz fijados al comenzar.
- Los trazos Sculpt llevan propietario e ID; son excluyentes con transform/tool/CAD.
  La preview difiere el commit nativo de undo hasta restaurar la matriz del objeto
  y registra exactamente un paso propio, incluso si el pincel devuelve FINISHED
  sin iniciar trazo sobre la superficie evaluada. Repetir/cancelar nunca deshace
  la entrada en Sculpt ni una selección anterior.
  Cada trazo confirmado aporta un undo nativo. Android limita una petición en vuelo,
  conserva el orden de muestras y cierra el trazo antes de navegar/cambiar intención.
  Dyntopo y Multires son alternativas explícitas, nunca se elimina uno al activar otro.
- Multires también se añade desde el panel general de modificadores. Vista,
  Escultura y Render solo eligen niveles creados; Subdividir añade uno (máximo seis).
  Object y Sculpt comparten la implementación nativa y conservan el resto de la pila.
  El esquema de modificadores describe etiquetas, campos de solo lectura, acciones
  y límites referenciados al estado; la UI no simula niveles inexistentes.
- El modificador Bisel anuncia campos numéricos editables por esquema: Ancho,
  Segmentos, Ángulo y Perfil. Ancho usa mm/cm/m del preset y convierte por
  `scale_length`; Ángulo usa grados. Escribir y confirmar envía el valor exacto,
  sin redondearlo al paso. Los snapshots no borran un borrador, tampoco vacío.
- Multires/Dyntopo respaldan la malla nativa durante el trazo para restaurar
  desplazamientos y topología; sus archivos privados se retiran al cerrar.
  Guardar desde el PC restaura el baseline en `save_pre` y difiere el cierre del
  historial: nunca ejecuta undo dentro de los handlers de guardado/carga.
  La tablet impide rehacer previews canceladas; el redo directo del PC es nativo.
- Referencias es un tablero local con varias imágenes, zoom, desplazamiento y
  opacidad. A opacidad completa tapa los controles que queden debajo, incluidos
  los márgenes de la imagen; bajar la opacidad deja ver el modelo detrás. Importa copias privadas acotadas y conserva los originales; sus gestos
  quedan en el panel. Cada escena tiene un tablero independiente: `scene_scale.reference_board_id`
  es un UUID persistido en `btr_reference_board_id` dentro del `.blend`, pero las
  fotos son copias locales de la tablet. Nueva escena empieza vacía y abrir una escena
  guardada recupera su tablero. Las imágenes globales de versiones previas solo se
  trasladan mediante Más → Recuperar imágenes anteriores. Añadir y Quitar siempre
  están visibles, sin scroll horizontal; quitar no borra el original ni la copia
  enviada a Blender. Un selector/importación abierto conserva el tablero de destino
  aunque se cambie de escena antes de terminar.
  Se abre desde el icono Referencias del borde derecho; cerrado no ocupa la vista.
  «A Blender» copia además la imagen elegida a la escena (`reference.add`) como
  Imagen de referencia nativa: Empty de imagen empaquetado en el `.blend`, frente a la
  cámara de la tablet y con la opacidad del panel, en un undo. El tablero local sigue
  existiendo; la copia en la escena se coloca después como cualquier objeto.
  En Object se selecciona tocando el rectángulo de la imagen en el vídeo: incluye
  aspecto, offset y transformación nativos, visibilidad, lados y profundidad
  Delante/Predeterminada/Detrás. Respeta ocultación y bloqueo; no crea una malla
  auxiliar ni participa en el picking de Edit.
  Doble toque/Encuadrar usan las cuatro esquinas del mismo rectángulo para centrar
  y ajustar al 85 %, no solo el origen del Empty. Incluye aspecto de píxel y matriz
  con padres; la referencia activa también sirve de respaldo sin selección.
- Object muestra una bandeja inferior de propiedades del activo cuando no hay
  herramientas ni sesiones: Posición XYZ, Rotación XYZ en grados y Tamaño.
  El título es la sección y su icono desplegable la cambia; la fila lleva solo sus
  números. En «⋯ Más» quedan el objeto y su selector (Referencia), Mostrar delante
  y las opciones no numéricas de Imagen (Forma). Mantener pulsado un número vuelve
  posición/giro a 0, escala a 1 y opacidad al 100 %. Ocultar/mostrar
  queda en el radial y Outliner, sin ojo duplicado en propiedades. No hay sección Visibilidad ni campos Visible en vista
  o Visible en render; las propiedades específicas de Imagen conservan su sección.
  Una única lista desplegable cambia de sección, sin pestañas mezcladas con campos.
  La sección elegida se recuerda por identidad de objeto fuera del ciclo de vida
  de la bandeja: navegar, ocultar controles, snapshots sin propiedades y cambiar
  de selección no la reinician. Al volver a cada objeto recupera su sección si
  sigue disponible; los borradores y envíos mantienen su ciclo independiente.
  El esquema viene del backend (`active.properties`); las longitudes viajan en metros y se muestran
  con la unidad del preset. En imágenes nativas añade un único campo Tamaño, sin
  repetir «de imagen» ni los factores Escala X/Y/Z; además ofrece
  opacidad, ortográfica/perspectiva, solo vista alineada, profundidad y lados visibles.
  El selector de objetos permite recuperar referencias sin tocarlas en la vista.
  Los cambios se aplican inmediatamente, sin Cancelar/Confirmar.
  Tamaño a cero por escala no bloquea el campo: se puede escribir otra medida para
  recuperarlo, también tras guardar/cargar. Solo un eje bloqueado o sin extensión
  en la geometría local es de solo lectura; no se inventa grosor para una malla plana.
  Los números vacíos o incompletos permanecen locales; los snapshots no interrumpen lo que se escribe.
  Una petición en vuelo y una cola que conserva los últimos valores evitan saltos
  y pérdidas al pulsar deprisa. Cada envío usa la revisión recién confirmada;
  deshacer o cambiar de contexto retira los valores aún no enviados. Cada lote
  aplicado crea un undo nativo. Identidad y revisión protegen frente a otro objeto
  o cambios concurrentes del PC. No abre ni altera la sesión de Mover.
  Rotación conserva el modo nativo Euler/cuaternión/eje-ángulo y los bloqueos.
  El pie de vistas y el inspector de modificadores respetan la altura de la bandeja.
- Edit permite seleccionar vértices/aristas sueltos sin una cara bajo el toque.
  Las curvas Bézier/NURBS mantienen sus datos nativos: se seleccionan puntos y
  tiradores y se usa Mover/Rotar/Escalar con baseline reversible y un undo al confirmar.
  La matriz del objeto no cambia. Un tirador automático/vector pasa a libre al moverlo;
  cancelar restaura coordenadas y tipos. No se anuncian Tweak, proporcional ni herramientas
  topológicas de malla sobre curvas. Ocultar, duplicar y borrar usan operadores nativos.
- El círculo de malla regular sin caras ofrece Círculo → Resolución (3–4096
  vértices). Se reconoce por su geometría, también en archivos anteriores; conserva
  radio, plano, origen, transformación y materiales al reconstruir. No sobrescribe
  círculos deformados, grupos de vértices, shape keys ni atributos con datos propios.
  Las curvas ofrecen Curva → Resolución con el valor nativo. Cada cambio crea un undo
  y separa los datos del activo para conservar otras copias enlazadas.
  Los contornos de mallas sin caras y curvas sin grosor se seleccionan por sus
  aristas evaluadas mediante la proyección y oclusión comunes de `commands/snap.py`;
  respetan ocultación y bloqueo. El centro vacío no se trata como una cara rellena.
- Outliner sustituye a «Ocultos» en la barra superior. Lista todos los objetos de
  la escena, incluidos ocultos y los de colecciones excluidas, con buscador, nombre,
  colección/padre, selección, ojo y candado. Las acciones usan identidad efímera,
  no el nombre de la fila. Mover selecciona solo ese objeto y abre la sesión MOVE
  habitual en una petición atómica, conservando sus ajustes y undo. Renombrar,
  ocultar/mostrar y bloquear/desbloquear registran un undo por cambio.
  Bloquear usa `hide_select`, deselecciona y retira el activo si procede; el picking,
  Caja/Círculo, seleccionar por nombre, Todo y revelar respetan esa restricción.
  Las acciones requieren Object sin sesiones activas. Una colección excluida u
  oculta se identifica en la lista; mostrar un objeto no altera la colección.
  Los cambios desde el PC se reflejan mediante `outliner.changed`.
- Outliner → «Nueva colección» crea una colección nativa vacía o mueve la selección
  a ella, con nombre y colección padre elegibles, en un solo undo. El botón de
  carpeta de cada objeto permite moverlo a una colección existente o a la raíz.
  No cambia matrices, mallas ni parentesco; solo pertenencias a colecciones de la
  escena actual, conservando las pertenencias externas. Valida todo el lote antes
  de crear/enlazar/desenlazar y restaura los enlaces si falla. Las colecciones
  vacías y anidadas aparecen en un árbol plegable con raíz «/», nombres simples
  y objetos bajo su colección. El mismo árbol elige destino y padre. La búsqueda
  revela las ramas coincidentes sin perder los pliegues previos; admite varios
  padres. El lápiz renombra cada colección nativa con un undo, excepto la raíz.
  Objetos y colecciones se identifican por ID efímero, no por nombre.
  Crear o modificar colecciones desde el PC también refresca el Outliner.
- El encuadre y el clipping siguen el tamaño visto, también en piezas de 1 mm y
  menores; los rangos de preset se convierten por `scale_length`. Edit/CAD no
  interpretan toques consecutivos como encuadre (en Edit son el doble toque de loop). El panel de vistas ofrece
  «Encuadrar objeto» explícito; cámaras/luces ajenas no ensanchan su fallback.
- Extruir/Bisel/Inset inicializan el paso al 1 % de la menor dimensión útil,
  redondeado a 1/2/5 y acotado por el preset. Una pieza de 1 mm usa 0,01 mm;
  Bisel e Inset comienzan en dos pasos. Los valores editados siguen siendo exactos.
  Bisel interpreta su ancho en mundo con escala sin aplicar, sin cambiar la matriz
  del objeto. Estos valores iniciales no cambian Mover ni Escalar.
- Deslizar el Paso de herramientas Edit avanza en su orden de magnitud. Sculpt muestra el radio métrico aproximado
  del plano del pivote; su parámetro de gesto continúa siendo relativo a la pantalla.
- La selección de Object/Edit vive en el rail helper vertical derecho (`SelectionHelperRail`),
  con el mismo `ToolRail` que las restricciones CAD. Muestra solo las acciones aplicables:
  Object muestra Todo/Nada, Invertir, Caja, Círculo y Pintar selección; Edit añade
  Loop/Enlazado cuando proceden. En curvas muestra Todo/Nada, Invertir y Pintar.
  Pintar selección alterna una sola vez cada elemento atravesado en cada trazo,
  con radio ajustable. BEGIN/UPDATE acumulan una selección reversible; END confirma
  la última muestra sin sondear de nuevo y crea un undo. CANCEL, dos dedos,
  desconexión, cambio de herramienta o guardar restauran la selección inicial.
  Identidad de trazo y propietario rechazan eventos antiguos; respeta ocultación,
  bloqueo y oclusión. No cambia vértices ni convierte objetos.
  Modificadores (botón y panel), vistas/atajos y navegación reservan a su derecha
  `Metrics.HelperRailInset` (80 dp). Vértices/Aristas/Caras siguen bajo el ojo en mallas.
  El radial conserva Malla y, con selección, Ocultar, Duplicar y Borrar.
- Mayús, Alt, ⇧R y Ring se han retirado de sus barras a petición del usuario. El doble toque
  conserva la selección de loop en Aristas/Caras y de enlazado en Vértices; no se
  sustituye por ring. Ctrl permanece para camino más corto.
- Doble toque en Edit sin modificadores ni sesión activa: en Aristas/Caras añade el
  loop de lo tocado (Alt+clic de Blender); en Vértices, la pieza enlazada. El segundo
  toque envía ADD sobre el elemento y después el loop/enlazado; no encuadra. Bisel permanece en el rail; Bridge vive en Malla para dejar visible
  Cortar. Las exclusiones se derivan del catálogo del rail, sin listas duplicadas.
- En Extruir/Bisel/Inset, deslizar la distancia y el arrastre libre usan el paso
  físico de la sesión; sin snap conservan sus fracciones. La unidad elegida en Paso
  gobierna también sus distancias. Paso permanece accesible con snap desactivado.
- CAD ofrece «Bocetos → Editar», «Editar boceto» desde un perfil/operación y
  «Finalizar boceto» con texto. Reabrir enfoca el plano y selecciona el original;
  no duplica el boceto ni crea un undo de navegación.
- En Edit, Vértices/Aristas/Caras se sitúa a la izquierda del selector de modo, en
  la misma fila bajo el ojo; no aparece en la barra superior.
- El panel de modificadores está disponible en Object y Edit de mallas, limitado
  entre modos y vistas/atajos. En Edit permite añadir modificadores compatibles,
  cambiar parámetros (incluido Clipping), ordenar, retirar y alternar visibilidad
  global o solo en edición (`show_in_editmode`). Aplicar y acciones nativas que
  requieren Object quedan deshabilitados. Una transformación activa debe cerrarse
  antes de modificar la pila en Edit.
- El botón cerrado de modificadores se sitúa 10 dp debajo del selector de modos para
  no tapar el manejador de órbita.
- Nueva escena exige elegir Pequeña/Mediana/Grande (`mm`/`cm`/`m`) antes de crearla.
  El preset queda en `btr_scene_scale` dentro del `.blend`; no existe menú para cambiarlo
  durante el trabajo y `scene.scale_set` lo rechaza. Archivos anteriores sin esa
  propiedad se interpretan por `length_unit`. No limita las dimensiones de los objetos
  ni modifica `scale_length`. La nueva escena recibe rejilla, clipping y pasos iniciales;
  cambiar de escena reinicia los pasos Android y CAD al preset, identificando la escena
  con `scene_scale.scene_id`. Reconectar a la misma escena conserva los ajustes manuales.
- La cabecera muestra preset y unidad activos cuando Blender está conectado, por ejemplo
  `Conectado · Mediana · cm`.
- Los comandos discretos viven en menús contextuales.
- En Edit el toque sin modificador acumula: añade lo tocado o lo quita si ya estaba
  seleccionado (`TOGGLE`). Tocar vacío, incluido otro objeto de fondo, deselecciona todo.
  Alt sigue restando; Caja/Círculo conservan su operación.
- Mayús + Ring añade el anillo a la selección existente (`ADD`) en Aristas y
  Caras; sin modificador reemplaza y Alt resta.
- Los atajos de Edit incluyen J para conectar vértices con la operación nativa
  `mesh.vert_connect_path`; requiere modo Vértices y al menos dos seleccionados,
  divide las caras atravesadas y registra un único undo.
  Mantener J arma «Unir J» (`tool.begin`, `tool: CONNECT`, entrada `REPEAT_TAP`):
  pasa a Vértices y vacía la selección; cada toque marca el vértice visible más
  cercano (repetirlo lo desmarca, fallar conserva el primero) y con dos los conecta
  igual que J, con un undo, y deselecciona todo para el siguiente par. Sin encadenar.
  Repetir J, ×, otra herramienta o cambiar de modo lo desarman.
- Los parámetros viven en una bandeja común. Toda bandeja inferior empieza con
  `TrayTitle` (herramienta en mayúsculas, color de acento) y termina con `TrayExits`
  (Cancelar rojo y, si procede, Confirmar verde) fijos a la derecha; también los
  avisos de herramienta armada. Ninguna bandeja dibuja sus salidas a mano.
- Regla de diseño para las barras inferiores: una única fila fija, sin apilar
  cabecera, pestañas, mensajes o campos en varias líneas y sin scroll horizontal
  (ver Bandejas tranquilas). Lo que no es frecuente va a «⋯ Más»; no se encogen
  los controles ni se reducen sus áreas táctiles para forzarlo a caber. Título breve fijo a la
  izquierda y Cancelar/Confirmar fijos a la derecha, siempre accesibles.
  Textos y nombres no envuelven: se abrevian o truncan y su detalle se ofrece en
  la ayuda. Los avisos se resumen en la misma fila. La vista y los paneles vecinos
  reservan solo la altura real de la barra. `SingleLineTray` es el componente común
  para esta disposición; la primera barra adaptada es Propiedades de Object.
  Las propiedades de aplicación inmediata son la excepción a las salidas fijas:
  no muestran Cancelar/Confirmar porque cada cambio ya está aplicado.
- Al adaptar una bandeja a esta regla, los avisos de edición conjunta, medidas y
  recuentos se resumen dentro de la misma fila, con el detalle en la ayuda; no
  justifican una fila superior adicional. Más de dos aristas muestran su longitud
  total, sin una lista de longitudes que desplace Ancho/Paso y las acciones.
- Las nuevas herramientas deben describirse mediante catálogo/esquema siempre que sea
  posible, evitando nuevas ramas específicas en Compose.
- Los componentes compartidos poseen disposición, estado, unidades y ciclo de sesión;
  Blender conserva únicamente la lógica geométrica específica.
- El manipulador (`commands/gizmo.py`) vive sobre la selección en Object/Edit con la
  herramienta de selección normal: flechas mueven por eje, cajas escalan por eje,
  anillos rotan, el aro blanco escala todo y el círculo central mueve en la vista.
  Se dibuja en GPUOffScreen y el backend decide el asa al empezar el arrastre, como
  Tweak: abre la sesión `transform` de siempre y la confirma al soltar con un undo;
  sin asa el arrastre orbita y un toque sigue seleccionando. Sigue al dedo 1:1 y usa
  el snap Incremento y el paso común. Los anillos vistos de canto se ocultan. Android
  lo activa con `gizmo.set` solo sin otra herramienta, forma ni sesión. Los tiradores
  empiezan desactivados al abrir la app y al crear/abrir otra escena; su botón los activa. Su sesión interna no abre la barra de transformación.
- Mover, Rotar y Escalar usan un único `TransformAxisInputs` (X/Y/Z) en Object y Edit
  sobre la misma sesión modal. Su fila muestra X/Y/Z, Snap, Libre·X·Y·Z y,
  en Escalar, la cadena; como mucho cinco controles además de título y ×/✓.
- En Edit, Mover/Rotar/Escalar continúan por pasos al tocar otra selección. Un único
  `transform.select` sondea la preview viva, confirma el cambio anterior con un undo
  y abre otro baseline sin salir de la herramienta; conserva ejes, orientación y snap.
  Los valores y referencias se reinician para la nueva selección. Reset/cancelar solo
  afectan al paso actual. Un miss o una selección idéntica/vacía conserva la sesión;
  cambiar sin transformar o terminar una continuación sin cambios no crea undo vacío.
  Con snap geométrico, «Otra selección» distingue elegir elementos de fijar un destino.
  Los toques consecutivos durante estas sesiones Edit no activan doble toque.
- El selector `mm`/`cm`/`m` junto a X/Y/Z gobierna tanto los valores escritos y
  mostrados como el paso, los botones y el snap de Mover.
- Android renueva `unitScaleLength` desde cada `scene_scale`; cargar otro `.blend` no
  conserva la conversión métrica de la conexión anterior.
- Mover y Escalar inicializan su unidad visible desde el preset activo: Pequeña usa
  `mm`, Mediana `cm` y Grande `m`, también después de abrir otro `.blend`.
- El comportamiento de Mover queda aceptado y protegido en los commits `a936769` y
  `667cbcf`: no se modifican su gesto libre, conversiones, campos X/Y/Z, incremento,
  snap ni sesión modal salvo que la incidencia activa mencione expresamente Mover.
- Si otro cambio toca un archivo compartido con Mover, su camino debe conservarse sin
  alteraciones funcionales; no se aprovecha ese cambio para "mejorarlo" o refactorizarlo.
- Rotar se presenta y se edita exclusivamente en grados; los radianes quedan limitados
  al cálculo interno y nunca se ofrecen como unidad en la interfaz.
- Mover, Rotar y Escalar ofrecen Restablecer en Más · Precisión: restaura la preview a
  `0`, `0°` y `100 %` sin cancelar ni reactivar la herramienta. Mantener pulsado un
  eje restablece solo ese eje (en Escalar con cadena, los tres).
- X/Y/Z de Mover/Rotar/Escalar se deslizan con el paso de la sesión, con o sin snap;
  deslizar no aplana: el cero de Escalar se escribe. El paso y la unidad viven en
  Más · Precisión aunque el snap esté desactivado. En Propiedades las longitudes usan
  el paso métrico común o el del preset, los ángulos 1° y la opacidad 1 % por paso.
- En Mover, la unidad va junto al paso en Más · Precisión y gobierna también X/Y/Z.
  En Escalar, mm/cm/m/% gobierna dimensiones, paso,
  deslizamiento y snap; `Paso` muestra la misma unidad. Cada eje cambia la dimensión
  de su eje; con cadena conserva proporciones. El gesto métrico usa el eje restringido
  o la dimensión mayor de los ejes activos. Los valores escritos y Reset son exactos.
- Escalar admite `0` exacto en % y mm/cm/m para aplanar, también con snap activo.
  Escribir y confirmar cero en el campo de un eje aplana solo ese eje, incluso con
  la cadena activa. No hay botones X=0/Y=0/Z=0: una única petición
  conserva los valores visibles de los demás y retira cualquier restricción incompatible.
  La cadena sigue siendo proporcional para valores distintos de cero; Reset recupera el baseline.
- El selector y los pasos de snap viven en `ui/SnapControl.kt`; las bandejas declaran
  opciones y reciben valores, pero no vuelven a implementar su interfaz.
- El radio proporcional muestra y acepta la unidad del preset (mm/cm/m); deslizarlo
  acumula el paso físico anunciado convertido por `scale_length` (1 mm en Pequeña).
  Cambiar radio, perfil o activación actualiza la influencia desde el baseline sin
  reiniciar la transformación, sus valores ni sus referencias. Reducir el radio
  restaura los vértices excluidos; confirmar sigue creando un único undo.
- Extruir, Inset y Bisel comparten incremento editable y selector mm/cm/m; comienzan
  en la unidad del preset y convierten el paso según `scale_length`. Su arrastre con
  Incremento/Rejilla recorre un paso por el 4 % de altura, conserva fracciones y
  publica el valor visual redondeado. Extruir muestra siempre Paso deslizable que edita
  el paso en la unidad elegida, conservando la distancia y la preview actuales;
  el siguiente gesto usa ese paso. Deslizar Distancia suma/resta el paso, incluso
  sin snap, y acumula sobre su valor local; Distancia numérica es exacta y no se vuelve a redondear por snap.
  Editar Distancia sustituye al destino geométrico
  sondeado. Knife usa el mismo desplegable de Snap.
- Paso común: el último paso métrico que el usuario escribe en Mover, Escalar (mm/cm/m),
  Extruir/Bisel/Inset o Tweak libre se guarda en metros en la tablet y gobierna todos
  ellos durante el trabajo en esa escena. Crear/abrir otra escena o iniciar una nueva
  conexión tras reiniciar la app adopta el paso de su preset. Con él
  Extruir/Bisel/Inset no usan el paso automático por tamaño. Cambiar solo la unidad lo
  expresa en ella sin alterarlo. Porcentajes, SLIDE de Tweak y CAD conservan su paso.
- En Bisel, Ancho se muestra en la unidad elegida; deslizarlo resta/suma el
  paso activo.
- Extruir Región/Manifold admite restricción a eje o a plano (XY/XZ/YZ) con los mismos
  botones Libre·X·Y·Z que Mover (mantener un eje = plano de los otros dos). Libre sobre caras sigue su normal (como E en Blender); Libre
  sobre aristas/vértices sigue al dedo en el plano de la vista, y un plano elegido
  sigue al dedo dentro de él (`planar_drag`, `tool.extrude_drag`). Así un perfil
  plano en XY con la vista superior se extruye en XY, nunca hacia la cámara.
- Extruir Región desplaza y selecciona únicamente los vértices nuevos. Los vértices
  originales de las aristas/caras de conexión permanecen fijos, también al continuar
  otra extrusión desde el extremo seleccionado.
- Extruir Región usa la selección efectiva: caras completas también en Vértices o
  Aristas, y aristas completas también en Vértices. Confirmar y después Escalar
  conserva la base y transforma solo el extremo nuevo.
- Extruir identifica cada variante con su icono en rail/menú y su nombre en la
  bandeja. Respeta los modos del catálogo; una variante incompatible no cierra la
  preview anterior. Cambiar de sesión reinicia los borradores de Distancia y Paso.
- Por petición del usuario, todo número que muestra la app (campos, medidas, pasos,
  propiedades, modificadores y CAD) tiene como máximo dos decimales, redondeados
  (`formatToolDistance`, `MaxDecimals`), aunque una cota muy pequeña se lea 0. Los
  valores escritos se envían tal cual; solo se redondea lo que se ve. Extruir
  muestra Distancia y Paso así, sin redondear los valores enviados. Reset 0 fija la distancia exacta a cero, limpia
  el borrador y el destino geométrico, y conserva la sesión, variante y paso.
- Extruir ofrece Manifold en Caras con la operación nativa de Blender: disuelve
  bordes coplanares e intersecta los nuevos. Comparte distancia, paso, ejes y snap
  de Región; cada preview parte del baseline y confirmar crea un único undo.
- Dibujar · polilínea (rail EDITAR, familia `DRAW`) traza vértice → arista →
  vértice con toques sucesivos, como Ctrl+clic derecho desde cero: empieza sin
  selección (pasa de Caras a Vértices), cada toque es un undo, tocar un vértice
  existente lo une y cierra la forma, y «Nuevo trazo» (`tool.draw_break`) empieza
  otra línea suelta. Reutiliza el plano de la cámara de Extruir «A toque».
  Usa el gesto de F2 (`tool.draw_gesture`): tocar dibuja en el punto inicial y
  arrastrar desde un vértice lo mueve (Tweak), lo selecciona como extremo y crea un
  undo; cancelar o desarmar lo restauran.
- Extruir «A toque» reproduce Ctrl+clic derecho en el plano de la cámara remota,
  a la profundidad de la selección (del cursor 3D si no hay selección). Cada toque
  crea y confirma un tramo, selecciona el extremo nuevo y registra un undo; salir
  conserva los tramos. Girar origen reparte el giro entre origen y extremo nuevo.
  Se anuncia como `REPEAT_TAP`: los toques consecutivos nunca encuadran por doble
  toque y navegar con dos dedos no extruye. Deslizar antes de soltar conserva el gesto
  y confirma la última posición estable. Extruye la geometría efectiva seleccionada:
  los extremos de una arista seleccionados en Vértices también producen una cara.
  Sus controles usan la bandeja por esquema.
- Revolución y Barrido/Marco viven en el catálogo contextual Edit y usan la bandeja
  por esquema. Revolución gira un perfil con ángulo en grados, segmentos, eje global
  y centro métrico (inicializado desde el cursor); cierra la vuelta de 360° y une los
  puntos sobre el eje. Barrido crea un perfil rectangular con ancho/fondo sobre una
  cadena o loop plano de aristas sin caras, con ingletes compartidos y tapas opcionales.
  Ambas reconstruyen la preview desde el baseline y confirman con un único undo.
- Cada tipo de Snap obtiene su símbolo semántico desde `AppIcons.snap`; la marca de
  selección es un indicador aparte y no sustituye el icono del tipo.
- El sondeo geométrico del backend permanece centralizado en `commands/snap.py`.
- La adquisición táctil de candidatos usa allí una única política pegajosa con
  histéresis, margen de cambio y conservación del último candidato estable; Snap,
  REL/Fuente, Tweak, Extrude y Knife no definen pegajosidad propia.
- En REL/Fuente, retener un candidato solo conserva su mismo `id`: si se pierde no se
  adquiere otro de la misma categoría antes de comparar todas las categorías.
- REL/Fuente compara todas las categorías por distancia incluso durante la retención;
  un nuevo candidato siempre debe entrar en su radio de adquisición. El radio de
  pantalla corrige el aspecto y la oclusión se comprueba antes de competir.
- La búsqueda de snap incluye las siluetas y mallas de aristas, aunque el rayo central
  no golpee una cara. Solo los objetos excluidos por la sesión se atraviesan.
- REL/Centro y Fuente mantienen separado el rol de su candidato temporal: la
  histéresis de uno nunca retiene ni confirma el marcador perteneciente al otro.
- En Rotar y Escalar, REL permite elegir centro de selección, punto señalado, origen
  del objeto o cursor 3D sin reiniciar la sesión.
- Los marcadores fijados se reproyectan desde su posición 3D durante la sesión para
  permanecer unidos visualmente al target al cambiar la vista.
- Centro, fuente, destino y candidato temporal de transformación se dibujan dentro
  de GPUOffScreen, sincronizados con el vídeo; Android no duplica estos marcadores.
  La fuente acompaña la transformación y el centro conserva su pivote estacionario.
- Al activar snap geométrico en Rotar o Escalar sin Fuente, Android arma su búsqueda
  automáticamente; un toque directo también intenta fijarla en ese mismo punto.
- Cada transformación inicia sin snap contra su propia selección; el botón `Propio`
  permite incluirla como destino durante esa sesión.
- CAD tiene un rail de geometría y otro de restricciones solo durante el boceto;
  sus iconos vectoriales distintos se resuelven mediante `AppIcons.cad`. Object/Edit
  conservan sus raíles. El rail de restricciones se agrupa con separadores:
  posición, orientación, relación y cotas. La selección múltiple y el arrastre operan sobre IDs y roles
  de puntos/aristas, nunca sobre índices de la malla evaluada.
- Las restricciones CAD se persisten y resuelven al editar o mover. Un conflicto
  no modifica el documento; el arrastre se proyecta a la libertad permitida. Un
  toque sin cambios no crea undo. El redondeo recorta dos líneas conectadas y
  añade un arco con coincidencias, tangencias y radio. Las uniones de línea usan
  la política pegajosa común de `commands/snap.py`.
- Tangente admite línea–arco/círculo y dos arcos/círculos distintos. Entre curvas
  el backend elige el contacto exterior o interior más cercano al dibujo y lo
  persiste como `mode:EXTERNAL/INTERNAL`; editar o arrastrar conserva esa rama.
  Coincidente une los extremos del contorno; Tangente conserva su contacto suave,
  sin fijar automáticamente centros, radios o ángulos. Un conflicto es atómico.
  Al añadir tangencia entre curvas se conservan los radios de las dos seleccionadas
  como objetivos de esa edición, desplazando sus centros libres y ajustando los
  extremos unidos. No añade candados de radio persistentes ni acepta radios negativos.
- En el boceto solo las cotas (reglas con valor) se tocan y arrastran, una cada vez
  (`CONSTRAINT`); puntos/aristas siguen siendo multiselección. Las reglas sin valor
  (H, V, ⊥, =…) son marcas discretas, no seleccionables, solo junto a la geometría
  seleccionada; se gestionan desde su lista. Las cotas se dibujan como un plano:
  líneas auxiliares finas, flechas esbeltas y el valor en una píldora de tamaño fijo;
  la caja táctil del backend es mayor que la píldora. Arrastrar solo cambia
  `label_position` en metros del croquis, sin solver ni evaluación del sólido. END
  conserva la última preview y crea un undo; cancelar restaura y un toque no crea undo.
- Colineal (`COLLINEAR`) mantiene dos líneas/lados del croquis sobre la misma
  recta, con longitudes y deslizamiento independientes, sin unir extremos.
  Respeta cotas y referencias fijas; no fija automáticamente ninguna línea.
- Horizontal/Vertical admite varias líneas o lados rectos seleccionados del boceto.
  Una petición crea una regla por referencia sin duplicarlas, resuelve el conjunto
  y registra un único undo. Un conflicto rechaza todo sin cambiar geometría ni cotas.
- Punto sobre recta (`POINT_ON_LINE`) usa un punto y una línea/lado recto de otra
  figura, seleccionados en cualquier orden; admite también el eje de una ranura.
  Solo restringe la distancia perpendicular: el punto desliza por la recta y su
  prolongación. Respeta FIX/cotas sin fijar automáticamente la guía. Rechaza
  puntos sobre su propia figura, dos puntos, dos líneas o una guía curva.
- Punto CAD (`POINT`) se dibuja con toque o arrastre reversible y conserva snap a
  puntos/rejilla; confirmar consume la última preview y crea un undo. Es auxiliar
  libre y no forma perfiles, tampoco al retirar Construcción. MIDPOINT admite
  punto+arista o tres puntos (último=medio); el mismo punto puede relacionar los
  centros de varias aristas y servir de centro de simetría. Subdividir, en el rail
  del croquis justo debajo de Punto, crea un punto auxiliar con MIDPOINT sobre una
  arista recta o entre dos puntos; permite mitades sucesivas sin partir el perfil.
- La fila de acciones del boceto junto a Deshacer/Rehacer evita pulsaciones largas:
  Seleccionar/Deseleccionar todo es un único botón que alterna según haya selección,
  y Cerrar perfil proyectado solo aparece si el croquis activo tiene curvas proyectadas.
- `ANGLE` con dos líneas/lados rectos es la cota de ángulo entre ellas (0–180°):
  cada segmento apunta desde la intersección de ambas rectas hacia su extremo más
  lejano, así una esquina compartida mide su ángulo interior. Vive en el grupo de
  cotas del rail, se ofrece con el valor actual y se dibuja como arco con flechas.
  Android conserva `ANGLE` al leer las capacidades; la prueba recorre anuncio,
  estado y catálogo del rail para evitar ocultarlo aunque el backend lo ofrezca.
- Las cotas CAD distinguen distancia diagonal, horizontal y vertical (`DISTANCE`,
  `DISTANCE_X`, `DISTANCE_Y`). Las dos últimas miden la separación absoluta en los
  ejes del croquis, admiten cero y conservan cantidades independientes. Pueden usar
  dos puntos (incluido origen/centros) o una línea/lado; se editan desde la misma bandeja.
- Dibujar primitivas CAD aplica las ayudas de editar: el inicio adquiere un punto
  existente con coincidencia (esquina de rectángulo, centro de círculo/arco, extremo
  de línea) o cae en la rejilla del paso; con Incremento, tamaño y radio se redondean
  al paso y una figura menor que un paso no se crea. Snap/Paso siguen visibles con
  la herramienta armada y las medidas se ven en vivo, de solo lectura, hasta soltar.
- `NGON` es un polígono regular nativo: parámetros centro, `flats` (entre caras =
  Ø inscrito) y `angle` en grados; `sides` (3–32) es discreto y nunca lo resuelve el
  solver. Sus esquinas son `P0…Pn-1`, sus lados `EDGEi` y su cota es un RADIUS
  inscrito (`value_factor` 0,5). Cambiar lados conserva la medida y se rechaza si hay
  reglas sobre esquinas/lados. Dibujar redondea Entre caras al paso.
- `SLOT` guarda centro, `length` entre centros, `width` y `angle`; sus puntos son
  `CENTER/START/END/SIDE` y `AXIS` es su eje para DISTANCE. Ancho es un RADIUS (0,5).
  Arrastrar `SIDE` (sobre un lado recto) solo cambia el ancho: los centros quedan fijos.
  `GEAR` es un engranaje recto de evolvente con `module` y `angle` resolubles y
  `teeth` (6–150)/`pressure` (14,5/20/25°) discretos; su RADIUS es el primitivo
  (`value_factor` = dientes/2). Cambiar dientes conserva el módulo; con Incremento,
  dibujar elige el módulo ISO más cercano. Ninguno se somete al test O(n²) de
  autointersección.
- Ranura ofrece Radio/Ancho como dos representaciones de la misma cota: R15 =
  ancho 30 mm. El radio público deriva de `width/2`; editarlo actualiza esa medida.
- Desfase por grosor (`cad.entity.offset`) crea un contorno vinculado de ranura,
  círculo o rectángulo, hacia dentro/fuera. `OFFSET` conserva la relación entre
  figuras del mismo croquis; en ranuras comparte centros, longitud recta y ángulo.
  El contorno derivado muestra solo Grosor; editarlo mantiene inmóvil la fuente.
  Un grosor que colapsa el contorno o contradice otra cota se rechaza atómicamente.
  Quitar OFFSET desvincula sin borrar; borrar una fuente requiere retirar primero
  sus derivados. No es un desfase genérico de cadenas de líneas/arcos. Vive en el
  rail del croquis junto a Redondear y actúa sobre la única figura seleccionada.
- Añadir una restricción desde la selección o editar el valor de una cota existente
  vacía la selección al terminar; una medida con `refs` explícitas (candado de la
  bandeja) conserva la selección del usuario.
- Simetría de operación (`cad.feature.mirror`, nodo `MIRROR`) refleja el operando
  de una Extrusión/Vaciado anterior del mismo cuerpo sobre XY/XZ/YZ del documento
  CAD y una posición métrica. Conserva el croquis fuente y hereda su profundidad y
  dirección; une/resta únicamente el operando reflejado, no todo el cuerpo acumulado.
  La pila vuelve a evaluar los dependientes; fuente desactivada desactiva también
  su resultado simétrico. Cada creación/edición es un undo. Se rechazan referencias
  futuras, ciclos, otra simetría como fuente y el borrado de fuentes con dependientes.
  La selección analítica refleja también sus superficies. No es el botón de
  extrusión por ambos lados del plano ni el modificador Mirror de una copia de malla.
- La bandeja de una figura CAD solo ofrece medidas (longitud, ancho/alto, radio,
  ángulo del arco), nunca coordenadas; la posición se fija con candados y cotas a
  otros puntos. No existe herramienta Cuadrado: es un rectángulo con Igualdad.
- Durante el arrastre CAD, las dimensiones de la figura seleccionada permanecen
  visibles y se actualizan desde la preview, también con Incremento. Se leen sin
  editar durante el gesto; al soltar se habilitan sus campos y candados para fijarlas.
- Igualdad admite varias medidas compatibles del mismo croquis y toma inicialmente
  el tamaño de la primera seleccionada, sin fijarlo permanentemente. Persiste parejas
  de igualdad sin duplicarlas; las cotas previas incompatibles rechazan el cambio.
  En círculos, Radio/Diámetro elige la representación del mismo parámetro y cota.
  Simetría usa tres puntos, con el último como centro; el origen ya está fijo.
- Cada cuerpo CAD publica un único objeto con el resultado acumulado de su historial:
  Extruir añade por unión y Vaciar resta del resultado anterior. Nuevo cuerpo crea una
  pieza independiente. El objeto conserva su identidad al editar y recorrer la pila;
  `btr_cad_body_id` identifica el cuerpo y `btr_cad_feature_id` su operación visible final.
  Crear copia de malla vive en el menú del cuerpo y exporta la pieza completa a Object.
  «Copia editable · Edición / Escultura» y Duplicar desde Object sobre una pieza
  CAD generan mallas independientes, conservan modificadores y retiran sus marcas
  CAD. La copia admite Edit/Sculpt; el original se guarda oculto para evitar solapes
  y reaparece temporalmente al volver a CAD. En CAD no hay duplicado enlazado;
  sobre mallas ordinarias Normal/Enlazado conserva el comportamiento nativo.
- La evaluación reutiliza operandos y resultados de operaciones que no cambian,
  y conserva su malla Blender. Las claves incluyen geometría, plano, profundidad y
  predecesor; el estado se descarta al cargar/deshacer. Renombrar no evalúa geometría.
- El resaltado CAD conserva lotes de GPU en coordenadas 3D; la cámara solo cambia
  su matriz de proyección. Las medidas y la adyacencia se reutilizan mientras la firma
  de geometría/topología/transformación/unidades siga igual. No se retienen referencias RNA.
- En CAD 3D, Redondear y Chaflán de las aristas del sólido aparecen únicamente en
  la bandeja inferior al seleccionar aristas; no se duplican en el rail izquierdo.
  El redondeo del croquis conserva su acceso contextual durante la edición.
  Extruir admite Simetría: la profundidad crece a los dos lados del croquis.
- Si el ancho de un acabado CAD no cabe, la sesión conserva Ancho y Segmentos para
  corregirlo; el candidato inválido nunca se confirma ni crea undo. Aplicar un
  borrador de Ancho espera su preview antes de permitir confirmar la operación.
  La limpieza del bisel actúa solo en las aristas elegidas y conserva el resto de
  la malla. Valida cierre, volumen y cruces de las caras modificadas contra el sólido;
  intersecciones previas entre caras intactas no se atribuyen al nuevo acabado.
- Extruir/Vaciar CAD siguen la normal del plano en pantalla: arriba/abajo o
  izquierda/derecha, y también el sentido contrario. El lápiz mueve un prisma
  ligero que sigue la punta 1:1 sobre la normal (rayo del lápiz contra la recta
  normal por el centro del perfil); el booleano se asienta al soltar. Incremento
  avanza por pasos enteros durante el trazo y redondea ese asiento; las
  cotas escritas son exactas. Vaciar crece a un lado del
  croquis (`ONE`) o a los dos (`BOTH`); la profundidad es la de cada lado.
  «Perforar todo» (`THROUGH_ALL`, solo CUT) calcula en cada evaluación un prisma
  que abarca el cuerpo acumulado a ambos lados del croquis, con margen. Conserva
  la cota manual al volver a ONE/BOTH; no ofrece campo ni gesto de profundidad
  mientras está activo. Funciona con perfiles con huecos, simetrías
  y cambios del grosor anterior; su fantasma usa el mismo cuerpo y no anuncia tapa
  de fondo ni apoyo de plano. Una profundidad explícita vuelve a ONE.
  Vaciar consume su sólido
  destino en el árbol y reconstruye desde los parámetros. Solo el volumen del
  vaciado activo es translúcido: un fantasma dibujado en GPUOffScreen, sin rayos X
  globales ni cambios de sombreado; el sólido y el resto de la escena siguen opacos.
  La sesión reutiliza la teselación local del perfil y sus huecos al variar profundidad;
  conserva operandos compactos para Vaciar y descarta la caché al cerrar. Android
  mantiene una petición CAD en vuelo y solo el último candidato absoluto pendiente
  de profundidad, ancho o lápiz; confirmar respeta ese orden. Navegar continúa
  durante el cálculo; cancelar/guardar/salir descartan la cola y el cálculo pendiente. Un fallo de
  profundidad impide confirmar una medida anterior. Repetir el mismo paso no reconstruye.
- Hasta cara (`extent:TO_FACE`) termina Extruir/Vaciar en el plano de una cara plana
  tocada, también inclinada respecto al perfil: evita vaciar el sobrante. Guarda el
  marco capturado (`to_face` en metros), nunca índices; el perfil debe quedar entero
  a un lado. Con un croquis completo, OpenCascade comprueba todos sus contornos
  cerrados y limita todas las regiones a la misma cara, incluidos los huecos.
  Se arma con el botón Hasta cara de la bandeja y el siguiente toque elige
  la cara; Una dirección/Simetría o una profundidad escrita vuelven a la cota.
- Redondeo/Chaflán (`FILLET`/`CHAMFER`) son nodos de la pila del cuerpo sin boceto
  (`sketch_id: null`): guardan `edges` como segmentos en metros de las aristas de
  diseño elegidas (nunca índices), `width` y `segments` (chaflán = 1). Se evalúan con
  el BREP de OpenCascade; una arista recta coincide si está sobre la recta de un
  segmento guardado y lo solapa, así sobrevive a cambios de longitud. Las curvas
  se emparejan sobre su geometría analítica. Sin coincidencia → error explícito.
  En modo Aristas la selección del sólido se acumula; Redondear/Chaflán abren una
  sesión `cad.finish.*` excluyente, con preview desde el baseline y un undo.
  No sirven de apoyo de bocetos. `segments` se conserva en documentos existentes
  por compatibilidad; la forma BREP y su teselación no dependen de ese campo.
- Carcasa (`SHELL`) abre una o varias caras planas del mismo cuerpo desde la
  bandeja de Caras, sin acción duplicada en el rail. Guarda sus puntos interiores y
  normales en metros locales del documento, no índices. Grosor inicia en 2 mm;
  Hacia dentro conserva el exterior y Hacia fuera conserva el interior. El gesto,
  paso y números comparten la política de acabados; el nodo se edita en la pila.
  OpenCascade empareja caras orientadas por geometría: primero el punto en su plano,
  o una única cara paralela que contenga su proyección si cambió la altura. Una
  referencia ausente/ambigua falla; no se elige otra cara por índice o proximidad.
  Verifica también que el hueco interior respete el grosor: un BREP válido puede
  ocultar el cruce de paredes. El cálculo siempre usa OpenCascade.
  La preview parte del baseline; error conserva controles y bloquea confirmación,
  cancelar/desconectar/guardar restaura, confirmar crea un undo. Carcasa no sirve
  como apoyo de plano; Boceto en cara captura la superficie resultante. Las caras
  del mismo cuerpo se acumulan para elegir varias aberturas.
- Un boceto sobre la cara superior sigue el plano/altura de su operación soporte.
  Los soportes con dependientes no se borran; crear una copia de malla conserva sus referencias.
- La iconografía se resuelve por intención desde `ui/Iconography.kt`; las pantallas no
  eligen símbolos ni mantienen tablas de iconos propias. Confirmar/Cancelar, marcas de
  menú, flechas, visibilidad, modos y Mover/Rotar/Escalar también salen de `AppIcons`;
  el menú radial usa `AppIcons.action(id)`, el mismo icono que la barra. Una intención
  distinta nunca comparte símbolo (Manipulador ≠ Mover, Atajos ≠ Modificadores).
- Los dibujos originales comunes viven en `ui/StudioIcons.kt`: cuadrícula 24×24,
  trazo 1,7 y extremos/uniones redondos, como los iconos CAD. El color indica estado;
  las acciones se distinguen por geometría, también sin color. Encuadrar/Aislar,
  Conectar/Camino más corto, modo de selección/destino de snap y las variantes de
  Cortar/Extruir/Inset tienen dibujos distintos. Rail y menú resuelven las variantes
  mediante `AppIcons.toolbarVariant`; Bisecar nunca hereda el icono de Cuchillo.
  `android-client/tools/export_icon_catalog.py` genera la lámina HTML y el paquete
  SVG desde los mismos trazados del APK, sin mantener una segunda colección manual.
- Las ayudas de iconos usan `HoverHelp` e `IconHelp`: acercar lápiz/borrador o ratón
  durante 450 ms muestra nombre y explicación, también en controles deshabilitados.
  Retirar el puntero, tocar, cancelar la entrada, retirar el control o pausar la app
  oculta la ayuda. No toma foco ni consume eventos; en el radial comparte la entrada
  con el velo que resuelve los toques. Las variantes muestran su explicación propia.
- Los ejes X/Y/Z tienen un único color, el del tema por defecto de Blender:
  `Ink.AxisX/Y/Z` en Android y `palette.AXIS_COLORS` en el vídeo (manipulador, plano
  CAD). Ninguna pantalla define su propia paleta de ejes.

## Compilación

```bash
export JAVA_HOME=/home/valle/.local/opt/jdk-17.0.20+8
export PATH="$JAVA_HOME/bin:$PATH"
./gradlew :android-client:app:assembleDebug

bash blender-backend/tools/build_addon.sh
```

Antes de entregar, revisar el diff, compilar ambos artefactos afectados y comprobar que
no quedan archivos o referencias temporales.

## Materiales y capturas

- Materiales es un workspace (`mode: MATERIAL`) y Blender permanece en Object.
  Permite seleccionar hasta 16 mallas sin salir y muestra la escena visible.
  Aislamiento opcional y ambientes existen solo dentro
  de la captura GPU y se restauran siempre, sin persistir visibilidad ni tocar `rv3d`.
- Los presets se describen mediante Tablet Material Recipe v1: JSON acotado,
  compilado a nodos nativos, sin código ejecutable. Contrato, esquema y ejemplos
  en `docs/material-recipe-v1.md`; guía en `docs/material-workspace.md`.
- Elegir material/color/acabado configura el pincel; Aplicar a todo sustituye la
  base explícitamente con un undo. Los objetos enlazados ajenos conservan sus datos.
- Pintar inicia en Color: cambia solo Base Color y conserva metal, brillo, transmisión
  y relieve. Material mezcla la receta completa. Capas permite seleccionar, ocultar,
  ajustar opacidad y borrar una de hasta ocho capas; el pincel y Borrar actúan sobre
  la elegida. Nueva capa fuerza otra al siguiente trazo, aunque tenga el mismo color.
  Cada edición conserva fuentes e imágenes independientes para undo y objetos enlazados.
- Las máscaras de 1024² se empaquetan en el `.blend`. El atlas privado usa Smart Project
  sobre una copia temporal aislada, conserva las UV y selecciones del usuario, une
  superficies coplanares y reparte espacio por área. Dos píxeles de margen extienden
  la máscara sin pintar otras islas. Los atlas ya pintados se conservan para no mover
  trazos; reaplicar una base retira solo el atlas privado y prepara uno nuevo al pintar.
  Las capas de archivos anteriores se incorporan conservando shaders y máscaras.
- Las previews de pintura tienen propietario/ID, copias de malla, material e imagen
  y un único undo al confirmar. END no pinta otra muestra. Cancelación, desconexión
  y save_pre restauran; un trazo vacío no crea undo. La cola Android ordena muestras
  y navegación con una petición en vuelo, compartida con Sculpt sin mezclar comandos.
- La profundidad de pintura procede de una pasada Workbench auxiliar con la cámara
  remota; Eevee entrega el color. Las superficies ocultas no reciben muestras.
- Archivo → Capturar escena produce un PNG desde GPUOffScreen en cualquier modo,
  sin overlays nativos, marcadores ni UI. Conserva la preview y el aislamiento actual;
  no crea undo. Android permite elegir dónde guardarlo mediante su selector de archivos.


## Pulido de feedback (septiembre 2026)

- CAD bloquea la órbita libre durante el boceto; orbit desplaza la vista,
  pan/zoom siguen activos. El giro de dos dedos y Girar 90° rotan la vista sobre el
  plano y se quedan; Enderezar la deja de frente, con el mundo arriba. En el boceto y en Extruir/Vaciar aparece el círculo de
  navegación de las transformaciones. En el boceto, sostenerlo orbita en perspectiva
  como vistazo y soltarlo restaura la vista ortográfica del plano; se aparta del rail
  de restricciones y se oculta mientras la pila CAD está abierta. El origen reservado `ORIGIN/POINT` es fijo y seleccionable.
  Se selecciona tocándolo en el boceto; no tiene un botón duplicado en el rail.
- Fijar restringe solo puntos/extremos de aristas seleccionados; figura completa
  fija todos sus parámetros. Selección múltiple comparte un undo. Punto medio y
  simetría (último punto = centro) usan el mismo solver, también con el origen.
- Construcción conserva restricciones y se excluye de los perfiles. El panel de
  restricciones filtra IDs y roles compartidos con la selección; las cotas se
  proyectan en backend y muestran unidades. Los bocetos tienen visibilidad propia.
- Redondeo admite varias esquinas en un undo: un rectángulo entero (sus cuatro),
  esquinas o lados contiguos de rectángulo, extremos de línea (se emparejan con la
  línea unida) o líneas seleccionadas (cada par con extremo común). Convierte el
  rectángulo a una cadena restringida y conserva las operaciones que usan el perfil.
  El primer arco lleva la cota RADIUS y los demás Igualdad: un valor edita todos.
- El polígono irregular dibuja una cadena de segmentos unidos por coincidencias:
  cada trazo o toque consolida un vértice; cerrar tocando el primer punto o con
  «Cerrar polígono» une también el último tramo con el primero (la esquina se mueve
  como un punto), registra un único undo y deja el perfil seleccionado. Empezar en
  un punto existente lo une al primer tramo. Con menos
  de tres vértices el cierre se ignora o responde error sin perder la sesión.
  Cancelar o dos dedos descarta la cadena completa; otra herramienta la abandona
  sin persistir nada. En construcción no genera perfil y selecciona el último tramo.
  Al soltar cada lado publica inmediatamente la cadena consolidada y `can_close`:
  dos lados (tres vértices) habilitan Cerrar y producen un triángulo sin otro trazo.
  Tocar un lado tras cerrar sustituye la selección del perfil por la del elemento;
  nunca mezcla PROFILE con ENTITY al editar. Los lados del polígono regular NGON
  cuentan como líneas para habilitar restricciones, incluidas Horizontal y Vertical.
- Cerrar perfil proyectado (`cad.reference.close`, anunciado por `reference_profile`)
  convierte las curvas proyectadas seleccionadas en perfiles, o todas sin selección.
  Une extremos cercanos hasta el Paso; líneas/arcos comparten un punto geométrico y
  los arcos conservan centro/radio. Actualiza los FIX de la copia y añade coincidencias
  con IDs intactos y un undo. Huecos mayores, uniones ambiguas, cruces y conflictos
  rechazan la transacción completa; no modifica el cuerpo del que se proyectó.
- Los cuerpos son piezas independientes con un historial de croquis/operaciones. Los planos guardados
  admiten desplazamiento métrico y giro local XYZ en grados, con referencias a
  boceto/cara superior. Una cara arbitraria guarda su marco capturado, sin índices
  evaluados persistentes; su adquisición pasa por `commands/snap.py`.
- `cad.convert` crea una copia de malla y sale a Object con ella seleccionada;
  conserva el original, el documento y todos los dependientes. No elimina histórico.
- CAD presenta y mueve la malla compacta del kernel. La copia editable conserva
  esa superficie sin forzar cuadriláteros ni añadir una retícula. `cad/editable_mesh.py`
  suelda coincidencias numéricas con tolerancia relativa al tamaño, elimina
  degenerados y disuelve divisiones casi coplanares, respetando contornos curvos,
  huecos, materiales y costuras. Retira las aristas sin caras y los vértices sueltos
  residuales de esa limpieza; nunca elimina bordes abiertos de la superficie.
  Valida cierre, caras/aristas no nulas y volumen para aceptar la limpieza. Si no
  puede conservar el sólido, entrega una copia independiente de la malla original,
  aunque necesite reparación manual; nunca una limpieza parcial. Conserva atributos,
  materiales y modificadores y permite Edit sin propiedad CAD. La limpieza ocurre solo al
  exportar/duplicar: nunca se realimenta a la pila CAD. Una malla compacta no
  garantiza biseles de cualquier ancho ni topología regular para Subdivisión.
- Los comandos CAD suspenden su respuesta durante la evaluación y se reanudan
  desde el pump. Un proceso Blender persistente calcula booleanos, redondeos y
  el solver de arrastre sobre snapshots; vídeo y navegación siguen atendidos.
  Cada resultado valida escena, documento, unidades y generación de cancelación.
  Cancelar/guardar/desconectar descarta el trabajo y restaura la evaluación baseline;
  cargar/deshacer invalida las cachés. Los ficheros privados y el proceso se retiran
  al cerrar; un error del worker no publica geometría ni crea undo. La limpieza
  de la copia editable y la materialización final usan el hilo principal del host.
- Materiales conserva tinte y acabado al cambiar de preset salvo valores explícitos.
  Óxido/Suciedad/Arañazos configuran el pincel de detalle sin sustituir la base.
  La pintura indexa muestras visibles por teselas y reutiliza atlas/profundidad
  solo mientras su geometría/UV y cámara coincidan.
- `server.resume` vincula una identidad privada Android con el workspace suspendido.
  Desconexión cancela previews y restaura visibilidad; reconectar recupera cámara,
  boceto y ajustes confirmados. Cargar otro archivo invalida la recuperación.

- Los campos numéricos aceptan cuentas (`10-3`, `2x4`, `(1+2)/4`) y, si empiezan
  por `+`, `*` o `/`, operan sobre el valor actual. Un menos seguido de un número
  sigue siendo una cota negativa.
- Los campos numéricos CAD seleccionan todo su contenido al enfocarse
  (`selectAllOnFocus`): con texto alineado a la derecha, el toque dejaba el cursor
  delante del número y lo tecleado se anteponía. Mover conserva su campo sin cambios.
- Tocar cerca de la línea entre los centros de una ranura selecciona su eje (`AXIS`),
  que Android resalta; sirve para Ángulo y Punto sobre recta. Arrastrarlo mueve la ranura.
- La bandeja inferior CAD usa `CompactNumericField` con `ScrubNumber` y el campo
  de paso compartido de `SnapControl.kt`; cada paso deslizado acumula sobre el
  pendiente local como un −/+ mantenido, sin multiplicar la cota elegida.
  Cancelar/aceptar permanecen fijos a la derecha con `RoundAction` rojo/verde.
  Las medidas del boceto se editan en borrador y se aplican juntas con un comando;
  Extruir/Vaciar conserva la preview inmediata y acumula pasos ante respuestas
  atrasadas. Los campos métricos usan el paso CAD; los angulares, grados.

- CAD tiene un único cursor: cada toque alterna la pertenencia a la selección y
  arrastrar adquiere/mueve el elemento, conservando el grupo si ya lo cubría la
  selección. Android exige superar el umbral táctil antes de UPDATE; END consume
  el sondeo de BEGIN/última preview sin raycast nuevo. Un toque no modifica geometría
  ni crea undo; cancelar/dos dedos restaura también la selección anterior.
- Dibujos abre siempre el árbol de bocetos/figuras, separado de la pestaña de
  restricciones contextuales. Seleccionar/Deseleccionar todo (un botón), Borrar selección,
  Construcción y Soldar puntos viven junto a Deshacer/Rehacer. Cada candado de medida está junto a
  su campo en la bandeja inferior. Redondear permanece en el rail del croquis y borrar
  en sus acciones/papeleras, sin duplicados en la bandeja de propiedades.
  Borrar un lado de rectángulo conserva los demás como líneas;
  una esquina retira sus dos lados. Un extremo/centro de otra primitiva elimina
  esa primitiva, nunca guarda una figura incompleta. El origen no se borra y romper
  un perfil usado se rechaza sin eliminar operaciones ni cambiar el documento.

- Las cotas CAD tienen una única fuente: editar Radio/Diámetro/Lado/Longitud actualiza
  la cota que gobierna esa medida. Añadir una cota equivalente reutiliza su ID;
  lados opuestos de rectángulos e igualdades explícitas comparten medida. Los
  duplicados antiguos se muestran como una cota y se fusionan al editar/quitar.
- Editar Longitud de una línea impone solo su distancia, sin fijar coordenadas ni
  un extremo implícito. Punto medio conserva el centro y reparte el cambio; un
  extremo fijado explícitamente permanece fijo. Se reutiliza la cota y se crea
  un undo; un conflicto real conserva geometría y restricciones anteriores.
- El cuadrado anuncia un único Lado: Igualdad mantiene sus lados iguales, no fija
  su tamaño. Los campos distinguen «sin cota» de «cota», con Fijar medida/Quitar cota;
  quitar la medida conserva la figura y la igualdad. La bandeja usa los descriptores
  `dimensions` del backend, sin duplicar el mapa de medidas en Compose.
- Confirmar una medida de boceto con el check verde crea o actualiza su cota y
  marca su candado desde el estado confirmado (`cad.entity.set`, `constrain:true`).
  Solo acota los campos editados que ofrecen candado; el resto sigue libre. Radio/
  diámetro/ancho y las Igualdades reutilizan la misma cota. Valores y cotas forman
  una transacción y un undo; un conflicto no deja bloqueos ni cambios parciales.
- Los redondeos se reconocen por sus coincidencias y tangencias, también en archivos
  anteriores. Editar su radio reconstruye el contacto con las dos líneas; Quitar
  redondeo restituye la esquina y actualiza el perfil de las operaciones dependientes.
  Las medidas/igualdades de lados redondeados usan las esquinas virtuales, no los
  tramos recortados, para conservar el tamaño y la igualdad de un cuadrado.
  Cada redondeo muestra también `CORNER`, la intersección exterior de sus lados,
  junto al centro del arco. Es seleccionable, acotable y usable en simetría/snap;
  se deriva de la geometría sin añadir entidades ni parámetros. El solver incluye
  ambos lados en sus dependencias. Redondear y quitar redondeo remapean las cotas
  y fijaciones de esa esquina; los archivos anteriores obtienen el punto al abrirse.
- Cotas y reglas ofrece Editar y Quitar explícitos. El valor inicial de una nueva
  medida procede de la geometría; si ya existe se abre esa cota, no otra superpuesta.
- Círculo muestra Radio durante el dibujo y tras confirmar. El estado público deriva
  `radius` de `diameter`; ambos editan la misma cota, sin cambiar el almacenamiento.
  Arco sigue armado tras dibujar para encadenar arcos. Su extremo END anuncia
  `intent:ANGLE` y se dibuja como rombo; apoyar sobre él (con Arco o con el cursor)
  lo arrastra y cambia solo el barrido, conservando centro, radio e
  inicio y las restricciones. Redondeos no ofrecen tirador angular. Solo los arcos
  dibujados describen Ángulo (`sweep`, cota `ANGLE` en grados, magnitud) con candado;
  el ángulo de un redondeo es automático y no se muestra ni se iguala.
  Igualdad entre arcos iguala radio y ángulo (`EQUAL` + `EQUAL_ANGLE`), solo radio si
  hay redondeos; con varios arcos seleccionados, la bandeja aplica sus medidas a todos
  (`equal_ids`) en un undo. Cada preview
  parte del baseline, END no sondea otra posición y confirmar crea un undo si cambió.
- El solver acepta residuos de hasta una millonésima del tamaño del boceto: las
  referencias proyectadas traen ruido float32 y reglas casi redundantes no bajan de
  ~1e-7; los conflictos reales siguen rechazándose. Su jacobiano solo reevalúa las
  reglas que leen la figura de cada parámetro (incluidos los lados de un redondeo).
  Distancia 0 entre dos puntos crea una coincidencia, no un error de rango.
- Soldar puntos añade coincidencias persistentes entre extremos/esquinas seleccionados
  sobre el último punto (el origen prevalece), con un undo. Respeta restricciones;
  un conflicto es atómico y una soldadura ya existente no duplica reglas ni undo.
- La pila CAD usa toda la altura disponible y se desplaza a la izquierda del rail de
  restricciones. Figuras/Restricciones permanecen fijas sobre su lista; Solo selección
  controla el filtro. El rail incluye un icono propio para crear croquis directamente
  en la cara seleccionada; se habilita con `surface.can_sketch`. Los demás planos
  siguen disponibles desde Planos y bocetos.
  Puntos/Aristas/Caras son iconos junto al selector CAD/Object, como en Edit;
  solo aparecen en 3D o al medir referencias del sólido explícitamente. Se ocultan
  al editar el croquis con su cursor, que ya selecciona puntos/aristas directamente.
  No se duplican como texto en la bandeja. Cursor vuelve a Perfiles/Boceto.
  El botón de vistas/atajos se sitúa sobre la altura medida de la bandeja CAD;
  la pila reserva también la altura real del teclado, plegado o desplegado.

- CAD diferencia la edición del boceto de la selección del sólido. Perfiles/Caras/
  Aristas/Puntos selecciona hasta dos referencias visibles para medir. El sondeo
  permanece en `commands/snap.py`: agrupa caras coplanares conectadas y omite sus
  aristas internas; las divisiones collineales se seleccionan como una arista.
  Los modificadores conservan su detalle visible, pero Caras/Aristas agrupa por
  la referencia CAD de origen: un cubo subdividido mantiene seis caras y doce
  aristas seleccionables. Las etiquetas FACE/EDGE se propagan con Blender solo
  al reconstruir la caché y se retiran siempre; el resaltado sigue la forma evaluada.
  En cuerpos CAD con Bisel/Subdivisión, medidas y planos de croquis pertenecen a
  la cara de diseño anterior al acabado; el resaltado sigue la superficie evaluada.
  Los puntos son los vértices de diseño: el bisel no los elimina como referencias.
  Su visibilidad respeta el cuerpo de diseño y los demás objetos oclusores.
  El resaltado se dibuja dentro de GPUOffScreen, nunca duplicado en Android.
- En un sólido CAD, Caras/Aristas/Puntos siguen la figura de diseño, no la
  teselación: un círculo extruido tiene dos contornos y ninguna muestra de malla
  como arista o punto. Un cubo conserva seis caras, doce aristas y ocho puntos.
- Extrusiones y vaciados etiquetan cada cara evaluada por la superficie analítica de
  su croquis (`cad/design_surfaces.py`): planos de tapa y de lados rectos, cilindros
  de arcos/círculos. Una cara CAD es una superficie; una arista, el par de
  superficies que separa. Así líneas y arcos tangentes (ranura, rectángulo
  redondeado) son caras, aristas y puntos distintos. No se propaga nada por los
  booleanos: las caras cortadas siguen sobre su superficie. Redondeos, solevado,
  helicoidal y flancos de engranaje quedan sin etiqueta y usan la heurística. El
  Barrido etiqueta sus tapas y, en cada línea recta del recorrido, los cilindros y
  planos del perfil (las curvas no). Un cilindro admite vértices de corte hundidos
  hasta la sagita de su teselación (2,2 ‰ del radio), así la unión de un tubo con
  una cara plana es una sola arista circular.
- En la selección 3D, las aristas de diseño contiguas y tangentes forman un único
  contorno seleccionable, medible y redondeable. La continuidad usa las normales
  analíticas, no los ángulos de la teselación. Conserva esquinas y ramificaciones;
  dentro del croquis, Proyectar mantiene las referencias de cada tramo por separado.
- Arrastrar el centro de un arco permite adaptar su radio y sus ángulos libres a
  los extremos unidos. El objetivo táctil tiene peso suficiente para recorrer esa
  libertad; la proyección final conserva todas las cotas y reglas fijadas.
- La primera selección CAD agrupa contornos suaves mediante uniones de conjuntos:
  calcula una vez qué segmentos terminan en esquinas y materializa cada grupo al
  final. No reinicia un recorrido global ni copia el contorno creciente por cada
  unión. Conserva las aristas rectas y reutiliza el grafo entre Caras/Aristas/Puntos.
- Boceto en cara consume la cara resaltada sin repetir raycast y crea plano+boceto
  en un solo undo. Sus ejes siguen la vista enderezada (Z del mundo arriba; Y en
  caras horizontales), nunca una arista teselada: un rectángulo sale recto en pantalla. Las caras superiores CAD conservan soporte asociativo; otras
  caras guardan su marco. Las selecciones del sólido son transitorias y se invalidan
  al cambiar geometría o transformación; no persisten índices de la malla evaluada.
- En un boceto, Proyectar está en el rail: cualquier punto, arista o cara, aunque esté
  a otra altura, se copia al plano del croquis como construcción fija. Las referencias
  se seleccionan de forma acumulativa, también entre tipos y objetos; tocar de nuevo
  retira esa referencia y un miss conserva el grupo. La bandeja cuenta la selección;
  Proyectar al plano copia todo en un undo y Limpiar retira el grupo completo.
  Los tramos se encadenan y ajustan: rectos → LINE, cocirculares con paso teselado pequeño → ARC,
  un lazo redondo → CIRCLE (con centro); un vértice → `POINT` (solo por proyección).
  FIX y un undo. Las figuras con FIX completo son constantes y no cuentan en el límite
  de 300 parámetros del solver. Permite acotar desde esos elementos;
  es una copia fija, no promete asociación topológica con cualquier cara/arista.
  Dentro del boceto, Proyectar es el único acceso a esa selección del sólido y su
  bandeja también muestra las medidas; no hay un icono Medir duplicado.
  Planos guardados nombra cada plano junto a los bocetos que lo usan (o «sin usar»).
  Ver escena (`show_scene`) es un icono fijo de la fila del ojo en todo CAD (3D,
  boceto y colocación de planos), no un botón de bandeja.
- Finalizar boceto restaura una vista 3D orbital, con encuadre del resultado, sin
  escribir `rv3d`. Extruir/Vaciar muestran su preview en 3D. Si el croquis nuevo tiene
  varios perfiles se selecciona completo (`SKETCH`), no su última figura; un perfil
  único conserva `PROFILE`. Al cerrar un boceto usado o vacío no se selecciona
  automáticamente la última operación ni se abren sus propiedades. Las medidas
  de figuras y los controles de dibujo solo se muestran dentro del boceto activo;
  editar una operación en 3D requiere seleccionarla expresamente.
  La pila muestra solo croquis y operaciones, sin filas
  para figuras o perfiles. El menú del croquis ofrece Renombrar y Seleccionar croquis
  completo; las figuras permanecen dentro de la edición. Tocar un nodo selecciona ese paso.
- Los planos se colocan de forma interactiva, sin diálogo: sesión `PLANE`
  (`cad.plane.begin/update`, confirmar/cancelar con `cad.session.*`). El rail pasa a
  elegir la base (Superior/Frontal/Lateral con el trípode de colores de Blender, o
  la cara seleccionada) y la bandeja lleva Separación, Inclinar sobre dos ejes y
  Mover dentro del plano, deslizables. La separación sigue la normal inclinada y el lápiz
  la arrastra 1:1 (rayo contra la recta normal), con Incremento por pasos enteros.
  GPUOffScreen dibuja la preview (lámina translúcida del tamaño del resultado, borde,
  ejes y normal); el documento no cambia hasta ✓, que crea plano y croquis en un undo.
  Lámina y flechas usan el preset, el tamaño del resultado y un mínimo relativo
  al zoom, con conversión por `scale_length`; no tienen un tamaño fijo en cm.
  Vídeo y sondeo comparten `cad/plane_display.py`. Al iniciar, un plano fuera de
  vista se encuadra sin mover su marco ni `rv3d`; si ya se ve conserva la cámara.
  Abrir un boceto vacío encuadra esa misma extensión en vez de usar 20 cm fijos.
  Las flechas son tiradores: el lápiz agarra al bajar la roja/verde (Mover por su
  dirección real, también inclinado) o la azul/fuera de ellas (Separación); la activa
  se dibuja amarilla. La bandeja muestra solo Separación; Inclinar y Mover por números
  viven en «⋯ Más» · Forma y Planos guardados en Referencia.
  Los planos guardados se reutilizan o se recolocan con esa misma sesión (`plane_id`).
  Boceto en cara usa `_face_plane`, compartido con la base Cara de la sesión.
  La base Arista usa la única arista recta seleccionada del sólido: X sigue la
  arista, empieza enrasada con una cara contigua e «Inclinar sobre la arista» la
  gira alrededor de ella. Es un plano implícito con su marco capturado.
  «Limpiar planos sin usar» (Planos guardados) borra con un undo los planos que
  ningún boceto usa; no existe borrado de planos con bocetos.
- Vista en sección (fila del ojo, solo en el boceto): el plano cercano de la cámara
  remota se apoya en el plano del croquis y retira lo que queda delante. Solo actúa
  con la vista de frente al plano; no escribe en `rv3d` ni crea undo, y la selección
  de referencias del sólido ignora la parte retirada.
- La vista del boceto es ortográfica por defecto; el icono Perspectiva de la fila del
  ojo (`view.perspective`) la cambia sin dejar de mirar de frente al plano. La elección
  (`sketch_projection`) se conserva al Enderezar, girar y reabrir bocetos.
- Todas las referencias del sólido seleccionadas (varias aristas incluidas) se
  resaltan en el mismo azul.
- «Copiar a otro plano paralelo» (menú del croquis) crea con un undo un plano implícito
  referido al croquis fuente (traslación `[0,0,z]`) y una copia con IDs nuevos y reglas
  remapeadas. Sigue al fuente; su «Separación Z» se edita en la bandeja 3D al
  seleccionarla y borrar la copia retira su plano. El fuente no se borra mientras exista.
- Solevado (`LOFT`) es un nodo de la pila con `sketch_id/profile_id` y
  `to_sketch_id/to_profile_id`: une un contorno exterior sin huecos de cada croquis
  con paredes regladas y se suma al cuerpo del primero. Cada anillo conserva sus
  esquinas (se muestrean ambos en la unión de sus parámetros de perímetro) y el
  inicio del segundo minimiza la torsión. Consume ambos croquis, que no se borran
  mientras exista; no sirve de apoyo de bocetos. Android: seleccionar perfil →
  Solevado → tocar el del otro croquis. Planos coincidentes se rechazan sin cambios.
- Barrido helicoidal (`HELIX`) guarda `sketch_id/profile_id`, `axis` (`X`/`Y` del
  croquis por su origen o id de una línea del mismo croquis), `pitch` (m por vuelta),
  `turns` y `hand`. Gira el contorno alrededor del eje avanzando el paso (48 pasos por
  vuelta) y se suma al cuerpo. Rechaza perfiles que toquen/crucen el eje y pasos
  menores o iguales que la altura axial del perfil (vueltas solapadas). Crear elige
  el primer eje Y/X no cruzado; la línea de eje no se borra mientras la use.
- Barrido (`SWEEP`) guarda `sketch_id/profile_id` y `path_sketch_id`: el recorrido es la
  única cadena abierta de líneas/arcos no constructivos de otro croquis, acotable y
  asociativa. El perfil (huecos incluidos) conserva su pose respecto al inicio y gira
  por transporte paralelo con la tangente analítica de cada vértice: las uniones
  tangentes no se inglean (los tramos rectos quedan cilindros exactos) y solo las
  esquinas reales se estiran a lo ancho del giro. Se suma al
  cuerpo y no sirve de apoyo. Android: perfil → Barrido → tocar el croquis del
  recorrido en la pila (que se abre sola).
- Revolución (`REVOLVE`) guarda `sketch_id/profile_id`, `axis` (`X`/`Y` del croquis
  o id de una línea del mismo croquis) y `angle` (0–360°). Gira el contorno y se suma
  al cuerpo. El perfil puede apoyarse en el eje (conos, cúpulas: esos puntos se
  comparten en todos los pasos) pero no cruzarlo; 360° cierra la vuelta sin tapas.
  Crear elige la primera línea de construcción válida y después Y/X. Comparte con el
  helicoidal la protección de su línea de eje y no sirve de apoyo de bocetos.
- Seleccionar todo/Deseleccionar todo comparten el rail de Deshacer/Rehacer, también
  en CAD 3D. En edición seleccionan figuras del croquis; en 3D el croquis elegido.
  Extruir/Vaciar aceptan `sketch_id` para todos sus contornos: exteriores como volumen,
  interiores como huecos y regiones separadas en una sola operación y undo. Construcción
  se excluye; geometría abierta o regiones cruzadas se rechazan sin modificar el modelo.
  La operación persiste `profile_<sketch_id>` y se reconstruye desde el croquis original.
- La lista CAD muestra solo figuras/reglas del boceto activo al editar. En 3D la
  pila de operaciones muestra la secuencia completa del cuerpo al estilo OnShape:
  tocar un nodo fija la barra de retroceso en ese punto y muestra el modelo de
  entonces; Atrás/Adelante/Final navegan y los nodos posteriores quedan atenuados
  e inaccesibles (`cad_rollback`). Los nodos nuevos se insertan justo tras la
  barra y al confirmar la barra avanza hasta ellos. Navegar no crea undo; salir o
  reconectar devuelve la vista al modelo completo. `order` conserva el orden de
  creación de bocetos/operaciones.
  La pila ocupa el sitio del inspector de modificadores: icono cerrado bajo el
  selector de modos y flecha de vuelta en su cabecera. El contexto CAD —Planos,
  Vista 3D, Girar 90°, Enderezar, Finalizar/Editar boceto— son iconos en la fila de
  Deshacer/Rehacer, sin franja propia bajo el menú. Dentro del boceto no existe
  «Volver al plano»: Enderezar ya deja la vista de frente con el mundo arriba y
  volver al cursor desde Medir/Proyectar se hace con sus propios botones del rail.
  Los bocetos consumidos se ocultan por defecto; el ojo conserva una elección
  explícita de visibilidad. Las caras seleccionadas nunca aparecen en captura limpia.

- Wireframe no está disponible en Materiales/Texturas: Android oculta el control
  y el backend convierte WIREFRAME/TOGGLE a SOLID mientras ese workspace está activo.
  Si el viewport ya estaba en Wireframe, incluso por un cambio desde el PC, la
  captura lo normaliza a Solid antes de guardar su estado de restauración. Así no
  se restaura Wireframe después de cada frame. Los demás flags se restauran siempre.

- La apariencia se compone en un orden fijo: receta del catálogo, acabado encima
  —cada acabado escribe solo los parámetros que define— y ajustes sueltos de
  `surface` encima de todo. Sin tinte, cada material se compila con su propio color:
  recorrer el catálogo no arrastra el color del anterior y el tinte es una decisión
  explícita y reversible (`color:null`). Elegir acabado descarta los ajustes; ajustar
  marca `custom`. El grano añade una capa teñida con el color efectivo sin tocar la
  receta. `material.save` guarda esa composición como preset propio de la escena.
- Materiales reparte su interfaz en cuatro superficies con una pregunta cada una:
  rail izquierdo (modo Seleccionar/Pintar/Borrar y trazo), fila del ojo (objetos,
  aislar, zona, luz: iconos junto a Deshacer/Rehacer, sin franja propia bajo el menú,
  con el número de objetos como marca del icono), panel derecho con pestañas
  Material/Acabado/Grano/Capas y bandeja
  inferior (Color/Material como icono, color, Tamaño e Intensidad deslizables; el
  obstáculo actual es un aviso fijo y la ayuda de uso solo aparece las primeras veces).
  Lo que se usa durante el trazo vive en el rail, sin plegarse ni abrirse. El panel
  derecho ocupa el sitio, el margen y el gesto de apertura/cierre del inspector de
  modificadores: icono bajo el rail de modos, flecha de vuelta en su cabecera.
  Aplicar vive al pie de ese panel y no dentro de una pestaña: material, acabado y
  grano son una sola receta y se asignan de una vez. En Capas se oculta Aplicar.
- Materiales permite Seleccionar/Pintar y una lista de objetos para piezas interiores.
  Selección vacía permite navegar, volver a seleccionar y salir. La profundidad incluye
  los oclusores visibles; Aislar selección sirve para pintar dentro de una carcasa.
- Zona limita pincel y relleno a caras seleccionadas en Edit o caras completas de un
  grupo de vértices. Guardar zona copia la malla para no alterar objetos enlazados;
  los atributos de delimitación por modificadores son temporales. Rellenar crea un
  único undo y una zona vacía conserva el baseline. El atlas conserva sus límites
  de 20 000 caras base / 200 000 evaluadas; aplicar una base completa no usa atlas.
- Redondo, Aerógrafo y Salpicado cambian la huella, independientemente del material.
  La cobertura conserva la presión cero y no depende de la partición de paquetes.
- Cristal activa transmisión por rayos y grosor superficial cero conectado al output,
  para que Eevee no salte por detrás del objeto omitiendo su interior. Ray tracing se
  activa solo en captura y se restaura al terminar. No es óptica volumétrica ni cáusticas.
  Compilar un preset corregido nunca modifica los materiales ya usados por otros objetos.
- Mover luces es un cursor de Materiales: dedo/lápiz gira horizontalmente el ambiente
  HDR (360° por ancho de vídeo) y en vertical cambia su intensidad de forma
  proporcional (0,2–3 en un alto de pantalla), con bombilla, ángulo y porcentaje.
  No hay elevación porque `View3DShading` solo expone `studiolight_rotate_z`: el eje
  vertical no puede quedarse muerto ni fingir un giro que Blender no hace. Restaurar
  luces recupera giro e intensidad del ambiente actual sin salir del cursor y se
  deshabilita cuando ya están en su sitio, que es la única forma de saberlo; cambiar
  ambiente reinicia ambos. Dos dedos navegan y el círculo derecho orbita. Cada gesto tiene
  propietario/ID y baseline; END conserva la última muestra estable y cancelar,
  navegar, guardar o desconectar restaura el inicio. Reconectar conserva el giro
  confirmado. Solo modifica GPUOffScreen; no crea undo ni toca luces de escena o `rv3d`.

- Taladro métrico (`HOLE`) usa POINT y centros de CIRCLE de un croquis, por ID.
  M2–M6 ofrecen pasante, cajeado, avellanado a 90°, tuerca hexagonal e inserto.
  La holgura es diametral (0,2 mm inicial) y los insertos permiten Ø/profundidad
  propios. Un único compuesto se resta al cuerpo; los puntos y el croquis usados
  no se borran. Su preview y controles se describen en `cad/operations.py`;
  Android consume ese esquema con los campos numéricos comunes. `kind` persistido
  describe la variante; el `kind` de la vista de historial solo clasifica nodos.

- Patrón (`PATTERN`) repite operandos EXTRUDE/CUT/HOLE anteriores del mismo cuerpo;
  nunca el sólido acumulado. Lineal admite dos direcciones y rejilla; circular usa
  360° sin duplicar el inicio o un ángulo parcial incluyendo extremos. Número incluye
  el original. Ambos lados reparte índices enteros alrededor del original (con un
  número par, una copia extra al lado negativo). Direcciones/ejes se capturan por
  segmentos o por eje cilíndrico, en metros locales; no persisten índices.
  Las fuentes desactivadas suprimen el patrón y no se borran mientras se utilicen.

- Combinar (`COMBINE`) opera entre dos cuerpos CAD: CUT/UNION/INTERSECT. CUT
  admite holgura por desfase BREP (paso 0,05 mm). La colocación relativa se captura
  en una matriz con traslación métrica; la geometría fuente sigue siendo paramétrica.
  El evaluador usa el estado de la herramienta en ese punto del historial y rechaza
  ciclos incluso indirectos. keep_tool:false oculta la herramienta consumida, sin
  borrarla; los cuerpos usados quedan protegidos frente a borrado.

- Partir (`SPLIT`) reutiliza la sesión de colocación de planos, con `split_body_id`.
  Conserva BELOW en el original y, con BOTH, crea un cuerpo `source:{feature_id,
  side:ABOVE}` que sigue al original y admite su propia pila. El corte no se
  aproxima: OpenCascade intersecta semiespacios planos exactos. El sólido inicial
  derivado se cachea por ID de cuerpo; su tip público es el SPLIT. Desactivar o
  retroceder antes del corte retira sus derivados; no se elimina una mitad con
  operaciones. Los planos guardados invalidan la caché por su marco resuelto.

- Recortar bocetos (`cad.entity.trim`) tiene sesión TRIM: BEGIN/UPDATE solo
  resaltan el tramo entre intersecciones analíticas; END confirma el último
  candidato sin otro sondeo. Cada gesto crea un undo; miss/cancelar no cambian nada.
  LINE/ARC se fragmentan, CIRCLE pasa a ARC y RECTANGLE a líneas. Construcción no
  corta; NGON/SLOT/GEAR no se recortan. Conserva cotas/fijaciones de extremos vivos,
  descarta las que perdieron sentido y añade POINT_ON_LINE contra rectas; contra
  curvas los extremos quedan libres. Protege perfiles usados, ejes, centros de
  Taladro y Desfase. El overlay candidato no participa en su propio picking.

- Vaciar selección se ofrece dentro del boceto: `cad.selected_cut` habilita CUT con
  `sketch_id` y `entity_ids` explícitos. Crea un único nodo y undo con los controles
  habituales de Vaciar. La lista persiste IDs del original, sin copiar figuras;
  filtra tanto OpenCascade como el prisma/fantasma y las referencias analíticas.
  Los círculos no elegidos no se convierten en cortes ni huecos del operando.
  Selecciones vacías/abiertas, puntos y construcción se rechazan; los elementos
  usados quedan protegidos. Simetría/Patrón heredan ese mismo operando. La caché
  conserva también las dependencias completas de otras operaciones del boceto.

- Editar un croquis difiere la reconstrucción de sus operaciones: dibujos, solver,
  cotas y arrastres actualizan solo el boceto y conservan el último sólido válido.
  `deferred_sketch_id` persiste el trabajo pendiente; la validación de los perfiles
  usados se completa al salir, sin relajar entidades, restricciones ni dependencias
  de borrado. Finalizar evalúa en el worker; éxito publica la pieza con undo.
  Fallar en una operación conserva el borrador y abre la pila con ese nodo
  seleccionado/visible (`sketch_failure`, `sketch_review`), sin borrar ni desactivar
  automáticamente. Finalizar y navegar calculan solo hasta el puntero; navegar
  fija el destino antes de cerrar un croquis pendiente. Un fallo detiene la barra
  en ese nodo, también al avanzar sin croquis abierto. Retroceder vuelve a evaluar
  ese prefijo. Editar calcula hasta la barra; borrar su nodo retrocede al anterior
  sin alcanzar pasos futuros. Las correcciones conservan undo y el sólido visible
  ante un fallo sigue siendo el último válido. La desconexión conserva el puntero.
  Los errores del propio croquis mantienen su edición.
  Cambiar de boceto, Vista 3D/Object o una operación de
  sólido resuelve antes el pendiente. Guardar conserva croquis y sólido congelado;
  volver a CAD recupera la edición, sin kernel dentro de los handlers.

- Redondear bocetos admite LINE+ARC unidos por un extremo (o ambos): calcula
  tangencias exactas mediante rectas desplazadas y círculos concéntricos, recorta
  los elementos y conserva sus IDs. El nuevo ARC guarda `fillet_kind:ARC_LINE`
  para distinguirlo del arco original; sus fuentes siguen las coincidencias y
  tangencias por ID existentes. Radio y Quitar redondeo usan
  el mismo flujo; CORNER conserva la esquina virtual recta–círculo y sus cotas.
  Valida continuidad, radio disponible y restricciones antes de persistir; no
  prolonga elementos separados ni ofrece redondeo ARC+ARC. LINE+LINE conserva
  su reconocimiento por coincidencias/tangencias sin migrar documentos antiguos.

- Vaciar conserva una preview ajustable si el corte inicial no alcanza material
  (`cad_cut_miss` del nodo nuevo): muestra el sólido previo y permite editar
  profundidad/Hasta cara/Perforar todo; Confirmar permanece deshabilitado. Alcanzar
  material habilita el único undo normal. Volver a una profundidad vacía restaura
  el sólido previo, nunca confirma el último corte válido por error. Otros fallos
  de la pila no se convierten en cortes vacíos ajustables.
- En la selección de croquis, dos centros coincidentes se desempatan a favor de
  la figura dibujada frente a una referencia de construcción. Conserva la prioridad
  de distancia y de las etiquetas de cotas; Figuras permite seleccionar contornos
  aunque una etiqueta cubra su centro.

- Mostrar boceto permite alternar varios perfiles del mismo croquis directamente
  en 3D (`profile_multiselect`). Vaciar recibe `profile_ids`, resuelve círculos y
  cadenas a `entity_ids` del original y reutiliza el vaciado por selección. No
  incluye contornos sin marcar ni entra en edición. Otro boceto/selección completa
  sustituye el grupo; repetir un perfil lo quita. Las herramientas de perfil único
  quedan deshabilitadas para un grupo, nunca usan silenciosamente el último.

- Enderezar (`cad.view.align`, flecha del boceto) solo restablece la orientación
  frontal de los ejes del croquis. Conserva exactamente zoom/distancia, posición
  desplazada y proyección. El encuadre inicial al abrir un boceto sigue separado.

- Deformación simple vive en Modificadores: cuatro métodos nativos, eje, ángulo en
  grados o factor según método, límites 0–1, bloqueos y objeto de origen opcional.
  Angle/factor comparten almacenamiento nativo: se escribe solo el activo, tras
  validar el cambio completo. La bandeja usa `visible_when` y `value_labels` del
  esquema compartido; conserva las acciones habituales de pila y undo.

- Modificadores incluye Grupos de vértices del objeto activo: crear, renombrar,
  borrar y, en Edit, asignar/quitar seleccionados con peso 0–1 o seleccionar sus
  miembros. Usa la capa deform del BMesh vivo sin cambiar de modo; al crearla se
  renuevan las referencias a vértices. Cada acción crea un undo. Renombrar/borrar
  actualiza las referencias de grupo en los modificadores del objeto. Los grupos
  bloqueados rechazan asignación; una preview activa debe terminar primero.
- Simple Deform acepta grupo e inversión mediante el tipo de campo `vertex_group`.
  Los snapshots incluyen nombres, bloqueo, grupo activo y disponibilidad; nunca
  recorren pesos por vértice a cada broadcast. Las mallas CAD requieren conversión
  antes de asignar grupos. Cambiar de objeto renueva las opciones y los borradores.

- Guardar selección como grupo es una acción común de Pintura y Modificadores:
  mismo diálogo Android y mismo servicio `vertex_groups.save_selection`. Crea y
  asigna en un solo undo; el grupo nativo sirve para ambas zonas. Edit usa BMesh;
  Pintura usa la selección conservada de Edit y copia las mallas enlazadas antes
  de escribir pesos. Valida todos los objetos antes de modificar cualquiera.

- El catálogo de modificadores incluye búsqueda por identificador y nombre recibido
  del servidor (sin acentos). Lattice usa el generador de campos RNA y el mismo
  inspector genérico: jaula, intensidad, grupo e inversión. Crear jaula ajustada es
  una acción explícita con un undo: 4×4×4 puntos, encuadre en coordenadas locales y
  matriz del objeto, sin deformación inicial. La edición táctil de puntos Lattice
  no está implementada; la inspección de propiedades no se anuncia como ese soporte.
- La reflexión de RNA se aplica gradualmente con adaptadores para contexto y
  acciones. El catálogo disponible sigue controlado; no se exponen colecciones,
  propiedades internas ni sockets de Geometry Nodes como campos ordinarios.

- Archivo → Versiones integra ValleTrack (fork de valle.mrv, original intacto).
  Un repositorio Git/LFS privado por ID persistente del `.blend` versiona solo
  `model.blend` y `.gitattributes`; nunca toma el repositorio padre ni usa add .,
  reset --hard o force-push. Guardar versión y subir son acciones separadas.
  Gitea usa cuenta/token propio fuera de escenas/Git, no visible en snapshots;
  HTTPS predeterminado y HTTP solo por elección explícita del usuario.
- Git/LFS/HTTP corren en un hilo sin bpy; guardar/cargar pertenecen al pump.
  Explorar desde un commit crea una idea/ramificación permanente en ese punto;
  Continuar idea abre su último paso. Antes se conserva el avance del camino de
  origen, incluidas ediciones durante la preparación. El selector Ver historial
  solo inspecciona. Se muestran padres, punto común e idea activa. Subir publica
  todas las ideas atómicamente; Descargar conserva divergencias locales.
  Los clones tienen copia de trabajo separada del snapshot Git; los antiguos se
  separan antes de navegar. `restore` se resuelve por el mismo flujo Explorar. Un cambio de archivo impide aplicarla; los conflictos de
  historiales binarios no se mezclan automáticamente. Los recursos externos se
  incluyen solo si Blender puede empaquetarlos y el usuario lo marca. El alcance,
  formato de clonación y requisitos están en `docs/valletrack-integration.md`.

- Outliner alterna selección al tocar objetos y ofrece Mover selección hacia una
  colección existente o nueva. Nueva colección incluye la selección inicialmente.
  Cada colección no raíz ofrece Renombrar, Mostrar/Ocultar y Bloquear selección.
  Usa las restricciones nativas de colección, respeta los estados propios de sus
  descendientes y la selección del visor consulta `context.selectable_objects`.

- En vistas planas del manipulador se oculta el eje perpendicular (Z en XY, Y en
  XZ y X en YZ), incluidas flecha, escala y anillo de rotación. El mismo layout
  gobierna dibujo y picking; orbitar fuera del plano recupera las asas aplicables.

- Cambiar de herramienta, seleccionar o cambiar modo confirma la preview estable
  de `transform.*`/`tool.*` y la siguiente operación parte de ese resultado.
  `interaction.finish` es idempotente y valida propietario; los inicios también
  confirman en servidor si la respuesta anterior aún no ha llegado. Transformar
  sin cambios y herramientas solo armadas no crean undo. Cuchillo/Bisect/Alinear
  incompletos se cierran sin crear geometría. ×, desconexión y segundo plano
  conservan su cancelación explícita. Cada operación confirmada conserva su undo.
  Cambiar la variante de Extruir ajusta la misma operación desde su baseline;
  no añade otra extrusión ni confirma una variante inválida.

- El radio de captura del snap geométrico de Mover y herramientas es de un dedo:
  Vértice 3 %, Centro arista/cara 2,8 % y Arista 2 % del ancho, en pantalla. Radios
  mayores atrapaban casi toda la malla al alejar la vista y el elemento no se movía.
- Mover/Rotar/Escalar ofrecen snap Arista (cualquier punto del segmento) separado
  de Centro arista. No se llama secante; reutiliza el candidato geométrico EDGE.

- El candado del pie de vistas es una tecla más de la botonera, al final de la fila
  7·8·9, con el mismo estilo que las demás. Bloquea el plano elegido en ortográfica. Impide
  órbita y roll desde gestos, navegador y comandos; mantiene zoom/pan. Elegir
  otra vista principal cambia explícitamente el plano sin quitar el candado.
  Desbloquear permite orbitar; nueva escena/carga reinicia el candado.

- Tweak usa adquisición sobre toda la jaula visible, también justo fuera de su
  silueta, con margen táctil propio. Seleccionado y no seleccionado tienen la misma
  prioridad espacial; tocar uno seleccionado conserva el grupo. Xray no salta
  automáticamente a otro elemento al empezar Tweak. GG ofrece Prolongar arista · Alt,
  activo por defecto: extrapola el riel en ambas direcciones sin el tope anterior
  de −1/2 longitudes. Desactivarlo limita al segmento. Un gesto Tweak pendiente
  se cancela por identidad antes de abrir otra herramienta, incluso sin ACK.
