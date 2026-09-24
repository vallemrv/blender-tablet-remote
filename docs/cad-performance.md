# Evaluación CAD y fluidez

CAD muestra el sólido compacto y reserva la retícula de cuadriláteros para una
copia editable. El documento paramétrico sigue siendo la fuente de verdad; no se
ha incorporado un kernel BREP ni se ha reducido el muestreo de círculos o arcos.

La evaluación de extrusiones, uniones, vaciados y redondeos se ejecuta en un proceso
Blender auxiliar persistente. El solver del arrastre también utiliza ese proceso.
Solo recibe datos serializados: nunca referencias a objetos o mallas del Blender
interactivo. Cada proceso utiliza `bpy`/`bmesh` en su propio hilo principal.
El proceso auxiliar reutiliza perfiles y resultados anteriores. El host conserva
la evaluación actual y el baseline, y actualiza coordenadas sin crear otra malla
cuando la topología permanece igual. Abrir un boceto sin operaciones no evalúa
los sólidos anteriores.

El pump sigue atendiendo vídeo y navegación mientras espera. Android limita los
comandos CAD a una petición en vuelo y conserva la última muestra absoluta
pendiente; begin, settle y confirmación conservan su orden. Cancelar, guardar,
cambiar de escena o desconectar invalidan el resultado pendiente. Tras cargar un
archivo, la primera cancelación restaura la geometría publicada sin recalcular
el historial. Un proceso fallido se puede reiniciar en la siguiente petición.

## Medición reproducible

Ensayo local del 25 de septiembre de 2026, Blender 5.2.2 LTS. Placa de 270 × 150 mm
con cuatro agujeros de radio 10 mm, círculos de 128 segmentos; doce cambios de
profundidad y doce muestras de lápiz. Comparación con `da8de6c`, anterior a esta
reestructuración, usando exactamente el mismo script:

```bash
blender --background --factory-startup --python-exit-code 1 \
  --python blender-backend/tools/benchmark_cad.py

# Para comparar otra copia del backend:
blender --background --factory-startup --python-exit-code 1 \
  --python blender-backend/tools/benchmark_cad.py -- --backend /ruta/blender-backend
```

| Medida | Antes | Después |
| --- | ---: | ---: |
| Vértices visibles | 4.654 | 1.032 |
| Caras visibles | 4.660 | 1.560 |
| Primera extrusión, cálculo local | 275,8 ms | 206,6 ms |
| Actualizar profundidad, mediana | 31,9 ms | 6,5 ms |
| Muestra de lápiz, mediana | 13,3 ms | 2,6 ms |

Las llamadas directas de este ensayo ejecutan el mismo evaluador sin transporte
entre procesos. Miden coste geométrico y actualización local, no FPS, latencia de
red ni el arranque del proceso auxiliar. En el ensayo de comunicación, su primer
arranque tardó aproximadamente 1,5 s y permitió seguir ejecutando el pump.
Los tiempos dependen del equipo y de la pieza; no garantizan ausencia absoluta
de pausas. La retícula editable y la publicación final de geometría siguen
ejecutándose en el host. La edición numérica de restricciones conserva su solver
síncrono; el solver trasladado al proceso auxiliar es el del arrastre.

## Comprobaciones

- 176 pruebas CAD en background: 151 correctas y 25 omitidas por requerir ventana.
- 36 pruebas con ventana correctas: selección, resaltado GPU, copias editables,
  historial y un undo/redo nativo de un vaciado calculado en el proceso auxiliar.
- Pruebas con el proceso real: continuidad del pump, cancelación, guardado,
  desconexión, fallo/reinicio del proceso y conservación del último trazo estable.
- 105 pruebas Android correctas y compilación de la APK; validación del ZIP de Blender.

La prueba antigua
`HistoryTests.test_undo_after_insertion_at_bar_restores_previous_document` falla
también en `da8de6c`: su preparación crea dos rectángulos coincidentes y el kernel
rechaza ese perfil. Se comprobó por separado en ambas versiones; no se incluye
en las 36 pruebas de ventana. El código de esa prueba se conserva sin cambios.
