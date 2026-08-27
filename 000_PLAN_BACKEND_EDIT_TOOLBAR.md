# 000 — Backend: toolbar activa de Edit y Cut/Bisect

**Estado: activo. Propiedad exclusiva: `blender-backend/**`.**

## Feedback que abre el ciclo

En tablet real, el usuario pide que Edit Mode tenga una barra izquierda de herramientas
activas equivalente a la lógica de Blender, no una lista de operaciones discretas. El
alcance congelado es Extrude, Inset, Loop Cut y Cut (Knife/Bisect). También se ha
detectado que el arrastre horizontal de Rotate y Scale está invertido tanto en Object
como en Edit; la navegación de cámara funciona correctamente y no debe cambiar.

## B0 — Contrato antes de implementación

Actualizar en orden `docs/protocol.md`, `protocol.py`, fixtures v2,
`tests/android_contract.py` e implementación.

- Añadir feature versionada `edit_toolbar` con familias ordenadas y variantes.
- Cada familia anuncia `id`, etiqueta, variante por defecto, requisitos, tipo de input,
  comando/sesión y parámetros aplicables.
- Familias obligatorias y orden: `EXTRUDE`, `INSET`, `LOOP_CUT`, `CUT`.
- Variantes obligatorias:
  - Extrude: `REGION`, `ALONG_NORMALS`, `INDIVIDUAL`.
  - Inset: `REGION`, `INDIVIDUAL`.
  - Loop Cut: una variante `LOOP_CUT` con entrada por toque de arista.
  - Cut: `KNIFE`, `BISECT`.
- Mantener `edit_catalog` y comandos existentes para clientes anteriores.
- Bevel, Subdivide y Bridge siguen accesibles por sus superficies actuales/fallback,
  pero no se añaden a esta toolbar sin nuevo feedback.

## B1 — Herramienta activa y ciclo de sesión

- El backend distingue herramienta/variante armada de sesión con preview ya iniciada.
- Activar otra familia o variante cancela y restaura la sesión incompatible; nunca
  confirma geometría implícitamente.
- `tool.status` devuelve familia, variante y parámetros efectivos.
- Tap/drag posterior usa la herramienta activa hasta que el usuario elige otra.

## B2 — Extrude e Inset

- Extrude REGION conserva distancia, bloqueo `FREE|X|Y|Z` y orientación
  `GLOBAL|LOCAL|VIEW`.
- Extrude ALONG_NORMALS e INDIVIDUAL conservan distancia pero rechazan/ocultan bloqueo
  de eje y orientación incompatibles.
- Inset implementa contractualmente REGION e INDIVIDUAL con thickness/depth y preview
  reconstruida desde backup.
- Cambiar variante o parámetro nunca acumula previews.

## B3 — Loop Cut

- Reutilizar `mesh.loop_probe`, `tool.begin LOOP_CUT` y `tool.loop_pick`.
- Al activarlo queda armado; el siguiente toque selecciona el loop y abre preview.
- Conservar cuts, factor, smoothness, falloff, even, flip y clamp.
- Todo sondeo se hace contra el backup, no contra índices del preview.

## B4 — Cut: Knife y Bisect

- Knife reutiliza la sesión de polilínea, puntos/pop/close/snap y overlay reproyectable.
- Bisect es una sesión `DRAG_LINE`: inicio y fin normalizados definen el plano visible
  con la dirección de cámara.
- Implementar Bisect con `bmesh.ops.bisect_plane`, sin reutilizar Knife ni operadores
  interactivos de escritorio.
- Parámetros Bisect: `clear_inner`, `clear_outer`, `fill`.
- Línea o parámetro nuevo reconstruye desde backup; confirm crea un undo y cancel
  restaura exactamente.

## B5 — Snap real en transformaciones y tools

- Auditar todos los parámetros de Snap anunciados y comprobar que no sean solo estado
  decorativo: `INCREMENT`, `GRID`, `VERTEX`, `EDGE` y `FACE` deben modificar la preview
  y el resultado confirmado.
- Cubrir Move/Rotate/Scale en Object y Edit, respetando las restricciones ya definidas:
  Rotate/Scale tratan GRID como INCREMENT y los candidatos geométricos solo se anuncian
  donde sean aplicables.
- Las tools de esta toolbar aplican únicamente los snaps que anuncien. Extrude debe
  respetar incremento/rejilla y candidatos compatibles con su variante; Loop Cut,
  Knife y Bisect deben usar su snap específico de geometría/entrada, sin simular el
  snap de transformación cuando no corresponda.
- `tool.status` y `transform.status` devuelven el snap efectivo y el valor ya ajustado,
  no solo la selección solicitada por Android.
- Un tipo no soportado se rechaza contractualmente y Android debe ocultarlo; nunca se
  acepta un control que no cambie el resultado.
- Añadir pruebas comparando exactamente la misma entrada con Snap apagado/encendido y
  verificando una diferencia geométrica reproducible, además de cancel/confirm.

## B6 — Signo de Rotate/Scale

- Reproducir el arrastre horizontal invertido en transformación modal y rutas legacy,
  tanto Object como Edit.
- Corregir el signo común una sola vez y fijarlo con pruebas: dedo a la derecha produce
  respuesta visual a la derecha/positiva según la herramienta.
- No modificar orbit, pan, zoom, roll ni Move.

## B7 — Cierre

- Pruebas headless de variantes, validación, preview repetida, cancel, confirm y undo.
- Pruebas GUI de Bisect, toque de Loop Cut, Snap efectivo y signo de Rotate/Scale desde
  Object/Edit.
- Contrato Android completo y compatibilidad con `edit_catalog`.
- Smoke físico con dedo y Lenovo Pen de las cuatro familias, Snap y Rotate/Scale.

No se cierra ni se borra este plan mientras falte alguno de estos criterios.
