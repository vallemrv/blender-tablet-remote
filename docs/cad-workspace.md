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
mantenerlo pulsado muestra su función. El panel se abre con **Modelo** (en 3D) o **Boceto activo** (al editar), arriba a
la izquierda; cada boceto muestra **Editar** junto a su nombre y plano.

Para continuar un boceto existente, toca **Modelo → Ver historial → Editar [nombre]**. También
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
- Rectángulo: arrastrar entre esquinas. Para un cuadrado, selecciona dos lados
  contiguos y aplica Igualdad; cambiar su ancho también modifica su alto.
- La bandeja muestra solo medidas (longitud, ancho/alto, radio y el ángulo del arco),
  no coordenadas. La posición se fija con candados y con cotas a otros puntos: el
  origen, esquinas, extremos o centros de otras figuras.
- Polígono regular: arrastrar centro → vértice (6 lados por defecto; los lados se eligen
  antes de dibujar o después con −/+). Su medida es **Entre caras** (la llave de una
  tuerca; en impares, el Ø inscrito) y su candado la fija. Con la medida fijada,
  arrastrar un vértice solo lo gira. Sirve para tuercas y alojamientos de tuerca.
- Ranura: arrastrar del centro de un extremo al del otro. Sus medidas son **Ancho**
  (diámetro de los extremos) y **Entre centros**; arrastrar un centro de extremo deja
  fijo el otro. Sirve para agujeros alargados y ajustes regulables.
- Engranaje recto de evolvente: arrastrar centro → círculo primitivo (20 dientes por
  defecto). Su medida es el **Módulo** (Ø primitivo = módulo × dientes; paso = π·módulo);
  con Incremento se elige el módulo normalizado más cercano. Dientes (6–150) y ángulo de
  presión (14,5°/20°/25°) se cambian después conservando el módulo. Dos engranajes del
  mismo módulo y ángulo engranan con sus centros a (Ø₁ + Ø₂)/2.
- Círculo: arrastrar centro → radio. Arco: arrastrar centro → inicio; inicialmente
  barre 90° y permite editar radio, ángulo inicial y barrido en grados.
- Dibujar usa las mismas ayudas que editar: el Snap Incremento y su Paso siguen en la
  bandeja con la herramienta elegida. El inicio se engancha a un punto existente
  (origen, esquina, extremo o centro) con una coincidencia; si no, cae en la rejilla
  del paso. Tamaños y radios se redondean al paso y las medidas se ven en vivo;
  al soltar se editan en la misma bandeja. Una figura menor que un paso no se crea.
- Cursor: tocar un punto o arista lo añade a la selección; tocarlo otra vez lo
  quita. Los toques sucesivos seleccionan varios sin activar otra herramienta.
  Tocar vacío limpia la selección; arrastrar vacío no la altera.
- Con el mismo cursor, arrastrar un punto o una arista lo selecciona y mueve.
  Conserva el grupo al tocar un miembro seleccionado; un punto restringido se ajusta a sus grados de libertad. Mover una
  esquina de rectángulo/cuadrado conserva su centro: las otras tres esquinas
  se reajustan en simetría; mover el radio del círculo conserva su centro.
  Un toque sin movimiento no crea undo.
- Redondear: selecciona una o varias esquinas (toca cada una), un rectángulo entero
  (sus cuatro esquinas; por ejemplo con Seleccionar todo), dos lados contiguos o las
  líneas de un contorno, y elige **Redondear esquinas seleccionadas** y el radio.
  Tras el primer redondeo el rectángulo pasa a ser líneas: tocar otra esquina sigue
  funcionando. Recorta los lados e inserta arcos con coincidencias y tangencias; todos
  los de una misma vez comparten el radio (editar uno cambia todos).
- Al editar, la vista queda perpendicular al plano y de pie respecto al mundo, aunque
  la cara no tenga un arriba propio (un círculo). Dos dedos giran esa vista y se queda;
  **Girar 90°** y **Enderezar** hacen lo mismo a saltos. El manejador de órbita desplaza
  la vista y dos dedos permiten pan/zoom sin dejar el plano. Con la pila cerrada,
  el círculo de navegación de la derecha (el mismo de Mover/Rotar/Escalar) gira la
  cámara en perspectiva para ver cómo queda el dibujo sobre la pieza; al soltarlo
  vuelve a la vista ortográfica del plano. En Extruir/Vaciar orbita la preview.
