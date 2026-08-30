# Backend de Blender Tablet Remote

Add-on Python que ejecuta en Blender las órdenes recibidas desde
[`../android-client`](../android-client). El contrato canónico está en
[`docs/protocol.md`](docs/protocol.md); el estado y las reglas globales, en
[`../AGENTS.md`](../AGENTS.md). Si hay un ciclo abierto, su trabajo pendiente vive en
un `PLAN_BACKEND.md` de la raíz.

## Instalación

```bash
./tools/build_addon.sh
```

El ZIP se genera en `dist/`. Instálalo con **Edit > Preferences > Add-ons > Install
from Disk**. En sus preferencias se configuran host, puerto, token, captura y
**Arrancar con Blender**. El panel operativo está en `View 3D > Sidebar (N) > Remote`.

El servidor usa WebSocket 8765 para control y HTTP 8766 para vídeo. La captura
GPUOffScreen mantiene una cámara remota independiente y no transmite la pantalla ni la
interfaz nativa del PC. La codificación se delega a `ffmpeg`.

## Reglas técnicas esenciales

- Los hilos de red nunca llaman a `bpy`; entregan mensajes al bridge del hilo principal.
- Los gestos continuos se agrupan para reducir trabajo y producir un solo paso de undo.
- Se prefiere la API de datos/BMesh; los operadores se usan solo cuando Blender no
  ofrece una alternativa fiable y siempre con el contexto adecuado.
- Toda ampliación del contrato se documenta y prueba antes de depender de ella desde Android.

## Desarrollo y pruebas

```bash
blender --python tools/run_server.py -- --port 8765 --token devtoken
python3 tools/blender_remote_cli.py --host 127.0.0.1 --token devtoken

blender --background --python tests/run_tests.py
blender --python tests/run_gui_tests.py
```

`undo/redo` y las operaciones que necesitan una región 3D pueden requerir Blender con
interfaz. No publiques los puertos: restringe el host a WireGuard o a una red confiable.
