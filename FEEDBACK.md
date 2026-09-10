# Feedback de pruebas — Blender Tablet Remote

Registro vivo de bugs y mejoras detectados al probar la app en tablet contra el backend de Blender.
Se va rellenando conforme se prueba. Formato de cada entrada:

`- [ ] Descripción del problema/mejora. (fecha, contexto si aplica)`

Estados de cada línea (no se borran las líneas, así queda historial de qué se pidió y cuándo):
- `- [ ]` — pendiente, nadie lo ha tocado todavía.
- `- [ ] 🔧 en revisión (Codex, dd-mm)` — se ha intentado arreglar/implementar, pero falta
  que el usuario lo pruebe en la tablet. No pasa a `[x]` hasta que se confirme.
- `- [x] (verificado dd-mm)` — probado en la tablet y confirmado que funciona.
- Si al probar sigue fallando: volver a `- [ ]` y añadir `(reabierto dd-mm: qué sigue mal)`.

Los hallazgos nuevos se añaden como bullets nuevos en la sección/modo/herramienta que
corresponda, sin marca especial.

---

## Object Mode

### Bugs
- [ ]

### Mejoras / estética / refinamientos
- [ ]

---

## Edit Mode

### Bugs generales
- [ ]

### Bugs por herramienta
- **Extrude**
  - [ ]
- **Bevel**
  - [ ]
- **Inset**
  - [ ]
- **Subdivide**
  - [ ]
- **Loop Cut**
  - [ ]
- **Knife**
  - [ ]
- **Bisect**
  - [ ]
- **Bridge Edge Loops**
  - [ ]
- **Align**
  - [ ]

### Mejoras / estética / refinamientos generales
- [ ]

### Mejoras / estética / refinamientos por herramienta
- [ ]

---

## Sculpt Mode

### Bugs generales
- [ ]

### Bugs por brocha/herramienta
- [ ]

### Mejoras / estética / refinamientos generales
- [ ]

### Mejoras / estética / refinamientos por brocha/herramienta
- [ ]

---

## Materiales / Texturas (modo pintura de materiales)

### Bugs generales
- [ ] 🔧 en revisión (Codex, 10-09) — Rendimiento: el modo de materiales va con mucho lag, igual que le pasaba a Sculpt.
      Revisar si es la misma causa que ya se diagnosticó/resolvió allí (cola de vídeo H.264,
      depsgraph desactualizado) o si es un cuello de botella propio de
      `materials/painting.py` (la pintura procesa el trazo punto a punto sobre píxeles del
      atlas). Tiene que ir fluido para pintar con el lápiz en tiempo real.
- [ ] 🔧 en revisión (Codex, 10-09) — Confirmado en código (`commands/material.py:41`): al cambiar el preset de material
      (p. ej. de "Plástico" a "Hierro") el tinte/color personalizado se resetea al color por
      defecto del preset nuevo, porque `MaterialWorkspace.kt` solo envía `preset` sin
      `color` y el backend interpreta la ausencia de `color` en el payload como "usa el
      color de ese preset". Efecto: no se puede tener una "bola metalizada roja" (preset
      Hierro + tinte rojo) sin perder el rojo en cuanto se toca el selector de material. El
      tinte debe conservarse al cambiar de preset salvo que también se cambie el color en el
      mismo gesto.

### Mejoras / estética / refinamientos generales
- [ ] 🔧 en revisión (Codex, 10-09) — Falta una forma de pintar detalles localizados distintos de la base (p. ej. pinceladas
      de óxido sobre una bola metalizada). Hoy solo hay presets de "material completo"
      (Plástico, Hierro, Madera...) pensados para aplicarse a todo el objeto o pintarse con
      el mismo preset activo. Sería útil tener presets pensados para detalle/desgaste
      (óxido, suciedad, arañazos) diseñados para pintarse en capas sobre una base ya
      aplicada, sin sustituirla.
- [ ] 🔧 en revisión (Codex, 10-09) — Pensar la experiencia como un ayudante para gente sin experiencia en shading (el caso
      del usuario): guiar el flujo base → tinte → acabado → detalle, y dejar claro en la UI
      que el tinte es independiente del preset elegido (para evitar el bug de arriba y la
      sensación de "perder el preset").

### Mejoras / estética / refinamientos por herramienta
- [ ]

---

