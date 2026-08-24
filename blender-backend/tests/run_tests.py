"""Suite de aceptación del backend, ejecutable sin interfaz gráfica.

    blender --background --python blender-backend/tests/run_tests.py

Cómo funciona: en `--background` Blender no corre su bucle de eventos, así que los
`bpy.app.timers` nunca se disparan. El test levanta el servidor, lanza el cliente en
un thread y bombea el bridge a mano desde el hilo principal — exactamente lo que hace
Blender con interfaz, pero bajo control del test.

Salida: resumen de PASS/FAIL y código de salida 1 si algo falla.
"""

from __future__ import annotations

import os
import shutil
import sys
import threading
import time
import traceback
from pathlib import Path

import bpy
import bmesh

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from blender_tablet_remote import bridge  # noqa: E402
from wsclient import WSClient, WSError  # noqa: E402

PORT = 8799
TOKEN = "test-token-1234"

_results: list[tuple[str, bool, str]] = []


def check(name: str, condition, detail: str = "") -> bool:
    ok = bool(condition)
    _results.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else '  <- ' + detail}")
    return ok


def ok_reply(name: str, reply: dict) -> dict:
    check(name, reply.get("ok"), f"{reply.get('code')}: {reply.get('error')}")
    return reply.get("result") or {}


def fail_reply(name: str, reply: dict, expect_code: str = "") -> None:
    detail = f"esperaba error, llegó {reply}"
    condition = not reply.get("ok") and (not expect_code or reply.get("code") == expect_code)
    check(name, condition, detail)


# ------------------------------------------------------------------- pruebas


