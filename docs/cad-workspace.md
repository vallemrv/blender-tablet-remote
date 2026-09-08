# Workspace CAD: bocetos y sólidos

CAD comparte conexión, vídeo y cámara remota con Object/Edit. Al entrar oculta
los objetos ajenos al documento; al salir, desconectar o guardar restaura su
visibilidad. Blender permanece en Object y el documento paramétrico del `.blend`
es la fuente de la geometría.

## Interfaz de sketch

El rail izquierdo contiene selección, selección múltiple, arrastre, línea,
rectángulo, cuadrado, círculo, arco y redondeo. El rail derecho contiene las
restricciones y solo aparece al editar un boceto. Los raíles y bandejas de
Object/Edit no aparecen en CAD. Cada intención tiene un icono vectorial propio;
mantenerlo pulsado muestra su función. El árbol se abre con su icono superior.

- Dibujar una línea: arrastrar entre extremos. Acercarse a un extremo existente
  lo adquiere con la política táctil común y guarda una coincidencia persistente.
- Rectángulo/cuadrado: arrastrar entre esquinas. El cuadrado guarda igualdad entre
  lados; cambiar su ancho también modifica su alto.
- Círculo: arrastrar centro → radio. Arco: arrastrar centro → inicio; inicialmente
  barre 90° y permite editar radio, ángulo inicial y barrido en grados.
- Seleccionar: tocar un punto o arista. El cursor con `+` permite añadir/quitar
  elementos para aplicar restricciones o mover un grupo.
- Mover: arrastrar un punto o una arista. Conserva el grupo al tocar un miembro
  seleccionado; un punto restringido se ajusta a sus grados de libertad. Mover una
  esquina de rectángulo conserva la opuesta; mover el radio del círculo conserva
  su centro. Un toque sin movimiento no crea undo.
- Redondear: seleccionar dos líneas con un extremo común y elegir el radio.
  Recorta los lados e inserta un arco con coincidencias, tangencias y radio.
- Dos dedos cancelan el trazo/arrastre actual y permiten navegar. Al soltar se
  consume la última preview válida, sin repetir el sondeo.

Restricciones disponibles: coincidencia entre puntos, horizontal, vertical,
paralela, perpendicular, tangencia entre línea y círculo/arco, igualdad de
longitudes o radios, distancia/longitud, radio y fijación de una entidad completa.
Los botones se habilitan según la selección. Las cotas se editan desde el árbol;
cada restricción también puede eliminarse allí. Los cambios incompatibles se
rechazan conservando el documento y la geometría anteriores.

La resolución numérica usa NumPy de Blender y admite hasta 300 parámetros por
boceto. Es un solver acotado a estas restricciones, no el motor completo de
FreeCAD. No anuncia un estado «totalmente restringido» ni restricciones que no
pueda evaluar. Los rectángulos siguen alineados a los ejes de su plano.

## Extruir y vaciar con el lápiz

1. Crear un boceto XY/XZ/YZ y dibujar un perfil cerrado. También se reconocen
   cadenas cerradas no ramificadas de líneas y arcos unidos en sus extremos.
2. Finalizar el boceto, seleccionar el perfil y pulsar **Extruir** en el rail.
3. Deslizar arriba/abajo para cambiar profundidad: cada 4 % de altura recorre un
   paso. Con Incremento avanza en saltos; sin snap conserva las fracciones.
   La bandeja permite editar el paso, la profundidad exacta y los botones −/+.
4. Confirmar crea un undo; cancelar restaura el resultado anterior.
5. Para vaciar desde arriba, seleccionar el sólido en el árbol y crear un boceto
   sobre su cara superior con el icono de boceto. Su plano sigue la altura de la
   operación de soporte. Dibujar el hueco y finalizar el boceto.
6. Seleccionar ese perfil, elegir el sólido **Destino** y pulsar **Vaciar**.
   La profundidad entra en dirección contraria a la normal del boceto. El lápiz,
   paso y botones funcionan como en Extruir. Puede atravesar toda la pieza.
