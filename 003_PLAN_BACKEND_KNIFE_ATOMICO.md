# 003 · Backend · Knife atómico y primer trazo directo

## Objetivo

Evitar que un error geométrico deje el BMesh parcialmente mutado antes de la captura
OFFSCREEN y hacer que el primer arrastre cree un tramo completo inicio→final.

## Fases y cierre

- [x] Restaurar el backup ante cualquier fallo de preview de Knife.
- [x] Revertir también las anclas tentativas que no produzcan una preview válida.
- [x] Hacer que BEGIN→END inicial añada inicio y final en una sola operación.
- [x] Cubrir éxito, fallo atómico y cancelación con pruebas backend.
- [x] Reproducir con captura OFFSCREEN y ejecutar suites aplicables.

Resultado: 811/811 headless. Prueba viva con OFFSCREEN/H.264 y 120 UPDATE consecutivos:
primer trazo con dos puntos, cancelación limpia, proceso y puertos operativos. La suite
GUI general se detuvo antes de Knife por fallos preexistentes de estado/transformación.

Pendiente: validación táctil sobre la malla real.
