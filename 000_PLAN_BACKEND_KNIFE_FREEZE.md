# 000 — Backend: congelación por sesiones inválidas

**Estado: ejecutado. Propietario: backend.**

## Objetivo

Evitar que una referencia RNA eliminada en una sesión modal detenga el timer principal,
y hacer mutuamente excluyentes las sesiones `transform.*` y `tool.*`.

## Criterios de cierre

- [x] El broadcast de eventos/modal no deja escapar excepciones al timer.
- [x] `transform.status` y `tool.status` invalidan limpiamente referencias eliminadas.
- [x] Comenzar una sesión restaura y cierra la sesión de la otra familia.
- [x] Undo/redo y borrados cancelan sesiones antes de invalidar datos.
- [x] Pruebas backend específicas y suite proporcional en verde.

Validación integrada: tras reinstalar el add-on, `transform.begin → object.delete`
conserva el pump; `transform.begin → tool.begin KNIFE` deja transformación inactiva y
Knife activa; al desconectar el propietario ambas sesiones vuelven a IDLE. El estado
sigue respondiendo y MJPEG recupera 18 fps bajo demanda.