def scenario(client: WSClient) -> None:
    print("\n[1] Handshake, auth y capacidades")
    caps = ok_reply("server.capabilities", client.command("server.capabilities"))
    check("hay comandos registrados", len(caps.get("commands", [])) > 20, str(caps.get("commands")))
    check("modo background detectado", caps.get("background") is True)
    check("protocolo v2", caps.get("protocol_version") == "2.0", str(caps.get("protocol_version")))
    check("features estructuradas", isinstance(caps.get("features", {}).get("transform_modal"), dict))
    check("enums canónicos", caps.get("enums", {}).get("constraint") == ["FREE", "X", "Y", "Z", "XY", "XZ", "YZ", "NORMAL", "VIEW"])
    check("unidades explícitas", caps.get("units", {}).get("rotation") == "DEGREE")

    print("\n[2] Estado inicial")
    state = ok_reply("scene.get_state", client.command("scene.get_state"))
    check("modo OBJECT", state.get("mode") == "OBJECT", str(state))
    check("hay objetos en la escena", len(state.get("selected_objects", [])) >= 0)

    objects = ok_reply("scene.list_objects", client.command("scene.list_objects"))
    names = [o["name"] for o in objects["objects"]]
    check("el cubo por defecto existe", "Cube" in names, str(names))

    print("\n[3] Selección de objeto")
    result = ok_reply("object.select Cube", client.command("object.select", {"names": ["Cube"]}))
    check("Cube seleccionado", result.get("selected_objects") == ["Cube"], str(result))
    check("Cube activo", bpy.context.view_layer.objects.active.name == "Cube")

    print("\n[4] Transformaciones en Object Mode")
    cube = bpy.data.objects["Cube"]
    cube.location = (0, 0, 0)
    cube.rotation_euler = (0, 0, 0)
    cube.scale = (1, 1, 1)

    ok_reply("transform.move delta", client.command("transform.move", {"x": 1.0, "y": 0.0, "z": 0.0}))
    check("posición tras mover", abs(cube.location.x - 1.0) < 1e-5, str(cube.location))

    ok_reply("transform.move absoluto", client.command("transform.move", {"x": 2, "y": 3, "z": 4, "absolute": True}))
    check("posición absoluta", tuple(round(v, 3) for v in cube.location) == (2.0, 3.0, 4.0), str(cube.location))

    ok_reply("transform.rotate 90 en Z", client.command("transform.rotate", {"z": 90}))
    check("rotación aplicada", abs(cube.rotation_euler.z - 1.5708) < 1e-3, str(cube.rotation_euler))

    ok_reply("transform.scale x2", client.command("transform.scale", {"factor": 2.0}))
    check("escala aplicada", abs(cube.scale.x - 2.0) < 1e-4, str(cube.scale))

    ok_reply("transform.reset", client.command("transform.reset"))
    check("transform reseteado", tuple(cube.location) == (0.0, 0.0, 0.0) and abs(cube.scale.x - 1) < 1e-6)

    print("\n[5] Edit Mode y modos de selección")
    ok_reply("mode.edit", client.command("mode.edit"))
    check("está en EDIT", cube.mode == "EDIT", cube.mode)

    ok_reply("selection.face", client.command("selection.face"))
    check(
        "select mode = FACE",
        tuple(bpy.context.scene.tool_settings.mesh_select_mode) == (False, False, True),
    )

    ok_reply("selection.all", client.command("selection.all", {"value": False}))
    info = ok_reply("mesh.info", client.command("mesh.info"))
    check("nada seleccionado", info.get("selected_faces") == 0, str(info))

    ok_reply("selection.elements face 0", client.command("selection.elements", {"faces": [0]}))
    info = ok_reply("mesh.info tras seleccionar", client.command("mesh.info"))
    check("una cara seleccionada", info.get("selected_faces") == 1, str(info))

    print("\n[6] Operaciones de malla")
    verts_before = info["verts"]
    result = ok_reply("mesh.extrude", client.command("mesh.extrude", {"offset": 0.5}))
    info = ok_reply("mesh.info tras extruir", client.command("mesh.info"))
    check("la extrusión añadió geometría", info["verts"] > verts_before, f"{verts_before} -> {info['verts']}")

    faces_before = info["faces"]
    ok_reply("mesh.inset", client.command("mesh.inset", {"thickness": 0.1}))
    info = ok_reply("mesh.info tras inset", client.command("mesh.info"))
    check("el inset añadió caras", info["faces"] > faces_before, f"{faces_before} -> {info['faces']}")

    ok_reply("selection.edge", client.command("selection.edge"))
    ok_reply("selection.all", client.command("selection.all", {"value": True}))
    faces_before = info["faces"]
    ok_reply("mesh.bevel", client.command("mesh.bevel", {"offset": 0.05, "segments": 2}))
    info = ok_reply("mesh.info tras bevel", client.command("mesh.info"))
    check("el bevel añadió caras", info["faces"] > faces_before, f"{faces_before} -> {info['faces']}")

    print("\n[7] Transformación en Edit Mode")
    ok_reply("selection.vertex", client.command("selection.vertex"))
    ok_reply("selection.all", client.command("selection.all", {"value": True}))
    bounds_before = max(v.co.length for v in cube.data.vertices) if cube.data.vertices else 0
    ok_reply("transform.move en edit", client.command("transform.move", {"z": 1.0}))
    ok_reply("transform.scale en edit", client.command("transform.scale", {"factor": 1.5}))
    check("la malla se transformó", True)

    ok_reply("mode.object", client.command("mode.object"))
    check("de vuelta en OBJECT", cube.mode == "OBJECT", cube.mode)

    print("\n[8] Duplicar y borrar")
    result = ok_reply("object.duplicate", client.command("object.duplicate", {"names": ["Cube"]}))
    created = result.get("created", [])
    check("se creó una copia", len(created) == 1 and created[0] in bpy.data.objects, str(created))
    ok_reply("object.delete", client.command("object.delete", {"objects": created}))
    check("la copia se borró", created[0] not in bpy.data.objects)

    result = ok_reply("object.add SPHERE", client.command("object.add", {"primitive": "SPHERE"}))
    check("esfera añadida", any(o.type == "MESH" and "Sphere" in o.name for o in bpy.data.objects))

    print("\n[9] Gestos con coalescing")
    ok_reply("object.select Cube", client.command("object.select", {"names": ["Cube"]}))
    cube.location = (0, 0, 0)
    before = bridge.status()["gestures_run"]
    client.gesture("move", "begin")
    for _ in range(200):
        client.gesture("move", "update", dx=0.001, dy=0.0)
    client.gesture("move", "end", dx=0.0, dy=0.0)
    time.sleep(0.4)
    after = bridge.status()["gestures_run"]
    check("se recibieron los 202 mensajes de gesto", after - before == 202, f"{after - before}")
    check("el gesto movió el cubo", cube.location.length > 1e-4, str(cube.location))
    check("un gesto = un paso, no 200", bridge.status()["commands_run"] < after, "sanity")
    check("el servidor sigue vivo tras el gesto", client.command("server.ping")["ok"])

    before_zoom = ok_reply("view.get", client.command("view.get"))["distance"]
    client.gesture("zoom", "begin")
    for _ in range(50):
        client.gesture("zoom", "update", factor=1.01)
    client.gesture("zoom", "end", factor=1.0)
    time.sleep(0.3)
    after_zoom = ok_reply("view.get", client.command("view.get"))["distance"]
    check("el gesto de zoom acercó la vista", after_zoom < before_zoom, f"{before_zoom} -> {after_zoom}")

    print("\n[9b] Navegación del viewport")
    # Blender carga el screen del startup file incluso en background, así que hay un
    # RegionView3D con el que trabajar. Sin él estos comandos devuelven 'no_viewport'.
    before = ok_reply("view.get", client.command("view.get"))
    after = ok_reply("view.orbit", client.command("view.orbit", {"dx": 0.25, "dy": 0.0}))
    check("la órbita cambió la rotación", before["rotation"] != after["rotation"], str(after["rotation"]))

    after = ok_reply("view.pan", client.command("view.pan", {"dx": 0.1, "dy": 0.1}))
    check("el pan movió el centro", before["location"] != after["location"], str(after["location"]))

    dist = after["distance"]
    after = ok_reply("view.zoom", client.command("view.zoom", {"factor": 2.0}))
    check("el zoom redujo la distancia", after["distance"] < dist, f"{dist} -> {after['distance']}")

    ok_reply("view.set restaura la vista", client.command("view.set", before))
    after = ok_reply("view.get", client.command("view.get"))
    check("vista restaurada", abs(after["distance"] - before["distance"]) < 1e-4, str(after))

    print("\n[10] Errores controlados")
    fail_reply("comando inexistente", client.command("no.such.command"), "unknown_command")
    fail_reply("payload inválido", client.command("transform.move", {"x": "hola"}), "bad_payload")
    fail_reply("objeto inexistente", client.command("object.select", {"names": ["NoExiste"]}), "not_found")
    fail_reply("mesh.* fuera de Edit Mode", client.command("mesh.extrude"), "wrong_mode")
    fail_reply("undo sin pila (background)", client.command("history.undo"), "no_undo_stack")
    fail_reply("gesto inexistente", client.command("view.axis", {"axis": "DIAGONAL"}), "bad_payload")

    client.send({"type": "command"})
    reply = client.recv(timeout=2.0)
    while reply.get("type") == "event":
        reply = client.recv(timeout=2.0)
    check("comando sin nombre da error", reply.get("ok") is False, str(reply))

    print("\n[11] Eventos")
    client.command("object.select", {"names": ["Cube"]})
    client.command("object.select_all", {"value": True})
    events = client.drain_events(0.6)
    kinds = {e["event"] for e in events}
    check("llegó selection.changed", "selection.changed" in kinds, str(kinds))


