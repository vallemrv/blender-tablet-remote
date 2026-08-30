# Knife remoto — dificultades, intentos y estado actual

Fecha de referencia: 2026-08-30.

## Propósito

Este documento registra los problemas encontrados durante el desarrollo y la prueba
del Knife táctil, las estrategias empleadas y su resultado. No define una solución
nueva ni autoriza cambios de código. Su finalidad es evitar repetir intentos que ya no
sirvieron y separar el problema actualmente resuelto del que continúa abierto.

## Resultado que busca el usuario

El Knife debe servir para construir topología de forma deliberada y precisa desde la
tablet. El caso representativo es crear varios cortes independientes, conectarlos a
vértices existentes o recién creados y construir transiciones de cuatro puntos a dos.
La figura dibujada y la topología final deben coincidir: cada ancla elegida debe
conservarse y cada segmento solicitado debe convertirse en el corte correspondiente,
sin diagonales, cierres ni aristas adicionales inventadas por el sistema.

## Problemas observados durante la evolución

### 1. El primer punto se fijaba demasiado pronto

El flujo inicial trataba un gesto BEGIN→END como un segmento completo. Al apoyar el
lápiz se elegía un inicio antes de que el usuario pudiera colocarlo con precisión.

Se cambió a un modelo en el que BEGIN y UPDATE solo sondean y END fija un único punto.
También se dejó de usar la muestra inestable de ACTION_UP y se confirma la última
posición estable de DOWN/MOVE.

Resultado: este problema de interacción quedó resuelto.

### 2. Solo existía una polilínea continua

El usuario no podía terminar una conexión y empezar otra dentro de la misma operación.
Esto impedía construir patrones como una reducción 4→2.

Se añadió el concepto de varios trazos y la acción «Nuevo corte». Los trazos se muestran
por separado en el overlay y se mantienen dentro de una misma sesión reversible.

Resultado: la interfaz permite expresar varios trazos, aunque la traducción geométrica
final de ese conjunto sigue siendo incorrecta.

### 3. El snap parecía débil o inexistente

Los umbrales iniciales eran demasiado pequeños para lápiz y dedo. Después se ampliaron,
pero la arista seguía ganando casi siempre: el punto proyectado sobre ella tiene
distancia matemática cero y robaba el candidato a su vértice o punto medio.

Se probaron radios mayores y prioridad categórica VERTEX > EDGE_CENTER > EDGE.

Resultado: mejoró la captura de vértices y puntos medios, pero aparecieron conflictos
al intentar seleccionar la propia arista.

### 4. Se capturaban vértices ocultos de la parte posterior

Para hacer el snap más pegajoso se amplió la búsqueda desde la cara tocada hacia caras
vecinas por conectividad. En una malla como un cubo esa vecindad alcanza rápidamente
caras posteriores, por lo que el Knife podía anclarse a geometría no visible.

Esa estrategia se descartó. Los candidatos quedaron limitados a la cara visible
alcanzada por el raycast.

Resultado: ya no debe usarse la expansión indiscriminada por caras conectadas.

### 5. Los radios automáticos impedían escoger aristas

Con vértices y puntos medios muy pegajosos, sus zonas podían cubrir una arista corta
completa. La prioridad automática no bastaba para expresar la intención del usuario.

Se añadió un destino explícito de snap: Auto, Vértice, Medio o Arista. De esta manera
se puede eliminar la ambigüedad sin reducir otra vez la facilidad de captura.

Resultado actual: **el sistema de snap de Knife funciona bien y se considera correcto**.
No debe rediseñarse ni degradarse mientras se investiga la geometría final.

### 6. La malla se cortaba mientras la figura estaba incompleta

Una versión reconstruía la preview después de cada punto. Una polilínea todavía
incompleta podía producir particiones provisionales, cierres prematuros o topología que
condicionaba los siguientes raycasts. Desde la tablet parecía que Knife decidía por su
cuenta cómo cerrar la figura.

Se probó entonces diferir toda mutación hasta Confirmar. Eso evitaba cortes parciales,
pero introdujo otro problema: los vértices de un trazo terminado todavía no existían y
el siguiente trazo no podía anclarse a ellos.

