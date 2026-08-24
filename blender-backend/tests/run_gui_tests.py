"""Pruebas de los caminos que NO se pueden validar sin interfaz gráfica.

    blender --python blender-backend/tests/run_gui_tests.py

Orbitar, hacer pan, hacer zoom y seleccionar por toque necesitan un VIEW_3D real:
sin ventana no hay región, ni matriz de vista, ni con qué lanzar un rayo. La suite
headless (run_tests.py) cubre el resto del protocolo, pero da por buenos justo los
tres caminos que el usuario toca todo el rato. Esto los ejercita de verdad, por el
mismo protocolo que usa Android, y comprueba el efecto en Blender.

Sale con código 1 si algo falla. Cierra Blender al terminar.
"""

from __future__ import annotations

import sys
import threading
import time
import traceback
import urllib.request
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from blender_tablet_remote import bridge  # noqa: E402
from wsclient import WSClient  # noqa: E402

PORT = 8791
STREAM_PORT = 8792

results: list[tuple[bool, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((bool(ok), name, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail and not ok else ""), flush=True)
    return bool(ok)


def moved(a, b, tol=1e-4) -> bool:
    return any(abs(x - y) > tol for x, y in zip(a, b))


def cmd(client: WSClient, name: str, payload: dict | None = None) -> dict:
    """Ejecuta un comando y devuelve su result, fallando fuerte si el servidor dice que no."""
    reply = client.command(name, payload or {})
    if not reply.get("ok"):
        raise AssertionError(f"{name} falló: {reply.get('error')} ({reply.get('code')})")
    return reply.get("result") or {}


def drag(client: WSClient, gesture: str, dx=0.0, dy=0.0, factor=1.0, steps=4):
    """Un arrastre completo. Los gestos no responden, así que damos tiempo al pump."""
    client.gesture(gesture, "begin")
    for _ in range(steps):
        client.gesture(
            gesture, "update",
            dx=dx / steps, dy=dy / steps, factor=factor ** (1.0 / steps),
        )
        time.sleep(0.05)
    client.gesture(gesture, "end")
    time.sleep(0.4)


def view_of(client: WSClient) -> dict:
    return cmd(client, "scene.get_state", {"include_view": True})["view"]


def scenario(client: WSClient) -> None:
    print("\n[1] Escena de partida", flush=True)
    state = cmd(client, "scene.get_state", {"include_view": True})
    check("hay un objeto activo", state.get("active_object") is not None, str(state.get("active_object")))
    check("arranca en Object Mode", state.get("mode") == "OBJECT", str(state.get("mode")))
    check("el estado trae la vista", "view" in state, str(list(state)))
    cube = state.get("active_object")

    print("\n[2] Mover el viewport", flush=True)
    before = view_of(client)
    drag(client, "orbit", dx=0.25)
    after = view_of(client)
    check("orbit gira la vista", moved(before["rotation"], after["rotation"]),
          f"{before['rotation']} -> {after['rotation']}")
    check("orbit no mueve el centro", not moved(before["location"], after["location"]))

    before = view_of(client)
    drag(client, "pan", dx=0.2, dy=0.1)
    after = view_of(client)
    check("pan desplaza el centro", moved(before["location"], after["location"]),
          f"{before['location']} -> {after['location']}")

    before = view_of(client)
    drag(client, "zoom", factor=2.0)
    after = view_of(client)
    check("zoom acerca la camara", after["distance"] < before["distance"],
          f"{before['distance']:.3f} -> {after['distance']:.3f}")
    drag(client, "zoom", factor=0.5)
    check("zoom aleja la camara", view_of(client)["distance"] > after["distance"])

    ortho = cmd(client, "view.perspective", {"mode": "ORTHO"})
    check("activa ortográfica real", ortho.get("perspective") == "ORTHO" and ortho.get("changed") is True, str(ortho))
    toggled = cmd(client, "view.perspective", {"mode": "TOGGLE"})
    check("toggle restaura perspectiva", toggled.get("perspective") == "PERSP", str(toggled))

    print("\n[3] Encuadrar", flush=True)
    # Ojo: el cubo por defecto es el objeto ACTIVO pero no está seleccionado, y
    # view_selected sin selección no mueve la vista. Por eso seleccionamos primero.
    cmd(client, "object.select_all", {"value": False})
    framed = cmd(client, "view.frame_selected")
    check("sin seleccion, frame_selected encuadra todo", framed.get("framed") == "all", str(framed.get("framed")))

    cmd(client, "object.select", {"name": cube})
    time.sleep(0.2)
    framed = cmd(client, "view.frame_selected")
    check("con seleccion, encuadra la seleccion", framed.get("framed") == "selected", str(framed.get("framed")))
    time.sleep(0.3)

    print("\n[4] Seleccionar objetos con el dedo", flush=True)
    cmd(client, "object.select_all", {"value": False})
    time.sleep(0.2)

    hit = cmd(client, "selection.pick", {"u": 0.5, "v": 0.5})
    check("tocar el centro acierta en el objeto", hit.get("hit") is True, str(hit))
    check("selecciona el objeto correcto", hit.get("object") == cube, f"{hit.get('object')} != {cube}")

    state = cmd(client, "scene.get_state")
    check("el objeto queda seleccionado", cube in state.get("selected_objects", []),
          str(state.get("selected_objects")))
    check("y queda como activo", state.get("active_object") == cube)

    miss = cmd(client, "selection.pick", {"u": 0.02, "v": 0.02})
    check("tocar el vacio no acierta", miss.get("hit") is False, str(miss))
    state = cmd(client, "scene.get_state")
    check("tocar el vacio deselecciona", not state.get("selected_objects"),
          str(state.get("selected_objects")))

    print("\n[5] Sin seleccion no se transforma nada", flush=True)
    # El cubo por defecto es el objeto ACTIVO pero no está seleccionado. Antes,
    # arrastrar con la herramienta de mover lo movía igualmente: parecía que la
    # navegación estaba rota cuando lo que pasaba es que se movía el objeto.
    cmd(client, "object.select_all", {"value": False})
    time.sleep(0.2)
    before = cmd(client, "scene.get_state")["active"]["location"]
    for gesture in ("move", "rotate", "scale"):
        client.gesture(gesture, "begin")
        for _ in range(3):
            client.gesture(gesture, "update", dx=0.08, dy=0.05, factor=1.2)
            time.sleep(0.05)
        client.gesture(gesture, "end")
    time.sleep(0.6)
    state = cmd(client, "scene.get_state")
    after = state["active"]["location"]
    check("un gesto sin seleccion no mueve el objeto activo",
          all(abs(a - b) < 1e-5 for a, b in zip(before, after)), f"{before} -> {after}")
    check("y sigue sin haber nada seleccionado", not state.get("selected_objects"),
          str(state.get("selected_objects")))

    print("\n[6] Manipulador (gizmo)", flush=True)
    # El paso anterior acabó deseleccionando: volvemos a tocar el objeto.
    cmd(client, "selection.pick", {"u": 0.5, "v": 0.5})
    time.sleep(0.3)
    gz = cmd(client, "view.gizmo")
    check("con objeto seleccionado hay gizmo", gz.get("visible") is True, str(gz))
    check("el gizmo es del objeto correcto", gz.get("object") == cube, str(gz.get("object")))
    origin = gz.get("origin") or []
    check("el origen cae dentro de la pantalla",
          len(origin) == 2 and all(0.0 <= c <= 1.0 for c in origin), str(origin))
    axes = gz.get("axes") or {}
    check("vienen los tres ejes", sorted(axes) == ["X", "Y", "Z"], str(sorted(axes)))
    check("los ejes no se solapan con el origen",
          all(axes.get(k) and moved(axes[k], origin, tol=1e-3) for k in ("X", "Y", "Z")), str(axes))
    check("los tres ejes apuntan a sitios distintos",
          len({tuple(axes[k]) for k in ("X", "Y", "Z") if axes.get(k)}) == 3, str(axes))

    candidate = cmd(client, "snap.query", {"u": 0.5, "v": 0.5, "snap_type": "FACE"})
    check("snap encuentra la cara visible", bool(candidate.get("hit") and candidate.get("id")), str(candidate))
    cmd(client, "transform.begin", {"mode": "MOVE", "snap_type": "FACE"})
    snapped = cmd(client, "transform.snap_candidate", {
        "u": 0.5, "v": 0.5, "snap_type": "FACE", "lock": True,
    })
    check("el candidato queda bloqueado en la sesión", snapped.get("snap_locked") is True and
          bool((snapped.get("snap_candidate") or {}).get("id")), str(snapped))
    cmd(client, "transform.cancel")

    # Mover por un eje debe cambiar solo esa coordenada.
    before = cmd(client, "scene.get_state")["active"]["location"]
    client.gesture("move", "begin", axis="X")
    for _ in range(3):
        client.gesture("move", "update", dx=0.05, dy=0.0)
        time.sleep(0.05)
    client.gesture("move", "end")
    time.sleep(0.5)
    after = cmd(client, "scene.get_state")["active"]["location"]
    check("arrastrar el eje X mueve en X", abs(after[0] - before[0]) > 1e-4,
          f"{before} -> {after}")
    check("y no toca Y ni Z",
          abs(after[1] - before[1]) < 1e-4 and abs(after[2] - before[2]) < 1e-4,
          f"{before} -> {after}")

    # Coordenadas absolutas: lo que usa el panel numérico.
    cmd(client, "transform.move", {"x": 1.5, "y": -2.0, "z": 0.25, "absolute": True})
    time.sleep(0.3)
    loc = cmd(client, "scene.get_state")["active"]["location"]
    check("fijar coordenadas absolutas coloca el objeto",
          all(abs(a - b) < 1e-4 for a, b in zip(loc, (1.5, -2.0, 0.25))), str(loc))

    cmd(client, "object.select_all", {"value": False})
    time.sleep(0.2)
    gz = cmd(client, "view.gizmo")
    check("sin seleccion no hay gizmo", gz.get("visible") is False, str(gz))

    # Lo dejamos otra vez seleccionado y centrado para los pasos siguientes.
    cmd(client, "object.select", {"name": cube})
    cmd(client, "transform.move", {"x": 0.0, "y": 0.0, "z": 0.0, "absolute": True})
    cmd(client, "view.frame_selected")
    time.sleep(0.4)

    print("\n[7] Object <-> Edit Mode", flush=True)
    cmd(client, "selection.pick", {"u": 0.5, "v": 0.5})
    time.sleep(0.2)
    cmd(client, "mode.edit")
    time.sleep(0.3)
    state = cmd(client, "scene.get_state")
    check("entra en Edit Mode", state.get("mode") == "EDIT", str(state.get("mode")))

    cmd(client, "selection.vertex")
    time.sleep(0.2)
    picked = cmd(client, "selection.pick", {"u": 0.5, "v": 0.5, "threshold": 0.25})
    check("en Edit Mode el toque selecciona geometria", picked.get("hit") is not False, str(picked))
    boxed = cmd(client, "selection.box", {
        "u0": 0.0, "v0": 0.0, "u1": 1.0, "v1": 1.0, "mode": "SET",
    })
    check("Box Select selecciona geometría proyectada", boxed.get("affected", 0) > 0, str(boxed))
    circled = cmd(client, "selection.circle", {
        "u": 0.5, "v": 0.5, "radius": 0.5, "mode": "SET",
    })
    check("Circle Select selecciona geometría proyectada", circled.get("affected", 0) > 0, str(circled))
    state = cmd(client, "scene.get_state")
    check("sigue en Edit Mode tras seleccionar", state.get("mode") == "EDIT", str(state.get("mode")))

    print("\n[8] Vuelta a Object Mode", flush=True)
    cmd(client, "mode.object")
    time.sleep(0.3)
    state = cmd(client, "scene.get_state")
    check("vuelve a Object Mode", state.get("mode") == "OBJECT", str(state.get("mode")))

    print("\n[9] El video refleja lo que pasa", flush=True)
    # Fuerza el gizmo Move nativo: el startup puede recordar Select u otra herramienta.
    for window in bpy.context.window_manager.windows:
        area = next((candidate for candidate in window.screen.areas if candidate.type == "VIEW_3D"), None)
        if area is None:
            continue
        region = next((candidate for candidate in area.regions if candidate.type == "WINDOW"), None)
        if region is None:
            continue
        space = area.spaces.active
        space.show_gizmo = True
        space.show_gizmo_tool = True
        space.show_gizmo_context = True
        space.show_gizmo_object_translate = True
        area.tag_redraw()
        break

    url = f"http://127.0.0.1:{STREAM_PORT}/frame.jpg"
    try:
        first = urllib.request.urlopen(url, timeout=5).read()
        Path("/tmp/blender_remote_post_pixel_test.jpg").write_bytes(first)
        stream = bridge.stream_info()
        check("la fuente activa es POST_PIXEL",
              stream.get("capture_active") == "post_pixel", str(stream.get("capture_active")))
        check("el draw handler entregó callbacks",
              (stream.get("post_pixel") or {}).get("callbacks", 0) > 0, str(stream.get("post_pixel")))
        drag(client, "orbit", dx=0.4)
        time.sleep(0.5)
        second = urllib.request.urlopen(url, timeout=5).read()
        check("llegan fotogramas", len(first) > 1000, f"{len(first)} bytes")
        check("el fotograma cambia al orbitar", first != second,
              f"{len(first)} vs {len(second)} bytes")
    except OSError as exc:
        check("el servidor de video responde", False, str(exc))


def run() -> None:
    try:
        client = WSClient("127.0.0.1", PORT, timeout=8.0)
        client.connect()
        try:
            scenario(client)
        finally:
            client.close()
    except Exception:  # noqa: BLE001
        print(traceback.format_exc(), flush=True)
        results.append((False, "la prueba reventó", ""))

    passed = sum(1 for ok, _, _ in results if ok)
    print("\n" + "=" * 70, flush=True)
    print(f"RESULTADO: {passed} PASS, {len(results) - passed} FAIL de {len(results)}", flush=True)
    print("=" * 70, flush=True)
    for ok, name, detail in results:
        if not ok:
            print(f"  FALLO: {name}   {detail}", flush=True)

    bridge.stop()
    # bpy.ops solo es seguro en el hilo principal: pedimos la salida desde un timer.
    code = 0 if passed == len(results) else 1
    bpy.app.timers.register(lambda: sys.exit(code), first_interval=0.2)


def start() -> None:
    bridge.start(
        "127.0.0.1", PORT, "",
        stream={
            "enabled": True,
            "port": STREAM_PORT,
            "fps": 20,
            "max_width": 960,
            "quality": 70,
            "capture_mode": "POST_PIXEL",
        },
    )
    threading.Thread(target=run, name="gui-tests", daemon=True).start()
    return None


bpy.app.timers.register(start, first_interval=2.0)