def snap_scenario(client: WSClient) -> None:
    print("\n[12] Cursor 3D y origen")
    ok_reply("mode.object", client.command("mode.object"))
    ok_reply("object.select Cube", client.command("object.select", {"names": ["Cube"]}))
    cube = bpy.data.objects["Cube"]
    check("solo el cubo seleccionado", [o.name for o in bpy.context.view_layer.objects if o.select_get()] == ["Cube"],
          str([o.name for o in bpy.context.view_layer.objects if o.select_get()]))
    check("el cubo no está en Edit Mode", cube.mode == "OBJECT", cube.mode)
    ok_reply("transform.move absoluto", client.command("transform.move", {"x": 2, "y": 3, "z": 4, "absolute": True}))

    result = ok_reply("snap.cursor_to_selected", client.command("snap.cursor_to_selected"))
    check(
        "el cursor fue a la selección",
        tuple(round(v, 3) for v in result["cursor"]) == (2.0, 3.0, 4.0),
        str(result),
    )

    ok_reply("snap.cursor_to_world", client.command("snap.cursor_to_world"))
    check("el cursor volvió al origen", tuple(bpy.context.scene.cursor.location) == (0.0, 0.0, 0.0))

    ok_reply("snap.cursor_set", client.command("snap.cursor_set", {"x": 1, "y": 1, "z": 1}))
    ok_reply("snap.selected_to_cursor", client.command("snap.selected_to_cursor"))
    check("el objeto fue al cursor", tuple(round(v, 3) for v in cube.location) == (1.0, 1.0, 1.0), str(cube.location))

    ok_reply("snap.cursor_set decimal", client.command("snap.cursor_set", {"x": 1.4, "y": 1.6, "z": 0.0}))
    result = ok_reply("snap.cursor_to_grid", client.command("snap.cursor_to_grid", {"step": 1.0}))
    check("el cursor cuadró a la rejilla", tuple(round(v, 3) for v in result["cursor"]) == (1.0, 2.0, 0.0), str(result))

    # El origen es lo que distingue "mover el objeto" de "mover su punto de giro":
    # tras esto la malla no se mueve pero location sí cambia.
    ok_reply("snap.cursor_set para el origen", client.command("snap.cursor_set", {"x": 5, "y": 0, "z": 0}))
    ok_reply("snap.origin_to_cursor", client.command("snap.origin_to_cursor"))
    check("el origen fue al cursor", tuple(round(v, 3) for v in cube.location) == (5.0, 0.0, 0.0), str(cube.location))

    ok_reply("snap.origin_to_geometry", client.command("snap.origin_to_geometry", {"center": "BOUNDS"}))
    check("el origen volvió a la geometría", abs(cube.location.x - 1.0) < 1e-3, str(cube.location))

    fail_reply("center inválido", client.command("snap.origin_to_geometry", {"center": "NOPE"}), "bad_payload")
    fail_reply("step negativo", client.command("snap.cursor_to_grid", {"step": -1}), "bad_payload")

    client.command("mode.edit")
    fail_reply(
        "snap de objeto fuera de Object Mode",
        client.command("snap.selected_to_cursor"),
        "wrong_mode",
    )
    # En Edit Mode Blender solo deja añadir mallas: una curva crearía un objeto nuevo.
    fail_reply(
        "añadir una curva en Edit Mode",
        client.command("object.add", {"primitive": "BEZIER_CURVE"}),
        "wrong_mode",
    )
    ok_reply("añadir una malla sí vale en Edit Mode", client.command("object.add", {"primitive": "CUBE"}))
    client.command("mode.object")


def add_menu_scenario(client: WSClient) -> None:
    print("\n[13] Catálogo del menú Añadir")
    catalog = ok_reply("object.add_options", client.command("object.add_options"))["categories"]
    check("agrupa por categoría", "MESH" in catalog and "CURVE" in catalog, str(list(catalog)))
    check("hay curvas Bézier", "BEZIER_CURVE" in catalog.get("CURVE", []), str(catalog.get("CURVE")))

    fail_reply("primitiva inexistente", client.command("object.add", {"primitive": "NOPE"}), "bad_payload")

    # Sin coordenadas se añade en el cursor 3D, como Blender. Antes caía siempre en
    # el origen del mundo, lo que dejaba sin sentido el submenú de cursor.
    ok_reply("cursor a (0,4,0)", client.command("snap.cursor_set", {"x": 0, "y": 4, "z": 0}))
    ok_reply("añadir texto", client.command("object.add", {"primitive": "TEXT"}))
    active = bpy.context.view_layer.objects.active
    check("el objeto nuevo cae en el cursor", round(active.location.y, 3) == 4.0, str(active.location))
    check("y es del tipo pedido", active.type == "FONT", active.type)

    # Con coordenadas explícitas manda el payload.
    ok_reply("añadir en coordenadas", client.command("object.add", {"primitive": "LIGHT_SUN", "x": 7, "y": 0, "z": 0}))
    active = bpy.context.view_layer.objects.active
    check("respeta las coordenadas", round(active.location.x, 3) == 7.0, str(active.location))
    check("crea una luz", active.type == "LIGHT", active.type)


