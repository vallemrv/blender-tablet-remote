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
    import bmesh
    from mathutils import Vector

    from blender_tablet_remote.bpy_utils import find_view3d
    from blender_tablet_remote.camera import camera as tablet_camera

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

    # Una pieza pequeña no puede heredar el antiguo suelo de 25 cm. El doble toque
    # debe acercar la cámara a su tamaño real y no perderla en el centro.
    cube_obj = bpy.data.objects[cube]
    old_scale = cube_obj.scale.copy()
    cube_obj.scale = (0.025, 0.025, 0.025)
    bpy.context.view_layer.update()
    tiny = cmd(client, "view.frame_selected")
    check("encuadrar una pieza de 5 cm no la aleja",
          tiny.get("distance", 1.0) < 0.2, str(tiny.get("distance")))
    cube_obj.scale = old_scale
    bpy.context.view_layer.update()
    cmd(client, "view.frame_selected")

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

    print("\n[6] Snap y transformaciones", flush=True)
    # El paso anterior acabó deseleccionando: volvemos a tocar el objeto.
    cmd(client, "selection.pick", {"u": 0.5, "v": 0.5})
    time.sleep(0.3)
    candidate = cmd(client, "snap.query", {"u": 0.5, "v": 0.5, "snap_type": "FACE"})
    check("snap encuentra la cara visible", bool(candidate.get("hit") and candidate.get("id")), str(candidate))
    from mathutils import Vector as SnapVector
    from blender_tablet_remote.bpy_utils import find_view3d as snap_find_view3d
    from blender_tablet_remote.camera import camera as snap_camera

    snap_obj = bpy.data.objects[cube]
    visible_polygon = snap_obj.data.polygons[candidate["element"]]
    snap_rv3d = snap_find_view3d()[3]
    face_center_world = snap_obj.matrix_world @ visible_polygon.center
    face_center_screen = snap_camera.project(face_center_world, snap_rv3d)
    face_center = cmd(client, "snap.query", {
        "u": face_center_screen[0], "v": face_center_screen[1],
        "snap_type": "FACE_CENTER", "threshold": 0.02,
    })
    check("snap detecta el centro exacto de la cara",
          face_center.get("hit") and
          (SnapVector(face_center.get("position")) - face_center_world).length < 1e-5,
          str(face_center))

    edge_key = visible_polygon.edge_keys[0]
    edge_center_world = (
        snap_obj.matrix_world @ snap_obj.data.vertices[edge_key[0]].co
    ).lerp(snap_obj.matrix_world @ snap_obj.data.vertices[edge_key[1]].co, 0.5)
    edge_center_screen = snap_camera.project(edge_center_world, snap_rv3d)
    # Un punto exactamente sobre la silueta puede caer fuera por precisión del
    # raycast; entrar un 3 % en la cara conserva el centro dentro del umbral.
    edge_probe_screen = (
        edge_center_screen[0] * .97 + face_center_screen[0] * .03,
        edge_center_screen[1] * .97 + face_center_screen[1] * .03,
    )
    edge_center = cmd(client, "snap.query", {
        "u": edge_probe_screen[0], "v": edge_probe_screen[1],
        "snap_type": "EDGE_CENTER", "threshold": 0.04,
    })
    check("snap detecta el punto medio exacto de la arista",
          edge_center.get("hit") and
          (SnapVector(edge_center.get("position")) - edge_center_world).length < 1e-5,
          str(edge_center))

    subdivided = cmd(client, "modifier.add", {
        "type": "SUBSURF", "parameters": {"levels": 2},
    })
    subsurf_name = next(m["name"] for m in subdivided["modifiers"] if m["type"] == "SUBSURF")
    evaluated_face = cmd(client, "snap.query", {"u": 0.5, "v": 0.5, "snap_type": "FACE"})
    check("snap FACE reconoce la superficie evaluada por Subdivision",
          evaluated_face.get("hit") and evaluated_face.get("object") == cube,
          str(evaluated_face))
    cmd(client, "modifier.remove", {"name": subsurf_name})

    cmd(client, "transform.begin", {"mode": "MOVE", "snap_type": "FACE"})
    snapped = cmd(client, "transform.snap_candidate", {
        "u": 0.5, "v": 0.5, "snap_type": "FACE", "lock": True,
    })
    check("el candidato queda bloqueado en la sesión", snapped.get("snap_locked") is True and
          bool((snapped.get("snap_candidate") or {}).get("id")), str(snapped))
    cmd(client, "transform.cancel")

    original_location = bpy.data.objects[cube].location.copy()
    cmd(client, "transform.begin", {"mode": "MOVE"})
    hovered = cmd(client, "transform.reference_candidate", {
        "u": face_center_screen[0], "v": face_center_screen[1], "lock": False,
    })
    check("REL sondea sin mover el objeto",
          bool((hovered.get("reference_candidate") or {}).get("id")) and
          (bpy.data.objects[cube].location - original_location).length < 1e-6,
          str(hovered))
    locked = cmd(client, "transform.reference_candidate", {
        "u": face_center_screen[0], "v": face_center_screen[1], "lock": True,
    })
    check("REL bloquea la referencia sin mover el objeto",
          locked.get("reference_locked") is True and
          (bpy.data.objects[cube].location - original_location).length < 1e-6,
          str(locked))
    zero = cmd(client, "transform.value", {"values": [0.0, 0.0, 0.0]})
    locked_position = SnapVector(locked["reference_position"])
    check("XYZ cero no mueve al fijar REL",
          (bpy.data.objects[cube].location - original_location).length < 1e-6,
          str(zero))
    travelled = cmd(client, "transform.value", {"values": [0.25, 0.0, 0.0]})
    check("el marcador REL acompaña al objeto",
          (SnapVector(travelled["reference_position"]) -
           (locked_position + SnapVector((0.25, 0.0, 0.0)))).length < 1e-5,
          str(travelled.get("reference_position")))
    cmd(client, "transform.cancel")
    check("cancelar REL restaura la posición",
          (bpy.data.objects[cube].location - original_location).length < 1e-6,
          str(bpy.data.objects[cube].location))

    # Caso CAD real: un vértice del cubo seleccionado contra un vértice de otro.
    target_state = cmd(client, "object.add", {"primitive": "CUBE", "x": 3.0, "y": 0.0, "z": 0.0})
    target_name = target_state["active_object"]
    cmd(client, "object.select", {"name": cube})
    cmd(client, "view.axis", {"axis": "FRONT"})
    cmd(client, "view.frame_all")
    time.sleep(0.2)
    snap_rv3d = snap_find_view3d()[3]
    snap_camera.sync_from_region(snap_rv3d)

    def vertex_probe(object_name):
        obj = bpy.data.objects[object_name]
        center_screen = snap_camera.project(obj.matrix_world.translation, snap_rv3d)
        face = cmd(client, "snap.query", {
            "u": center_screen[0], "v": center_screen[1], "snap_type": "FACE",
        })
        polygon = obj.data.polygons[face["element"]]
        face_screen = snap_camera.project(obj.matrix_world @ polygon.center, snap_rv3d)
        vertex_index = polygon.vertices[0]
        vertex_world = obj.matrix_world @ obj.data.vertices[vertex_index].co
        vertex_screen = snap_camera.project(vertex_world, snap_rv3d)
        return vertex_world, (
            vertex_screen[0] * .97 + face_screen[0] * .03,
            vertex_screen[1] * .97 + face_screen[1] * .03,
        )

    source_world, source_probe = vertex_probe(cube)
    target_world, target_probe = vertex_probe(target_name)
    cmd(client, "transform.begin", {"mode": "MOVE", "snap_type": "VERTEX"})
    source_locked = cmd(client, "transform.reference_candidate", {
        "u": source_probe[0], "v": source_probe[1], "lock": True,
    })
    check("REL fija un vértice del objeto móvil",
          source_locked.get("reference_locked") is True and
          (source_locked.get("reference_candidate") or {}).get("snap_type") == "VERTEX",
          str(source_locked))
    aligned = cmd(client, "transform.snap_candidate", {
        "u": target_probe[0], "v": target_probe[1], "snap_type": "VERTEX", "lock": True,
    })
    check("snap excluye el móvil y encuentra el otro cubo",
          (aligned.get("snap_candidate") or {}).get("object") == target_name,
          str(aligned.get("snap_candidate")))
    check("vértice origen coincide exactamente con vértice destino",
          (SnapVector(aligned["reference_position"]) - SnapVector(
              aligned["snap_candidate"]["position"])).length < 1e-5,
          f"{aligned.get('reference_position')} -> {aligned.get('snap_candidate')}")
    cmd(client, "transform.cancel")
    cmd(client, "object.select", {"name": target_name})
    cmd(client, "object.delete")
    cmd(client, "object.select", {"name": cube})

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
    # Alejar antes del toque: con el encuadre ajustado, la orientación de cámara
    # (que depende de los gestos previos) puede dejar el vértice más cercano a más
    # de 0.25 del centro. Reducir el cubo en pantalla lo devuelve al umbral.
    cmd(client, "view.zoom", {"factor": 0.5})
    time.sleep(0.3)
    picked = cmd(client, "selection.pick", {"u": 0.5, "v": 0.5, "threshold": 0.25})
    check("en Edit Mode el toque selecciona geometria", picked.get("hit") is not False, str(picked))
    boxed = cmd(client, "selection.box", {
        "u0": 0.0, "v0": 0.0, "u1": 1.0, "v1": 1.0, "mode": "SET",
    })
    check("Box Select selecciona geometría proyectada", boxed.get("affected", 0) > 0, str(boxed))
    circled = cmd(client, "selection.circle", {
        "u": 0.5, "v": 0.5, "radius": 0.5, "mode": "SET",
    })
    cmd(client, "tool.begin", {"tool": "EXTRUDE", "parameters": {
        "variant": "REGION", "snap_type": "FACE", "offset": 0.0}})
    tool_snapped = cmd(client, "tool.snap_candidate", {
        "u": 0.5, "v": 0.5, "snap_type": "FACE", "lock": True})
    tool_candidate = tool_snapped.get("snap_candidate") or {}
    check("Extrude bloquea candidato geométrico con position y screen",
          bool(tool_candidate.get("id")) and len(tool_candidate.get("position", [])) == 3
          and len(tool_candidate.get("screen", [])) == 2, str(tool_snapped))
    cmd(client, "tool.cancel")
    check("Circle Select selecciona geometría proyectada", circled.get("affected", 0) > 0, str(circled))
    state = cmd(client, "scene.get_state")
    check("sigue en Edit Mode tras seleccionar", state.get("mode") == "EDIT", str(state.get("mode")))

    print("\n[8] Vuelta a Object Mode", flush=True)
    cmd(client, "mode.object")
    time.sleep(0.3)
    state = cmd(client, "scene.get_state")
    check("vuelve a Object Mode", state.get("mode") == "OBJECT", str(state.get("mode")))

    print("\n[9] El offscreen dibuja la escena al día", flush=True)
    url = f"http://127.0.0.1:{STREAM_PORT}/frame.jpg"
    # El vídeo offscreen debe seguir una transformación viva, sin confirmar: es lo que
    # se mira mientras se arrastra, y `transform.confirm` no sirve para comprobarlo
    # porque su `undo_push` es un `bpy.ops` que arrastra evaluación y redibujo propios.
    # Se prueban los dos modos porque Edit no dibuja la malla base sino el cage
    # evaluado del objeto.
    #
    # El criterio es el peso del JPEG y no la igualdad de bytes: el objeto se manda
    # lejísimos hasta salir del encuadre, y un fondo vacío comprime mucho mejor. Así
    # el ruido temporal del render no puede dar el test por bueno.
    #
    # AVISO medido, no supuesto: este bloque NO es un guardián de la sincronización del
    # depsgraph en `_grab_offscreen`. Se ejecutó a propósito con esa llamada desactivada
    # y los tres checks siguen en verde, porque con la ventana de Blender visible es el
    # propio redibujo de Blender el que evalúa el depsgraph a tiempo. Cubre el contrato
    # visible ("el vídeo sigue la transformación"), no la causa interna.
    bridge._capture.configure(enabled=True, fps=20, max_width=960, quality=70)
    time.sleep(0.6)

    def frame_size() -> int:
        return len(urllib.request.urlopen(url, timeout=5).read())

    def send_far() -> int:
        """Abre un MOVE y lo deja vivo: el objeto sale del encuadre sin confirmar."""
        cmd(client, "transform.begin", {"mode": "MOVE"})
        cmd(client, "transform.value", {"values": [0.0, 0.0, 80.0]})
        time.sleep(0.5)
        return frame_size()

    try:
        cmd(client, "object.select", {"name": cube})
        cmd(client, "view.axis", {"axis": "FRONT"})
        cmd(client, "view.frame_selected")
        time.sleep(0.4)
        visible = frame_size()
        gone = send_far()
        check("Object Mode: el frame sigue la transformación sin confirmar",
              gone < visible * 0.9, f"{visible} -> {gone} bytes")
        cmd(client, "transform.cancel")
        time.sleep(0.5)
        check("Object Mode: cancelar devuelve el objeto al frame",
              frame_size() > gone * 1.2, f"{gone} bytes con el objeto fuera")

        cmd(client, "mode.edit")
        cmd(client, "selection.all", {"value": True})
        time.sleep(0.4)
        visible = frame_size()
        gone = send_far()
        check("Edit Mode: el frame sigue la transformación sin confirmar",
              gone < visible * 0.9, f"{visible} -> {gone} bytes")
        cmd(client, "transform.cancel")
        cmd(client, "mode.object")
    except OSError as exc:
        check("el servidor de video responde en offscreen", False, str(exc))

    print("\n[11] Shading, pick a través y selección por caja", flush=True)
    # Wireframe activa xray: el toggle se refleja en el estado.
    wire = cmd(client, "view.shading", {"mode": "WIREFRAME"})
    check("shading pasa a WIREFRAME", wire.get("shading") == "WIREFRAME", str(wire))
    state = cmd(client, "scene.get_state")
    check("el estado lleva el shading", state.get("shading") == "WIREFRAME", str(state.get("shading")))
    solid = cmd(client, "view.shading", {"mode": "TOGGLE"})
    check("toggle vuelve a SOLID", solid.get("shading") == "SOLID", str(solid))

    # El PC deja un WIREFRAME sin xray (Shift+Z, un .blend guardado así): para la
    # tablet eso no es wireframe a medias, y el toggle debe re-arma el paquete.
    for window in bpy.context.window_manager.windows:
        area = next((candidate for candidate in window.screen.areas if candidate.type == "VIEW_3D"), None)
        if area is None:
            continue
        space = area.spaces.active
        space.shading.type = "WIREFRAME"
        space.shading.show_xray_wireframe = False
        area.tag_redraw()
        break
    time.sleep(0.3)
    repaired = cmd(client, "view.shading", {"mode": "TOGGLE"})
    check("toggle re-arma wireframe+xray en vez de bajar a SOLID",
          repaired.get("shading") == "WIREFRAME", str(repaired))
    off = cmd(client, "view.shading", {"mode": "TOGGLE"})
    check("con el paquete completo, toggle si baja a SOLID",
          off.get("shading") == "SOLID", str(off))

    cmd(client, "view.shading", {"mode": "WIREFRAME"})
    wire_space = next(
        (area.spaces.active for window in bpy.context.window_manager.windows
         for area in window.screen.areas if area.type == "VIEW_3D"), None)
    check("wireframe deja ver el interior",
          wire_space is not None and wire_space.shading.xray_alpha_wireframe < 1.0,
          str(None if wire_space is None else wire_space.shading.xray_alpha_wireframe))

    # Dos cubos en la misma línea de vista, a profundidad distinta: en wireframe
    # +xray, picar con ADD sobre el ya seleccionado debe dar el de detrás.
    cmd(client, "view.axis", {"axis": "FRONT"})
    cmd(client, "object.add", {"primitive": "CUBE", "x": 0.0, "y": -1.5, "z": 0.0})
    behind = cmd(client, "scene.get_state").get("active_object")
    cmd(client, "object.select_all", {"value": False})
    cmd(client, "object.select", {"names": [behind]})
    cmd(client, "view.frame_selected")
    cmd(client, "object.select_all", {"value": False})
    first_hit = cmd(client, "selection.pick", {"u": 0.5, "v": 0.5})
    check("SET coge el frente", first_hit.get("object") == behind, str(first_hit))
    set_hit = cmd(client, "selection.pick", {"u": 0.5, "v": 0.5, "mode": "SET"})
    check("SET repetido también pasa al objeto interior",
          set_hit.get("object") == cube, f"{set_hit.get('object')} != {cube}")
    cmd(client, "object.select", {"names": [behind]})
    add_hit = cmd(client, "selection.pick", {"u": 0.5, "v": 0.5, "mode": "ADD"})
    check("ADD sobre el seleccionado pasa al de detrás",
          add_hit.get("object") == cube, f"{add_hit.get('object')} != {cube}")
    cmd(client, "object.select", {"names": [behind]})
    cmd(client, "object.delete")

    # Subdivision cambia la topología evaluada. El toque en Edit debe resolverse
    # contra la jaula editable y devolver siempre un índice de cara original válido.
    cmd(client, "object.select", {"name": cube})
    subdivided = cmd(client, "modifier.add", {"type": "SUBSURF", "parameters": {"levels": 2}})
    edit_subsurf_name = next(m["name"] for m in subdivided["modifiers"] if m["type"] == "SUBSURF")
    cmd(client, "mode.edit")
    cmd(client, "selection.face")
    cmd(client, "selection.all", {"value": False})
    cmd(client, "view.axis", {"axis": "FRONT"})
    cmd(client, "view.frame_selected")
    cage_face = cmd(client, "selection.pick", {"u": 0.5, "v": 0.5})
    check("Edit con Subsurf selecciona una cara de la jaula",
          cage_face.get("hit") is True and cage_face.get("element") == "face"
          and 0 <= cage_face.get("index", -1) < len(bpy.data.objects[cube].data.polygons),
          str(cage_face))
    cmd(client, "mode.object")
    cmd(client, "modifier.remove", {"name": edit_subsurf_name})

    # Edit Mode + wireframe/xray: el vértice de detrás se ve y se tiene que poder
    # picar. En PERSP+FRONT la esquina trasera proyecta dentro de la silueta de la
    # cara frontal, desplazada `sep` de la esquina frontal: con un umbral justo
    # bajo `sep` solo la trasera es candidata, y con uno holgado caben las dos.
    cmd(client, "object.select", {"name": cube})
    cmd(client, "mode.edit")
    cmd(client, "selection.vertex")
    cmd(client, "selection.all", {"value": False})
    cmd(client, "view.axis", {"axis": "FRONT"})
    cmd(client, "view.perspective", {"mode": "PERSP"})
    cmd(client, "view.frame_all")
    time.sleep(0.3)

    import bmesh
    from mathutils import Vector

    from blender_tablet_remote.bpy_utils import find_view3d
    from blender_tablet_remote.camera import camera as tablet_camera

    rv3d = find_view3d()[3]
    matrix = bpy.data.objects[cube].matrix_world
    bm = bmesh.from_edit_mesh(bpy.data.objects[cube].data)
    front = next(v for v in bm.verts if tuple(round(c, 4) for c in v.co) == (1.0, -1.0, 1.0))
    back = next(v for v in bm.verts if tuple(round(c, 4) for c in v.co) == (1.0, 1.0, 1.0))
    p_front = tablet_camera.project(matrix @ front.co, rv3d)
    p_back = tablet_camera.project(matrix @ back.co, rv3d)
    check("proyeccion de la esquina disponible", p_front is not None and p_back is not None,
          f"{p_front} {p_back}")
    sep = ((p_front[0] - p_back[0]) ** 2 + (p_front[1] - p_back[1]) ** 2) ** 0.5
    check("perspectiva separa esquina frontal y trasera", 0.005 < sep < 0.3, f"sep={sep:.4f}")
    tight = min(0.25, sep * 0.6)
    wide = min(0.25, sep * 1.8)

    cmd(client, "view.shading", {"mode": "SOLID"})
    solid_hit = cmd(client, "selection.pick", {"u": p_back[0], "v": p_back[1], "threshold": tight})
    check("SOLID no pica el vertice de detras",
          solid_hit.get("index") != back.index, str(solid_hit))

    cmd(client, "view.shading", {"mode": "WIREFRAME"})
    through_hit = cmd(client, "selection.pick", {
        "u": p_back[0], "v": p_back[1], "threshold": tight, "mode": "SET",
    })
    check("wireframe+xray pica el vertice de detras",
          through_hit.get("index") == back.index, str(through_hit))

    # Tweak une el pick y el movimiento en un único gesto reversible.
    cmd(client, "selection.all", {"value": False})
    tweak_index = back.index
    tweak_start = back.co.copy()
    tweak_begin = cmd(client, "selection.tweak", {
        "phase": "BEGIN", "u": p_back[0], "v": p_back[1], "threshold": tight,
    })
    check("Tweak selecciona el vértice bajo el apoyo",
          tweak_begin.get("hit") is True and tweak_begin.get("index") == tweak_index,
          str(tweak_begin))
    cmd(client, "selection.tweak", {"phase": "UPDATE", "dx": 0.08, "dy": 0.0})
    bm = bmesh.from_edit_mesh(bpy.data.objects[cube].data)
    check("Tweak mueve durante el arrastre", (bm.verts[tweak_index].co - tweak_start).length > 1e-4,
          str(bm.verts[tweak_index].co))
    cmd(client, "selection.tweak", {"phase": "CANCEL"})
    bm = bmesh.from_edit_mesh(bpy.data.objects[cube].data)
    check("cancelar Tweak restaura", (bm.verts[tweak_index].co - tweak_start).length < 1e-6,
          str(bm.verts[tweak_index].co))

    cmd(client, "selection.tweak", {
        "phase": "BEGIN", "u": p_back[0], "v": p_back[1], "threshold": tight,
    })
    cmd(client, "selection.tweak", {"phase": "UPDATE", "dx": 0.08, "dy": 0.0})
    tweak_end = cmd(client, "selection.tweak", {"phase": "END"})
    check("soltar Tweak confirma", tweak_end.get("moved") is True, str(tweak_end))
    bm = bmesh.from_edit_mesh(bpy.data.objects[cube].data)
    bm.verts[tweak_index].co = tweak_start
    bmesh.update_edit_mesh(bpy.data.objects[cube].data, loop_triangles=False, destructive=False)
    back = bm.verts[tweak_index]

    cmd(client, "selection.edge")
    tweak_edge = back.link_edges[0]
    edge_midpoint = matrix @ ((tweak_edge.verts[0].co + tweak_edge.verts[1].co) * 0.5)
    edge_screen = tablet_camera.project(edge_midpoint, rv3d)
    edge_tweak = cmd(client, "selection.tweak", {
        "phase": "BEGIN", "u": edge_screen[0], "v": edge_screen[1], "threshold": 0.045,
    })
    check("Tweak también captura una arista",
          edge_tweak.get("hit") is True and edge_tweak.get("element") == "edge",
          str(edge_tweak))
    cmd(client, "selection.tweak", {"phase": "CANCEL"})
    cmd(client, "selection.vertex")
    bm = bmesh.from_edit_mesh(bpy.data.objects[cube].data)
    back = bm.verts[tweak_index]

    # En el vacío, Tweak se convierte en la navegación de un dedo y no abre MOVE.
    view_before_tweak_miss = cmd(client, "view.get")
    tweak_miss = cmd(client, "selection.tweak", {
        "phase": "BEGIN", "u": 0.02, "v": 0.02, "threshold": 0.01,
    })
    tweak_orbit = cmd(client, "selection.tweak", {
        "phase": "UPDATE", "dx": 0.08, "dy": 0.0,
    })
    cmd(client, "selection.tweak", {"phase": "END"})
    view_after_tweak_miss = cmd(client, "view.get")
    check("Tweak fuera de la malla orbita",
          tweak_miss.get("hit") is False and tweak_orbit.get("orbit") is True
          and view_before_tweak_miss.get("rotation") != view_after_tweak_miss.get("rotation"),
          f"{tweak_miss} {tweak_orbit}")
    cmd(client, "view.set", view_before_tweak_miss)

    # El camino parte del vértice ACTIVO, y entre medias el escenario ha tocado la
    # selección: se vuelve a fijar `back` como activo para no medir desde otro sitio.
    p_back_again = tablet_camera.project(matrix @ back.co, rv3d)
    cmd(client, "selection.pick", {
        "u": p_back_again[0], "v": p_back_again[1], "threshold": wide, "mode": "SET",
    })

    # Se busca por anchura un vértice a distancia topológica exacta 2, en vez de fiarse
    # de que un vecino cualquiera caiga lejos: con un vecino directo el camino mide 1 y
    # no prueba nada, y antes colaba de casualidad porque la topología que dejaba el
    # Knife viejo (abanico de triángulos) lo alejaba.
    distancias = {back: 0}
    cola = [back]
    destination = None
    while cola and destination is None:
        actual = cola.pop(0)
        for edge in actual.link_edges:
            vecino = edge.other_vert(actual)
            if vecino in distancias:
                continue
            distancias[vecino] = distancias[actual] + 1
            if distancias[vecino] == 2:
                destination = vecino
                break
            cola.append(vecino)
    check("hay un vértice a dos saltos", destination is not None, str(len(distancias)))
    p_destination = tablet_camera.project(matrix @ destination.co, rv3d)
    check("destino vecino del camino está proyectado", p_destination is not None, str(p_destination))
    path_hit = cmd(client, "selection.shortest_path", {
        "u": p_destination[0], "v": p_destination[1], "threshold": 0.045,
    })
    check("Ctrl+toque selecciona el camino hasta el destino",
          path_hit.get("index") == destination.index and path_hit.get("path_length", 0) >= 2,
          str(path_hit))

    cmd(client, "selection.all", {"value": False})
    cycle_hit = cmd(client, "selection.pick", {
        "u": p_back[0], "v": p_back[1], "threshold": wide, "mode": "ADD",
    })
    check("ADD conserva el vertice exacto bajo el dedo",
          cycle_hit.get("index") == back.index, str(cycle_hit))
    info = cmd(client, "selection.info")
    check("ADD no incorpora una esquina cercana que no se tocó",
          info.get("verts", []) == [back.index], str(info))

    cmd(client, "selection.all", {"value": False})
    cmd(client, "mode.object")

    # Caja en Object Mode: engloba la mitad de la pantalla y debe caer el cubo.
    cmd(client, "object.select_all", {"value": False})
    cmd(client, "view.frame_all")
    boxed = cmd(client, "selection.box", {"u0": 0.2, "v0": 0.2, "u1": 0.8, "v1": 0.8, "mode": "ADD"})
    check("la caja seleccionó algo", boxed.get("affected", 0) >= 1, str(boxed))
    check("y volvió la selección", bool(boxed.get("selected_objects")), str(boxed))
    cmd(client, "view.shading", {"mode": "SOLID"})

    print("\n[11b] Loop Cut: colocar el corte con el toque", flush=True)
    cmd(client, "object.select", {"names": [cube]})
    cmd(client, "mode.edit")
    cmd(client, "view.axis", {"axis": "FRONT"})
    cmd(client, "view.perspective", {"mode": "ORTHO"})
    cmd(client, "view.frame_all")
    time.sleep(0.3)

    # La arista vertical frontal del cubo, vista de frente: tocarla a 3/4 de
    # altura debe devolver esa arista y el factor que coloca el corte ahí.
    rv3d = find_view3d()[3]
    matrix = bpy.data.objects[cube].matrix_world
    bm = bmesh.from_edit_mesh(bpy.data.objects[cube].data)
    top = next(v for v in bm.verts if tuple(round(c, 4) for c in v.co) == (1.0, -1.0, 1.0))
    bottom = next(v for v in bm.verts if tuple(round(c, 4) for c in v.co) == (1.0, -1.0, -1.0))
    ring_edge = next(e for e in bm.edges if {v.index for v in e.verts} == {top.index, bottom.index})
    ring_edge_index = ring_edge.index
    # La sesión de herramienta restaura la malla: los BMEdge capturados caducan.
    ring_v0 = ring_edge.verts[0].co
    p_top = tablet_camera.project(matrix @ top.co, rv3d)
    p_bottom = tablet_camera.project(matrix @ bottom.co, rv3d)
    p0 = tablet_camera.project(matrix @ ring_v0, rv3d)
    p1 = tablet_camera.project(matrix @ ring_edge.verts[1].co, rv3d)
    span = Vector(p1) - Vector(p0)
    # Toque al 75% desde verts[0]: el factor esperado sale de esa orientación.
    touch = (Vector(p0) + span * 0.75)
    expected_factor = 2 * 0.75 - 1
    probe = cmd(client, "mesh.loop_probe", {"u": touch.x, "v": touch.y})
    check("el sondeo acierta la arista", probe.get("hit") is True and probe.get("edge") == ring_edge_index, str(probe))
    check("y el factor coloca el corte bajo el dedo",
          abs((probe.get("factor") or 9.0) - expected_factor) < 0.02, str(probe))

    miss = cmd(client, "mesh.loop_probe", {"u": 0.02, "v": 0.02})
    check("tocar el vacío no acierta", miss.get("hit") is False, str(miss))

    begun = cmd(client, "tool.begin", {"tool": "LOOP_CUT", "edge": ring_edge_index,
                                       "parameters": {"cuts": 1, "factor": 0.0}})
    check("sesión loop cut", begun.get("active") is True, str(begun))
    # El anillo del cubo son 4 aristas: un corte = 4 vértices nuevos encima de los
    # 8 originales, y el re-target no cambia la cuenta (sigue siendo UN corte).
    original_verts = cmd(client, "mesh.info")["verts"] - 4
    retarget = cmd(client, "tool.loop_pick", {"u": touch.x, "v": touch.y})
    pick = retarget.get("pick") or {}
    params = retarget.get("parameters") or {}
    check("loop_pick re-ubica con el toque", retarget.get("active") is True and pick.get("hit") is True, str(retarget))
    check("la sesión toma edge y factor del sondeo",
          params.get("edge") == ring_edge_index and abs((params.get("factor") or 9.0) - expected_factor) < 0.02,
          str(params))
    cut_verts = cmd(client, "mesh.info")["verts"]
    check("el preview sigue siendo un corte del anillo", cut_verts == original_verts + 4,
          f"{original_verts} -> {cut_verts}")
    added = cmd(client, "tool.loop_pick", {"u": touch.x, "v": touch.y, "add": True})
    multi_verts = cmd(client, "mesh.info")["verts"]
    check("Mayús/add acumula un segundo loop",
          added.get("loop_count") == 2 and multi_verts > cut_verts,
          f"{added} | {cut_verts} -> {multi_verts}")
    popped = cmd(client, "tool.loop_pop")
    pop_verts = cmd(client, "mesh.info")["verts"]
    check("loop_pop vuelve al corte anterior editable",
          popped.get("loop_count") == 1 and pop_verts == cut_verts,
          f"{popped} | {pop_verts}")
    cmd(client, "tool.cancel")
    restored = cmd(client, "mesh.info")["verts"]
    check("cancelar restaura la topología", restored == original_verts, str(restored))
    cmd(client, "mode.object")

    print("\n[12] Snap continuo sin rejilla modal", flush=True)
    # Vista FRONT: el nudge en pantalla mueve a lo largo del eje X de mundo, así las
    # posiciones son comparables y los múltiplos del paso se pueden comprobar.
    cmd(client, "object.select", {"name": cube})
    cmd(client, "view.axis", {"axis": "FRONT"})
    cmd(client, "transform.move", {"x": 0.0, "y": 0.0, "z": 0.0, "absolute": True})
    time.sleep(0.2)

    # MOVE + INCREMENT: una sola sesión, varios nudges espaciados -> posiciones
    # progresivas. El snap cuantiza el acumulado en vivo, no reinicia en cada nudge.
    cmd(client, "transform.begin", {"mode": "MOVE", "snap": True, "snap_type": "INCREMENT", "step": 0.05})
    positions = []
    for _ in range(8):
        nudged = cmd(client, "transform.nudge", {"dx": 0.06, "dy": 0.0})
        positions.append(nudged["values"][0])
    distinct = len({round(v, 4) for v in positions})
    check("INCREMENT acumula posiciones progresivas", distinct >= 3, f"{distinct}: {positions}")
    # La comparación va en unidades de mundo: dividir entre el paso y pedir 1e-6
    # multiplica el error de float32 de `location` por 20 y falla por un ulp.
    check("los saltos de INCREMENT son múltiplos del paso",
          all(abs(v - round(v / 0.05) * 0.05) < 1e-6 for v in positions), str(positions))
    cmd(client, "transform.cancel")
    time.sleep(0.2)

    print("\n[13] Signo del giro de cámara", flush=True)
    # El yaw es sobre el eje vertical LOCAL de la cámara (no el Z global): así el
    # arrastre horizontal conserva su sentido visual aunque la cámara quede boca
    # abajo. `dx>0` debe girar la cámara alrededor de su eje "up" con ángulo negativo,
    # y `dy>0` alrededor del eje "right" (pitch sin cambios). Se comprueba la rotación
    # RELATIVA, no un punto proyectado, que ya causó inversiones erróneas.
    before_rot = tablet_camera.rotation.copy()
    up_before = before_rot @ Vector((0.0, 1.0, 0.0))
    drag(client, "orbit", dx=0.1)
    time.sleep(0.3)
    rel = (tablet_camera.rotation @ before_rot.inverted()).normalized()
    check("dedo a la derecha gira sobre el eje vertical local",
          rel.axis.dot(up_before) < -0.9 and rel.angle > 0.1,
          f"up={[round(c, 3) for c in up_before]} axis={[round(c, 3) for c in rel.axis]} angle={rel.angle:.3f}")

    before_rot = tablet_camera.rotation.copy()
    drag(client, "orbit", dy=0.1)
    time.sleep(0.3)
    rel = (tablet_camera.rotation @ before_rot.inverted()).normalized()
    right = before_rot @ Vector((1.0, 0.0, 0.0))
    check("dedo abajo gira la cámara sobre el eje derecha",
          rel.angle > 0.1 and rel.axis.dot(right) < -0.9,
          f"right={[round(c, 3) for c in right]} axis={[round(c, 3) for c in rel.axis]} angle={rel.angle:.3f}")

    print("\n[14] Giro horizontal consistente desde BACK y BOTTOM", flush=True)
    # La escena debe acompañar al dedo sea cual sea el lado desde el que se mire.
    # Se mide con el vector FORWARD de la cámara: tras un arrastre hacia la derecha,
    # el forward debe inclinarse hacia el lado DERECHO de la pantalla con la semántica
    # observada en el dispositivo real. Cubre BACK y BOTTOM, las dos
    # orientaciones donde el yaw sobre Z global fallaba.
    for axis in ("BACK", "BOTTOM"):
        cmd(client, "view.axis", {"axis": axis})
        time.sleep(0.3)
        before = tablet_camera.rotation.copy()
        right_before = before @ Vector((1.0, 0.0, 0.0))
        forward_before = before @ Vector((0.0, 0.0, -1.0))
        drag(client, "orbit", dx=0.1)
        time.sleep(0.3)
        after = tablet_camera.rotation.copy()
        forward_after = after @ Vector((0.0, 0.0, -1.0))
        shift = (forward_after - forward_before).dot(right_before)
        check(f"desde {axis}, dedo a la derecha mueve la escena a la derecha",
              shift > 1e-4,
              f"shift={shift:.4f} axis={[round(c, 3) for c in before.axis]}")

    print("\n[15] Knife: colocar puntos desde la cámara", flush=True)
    cmd(client, "object.select", {"name": cube})
    cmd(client, "mode.edit")
    cmd(client, "selection.face")
    cmd(client, "view.axis", {"axis": "FRONT"})
    cmd(client, "view.frame_all")
    time.sleep(0.3)
    before = cmd(client, "mesh.info")
    begun = cmd(client, "tool.begin", {"tool": "KNIFE"})
    check("sesión knife", begun.get("active") is True and begun.get("tool") == "KNIFE", str(begun))
    # El sondeo inicial se dirige al centro real de una arista de la cara que mira
    # a la cámara: unas coordenadas fijas caen dentro de la cara y el candidato
    # sería FACE, que es la respuesta correcta pero no la que se quiere medir.
    # Como en [4], se entra un 3 % hacia el centro de la cara para que el raycast
    # no se escape por la silueta.
    import bmesh as knife_bmesh

    knife_rv3d = snap_find_view3d()[3]
    knife_bm = knife_bmesh.from_edit_mesh(snap_obj.data)
    view_dir = snap_rv3d.view_rotation @ SnapVector((0.0, 0.0, -1.0))
    normal_matrix = snap_obj.matrix_world.to_3x3()
    facing = min(knife_bm.faces, key=lambda f: (normal_matrix @ f.normal).normalized().dot(view_dir))
    knife_edge = facing.edges[0]
    knife_edge_world = snap_obj.matrix_world @ (
        (knife_edge.verts[0].co + knife_edge.verts[1].co) * 0.5)
    knife_edge_screen = snap_camera.project(knife_edge_world, knife_rv3d)
    knife_face_screen = snap_camera.project(
        snap_obj.matrix_world @ facing.calc_center_median(), knife_rv3d)
    knife_probe = (
        knife_edge_screen[0] * .97 + knife_face_screen[0] * .03,
        knife_edge_screen[1] * .97 + knife_face_screen[1] * .03,
    )
    first = cmd(client, "tool.knife_drag",
                {"phase": "BEGIN", "u": knife_probe[0], "v": knife_probe[1]})
    check("inicio de arrastre acierta", first.get("hit") is True, str(first))
    check("centro de arista es un snap propio",
          (first.get("candidate") or {}).get("snap_type") == "EDGE_CENTER", str(first))
    check("el centro de arista snapea a la posición exacta",
          (SnapVector((first.get("candidate") or {}).get("position") or (0, 0, 0))
           - knife_edge_world).length < 1e-5, str(first.get("candidate")))
    hover = cmd(client, "tool.knife_drag", {"phase": "UPDATE", "u": 0.5, "v": 0.5})
    check("hover publica candidato de cara", (hover.get("candidate") or {}).get("snap_type") in {"FACE", "EDGE", "VERTEX"}, str(hover))
    one = cmd(client, "mesh.info")
    check("mover sin soltar no corta", one["verts"] == before["verts"], f"{before} -> {one}")
    first_end = cmd(client, "tool.knife_drag", {"phase": "END", "u": knife_probe[0], "v": knife_probe[1]})
    check("primer gesto fija solo un punto", first_end.get("hit") is True
          and len(first_end.get("projected_points", [])) == 1, str(first_end))
    cmd(client, "tool.knife_drag", {"phase": "BEGIN", "u": 0.5, "v": 0.65})
    second_end = cmd(client, "tool.knife_drag", {"phase": "END", "u": 0.5, "v": 0.65})
    check("segundo punto crea el primer segmento", second_end.get("hit") is True
          and len(second_end.get("projected_points", [])) == 2, str(second_end))
    cut = cmd(client, "mesh.info")
    check("dos puntos solo cambian overlay antes de confirmar", cut["verts"] == before["verts"], f"{before} -> {cut}")
    miss = cmd(client, "tool.knife_drag", {"phase": "UPDATE", "u": 0.01, "v": 0.01})
    check("punto en el vacío no altera", miss.get("hit") is False, str(miss))
    cmd(client, "tool.knife_pop")
    popped = cmd(client, "mesh.info")
    check("pop retira el último corte", popped["verts"] == before["verts"], f"{before} -> {popped}")
    cmd(client, "tool.cancel")
    restored = cmd(client, "mesh.info")
    check("cancel restaura la topología", restored["verts"] == before["verts"], str(restored))
    cmd(client, "mode.object")

    print("\n[16] Roll de cámara (rueda de dos dedos)", flush=True)
    cmd(client, "object.select", {"name": cube})
    cmd(client, "view.axis", {"axis": "FRONT"})
    cmd(client, "view.frame_all")
    time.sleep(0.3)
    roll_before = tablet_camera.rotation.copy()
    roll_forward = roll_before @ Vector((0.0, 0.0, -1.0))
    rv3d_roll = find_view3d()[3]
    matrix_roll = bpy.data.objects[cube].matrix_world
    top_center = tablet_camera.project(matrix_roll @ Vector((0.0, 0.0, 1.0)), rv3d_roll)
    cmd(client, "view.roll", {"angle": 0.4})
    time.sleep(0.3)
    roll_after = tablet_camera.rotation.copy()
    rel = (roll_after @ roll_before.inverted()).normalized()
    check("roll gira sobre el eje de visión",
          abs(rel.axis.dot(roll_forward)) > 0.9 and rel.angle > 0.1,
          f"forward={[round(c, 3) for c in roll_forward]} axis={[round(c, 3) for c in rel.axis]} angle={rel.angle:.3f}")
    top_after = tablet_camera.project(matrix_roll @ Vector((0.0, 0.0, 1.0)), rv3d_roll)
    check("rueda horaria mueve la parte superior a la derecha",
          top_center is not None and top_after is not None and top_after[0] > top_center[0],
          f"{top_center} -> {top_after}")
    cmd(client, "view.axis", {"axis": "FRONT"})


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
        },
    )
    threading.Thread(target=run, name="gui-tests", daemon=True).start()
    return None


bpy.app.timers.register(start, first_interval=2.0)
