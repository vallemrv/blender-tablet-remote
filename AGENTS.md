# Blender Tablet Remote — guía de trabajo

## Objetivo

La tablet Android es una interfaz táctil para Blender, no un escritorio remoto.
Blender conserva el motor 3D; Android muestra una cámara remota y envía intención
adaptada a dedo y stylus. El alcance actual es Object Mode, Edit Mode, Sculpt
(`docs/sculpt-workspace.md`) y el workspace CAD paramétrico (`docs/cad-workspace.md`).

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
- Tweak en Edit selecciona y arrastra vértices, aristas o caras con un gesto; conserva
  el grupo al tocar un elemento seleccionado. Un toque sin arrastre no mueve ni crea
  undo. Otra herramienta o repetir su botón desactiva Tweak; sus eventos pendientes
  nunca modifican una transformación posterior. En caras usa movimiento libre.
- H.264 se decodifica sobre una `Surface`; MJPEG se decodifica a Bitmap.
- AUD/NAL H.264 se localizan con búsquedas nativas de bytes, sin recorridos Python
  por byte. El pump respeta el próximo vencimiento de captura descontando el tiempo
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
- CAD v1: planos XY/XZ/YZ y cara superior asociativa, líneas, rectángulos, cuadrados,
  círculos, arcos, redondeo de sketch, selección de puntos/aristas y restricciones.
  Extrusión de perfiles cerrados y vaciado por profundidad con incrementos. Documento JSON
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
- El toque de Loop Cut elige el anillo y crea el corte centrado (50 %); cada nuevo
  corte comienza sin desplazamiento. La bandeja permite porcentaje o mm/cm/m desde
  el centro, además de volver a Centro. Las medidas físicas incluyen la escala del
  objeto y de escena; los cortes múltiples conservan su espaciado al desplazarse.
- El campo de posición de Loop Cut permite un borrador vacío en % y mm/cm/m;
  las actualizaciones remotas no lo rellenan mientras se escribe. Vacío no envía valor.
- Las referencias RNA inválidas nunca deben detener el pump ni el broadcast.
- El explorador identifica cada fila por nombre y ruta: varios enlaces simbólicos
  pueden compartir un destino canónico sin ser la misma entrada de la lista.
- Knife acumula puntos interiores y divide una cara una sola vez en dos n-gons. No se
  sustituye por triangulación punto a punto. Sondea el BMesh vivo y admite n-gons
  cóncavos de cortes previos; cada segmento recorre la superficie y nunca el volumen.
- El cierre de Tweak identifica `tweak_finished`; Android retira únicamente esa
  sesión MOVE interna y conserva cualquier transformación posterior.
- Las respuestas UPDATE de Tweak describen una transformación (`mode: MOVE`), no
  una escena. Android solo actualiza la escena desde sus snapshots explícitos;
  el arrastre nunca cambia el selector Edit/Object ni cancela su propia entrada.
- El snap táctil filtra primero por geometría visible y después clasifica el candidato.
- Mover sin snap sigue al dedo continuamente; con Incremento avanza en saltos táctiles
  perceptibles y no reutiliza la misma sensibilidad del movimiento libre.
- Un preset de escala de trabajo nunca reescala geometría ni modifica `scale_length`.
- Al crear primitivas, `primitive_size` expresa metros y se divide por el
  `scale_length` vigente antes de llamar a Blender. El cubo de Pequeña mide 10 mm,
  también en archivos donde una unidad Blender equivale a un milímetro.
- Al abrir una escena, el preset mostrado se deduce de su `length_unit`; nunca se
  anuncia Mediana por defecto si el `.blend` está en milímetros o metros.
- La cámara remota no escribe en `rv3d`.
- El zoom ortográfico conserva la profundidad alrededor del pivote: acercarse no
  recorta la cara delantera al atravesar la posición nominal de la cámara. El doble
  toque en Object y el botón Encuadrar encuadran los límites del objeto al 85 % de la vista según orientación y
  proyección reales, también si el PC está en ortográfica.