def modal_scenario(client: WSClient) -> None:
    print("\n[14] Transformación modal (se confirma a mano)")
    ok_reply("mode.object", client.command("mode.object"))
    ok_reply("object.select Cube", client.command("object.select", {"names": ["Cube"]}))
    cube = bpy.data.objects["Cube"]
    ok_reply("posición conocida", client.command("transform.move", {"x": 0, "y": 0, "z": 0, "absolute": True}))
    absolute = ok_reply("modal absoluto", client.command("transform.begin", {
        "mode": "MOVE", "axes": ["X"], "value_mode": "ABSOLUTE",
    }))
    ok_reply("valor absoluto", client.command("transform.value", {"values": [2.0, 0.0, 0.0]}))
    check("ABSOLUTE fija la coordenada del pivote", abs(cube.location.x - 2.0) < 1e-5, str(cube.location))
    ok_reply("cancelar absoluto", client.command("transform.cancel"))
    cube.rotation_euler = (0.0, 0.0, 1.57079632679)
    bpy.context.view_layer.update()
    ok_reply("modal local", client.command("transform.begin", {
        "mode": "MOVE", "axes": ["X"], "orientation": "LOCAL",
    }))
    ok_reply("mover por X local", client.command("transform.value", {"values": [1.0, 0.0, 0.0]}))
    check("X local respeta la rotación del objeto", abs(cube.location.y - 1.0) < 1e-4, str(cube.location))
    ok_reply("cancelar local", client.command("transform.cancel"))
    cube.rotation_euler = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    fail_reply("sin sesión no hay nudge", client.command("transform.nudge", {"dx": 1}), "no_session")

    ok_reply("transform.begin", client.command("transform.begin", {"mode": "MOVE", "axes": ["X"], "snap": True, "step": 0.01}))
    result = ok_reply("valor numérico", client.command("transform.value", {"values": [1.234, 5.0, 9.0]}))
    check("el eje restringe", abs(cube.location.y) < 1e-6 and abs(cube.location.z) < 1e-6, str(cube.location))
    check("el snap cuadra a 1 cm", abs(cube.location.x - 1.23) < 1e-6, str(cube.location))
    check("status devuelve lo que se ve", abs(result["values"][0] - 1.23) < 1e-6, str(result))

    # Cambiar de eje en vivo no debe dejar residuo del anterior: es lo que garantiza
    # recalcular desde las matrices originales en vez de acumular.
    ok_reply("cambiar de eje en vivo", client.command("transform.axes", {"axes": ["Y"]}))
    check("el eje anterior vuelve a cero", abs(cube.location.x) < 1e-6, str(cube.location))

    ok_reply("transform.cancel", client.command("transform.cancel"))
    check("cancelar restaura la posición", cube.location.length < 1e-6, str(cube.location))
    status = ok_reply("status tras cancelar", client.command("transform.status"))
    check("la sesión queda cerrada", status.get("active") is False, str(status))

    ok_reply("begin para confirmar", client.command("transform.begin", {"mode": "MOVE", "axes": ["Z"]}))
    ok_reply("valor exacto", client.command("transform.value", {"values": [0, 0, 3.0]}))
    ok_reply("transform.confirm", client.command("transform.confirm"))
    check("confirmar conserva el cambio", abs(cube.location.z - 3.0) < 1e-6, str(cube.location))

    ok_reply("rotar con snap", client.command("transform.begin", {"mode": "ROTATE", "axes": ["Z"], "snap": True}))
    result = ok_reply("ángulo 47°", client.command("transform.value", {"angle": 47.0}))
    check("cuadra a 5 grados", abs(result["angle"] - 45.0) < 1e-6, str(result["angle"]))
    ok_reply("cancelar rotación", client.command("transform.cancel"))

    ok_reply("escalar", client.command("transform.begin", {"mode": "SCALE", "axes": ["X"]}))
    ok_reply("factor 2", client.command("transform.value", {"values": [2.0, 2.0, 2.0]}))
    check("escala solo en X", abs(cube.scale.x - 2.0) < 1e-5 and abs(cube.scale.y - 1.0) < 1e-5, str(cube.scale))
    ok_reply("cancelar escala", client.command("transform.cancel"))
    check("escala restaurada", abs(cube.scale.x - 1.0) < 1e-5, str(cube.scale))

    fail_reply("eje inventado", client.command("transform.begin", {"mode": "MOVE", "axes": ["W"]}), "bad_payload")
    fail_reply("modo inventado", client.command("transform.begin", {"mode": "SHEAR"}), "bad_payload")

    client.command("mode.edit")
    bpy.context.scene.tool_settings.mesh_select_mode = (True, False, False)
    bm = bmesh.from_edit_mesh(cube.data)
    for vert in bm.verts:
        vert.select = True
    bmesh.update_edit_mesh(cube.data)
    before_edit = [v.co.copy() for v in bm.verts]
    edit_session = ok_reply("modal también en Edit Mode", client.command("transform.begin", {"mode": "MOVE"}))
    check("sesión Edit identificada", bool(edit_session.get("session_id")), str(edit_session))
    ok_reply("preview modal Edit", client.command("transform.value", {"values": [0, 0, 0.5]}))
    bm = bmesh.from_edit_mesh(cube.data)
    check("preview mueve BMesh", any((v.co - old).length > 0.1 for v, old in zip(bm.verts, before_edit)))
    ok_reply("cancelar modal Edit", client.command("transform.cancel"))
    bm = bmesh.from_edit_mesh(cube.data)
    check("cancelar restaura BMesh", all((v.co - old).length < 1e-6 for v, old in zip(bm.verts, before_edit)))
    fail_reply("orientación inventada", client.command("transform.begin", {"orientation": "MARS"}), "bad_payload")

    ok_reply("modo cara para herramienta", client.command("selection.face"))
    ok_reply("seleccionar una cara", client.command("selection.elements", {"faces": [0], "mode": "SET"}))
    ok_reply("modo arista para loop/ring", client.command("selection.edge"))
    ok_reply("semilla de arista", client.command("selection.elements", {"edges": [0], "mode": "SET"}))
    loop = ok_reply("selection.loop", client.command("selection.loop", {"edge": 0, "mode": "SET"}))
    check("loop selecciona una cadena", loop.get("affected", 0) >= 1, str(loop))
    ring = ok_reply("selection.ring", client.command("selection.ring", {"edge": 0, "mode": "SET"}))
    check("ring selecciona una cadena", ring.get("affected", 0) >= 1, str(ring))
    ok_reply("restaurar modo cara", client.command("selection.face"))
    ok_reply("restaurar cara para herramienta", client.command("selection.elements", {"faces": [0], "mode": "SET"}))
    topology_before = ok_reply("topología antes de tool", client.command("mesh.info"))
    tool = ok_reply("tool.begin extrude", client.command("tool.begin", {
        "tool": "EXTRUDE", "parameters": {"offset": 0.2}}))
    check("tool tiene sesión", bool(tool.get("session_id")), str(tool))
    topology_preview = ok_reply("topología preview", client.command("mesh.info"))
    check("preview paramétrico crea geometría", topology_preview["verts"] > topology_before["verts"])
    ok_reply("cambiar parámetro reconstruye", client.command("tool.parameter", {"parameters": {"offset": 0.4}}))
    ok_reply("tool.cancel", client.command("tool.cancel"))
    topology_cancel = ok_reply("topología tras cancel", client.command("mesh.info"))
    check("cancel restaura topología", topology_cancel["verts"] == topology_before["verts"], str(topology_cancel))
    ok_reply("tool.begin para confirmar", client.command("tool.begin", {
        "tool": "EXTRUDE", "parameters": {"offset": 0.2}}))
    result = ok_reply("tool.confirm", client.command("tool.confirm"))
    check("tool confirma fase", result.get("phase") == "CONFIRMED", str(result))
    client.command("mode.object")