- Dos dedos cancelan el trazo/arrastre actual y permiten navegar. Al soltar se
  consume la última preview válida, sin repetir el sondeo.

Restricciones disponibles: coincidencia entre puntos, horizontal, vertical,
paralela, perpendicular, tangencia entre línea y círculo/arco, igualdad de
longitudes o radios, distancia diagonal/horizontal/vertical, radio, punto medio, simetría respecto al
último de tres puntos, simetría respecto a una línea (eje) y fijación estricta de
la selección. El origen (0,0) se puede seleccionar tocándolo en la vista y usar
como referencia fija.

Para una cota, selecciona dos puntos (también centros de círculos u origen) o una
línea/lado y elige **Distancia diagonal**, **Distancia horizontal** o **Distancia
vertical** en el rail de restricciones. Horizontal y vertical miden la separación
absoluta sobre los ejes del croquis y admiten cero; cada cota se conserva y edita
independientemente. El valor inicial es la medida actual.

**Simetría** usa tres puntos, en este orden: primer punto, segundo punto y centro.
Para dos círculos, puedes seleccionar sus centros y después el origen. Si eliges
otro centro y quieres que permanezca inmóvil, fíjalo antes. Es simetría respecto
a un punto; no se elige una línea como eje.

**Simetría respecto a línea** usa dos puntos y una línea/lado como eje, en ese
orden: primer punto, segundo punto y la línea. Sirve para horizontal, vertical o
cualquier diagonal según la orientación de esa línea — no hace falta elegir un
tipo distinto para cada caso. Si el eje no debe moverse al arrastrar, fíjalo
antes, igual que con la simetría por punto.

**Igualdad** admite dos o más círculos/arcos o líneas/lados del mismo croquis.
Selecciona primero la figura cuyo tamaño quieres conservar, luego las demás y
pulsa Igualdad. Más tarde, editar el tamaño de una actualiza el grupo. Si otras
cotas fijan tamaños incompatibles, se rechaza el cambio conservando la geometría.
En un círculo, **Radio/Diámetro** permite editar la misma medida con cualquiera de
las dos representaciones; no crea dos cotas independientes.
Al editar, **Boceto activo → Figuras** contiene solo las figuras de ese boceto.
Sus filas seleccionan figuras completas y ofrecen papelera;
**Cotas y reglas** es una pestaña separada. **Seleccionar todo**, **Deseleccionar
todo** y **Borrar selección** están junto a Deshacer/Rehacer; el borrado permanece en las acciones del
croquis y sus papeleras. Redondear se activa desde su rail. Estas acciones no se
duplican en la bandeja de propiedades. El origen queda fuera de Seleccionar
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

### Copiar un croquis a otro plano

En la pila, el menú del croquis ofrece **Copiar a otro plano paralelo**. La copia
conserva figuras y reglas en un plano que sigue al original, desplazado por su
normal (10 pasos al crearla). Con la copia seleccionada, **Separación Z** en la
bandeja la sube o baja (negativo = al otro lado). Es la base para unir dos croquis.

### Solevado entre dos croquis

Selecciona un perfil (o un croquis de un solo contorno), pulsa **Solevado** en el
rail 3D y toca el perfil del otro croquis (o elígelo en la pila). Se crea un sólido
de transición con paredes rectas entre ambos: círculo → cuadrado, rectángulo grande →
pequeño, etc. Los contornos no pueden tener huecos. Cambiar la Separación Z o las
medidas de cualquiera de los dos croquis actualiza el solevado.

### Barrido helicoidal (roscas y muelles)

Dibuja el perfil del filete (o la sección del muelle) apartado del eje: por defecto
el eje es la Y del croquis que pasa por su origen (o la X si el perfil cruza la Y).
Con el perfil seleccionado, pulsa **Barrido helicoidal** en el rail 3D. En la bandeja:
**Paso** (avance por vuelta; debe superar la altura del perfil), **Vueltas**,
**Derecha/Izquierda** y el **eje** (Y, X o una línea de construcción del croquis).
Para una rosca, extruye además el núcleo cilíndrico a lo largo del mismo eje (croquis
en el plano perpendicular) y el filete se une a él.

## Bandeja de cotas

