# 001 — Backend: múltiples Loop Cut en una sesión

- Extender `tool.loop_pick` con `add` para fijar el preview y abrir otro corte.
- Mantener backup original para cancelar y bases acumuladas para previews sucesivas.
- Añadir `tool.loop_pop` para volver al corte anterior editable.
- Confirmar todos los cortes con un único undo; congelar contrato y pruebas.
