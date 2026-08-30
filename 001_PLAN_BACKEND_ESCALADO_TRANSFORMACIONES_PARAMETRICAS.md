# 001 — Backend: escalar transformaciones paramétricas a Object y Edit

## Objetivo

Convertir la base validada de Mover en un sistema común de MOVE, ROTATE y SCALE para
Object Mode y Edit Mode, con entrada exacta, incremento, orientación, referencias
geométricas y preview reversible. Blender ejecuta la transformación; el protocolo
expresa intención paramétrica sin depender de operadores modales ni del pivote visible
del PC.

## Invariantes heredados de `000`

- Cada preview se reconstruye desde matrices o BMesh originales; nunca se acumula
  sobre el preview anterior.
- Un punto sondeado pertenece al espacio visible actual. Si debe persistir, se convierte
  al baseline de la sesión y al publicarlo se aplica el preview exactamente una vez.
- `ACTION_UP` bloquea el último candidato mostrado; no repite el raycast.
- Fuente, centro y destino son roles distintos. No reutilizar un único vector con tres
  significados implícitos.
- El destino excluye la geometría móvil: objetos completos en Object, elementos
  transformados en Edit. La geometría inmóvil de la misma malla sí puede ser destino.
- Confirmar produce un único undo y cancelar restaura exactamente el baseline.

## Modelo paramétrico común

La sesión publicará explícitamente:

- `center`: centro alrededor del cual operan ROTATE/SCALE; por defecto el centro de la
  selección y, con REL, una referencia geométrica independiente del pivote de Blender.
- `source`: punto ligado a la selección que sirve de asa geométrica.
- `target`: destino exacto visible para el solver de snap.
- `values`: vector canónico del modo: distancia XYZ, ángulo XYZ o factores XYZ.
- `step` y `step_unit`, `axes`, `orientation`, estado bloqueado y proyecciones de cada
  marcador.

MOVE conserva el contrato validado: `source → target` determina la traslación. ROTATE
usa `center` y calcula el ángulo que alinea `source-center` con `target-center` en el
eje/plano restringido. SCALE usa el cociente entre ambas distancias o componentes
orientadas respecto de `center`; se rechazan denominadores degenerados en vez de
producir factores infinitos. Sin target, los tres modos admiten valores e incremento.

## Fases

### A. Contrato y núcleo compartido

- Separar estado base, estado visible y conversión entre espacios en helpers probados.
- Tipar centro/fuente/destino y conservar compatibilidad con los campos REL de Move v2.
- Versionar `parametric_transforms` y actualizar protocolo, capabilities y fixtures.
- Definir errores controlados: referencia degenerada, restricción insuficiente,
  candidato eliminado y cambio de selección durante la sesión.

### B. Object Mode

- Generalizar valores exactos e incremento de MOVE a ROTATE y SCALE.
- ROTATE: ángulos XYZ canónicos en radianes; incremento angular; orientación
  GLOBAL/LOCAL/VIEW; centro REL y solver geométrico restringido.
- SCALE: factores XYZ canónicos, uniforme o por ejes; incremento porcentual; centro REL
  y solver geométrico. Impedir cruces por cero accidentales y permitir valores
  negativos solo mediante entrada explícita.
- Mantener matrices originales por objeto, jerarquías y transformaciones locales sin
  introducir dependencia de selección activa mutable.

### C. Edit Mode

- Aplicar los mismos comandos y estado a vértices seleccionados sobre BMesh original.
- Calcular centro/fuente en la jaula original y sondear la geometría visible evaluada
  con correspondencia estable a la jaula cuando sea posible.
- Excluir del target los vértices/aristas/caras móviles, no el objeto completo.
- Conservar edición proporcional, vértices ocultos, Auto Merge solo en MOVE y Mirror
  Clipping en MOVE/SCALE según sus invariantes ya validados.
- Invalidar limpiamente la sesión si cambia topología, submodo o selección efectiva.

### D. Snap y continuidad de sesión

- Reutilizar VERTEX/EDGE_CENTER/FACE_CENTER y sus umbrales de intención explícita.
- Probar secuencias de dos o más cambios de valor, REL tardío, cambio de orientación,
  cambio de restricción y nuevo target sin confirmar.
- Reproyectar todos los marcadores tras transformar o mover cámara.
- Asegurar que confirmar, cancelar, undo, redo, borrar y cambio de tool no dejan RNA o
  BMesh obsoletos en el broadcast.

### E. Eficiencia

- Cachear matrices, inversas y bases por sesión; el sondeo puede ejecutarse a frecuencia
  de stylus, pero solo el último candidato pendiente necesita procesarse.
- Medir Object y Edit con mallas grandes. `status()` no recorrerá toda la malla ni
  recalculará geometría evaluada para limitarse a reproyectar marcadores.

## Pruebas obligatorias

- Matriz MOVE/ROTATE/SCALE × Object/Edit × GLOBAL/LOCAL/VIEW × libre/eje/plano.
- Valores exactos, incremento, centro REL, source→target, varias operaciones sin
  confirmar, confirm/cancel y undo/redo.
- Object múltiple, objeto rotado/escalado, parentado y escala no uniforme.
- Edit por submodo, proporcional on/off, Mirror Clipping y targets inmóviles de la
  misma malla y de otros objetos.
- Regresiones explícitas: candidato verde congelado, ausencia de doble aplicación del
  preview, exclusión del móvil y ausencia de referencias RNA/BMesh obsoletas.
- Backend headless, GUI aplicable, contrato Android y prueba viva contra el ZIP instalado.

## Criterios de cierre

- Los seis casos principales —tres modos en Object y Edit— comparten contrato y
  semántica, no implementaciones paralelas incompatibles.
- Los valores mostrados describen exactamente el preview actual y siguen siendo
  correctos tras cualquier número de ajustes dentro de la misma sesión.
- REL y snap geométrico nunca saltan al fijarse ni aplican dos veces una transformación.
- Cancelar es exacto, confirmar crea un undo y el servidor continúa operativo tras
  invalidaciones.
- Todas las pruebas obligatorias están verdes y el usuario valida el comportamiento
  con lápiz en tablet antes de retirar el plan.
