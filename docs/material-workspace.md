# Materiales y pintura

Materiales es un workspace de la tablet. Blender permanece en Object Mode. Selecciona
uno o varios objetos en Object y entra con el icono de paleta bajo el ojo. La escena
permanece visible.

## Disposición

El taller reparte sus controles en cuatro superficies fijas, cada una con una sola
pregunta, en lugar de una bandeja única con todo apilado:

- **Rail izquierdo — qué hace el dedo.** `MODO` ofrece Seleccionar, Pintar y Borrar;
  `TRAZO` ofrece Redondo, Aerógrafo y Salpicado; abajo, Solo lápiz. Es lo único que
  se toca durante un trazo y no cambia de sitio.
- **Barra superior — sobre qué se trabaja.** El botón de objetos indica cuántos hay
  elegidos y despliega la lista para varios o para una pieza interior que queda detrás
  de otra. **Aislar** oculta temporalmente el resto para trabajar dentro de una carcasa;
  desactívalo para ver el conjunto (no cambia la visibilidad guardada). Después,
  **Zona**, guardar la selección de Edit como zona, y **Luz** (ambiente de comprobación).
  El icono de paleta pliega y despliega la biblioteca.
- **Panel derecho — la biblioteca.** Tres pestañas para tres preguntas distintas:
  **Material** (base, color, Aplicar, detalle, guardar/importar), **Acabado** (cómo
  responde a la luz) y **Grano** (qué textura tiene). Cada ficha lleva su color, así
  que el catálogo se reconoce antes de leerlo. Se pliega cuando estorba a la vista.
- **Bandeja inferior — el pincel.** Material y tinte activos, Tamaño, Intensidad y una
  sola línea de ayuda: la del obstáculo actual, no la de todo el flujo.

## Uso

1. Elige en `BASE` **Plástico, Aluminio, Hierro, Cristal, Roca, Madera, Mercurio,
   Goma, Cerámica u Oro**. El catálogo también incluye los materiales importados.
2. El color de partida es **Del material**: el oro se ve oro y el cristal, cristal.
   Cambiar de material cambia también su color, así que se puede recorrer el catálogo
   entero sin perder nada. **Tinte** es una decisión explícita: muestras habituales y
   controles «Color», «Vivo o apagado» y «Claro u oscuro», sin RGB ni nodos. Una vez
   puesto se conserva al cambiar de material, y **Del material** lo retira.
3. La pestaña **Acabado** decide cómo se comporta la superficie con la luz:
   **Natural, Pulido, Satinado, Mate, Gastado, Metálico, Barnizado o Translúcido**.
   Cada uno explica en una línea lo que hace y escribe solo lo suyo: Pulido no
   convierte en metal un plástico, y el barniz del plástico sigue siendo suyo.
   Debajo, `AJUSTE FINO` expone los cinco parámetros reales de la superficie con sus
   extremos en castellano —Pulido (espejo↔mate), Metal, Transparencia, Densidad
   óptica (aire↔diamante) y Barniz—. Tocar uno deja el acabado como punto de partida
   y marca la superficie como ajustada a mano; **Volver al acabado** los descarta.
   La densidad óptica solo aparece cuando hay transparencia, que es cuando significa
   algo. Una línea en azul resume el resultado: «Metal · espejo», «Transparente ·
   brillante». Nada de esto modifica la receta del catálogo.
4. La pestaña **Grano** añade textura de superficie: **Granulado, Vetas, Cepillado o
   Escamas**, con Tamaño, Intensidad y Relieve. Se tiñe sola con el color del material
   y se suma a las texturas que ya trae la receta (la madera conserva sus vetas).
5. **Guardar…** conserva lo que se ve —material, color, acabado, ajustes y grano—
   como material propio de la escena, con su nombre, listo para volver a usarlo o
   para aplicarlo a otro objeto. Queda seleccionado y en limpio. Caben 64 por escena;
   **Importar…** sigue aceptando recetas JSON de otros proyectos.
6. **Aplicar a la selección** asigna la base a esos objetos. Es una acción
   explícita que sustituye sus asignaciones de material anteriores; admite Deshacer.
   Los objetos enlazados que quedaron fuera del grupo conservan su malla y materiales.
7. Después elige otro material/color y pinta con el lápiz. El pincel mezcla el
   material completo, incluidas sus texturas, con la base. Tamaño e Intensidad
   controlan la marca. El rail `TRAZO` ofrece Redondo, Aerógrafo (borde suave) y Salpicado
   (gotas separadas); funcionan con cualquier material de base o detalle. La presión del lápiz modula la intensidad; presión cero
   no pinta. **Borrar**, el tercer modo del rail, retira la capa superior por donde pasa el pincel
   y deja ver lo que había debajo.
