# 004 — Backend: Knife avanzado multitrazo

## Objetivo

Permitir construcción topológica táctil con varios trazos independientes dentro de
una sola sesión atómica de Knife, incluido el patrón de conexiones 4→2.

## Criterios de cierre

- Cada liberación fija exactamente un punto; el primer contacto no muta la malla.
- Snap táctil pegajoso y prioritario para vértice, centro de arista y arista.
- La prioridad es categórica VERTEX > EDGE_CENTER > EDGE y cubre caras vecinas.
- AUTO usa radios de prioridad reducidos; los modos Vértice/Medio conservan radios grandes.
- `tool.knife_new_stroke` termina el trazo actual y permite empezar otro sin confirmar.
- Preview, error, cancelar y confirmar abarcan todos los trazos como una operación.
- El trazo activo solo altera overlay; «Nuevo corte» crea preview para snap posterior.
- Un único Undo elimina Knife y conserva Edit Mode.
- Los candidatos pertenecen a la cara visible y admiten filtro explícito de destino.
- Deshacer elimina un punto y puede volver al trazo anterior.
- Estado y contrato publican trazos y proyecciones sin romper clientes v2 antiguos.
- Pruebas headless, contrato y prueba viva OFFSCREEN pasan sin crash.
