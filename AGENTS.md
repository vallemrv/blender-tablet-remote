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
  Layouts se ha retirado. En CAD los demás modos se ocultan: solo se ve CAD y,
  al final de la lista, Object como salida.
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
- La bandeja de propiedades Sculpt muestra el detalle de Dyntopo cuando está
  activo, o el selector discreto de niveles Multires y Subdividir cuando existe.
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
  conservan sus raíles. El rail de restricciones se agrupa con separadores:
  posición, orientación, relación y cotas. La selección múltiple y el arrastre operan sobre IDs y roles
  de puntos/aristas, nunca sobre índices de la malla evaluada.
- Las restricciones CAD se persisten y resuelven al editar o mover. Un conflicto
  no modifica el documento; el arrastre se proyecta a la libertad permitida. Un
  toque sin cambios no crea undo. El redondeo recorta dos líneas conectadas y
  añade un arco con coincidencias, tangencias y radio. Las uniones de línea usan
  la política pegajosa común de `commands/snap.py`.
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
  `CENTER/START/END` y `AXIS` es su eje para DISTANCE. Ancho es un RADIUS (0,5).
  `GEAR` es un engranaje recto de evolvente con `module` y `angle` resolubles y
  `teeth` (6–150)/`pressure` (14,5/20/25°) discretos; su RADIUS es el primitivo
  (`value_factor` = dientes/2). Cambiar dientes conserva el módulo; con Incremento,
  dibujar elige el módulo ISO más cercano. Ninguno se somete al test O(n²) de
  autointersección.
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
- En CAD 3D, el rail ofrece Redondear y Chaflán de las aristas del sólido. Sin
  aristas elegidas, el botón pasa a Aristas para tocarlas; con selección abre la
  preview. Extruir admite Simetría: la profundidad crece a los dos lados del croquis.
- Extruir/Vaciar CAD siguen la normal del plano en pantalla: arriba/abajo o
  izquierda/derecha, y también el sentido contrario. El lápiz mueve un prisma
  ligero; el booleano se asienta al soltar. Incremento redondea ese asiento; las
  cotas escritas son exactas. Vaciar crece a un lado del
  croquis (`ONE`) o a los dos (`BOTH`); la profundidad es la de cada lado.
  Vaciar consume su sólido
  destino en el árbol y reconstruye desde los parámetros. La transparencia se
  limita a GPUOffScreen mediante un contexto que restaura el sombreado siempre.
  La sesión reutiliza la teselación local del perfil y sus huecos al variar profundidad;
  conserva operandos compactos para Vaciar y descarta la caché al cerrar. Android
  mantiene una petición CAD en vuelo y solo el último candidato absoluto pendiente
  de profundidad, ancho o lápiz; confirmar respeta ese orden. Navegar continúa
  durante el cálculo; cancelar/guardar/salir descartan la cola y el cálculo pendiente. Un fallo de
  profundidad impide confirmar una medida anterior. Repetir el mismo paso no reconstruye.
- Redondeo/Chaflán (`FILLET`/`CHAMFER`) son nodos de la pila del cuerpo sin boceto
  (`sketch_id: null`): guardan `edges` como segmentos en metros de las aristas de
  diseño elegidas (nunca índices), `width` y `segments` (chaflán = 1). Se evalúan con
  `bmesh.ops.bevel` sobre el sólido compacto tras disolver la teselación coplanar; una
  arista coincide si está en la recta de un segmento guardado y lo solapa, así sobrevive
  a cambios de longitud. Sin coincidencia → error explícito. En modo Aristas la
  selección del sólido se acumula; Redondear/Chaflán abren una sesión `cad.finish.*`
  excluyente, con preview desde el baseline y un undo. No sirven de apoyo de bocetos.
- Un boceto sobre la cara superior sigue el plano/altura de su operación soporte.
  Los soportes con dependientes no se borran; crear una copia de malla conserva sus referencias.
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
- La pintura mezcla shaders mediante máscaras de 1024² empaquetadas y un atlas UV
  privado; no reemplaza las UV existentes. Ocho capas de materiales distintos;
  trazos consecutivos iguales continúan la superior. Borrar retira esa máscara.
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

- CAD bloquea órbita libre y proyección durante el boceto; orbit desplaza la vista,
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
- Los cuerpos son piezas independientes con un historial de croquis/operaciones. Los planos guardados
  admiten desplazamiento métrico y giro local XYZ en grados, con referencias a
  boceto/cara superior. Una cara arbitraria guarda su marco capturado, sin índices
  evaluados persistentes; su adquisición pasa por `commands/snap.py`.
- `cad.convert` crea una copia de malla y sale a Object con ella seleccionada;
  conserva el original, el documento y todos los dependientes. No elimina histórico.
- CAD presenta y mueve la malla compacta del kernel. La retícula de cuadriláteros
  se genera únicamente al crear una copia editable, también al duplicar una pieza CAD.
  La copia se ordena por cara plana de diseño (`cad/quad_layout.py`):
  sin hueco es un parche de cuatro lados; con un hueco, un marco de cuatro parches.
  Se rellenan por interpolación de Coons, sin polo central en círculos. Los lados
  opuestos tienen igual subdivisión: las polilíneas teseladas son fijas y las aristas
  rectas y conectores son libres, resueltas en toda la pieza sin T-junctions. Las
  caras sin disposición válida (varios huecos, contornos cóncavos) caen en los parches
  con puntos medios compartidos. Los operandos booleanos conservan su malla compacta:
  nunca se realimenta la copia editable a operaciones posteriores.
