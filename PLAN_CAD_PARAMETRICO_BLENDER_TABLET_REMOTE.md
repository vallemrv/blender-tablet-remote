# PLAN — Workspace CAD paramétrico para Blender Tablet Remote

## 0. Contexto y objetivo

Este plan parte del estado actual descrito en `AGENTS.md`.

El producto existente **no es un escritorio remoto**: la tablet Android es una interfaz táctil especializada y Blender sigue siendo el motor 3D que vive en el PC. La arquitectura actual ya dispone de:

- Android en Kotlin + Jetpack Compose.
- Viewport remoto dominante.
- Entrada única por `InputSurface.kt`.
- Cámara orbital propia en backend.
- WebSocket JSON para control.
- Streaming H.264/MJPEG separado del canal de control.
- Object Mode y Edit Mode funcionales.
- Picking táctil.
- Dedo, stylus, eraser, presión e inclinación.
- Navegación táctil/orbital ya resuelta.
- Sesiones modales reversibles.
- Tools paramétricas con preview reconstruida desde backup.
- Bandejas horizontales de parámetros.
- Protocolo v2, capabilities, fixtures y tests contractuales.

El nuevo objetivo es añadir un **tercer workspace llamado CAD** dentro de la misma aplicación Android.

No se creará una segunda aplicación.

No se intentará clonar Fusion 360 completo desde el principio.

El primer hito debe conseguir este flujo:

> Crear un sketch con lápiz → cerrar un perfil → añadir cotas → extruir → cambiar una cota → reconstruir automáticamente la pieza.

Ese flujo será la base de un sistema CAD paramétrico orientado a piezas de precisión, impresión 3D, electrónica, carcasas, soportes, adaptadores y piezas mecánicas sencillas.

---

# 1. Principios obligatorios

## 1.1 Mantener la arquitectura existente

No duplicar:

- viewport;
- streaming;
- conexión;
- cámara;
- entrada táctil;
- reconexión;
- gestión de archivos;
- estado remoto;
- patrones de bandejas;
- acciones/context menus.

El workspace CAD reutiliza la infraestructura ya existente.

## 1.2 Mantener una única app Android

La aplicación seguirá siendo:

```text
android-client/
```

No crear:

```text
android-cad/
cad-client/
fusion-client/
```

ni ningún segundo APK.

## 1.3 No convertir el Edit Mode actual en CAD

El sistema CAD será un subsistema nuevo y separado.

Debe convivir con:

- Object Mode
- Edit Mode
- CAD Mode

pero no reutilizar incorrectamente las operaciones Edit como si fueran features CAD.

BMesh sigue siendo útil para Blender/Edit, pero no debe convertirse forzosamente en el kernel paramétrico.

## 1.4 No programar un kernel CAD desde cero

No implementar desde cero:

- BREP robusto;
- booleanos sólidos;
- fillets geométricos complejos;
- solver completo de restricciones;
- intersecciones topológicas;
- shelling;
- operaciones geométricas CAD avanzadas.

Diseñar una capa de abstracción que permita usar una librería/kernel Python especializado.

La elección definitiva del kernel debe quedar desacoplada del protocolo Android.

## 1.5 El documento paramétrico es la fuente de verdad

Mientras un objeto siga siendo CAD, una malla Blender **no será la fuente autoritativa**.

La fuente será una definición paramétrica:

```text
CAD Document
    ├── Sketch001
    ├── Extrude001
    ├── Hole001
    └── Fillet001
```

La geometría visible en Blender será el resultado evaluado.

---

# 2. Experiencia de usuario objetivo

Añadir un nuevo workspace o modo principal:

```text
OBJECT | EDIT | CAD
```

El cambio de modo debe integrarse con el patrón visual ya existente de `TOP_MODE`.

No añadir el modo CAD al rail.

## 2.1 CAD Mode

Al entrar en CAD Mode, el viewport existente permanece.

Gestos:

```text
Stylus / 1 dedo
    dibujar / seleccionar / editar entidades según la herramienta activa

2 dedos
    navegación de viewport usando la infraestructura existente

Long press
    menú contextual CAD

Doble toque
    mantener el comportamiento de encuadre si no entra en conflicto con Sketch
```

No crear una segunda capa de entrada.

Toda interacción del viewport debe seguir entrando por:

