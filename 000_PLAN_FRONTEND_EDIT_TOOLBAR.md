# 000 — Android: barra izquierda de tools activas en Edit

**Estado: activo. Propiedad exclusiva: `android-client/**`.** Depende del contrato
backend `000`; Android no inventa familias, variantes ni parámetros wire.

## Feedback que abre el ciclo

La barra izquierda de Edit debe entrar en modo herramienta activa y contener, con la
lógica agrupada de Blender, Extrude, Inset, Loop Cut y Cut (Knife/Bisect). En Extrude se
necesitan distancia, bloqueo de ejes y modos Region/Along Normals/Individual. Además,
Rotate y Scale responden al revés al arrastre horizontal en Object y Edit, mientras la
navegación de cámara ya se siente correcta.

## F0 — Modelos y parser

- Parsear `edit_toolbar` de forma tolerante a campos y variantes futuras.
- Modelar familia, variante, default, input, requisitos, parámetros y estado armado.
- Orden, disponibilidad y defaults vienen del servidor.
- Sin la feature nueva, conservar el rail y `edit_catalog` legacy actuales.
- Tests de campos futuros, catálogo vacío, requisitos por submodo y servidor antiguo.

## F1 — Barra izquierda en Edit Mode

- Mostrar las familias contractuales en este orden: Extrude, Inset, Loop Cut y Cut.
- Tap activa la variante recordada o el default del servidor.
- Pulsación larga abre un selector compacto anclado al botón y cambia variante sin
  confirmar la sesión anterior.
- El botón refleja icono/etiqueta de la variante activa y permanece marcado mientras la
  herramienta está armada o tiene sesión.
- Seleccionar/Mover/Rotar/Escalar siguen en el rail; la bandeja inferior solo contiene
  parámetros de la tool activa y Descartar/Confirmar.
- Retirar duplicidades de Knife y de estas familias en footer/menú cuando
  `edit_toolbar` esté disponible; conservarlas únicamente en fallback legacy.

## F2 — Extrude e Inset

- Extrude ofrece Región, A lo largo de normales e Individual.
- Región muestra Distancia, Libre/X/Y/Z y Global/Local/Vista.
- Along Normals e Individual muestran solo los controles aplicables anunciados.
- Inset ofrece Región e Individual y muestra thickness/depth según esquema.
- Cambio de variante, eje u orientación conserva la herramienta activa y no acumula
  geometría.

## F3 — Loop Cut

- Al activar Loop Cut, el siguiente toque en viewport coloca el corte; con sesión
  abierta, nuevos toques lo recolocan.
- Conservar cortes, posición, suavidad, perfil, uniforme, invertir y fijar.
- El arrastre por viewport ajusta el factor sin competir con navegación a dos dedos.

## F4 — Cut: Knife/Bisect

- Cut agrupa Knife y Bisect bajo un único slot con selector por pulsación larga.
- Knife conserva puntos por tap, overlay, pop, close, snap y círculo de órbita.
- Bisect captura un arrastre de línea completo en `InputSurface` y envía inicio/fin
  normalizados al soltar.
- La bandeja Bisect muestra clear inner, clear outer, fill, cancelar y confirmar.
- Prioridad de entrada: dos dedos > círculo de órbita > tool activa > selección/menú.

## F5 — Snap funcional en la barra de propiedades

- Auditar Move/Rotate/Scale y cada tool: todo selector de Snap visible debe enviar el
  tipo/estado correcto, actualizarse con la respuesta y producir una preview distinta.
- Mostrar solo los tipos anunciados y realmente aplicables a la operación actual.
- Transformaciones: incremento, rejilla y candidatos Vertex/Edge/Face en Object/Edit;
  Rotate/Scale muestran únicamente los modos que el backend pueda aplicar.
- Tools: Extrude, Loop Cut, Knife y Bisect presentan su snap contractual, sin reutilizar
  controles genéricos que el backend ignore. Inset no muestra Snap si no tiene efecto.
- El candidato bloqueado se representa claramente y se puede liberar/cambiar sin cerrar
  la sesión.
- Tests de payload y reconciliación, más pruebas donde el mismo arrastre con Snap
  apagado/encendido arroja valores efectivos diferentes.

## F6 — Rotate/Scale horizontal

- Añadir pruebas de la traducción gesto→payload para Object y Edit.
- Corregir el signo horizontal compartido de Rotate y Scale.
- No cambiar Move ni ningún gesto de cámara.

## F7 — Superficies, accesibilidad y cierre

- Actualizar `ActionSurface` y `SurfaceCatalogTest`: cada ejecución visible vive en una
  sola superficie cuando la feature nueva está presente.
- Objetivos táctiles amplios, rail desplazable y popup dentro de pantalla.
- Tests JVM de tap/long-click, variante recordada, cancelación, payload y conflictos de
  punteros; `assembleDebug` correcto.
- Smoke físico con dedo y Lenovo Pen, incluyendo Snap real, cambio rápido entre
  Cut/transformación y navegación a dos dedos.

No se cierra ni se borra este plan mientras falte alguno de estos criterios.
