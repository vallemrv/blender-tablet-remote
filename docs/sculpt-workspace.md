# Escultura con lápiz en la tablet

Selecciona una malla en Object y pulsa Sculpt bajo el ojo. Blender debe tener una
ventana 3D: se anuncia desde Blender 4.4, y la implementación está comprobada con
Blender 5.2.1. Las piezas CAD requieren conversión explícita a malla.

El rail ofrece Dibujar, Arcilla, Inflar, Pliegue, Aplanar, Agarrar, Suavizar,
Máscara y Pellizcar. Son los pinceles nativos de los recursos esenciales de Blender.
La bandeja reúne tamaño, fuerza, presión sobre fuerza o tamaño, inversión y
suavizado temporal. La simetría X/Y/Z actúa en los ejes locales del objeto.
Radio muestra la medida aproximada en mm/cm/m sobre el plano del pivote (`≈`);
el círculo conserva su tamaño en pantalla y esa medida cambia al acercar la vista.
El lápiz transmite presión real, incluidos sus puntos históricos; el dedo usa
fuerza uniforme. En «Solo lápiz», un dedo orbita y dos desplazan/zoom. Los dedos
que se apoyan mientras el lápiz está dibujando se ignoran como posibles contactos
de palma. En «Lápiz + dedo», pasar del dibujo con dedo a dos dedos cancela ese trazo.

Un trazo crea una preview visible. Levantar el lápiz conserva el último resultado
mostrado, sin volver a sondear la posición de salida, y deja un paso de undo.
Cancelar, perder la conexión o cambiar de herramienta restaura el punto de partida.
Las respuestas atrasadas se identifican por propietario e ID de trazo.

## Resolución

**Dyntopo** subdivide y colapsa topología mientras se esculpe. Detalle expresa el
tamaño relativo nativo en píxeles (1–40): un número menor produce más densidad.
Como en Blender, la triangulación dinámica puede perder UVs, colores, grupos de
caras y otros atributos. No admite claves de forma ni un modificador Multires.

**Multires** añade el modificador nativo con un primer nivel de subdivisión,
permite subdividir de nuevo y elegir el nivel de trabajo. Conserva el detalle de
los niveles superiores al bajar y subir. Desde la tablet se limita a seis niveles;
el coste real depende de las caras del objeto. La malla debe ser propia: una
copia enlazada necesita convertirse primero en copia normal.

En Object se encuentra en **Modificadores → + → Multiresolución**. La tarjeta
ofrece Vista, Escultura y Render, muestra los niveles creados y tiene
**Subdividir (+1 nivel)**. El botón crea resolución real; los selectores recorren
los niveles ya creados. También sigue disponible desde Malla dentro de Sculpt.

En la comparación controlada de vídeo con Subdivision 2, GPU GTX 1080,
1280 × 710 y la misma calidad, dos rondas pasaron de 19,25–19,75 a 22,25–22,75 fps.
El retraso mediano de captura a recepción HTTP local pasó de 92–95 a 48–57 ms;
el percentil 95, de 162–174 a unos 88 ms. Es una medida del PC y del transporte
local, no de la red Wi-Fi ni de la respuesta física del lápiz. Se eliminaron
recorridos por byte en el parser H.264 y esperas innecesarias entre capturas.

La salida H.264 también publica ahora cada fotograma al completar su paquete, sin
retenerlo hasta recibir el siguiente. En una prueba del codificador con 48 cuadros
RGBA de 640 × 480 a 24 fps, la mediana pasó de 46,69 a 2,09 ms (P95: 47,03 a
5,42 ms). El último cuadro se recibió sin enviar otro ni cerrar ffmpeg. Es una
medida aislada del codificador: los costes del trazo, Dyntopo, la captura, la red
y la tablet se suman. Dyntopo continúa reconstruyendo topología y restaurando su
baseline nativo durante la preview, por lo que su coste crece con el detalle y el
recorrido.

Máscara protege zonas frente a los pinceles. Con ese pincel activo, una pulsación
larga sobre su botón del rail abre «Invertir máscara» y «Borrar toda la máscara».
Ambas acciones admiten Deshacer. Suavizar temporalmente usa Smooth y mantiene el pincel elegido para el
siguiente trazo.

La rejilla y los ejes se ocultan en el vídeo mientras Sculpt está activo. Al salir
vuelven a su estado anterior; las máscaras y las demás ayudas siguen disponibles.

Las imágenes de referencia viven en el panel Referencias de Android: se importan
desde Archivo → Imágenes de referencia, se conservan localmente y permiten
comparar proporciones mientras se esculpe. Su funcionamiento completo está en
[referencias](reference-images.md).

## Implementación y límites comprobados

