# Blender Tablet Remote — guía de trabajo

## Objetivo

La tablet Android es una interfaz táctil para Blender, no un escritorio remoto.
Blender conserva el motor 3D; Android muestra una cámara remota y envía intención
adaptada a dedo y stylus. El alcance actual es Object Mode, Edit Mode y el primer
núcleo del workspace CAD paramétrico descrito en `docs/cad-workspace.md`.

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
- Alinear caras en Object: contacto entre caras, orientación de caras y copia de
  rotación del objeto destino, con preview reversible.
- H.264 preferido con fallback MJPEG.
- CAD v1: planos XY/XZ/YZ, líneas abiertas, rectángulos y círculos, parámetros de
  ancho/alto/diámetro y extrusión asociativa con huecos simples. Documento JSON
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
- Las referencias RNA inválidas nunca deben detener el pump ni el broadcast.
- El explorador identifica cada fila por nombre y ruta: varios enlaces simbólicos
  pueden compartir un destino canónico sin ser la misma entrada de la lista.
- Knife acumula puntos interiores y divide una cara una sola vez en dos n-gons. No se
  sustituye por triangulación punto a punto.
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
- CAD es un workspace; Blender permanece en Object. Sus longitudes son metros y
  se convierten a unidades Blender al materializar. IDs y revisión pertenecen al
  documento; la malla evaluada no es la fuente ni admite Edit sin conversión explícita.
- Las previews CAD también son excluyentes con `transform.*` y `tool.*`; confirmación
  crea un undo, cancelación/desconexión restaura y guardar descarta la preview.
- CAD usa la misma entrada y vídeo. El overlay de sketches se proyecta en backend
  y se dibuja en el rectángulo del vídeo en Android; no persiste píxeles como geometría.
- La vista CAD aísla temporalmente sus resultados y restaura la visibilidad previa
  al salir. Los `.blend` y estados de undo conservan la visibilidad de la escena.
- El kernel CAD v1 es nativo y limitado a perfiles rectangulares/circulares simples.
  No anuncia BREP, STEP, solver general ni operaciones avanzadas. La evaluación de
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
  si el backend lo anuncia. Sculpt y el menú superior
  Layouts son por ahora únicamente presencia visual y no envían comandos.
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
- El selector y los pasos de snap viven en `ui/SnapControl.kt`; las bandejas declaran
  opciones y reciben valores, pero no vuelven a implementar su interfaz.
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
