# 003 · Frontend · Knife comprensible y menos agresivo

## Objetivo

Explicar dentro de la bandeja cómo se crea un corte y reducir el sondeo continuo sin
perder feedback visual.

## Fases y cierre

- [x] Mostrar una instrucción breve antes y después del primer tramo.
- [x] Reflejar que un único arrastre válido ya produce dos puntos.
- [x] Reducir la frecuencia de UPDATE de Knife para no saturar el pump/captura.
- [x] Cubrir las reglas de texto y frecuencia con pruebas JVM.
- [x] Ejecutar tests JVM y `assembleDebug` con JDK 17.

Pendiente: validar la comprensión del flujo y el trazo con dedo/stylus en tablet.