Los trazos ejecutan `bpy.ops.sculpt.brush_stroke('EXEC_DEFAULT', True, ...)` desde
el pump principal. Las muestras se sondean sobre la superficie visible del último
GPUOffScreen; su profundidad se invalida al cambiar de cámara, tamaño o archivo.
El raycast también descarta objetos que ocultan la malla activa. Sin profundidad
capturada se usa el raycast de la malla evaluada, que representa la base en Sculpt.

El motor nativo depende de su vista para Agarrar y otros cálculos. Durante su
llamada se adapta temporalmente la matriz del objeto a la cámara remota y se
restaura en `finally`; no se escribe en `rv3d` ni se cambia la vista del PC.
El tamaño nativo usa píxeles de pantalla para evitar el mínimo RNA de 0,001
unidades del campo de tamaño en mundo. La adaptación coloca temporalmente el
trazo a la profundidad de trabajo del PC, evitando que su near plane excluya
una pieza milimétrica. Al terminar la llamada se restaura la matriz original.

Cada actualización deshace la preview nativa anterior y reproduce las aplicaciones
acumuladas. El historial del lápiz se remuestrea con el espaciado nativo del pincel,
conservando el recorrido y la presión interpolada. El extremo visible es provisional:
se sustituye en la siguiente actualización, sin acumular una aplicación por paquete.
Grab conserva su recorrido completo. Hay una sola solicitud de trazo en vuelo en
Android. Se admiten 128
muestras por mensaje y 4096 por trazo; al superar ese límite se conserva la última
preview confirmándola y se pide levantar el lápiz para continuar con otro trazo.
La reproducción completa cuesta más cuanto más largo es el trazo o más
densa es la malla; no se presupone una latencia fija en escenas grandes.

En malla ordinaria se actualiza además su superficie sólida durante el trazo y al
cancelar/deshacer, sin cambiar de modo ni activar Wireframe. Con una esfera de unas
6.000 caras y Mirror, un recorrido de 400 muestras con Suavizar pasó de unos 69 ms
a 20 ms en la última actualización. Es tiempo del backend, no latencia total del lápiz.

Multires muestra en GPUOffScreen la superficie correspondiente a **Escultura**, aunque
**Vista** tenga otro nivel. Workbench no utiliza los buffers de escultura PBVH al
dibujar una imagen offscreen: las rejillas nativas se materializan temporalmente
como malla evaluada mediante `use_sculpt_base_mesh`, y se restauran antes de volver
a aceptar entrada. Se conserva el estado original del flag. No se actualiza la
malla base con `Mesh.update()`, no se cambia de modo y no se aplica el modificador.
El relieve aparece durante el trazo y al confirmar, cancelar, deshacer o rehacer.
Esta evaluación tiene un coste dependiente del nivel y del tamaño de la malla.

Multires y Dyntopo conservan además un baseline nativo en un archivo `.blend`
temporal privado, retirado al confirmar, cancelar, desconectar o cargar otra
escena. Esto preserva las rejillas de desplazamiento y toda la topología al
reproducir. La confirmación sustituye la preview nativa por un único estado global
de undo con su última geometría visual. Los materiales conservan sus IDs.
Esta ruta tiene costes adicionales de copia y E/S, especialmente en niveles altos.

Guardar desde la tablet cierra el trazo antes de guardar. Si se guarda desde el PC,
el handler serializa el baseline y termina su cierre después del guardado: Blender
no permite ejecutar undo de manera segura dentro de `save_pre`. Abrir otra escena
retira la sesión anterior sin ejecutar undo dentro de `load_pre`.

Blender puede conservar en su pila de redo nativa una preview cancelada hasta la
siguiente edición. La tablet mantiene una barrera para impedir recuperarla,
permitiendo deshacer y rehacer los pasos confirmados anteriores. El redo invocado
directamente desde el PC sigue perteneciendo a Blender.

Pruebas gráficas:

```bash
blender -t 2 --factory-startup --python blender-backend/tests/test_sculpt.py
```

Comprueban presión, Agarrar con cámaras distintas, simetría/activos nativos,
preview y undo, propiedad de trazo, Dyntopo, Multires con dos confirmaciones y sus
undo/redo, conservación de material y nivel, profundidad/oclusión, guardado,
carga, desconexión y limpieza ante fallos de snapshot. La regresión de Multires
compara píxeles y profundidad en Sólido con niveles de Vista/Escultura distintos,
durante el trazo y tras cancelación/confirmación/undo/redo; también comprueba que
un error de dibujo restaure el flag de evaluación. Las 17 pruebas gráficas de
Sculpt pasan con esta corrección.

Validación del refinamiento: 14 pruebas gráficas de escultura (incluida una pieza
de 1 mm con PC en perspectiva y ortográfica), 39 de CAD, 56 de Android,
8 de cámara/edición proporcional, 4 de dimensiones, 5 de primitivas y 26 de Edit
aprobadas. APK compilado,
ZIP validado con Blender y comprobación de interfaz conectada en tablet emulada.
La sensación y respuesta de un lápiz físico quedan pendientes de validación en
el dispositivo del usuario.