```text
ui/InputSurface.kt
```

---

# 3. Alcance de la V1

La primera versión CAD NO necesita:

- assemblies;
- sheet metal;
- simulation;
- generative design;
- CAM;
- rendering CAD;
- surfacing avanzado;
- T-splines;
- constraints complejos;
- collaboration cloud;
- drawings técnicos;
- importación STEP avanzada;
- timeline editable completa al estilo Fusion 360.

La V1 debe centrarse en un núcleo pequeño pero correcto.

---

# 4. Sketcher V1

## 4.1 Planos iniciales

Permitir crear Sketch sobre:

```text
XY
XZ
YZ
```

Preparar la arquitectura para soportar posteriormente sketch sobre cara plana.

## 4.2 Entidades mínimas

Implementar inicialmente:

```text
POINT
LINE
RECTANGLE
CIRCLE
ARC
```

`RECTANGLE` puede ser una herramienta de creación que internamente genere cuatro líneas.

## 4.3 Identificadores estables

Toda entidad debe tener ID estable.

Ejemplo:

```json
{
  "id": "line_0004",
  "type": "LINE",
  "p1": [0.0, 0.0],
  "p2": [40.0, 0.0]
}
```

No usar índices temporales como identidad persistente.

## 4.4 Coordenadas

Los sketches se definen en coordenadas 2D locales del plano del sketch.

No almacenar coordenadas directamente en píxeles de pantalla.

Debe existir transformación explícita:

```text
screen
  ↓
ray del viewport
  ↓
plano de sketch
  ↓
coordenada local 2D
```

El backend es responsable de geometría/proyección real.

Android expresa intención.

## 4.5 Perfil cerrado

El sistema debe poder detectar qué bucles forman perfiles cerrados.

Para V1 basta con soportar correctamente perfiles sencillos sin auto-intersección.

El backend debe devolver a Android qué regiones están disponibles para operaciones posteriores.

---

# 5. Constraints V1

No intentar implementar un solver completo de Fusion 360 en la primera fase.

Implementar un subconjunto útil.

## 5.1 Restricciones geométricas iniciales

```text
COINCIDENT
HORIZONTAL
VERTICAL
```

Después:

```text
PARALLEL
PERPENDICULAR
EQUAL
CONCENTRIC
```

solo si el núcleo anterior ya está estable.

## 5.2 Restricciones dimensionales iniciales

```text
LENGTH
HORIZONTAL_DISTANCE
VERTICAL_DISTANCE
RADIUS
DIAMETER
```

Toda cota debe tener:

```text
id
entity/entity_refs
value
unit
driving
```

La V1 puede asumir cotas driving.

Preparar el modelo para futuras cotas driven/reference.

## 5.3 Unidades

Usar el sistema de unidades ya existente en el protocolo cuando sea posible.

No inventar otro sistema paralelo de unidades.

El sketch debe poder representar internamente valores físicos coherentes.

---

# 6. Motor de resolución

Crear una interfaz independiente del kernel CAD.

Propuesta:

```text
blender-backend/
  blender_tablet_remote/
    cad/
      __init__.py
      document.py
      sketch.py
      constraints.py
      solver.py
      features.py
      evaluator.py
      kernel.py
      blender_bridge.py
```

## 6.1 `document.py`

Responsabilidades:

- modelo completo del documento CAD;
- IDs;
- sketches;
- features;
- historial;
- serialización;
- versionado de schema.

## 6.2 `sketch.py`

Responsabilidades:

- entidades;
- geometría 2D;
- perfiles;
- topología de sketch.

## 6.3 `constraints.py`

Responsabilidades:

- estructura de constraints;
- validación;
- creación/eliminación;
- representación serializable.

## 6.4 `solver.py`

Responsabilidades:

- resolver sketch;
- grados de libertad;
- estado solved/under-constrained/over-constrained/error.

No acoplar Android al solver elegido.

## 6.5 `kernel.py`

Crear una interfaz abstracta.

Ejemplo conceptual:

```python
class CadKernel:
    def make_profile(...): ...
    def extrude(...): ...
    def cut(...): ...
    def revolve(...): ...
    def fillet(...): ...
```

No filtrar objetos internos del kernel al protocolo.

## 6.6 `evaluator.py`