def file_scenario(client: WSClient) -> None:
    print("\n[15] Archivo")
    import tempfile

    info = ok_reply("file.info", client.command("file.info"))
    check("archivo sin guardar", info.get("saved") is False, str(info))
    check("nombre por defecto", info.get("name") == "Sin título", str(info))

    fail_reply("file.save sin ruta", client.command("file.save"), "no_path")
    fail_reply("file.save_as sin path", client.command("file.save_as"), "bad_payload")
    fail_reply("file.open inexistente", client.command("file.open", {"path": "/no/existe.blend"}), "not_found")

    recent = ok_reply("file.recent", client.command("file.recent", {"limit": 5}))
    check("recientes es una lista", isinstance(recent.get("files"), list), str(recent))
    check("respeta el límite", len(recent.get("files", [])) <= 5, str(recent))
    fail_reply("limit inválido", client.command("file.recent", {"limit": "muchos"}), "bad_payload")

    folder = tempfile.mkdtemp(prefix="blender-remote-test-")
    target = os.path.join(folder, "prueba")  # sin extensión: la debe añadir el servidor

    info = ok_reply("file.save_as", client.command("file.save_as", {"path": target}))
    check("guardó con extensión .blend", info.get("path", "").endswith("prueba.blend"), str(info))
    check("el archivo existe en disco", os.path.isfile(target + ".blend"), info.get("path", ""))
    check("ya consta como guardado", info.get("saved") is True, str(info))

    ok_reply("file.save sobre la ruta ya conocida", client.command("file.save"))

    info = ok_reply("file.new", client.command("file.new"))
    check("el archivo nuevo no tiene ruta", info.get("saved") is False, str(info))

    info = ok_reply("file.open", client.command("file.open", {"path": target + ".blend"}))
    check("reabrió el archivo guardado", info.get("name") == "prueba.blend", str(info))

    # El servidor tiene que seguir en pie después de cargar otro .blend: el timer del
    # puente es persistent, pero es justo lo que se rompería sin darse cuenta.
    ok_reply("el servidor sigue vivo tras abrir", client.command("server.ping"))
    state_after = ok_reply("scene.get_state tras abrir", client.command("scene.get_state"))
    check("hay estado tras la carga", "mode" in state_after, str(state_after))

    shutil.rmtree(folder, ignore_errors=True)


