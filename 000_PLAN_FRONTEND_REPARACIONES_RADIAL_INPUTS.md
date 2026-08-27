# 000 — Android: reparaciones del radial y campos numéricos

**Estado: ejecutado. Propiedad exclusiva: `android-client/**`.**

## Feedback que abre el ciclo

Tras dar por concluido el ciclo anterior en tablet real, se reportaron tres defectos:
Caja no quedaba armada desde el menú circular, Borrar no era una acción directa y
fiable para Vértice/Arista/Cara, y el texto de los inputs numéricos de las bandejas de
propiedades no era visible.

## Criterios de cierre

- Caja y Círculo arman explícitamente `ShapeTool` desde el radial y el arrastre llega a
  `selection.box`/`selection.circle`; repetir el botón no desarma la herramienta.
- Edit muestra Borrar directamente cuando existe selección y envía `mesh.delete` con
  `VERTS`, `EDGES` o `FACES` según el submodo activo, sin superar ocho sectores.
- `DELETE` no se duplica dentro del submenú de `edit.catalog`.
- Los inputs numéricos de Transform y de las tools fijan texto claro en el propio
  `TextStyle`, además de sus colores Material3.
- Tests JVM y `assembleDebug` terminan correctamente.

Todos los criterios están implementados y verificados. Queda la validación habitual en
tablet real como feedback de uso, no como trabajo de código pendiente.
