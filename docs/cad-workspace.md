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
Al salir se retiran las cotas de las figuras y las propiedades de dibujo. Si el
boceto ya tiene operaciones, la bandeja no abre automáticamente la última: para
editarla, selecciónala en la pila. Un boceto nuevo conserva su perfil o conjunto
de perfiles seleccionado para poder extruirlo.

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
  fijo el otro y el punto sobre un lado recto ensancha o estrecha la ranura (con la
  ranura sin seleccionar entera; seleccionada, el arrastre la mueve completa). Sirve para agujeros alargados y ajustes regulables.
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
paralela, colineal, perpendicular, tangencia entre línea y círculo/arco, igualdad de
longitudes o radios, distancia diagonal/horizontal/vertical, radio, punto medio, simetría respecto al
último de tres puntos, simetría respecto a una línea (eje) y fijación estricta de
la selección. El origen (0,0) se puede seleccionar tocándolo en la vista y usar
como referencia fija.

Toca directamente una **cota** del dibujo con el cursor para editarla: la bandeja
muestra su valor y una papelera para quitarla. Se selecciona una cada vez; los
puntos y las aristas conservan su selección múltiple. Las reglas sin valor
(Horizontal, Tangente, Igualdad…) no se seleccionan en el dibujo: aparecen como
marcas pequeñas junto a la geometría seleccionada y se quitan desde su lista.

Las distancias llevan líneas auxiliares finas y flechas entre los extremos medidos;
los radios señalan desde el centro al contorno del círculo o arco. El valor va en
una píldora compacta. **Arrastra la cota para recolocarla**, sin cambiar su valor
ni mover la geometría. La colocación se guarda en el boceto y se mantiene al girar
o acercar la vista. Soltar confirma un único paso de deshacer; cancelar el gesto
restaura su posición.

**Horizontal/Vertical** se aplica a todas las líneas o lados rectos seleccionados,
también cuatro o más, con una sola pulsación. Cada arista conserva su propia regla;
se confirman juntas con un único deshacer. Si alguna contradice una cota o fijación,
se rechaza el conjunto sin cambios parciales. No alinea curvas ni puntos sueltos.

**Punto sobre recta** mantiene un punto sobre una línea y permite deslizarlo a
lo largo de ella. Selecciona un punto (extremo, esquina, centro u origen) y una
línea o lado recto de otra figura, en cualquier orden, y pulsa Punto sobre recta
en el grupo de posición del rail. También admite el eje de una ranura.
El punto puede sobrepasar los extremos del segmento: la relación usa su recta
completa. Para mantener la guía inmóvil, fíjala o acótala antes. La relación se
conserva al arrastrar y guardar; un conflicto con otras cotas rechaza el cambio.

Para una cota, selecciona dos puntos (también centros de círculos u origen) o una
línea/lado y elige **Distancia diagonal**, **Distancia horizontal** o **Distancia
vertical** en el rail de restricciones. Horizontal y vertical miden la separación
absoluta sobre los ejes del croquis y admiten cero; cada cota se conserva y edita
independientemente. El valor inicial es la medida actual.

**Colineal (misma recta)** usa dos líneas o lados rectos del mismo boceto.
Mantiene ambos sobre la misma recta, aunque tengan distinta longitud o no se
solapen. Puedes acotar cada longitud y deslizar sus extremos sobre esa recta.
Si la línea madre debe permanecer inmóvil, fíjala antes; las referencias
proyectadas ya están fijas. No obliga a que coincidan los extremos.

**Simetría** usa tres puntos, en este orden: primer punto, segundo punto y centro.
Para dos círculos, puedes seleccionar sus centros y después el origen. Si eliges
otro centro y quieres que permanezca inmóvil, fíjalo antes. Es simetría respecto
a un punto; no se elige una línea como eje.

**Simetría respecto a línea** usa dos puntos y una línea/lado como eje, en ese
orden: primer punto, segundo punto y la línea. Sirve para horizontal, vertical o
cualquier diagonal según la orientación de esa línea — no hace falta elegir un
tipo distinto para cada caso. Si el eje no debe moverse al arrastrar, fíjalo
antes, igual que con la simetría por punto.

