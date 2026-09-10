# Workspace CAD: bocetos y sólidos

CAD comparte conexión, vídeo y cámara remota con Object/Edit. Al entrar oculta
los objetos ajenos al documento; al salir, desconectar o guardar restaura su
visibilidad. Blender permanece en Object y el documento paramétrico del `.blend`
es la fuente de la geometría.

## Interfaz de sketch

El rail izquierdo contiene un cursor único, línea,
rectángulo, cuadrado, círculo, arco y redondeo. El rail derecho contiene las
restricciones y solo aparece al editar un boceto. Los raíles y bandejas de
Object/Edit no aparecen en CAD. Cada intención tiene un icono vectorial propio;
mantenerlo pulsado muestra su función. El árbol se abre con **Dibujos** arriba a
la izquierda; cada boceto muestra **Editar** junto a su nombre y plano.

Para continuar un boceto existente, toca **Dibujos → Editar [nombre]**. También
puedes seleccionar un perfil en la vista o una operación en el árbol y pulsar
**Editar boceto** en la cabecera: abre el boceto de origen, encuadra su plano y
activa selección, sin duplicarlo. Toca sus puntos/aristas para cambiar las cotas
en la bandeja o arrástralos directamente con el cursor. Elegir una figura en el rail
activa dibujo; volver al **Cursor** permite editar lo que ya existe.
**Finalizar boceto**, siempre visible en la cabecera durante la edición, vuelve
a los sólidos. Entrar/salir del boceto no crea undo; cambiar su geometría sí
actualiza las operaciones dependientes y registra un paso de undo.

- Dibujar una línea: arrastrar entre extremos. Acercarse a un extremo existente
  lo adquiere con la política táctil común y guarda una coincidencia persistente.
- Rectángulo/cuadrado: arrastrar entre esquinas. El cuadrado guarda igualdad entre
  lados; cambiar su ancho también modifica su alto.
- Círculo: arrastrar centro → radio. Arco: arrastrar centro → inicio; inicialmente
  barre 90° y permite editar radio, ángulo inicial y barrido en grados.
- Cursor: tocar un punto o arista lo añade a la selección; tocarlo otra vez lo
  quita. Los toques sucesivos seleccionan varios sin activar otra herramienta.
  Tocar vacío limpia la selección; arrastrar vacío no la altera.
- Con el mismo cursor, arrastrar un punto o una arista lo selecciona y mueve.
  Conserva el grupo al tocar un miembro seleccionado; un punto restringido se ajusta a sus grados de libertad. Mover una
  esquina de rectángulo conserva la opuesta; mover el radio del círculo conserva
  su centro. Un toque sin movimiento no crea undo.
- Redondear: seleccionar dos líneas con un extremo común, una esquina de un
  rectángulo o dos lados contiguos, y elegir **Redondear esquina** y el radio.
  Recorta los lados e inserta un arco con coincidencias, tangencias y radio.
- Al editar, la vista queda perpendicular al plano; el manejador de órbita desplaza
  la vista y dos dedos permiten pan/zoom sin inclinar el boceto.
- Dos dedos cancelan el trazo/arrastre actual y permiten navegar. Al soltar se
  consume la última preview válida, sin repetir el sondeo.

Restricciones disponibles: coincidencia entre puntos, horizontal, vertical,
paralela, perpendicular, tangencia entre línea y círculo/arco, igualdad de
longitudes o radios, distancia/longitud, radio, punto medio, simetría respecto al
último de tres puntos y fijación estricta de la selección. El origen (0,0) se puede
seleccionar desde la vista o el rail y usar como referencia fija.
El panel **Dibujos** siempre permite acceder a bocetos y figuras, incluso con
selección activa. Sus filas seleccionan figuras completas y ofrecen papelera;
**Restricciones** es una pestaña separada. La bandeja añade **Seleccionar todo**,
**Deseleccionar todo** y **Borrar selección**. El origen queda fuera de Seleccionar
todo y no se borra. Borrar una arista de rectángulo conserva sus otros lados como
líneas; borrar una esquina retira los dos lados incidentes. Un extremo de línea/
arco o el centro/radio de un círculo pertenece a la figura: borrarlo retira esa
figura completa. Se conservan las restricciones de los elementos supervivientes.
El borrado de un perfil utilizado se rechaza antes de cambiar el documento.

