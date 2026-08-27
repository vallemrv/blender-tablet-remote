# 001 — Frontend Android: snap táctil de tools y Dissolve contextual

**Estado: ejecutado.** Propietario: agente frontend (`android-client/**`).  Este plan no
modifica protocolo, fixtures ni backend. Se ejecutó contra el contrato que congeló el
propietario backend.

## Cierre (2026-08-27)

- [x] F1: `SnapToggle` es schema-driven vía `ToolSession.availableSnapTypes`; candidato
  visual tolera servidores antiguos (`screen` opcional).
- [x] F2: `InputSurface`/`MainViewModel.toolPointer` envían `u/v` coalescido (latest-wins,
  máx. 30 Hz) durante el arrastre, sin interferir con navegación de dos dedos.
- [x] F3: selector de tipo/paso schema-driven cableado en Extrude, Inset, Loop Cut,
  **Bevel y Bridge Edge Loops** (los dos últimos tenían el contrato ampliado en backend
  pero ninguna llamada a `SnapToggle` en `EditToolTray`; se añadió `BevelParams` —antes
  inexistente, cara al `else` genérico sin snap— y la llamada que faltaba en
  `BridgeParams`). `MainViewModel.toolDefaultParameters` ahora siembra `snap_type: NONE`
  para las tools que lo anuncian, así el selector no depende de que el usuario ya haya
  tocado un preset antes de que aparezca.
- [x] F4: marcador de candidato dibujado en `InputSurface.drawSnapCandidate` con forma
  por tipo (Vértice/Arista/Cara/Cursor), oculto cuando `snapCandidate` es null (pérdida
  de hit, cambio de snap, cierre de sesión).
- [x] F5: Disolver vive en el submenú de `DELETE` del radial (Borrar/Disolver por
  Vértice/Arista/Cara), sin gastar un sector aparte ni sustituir por `ONLY_FACES`.

Validación: 107/107 tests JVM (`:android-client:app:testDebugUnitTest`,
incluye nuevos casos de `availableSnapTypes` para Bevel/Bridge/Subdivide) y
`assembleDebug` en verde.

## Objetivo

Hacer que el snap sea preciso y visible tanto en transformaciones como en las tools
paramétricas, con pasos expresables en m/cm/mm, y separar claramente **Borrar** de
**Disolver** en el radial de Edit según Vértice/Arista/Cara.

## Auditoría inicial (2026-08-27)

### Transformaciones

- `SnapType` ya modela `NONE`, `INCREMENT`, `GRID`, `VERTEX`, `EDGE`, `FACE` y
  `CURSOR`; los geométricos solo se ofrecen en `MOVE`, conforme al contrato actual.
- `TransformBar` ya permite tipo de snap, paso, valor exacto y orientación.
- `ValueParser` ya acepta metros, centímetros y milímetros (`m`, `cm`, `mm`), grados
  y porcentajes. Los presets de movimiento ya llegan hasta 1 mm.
- El arrastre se despacha a 30 Hz acumulando deltas. Sin embargo,
  `transform.snap_candidate` solo se solicita desde `MainViewModel.pick()`: durante un
  arrastre no se actualiza con la posición absoluta del dedo.
- `TransformSession.snapCandidate` solo contiene tipo/id/objeto. La UI enseña texto en
  la bandeja (`SnapCandidateHint`), pero no puede colocar un marcador sobre el objetivo
  porque el contrato no publica coordenadas de pantalla del candidato.

### Tools paramétricas

- El catálogo actual ya anuncia `snap_type` y `snap_step` para Extrude, Inset y Loop
  Cut, pero solo como snap escalar (`NONE|INCREMENT|GRID`); en escalares, GRID equivale
  actualmente a INCREMENT.
- `EditToolTray` no consume el schema del catálogo para el snap: `SnapToggle` está
  hardcodeado a `NONE <-> INCREMENT` y no muestra ni edita `snap_step`.
- Bevel, Subdivide y Bridge no anuncian snap en el contrato actual.
- `tool.nudge` recibe solo un delta escalar, no la posición absoluta del dedo. Por ello
  no puede resolver snap geométrico a vértice/arista/cara ni mostrar candidato sin una
  ampliación de contrato.
- Loop Cut necesita distinguir dos precisiones: posición sobre el loop (factor/paso) y
  candidato de colocación/reubicación bajo el dedo. No deben mezclarse en un único
  booleano "Snap".

### Radial Borrar / Disolver

