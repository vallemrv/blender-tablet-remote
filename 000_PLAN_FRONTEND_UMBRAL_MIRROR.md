# 000 · Frontend · Umbral de Mirror visible y ajustable

## Objetivo

Mostrar y ajustar `merge_threshold` con la precisión que anuncia el schema, sin
redondear `0.001` a `0` ni ocultar los pasos pequeños.

## Fases y cierre

- [x] Formatear los floats del inspector según el paso contractual.
- [x] Mantener los botones −/+ operativos en incrementos de `0.001` para Mirror.
- [x] Cubrir la presentación y el stepper con pruebas JVM.
- [x] Ejecutar tests JVM y `assembleDebug` con JDK 17.

Pendiente: validación táctil del inspector antes de retirar el plan.