La estrategia posterior fue escalonada: el trazo activo permanece como overlay y
«Nuevo corte» fija el trazo terminado en una preview reversible. Así los siguientes
trazos pueden sondear los vértices reales creados por los anteriores. Confirmar vuelve
a reconstruir el conjunto desde el backup.

Resultado: la disponibilidad de anclas entre trazos mejoró, pero **el corte final sigue
sin reproducir la figura solicitada**.

### 7. Una preview fallida podía dejar BMesh parcialmente modificado

Se observó un crash tras `Anchor not on mesh surface` y una captura OFFSCREEN. El motor
geométrico podía haber partido parte de la malla antes de descubrir un tramo inválido.

Se añadió restauración del backup ante `CommandError` o cualquier excepción y retirada
de anclas tentativas. También se probó el servidor con ráfagas de UPDATE.

Resultado: la atomicidad y la resistencia al crash mejoraron. Esta protección debe
mantenerse en cualquier solución posterior.

### 8. Deshacer podía salir de Edit Mode

Después de confirmar un Knife, Undo eliminaba correctamente el corte, pero devolvía
Blender a Object Mode. La explicación probable es que el paso anterior disponible en
la pila era la entrada a Edit Mode y no un estado base de la malla inmediatamente antes
del Knife.

Se añadió un baseline explícito de undo antes de aplicar la geometría y el paso final
después de aplicarla.

Resultado: está implementado, pero necesita validación real en Blender interactivo y
tablet. Las pruebas headless no disponen de una pila de undo equivalente.

## Estado actual confirmado por el usuario

### Funciona

- La colocación y ajuste de puntos es controlable.
- El snap de Knife funciona correctamente.
- Los vértices y puntos medios son suficientemente pegajosos.
- Puede forzarse Auto, Vértice, Medio o Arista.
- Ya no interesa seguir modificando el sistema de snap mientras se resuelve el motor
  de corte.

### No funciona

- La topología final no se parece al trazado buscado.
- Los cortes resultantes son caóticos o impredecibles.
- El conjunto de segmentos dibujados no se conserva fielmente al ejecutar el corte.
- No está demostrado que las conexiones entre trazos se resuelvan usando exactamente
  los vértices generados por trazos anteriores.
- La conservación de Edit Mode después de Undo sigue pendiente de validación práctica.

## Hipótesis del problema activo

El problema actual ya no está en picking, coordenadas táctiles ni selección del destino
de snap. Está en la traducción de una colección de trazos y anclas correctas a
operaciones BMesh.

Aspectos que conviene investigar antes de otro cambio:

1. Si cada ancla conserva identidad topológica o solo una coordenada 3D aproximada.
2. Si al reconstruir desde el backup se vuelven a resolver las anclas contra una
   topología distinta de aquella sobre la que se escogieron.
3. Si `cut_polyline` procesa cada segmento de forma independiente y altera las caras
   necesarias para interpretar los segmentos posteriores.
4. Si dos trazos que comparten visualmente un punto terminan usando dos coordenadas
   próximas pero no el mismo BMVert.
5. Si el orden de aplicación de los trazos cambia el resultado.
6. Si el cierre de una polilínea se infiere por coincidencia geométrica además del flag
   explícito `closed`.
7. Si la triangulación o elección de cara interna introduce diagonales que no forman
   parte del dibujo.

## Estrategias que no deben repetirse sin nueva evidencia

- Aumentar otra vez los radios de snap como respuesta a cortes erróneos.
- Buscar candidatos recorriendo caras vecinas sin comprobación de visibilidad.
- Ejecutar toda la topología con cada movimiento o con cada punto provisional.
- Suponer que dos anclas con coordenadas casi iguales representan automáticamente el
  mismo vértice topológico.
- Considerar que las pruebas de transporte, contrato o ausencia de crash demuestran la
  corrección geométrica del corte.

## Criterio de éxito para el siguiente trabajo

La siguiente solución debe probarse con una figura conocida que contenga varios trazos
y conexiones 4→2. Antes de confirmar debe registrarse la lista exacta de anclas,
segmentos, tipos de snap e identidades topológicas. Después de confirmar debe verificarse
que existe una correspondencia uno a uno entre segmentos solicitados y aristas creadas,
sin aristas adicionales, sin conexiones a caras posteriores y sin depender de tolerancias
casuales. Undo debe devolver exactamente la malla anterior y conservar Edit Mode.