Responsabilidades:

- recorrer features en orden;
- reconstruir el resultado;
- invalidar desde el primer feature afectado;
- detectar errores;
- producir geometría final.

## 6.7 `blender_bridge.py`

Responsabilidades:

- crear/actualizar representación visible en Blender;
- sustituir mesh evaluada;
- preservar nombre, selección y transformaciones cuando proceda;
- mapear documento CAD ↔ objeto Blender.

---

# 7. Features CAD V1

Primer conjunto:

```text
EXTRUDE
CUT
```

Segundo conjunto, tras estabilizar:

```text
REVOLVE
HOLE
FILLET
CHAMFER
```

Tercero:

```text
MIRROR
LINEAR_PATTERN
CIRCULAR_PATTERN
```

No comenzar por fillet.

La prioridad absoluta inicial es:

```text
Sketch → Extrude → editar dimensión → reconstruir
```

---

# 8. Feature tree / timeline

El sistema debe modelar un historial ordenado de features.

Ejemplo:

```text
Part001
├── Sketch001
├── Extrude001
├── Sketch002
├── Cut001
└── Fillet001
```

Cada feature debe tener:

```text
id
type
enabled
inputs
parameters
result_state
```

Ejemplo:

```json
{
  "id": "extrude_001",
  "type": "EXTRUDE",
  "enabled": true,
  "inputs": {
    "sketch": "sketch_001",
    "profiles": ["profile_001"]
  },
  "parameters": {
    "distance": 20.0,
    "operation": "NEW_BODY"
  }
}
```

No permitir referencias frágiles basadas exclusivamente en índices de caras Blender.

---

# 9. Persistencia

La definición CAD debe sobrevivir al guardar/cerrar `.blend`.

Primera opción recomendada:

- serialización JSON versionada;
- guardada en custom properties / datablock adecuado o estructura persistente del add-on;
- vinculada explícitamente al objeto Blender resultante.

Requisitos:

```text
cad_schema_version
document_id
object association
serialized document
```

La carga de un `.blend` debe reconstruir el estado CAD.

No depender exclusivamente de memoria Python viva.

---

# 10. Representación Blender

Para cada documento/body CAD debe existir una representación visible utilizable en Blender.

La geometría evaluada debe materializarse como mesh Blender o representación compatible.

Objetivo:

```text
CAD source
   ↓ evaluate
result geometry
   ↓
Blender object
```

La mesh Blender se actualiza cuando cambia un feature.

Debe evitarse crear objetos basura en cada preview.

---

# 11. Preview paramétrica

Reutilizar la filosofía ya establecida en el proyecto:

> una preview paramétrica se reconstruye desde una fuente estable y nunca acumula sobre la preview anterior.

Para cambios durante drag/slider:

```text
begin
update
update
update
confirm
```

o:

```text
begin
update
cancel
```

No crear un undo por cada `update`.

Confirmar genera un punto lógico de undo.

Cancelar restaura estado anterior.

---

# 12. Protocolo

Respetar el orden contractual de `AGENTS.md`.

Para cualquier mensaje nuevo:

1. `blender-backend/docs/protocol.md`
2. `protocol.py`
3. fixtures v2
4. `android_contract.py`
5. implementación backend
6. parser/cliente Android

El backend sigue siendo propietario del protocolo.

Android no inventa campos.

---

# 13. Familias de comandos propuestas

No congelar nombres definitivos sin pasar por el proceso contractual.

Propuesta inicial:

## Documento

```text
cad.document.create
cad.document.get
cad.document.delete
cad.document.rebuild
```

## Sketch

```text
cad.sketch.create
cad.sketch.get
cad.sketch.finish
cad.sketch.delete
```

## Entidades

```text
cad.sketch.entity.add
cad.sketch.entity.update
cad.sketch.entity.delete
```

## Constraints

```text
cad.sketch.constraint.add
cad.sketch.constraint.update
cad.sketch.constraint.delete
```

## Features

```text
cad.feature.add
cad.feature.update
cad.feature.delete
cad.feature.move
cad.feature.toggle
```

## Sesiones

Si encaja con el modelo existente:

```text
cad.session.begin
cad.session.update
cad.session.confirm
cad.session.cancel
```

Evitar crear cientos de comandos ultraespecíficos si un comando schema-driven puede mantener el protocolo más estable.