8. Un dedo gira la vista y dos dedos navegan. Desactiva **Solo lápiz** para pintar
   también con el dedo. Deshacer/Rehacer recorre trazos completos. Cancelar o
   recibir una palma restaura el trazo. Soltar confirma lo ya dibujado.
9. En **Luz**, elige **Estudio, Exterior, Atardecer o Luz suave** para comprobar el material.
   Se usan los ambientes de Material Preview incluidos en Blender. La iluminación,
   visibilidad, rejilla y gizmos se cambian solo durante la captura GPU y se restauran
   siempre: ni el archivo ni la vista del PC guardan el aislamiento o ambiente remoto.

Cambiar de material/color configura el siguiente pincel. Para sustituir el objeto
completo, pulsa Aplicar a la selección. Esta distinción evita que elegir un color borre
accidentalmente un trabajo pintado.

## Zonas y piezas interiores

Selecciona caras en Edit y vuelve a Materiales. En **Zona**, elige **Caras seleccionadas
en Edit** o pulsa el marcador de la barra superior para conservarla como grupo de
vértices con nombre. Los grupos existentes aparecen también en Zona; se incluyen
solo caras cuyos vértices pertenecen al grupo. En selección múltiple se ofrecen los
grupos comunes a todos los objetos. Separa los objetos para usar grupos diferentes.

Aplica primero una base al objeto completo. Después **Aplicar a la zona** rellena esa
zona con otro color/material; el pincel queda igualmente limitado a ella. La zona
vacía no modifica nada. Los modificadores que conservan el atributo de cara mantienen
la delimitación. Puedes crear así las mitades roja/blanca de una Poké Ball sobre una
sola malla, o seleccionar sus piezas separadas y aplicar materiales por objeto.

Para una bola con piezas interiores, aplica **Cristal** a la esfera exterior y un
color opaco a los objetos interiores. Un tinte claro conserva mejor la visibilidad.
El cristal activa la transmisión por rayos y conecta grosor superficial cero:
evita que la estimación automática de grosor de Eevee salte directamente detrás de
toda la esfera, omitiendo las piezas dentro. La captura activa ray tracing y restaura
el ajuste de escena al terminar. Es una aproximación de superficie para visualización
interactiva, no una simulación óptica de un volumen macizo ni de cáusticas.

El aviso de **20 000 caras** cuenta polígonos de la malla base, antes de modificadores.
El límite sigue vigente para construir el atlas de pincel de 1024²; no limita colores,
trazos ni la aplicación de materiales completos. La bandeja lo indica antes de pintar.
Para detalle geométrico usa una base ligera con Subdivisión sin aplicar (hasta 200 000
caras evaluadas), o aplica materiales completos a las piezas de una malla más densa.

## Capturar escena

**Archivo → Capturar escena…** funciona en Object, Edit, CAD, Sculpt y Materiales,
con H.264, MJPEG o sin un reproductor de vídeo conectado. Produce un PNG con la cámara
y encuadre de la tablet a la resolución de captura actual (hasta el límite configurado).
Android abre su selector de ubicación para guardarlo, sin solicitar permiso global
sobre los archivos. No contiene interfaz Android, rejilla, gizmos, contornos de selección,
overlay CAD ni marcadores de herramientas. Mantiene el aislamiento y aspecto que ves;
para capturar la escena completa, desactiva Aislar selección antes de capturar.

La captura conserva las previews de geometría actuales; no confirma, cancela ni crea
un undo. Es una imagen del viewport, no un render final de Cycles.

## Persistencia y límites explícitos

- Las piezas CAD paramétricas requieren conversión explícita a malla antes de
  texturizarlas. Los objetos enlazados desde bibliotecas externas requieren una copia local.
- Los materiales son nodos nativos de Blender; las máscaras son imágenes PNG de
  1024 × 1024 empaquetadas dentro del `.blend`. No hay archivos de textura externos
  que se pierdan al mover el proyecto.
- El atlas de pintura usa una capa UV privada `TabletPaintUV`; conserva las UV
  existentes y no necesita que el usuario despliegue la malla. Cada cara base recibe
  una región del atlas. Muchas caras reducen la resolución disponible por cara.
- Se admiten hasta 16 objetos seleccionados, 20 000 caras base y 200 000 caras evaluadas
  por objeto para pintar. Los materiales procedurales completos no necesitan ese atlas.
- Los modificadores que mantienen UV se evalúan antes de proyectar la pintura.
  La repetición de UV de un modificador como Mirror o Array comparte la pintura entre
  sus copias, igual que una textura normal de Blender. Geometría generada sin UV no
  puede recibir una máscara de este sistema.
