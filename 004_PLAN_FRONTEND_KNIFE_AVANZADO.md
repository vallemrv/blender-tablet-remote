# 004 — Android: Knife avanzado usable

## Objetivo

Ofrecer un flujo preciso de colocar puntos y construir varios cortes, sin que tocar
fije un inicio arbitrario ni obligue a una única polilínea.

## Criterios de cierre

- Pulsar, ajustar y soltar coloca un único punto en el candidato visible.
- Soltar confirma la última muestra estable, no el salto final de `ACTION_UP`.
- El overlay separa visualmente los trazos independientes.
- La bandeja ofrece «Nuevo corte», deshacer punto, cerrar, snap y contador claro.
- La bandeja permite forzar Auto/Vértice/Medio/Arista para evitar ambigüedad.
- Confirmar se habilita cuando existe al menos un segmento válido.
- Hay pruebas JVM del gesto y del estado multitrazo; `assembleDebug` pasa.
- APK enviada por Telegram, add-on reinstalado limpio y Blender reiniciado/verificado.