---

# 14. Eventos y estado

Definir eventos ricos.

Ejemplos:

```text
cad.document.changed
cad.sketch.changed
cad.feature.changed
cad.selection.changed
cad.rebuild.completed
cad.rebuild.failed
```

El snapshot del CAD no debe engordar innecesariamente el snapshot normal de escena.

Preferir peticiones específicas si el árbol CAD es grande.

---

# 15. Capabilities

El cliente debe ocultar cualquier función CAD no anunciada.

Ejemplo conceptual:

```text
cad
cad.sketch
cad.constraints
cad.features.extrude
cad.features.cut
```

No dejar botones muertos.

---

# 16. Android — estructura

Crear un subsistema UI claro.

Propuesta:

```text
android-client/app/src/main/.../
  ui/
    cad/
      CadWorkspace.kt
      CadToolbar.kt
      CadSketchOverlay.kt
      CadFeatureTray.kt
      CadTreePanel.kt
      CadContextMenu.kt
```

Mantener:

```text
InputSurface.kt
```

como única frontera de entrada del viewport.

No crear `CadInputSurface`.

La lógica decide la intención a partir del modo activo.

---

# 17. Estado Android

Añadir al estado conceptos como:

```text
workspaceMode
cadDocument
activeSketch
activeCadTool
activeCadSession
cadSelection
cadFeatureTree
cadError
```

No meter blobs gigantes si no son necesarios para recomposición.

Evitar recomponer todo `Workspace` por movimiento del stylus.

La interacción caliente debe seguir optimizada.

---

# 18. Overlay de Sketch

Android necesita overlay ligero para:

- entidades sketch;
- puntos;
- selección;
- previews;
- cotas;
- constraints;
- perfiles cerrados;
- feedback bajo el stylus.

El overlay NO sustituye la geometría autoritativa del backend.

Durante una sesión puede haber feedback local predictivo, pero debe reconciliarse con el estado remoto.

Inspirarse en el patrón ya usado por Knife.

---

# 19. Herramientas Sketch UI

Primera toolbar:

```text
Seleccionar
Línea
Rectángulo
Círculo
Arco
Cota
Constraint
Finalizar sketch
```

No llenar la pantalla.

Priorizar viewport dominante.

Usar menús/contextos para herramientas menos frecuentes.

---

# 20. Bandejas CAD

Reutilizar el patrón visual de:

```text
TransformBar
EditToolTray
KnifeTray
```

Ejemplo:

```text
EXTRUIR

Distancia [ 20.00 mm ]
Operación [ Nuevo cuerpo ]
Dirección [ Normal ]

                 DESCARTAR   CONFIRMAR
```

Los controles deben ser schema-driven cuando tenga sentido.

---

# 21. Árbol CAD en Android

Añadir un panel/overlay opcional para:

```text
Sketch001
Extrude001
Sketch002
Cut001
```

Acciones mínimas:

- seleccionar feature;
- editar parámetros;
- activar/desactivar;
- borrar;
- renombrar.

Mover/reordenar features puede esperar.

---

# 22. Selección CAD

Separar claramente:

```text
Blender selection
CAD selection
Sketch selection
```

No mezclar IDs de vértices BMesh con entidades paramétricas.

Tipos de selección CAD futuros:

```text
BODY
FACE
EDGE
VERTEX
SKETCH
SKETCH_ENTITY
PROFILE
FEATURE
```

La V1 necesita como mínimo:

```text
SKETCH_ENTITY
PROFILE
FEATURE
```

---

# 23. Conversión a mesh

Añadir explícitamente una acción futura:

```text
Convertir a malla
```

Comportamiento:

1. evaluar CAD;
2. conservar geometría visible;
3. desvincular o archivar definición paramétrica según diseño final;
4. convertir el objeto a Blender mesh normal;
5. pasar a Object/Edit workflow estándar.

Debe ser una operación deliberada y destructiva.

No convertir automáticamente a malla editable al crear una feature.

---

# 24. Undo/redo

Decidir claramente dos niveles:

```text
CAD document history
Blender undo
```

Para V1 puede ser aceptable que cada confirmación CAD genere una operación atómica y un undo Blender asociado.

Nunca empujar undo por cada pixel de drag.