- CAD es un workspace; Blender permanece en Object. Sus longitudes son metros y
  se convierten a unidades Blender al materializar. IDs y revisión pertenecen al
  documento; la malla evaluada no es la fuente ni admite Edit sin conversión explícita.
- Las previews CAD también son excluyentes con `transform.*` y `tool.*`; confirmación
  crea un undo, cancelación/desconexión restaura y guardar descarta la preview.
- CAD usa la misma entrada y vídeo. El overlay de sketches se proyecta en backend
  y se dibuja en el rectángulo del vídeo en Android; no persiste píxeles como geometría.
- La vista CAD aísla temporalmente sus resultados y restaura la visibilidad previa
  al salir. Los `.blend` y estados de undo conservan la visibilidad de la escena.
- El kernel CAD es nativo: extruye contornos simples y vacía con booleano de Blender.
  El solver NumPy resuelve las restricciones anunciadas, hasta 300 parámetros.
  No anuncia BREP, STEP, el solver completo de FreeCAD, Shell ni fillet de sólidos. La evaluación de
  OCP/CadQuery, build123d y FreeCAD vive en `docs/cad-kernel-evaluation.md`.

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
- Duplicar vive en el radial. En Object conserva normal/enlazado y en Edit duplica la
  selección efectiva.
- En Object, el radial agrupa Alinear caras y las acciones de origen bajo Colocar,
  conservando ocho sectores y el acceso a Borrar.
- Alinear caras pertenece a `tool.*`: mueve únicamente el objeto fuente, conserva
  tamaño, fija el destino y reconstruye desde su matriz inicial. Contacto enfrenta
  normales y hace coincidir centros; orientar y copiar rotación conservan el origen
  de la fuente. Confirmar crea un undo; cancelar o desconectar restaura la matriz.
- Sus controles se describen en el estado de herramienta y se dibujan en la bandeja
  común. Las caras fuente/destino y el candidato se dibujan en GPUOffScreen. Navegar
  con dos dedos cancela el sondeo temporal, sin fijar otra cara.
- Debajo del ojo hay un selector horizontal Object/Edit/CAD/Sculpt; CAD solo aparece
  si el backend lo anuncia. Sculpt se habilita según `sculpt.available` sobre mallas;
  Layouts se ha retirado.
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
- Con Máscara activa, mantener su botón del rail abre «Invertir máscara» y
  «Borrar toda la máscara». Ambas acciones usan el undo nativo; viven en ese menú,
  no en los ajustes de topología de Malla.
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
- Multires/Dyntopo respaldan la malla nativa durante el trazo para restaurar
  desplazamientos y topología; sus archivos privados se retiran al cerrar.
  Guardar desde el PC restaura el baseline en `save_pre` y difiere el cierre del
  historial: nunca ejecuta undo dentro de los handlers de guardado/carga.
  La tablet impide rehacer previews canceladas; el redo directo del PC es nativo.
- Referencias es un tablero local con varias imágenes, zoom, desplazamiento y
  opacidad. Importa copias privadas acotadas y conserva los originales; sus gestos
  quedan en el panel. No son planos 3D ni contenido del `.blend`.
  Se abre desde Archivo → Imágenes de referencia; cerrado no ocupa la vista.
- El encuadre y el clipping siguen el tamaño visto, también en piezas de 1 mm y
  menores; los rangos de preset se convierten por `scale_length`. Edit/CAD no
  interpretan toques consecutivos como encuadre. El panel de vistas ofrece
  «Encuadrar objeto» explícito; cámaras/luces ajenas no ensanchan su fallback.
- Extruir/Bisel/Inset inicializan el paso al 1 % de la menor dimensión útil,
  redondeado a 1/2/5 y acotado por el preset. Una pieza de 1 mm usa 0,01 mm;
  Bisel e Inset comienzan en dos pasos. Los valores editados siguen siendo exactos.
  Bisel interpreta su ancho en mundo con escala sin aplicar, sin cambiar la matriz
  del objeto. Estos valores iniciales no cambian Mover ni Escalar.
