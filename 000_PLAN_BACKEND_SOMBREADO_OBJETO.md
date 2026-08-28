# 000 — Backend: sombreado Plano/Suave por objeto

- Añadir `object.shade` con `mode: TOGGLE|FLAT|SMOOTH` para objetos MESH.
- Publicar la capability `object_shading` y documentar el contrato.
- Devolver snapshot resultante y crear un único paso de undo.
- Congelar fixture, contrato y aceptación headless.

## Cierre

- Toggle Plano/Suave verificado sin afectar objetos no indicados.
- Suite backend y contrato sin regresiones.
