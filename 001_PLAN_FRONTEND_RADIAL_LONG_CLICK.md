# 001 — Android: restaurar el menú radial circular de long-click

**Estado: activo. Propiedad exclusiva: `android-client/**`.**

## Feedback que abre el plan

El long-click debe volver a mostrar el menú circular de iconos tanto en Object Mode
como en Edit Mode. La presentación rectangular actual de Object resulta menos elegante
y varias acciones visibles no producen ningún efecto. El cierre exige apariencia radial
primitiva, handlers reales y verificación de cada acción contra su endpoint.

## F0 — Inventario ejecutable antes de rediseñar

- Inventariar por modo y contexto cada `ActionId` visible en long-click.
- Construir una tabla comprobable `ActionId → handler MainViewModel → método de
  RemoteBlenderClient → comando wire/endpoint`.
- Distinguir acciones locales de UI, comandos discretos, sesiones y navegación a un
  submenú; ninguna entrada puede terminar en un `when` vacío o callback nulo.
- Si falta un comando backend, ocultar la acción y documentar el hueco al agente
  principal; Android no inventa endpoints.
- Añadir test que falle si una acción radial visible no tiene handler ejecutable.

## F1 — Un único radial para Object y Edit

- Sustituir `ContextSheet` rectangular de Object Mode por el compositor circular de
  `QuickMenu`, compartiendo geometría, hit testing, cierre y animación.
- Mantener contenido contextual distinto por modo, selección y resultado del probe.
- Long-click primero sondea el punto y después abre el radial anclado allí.
- La X central/cierre, toque fuera y botón Back cierran sin ejecutar acciones.
- Conservar como máximo ocho sectores por anillo; los catálogos amplios usan subanillos
  o páginas, nunca una lista rectangular superpuesta.

## F2 — Apariencia circular de iconos

- Recuperar la apariencia primitiva: iconos grandes distribuidos en círculo, fondo de
  sector discreto, centro despejado y etiqueta corta asociada al sector enfocado.
- Usar iconos existentes del sistema visual; no introducir botones de escritorio
  diminutos ni texto largo dentro del anillo.
- Mantener objetivos táctiles amplios para dedo y Lenovo Pen.
- Reposicionar o comprimir el anillo cerca de bordes para que ningún sector quede fuera
  del viewport.
- Estado deshabilitado visible solo cuando aporta contexto; ocultar capacidades no
  anunciadas por el backend.

## F3 — Object Mode

- Contexto sobre objeto: selección, transformaciones/aplicar, duplicar, borrar, ocultar
  y demás acciones aprobadas por `SurfaceCatalog`, cada una conectada a su handler real.
- Contexto vacío: selección por caja/círculo y `Agregar` como entrada a subanillos por
  categoría y primitiva.
- Agregar conserva el catálogo anunciado por `object.add_options`; no se hardcodean
  primitivas ni se devuelve al menú rectangular.
- El objeto sondeado y el objeto activo/seleccionado se reconcilian antes de ejecutar
  una operación contextual.

## F4 — Edit Mode

- Conservar el radial contextual por Vértice/Arista/Cara y las acciones frecuentes
  permitidas por el catálogo backend.
- Caja y Círculo arman correctamente la herramienta de selección y cierran el radial.
- Ocultar/revelar geometría, borrar, separar, split, normales y demás entradas visibles
  ejecutan el comando o sesión contractual correspondiente.
- Las tools cuya propiedad pase al rail de `000` no se duplican en el radial cuando
  `edit_toolbar` esté disponible; el servidor legacy conserva el fallback.

## F5 — Entrada y conflictos

- Toda detección permanece en `InputSurface`; el radial pinta y hace hit test sin crear
  otra capa receptora competidora.
- Diferenciar tap, drag, long-click, stylus y navegación a dos dedos sin disparos dobles.
- Abrir/cerrar el radial cancela únicamente el gesto contextual, nunca confirma una
  transformación o tool activa.
- Prioridad durante sesión: dos dedos/círculo de órbita > tool activa; el long-click
  radial solo se arma donde el estado lo permita.

## F6 — Pruebas y cierre

- Tests de layout circular, ocho sectores, bordes, subanillos y coordenadas de hit.
- Tests de Object vacío/objeto, Edit Vértice/Arista/Cara y servidor legacy/nuevo.
- Test parametrizado de todas las acciones visibles: una pulsación produce exactamente
  un handler/comando esperado o una navegación de subanillo.
- Verificar cero duplicidades en `SurfaceCatalogTest` junto al plan `000`.
- JVM y `assembleDebug` en verde.
- Smoke físico con dedo y Lenovo Pen: cada icono visible se pulsa y produce efecto real.

No se cierra ni se borra este plan mientras quede una acción visible sin efecto o una
ruta de Object/Edit que vuelva al menú rectangular.