## CAD (workspace paramétrico)

> Estado inicial comunicado (10-09-2026): muy verde, aún no se había podido completar ninguna pieza. Faltaban
> restricciones y herramientas básicas de sketch para que sea usable. Revisar esta lista
> según se vaya pudiendo avanzar, seguramente faltan más restricciones que las aquí listadas.

### Bugs generales
- [ ] 🔧 en revisión (Codex, 10-09) — Al editar un boceto, se puede rotar libremente el viewport (orbit). Debería quedar
      bloqueado en vista ortogonal al plano del boceto mientras se está editando, como en
      cualquier CAD paramétrico (FreeCAD, SolidWorks, Fusion).
- [ ] 🔧 en revisión (Codex, 10-09) — Falta un punto fijo en el origen de coordenadas (0,0) del boceto contra el que se
      pueda restringir (simetría, coincidente, etc.). Sin origen de referencia no hay forma
      fiable de anclar el boceto en el espacio.
- [ ] 🔧 en revisión (Codex, 10-09) — Faltan cotas (dimensiones) que muestren la medida de cada restricción aplicada. Sin
      esto no se puede saber qué tamaño/posición tiene realmente el boceto mientras se edita.
- [ ] 🔧 en revisión (Codex, 10-09) — La restricción de "fijar" (candado) sobre un punto o arista actualmente parece afectar
      a todo el boceto en vez de restringir solo el/los elemento(s) seleccionado(s). Debe
      limitarse estrictamente a la selección.
- [ ] 🔧 en revisión (Codex, 10-09) — Historial/pila de bocetos y restricciones: al entrar a editar un boceto no aparecía (o
      no se veía claramente). Ha terminado apareciendo pero la presentación es confusa/lioso
      de leer — revisar diseño de esa pila.

### Bugs por herramienta / restricción
- **Fillet**
  - [ ] 🔧 en revisión (Codex, 10-09) — No existe todavía (herramienta imprescindible de uso habitual en diseño).
- **Geometría de construcción**
  - [ ] 🔧 en revisión (Codex, 10-09) — No existe todavía (imprescindible para poder apoyar restricciones sin que la
        geometría de construcción forme parte del perfil final).
- **Restricciones**
  - [ ] 🔧 en revisión (Codex, 10-09) — Falta restricción de punto medio / centro de arista.
  - [ ] Pendiente de revisar qué otras restricciones faltan — bloqueado hasta poder avanzar
        más en una pieza real de prueba.
- **Convertir a malla ("crear malla")**
  - [ ] 🔧 en revisión (Codex, 10-09) — Al pulsar crear malla se pierde el modelo paramétrico CAD (el árbol de bocetos y
        operaciones). Debe conservarse el modelo CAD y solo generarse/mostrarse la malla
        resultante como representación, sin destruir el histórico paramétrico — para poder
        seguir viendo y editando en modo CAD después.
- **Planos**
  - [ ] 🔧 en revisión (Codex, 10-09) — No existe sistema de planos: falta poder elegir un plano de boceto ya existente o una
        cara plana del objeto como referencia para un nuevo boceto.
  - [ ] 🔧 en revisión (Codex, 10-09) — Falta poder crear planos nuevos y posicionarlos/orientarlos respecto al objeto
        (offset, ángulo), necesario para hacer perforaciones u operaciones sobre formas
        curvas donde no vale ninguno de los planos base.
- **Bocetos (gestión)**
  - [ ] 🔧 en revisión (Codex, 10-09) — Falta poder crear más de un boceto en la misma pieza.
  - [ ] 🔧 en revisión (Codex, 10-09) — Falta poder ocultar/mostrar bocetos ya creados.
- **Cuerpos / Piezas (multi-body)**
  - [ ] 🔧 en revisión (Codex, 10-09) — Falta poder crear piezas/cuerpos distintos dentro del mismo diseño (p. ej. un cuerpo
        principal + piezas adicionales), como en un CAD paramétrico multi-body habitual.

### Mejoras / estética / refinamientos generales
- [ ] 🔧 en revisión (Codex, 10-09) — Unificar la bandeja inferior CAD: Paso y
      dimensiones con −/+ y repetición acelerada, campos compactos como Edit y
      cancelar/aceptar fijos a la derecha con los mismos iconos rojo/verde.

