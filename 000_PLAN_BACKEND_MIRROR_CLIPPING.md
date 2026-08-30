# 000 · Backend · Clipping de Mirror no captura vértices vecinos

## Objetivo

Hacer que las transformaciones remotas respeten Mirror Clipping sin pegar al plano los
vértices que solo están cerca de la costura.

## Fases y cierre

- [x] Separar la detección de vértices ya situados en la costura del `merge_threshold`.
- [x] Conservar el bloqueo de la costura real y el impedimento de cruzar el plano.
- [x] Cubrir con pruebas un vértice contiguo situado dentro del umbral de merge.
- [x] Ejecutar la suite backend aplicable (809/809).

Pendiente: validación táctil con la malla real antes de retirar el plan.