Cancelar una sesión no deja residuos.

---

# 25. Librería/kernel CAD

Antes de implementar features sólidos avanzados, realizar una spike técnica.

Evaluar al menos:

```text
CadQuery / OCP/OpenCascade
build123d
FreeCAD Python API
```

Criterios:

- compatibilidad con Python embebido de Blender objetivo;
- posibilidad real de empaquetado;
- dependencias binarias;
- licencia;
- estabilidad;
- booleanos;
- fillet/chamfer;
- STEP futuro;
- conversión a mesh;
- rendimiento;
- dificultad de distribución dentro del add-on.

No comprometer el protocolo con una librería concreta.

Crear primero la interfaz `CadKernel`.

---

# 26. Riesgo crítico: dependencias binarias

Blender usa su propio Python.

Antes de elegir OpenCascade/OCP/etc. verificar:

- versión Python exacta;
- plataformas objetivo;
- wheels disponibles;
- arquitectura CPU;
- compatibilidad con Blender 4.2+ y la versión usada principalmente;
- tamaño del add-on;
- instalación sin compilar localmente.

Si empaquetar un kernel CAD resulta inviable, mantener una alternativa:

```text
Blender-native V1
```

para Sketch + Extrude/Cut simples, sin hipotecar el diseño.

---

# 27. Fases de implementación

## Fase 000 — Arquitectura CAD y spike de kernel

Backend owner.

Entregables:

- documento técnico de arquitectura;
- interfaz `CadKernel`;
- evaluación reproducible de librerías;
- decisión documentada;
- formato inicial de `CadDocument`;
- pruebas de serialización;
- ningún cambio destructivo en UI.

Cierre:

- se puede crear un documento CAD vacío;
- serializar;
- deserializar;
- persistir en `.blend`;
- tests verdes.

---

## Fase 001 — Sketch base

Backend + frontend, cada uno en su árbol correspondiente.

Backend:

- planes XY/XZ/YZ;
- Line;
- Rectangle;
- Circle;
- Arc;
- IDs estables;
- transformación ray → sketch plane → 2D;
- perfiles cerrados básicos;
- comandos/protocolo/fixtures/tests.

Android:

- CAD Mode en `TOP_MODE`;
- toolbar Sketch;
- routing por `InputSurface`;
- overlay;
- crear entidades con stylus;
- seleccionar;
- borrar;
- finalizar sketch.

Cierre:

> desde tablet se crea un sketch rectangular con un círculo y se recupera igual al reconectar.

---

## Fase 002 — Cotas y constraints

Backend:

- Coincident;
- Horizontal;
- Vertical;
- Length;
- Horizontal distance;
- Vertical distance;
- Radius;
- Diameter;
- solver;
- estado de constraint.

Android:

- tool de cota;
- edición numérica;
- indicadores de constraint;
- feedback de sketch resuelto.

Cierre:

> crear un rectángulo, fijarlo a 80 × 45 mm, círculo Ø6 y reconstruir de forma determinista.

---

## Fase 003 — Extrude

Backend:

- selección de perfil;
- feature `EXTRUDE`;
- evaluación;
- preview;
- confirm/cancel;
- reconstrucción;
- representación Blender.

Android:

- selección visual de profile;
- comando Extrude;
- bandeja de distancia;
- preview;
- confirm/cancel.

Cierre obligatorio:

> Sketch cerrado → Extrude 20 mm → cambiar ancho del sketch → sólido se reconstruye correctamente.

Este es el primer milestone de producto.

---

## Fase 004 — Cut + múltiples sketches

Implementar:

- sketch adicional;
- sketch asociado a plano;
- Cut por extrusión;
- árbol de features básico;
- editar feature existente.

Cierre:

> caja rectangular extruida + segundo sketch circular + Cut que genere un agujero.

---

## Fase 005 — Feature Tree

Android:

- panel del árbol;
- seleccionar;
- renombrar;
- editar;
- toggle;
- borrar.

Backend:

- dependencia;
- invalidación;
- rebuild parcial cuando sea posible;
- errores de feature.

Cierre:

> editar un feature antiguo reconstruye los posteriores o devuelve un error controlado.

---

## Fase 006 — Features mecánicas

Después de estabilidad:

```text
REVOLVE
HOLE
CHAMFER
FILLET
```