**Ranura: Radio/Ancho.** El selector muestra el radio de los extremos o el ancho
total de la misma ranura. Para R15 escribe Radio = 15 mm (equivale a Ancho = 30 mm).
Entre centros sigue siendo la distancia recta entre los dos centros, no la longitud
total exterior; la longitud total es Entre centros + Ancho.

**Desfase por grosor.** En Figuras, abre ⋮ de una ranura, círculo o rectángulo y
elige Desfase por grosor. En la bandeja selecciona Hacia dentro/Hacia fuera, escribe
Grosor y confirma. La nueva figura queda vinculada a la fuente. En una ranura
comparte los centros de los extremos y el ángulo; cambia su ancho en dos veces
el grosor. Una ranura interior de 15 mm y grosor exterior de 7,5 mm crea otra de
30 mm. Para extruir el anillo elige el perfil exterior o el croquis completo;
el interior queda como hueco. Seleccionar el derivado permite editar solo Grosor.
Quitar su regla de desfase desvincula la figura y conserva su forma. No admite
todavía polígonos irregulares ni cadenas generales de líneas y arcos.

**Simetría de operación.** En la pila, abre ⋮ de una Extrusión o Vaciado y elige
Simetría de operación. La bandeja permite escoger XY/XZ/YZ y la posición del plano
en la unidad activa. Al confirmar aparece un nodo vinculado: cambiar el perfil o
la profundidad de la fuente actualiza también su simétrico. El plano se refiere
a los ejes del documento CAD; posición cero pasa por su origen.
Para repetir un saliente perforado, refleja la extrusión y su vaciado: cada uno
repite su propio volumen añadido/restado, sin copiar la base completa. La simetría
se puede desactivar o borrar sin quitar la fuente. El botón Operación fuente
permite editar sus parámetros; profundidad/dirección se heredan y no se duplican.

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
Los arcos dibujados con la herramienta Arco muestran **Ángulo** en grados con su
propio candado: cerrado, el barrido ya no cambia al arrastrar el rombo ni por otras
reglas. Confirmar un Ángulo escrito lo fija; aparece en Cotas y reglas como «Ángulo
del arco». Los redondeos no muestran Ángulo: el suyo lo deciden sus dos lados.
Para fijar el ángulo entre dos líneas o lados (por ejemplo un brazo a 45° o una
cara con 10° de inclinación), selecciona ambos y pulsa **Ángulo** en el grupo de
cotas. Se mide el ángulo que se ve entre los dos tramos; en una esquina, el
interior. Escribe el valor en grados y se dibuja como un arco con flechas.
Para varios arcos iguales, selecciónalos y pulsa **Igualdad**: toman el radio y el
ángulo del primero, sin fijarlos. Con varios arcos seleccionados, escribir Radio o
Ángulo en la bandeja y confirmar lo aplica a todos: añade las igualdades que falten
y una sola cota, en un único paso de undo. Si hay redondeos entre ellos, solo se
iguala el radio.

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
derecha aunque desplaces los parámetros. En las figuras del boceto, ✓ también
fija las medidas editadas que tienen candado: crea o actualiza sus cotas y deja
los candados marcados. Las medidas no editadas siguen libres. Se guarda todo en
un único deshacer; si alguna cota entra en conflicto, no se aplica ninguna.
En la preview de Extruir/Vaciar, −/+
actualiza la profundidad visible inmediatamente; ✓ confirma y × cancela la sesión.
Extruir puede ir en el sentido de la normal o en el contrario (Arriba/Abajo,
Izquierda/Derecha o Adelante/Atrás, según el plano). El lápiz sigue ese eje en
pantalla; al soltar se asienta el sólido.
Las respuestas antiguas de Blender no hacen perder pulsaciones acumuladas.

## Medida libre, cota y redondeo

Un cuadrado tiene **lados iguales**, pero su tamaño no queda fijado por dibujarlo.
Por eso muestra un único campo **Lado**. Un campo **sin cota** describe el tamaño
actual; editarlo y confirmar con **✓**, o pulsar **Fijar medida**, lo convierte
en una cota que se conserva al arrastrar.
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

