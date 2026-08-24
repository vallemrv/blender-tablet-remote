# Plan activo — agente backend

**Estado: completado (B0–B6).** Contrato v2 congelado, implementación y CLI
entregadas; suite headless y contrato Android pasan contra Blender 5.2 LTS.

Propiedad exclusiva: `blender-backend/**`. Lee `AGENTS.md` completo antes de editar.
No modifiques `android-client/**`, archivos raíz ni `PLAN_FRONTEND.md`.

## Objetivo

Entregar el contrato y backend para:

- modifiers SUBSURF, ARRAY, BEVEL, SOLIDIFY y BOOLEAN;
- Loop Cut paramétrico en Edit;
- ocultar/revelar objetos del view layer;
- aplicar posición, rotación y escala sin confundirlo con reset;
- estado/eventos suficientes para el inspector Android y menú `Ocultos`.

## B0 — Congelar contrato antes de implementar

Actualizar en este orden: `docs/protocol.md`, `protocol.py`, fixtures v2 y
`tests/android_contract.py`.

### Respuestas y eventos

- Todo `modifier.*` acepta `object?` (default activo) y responde
  `{object, modifiers}`. `modifier.add` incluye el nombre real asignado.
- Identidad de modifier: `(object, name)`, nunca nombre global ni índice.
- `modifier.add_options` describe parámetros con `type`, `default` y
  `min/max/step`, `values` o filtro de objeto según corresponda.
- Estado: `active.modifiers[]` y
  `hidden_objects:[{name,type}]` provenientes del view layer/H.
- `modifiers.changed {object,modifiers}`.
- `visibility.changed {hidden_objects}`.
- Respuestas hide/reveal incluyen ocultos y selección/activo resultante.
- Documentar `shared_data`, `unsupported_type`, `wrong_mode`, `not_found`,
  `bad_payload` y demás errores usados.
- Sincronizar `fixtures/v2/capabilities.json` exactamente con `protocol.py` y añadir
  fixtures Edit Vertex/Edge además de Face.

### Comandos

```text
modifier.add_options
modifier.add      object? type name?
modifier.remove   object? name
modifier.move     object? name index
modifier.set      object? name parameters{}
modifier.toggle   object? name viewport? render?
modifier.apply    object? name

object.hide       objects[]? unselected?
object.reveal     objects[]? select?
transform.apply   objects[]? location? rotation? scale?

tool.begin {tool:LOOP_CUT, parameters:{cuts,smoothness,factor}, edge?}
```

`object.hide/reveal` son solo Object Mode. Edit usa `selection.hide/reveal`.

## B1 — Estado y eventos

1. Serializar los cinco tipos de modifiers en `state.object_info()`.
2. `visible` usa `not obj.hide_get()`, no `hide_viewport`.
3. Enumerar ocultos del view layer aunque estén deseleccionados.
4. Añadir firmas ligeras de pila y ocultos al watcher.
5. Emitir eventos con datos completos; no un `context.changed` vacío de esa información.
6. Mantener `scene.get_state` y `scene.list_objects` coherentes con los eventos.

## B2 — Modifiers

Crear `commands/modifiers.py` e importarlo en `commands.load_all()`.

- Usar datablock API para add/set/toggle/move/remove.
- Validar tipos, rangos, enums y Boolean operand.
- Boolean: operand MESH distinto del activo; inexistente `not_found`; sí mismo o
  no-mesh `bad_payload`; sin operand es válido.
- `modifier.apply` es la excepción autorizada: usar
  `bpy.ops.object.modifier_apply(modifier=name)` con override seguro, restaurando
  selección/activo. No copiar el depsgraph completo porque aplicaría toda la pila.
- Probar que aplicar uno no aplica los posteriores.

## B3 — Ocultar objetos

- `object.hide`: selección/payload o `unselected` para Shift+H.
- `object.reveal` con lista revela esos nombres; sin lista recorre explícitamente todos
  los ocultos del view layer. No usar `resolve_objects()` como fallback.
- Usar `hide_set/hide_get`, nunca `hide_viewport`.
- Definir `select` (default contractual) y corregir activo si el ocultado lo invalida.
- En Edit devolver `wrong_mode`; no sacar de la vista el objeto en edición.

## B4 — Aplicar transformaciones

- `transform.apply` exige al menos un flag true.
- No es `transform.reset`: apply hornea; reset borra el transform sin hornear.
- Operar sobre transform local/matrix basis conservando parent e inverse, rotación y
  escala no uniforme. Añadir tests específicos antes de cerrar el diseño.
- Tipos sin datablock transformable devuelven `unsupported_type`; nunca resetear en
  silencio algo que no pudo hornearse.
- Decisión congelada para datos compartidos: fallar `shared_data` o hacer single-user;
  documentar una sola semántica y probarla.
- Un único undo y restauración correcta.

## B5 — Refactor de tools y Loop Cut

Antes de Loop Cut, separar operaciones BMesh puras de wrappers `mesh.*`: ninguna
preview puede hacer `undo_push`.

- Extraer `_edge_ring/_seed_edge` a helper de topología compartido.
- Guardar la edge semilla en la sesión y re-resolverla tras cada restore.
- Preview siempre desde backup BMesh.
- `cuts >= 1`, smoothness contractual y factor limitado a `[-1,1]`.
- Con varios cuts, factor desplaza el conjunto conservando espaciado sin cruzar bordes.
- Triángulo/anillo degenerado corta al menos la semilla.
- Confirm un undo; cancel topología idéntica y ningún undo.

## B6 — CLI, pruebas y entrega

Añadir CLI: modifier add/set/apply, loopcut, hide/reveal y apply transform.

Pruebas mínimas:

- catálogo y add/set/toggle/move/remove de cinco modifiers;
- depsgraph evaluado y Boolean real;
- aplicar solo el modifier nombrado;
- hide/reveal individual/todos/unselected + estado/eventos;
- apply T/R/S, parent, escala no uniforme, shared data, unsupported;
- Loop Cut begin/preview/parameter/nudge/cancel y begin/confirm/undo;
- payload inválido, wrong mode, empty selection y not found;
- contrato Android contra servidor real.

Cierre:

```bash
blender --background --python blender-backend/tests/run_tests.py
blender --python blender-backend/tests/run_gui_tests.py  # solo si toca contexto real
bash blender-backend/tools/build_addon.sh
```

No cambies el contrato después de que el agente Android empiece sin coordinarlo con el
agente principal.