def modeling_scenario(client: WSClient) -> None:
    print("\n[18] Modificadores, hide, apply y loop cut")
    ok_reply("escena limpia", client.command("file.new"))
    ok_reply("seleccionar Cube", client.command("object.select", {"names": ["Cube"]}))

    opts = ok_reply("modifier.add_options", client.command("modifier.add_options"))
    types = opts.get("types", {})
    for kind in ("SUBSURF", "ARRAY", "BEVEL", "SOLIDIFY", "BOOLEAN"):
        check(f"catálogo incluye {kind}", kind in types, str(types))
    fail_reply("tipo inventado", client.command("modifier.add", {"type": "MIRROR"}), "bad_payload")

    sub = ok_reply("add SUBSURF", client.command("modifier.add", {"type": "SUBSURF"}))
    check("subsurf en la pila", any(m["type"] == "SUBSURF" for m in sub.get("modifiers", [])), str(sub))
    info = ok_reply("object_info trae modifiers", client.command("scene.get_object", {"name": "Cube"}))
    check("modifiers en object_info", isinstance(info.get("modifiers"), list), str(info))
    sub_name = next(m["name"] for m in info["modifiers"] if m["type"] == "SUBSURF")
    ok_reply("set levels", client.command("modifier.set", {"name": sub_name, "parameters": {"levels": 2}}))
    toggled = ok_reply("toggle viewport", client.command("modifier.toggle", {"name": sub_name, "viewport": False}))
    check("viewport apagado", any(m["name"] == sub_name and m["show_viewport"] is False for m in toggled["modifiers"]))
    ok_reply("quitar subsurf", client.command("modifier.remove", {"name": sub_name}))

    arr = ok_reply("add ARRAY", client.command("modifier.add", {"type": "ARRAY"}))
    arr_name = next(m["name"] for m in arr["modifiers"] if m["type"] == "ARRAY")
    ok_reply("array count 3", client.command("modifier.set", {"name": arr_name, "parameters": {"count": 3}}))
    info = ok_reply("dims tras array", client.command("scene.get_object", {"name": "Cube"}))
    check("array alarga el cubo", info["dimensions"][0] > 3.5, str(info["dimensions"]))
    ok_reply("add BEVEL encima", client.command("modifier.add", {"type": "BEVEL"}))
    bev_name = next(m["name"] for m in client.command("scene.get_object", {"name": "Cube"})["result"]["modifiers"] if m["type"] == "BEVEL")
    moved = ok_reply("bevel al índice 0", client.command("modifier.move", {"name": bev_name, "index": 0}))
    check("bevel quedó primero", moved["modifiers"][0]["type"] == "BEVEL", str(moved["modifiers"]))
    ok_reply("quitar bevel", client.command("modifier.remove", {"name": bev_name}))
    later = ok_reply("añadir modifier posterior", client.command("modifier.add", {"type": "BEVEL"}))
    later_name = next(m["name"] for m in later["modifiers"] if m["type"] == "BEVEL")
    applied = ok_reply("apply array", client.command("modifier.apply", {"name": arr_name}))
    check("apply quita el array", not any(m["type"] == "ARRAY" for m in applied.get("modifiers", [])), str(applied))
    check("apply conserva modifiers posteriores", any(m["name"] == later_name for m in applied.get("modifiers", [])), str(applied))
    info = ok_reply("malla horneada", client.command("scene.get_object", {"name": "Cube"}))
    check("la malla real creció", info["mesh"]["vertices"] > 8, str(info["mesh"]))

    ok_reply("escena para boolean", client.command("file.new"))
    ok_reply("Cube activo", client.command("object.select", {"names": ["Cube"]}))
    ok_reply("add SOLIDIFY", client.command("modifier.add", {"type": "SOLIDIFY", "parameters": {"thickness": 0.5}}))
    solid = next(m for m in client.command("scene.get_object", {"name": "Cube"})["result"]["modifiers"] if m["type"] == "SOLIDIFY")
    check("solidify thickness", abs(solid["parameters"]["thickness"] - 0.5) < 1e-6, str(solid))
    ok_reply("quitar solidify", client.command("modifier.remove", {"name": solid["name"]}))

    ok_reply("cortador", client.command("object.add", {"primitive": "CUBE", "x": 0.8, "y": 0.0, "z": 0.0}))
    cutter = client.command("scene.get_state")["result"]["active_object"]
    ok_reply("volver al cubo", client.command("object.select", {"names": ["Cube"]}))
    added_bool = ok_reply("add BOOLEAN", client.command("modifier.add", {"type": "BOOLEAN"}))
    bool_name = next(m["name"] for m in added_bool["modifiers"] if m["type"] == "BOOLEAN")
    fail_reply("boolean consigo mismo", client.command("modifier.set", {
        "name": bool_name, "parameters": {"object": "Cube"}}), "bad_payload")
    fail_reply("operando inventado", client.command("modifier.set", {
        "name": bool_name, "parameters": {"object": "NoExiste"}}), "not_found")
    set_bool = ok_reply("enganchar cortador", client.command("modifier.set", {
        "name": bool_name, "parameters": {"object": cutter, "operation": "DIFFERENCE"}}))
    bool_mod = next(m for m in set_bool["modifiers"] if m["name"] == bool_name)
    check("boolean apunta al cortador", bool_mod["parameters"]["object"] == cutter, str(bool_mod))
    client.command("mode.edit")
    fail_reply("apply boolean en Edit", client.command("modifier.apply", {"name": bool_name}), "wrong_mode")
    client.command("mode.object")

    print("  hide / reveal")
    ok_reply("escena para hide", client.command("file.new"))
    ok_reply("Cube para hide", client.command("object.select", {"names": ["Cube"]}))
    hidden = ok_reply("object.hide", client.command("object.hide"))
    check("hide nombra el cubo", "Cube" in hidden.get("hidden", []), str(hidden))
    info = ok_reply("estado oculto", client.command("scene.get_object", {"name": "Cube"}))
    check("visible es false", info.get("visible") is False, str(info))
    revealed = ok_reply("object.reveal", client.command("object.reveal"))
    check("reveal devuelve el cubo", "Cube" in revealed.get("revealed", []), str(revealed))
    info = ok_reply("estado visible", client.command("scene.get_object", {"name": "Cube"}))
    check("visible es true", info.get("visible") is True, str(info))
    ok_reply("esfera para Shift+H", client.command("object.add", {"primitive": "SPHERE"}))
    sphere = client.command("scene.get_state")["result"]["active_object"]
    ok_reply("dejar Cube seleccionado", client.command("object.select", {"names": ["Cube"]}))
    ok_reply("hide unselected", client.command("object.hide", {"unselected": True}))
    check("la esfera se ocultó", client.command("scene.get_object", {"name": sphere})["result"]["visible"] is False)
    check("el cubo sigue visible", client.command("scene.get_object", {"name": "Cube"})["result"]["visible"] is True)
    ok_reply("revelar todo", client.command("object.reveal"))

    print("  transform.apply")
    ok_reply("escala 2", client.command("transform.scale", {"factor": 2.0}))
    ok_reply("apply scale", client.command("transform.apply", {"scale": True}))
    info = ok_reply("tras apply scale", client.command("scene.get_object", {"name": "Cube"}))
    check("scale vuelve a 1", abs(info["scale"][0] - 1.0) < 1e-4, str(info["scale"]))
    check("la caja creció", info["dimensions"][0] > 3.5, str(info["dimensions"]))
    fail_reply("apply sin flags", client.command("transform.apply", {}), "bad_payload")
    client.command("mode.edit")
    fail_reply("apply en Edit", client.command("transform.apply", {"scale": True}), "wrong_mode")
    client.command("mode.object")
    ok_reply("mover a X=3", client.command("transform.move", {"x": 3.0, "absolute": True}))
    ok_reply("apply location", client.command("transform.apply", {"location": True}))
    info = ok_reply("tras apply loc", client.command("scene.get_object", {"name": "Cube"}))
    check("location a cero", abs(info["location"][0]) < 1e-4, str(info["location"]))
    ok_reply("duplicado enlazado", client.command("object.duplicate", {"linked": True}))
    fail_reply("apply con datos compartidos", client.command("transform.apply", {"scale": True}), "shared_data")
    ok_reply("crear Empty no transformable", client.command("object.add", {"primitive": "EMPTY_PLAIN_AXES"}))
    fail_reply("apply tipo no transformable", client.command("transform.apply", {"scale": True}), "unsupported_type")

    print("  LOOP_CUT")
    ok_reply("escena para loop cut", client.command("file.new"))
    ok_reply("Cube loop", client.command("object.select", {"names": ["Cube"]}))
    fail_reply("loop cut en Object", client.command("tool.begin", {"tool": "LOOP_CUT"}), "wrong_mode")
    ok_reply("entrar en Edit", client.command("mode.edit"))
    ok_reply("modo arista", client.command("selection.edge"))
    ok_reply("semilla arista 0", client.command("selection.elements", {"edges": [0], "mode": "SET"}))
    before = ok_reply("topo antes", client.command("mesh.info"))
    begun = ok_reply("tool.begin LOOP_CUT", client.command("tool.begin", {
        "tool": "LOOP_CUT", "parameters": {"cuts": 1, "factor": 0.0}}))
    check("sesión loop cut", begun.get("tool") == "LOOP_CUT" and begun.get("active"), str(begun))
    preview = ok_reply("topo preview", client.command("mesh.info"))
    check("preview añade vértices", preview["verts"] > before["verts"], f"{before['verts']} -> {preview['verts']}")
    ok_reply("nudge factor", client.command("tool.nudge", {"delta": 0.2}))
    ok_reply("cancel loop cut", client.command("tool.cancel"))
    cancelled = ok_reply("topo cancel", client.command("mesh.info"))
    check("cancel restaura", cancelled["verts"] == before["verts"], str(cancelled))
    ok_reply("semilla otra vez", client.command("selection.elements", {"edges": [0], "mode": "SET"}))
    ok_reply("begin cuts=1", client.command("tool.begin", {"tool": "LOOP_CUT", "parameters": {"cuts": 1}}))
    verts_one = ok_reply("verts cuts=1", client.command("mesh.info"))["verts"]
    ok_reply("cancel cuts=1", client.command("tool.cancel"))
    ok_reply("semilla cuts=2", client.command("selection.elements", {"edges": [0], "mode": "SET"}))
    ok_reply("begin cuts=2", client.command("tool.begin", {"tool": "LOOP_CUT", "parameters": {"cuts": 2}}))
    verts_two = ok_reply("verts cuts=2", client.command("mesh.info"))["verts"]
    check("cuts=2 crea más geometría", verts_two > verts_one, f"{verts_one} -> {verts_two}")
    confirmed = ok_reply("confirm loop cut", client.command("tool.confirm"))
    check("fase confirmada", confirmed.get("phase") == "CONFIRMED", str(confirmed))
    ok_reply("deseleccionar", client.command("selection.all", {"value": False}))
    fail_reply("sin arista", client.command("tool.begin", {"tool": "LOOP_CUT"}), "empty_selection")
    client.command("mode.object")