No implementar todos a la vez.

Uno por ciclo.

---

## Fase 007 — Patterns

```text
MIRROR
LINEAR_PATTERN
CIRCULAR_PATTERN
```

Solo tras estabilizar referencias topológicas.

---

# 28. Topological naming

Este es un riesgo serio.

No depender de:

```text
Face 3
Edge 8
```

como referencia permanente de un feature posterior.

Diseñar desde el principio una abstracción de referencias geométricas.

La V1 puede limitar funcionalidades para evitar resolver completamente el topological naming problem, pero no debe fingir que índices Blender son estables.

Documentar cualquier limitación explícitamente.

---

# 29. Rendimiento

No enviar cada punto del stylus como una operación pesada si puede coalescerse.

Mantener la regla existente:

> nudges caros se serializan/coalescen.

Aplicar lo mismo a:

```text
cad.session.update
sketch drag
dimension drag
feature slider
```

Android puede dibujar feedback local inmediato.

El backend es autoritativo.

---

# 30. Threading

Mantener las reglas existentes.

No llamar:

```text
bpy
bmesh
```

desde threads de red.

Las mutaciones Blender deben pasar por el hilo principal y el pump existente.

Si el kernel CAD puede calcular fuera del hilo principal y no toca Blender, estudiar mover trabajo pesado a worker, pero:

- no introducir carreras;
- no entregar resultados sobre documentos ya invalidados;
- usar revision IDs.

---

# 31. Revisionado

Añadir revision/version a documentos y sesiones.

Ejemplo:

```text
document_revision = 34
```

Si llega un resultado asíncrono para revision 31 cuando el documento ya está en 34:

```text
descartar
```

Esto será especialmente importante si el kernel se ejecuta fuera del hilo principal.

---

# 32. Errores

Definir errores estables.

Ejemplos conceptuales:

```text
CAD_DOCUMENT_NOT_FOUND
CAD_SKETCH_NOT_FOUND
CAD_PROFILE_INVALID
CAD_PROFILE_OPEN
CAD_CONSTRAINT_CONFLICT
CAD_REBUILD_FAILED
CAD_KERNEL_ERROR
CAD_REFERENCE_INVALID
```

No devolver traceback Python a Android como contrato.

Guardar detalle diagnóstico para logs.

---

# 33. Tests mínimos

Backend:

- serialización;
- persistencia;
- entidades sketch;
- constraints;
- solver;
- perfiles;
- evaluator;
- extrude;
- cancel;
- rebuild;
- errores;
- protocolo;
- fixtures;
- contrato Android.

GUI:

- proyección ray/plano desde VIEW_3D real;
- selección sobre sketch;
- resultado Blender visible;
- reconstrucción visible.

Android JVM:

- parser;
- reducers/state;
- capability gating;
- command creation;
- routing InputSurface;
- UI state;
- session reconciliation.

No congelar conteos de tests en documentación.

---

# 34. Regresión obligatoria

Cada ciclo CAD debe verificar que no rompe:

- Object Mode;
- Edit Mode;
- navegación;
- selección;
- H.264;
- MJPEG fallback;
- file browser;
- transform sessions;
- tools Edit;
- Knife;
- modifiers;
- undo/redo;
- reconexión.

CAD no puede degradar el workflow Blender ya terminado.

---

# 35. Separación de agentes

Mantener estrictamente las reglas actuales.

## Backend agent

Solo:

```text
blender-backend/**
*_PLAN_BACKEND_*.md
```

## Frontend agent

Solo:

```text
android-client/**
*_PLAN_FRONTEND_*.md
```

## Principal

Gestiona:

```text
AGENTS.md
README.md
configuración raíz
coordinación
```

El backend posee protocolo y fixtures.

El frontend no los modifica.

---

# 36. Nueva numeración

Según `AGENTS.md`, no hay planes activos y el siguiente ciclo debe comenzar desde:

```text
000
```

Si se inicia el desarrollo CAD, crear como mínimo:

```text
000_PLAN_BACKEND_CAD_ARCHITECTURE.md
000_PLAN_FRONTEND_CAD_WORKSPACE.md
```

Si la fase inicial no requiere todavía frontend, puede comenzar únicamente el backend siempre que quede documentado.

No mezclar fases independientes en un mega-plan imposible de cerrar.

