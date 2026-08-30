# 000 — Android: precisión XYZ y referencia REL en Mover

## Objetivo

Entregar en Object Mode una bandeja de Mover apta para lápiz y posicionamiento
exacto, construida sobre controles que puedan reutilizar Rotar y Escalar.

## Alcance

- Conservar los botones X/Y/Z y el arrastre normal del lápiz.
- Sustituir el único valor por tres campos X/Y/Z, cada uno con − y +.
- Usar esos campos como lectura viva durante el gesto, con identidad de color por eje,
  sin duplicar una segunda leyenda XYZ y sin sobrescribir el campo que se está editando.
- Integrar X/Y/Z como labels pulsables de sus propios inputs y ordenar la bandeja como
  XYZ/incremento → REL → Snap → Global/Local/Vista.
- Añadir campo de incremento con −/+ y selector `mm | cm | m | %`.
- En Move, `%` mide una fracción de la distancia pivote→referencia REL y queda
  deshabilitado hasta que exista esa referencia.
- Retirar Rejilla y Cursor del selector de snap de Move.
- Ofrecer únicamente los destinos exactos Vértice, Punto medio y Centro de cara.
- Añadir botón REL: armado, seguimiento bajo el lápiz, bloqueo al levantar y limpiar.
- Reutilizar los marcadores existentes para vértice, arista y cara.
- Dibujar el ancla REL verde mientras se sondea, roja al fijarla y reproyectada durante
  todo el viaje del objeto; el destino de snap permanece visible a la vez.
- Mantener confirmar/descartar fijos y la bandeja desplazable.
- Añadir pruebas JVM de modelos, parseo y política de unidades.

## Criterios de cierre

- Los tres valores se pueden editar y escalonar por separado sin perder los otros.
- Cambiar incremento o unidad actualiza el paso enviado sin alterar el preview.
- REL no interfiere con el arrastre normal cuando está desarmado.
- Mientras REL está armado el lápiz solo sondea; al levantar bloquea la referencia.
- `assembleDebug` y pruebas JVM quedan verdes.
- Validación táctil real queda como criterio de aceptación del usuario antes de
  retirar estos planes.