- Hay hasta ocho capas sucesivas de materiales distintos. Trazos consecutivos con
  el mismo material/color/acabado continúan la capa superior y no consumen otra.
  Borrar actúa sobre esa capa superior. Aplicar a la selección comienza una nueva base sin
  capas; Deshacer permite recuperar el trabajo anterior.
- La intensidad es un objetivo de cobertura: repasar con el mismo pincel no oscurece
  arbitrariamente por recibir más paquetes de red. Borrar reduce esa cobertura.
- Cada trazo usa imágenes y asignaciones independientes de sus versiones confirmadas,
  de modo que el undo global de Blender restaura también los píxeles. Un trazo vacío
  no crea undo. Guardar desde el PC descarta una preview pendiente antes de escribir.
- Texturizar no añade mapas UV a Sculpt, no activa Texture Paint nativo, no remalla ni
  cambia la geometría. Para detalles superiores se puede aumentar el atlas en una
  versión posterior del protocolo; esta versión anuncia su tamaño real.
- Los presets importados se guardan por escena, hasta 64. El JSON original sigue siendo
  la forma de compartir una receta con otros proyectos o clientes.

## Formato abierto Tablet Material Recipe 1

El contrato completo está en [material-recipe-v1.md](material-recipe-v1.md), con
[JSON Schema](material-recipe-v1.schema.json) y ejemplos importables. Es un formato
propio, público y versionado: JSON, sin Python, expresiones ejecutables ni descargas
implícitas. Una IA puede generar recetas siguiendo esa especificación sin tener
que reproducir la interfaz de Blender.

## Verificación

`test_materials.py` comprueba compilación de presets, validación, aislamiento de datos,
UV, imágenes, oclusión y cancelación. `test_materials_viewport.py` se ejecuta con ventana
real y GPU: captura, pintura, undo/redo, guardado/carga y restauración de visibilidad.
Las pruebas Kotlin cubren el parsing y la cola ordenada compartida de trazos.

Verificación actual con Blender 5.2.1: 22 pruebas de materiales, 6 de acabados
(`test_materials_finish.py`: color propio, composición acabado/ajustes, grano y
guardado) y 80 pruebas Kotlin aprobadas. Las pruebas con GPU verifican pintura,
cancelación, undo/redo, guardado/carga y cristal con un objeto interior visible.
La prueba por WebSocket comprueba selección vacía, selección por toque, pintura y
recuperación de los nuevos ajustes después de reconectar; las pruebas con ventana
y GPU no se han vuelto a ejecutar tras la ampliación de acabados. APK compilado.

El comprobador estático `blender-backend/tools/android_contract.py` conserva un fallo
previo en `entities`: la fixture CAD enumera LINE/RECTANGLE/CIRCLE, mientras el
contrato ya enumera también SQUARE/ARC. La diferencia se comprobó contra el commit
anterior a esta implementación y no se ha cambiado en esta incidencia.

No había dispositivo Android conectado: quedan pendientes la comprobación visual
de la interfaz en la tablet y la respuesta de un lápiz físico.


## Flujo y rendimiento tras las pruebas

La biblioteca guía **Base → Color → Acabado → Grano → Detalle**. La apariencia se
compone siempre en el mismo orden: receta del catálogo, acabado encima y ajustes
finos encima de todo. El tinte, el acabado y los ajustes se conservan al cambiar de
preset; **Aplicar a la selección** fija la base explícitamente.
Óxido, Suciedad y Arañazos configuran un pincel con su propio color y acabado
natural en el mismo gesto. Pintar los mezcla sobre la base mediante máscaras;
seleccionarlos no sustituye el material aplicado a todo el objeto.

El atlas se reutiliza por identidad de geometría evaluada, matriz y UV. Cada trazo
proyecta/oculta sus muestras una vez e indexa las visibles en teselas de pantalla.
Cada aplicación procesa únicamente las teselas bajo el pincel. La profundidad
Workbench se reutiliza mientras cámara y geometría coincidan, también durante
el trazo. Las ediciones desde el PC invalidan la caché.

En la regresión de 262 144 texeles y 128 aplicaciones, el cálculo por teselas tardó
17,3 ms frente a 339,1 ms del recorrido completo (misma máscara; proyección inicial
42,5 ms). Es una medición del cálculo de pintura, no una medida extremo a extremo
ni una garantía de FPS. La prueba gráfica comprueba pintura, cancelación, undo/redo,
conservación de máscaras al guardar y restauración de la visibilidad del PC.

Wireframe se ha retirado de Materiales/Texturas. Las peticiones antiguas o en vuelo
se normalizan a Solid. Si Wireframe ya estaba activo o se activa desde el PC,
la siguiente captura pasa a Solid y conserva ese estado al terminar, evitando
restaurar Wireframe entre fotogramas. Los demás ajustes del viewport se restauran.
