# 001 — Backend: snap de tools y Dissolve

**Estado: ejecutado. Propietario: backend (`blender-backend/**`).**

## Alcance

- Snap escalar INCREMENT/GRID y paso en parámetros continuos de tools.
- Candidato geométrico bloqueable para Extrude REGION mediante
  `tool.snap_candidate`, visible en `tool.status`, sin previews acumulativas.
- `mesh.dissolve` por VERTS/EDGES/FACES, habilitado y separado de Delete.
- Contrato, fixtures y pruebas sincronizados.

## Cierre

- [x] Documentación, protocolo, fixtures y contrato Android coinciden.
- [x] Pruebas cubren cuantización, candidato y los tres modos de Dissolve.
- [x] Cancel restaura exactamente la topología inicial.

Validación: 701/701 headless (`tests/run_tests.py`) y 251/252 contrato Android
(`tests/android_contract.py`; el único fallo es un choque de puerto 8766 con la
instancia GUI del usuario al correr ambos servidores a la vez, no una regresión).

## Adenda (2026-08-27): Bevel y Bridge Edge Loops en `edit_toolbar`

El usuario reportó que no encontraba Bevel ni Bridge Edge Loops tras la primera
entrega: existían en `edit_catalog` (submenú "Tools de malla" del radial) pero nunca
se añadieron a `edit_toolbar` (la barra izquierda), a diferencia de Extrude/Inset/Loop
Cut/Cut. `EDIT_TOOLBAR` sube a versión 2 con dos familias nuevas de una sola variante
(mismo patrón que Loop Cut), reutilizando `_TOOL_PARAMETERS["BEVEL"]` y
`["BRIDGE_EDGE_LOOPS"]` (ya con snap) sin duplicar el esquema. `fixtures/v2/capabilities.json`
y `tests/android_contract.py` (orden de familias, snap anunciado por Bevel/Bridge)
quedaron sincronizados; verificado byte a byte contra la salida real de
`server.capabilities`.