---

# 37. Primer objetivo exacto recomendado para Codex

Antes de implementar todo el roadmap, ejecutar únicamente este vertical slice:

```text
1. Añadir CAD como modo reconocido.
2. Crear CadDocument versionado.
3. Crear Sketch sobre XY.
4. Crear LINE/RECTANGLE/CIRCLE.
5. Renderizar overlay en Android.
6. Detectar profile rectangular cerrado.
7. Añadir cotas de ancho/alto.
8. Crear EXTRUDE.
9. Materializar resultado en Blender.
10. Editar ancho.
11. Rebuild.
12. Ver la pieza actualizarse en tablet.
13. Guardar .blend.
14. Reabrir.
15. Recuperar el documento paramétrico.
```

No añadir otras features antes de que este flujo sea sólido.

---

# 38. Criterio de éxito del MVP

El MVP CAD se considera conseguido cuando en tablet real se puede hacer sin teclado/ratón:

1. entrar en CAD;
2. crear sketch XY;
3. dibujar rectángulo;
4. ajustar 80 × 45 mm;
5. dibujar círculo;
6. ajustar Ø6 mm;
7. finalizar sketch;
8. seleccionar profile exterior;
9. extruir 20 mm;
10. volver al sketch;
11. cambiar 80 → 100 mm;
12. ver reconstrucción correcta;
13. guardar `.blend`;
14. cerrar;
15. reabrir;
16. seguir editando el modelo paramétrico.

---

# 39. No objetivos del MVP

No retrasar el MVP por:

- STEP;
- IGES;
- assemblies;
- fillet perfecto;
- topological naming general;
- constraints avanzados;
- sketch sobre cualquier superficie;
- snapping CAD complejo;
- inferencia automática de constraints sofisticada;
- timeline drag&drop;
- cloud;
- IA;
- reconocimiento de dibujos a mano alzada.

---

# 40. Dibujo libre / reconocimiento futuro

La idea de dibujar de forma libre con stylus y convertir intención en geometría es válida, pero debe ser una capa superior futura.

Ejemplo:

```text
stylus gesture
    ↓
recognizer
    ↓
rectangle/circle/arc candidate
    ↓
Sketch entities exactas
    ↓
dimensions
```

No hacer que la geometría CAD interna sea un conjunto de trazos.

El reconocimiento debe producir entidades paramétricas normales.

---

# 41. Arquitectura final deseada

```text
┌──────────────────────────────────────┐
│              ANDROID                 │
│                                      │
│  Object | Edit | CAD                 │
│                                      │
│  InputSurface                        │
│  Viewport / H264                     │
│  Sketch overlay                      │
│  CAD toolbars                        │
│  CAD trays                           │
│  Feature tree                        │
└─────────────────┬────────────────────┘
                  │ WebSocket JSON
┌─────────────────▼────────────────────┐
│         BLENDER TABLET REMOTE        │
│                                      │
│  protocol / bridge / pump            │
│                                      │
│  Blender subsystem                   │
│  ├─ Object                           │
│  └─ Edit                             │
│                                      │
│  CAD subsystem                       │
│  ├─ CadDocument                      │
│  ├─ Sketch                           │
│  ├─ Constraints                      │
│  ├─ Solver                           │
│  ├─ Features                         │
│  ├─ Evaluator                        │
│  └─ CadKernel abstraction            │
│                                      │
│        ↓ evaluated geometry          │
│                                      │
│  Blender Object / Mesh               │
└──────────────────────────────────────┘
```

---

# 42. Regla final para Codex

No intentar completar “Fusion 360 para Android” en un único ciclo.

Construir vertical slices pequeños, probables y cerrables.

La prioridad es conseguir primero un sistema donde:

> el usuario dibuja una pieza de precisión en la tablet, la acota, la extruye y puede cambiar sus dimensiones posteriormente sin destruir el modelo.

Si eso funciona bien, el resto del CAD se construirá encima.

Ese núcleo debe conservar la filosofía actual del proyecto:

- Android expresa intención;
- Blender sigue siendo el host;
- protocolo estable;
- UI táctil;
- viewport dominante;
- sesiones reversibles;
- estado autoritativo en backend;
- capabilities;
- tests;
- cero duplicación innecesaria.