- [ ] 🔧 en revisión (Codex, 10-09) — La malla generada por extrude/vaciado (`cad/kernel.py`) sale con topología sucia
      (n-gons/triángulos sueltos) porque depende del resultado bruto del booleano de
      Blender. Construir las caras de forma ordenada (quads siguiendo el perímetro del
      sketch, como haría el módulo Part de FreeCAD) para no tener que retopologizar a mano
      después y poder usar directamente las tools de Edit Mode sobre el resultado.
- [ ] 🔧 en revisión (Codex, 10-09) — Panel de historial de restricciones con comportamiento contextual:
  - Sin nada seleccionado: mostrar todo el historial de bocetos y restricciones (como ahora).
  - Con un punto/arista seleccionado: mostrar solo las restricciones asociadas a ese
    elemento (quizás en un riel/panel aparte), y no mostrar nada si el elemento no tiene
    ninguna restricción.

### Mejoras / estética / refinamientos por herramienta
- [ ]

---

## Transversal (streaming, conexión, UI general, no ligado a un modo)

### Bugs
- [ ] 🔧 en revisión (Codex, 10-09) — Si la app en la tablet pierde el foco (p. ej. al consultar una referencia en otra app)
      y luego lo recupera, el modo vuelve a Object en vez de mantener el modo/estado en el
      que estaba (p. ej. editando un boceto en CAD). Obliga a re-entrar a edición de boceto
      y volver a activar CAD cada vez. Sería deseable congelar el estado (en el server o
      donde sea más eficiente) y restaurarlo al recuperar el foco.

### Mejoras / estética / refinamientos
- [ ]


---

## Resolución y verificación (10-09-2026)

Las entradas «🔧 en revisión» tienen implementación y comprobación automatizada.
La sensación del lápiz y la disposición en la tablet física quedan por probar; no
había una tablet ni un emulador conectado en esta sesión.

- **Materiales:** tinte y acabado independientes del preset; selector de detalles
  Óxido/Suciedad/Arañazos y guía Base → Tinte → Acabado → Detalle. Atlas reutilizado,
  proyección por trazo e índice de teselas; profundidad reutilizada con geometría y
  cámara idénticas. En 262 144 texeles y 128 aplicaciones: 17,3 ms de pintura frente
  a 339,1 ms del recorrido completo, con máscara equivalente. No mide la latencia
  completa de red, vídeo y tablet.
- **Bocetos:** orientación ortogonal bloqueada con pan/zoom disponibles, origen fijo
  seleccionable, punto medio y simetría, fijación estricta por punto/arista y selección
  múltiple. Construcción discontinua excluida de perfiles y cotas visibles. El panel
  presenta restricciones y referencias por selección; sin asociaciones no abre un
  panel vacío. Los bocetos tienen su propio control de visibilidad.
- **Redondeo:** el de dos líneas ya existía; se hace explícito en la bandeja y ahora
  admite esquinas de rectángulos, conservando restricciones y operaciones del perfil.
- **Planos y cuerpos:** selector de planos existentes/de otro boceto, cara plana
  visible, planos desplazados/inclinados y cuerpos independientes con varios bocetos.
  Las caras arbitrarias guardan su marco capturado; la cara superior y las referencias
  a bocetos sí siguen al soporte. No se guardan índices inestables de polígonos.
- **Malla:** crear copia conserva el modelo CAD y todos sus dependientes. Extrusiones
  y vaciados materializan quads conectados sin realimentar esa subdivisión al kernel.
  Se verifica volumen/manifold y una cadena de tres vaciados sin crecimiento exponencial.
- **Segundo plano:** identidad privada Android y recuperación del workspace/cámara/
  boceto tras perder el socket. Los gestos interrumpidos se cancelan; no se reproducen.
  Verificado también mediante conexiones WebSocket reales sucesivas.

La entrada pendiente sobre «qué otras restricciones faltan» no identifica una
restricción adicional concreta. Se conserva abierta para los próximos hallazgos
de la pieza de prueba, ahora que las herramientas anteriores están disponibles.

Pruebas: `test_materials.py`, `test_materials_viewport.py`,
`test_materials_network.py`, `test_cad_feedback.py`, `test_cad_sketch.py`,
`test_capture_deadline.py`, pruebas H.264, contrato CAD y suite unitaria Android.
APK y ZIP deben instalarse juntos porque se ha ampliado el contrato.