El círculo muestra **Radio** mientras se dibuja y después de soltar. Editarlo modifica
la misma cota de radio, si existe. Tras dibujar un arco se activa el cursor: arrastra
el **rombo de su extremo** para cambiar el ángulo conservando centro, radio e inicio.
Cancelar restaura el arco; las restricciones siguen mandando. Los redondeos conservan
sus tangencias y no ofrecen ese tirador.

Junto a **Deshacer/Rehacer** hay un grupo con **Seleccionar todo**, **Deseleccionar
todo**, **Borrar selección**, **Construcción** y **Soldar puntos**. Cada candado de **Fijar medida/Quitar
cota** está junto a su campo (Ancho, Alto, Lado, Radio o Longitud) en la bandeja
inferior de la figura seleccionada. Los candados se deshabilitan mientras haya medidas
en borrador. Construcción afecta a la selección, o al dibujo siguiente si no hay
figuras seleccionadas.

Para cerrar un contorno, selecciona sus extremos y pulsa **Soldar puntos**. Se unen
en el último punto seleccionado (o en el origen si está incluido) con coincidencias
persistentes y un solo paso de deshacer. Un conflicto conserva el documento anterior.

La pila aprovecha la altura entre el selector de modos y la bandeja, a la izquierda
del rail de restricciones para dejarlo accesible. **Figuras/Restricciones** permanecen
visibles sobre la lista. En Restricciones puedes editar cotas y borrar cualquier regla;
**Solo selección** permite alternar el filtro cuando hay elementos seleccionados.
El icono **Crear croquis en la cara seleccionada** del rail usa directamente la
cara resaltada y se habilita cuando esa cara permite crear un boceto. Los planos
desplazados/inclinados siguen en **Planos y bocetos**.
El botón de vistas/atajos queda justo encima de la bandeja. La pila reserva su
altura real, también al desplegar el teclado, para que no se tapen.

Paso y dimensiones usan los campos compactos y botones −/+ de las otras bandejas.
Mantener un botón inicia la repetición a los 400 ms y acelera de 180 a 80 ms entre
pasos; soltar no añade otro incremento. La unidad elegida junto a Paso gobierna
las cotas métricas. Los campos angulares permanecen en grados.
Al arrastrar un punto o una arista, las dimensiones siguen visibles y muestran
el tamaño actual, también con snap de Incremento. Durante el gesto son de lectura;
al soltar puedes editarlas o fijarlas con el candado de cada medida.

Al editar un boceto o una operación confirmada, las medidas quedan en borrador:
**✓** las aplica juntas y **×** las descarta. Ambos botones permanecen fijos a la
derecha aunque desplaces los parámetros. En la preview de Extruir/Vaciar, −/+
actualiza la profundidad visible inmediatamente; ✓ confirma y × cancela la sesión.
Extruir puede ir en el sentido de la normal o en el contrario (Arriba/Abajo,
Izquierda/Derecha o Adelante/Atrás, según el plano). El lápiz sigue ese eje en
pantalla; al soltar se asienta el sólido.
Las respuestas antiguas de Blender no hacen perder pulsaciones acumuladas.

## Medida libre, cota y redondeo

Un cuadrado tiene **lados iguales**, pero su tamaño no queda fijado por dibujarlo.
Por eso muestra un único campo **Lado**. Un campo **sin cota** describe el tamaño
actual; **Fijar medida** la convierte en una cota que se conserva al arrastrar.
El campo pasa a indicar **cota**: editarlo cambia esa misma restricción. **Quitar
cota** retira esa medida fija conservando el dibujo y sus otras reglas. Fijar
geometría u otras restricciones todavía pueden limitar el cambio. Quitar Igualdad
convierte el cuadrado en un rectángulo con Ancho y Alto independientes.

**Restricciones → Editar** abre la medida existente; su papelera y **Quitar cota**
la retiran. El panel se actualiza al borrar o deshacer. Añadir la misma medida en
otro lado equivalente reutiliza la cota: no apila duplicados. El valor inicial
procede del tamaño real del dibujo, no del paso de la herramienta. Dos puntos
siguen permitiendo una distancia independiente cuando representan otra medida.

