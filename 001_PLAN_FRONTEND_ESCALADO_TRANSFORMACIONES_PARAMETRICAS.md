# 001 — Android: bandejas paramétricas para Object y Edit

## Objetivo

Extender la interacción validada de Mover a Mover, Rotar y Escalar en Object Mode y
Edit Mode, conservando una bandeja compacta, lectura viva, lápiz directo y precisión
CAD sin crear una interfaz distinta para cada contexto.

## Principios de interacción

- Una misma composición visual sirve a Object/Edit; capabilities deciden qué controles
  están disponibles, no condicionales ocultos por pantalla.
- Los inputs son también la leyenda viva X/Y/Z. Mientras se edita uno, las respuestas
  remotas no pisan el texto; al confirmar vuelve a reconciliarse con el servidor.
- El lápiz conserva el gesto natural. Los controles paramétricos afinan o sustituyen el
  gesto sin cerrar la sesión.
- Verde significa candidato; rojo significa referencia fijada; el destino mantiene una
  identidad visual distinta. El marcador fijado nunca salta al levantar el lápiz.
- Centro, fuente y destino no se presentan como un único botón ambiguo. La UI muestra
  solo los roles que el modo necesita y explica el siguiente toque.

## Controles por transformación

### Mover

- Conservar XYZ de distancia, incremento `mm | cm | m | %`, REL source, snap exacto y
  orientación GLOBAL/LOCAL/VIEW tal como fue validado en `000`.

### Rotar

- Inputs X/Y/Z angulares como lectura viva; selector `° | rad` para entrada y un
  incremento angular independiente.
- Restricción por eje y orientación GLOBAL/LOCAL/VIEW.
- REL elige el centro geométrico alternativo. Cuando se activa snap a destino, la UI
  guía la elección del asa fuente y después del target; el overlay dibuja centro, arco
  y ángulo resultante.

### Escalar

- Inputs X/Y/Z de factor, con modo uniforme accesible y visualmente inequívoco.
- Entrada en factor o `%`; el incremento se expresa en la misma unidad de presentación.
- REL elige el centro geométrico alternativo. El snap guiado muestra source y target y
  publica el factor resuelto antes de fijarlo.
- Los factores negativos requieren entrada explícita; los steppers no cruzan cero por
  accidente.

## Edit Mode

- Reutilizar las mismas bandejas y orden. El cambio de Object a Edit no altera memoria
  de unidad/incremento salvo que el backend anuncie incompatibilidad.
- Mostrar edición proporcional y su radio/perfil junto a las transformaciones que la
  soportan; Auto Merge permanece exclusivo de MOVE.
- Los marcadores distinguen geometría seleccionada móvil de destino inmóvil, incluso
  dentro del mismo objeto.
- Si la selección o topología invalida la sesión, cerrar la bandeja con un aviso breve
  y sin dejar controles aparentemente activos.

## Orden y economía de espacio

- Mantener: grupo de inputs → REL/referencias → Snap → orientación → descartar/confirmar.
- La franja central continúa desplazable; descartar y confirmar permanecen fijos.
- No reintroducir la antigua leyenda XYZ separada ni botones X/Y/Z duplicados.
- Los estados guiados de referencia usan texto corto contextual: `Centro`, `Fuente`,
  `Destino`; no añaden paneles permanentes.

## Estado y red

- Renderizar exclusivamente el estado confirmado por `transform.session`; el estado
  local solo conserva texto en edición y preferencias de presentación.
- Coalescer hover y nudge latest-wins, pero nunca descartar el comando que fija el
  candidato visible.
- Al recibir status, reconciliar por `session_id` para que una respuesta tardía de una
  sesión anterior no mueva marcadores ni valores de la nueva.
- Mantener H.264/Compose fuera del camino de alta frecuencia del stylus.

## Pruebas obligatorias

- JVM para unidades, formato, steppers, reconciliación de inputs y máquina de estados
  Centro→Fuente→Destino.
- Compose/semántica para orden, controles visibles por modo y accesibilidad táctil.
- Secuencias de red con respuestas tardías, candidato hover seguido de lock y dos o más
  movimientos/rotaciones/escalados sin confirmar.
- `testDebugUnitTest` y `assembleDebug` en verde.
- Matriz táctil real en tablet: Object/Edit × MOVE/ROTATE/SCALE, valores, steppers,
  gesto, REL, snap, cámara con dos dedos y confirmar/cancelar.

## Criterios de cierre

- Las seis combinaciones principales son utilizables con el mismo lenguaje visual y
  sin controles duplicados.
- Los inputs siempre coinciden con el preview visible, también tras varias operaciones
  dentro de una sesión.
- El flujo de referencias se entiende sin conocer pivotes de Blender y ningún marcador
  cambia de lugar al fijarlo.
- El usuario valida cada modo en Object y Edit con lápiz antes de retirar el plan.
