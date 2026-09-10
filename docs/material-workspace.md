# Materiales y pintura

Materiales es un workspace de la tablet. Blender permanece en Object Mode. Selecciona
uno o varios objetos en Object, entra con el icono de paleta bajo el ojo y solo verás
esas piezas. Salir devuelve la vista completa. La selección se fija al entrar;
para cambiar el grupo, vuelve a Object y selecciónalo allí.

## Uso

1. Elige **Plástico, Aluminio, Hierro, Cristal, Roca, Madera, Mercurio, Goma,
   Cerámica u Oro**. El catálogo también incluye los materiales importados.
2. Elige **Color**: muestras habituales y controles «Color», «Vivo o apagado» y
   «Claro u oscuro». No hace falta conocer RGB ni los nodos de Blender.
3. El acabado puede ser **Natural**, **Pulido** o **Gastado**. Natural conserva
   los parámetros originales del preset. Pulido/Gastado ajustan el acabado para
   esta aplicación o pincel sin cambiar la receta del catálogo.
4. **Aplicar a todo** asigna la base a todos los objetos aislados. Es una acción
   explícita que sustituye sus asignaciones de material anteriores; admite Deshacer.
   Los objetos enlazados que quedaron fuera del grupo conservan su malla y materiales.
5. Después elige otro material/color y pinta con el lápiz. El pincel mezcla el
   material completo, incluidas sus texturas, con la base. Tamaño e Intensidad
   controlan la marca. La presión del lápiz modula la intensidad; presión cero
   no pinta. **Borrar pintura** retira la capa superior por donde pasa el pincel
   y deja ver lo que había debajo.
6. Un dedo gira la vista y dos dedos navegan. Desactiva **Solo lápiz** para pintar
   también con el dedo. Deshacer/Rehacer recorre trazos completos. Cancelar o
   recibir una palma restaura el trazo. Soltar confirma lo ya dibujado.
7. Elige **Estudio, Exterior, Atardecer o Luz suave** para comprobar el material.
   Se usan los ambientes de Material Preview incluidos en Blender. La iluminación,
   visibilidad, rejilla y gizmos se cambian solo durante la captura GPU y se restauran
   siempre: ni el archivo ni la vista del PC guardan el aislamiento o ambiente remoto.

Cambiar de material/color configura el siguiente pincel. Para sustituir el objeto
completo, pulsa Aplicar a todo. Esta distinción evita que elegir un color borre
accidentalmente un trabajo pintado.

## Capturar escena

**Archivo → Capturar escena…** funciona en Object, Edit, CAD, Sculpt y Materiales,
con H.264, MJPEG o sin un reproductor de vídeo conectado. Produce un PNG con la cámara
y encuadre de la tablet a la resolución de captura actual (hasta el límite configurado).
Android abre su selector de ubicación para guardarlo, sin solicitar permiso global
sobre los archivos. No contiene interfaz Android, rejilla, gizmos, contornos de selección,
overlay CAD ni marcadores de herramientas. Mantiene el aislamiento y aspecto que ves;
para capturar la escena completa, sal del workspace aislado antes de capturar.

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
- Se admiten hasta 16 objetos aislados, 20 000 caras base y 200 000 caras evaluadas
  por objeto para pintar. Los materiales procedurales completos no necesitan ese atlas.
- Los modificadores que mantienen UV se evalúan antes de proyectar la pintura.
  La repetición de UV de un modificador como Mirror o Array comparte la pintura entre
  sus copias, igual que una textura normal de Blender. Geometría generada sin UV no
  puede recibir una máscara de este sistema.
- Hay hasta ocho capas sucesivas de materiales distintos. Trazos consecutivos con
  el mismo material/color/acabado continúan la capa superior y no consumen otra.
  Borrar actúa sobre esa capa superior. Aplicar a todo comienza una nueva base sin
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

Verificación de esta entrega con Blender 5.2.1: 10 pruebas de materiales,
66 pruebas Kotlin, 18 regresiones gráficas de Sculpt y 3 de cadencia de captura
aprobadas; CAD ejecutó 21 pruebas con 4 omisiones por requerir ventana. Las pruebas
propias con GPU verificaron pintura sobre caras inclinadas, cancelación, undo/redo
y persistencia. La prueba por WebSocket verificó capturas en los cinco modos,
propiedad de sesión y desconexión. APK compilado y ZIP validado por Blender.

El comprobador estático `blender-backend/tools/android_contract.py` conserva un fallo
previo en `entities`: la fixture CAD enumera LINE/RECTANGLE/CIRCLE, mientras el
contrato ya enumera también SQUARE/ARC. La diferencia se comprobó contra el commit
anterior a esta implementación y no se ha cambiado en esta incidencia.

No había dispositivo Android conectado: quedan pendientes la comprobación visual
de la interfaz en la tablet y la respuesta de un lápiz físico.


## Flujo y rendimiento tras las pruebas

La bandeja guía **Base → Tinte → Acabado → Detalle**. El tinte y el acabado se
conservan al cambiar de preset; **Aplicar a todo** fija la base explícitamente.
Óxido, Suciedad y Arañazos configuran un pincel con su color de detalle y acabado
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