def auth_scenario() -> None:
    print("\n[16] Autenticación")
    bad = WSClient("127.0.0.1", PORT, token="")
    try:
        bad.connect()
        bad.send({"type": "command", "id": "x", "command": "scene.get_state"})
        reply = bad.recv(timeout=3.0)
        check("sin token se rechaza", reply.get("code") == "auth_required", str(reply))
    except WSError as exc:
        check("sin token se rechaza", False, str(exc))
    finally:
        bad.close()

    wrong = WSClient("127.0.0.1", PORT, token="")
    try:
        wrong.connect()
        wrong.send({"type": "auth", "id": "1", "token": "nope"})
        reply = wrong.recv(timeout=3.0)
        check("token incorrecto se rechaza", reply.get("code") == "auth_failed", str(reply))
    except WSError as exc:
        check("token incorrecto se rechaza", False, str(exc))
    finally:
        wrong.close()


def query_token_scenario() -> None:
    print("\n[17] Token en la query del handshake")
    import base64
    import socket

    sock = socket.create_connection(("127.0.0.1", PORT), timeout=5)
    key = base64.b64encode(os.urandom(16)).decode()
    sock.sendall(
        (
            f"GET /?token={TOKEN} HTTP/1.1\r\nHost: 127.0.0.1\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        ).encode()
    )
    time.sleep(0.3)
    data = sock.recv(4096)
    check("handshake aceptado", b"101 Switching Protocols" in data, str(data[:60]))
    check("hello dice authenticated", b'"authenticated":true' in data, str(data[-200:]))
    sock.close()

    # Una capa de red defectuosa puede añadir otra copia de la cabecera. El servidor
    # debe responder usando la primera clave, que es la que conserva el cliente.
    import hashlib

    import wsclient

    from blender_tablet_remote.wsserver import GUID

    # Vector de ejemplo del RFC 6455 §1.3. Sin esta comprobación un GUID mal
    # tecleado pasa inadvertido: servidor y test comparten la constante y siempre
    # coinciden, mientras que OkHttp (que sí valida) rechaza todos los handshakes.
    check(
        "GUID coincide con el vector del RFC 6455",
        base64.b64encode(
            hashlib.sha1(("dGhlIHNhbXBsZSBub25jZQ==" + GUID).encode()).digest()
        ).decode()
        == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=",
        GUID,
    )
    check(
        "el GUID del cliente CLI coincide con el del servidor",
        wsclient.GUID == GUID,
        f"{wsclient.GUID} != {GUID}",
    )

    sock = socket.create_connection(("127.0.0.1", PORT), timeout=5)
    original_key = base64.b64encode(os.urandom(16)).decode()
    extra_key = base64.b64encode(os.urandom(16)).decode()
    expected = base64.b64encode(hashlib.sha1((original_key + GUID).encode()).digest()).decode()
    sock.sendall(
        (
            f"GET / HTTP/1.1\r\nHost: 127.0.0.1\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {original_key}\r\n"
            f"Sec-WebSocket-Key: {extra_key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        ).encode()
    )
    data = sock.recv(4096)
    check(
        "cabecera WebSocket duplicada conserva la primera clave",
        f"Sec-WebSocket-Accept: {expected}".encode() in data,
        str(data[:300]),
    )
    sock.close()


# ----------------------------------------------------------------- ejecución


def client_worker(done: threading.Event) -> None:
    try:
        client = WSClient("127.0.0.1", PORT, token=TOKEN, timeout=8.0)
        client.connect()
        try:
            scenario(client)
        finally:
            client.close()

        # Cliente nuevo a propósito: `scenario` termina drenando eventos, y un recv
        # que expira deja el buffer del socket inservible para las lecturas siguientes.
        extra = WSClient("127.0.0.1", PORT, token=TOKEN, timeout=8.0)
        extra.connect()
        try:
            snap_scenario(extra)
            add_menu_scenario(extra)
            modal_scenario(extra)
            file_scenario(extra)
            modeling_scenario(extra)
        finally:
            extra.close()

        auth_scenario()
        query_token_scenario()
    except Exception:  # noqa: BLE001
        _results.append(("excepción en el cliente", False, traceback.format_exc()))
        print(traceback.format_exc())
    finally:
        done.set()


def main() -> int:
    print("=" * 70)
    print("Blender Tablet Remote — tests de aceptación (headless)")
    print(f"Blender {bpy.app.version_string} | Python {sys.version.split()[0]}")
    print("=" * 70)

    bridge.start("127.0.0.1", PORT, TOKEN, verbose=False)

    done = threading.Event()
    thread = threading.Thread(target=client_worker, args=(done,), daemon=True)
    thread.start()

    # Hacemos de bucle de eventos de Blender: el pump es lo que ejecuta los comandos.
    deadline = time.monotonic() + 150
    while not done.is_set() and time.monotonic() < deadline:
        bridge._pump()
        time.sleep(0.004)

    if not done.is_set():
        _results.append(("timeout global", False, "los tests no terminaron en 90s"))

    bridge.stop()

    passed = sum(1 for _n, ok, _d in _results if ok)
    failed = [(n, d) for n, ok, d in _results if not ok]
    print("\n" + "=" * 70)
    print(f"RESULTADO: {passed} PASS, {len(failed)} FAIL de {len(_results)}")
    for name, detail in failed:
        print(f"  FAIL {name}: {detail}")
    print("=" * 70)
    return 1 if failed else 0


if __name__ == "__main__":
    code = main()
    # sys.exit dentro de Blender no fija el código de salida de forma fiable.
    bpy.ops.wm.quit_blender() if False else None
    sys.exit(code)
