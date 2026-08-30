# 001 · Frontend · El radial no interrumpe transformaciones ni tools

## Objetivo

Impedir que una pulsación sostenida o un movimiento lento abra el menú radial mientras
una transformación o una herramienta paramétrica tiene una sesión activa.

## Fases y cierre

- [x] Publicar en la capa de entrada si la pulsación larga está habilitada.
- [x] No programar ni disparar el long-press durante sesiones transform/tool.
- [x] Conservar el radial cuando no hay ninguna sesión activa.
- [x] Cubrir la prioridad gestual con pruebas JVM.
- [x] Ejecutar tests JVM y `assembleDebug` con JDK 17.

Pendiente: validar en tablet movimientos lentos de transformaciones y tools.
