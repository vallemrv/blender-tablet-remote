# 005 · Backend · El Knife corta en n-gons, no en abanico

## Objetivo

Que el corte se parezca al trazo. Hoy un punto puesto en el interior de una cara borra
la cara y la reemplaza por un abanico de triángulos hacia todas sus esquinas
(`_poke`), así que la malla acaba llena de diagonales que nadie dibujó. El Knife de
Blender parte la cara atravesada en dos n-gons siguiendo el trazo, y eso es lo que hay
que reproducir.

## Evidencia

Dos capturas del usuario: el trazo pedido (polilínea limpia sobre la cara frontal de un
cubo) y el resultado (diagonales desde cada punto interior a las cuatro esquinas). El
abanico de `_poke` explica exactamente esas diagonales.

## Fases y cierre

- [x] Caso de referencia en la suite headless que reproduzca el trazo de la foto y falle
  con el motor actual: ninguna cara nueva debe ser un triángulo que nadie pidió.
- [x] Un ancla interior deja de triangular la cara: se integra al partirla en n-gons.
- [x] La cara atravesada se reconstruye en dos n-gons siguiendo la cadena de puntos.
- [x] Conservar lo que ya funciona: anclas sobre vértice y sobre arista, cortes de borde
  a borde, cierre de polilínea y los errores existentes.
- [x] Ejecutar headless y GUI.
- [ ] Contrato: bloqueado por deuda ajena, ver abajo.

Resultado: headless **815/815** (el caso de referencia falla con el motor viejo: daba
6 triángulos y un vértice interior con 5 aristas; ahora da 2 n-gons y 2 aristas). GUI
**108/109**. Comprobado en vivo: el trazo de la foto sobre el cubo pasa de 6 a 7 caras,
es decir la cara frontal se parte en dos, en vez de estallar en un abanico.

## Qué funcionó y qué no

Funcionó:

- **Partir la cara en dos n-gons con la cadena del trazo.** Es el arreglo. El caso de
  referencia pasó de 6 triángulos y un vértice interior con 5 aristas, a 2 n-gons y ese
  vértice con las 2 aristas del trazo. En vivo, el trazo de las capturas lleva el cubo de
  6 a 7 caras: la cara frontal se parte en dos y ya está.
- **Escribir antes la prueba y verla fallar.** Sin eso no habría forma de saber que el
  arreglo ataca lo que se ve en la foto.

No funcionó:

- **`bpy.ops.mesh.knife_project`** (delegar en el Knife nativo). Cuatro intentos. El
  operador responde `No other selected objects have wire or boundary edges` aunque el
  cutter esté seleccionado, visible y con sus aristas. Medido: el cutter evaluado tiene
  4 aristas en Object Mode y **0** en Edit Mode, así que el operador no lo ve. Además
  exigiría forzar la vista de la ventana del usuario a la cámara de la tablet y no sería
  testeable en headless. Descartado de acuerdo con el usuario.
- **Sincronizar el fixture de `capabilities`** para arreglar el contrato. Se intentó dos
  veces (una con el servidor ya usado, otra recién arrancado) y `capabilities coincide
  con fixture` siguió rojo. Se revirtió el fixture al estado del repo para no dejar un
  artefacto a medio validar. La causa está identificada pero el arreglo no.
- **Reproducir el segfault de la captura** (serie `003` backend): dos hipótesis
  descartadas con evidencia, sin reproducción.

## Limitación conocida

`_split_face_with_chain` solo entra cuando entrada y salida están en el contorno de la
**misma** cara, que es el caso corriente. Un trazo que encadena puntos interiores de
caras distintas cae al camino antiguo (`_poke`), que sigue triangulando. Para cubrirlo
haría falta caminar el trazo acumulando por cara los cruces con las aristas, y partir
cada cara una sola vez con su subcadena. No se ha hecho: es otro rediseño y el caso de
las capturas ya queda resuelto.

## Efectos colaterales encontrados

- El caso GUI "Ctrl+toque selecciona el camino hasta el destino" estaba acoplado a la
  topología que dejaba el abanico y al vértice activo. Se hizo determinista: se fija el
  activo y se busca por anchura un vértice a distancia exacta 2.
- **El contrato está midiendo contra el addon instalado, no contra el repo.** Al
  reinstalar el addon con el código actual, `capabilities` dejó de coincidir con el
  fixture: el código del working tree anuncia `LOOPTOOLS_CIRCLE`, `snap_mode`, otros
  umbrales de Knife y `edit_tools.version = 9`, mientras el fixture commiteado se quedó
  en la 7. Es deuda del trabajo previo no commiteado, no de esta serie. Se intentó
  sincronizar el fixture desde el servidor y el contrato siguió sin cuadrar, así que se
  dejó el fixture **como estaba en el repo** en vez de dejar un artefacto a medio
  validar. Merece su propia serie.
