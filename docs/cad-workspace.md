# Workspace CAD paramétrico

Este primer núcleo implementa el recorrido recomendado en las secciones 37–38 del
[documento original](../PLAN_CAD_PARAMETRICO_BLENDER_TABLET_REMOTE.md). Convive con
Object y Edit en la misma aplicación, conexión, cámara y viewport.

Al entrar, **Vista CAD aislada** oculta temporalmente los objetos ajenos al
documento para que no tapen el boceto. Al salir o desconectarse se recupera su
visibilidad anterior; guardar el archivo no convierte ese aislamiento en objetos
ocultos permanentemente.
Entrar con un documento existente encuadra su boceto para que una pieza pequeña
sea visible tras reabrir el archivo; pulsar CAD otra vez conserva la vista actual.

## Dibujar, acotar y extruir

1. Instalar juntos el APK y el ZIP de esta entrega. Conectar la tablet al servidor.
2. Pulsar **CAD**, junto a Object/Edit. Solo aparece si el servidor anuncia CAD v1.
3. Elegir **Boceto XY** (también se admiten XZ y YZ).
4. Elegir **Rectángulo** y arrastrar entre dos esquinas. Al soltar se confirma la
   última posición estable. Un segundo dedo cancela el trazo y permite navegar.
5. Seleccionar el rectángulo en la vista o en **Modelo**. Elegir mm y escribir
   **Ancho 80**, **Alto 45**, pulsando **Aplicar** en cada cota.
6. Elegir **Círculo**, arrastrar desde el centro y fijar **Diámetro 6**. Situarlo
   completamente dentro del rectángulo para obtener un agujero en la extrusión.
7. Pulsar **Finalizar boceto**, seleccionar el perfil **Rectángulo** y **Extruir**.
8. Revisar **Profundidad 20 mm**, navegar para ver la pieza y pulsar **Confirmar**.
   **Cancelar** restaura el documento y la geometría anteriores.
9. Seleccionar la extrusión y **Editar boceto**, seleccionar el rectángulo, cambiar
   el ancho a **100** y pulsar **Aplicar**. Se reconstruye la extrusión asociada.
10. Guardar el `.blend` con el menú Archivo. Al abrirlo de nuevo, entrar en CAD y
    elegir el sketch o la extrusión del árbol para seguir editando.

**Modelo** muestra u oculta el árbol para dejar más espacio al dibujo. En el árbol
se seleccionan sketches, perfiles y extrusiones. La bandeja permite editar la
profundidad, ocultar/mostrar el resultado y borrar una extrusión. Las entidades con
una extrusión dependiente no se borran de forma implícita.

El contorno exterior de un rectángulo o círculo puede contener contornos interiores
separados: se evalúan como huecos. Las intersecciones, tangencias, huecos anidados y
medidas degeneradas se rechazan conservando la última geometría válida.

## Datos y límites

- El `.blend` guarda un documento JSON versionado, IDs estables y una revisión.
  Las longitudes autoritativas son metros; mm/cm/m son su representación en Android.
- La malla evaluada mantiene una asociación con su documento y feature. Cambiar una
  cota reconstruye desde los parámetros, sin acumular deformaciones sobre la malla.
- Una preview es reversible y pertenece a una conexión. Su confirmación crea un
  único paso de undo. Guardar, cambiar de modo o desconectar descarta la preview.
- Para editar vértices Blender, seleccionar la extrusión y ejecutar deliberadamente
  **Convertir a malla**. Esa acción elimina la asociación paramétrica del resultado;
  Blender undo puede recuperarla.
- Esta entrega admite líneas abiertas, rectángulos y círculos sobre planos principales.
  La extrusión de perfiles se limita a rectángulos y círculos. Las cadenas arbitrarias
  de líneas, arcos, restricciones entre entidades, cotas de referencia y un solver
  general no forman parte de este primer recorrido.
- Las cotas de rectángulo y diámetro son parámetros directos. No se presentan como
  un sistema general de restricciones ni como un estado «totalmente restringido».
- El kernel nativo produce mallas; el círculo mantiene su diámetro exacto en el
  documento y se aproxima con segmentos al visualizar/evaluar la superficie.
  No se anuncia un sólido BREP exportable a STEP.
- El overlay Android recibe puntos proyectados por la cámara del backend; sus
  coordenadas no se almacenan como geometría. Su actualización viaja por control,
  mientras el vídeo usa H.264/MJPEG: puede existir desfase durante la navegación.
- Cut, revolve, hole como feature independiente, fillet, chamfer y patterns quedan
  para los siguientes ciclos del documento, después de estabilizar este núcleo.

La evaluación reproducible de CadQuery/OCP, build123d y FreeCAD está en
[cad-kernel-evaluation.md](cad-kernel-evaluation.md). La definición del protocolo y
sus capabilities está en [protocol.md](../blender-backend/docs/protocol.md).

## Verificación

El desarrollo se verifica en Blender con geometría real, guardado/reapertura,
preview/cancelación y undo/redo; Android verifica parser, capabilities y el fixture
compartido. Las pruebas de UI se ejecutan en un emulador Android API 35 de tablet,
con una instancia Blender independiente de la escena del usuario.

Se comprobó el recorrido de 80 × 45 mm, círculo Ø6 mm y extrusión de 20 mm,
seguido del cambio de ancho a 100 mm. Guardar y abrir desde el menú Archivo de
Android recuperó el mismo documento,
las cotas y sus dependencias; deshacer/rehacer desde Android reconstruyó el cambio.
La entrada multitáctil real del emulador canceló un trazo al apoyar el segundo
dedo, sin crear una entidad accidental. Salir de CAD o desconectar restauró los
objetos ocultados por el aislamiento. También pasan las regresiones de snap,
Tweak y alineación de caras.

El emulador no sustituye una prueba física de presión, rechazo de palma o tacto del
stylus en el dispositivo del usuario.