- Los botones del Paso de herramientas Edit siguen su orden de magnitud y nunca
  muestran cero por falta de decimales. Sculpt muestra el radio métrico aproximado
  del plano del pivote; su parámetro de gesto continúa siendo relativo a la pantalla.
- El radial Edit separa Selección y Malla, con Duplicar y Borrar accesibles al nivel
  principal. Bisel permanece en el rail; Bridge vive en Malla para dejar visible
  Cortar. Las exclusiones se derivan del catálogo del rail, sin listas duplicadas.
- En Extruir/Bisel/Inset, los botones de distancia y el arrastre libre usan el paso
  físico de la sesión; sin snap conservan sus fracciones. La unidad elegida en Paso
  gobierna también sus distancias. Paso permanece accesible con snap desactivado.
- CAD ofrece «Bocetos → Editar», «Editar boceto» desde un perfil/operación y
  «Finalizar boceto» con texto. Reabrir enfoca el plano y selecciona el original;
  no duplica el boceto ni crea un undo de navegación.
- En Edit, Vértices/Aristas/Caras se sitúa a la izquierda del selector de modo, en
  la misma fila bajo el ojo; no aparece en la barra superior.
- El panel de modificadores queda limitado entre ese selector de modos y el selector
  inferior de vistas/atajos, con un pequeño margen respecto a ambos y sin invadirlos.
- El botón cerrado de modificadores se sitúa 10 dp debajo del selector de modos para
  no tapar el manejador de órbita.
- Pequeña/Mediana/Grande son la única elección de escala visible y fijan respectivamente
  `mm`/`cm`/`m`; no existe un selector de unidad independiente en Android.
- La cabecera muestra preset y unidad activos cuando Blender está conectado, por ejemplo
  `Conectado · Mediana · cm`.
- Los comandos discretos viven en menús contextuales.
- Mayús + Ring añade el anillo a la selección existente (`ADD`) en Aristas y
  Caras; sin modificador reemplaza y Alt resta.
- Los atajos de Edit incluyen J para conectar vértices con la operación nativa
  `mesh.vert_connect_path`; requiere modo Vértices y al menos dos seleccionados,
  divide las caras atravesadas y registra un único undo.
- Los parámetros viven en una bandeja común.
- Las nuevas herramientas deben describirse mediante catálogo/esquema siempre que sea
  posible, evitando nuevas ramas específicas en Compose.
- Los componentes compartidos poseen disposición, estado, unidades y ciclo de sesión;
  Blender conserva únicamente la lógica geométrica específica.
- Mover usa un único `MovementControls` en Object y Edit sobre la misma sesión modal.
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
- Mover, Rotar y Escalar ofrecen Reset dentro de la sesión: restauran la preview a
  `0`, `0°` y `100 %` respectivamente sin cancelar ni reactivar la herramienta.
- Los controles de incremento —paso y botones `−/+`— solo se muestran cuando el Snap
  activo es Incremento, en Mover, Rotar y Escalar.
- En Mover, el selector de unidades va inmediatamente después del campo de incremento,
  antes de `+`. En Escalar, mm/cm/m/% junto a XYZ gobierna dimensiones, paso,
  botones y snap; `Paso` muestra la misma unidad. Cada botón cambia la dimensión de
  su eje; con cadena conserva proporciones. El gesto métrico usa el eje restringido
  o la dimensión mayor de los ejes activos. Los valores escritos y Reset son exactos.
- Escalar admite `0` exacto en % y mm/cm/m para aplanar, también con snap activo.
  Escribir cero en un eje o pulsar X=0/Y=0/Z=0 aplana solo ese eje: una única petición
  conserva los valores visibles de los demás y retira cualquier restricción incompatible.
  La cadena sigue siendo proporcional para valores distintos de cero; Reset recupera el baseline.
- El selector y los pasos de snap viven en `ui/SnapControl.kt`; las bandejas declaran
  opciones y reciben valores, pero no vuelven a implementar su interfaz.
