# 002 · Frontend · Tweak sin círculo de órbita

## Objetivo

No mostrar el círculo derecho de navegación durante Tweak, que es una herramienta de
gesto directo y ya conserva la navegación con dos dedos.

## Fases y cierre

- [x] Excluir Tweak de la regla de visibilidad del círculo de órbita.
- [x] Mantener el círculo para las demás sesiones transform/tool.
- [x] Cubrir la decisión con pruebas JVM.
- [x] Ejecutar tests JVM y `assembleDebug` con JDK 17.

Pendiente: validar Tweak con dedo y stylus en tablet.