- Los comandos CAD suspenden su respuesta durante la evaluación y se reanudan
  desde el pump. Un proceso Blender persistente calcula booleanos, redondeos y
  el solver de arrastre sobre snapshots; vídeo y navegación siguen atendidos.
  Cada resultado valida escena, documento, unidades y generación de cancelación.
  Cancelar/guardar/desconectar descarta el trabajo y restaura la evaluación baseline;
  cargar/deshacer invalida las cachés. Los ficheros privados y el proceso se retiran
  al cerrar; un error del worker no publica geometría ni crea undo. La retícula
  editable y la materialización final siguen usando el hilo principal del host.
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
- La bandeja inferior CAD usa `CompactNumericField`, `StepperButton` y el campo
  de paso compartido de `SnapControl.kt`; mantener −/+ acelera la repetición
  común de 180 a 80 ms después de 400 ms, sin multiplicar la cota elegida.
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
  restricciones contextuales. Seleccionar todo/Deseleccionar todo, Borrar selección, Construcción y
  Soldar puntos viven junto a Deshacer/Rehacer. Cada candado de medida está junto a
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
- El cuadrado anuncia un único Lado: Igualdad mantiene sus lados iguales, no fija
  su tamaño. Los campos distinguen «sin cota» de «cota», con Fijar medida/Quitar cota;
  quitar la medida conserva la figura y la igualdad. La bandeja usa los descriptores
  `dimensions` del backend, sin duplicar el mapa de medidas en Compose.
- Los redondeos se reconocen por sus coincidencias y tangencias, también en archivos
  anteriores. Editar su radio reconstruye el contacto con las dos líneas; Quitar
  redondeo restituye la esquina y actualiza el perfil de las operaciones dependientes.
  Las medidas/igualdades de lados redondeados usan las esquinas virtuales, no los
  tramos recortados, para conservar el tamaño y la igualdad de un cuadrado.
- Cotas y reglas ofrece Editar y Quitar explícitos. El valor inicial de una nueva
  medida procede de la geometría; si ya existe se abre esa cota, no otra superpuesta.
- Círculo muestra Radio durante el dibujo y tras confirmar. El estado público deriva
  `radius` de `diameter`; ambos editan la misma cota, sin cambiar el almacenamiento.
  Tras dibujar Arco se vuelve al cursor. Su extremo END anuncia `intent:ANGLE` y se
  dibuja como rombo; arrastrarlo cambia solo el barrido, conservando centro, radio e
  inicio y las restricciones. Redondeos no ofrecen tirador angular. Cada preview
  parte del baseline, END no sondea otra posición y confirmar crea un undo si cambió.
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
- La primera selección CAD agrupa contornos suaves mediante uniones de conjuntos:
  calcula una vez qué segmentos terminan en esquinas y materializa cada grupo al
  final. No reinicia un recorrido global ni copia el contorno creciente por cada
  unión. Conserva las aristas rectas y reutiliza el grafo entre Caras/Aristas/Puntos.
- Boceto en cara consume la cara resaltada sin repetir raycast y crea plano+boceto
  en un solo undo. Las caras superiores CAD conservan soporte asociativo; otras
  caras guardan su marco. Las selecciones del sólido son transitorias y se invalidan
  al cambiar geometría o transformación; no persisten índices de la malla evaluada.
- En un boceto, Proyectar está en el rail: cualquier arista, aunque esté a otra
  altura, se copia al plano del croquis como construcción fija. Un contorno
  circular llega como círculo. FIX y un undo. Permite acotar desde esos elementos;
  es una copia fija, no promete asociación topológica con cualquier cara/arista.
  Medir desde sólido se abre desde Planos y bocetos durante la edición; no ocupa
  permanentemente la bandeja de cotas del croquis.
- Finalizar boceto restaura una vista 3D orbital, con encuadre del resultado, sin
  escribir `rv3d`. Extruir/Vaciar muestran su preview en 3D. Si el croquis nuevo tiene
  varios perfiles se selecciona completo (`SKETCH`), no su última figura; un perfil
  único conserva `PROFILE`. La pila muestra solo croquis y operaciones, sin filas
  para figuras o perfiles. El menú del croquis ofrece Renombrar y Seleccionar croquis
  completo; las figuras permanecen dentro de la edición. Tocar un nodo selecciona ese paso.
- Planos ofrece Superior/Frontal/Lateral, una cara y Separación como controles básicos.
  Crear croquis crea plano y boceto en un undo. Inclinación/XYZ son ajustes opcionales;
  Planos existentes permite reutilizar y colocar los guardados con la misma interfaz.
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
  Material/Acabado/Grano y bandeja
  inferior (tamaño, intensidad y una sola línea de ayuda, la del obstáculo actual).
  Lo que se usa durante el trazo vive en el rail, sin plegarse ni abrirse. El panel
  derecho ocupa el sitio, el margen y el gesto de apertura/cierre del inspector de
  modificadores: icono bajo el rail de modos, flecha de vuelta en su cabecera.
  Aplicar vive al pie de ese panel y no dentro de una pestaña: material, acabado y
  grano son una sola receta y se asignan de una vez.
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
