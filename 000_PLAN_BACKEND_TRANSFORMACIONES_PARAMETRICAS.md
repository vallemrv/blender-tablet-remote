# 000 — Backend: base paramétrica de transformaciones

## Estado

Funcionalmente aceptado por el usuario en tablet el 2026-08-30, incluida la secuencia
de varios movimientos sin confirmar seguida de REL y snap vértice→vértice. Backend
832/832 y ZIP validados. La última repetición de la suite GUI queda registrada como no
concluida porque Blender sufrió el segfault gráfico previo antes de alcanzar este caso;
la misma suite había quedado 104/104 antes de los dos ajustes finales, que son internos
al estado de la sesión y tienen cobertura headless específica.

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
- Limitar el snap exacto de Move a Vértice/Punto medio/Centro de cara, con radios
  táctiles respectivos 0,080/0,070/0,065 en fuente y destino.
- Al fijar REL, congelar el último candidato verde sin repetir el raycast con ACTION_UP.
- Si REL se fija tras uno o más movimientos de la misma sesión, convertir el punto
  visible a la base original para no aplicar dos veces el desplazamiento acumulado.
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

## Problemas encontrados y solución estable

- Un segundo raycast en `ACTION_UP` podía sustituir el punto verde por otro destino
  exacto distante. Fijar REL congela el último candidato visible.
- El raycast observa la geometría ya desplazada, mientras la sesión reconstruye desde
  las matrices/BMesh originales. Guardar directamente ese punto duplicaba el primer
  movimiento. La referencia persistente debe almacenarse en la base original:
  `P_base = P_visible - delta_actual`; el estado publica después
  `P_visible = P_base + delta_actual`.
- El objeto o los elementos móviles nunca pueden ser candidatos de destino. En Object
  se excluyen los objetos de la sesión; al escalar a Edit habrá que excluir únicamente
  la geometría móvil y conservar como destino la geometría inmóvil compatible.
- Los destinos libres de arista/cara resultaron ambiguos para posicionamiento CAD. Move
  conserva solo Vértice, Punto medio y Centro de cara con sus radios explícitos.