En **Figuras**, un arco de redondeo aparece como **Redondeo**. Selecciónalo para
editar su Radio; no se ofrecen ángulos que contradigan sus tangencias. Su papelera
(**Quitar redondeo**) restituye la esquina y conserva el perfil y las
extrusiones que lo utilizan. Los lados recortados muestran **Lado completo**:
la longitud y sus igualdades se miden hasta las esquinas virtuales. Así, variar
el radio no obliga a cambiar la cota de un cuadrado para compensar el recorte.
Un radio que no cabe o un cambio incompatible con otras reglas se rechaza sin
alterar el documento. Estas transacciones conservan un único undo.

## Elegir caras, medir y usar referencias

En 3D, **Puntos**, **Aristas** y **Caras** son iconos junto al selector CAD/Object,
como en Edit, y permiten seleccionar directamente el sólido. En una pieza CAD
eligen la figura de diseño, no los trozos de la malla: la arista de un círculo
es el contorno entero y sus muestras no son puntos. **Cursor**, en el
rail, vuelve a seleccionar perfiles o geometría del boceto. La primera referencia
se resalta en azul y la segunda en naranja dentro
del vídeo. Tocar una seleccionada la retira; **Limpiar** deja la vista sin
referencias. Las caras coplanares forman una sola selección, sin confundir su
cuadrícula interna con aristas reales. Se muestran longitud, área/perímetro y,
con dos elementos compatibles, distancia o ángulo. Las caras paralelas muestran
separación entre planos; una arista/punto y una cara, distancia al plano.

Los modificadores siguen mostrando toda su geometría, pero la selección conserva
las caras y aristas de origen. Un cubo con Subdivisión ofrece seis caras y doce
aristas completas: tocar dos subdivisiones de la misma cara alterna esa misma
selección. En cuerpos CAD con Bisel/Subdivisión, el resaltado sigue la forma
modificada y las medidas y planos conservan la referencia de diseño anterior al
acabado. Puedes crear otro croquis sobre esa cara y seleccionar sus vértices
originales aunque el bisel haya redondeado las esquinas visibles.

Para conservar paredes rectas y cotas de una caja vaciada, ajusta el redondeo con
Ancho y Segmentos de Bisel. Subdivisión Catmull-Clark modifica también la forma
de las paredes y del hueco; puede cerrar sus esquinas, incluso detrás de un bisel.

Estos selectores se ocultan al editar el croquis: su cursor ya selecciona puntos
y aristas directamente. Solo reaparecen si abres **Medir desde sólido** para
elegir referencias 3D explícitamente.

Para dibujar en una cara: **Caras → tocar la cara → icono Crear croquis en la cara seleccionada**, en el rail.
El botón usa exactamente la selección visible, crea plano+boceto en un solo undo
y orienta la vista al plano. Una cara superior CAD sigue a su operación soporte;
una cara arbitraria conserva el marco capturado. Si el sólido cambia antes de
confirmar, la selección se invalida y hay que volver a elegirla.

Durante un boceto, el rail tiene **Proyectar**. Toca cualquier arista del sólido,
aunque esté en otra altura: se copia al plano del croquis como construcción fija.
Un contorno circular llega como círculo. También sigue en **Planos y bocetos →
Medir desde sólido**. No aparece permanentemente en la bandeja de
propiedades. **Proyectar al plano** vuelve al cursor y usa esos puntos/aristas para acotar.
La referencia no entra en la extrusión ni cambia las piezas originales. Es una
copia fija, no un enlace topológico dinámico a cualquier arista del sólido.

## Vista 3D y árbol contextual

**Finalizar boceto** recupera la vista 3D anterior y encuadra el resultado. Si esa
vista era frontal, se ofrece una vista oblicua. Un dedo orbita en 3D; durante una
preview de profundidad, el manejador de órbita y dos dedos permiten navegar.
El botón **Vista 3D** vuelve a encuadrar. Nada de esto modifica la cámara del PC.
Un croquis nuevo con varios perfiles queda seleccionado completo al finalizar;
si solo tiene uno, se selecciona ese perfil. **Seleccionar todo/Deseleccionar todo**
permanecen junto a Deshacer/Rehacer: en edición actúan sobre las figuras; en 3D,
sobre el croquis elegido. La pila contiene solo croquis y operaciones: las figuras
pertenecen al croquis. Su menú ⋮ permite **Renombrar croquis**, **Editar boceto** y
**Seleccionar croquis completo**. Renombrar conserva sus referencias y no reconstruye mallas.

