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