Durante un boceto, el rail tiene **Proyectar**. Toca puntos, aristas o caras para
acumular referencias, incluso de distintos objetos o alturas. Puedes cambiar entre
Puntos/Aristas/Caras sin perder el grupo; repetir un toque quita esa referencia y
tocar el fondo conserva la selección. La bandeja muestra el total y **Limpiar** lo
vacía. **Proyectar al plano (N)** copia toda la selección como construcción fija
en una sola operación de deshacer.
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
3. Deslizar a lo largo de la dirección de extrusión: la profundidad sigue a la
   punta del lápiz 1:1 (1 mm de recorrido en la pieza = 1 mm). Con Incremento avanza
   en saltos de un paso; sin snap conserva las fracciones. Si la dirección apunta a la
   cámara, se usa la escala antigua (un paso por cada 4 % de altura).
   La bandeja permite editar el paso, la profundidad exacta y los botones −/+.
4. Confirmar crea un undo; cancelar restaura el resultado anterior.
5. Para vaciar desde arriba, seleccionar **Caras**, tocar la cara superior y pulsar
   **Boceto en cara**. Su plano sigue la altura de la
   operación de soporte. Dibujar el hueco y finalizar el boceto.
6. Seleccionar ese perfil, elegir el sólido **Destino** y pulsar **Vaciar**.
   La profundidad entra en dirección contraria a la normal del boceto. El lápiz,
   paso y botones funcionan como en Extruir. Puede atravesar toda la pieza.
7. Durante el vaciado solo el material retirado se ve translúcido, en rojo y con
   sus aristas, a través de la pieza. El sólido y el resto de la escena conservan
   su sombreado opaco. Confirmar/cancelar retira el fantasma automáticamente.

Un vaciado es una diferencia booleana de Blender con el solver nativo Manifold
sobre sólidos cerrados (Blender 4.5 o posterior). Los vaciados desde caras opuestas
y sus simetrías usan el mismo cálculo y conservan las cotas del documento.
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
- **Nuevo plano y croquis** (icono de capas arriba, o los iconos de plano del rail)
  entra en modo plano, sin diálogo. El plano aparece en la vista como una lámina
  azul translúcida con sus ejes (X rojo, Y verde, normal azul) y se ajusta en vivo:
  - el rail elige la base: Superior (XY), Frontal (XZ), Lateral (YZ) o la cara que
    tengas seleccionada;
  - **arrastrar con el lápiz** lo separa por su normal, siguiendo la punta 1:1; con
    Incremento, en pasos del paso CAD;
  - la bandeja tiene **Separación**, **Inclinar** sobre sus dos ejes y **Mover**
    dentro del plano, con −/+; la línea de ayuda dice hacia dónde es positivo;
  - **Planos guardados** permite abrir un croquis en uno existente o recolocarlo;
  - ✓ crea plano y croquis en un solo paso de deshacer; ✗ lo descarta sin cambios.
  Dentro de un croquis, el mismo sitio arriba es **Medir desde el sólido**.
  **Boceto en cara** consume la cara resaltada; **Ver objetos
  de la escena** permite elegir referencias externas. Esa referencia conserva su
  posición capturada, sin seguir cambios topológicos de una cara arbitraria.
- **Revolución** (rail 3D, con un perfil seleccionado) gira el contorno alrededor de
  un eje del croquis y lo suma a la pieza. Para un cono, dibuja un triángulo con un
  lado sobre una línea de construcción: esa línea es el eje por defecto. La bandeja
  cambia el **Ángulo** (hasta 360°) y el eje (Y, X o las líneas de construcción).
  El perfil puede tocar el eje, pero no cruzarlo.
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
  al variar profundidad. La copia editable conserva esa superficie y limpia
  coincidencias numéricas, elementos degenerados y divisiones casi coplanares.
  Mantiene los contornos curvos, huecos, materiales y costuras; no fuerza una
  retícula de cuadriláteros. Las caras planas pueden ser n-gons y las que tienen
  huecos conservan los conectores necesarios. La copia se valida como sólido
  cerrado con volumen conservado antes de entregarse; un fallo deja el original intacto.
  Los biseles siguen limitados por los detalles estrechos y el solapamiento;
  Subdivisión puede requerir topología específica. La copia no se realimenta
  a cortes posteriores ni modifica el documento CAD.
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