7. Durante el vaciado la captura GPU de la tablet activa transparencia al 35 %;
   restaura los ajustes de sombreado tras cada captura, incluso si falla el render.
   Confirmar/cancelar termina la transparencia automáticamente.

Un vaciado es una diferencia booleana exacta de Blender sobre mallas evaluadas.
Consume visualmente su operación destino conservando su dependencia en el árbol.
Cambiar el perfil, la profundidad o la altura del soporte reconstruye el resultado.
Un perfil que no intersecta el destino o elimina todo el sólido se rechaza.
No se pueden borrar/convertir soportes con operaciones o bocetos dependientes:
primero se eliminan los dependientes. El árbol permite borrar bocetos sin operaciones.

## Persistencia y límites

- Documento JSON v1 extendido con IDs estables, revisión, restricciones, planos de
  soporte y features `EXTRUDE`/`CUT`. APK y ZIP se instalan juntos.
- Las longitudes son metros; mm/cm/m son la representación en Android. Los ángulos
  de arco se guardan en grados. Las medidas se convierten a unidades Blender al
  materializar, también cuando una unidad Blender equivale a un milímetro.
- Las previews pertenecen a una conexión y son excluyentes con `transform.*` y
  `tool.*`. Guardar, desconectar o salir descarta la preview. Confirmación crea un
  único undo. Las cotas y restricciones reconstruyen las operaciones dependientes.
- Los contornos exteriores admiten huecos simples separados. Se rechazan cruces,
  tangencias entre contornos y huecos anidados. No se extraen regiones arbitrarias
  de una red de segmentos cruzados o ramificados.
- El resultado es una malla. Círculos/arcos mantienen parámetros analíticos en el
  documento y se segmentan al visualizar/evaluar. No es BREP ni exporta STEP.
- El redondeo es de sketch entre dos líneas conectadas. No es fillet de aristas
  del sólido. Vaciar quita un perfil por profundidad; no es una operación Shell
  de espesor automático sobre caras arbitrarias.
- Los bocetos se apoyan en planos principales o en la cara superior de una
  operación; todavía no hay referencias persistentes a cualquier cara 3D.
- El overlay se proyecta en Blender y se dibuja en el rectángulo del vídeo Android.
  Sus píxeles no se guardan como geometría. El control y el vídeo tienen canales
  separados, por lo que puede existir un pequeño desfase durante la navegación.

Referencias de interacción: [Sketcher de FreeCAD](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Sketcher_Workbench.md),
[redondeo de sketch](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Sketcher_CreateFillet.md)
y [extrusión de Fusion](https://help.autodesk.com/view/fusion360/ENU/?guid=SLD-EXTRUDE-SOLID).
Los iconos son vectores originales en `ui/Iconography.kt`.

La evaluación de kernels binarios está en [cad-kernel-evaluation.md](cad-kernel-evaluation.md).
El contrato está en [protocol.md](../blender-backend/docs/protocol.md).

## Verificación

`blender-backend/tests/test_cad_sketch.py` comprueba geometría real, restricciones,
conflictos, arrastre, unión automática, redondeo, volumen/manifold, vaciado,
cancelación, soporte asociativo y conversión de unidades. Hereda los recorridos
CAD de persistencia y undo/redo; las comprobaciones de cámara y undo real requieren
una instancia gráfica independiente. Android verifica el parser y las capabilities.

La tablet emulada sirve para revisar disposición, iconos y entrada, pero no
sustituye comprobar la sensación del lápiz y el rechazo de palma en la tablet física.

Comprobación de esta entrega: 38 pruebas CAD pasan en Blender gráfico, 35 pruebas
unitarias Android pasan y la tablet emulada completa dibujo, arrastre, extrusión
por gesto y vaciado con transparencia. La comprobación de snap pasa sus pruebas
sin viewport (13 pasan; 2 requieren su propio entorno gráfico).