Los botones se habilitan según la selección. Las cotas se ven junto a la geometría
y se editan desde el árbol. Sin selección se ve el modelo completo; al elegir un
punto/lado se muestran únicamente sus restricciones, con la medida y las referencias;
cada restricción también puede eliminarse allí. Los cambios incompatibles se
rechazan conservando el documento y la geometría anteriores.

La resolución numérica usa NumPy de Blender y admite hasta 300 parámetros por
boceto. Es un solver acotado a estas restricciones, no el motor completo de
FreeCAD. No anuncia un estado «totalmente restringido» ni restricciones que no
pueda evaluar. Los rectángulos siguen alineados a los ejes de su plano.

## Bandeja de cotas

Paso y dimensiones usan los campos compactos y botones −/+ de las otras bandejas.
Mantener un botón inicia la repetición a los 400 ms y acelera de 180 a 80 ms entre
pasos; soltar no añade otro incremento. La unidad elegida junto a Paso gobierna
las cotas métricas. Los campos angulares permanecen en grados.

Al editar un boceto o una operación confirmada, las cotas quedan en borrador:
**✓** las aplica juntas y **×** las descarta. Ambos botones permanecen fijos a la
derecha aunque desplaces los parámetros. En la preview de Extruir/Vaciar, −/+
actualiza la profundidad visible inmediatamente; ✓ confirma y × cancela la sesión.
Las respuestas antiguas de Blender no hacen perder pulsaciones acumuladas.

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
No se pueden borrar soportes con operaciones o bocetos dependientes:
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
- El redondeo es de sketch entre líneas conectadas o en esquinas de rectángulos. No es fillet de aristas
  del sólido. Vaciar quita un perfil por profundidad; no es una operación Shell
  de espesor automático sobre caras arbitrarias.
- **Planos** permite usar XY/XZ/YZ, el plano de otro boceto, una cara superior
  asociativa o un plano guardado. Un plano nuevo admite desplazamiento XYZ en la
  unidad elegida y rotación XYZ en grados, relativos al plano de referencia.
  **Plano desde cara plana** captura el marco de una cara visible; **Ver objetos
  de la escena** permite elegir referencias externas. Esa referencia conserva su
  posición capturada, sin seguir cambios topológicos de una cara arbitraria.
- **Nuevo cuerpo** crea una pieza independiente. El árbol agrupa sus bocetos y
  operaciones; **Nuevo boceto** está disponible también cuando ya hay otros.
  El ojo de cada boceto oculta/muestra su overlay sin desactivar las operaciones.
- **Construcción** dibuja geometría auxiliar discontinua. También puede convertir
  las figuras seleccionadas; sus restricciones siguen activas y sus contornos
  nunca extruyen ni abren huecos. Si rompería un perfil usado, se rechaza el cambio.
- **Crear copia de malla** sale a Object con una copia seleccionada para Edit o
  Materiales. El original y todo el árbol CAD permanecen editables al regresar.
- Las extrusiones de rectángulos y contornos convexos pares usan tapas y paredes
  en quads ordenados. Los perfiles con huecos y vaciados convierten sus parches a
  quads con puntos medios compartidos, conservando frontera, volumen y conectividad.
  Las zonas cóncavas se descomponen antes para no crear caras cruzadas. La evaluación
  booleana conserva operandos compactos; la malla de presentación no se realimenta
  a cortes posteriores. Es topología editable en quads, sin prometer una cuadrícula
  regular ni un reparto de polos elegido por un artista.
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

La reapertura de bocetos se verifica con 39 pruebas CAD en Blender gráfico y las
pruebas de `CadParserTest` en Android. Incluye reapertura desde perfil/operación,
identidad estable, regeneración del sólido tras editar y ausencia de undo al
entrar/salir. La suite gráfica comprueba además cámara, persistencia y undo real.

La reconexión recupera el workspace y boceto abierto mediante una identidad privada
de la instalación Android. Mantiene cámara y ajustes; las previews interrumpidas
se cancelan y no se reenvían. Cargar otro archivo invalida el estado suspendido.

`test_cad_feedback.py` añade regresiones de origen, fijación por punto/arista,
construcción, planos inclinados, varios cuerpos, exportación sin perder el árbol,
redondeo de rectángulos y recuperación de conexión. Sus comprobaciones gráficas
validan la cámara y las cotas junto con el undo real.

`test_cad_cursor.py` verifica toques aditivos, deselección, adquisición por arrastre,
conservación del grupo, cancelación, ausencia de undo vacío y borrados atómicos de
figuras/lados/puntos, con protección de perfiles utilizados por sólidos.