- `DELETE` ya elige `VERTS`, `EDGES` o `FACES` según `SelectionMode`.
- `DISSOLVE` solo aparece en Face y hoy ejecuta `mesh.delete("ONLY_FACES")`. Eso borra
  caras conservando bordes; no representa las tres operaciones Dissolve de Blender.
- No debe inventarse un wire desde Android. El radial podrá habilitar Dissolve en los
  submodos anunciados cuando el catálogo/capabilities entregue comando y payload.

## Necesidades exactas del contrato backend

1. Snap de tools anunciado por schema, por tool y parámetro:
   - tipos admitidos;
   - paso, mínimo/máximo y unidad;
   - parámetro al que aplica;
   - si admite seguimiento geométrico por posición de viewport.
2. Un comando contractual para actualizar una tool activa con la posición absoluta
   normalizada del dedo (`u`, `v`) y el tipo elegido, o una extensión equivalente del
   comando de nudge. Android no fijará el nombre.
3. Estado de sesión de tool que devuelva el tipo/paso efectivos y el candidato actual.
4. Para todo candidato visual (transform y tool): `hit`, tipo, id estable, objeto y
   posición normalizada `[u,v]`. Opcionalmente etiqueta; Android puede derivarla del
   tipo si no se anuncia.
5. Dissolve como acción discreta anunciada para VERTEX/EDGE/FACE, con comando y payload
   canónicos diferentes de `mesh.delete`. Debe indicar requisitos y disponibilidad.

## Fases de implementación

### F1 — Modelo y parser tolerante

- Modelar opciones de snap de tool desde los parámetros declarativos, sin duplicar
  enums del servidor ni asumir soporte universal.
- Parsear tipo, paso y candidato de tool; ignorar campos desconocidos y ocultar controles
  cuando no se anuncien.
- Extender el candidato visual con posición normalizada opcional, manteniendo
  compatibilidad con servidores antiguos.
- Añadir fixtures/tests Android solo después de que backend congele sus fixtures.

### F2 — Seguimiento del dedo y coalescing

- `InputSurface` seguirá siendo la única capa de entrada.
- Enviar la posición absoluta del puntero al ritmo acompasado existente (máximo 30 Hz),
  acumulando deltas y conservando el último `u/v`.
- Serializar/coalescer la consulta geométrica: como máximo una en vuelo y conservar
  latest-wins, para no ahogar el hilo principal de Blender.
- Mantener navegación con dos dedos y el círculo derecho fuera del flujo de snap.

### F3 — UI de snap para tools

- Sustituir `SnapToggle` por selector schema-driven de tipo y paso.
- Ofrecer presets de distancia (m/cm/mm) solo en parámetros de distancia; grados,
  factor o porcentaje según unidad declarada.
- Permitir valor exacto con el parser correspondiente y mostrar el valor efectivo
  devuelto por la sesión, no uno optimista divergente.
- Loop Cut mostrará por separado snap de factor/posición y snap geométrico de pick si
  ambos son anunciados.

### F4 — Marcador de candidato

- Dibujar en `InputSurface` un marcador pequeño sobre `[u,v]`, con forma/color por
  Vértice/Arista/Cara y sin interceptar eventos.
- Ocultarlo al perder candidato, cambiar snap, terminar/cancelar sesión o navegar.
- Mantener el texto de la bandeja como complemento accesible.

### F5 — Dissolve radial

- Mostrar Dissolve directamente en el radial de Edit cuando haya selección y el
  catálogo lo anuncie para el submodo activo.
- Borrar conserva su semántica destructiva `VERTS/EDGES/FACES`; Disolver invoca el
  comando/payload anunciado, nunca `ONLY_FACES` como sustituto.
- Si el límite de ocho sectores se supera, ajustar el conjunto contextual sin duplicar
  acciones ni esconder Borrar/Disolver dentro de un botón sin handler.

## Pruebas y cierre

- Tests puros de disponibilidad de tipos/unidades y selección del parser por schema.
- Tests de coalescing latest-wins y de limpieza del candidato al cerrar sesión.
- Tests de layout/normalización del marcador y de que no consume input.
- Tests del radial para VERTEX/EDGE/FACE: Borrar y Disolver distintos, con payloads
  contractuales y ocultación ante servidor antiguo.
- `:android-client:app:testDebugUnitTest` y `:android-client:app:assembleDebug` en verde.
- Validación en tablet: arrastre continuo con Incremento/Rejilla y con candidato
  Vértice/Arista/Cara visible, además de Borrar y Disolver en los tres submodos.

