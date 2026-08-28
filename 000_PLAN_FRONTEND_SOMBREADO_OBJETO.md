# 000 — Frontend: toggle Plano/Suave en Object Mode

- Añadir una acción única `SHADE_OBJECT` al long-click de Object Mode.
- Mostrarla solo sobre un objeto MESH seleccionado y con capability anunciada.
- Enviar `object.shade {mode: TOGGLE, objects:[objeto tocado]}` desde el ViewModel.
- Mantener el menú dentro de su límite y cubrirlo con tests JVM.

## Cierre

- Tests JVM y `assembleDebug` correctos; APK entregable.
