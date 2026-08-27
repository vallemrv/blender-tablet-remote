# 000 — Android: reparaciones del radial y campos numéricos

**Estado: ejecutado. Propiedad exclusiva: `android-client/**`.**

## Feedback que abre el ciclo

Tras dar por concluido el ciclo anterior en tablet real, se reportaron tres defectos:
Caja no quedaba armada desde el menú circular, Borrar no era una acción directa y
fiable para Vértice/Arista/Cara, y el texto de los inputs numéricos de las bandejas de
propiedades no era visible.

## Criterios de cierre

- El radial usa un único hit-test geométrico en su contenedor; el fondo de cierre no
  compite con nodos desplazados. Caja y Círculo arman explícitamente `ShapeTool` y el
  arrastre llega a `selection.box`/`selection.circle`.
- `QuickAction.onClick` es el último parámetro funcional para que la trailing lambda de
  Kotlin se conecte al tap. Se cubre con una regresión que ejecuta el callback y fija
  `onLongClick == null`; el orden anterior dejaba el tap vacío en todas las acciones
  construidas como `QuickAction(...) { acción() }`.
- Edit muestra Borrar directamente cuando existe selección y envía `mesh.delete` con
  `VERTS`, `EDGES` o `FACES` según el submodo activo, sin superar ocho sectores.
- `DELETE` no se duplica dentro del submenú de `edit.catalog`.
- Los inputs numéricos de Transform y tools usan `CompactNumericField` de 34 dp; no
  dependen del mínimo de 56 dp de Material3 `TextField`, que recortaba el texto dentro
  de las bandejas horizontales.
- Knife y Bisect rechazan `tool.nudge` tanto en el enrutado del ViewModel como en la
  frontera WebSocket; sus taps/líneas y la navegación independiente siguen intactos.
- Tests JVM y `assembleDebug` terminan correctamente.

Todos los criterios están implementados y verificados. Queda la validación habitual en
tablet real como feedback de uso, no como trabajo de código pendiente.