- Los botones −/+ comparten pulsación mantenida: esperan 400 ms y aceleran de
  180 a 80 ms entre incrementos, sin multiplicar el paso. Soltar no añade otro
  incremento; cancelar, desplazar el panel, deshabilitar o retirar el control
  detiene la repetición. Un toque corto sigue dando exactamente un paso.
- El radio proporcional muestra y acepta la unidad del preset (mm/cm/m); sus −/+
  acumulan el paso físico anunciado convertido por `scale_length` (1 mm en Pequeña).
  Cambiar radio, perfil o activación actualiza la influencia desde el baseline sin
  reiniciar la transformación, sus valores ni sus referencias. Reducir el radio
  restaura los vértices excluidos; confirmar sigue creando un único undo.
- Extruir, Inset y Bisel comparten incremento editable y selector mm/cm/m; comienzan
  en la unidad del preset y convierten el paso según `scale_length`. Su arrastre con
  Incremento/Rejilla recorre un paso por el 4 % de altura, conserva fracciones y
  publica el valor visual redondeado. Extruir muestra siempre Paso con −/+ que editan
  el paso en la unidad elegida, conservando la distancia y la preview actuales;
  el siguiente gesto usa ese paso. Distancia tiene sus propios −/+ que suman/restan
  el paso, incluso sin snap. Los botones conservan su valor local entre pulsaciones
  rápidas; Distancia numérica es exacta y no se vuelve a redondear por snap.
  Editar Distancia sustituye al destino geométrico
  sondeado. Knife usa el mismo desplegable de Snap.
- En Bisel, Ancho se muestra en la unidad elegida; con Incremento/Rejilla sus
  botones −/+ restan/suman el paso activo y conservan las pulsaciones rápidas.
- Extruir Región desplaza y selecciona únicamente los vértices nuevos. Los vértices
  originales de las aristas/caras de conexión permanecen fijos, también al continuar
  otra extrusión desde el extremo seleccionado.
- Extruir Región usa la selección efectiva: caras completas también en Vértices o
  Aristas, y aristas completas también en Vértices. Confirmar y después Escalar
  conserva la base y transforma solo el extremo nuevo.
- Extruir identifica cada variante con su icono en rail/menú y su nombre en la
  bandeja. Respeta los modos del catálogo; una variante incompatible no cierra la
  preview anterior. Cambiar de sesión reinicia los borradores de Distancia y Paso.
- Extruir muestra Distancia y Paso en mm normalmente con dos decimales, ampliándolos
  para no mostrar cero en cotas subcentésimas, sin
  redondear los valores enviados. Reset 0 fija la distancia exacta a cero, limpia
  el borrador y el destino geométrico, y conserva la sesión, variante y paso.
- Extruir ofrece Manifold en Caras con la operación nativa de Blender: disuelve
  bordes coplanares e intersecta los nuevos. Comparte distancia, paso, ejes y snap
  de Región; cada preview parte del baseline y confirmar crea un único undo.
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
  conservan sus raíles. La selección múltiple y el arrastre operan sobre IDs y roles
  de puntos/aristas, nunca sobre índices de la malla evaluada.
- Las restricciones CAD se persisten y resuelven al editar o mover. Un conflicto
  no modifica el documento; el arrastre se proyecta a la libertad permitida. Un
  toque sin cambios no crea undo. El redondeo recorta dos líneas conectadas y
  añade un arco con coincidencias, tangencias y radio. Las uniones de línea usan
  la política pegajosa común de `commands/snap.py`.
- Extruir/Vaciar CAD recorren un paso por 4 % de altura con lápiz; Incremento
  redondea el gesto, las cotas escritas son exactas. Vaciar consume su sólido
  destino en el árbol y reconstruye desde los parámetros. La transparencia se
  limita a GPUOffScreen mediante un contexto que restaura el sombreado siempre.
- Un boceto sobre la cara superior sigue el plano/altura de su operación soporte.
  Los soportes con dependientes no se borran ni convierten implícitamente.
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
