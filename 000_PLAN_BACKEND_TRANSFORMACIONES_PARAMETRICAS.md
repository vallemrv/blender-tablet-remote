# 000 — Backend: base paramétrica de transformaciones

## Objetivo

Crear una base común para transformaciones exactas y entregar su primera aplicación
en `MOVE` de Object Mode: valores XYZ, incremento configurable y una referencia
geométrica independiente del pivote.

## Alcance

- Retirar `GRID` y `CURSOR` del contrato de snap de transformaciones modales.
- Mantener `INCREMENT` y los destinos geométricos de Move.
- Añadir una referencia REL reversible que se ancla a la selección y viaja con ella.
- Usar esa ancla como origen del snap geométrico: destino menos ancla, excluyendo del
  sondeo los objetos móviles para permitir vértice contra vértice entre objetos.
- Permitir que el incremento se ancle a la referencia, sin acumulación numérica.
- Hacer más tolerante el sondeo geométrico usado durante el movimiento con lápiz.
- Publicar candidato, referencia y origen de valores en `transform.session`.
- Actualizar capabilities, protocolo, fixtures y pruebas.

## Criterios de cierre

- Elegir una referencia no desplaza el objeto.
- Bloquearla no mueve la selección; después, el snap alinea el ancla con el destino
  y los valores XYZ siguen representando el desplazamiento exacto aplicado.
- Cancelar restaura exactamente las matrices originales y confirmar crea un undo.
- Los snaps `GRID` y `CURSOR` son rechazados por `transform.begin/snap` y no se
  anuncian como disponibles para la transformación.
- Pruebas backend, GUI aplicable y contrato en verde contra el ZIP instalado.
