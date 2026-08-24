# Plan activo — agente frontend Android

**Estado: completado (F0–F6).** Contrato integrado, UI y cliente entregados; tests
JVM y APK debug compilan correctamente. Queda únicamente el smoke manual en hardware
real con dedo y Lenovo Pen.

Propiedad exclusiva: `android-client/**`. Lee `AGENTS.md` completo antes de editar.
No modifiques `blender-backend/**`, protocolo, fixtures, archivos raíz ni
`PLAN_BACKEND.md`.

## Objetivo

Integrar el contrato congelado de modifiers, Loop Cut, apply y objetos ocultos sin
romper el diseño actual ni duplicar ninguna acción.

## F0 — Trabajar contra contrato congelado

- Leer `blender-backend/docs/protocol.md` y fixtures v2.
- No inventar defaults, campos ni parámetros de modifiers.
- Capability gating: una superficie no aparece si el servidor no la anuncia.
- Si una fixture es insuficiente, informar al principal; no editarla.

## F1 — Modelos, parser y cliente

Añadir:

- `HiddenObject(name,type)`.
- descriptor de modifier y parámetros tipados (integer, decimal, boolean, enum,
  vector, object picker).
- `ModifierState` y pila del activo.
- `BlenderState.hiddenObjects`.
- `ActiveTool/EditTool.LOOP_CUT`.

Extender `RemoteBlenderClient`, implementación WebSocket y `MainViewModel` con todos
los `modifier.*`, `object.hide/reveal`, `transform.apply` y Loop Cut.

- Actualizar modifiers/hidden slices directamente desde respuestas/eventos ricos.
- No pedir `scene.get_state` por cada evento si el payload ya contiene los datos.
- Coalescer sliders y serializar nudges caros.

## F2 — Propiedad de acciones

Actualizar `Actions.kt`, `RadialMenu.kt` y tests:

- `HIDE_OBJECT`: RADIAL solo Object con objetivo/selección.
- `HIDE_GEOMETRY`: RADIAL solo Edit con selección.
- `REVEAL_GEOMETRY`: RADIAL solo Edit.
- `SHOW_HIDDEN_OBJECT` y `SHOW_ALL_HIDDEN_OBJECTS`: TOP_DYNAMIC.
- acciones de modifier: MODIFIER_PANEL.
- `TOOL_LOOP_CUT`: RAIL; parámetros/confirm/cancel: bandeja de tool.
- Apply: TOP dentro de Objeto.

Retirar los IDs ambiguos `HIDE_SELECTION/REVEAL_SELECTION` cuando todos sus consumidores
estén migrados. H no aparece en top, rail, footer ni panel. Reveal Object no aparece en
radial.

## F3 — Menú dinámico Ocultos y Aplicar

En `MenuBar.kt`:

- `Ocultos` aparece inmediatamente después de `Objeto` solo si la lista no está vacía.
- Una fila por objeto con nombre, tipo y check de visibilidad; tocar revela exactamente
  ese nombre y la fila desaparece al reconciliar estado.
- `Mostrar todos` al final del mismo menú.
- Al vaciarse, desaparece el anchor completo.
- No mostrar flags `hide_viewport` del outliner.

En `Objeto > Aplicar`: Posición, Rotación, Escala y opcional combinación Posición y
escala. Solo Object Mode y selección válida. Nunca llamarlo Reset ni duplicarlo en el
footer/radial.

## F4 — Inspector de modifiers

Crear `ui/ModifierPanel.kt` y abrirlo desde anchor top `Modificadores`.

- Panel flotante lateral derecho, plegable, con estética de `Theme.kt`.
- Visible solo con capability y objeto activo compatible.
- Lista ordenada de tarjetas; add, parámetros, viewport/render, subir/bajar, aplicar y
  eliminar.
- Generar controles desde `modifier.add_options`; no hardcodear knobs/defaults.
- Boolean object picker: solo MESH, excluye activo, y permite “sin operando”.
- Acciones destructivas claras; aplicar/eliminar reconciliados con respuesta.
- Cambiar activo actualiza el contenido; perder objeto válido cierra el panel.
- No ocupar footer ni rail.

## F5 — Loop Cut

- Añadir Loop Cut al rail de Edit.
- Si hay edge seleccionada, comenzar sesión.
- Si no, armar tool; el siguiente tap selecciona EDGE, espera respuesta con índice y
  llama `tool.begin`.
- `EditToolTray`: cuts entero, smoothness, factor, confirm y cancel.
- Drag alimenta factor con nudge serializado.
- Confirm/cancel cierran sesión pero dejan Loop Cut elegido para repetir.
- No confundir con Select Loop/Ring ni Subdivide.

## F6 — Pruebas y APK

Obligatorias:

- parser de descriptors, cinco modifiers, Boolean null y hidden empty/nonempty;
- payload exacto de todos los comandos y eventos parciales;
- SurfaceCatalog sin duplicados;
- radial: H Object sin Reveal Object; Hide/Reveal geometry solo Edit; máximo ocho;
- Compose: `Ocultos` ausente/vigente, reveal individual/all y desaparición;
- inspector schema-driven, reorder/toggles/apply/remove y Boolean filter;
- Loop Cut con edge, armado sin edge, confirm/cancel persistente y nudge serial;
- capability gating.

Cierre:

```bash
JAVA_HOME=/home/valle/.local/opt/jdk-17.0.20+8 \
  ./gradlew --no-daemon :android-client:app:testDebugUnitTest \
  :android-client:app:assembleDebug
```

Hacer smoke manual con dedo y Lenovo Pen. No tocar nombres wire para “hacer que pase”:
si el contrato real diverge, detener integración e informar al principal.