Mientras editas, el panel muestra únicamente el boceto activo: **Figuras** y
**Cotas y reglas**. Al salir, muestra la secuencia de croquis y operaciones del
cuerpo y desplaza la lista al final cuando
se añade un nodo. Los cuerpos se eligen mediante el desplegable del panel.
Los bocetos usados por una operación se ocultan automáticamente. El ojo permite
mostrarlos explícitamente y conserva esa elección al guardar.

Referencia de organización: [lista de operaciones plegable de Onshape](https://www.onshape.com/en/resource-center/tech-tips/feature-list-organization).

## Extruir y vaciar con el lápiz

1. Crear un boceto XY/XZ/YZ y dibujar un perfil cerrado. También se reconocen
   cadenas cerradas no ramificadas de líneas y arcos unidos en sus extremos.
2. Finalizar el boceto y pulsar **Extruir**. **Croquis completo** extruye todos sus
   contornos exteriores y conserva los interiores como huecos: un rectángulo con
   cuatro círculos produce una placa con cuatro taladros. Varios contornos exteriores
   separados forman una sola operación con la misma profundidad. También puedes
   elegir un perfil individual tocándolo en la vista. Las líneas abiertas deben cerrarse o
   marcarse como construcción; no se extruyen silenciosamente como si fueran sólidos.
3. Deslizar arriba/abajo para cambiar profundidad: cada 4 % de altura recorre un
   paso. Con Incremento avanza en saltos; sin snap conserva las fracciones.
   La bandeja permite editar el paso, la profundidad exacta y los botones −/+.
4. Confirmar crea un undo; cancelar restaura el resultado anterior.
5. Para vaciar desde arriba, seleccionar **Caras**, tocar la cara superior y pulsar
   **Boceto en cara**. Su plano sigue la altura de la
   operación de soporte. Dibujar el hueco y finalizar el boceto.
6. Seleccionar ese perfil, elegir el sólido **Destino** y pulsar **Vaciar**.
   La profundidad entra en dirección contraria a la normal del boceto. El lápiz,
   paso y botones funcionan como en Extruir. Puede atravesar toda la pieza.
7. Durante el vaciado la captura GPU de la tablet activa transparencia al 35 %;
   restaura los ajustes de sombreado tras cada captura, incluso si falla el render.
   Confirmar/cancelar termina la transparencia automáticamente.

Un vaciado es una diferencia booleana exacta de Blender sobre mallas evaluadas.
Cada cuerpo publica un único objeto. Sus extrusiones se unen al resultado anterior
y los vaciados restan de ese resultado; **Nuevo cuerpo** inicia otra pieza independiente.
La pila conserva los pasos paramétricos y permite ver el cuerpo en cada momento.
La evaluación y el resaltado reutilizan resultados y geometría GPU mientras no cambien;
dibujar en otro croquis no obliga a reconstruir las operaciones anteriores.
Durante la preview, cambiar profundidad reutiliza los contornos y huecos ya
teselados. Android mantiene una petición CAD en vuelo y conserva la última muestra
absoluta pendiente de profundidad, ancho o lápiz; confirmar espera a ese valor.
Los booleanos y el solver de arrastre se calculan en un proceso Blender auxiliar
aislado; el vídeo y la navegación continúan. Cancelar, guardar o desconectar descartan
el cálculo pendiente y restauran el baseline. La primera evaluación arranca ese
proceso y puede tardar más que las siguientes. Una profundidad rechazada
muestra el error e impide que una confirmación pendiente acepte el sólido anterior.
El vaciado consume visualmente su operación destino conservando su dependencia en el árbol.
Cambiar el perfil, la profundidad o la altura del soporte reconstruye el resultado.
Un perfil que no intersecta el destino o elimina todo el sólido se rechaza.
No se pueden borrar soportes con operaciones o bocetos dependientes:
primero se eliminan los dependientes. El árbol permite borrar bocetos sin operaciones.

## Redondear y achaflanar aristas del sólido

1. Fuera del boceto, elige **Aristas** (icono junto al selector CAD/Object).
2. Toca las aristas: la selección se acumula (toca otra vez para quitar una).
3. Pulsa **Redondear aristas** o **Chaflán en aristas** en la bandeja.
4. Desliza arriba/abajo o escribe el **Ancho**; el redondeo admite 1–16 **Segmentos**.
5. ✓ añade la operación a la pila del cuerpo con un undo; × la descarta.

Es una operación más de la pila: se puede ocultar, borrar o editar su ancho y
segmentos tocando su nodo. Las aristas se guardan por su geometría, no por índices
de malla: si alargas una extrusión, sus aristas rectas conservan el redondeo. Si
una arista desaparece del diseño, la pila lo indica con un error en vez de ignorarla.
Usa el bisel nativo de Blender sobre el sólido; no es un fillet B-rep.

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
  del sólido. Vaciar quita un perfil por profundidad, a un lado del croquis o a los dos; no es una operación Shell
  de espesor automático sobre caras arbitrarias.
- **Planos y bocetos** empieza por Superior/Frontal/Lateral o una cara y una medida
  de **Separación**. **Crear croquis** crea su plano y lo abre en un solo paso.
  **Inclinación y ajustes avanzados** despliega XYZ y el plano de otro croquis.
  **Planos existentes → Colocar** ajusta la separación de un plano guardado.
  Permite usar XY/XZ/YZ, el plano de otro boceto, una cara superior
  asociativa o un plano guardado. Un plano nuevo admite desplazamiento XYZ en la
  unidad elegida y rotación XYZ en grados, relativos al plano de referencia.
  **Boceto en cara** consume la cara resaltada; **Ver objetos
  de la escena** permite elegir referencias externas. Esa referencia conserva su
  posición capturada, sin seguir cambios topológicos de una cara arbitraria.
- **Nuevo cuerpo** crea una pieza independiente. El árbol agrupa sus bocetos y
  operaciones; **Nuevo boceto** está disponible también cuando ya hay otros.
  El ojo de cada boceto oculta/muestra su overlay sin desactivar las operaciones.
- **Construcción** dibuja geometría auxiliar discontinua. También puede convertir
  las figuras seleccionadas; sus restricciones siguen activas y sus contornos
  nunca extruyen ni abren huecos. Si rompería un perfil usado, se rechaza el cambio.
- **Pila → menú del cuerpo → Copia editable · Edición / Escultura** sale a Object
  con una copia de la pieza completa seleccionada. Su malla es independiente y
  conserva los modificadores; puedes entrar en Edit o Sculpt directamente.
  **Duplicar** en Object sobre una pieza CAD produce esa misma copia independiente.
  El original queda oculto para evitar superficies superpuestas y vuelve a verse
  al entrar en CAD, con todo su árbol paramétrico intacto.
- En la copia, **Edit → Caras → seleccionar una cara → Bisel** bisela su contorno;
  **Edit → Aristas → seleccionar una arista → Bisel** actúa sobre esa arista.
  Para biselar el objeto completo, usa el modificador Bisel y sus campos Ancho y
  Segmentos. Son operaciones nativas sobre la copia; no añaden un fillet de sólido
  al historial paramétrico CAD.
- Durante CAD se muestra la malla compacta del kernel y se reutiliza su topología
  al variar profundidad. La retícula densa se genera solo al crear una copia editable.
  Esa copia se ordena por caras de diseño: cada cara plana sin hueco es
  una rejilla de quads (un círculo queda como rejilla, sin polo central) y una cara
  con un agujero forma un marco de cuatro rejillas que crecen desde el agujero hacia
  el borde. Las caras vecinas comparten sus divisiones: los loops recorren la pieza
  sin T-junctions ni triángulos, listos para Edit, Bisel o Subdivisión.
- Todavía sin rejilla ordenada: caras con varios agujeros y contornos cóncavos
  (forma de L). Esas caras usan quads con puntos medios compartidos, conservando
  frontera, volumen y conectividad. La evaluación booleana conserva operandos
  compactos; la copia editable no se realimenta a cortes posteriores.
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

`test_cad_dimensions.py` cubre radio editable y eliminación del redondeo con sólido
dependiente, medidas libres/fijas, cotas equivalentes, duplicados antiguos,
valores iniciales reales y conservación del tamaño al redondear un cuadrado.

`test_cad_surface.py` verifica selección visible real, medición en metros, proyección,
invalidez de referencias antiguas, vuelta a 3D sin tocar el PC y orden del árbol.
La prueba GPU comprueba el resaltado completo y su exclusión de las capturas limpias.
