"""Suite de aceptación del backend, ejecutable sin interfaz gráfica.

    blender --background --python blender-backend/tests/run_tests.py

Cómo funciona: en `--background` Blender no corre su bucle de eventos, así que los
`bpy.app.timers` nunca se disparan. El test levanta el servidor, lanza el cliente en
un thread y bombea el bridge a mano desde el hilo principal — exactamente lo que hace
Blender con interfaz, pero bajo control del test.

Salida: resumen de PASS/FAIL y código de salida 1 si algo falla.
"""

from __future__ import annotations

import math
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
    from blender_tablet_remote.commands.selection import _edge_loop, _seed_edge, _shortest_element_path

    loop_bm = bmesh.new()
    bmesh.ops.create_cube(loop_bm, size=2.0)
    vertical_edges = [
        edge for edge in loop_bm.edges
        if abs((edge.verts[1].co - edge.verts[0].co).normalized().z) > 0.9
    ]
    bmesh.ops.subdivide_edges(
        loop_bm, edges=vertical_edges, cuts=1, use_grid_fill=True)
    middle_loop = {
        edge for edge in loop_bm.edges
        if all(abs(vertex.co.z) < 1e-6 for vertex in edge.verts)
    }
    selected_loop = _edge_loop(next(iter(middle_loop)))
    check(
        "selection.loop recorre las esquinas de un Loop Cut cerrado",
        selected_loop == middle_loop,
        f"esperadas={len(middle_loop)}, seleccionadas={len(selected_loop)}",
    )
    first_seed, last_seed = tuple(middle_loop)[:2]
    first_seed.select = True
    last_seed.select = True
    loop_bm.select_history.add(first_seed)
    loop_bm.select_history.add(last_seed)
    check(
        "selection.loop usa como semilla la última arista tocada",
        _seed_edge(loop_bm, {}) is last_seed,
    )
    loop_bm.verts.ensure_lookup_table()
    vertex_path = _shortest_element_path(loop_bm.verts[0], loop_bm.verts[6])
    check(
        "selection.shortest_path recorre una ruta conectada",
        vertex_path[0] is loop_bm.verts[0] and vertex_path[-1] is loop_bm.verts[6]
        and all(any(a in edge.verts and b in edge.verts for edge in loop_bm.edges)
                for a, b in zip(vertex_path, vertex_path[1:])),
        str([vertex.index for vertex in vertex_path]),
    )
    loop_bm.free()

    print("\n[0] Transporte H.264 preferido y MJPEG fallback")
    import socket

    from blender_tablet_remote.streaming.mjpeg import CLIENT_SEND_BUFFER, _tune_client_socket

    class FakeSocket:
        def __init__(self):
            self.options = {}

        def setsockopt(self, level, option, value):
            self.options[(level, option)] = value

    mjpeg_socket = FakeSocket()
    _tune_client_socket(mjpeg_socket)
    check(
        "MJPEG limita la cola TCP de salida",
        mjpeg_socket.options.get((socket.SOL_SOCKET, socket.SO_SNDBUF)) == CLIENT_SEND_BUFFER
        and CLIENT_SEND_BUFFER <= 32 * 1024,
        str(mjpeg_socket.options),
    )
    check(
        "MJPEG desactiva Nagle",
        mjpeg_socket.options.get((socket.IPPROTO_TCP, socket.TCP_NODELAY)) == 1,
        str(mjpeg_socket.options),
    )
    from blender_tablet_remote.streaming.frames import FrameBuffer
    from blender_tablet_remote.streaming.mjpeg import StreamServer
    demand_server = StreamServer(FrameBuffer(), lambda: {}, FrameBuffer())
    demand_server.clients_delta(+1, "h264")
    check("solo H.264 se codifica para cliente H.264",
          demand_server.formats_wanted() == {"h264"}, str(demand_server.formats_wanted()))
    demand_server.clients_delta(+1, "mjpeg")
    check("MJPEG arranca solo al conectar fallback",
          demand_server.formats_wanted() == {"h264", "mjpeg"}, str(demand_server.formats_wanted()))
    demand_server.clients_delta(-1, "h264")
    check("H.264 se apaga al quedar solo fallback",
          demand_server.formats_wanted() == {"mjpeg"}, str(demand_server.formats_wanted()))

    # El timestamp del multipart debe incluir la espera/coste del codificador. Si
    # se sellara al publicar, una cola ffmpeg de varios segundos parecería latencia
    # cero tanto en /stats como en Android y el diagnóstico sería engañoso.
    import io
    import time
    from blender_tablet_remote.streaming.encoder import JpegEncoder
    measured_frames = FrameBuffer()
    measured_encoder = JpegEncoder(measured_frames)
    captured_at = time.time() - 0.025
    measured_encoder._capture_stamps.put(captured_at)
    jpeg = b"synthetic-jpeg"
    fake_stdout = io.BytesIO(
        b"--ffmpeg\r\nContent-Type: image/jpeg\r\nContent-Length: "
        + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg
    )
    measured_encoder._read_loop(type("FakeProc", (), {"stdout": fake_stdout})())
    published, seq, stamp = measured_frames.latest()
    check("timestamp MJPEG nace en captura", seq == 1 and published == jpeg and stamp == captured_at,
          f"seq={seq}, stamp={stamp}, captured={captured_at}")
    check("métrica incluye captura -> ffmpeg", measured_encoder.stats["last_encode_ms"] >= 20.0,
          str(measured_encoder.stats))

    from blender_tablet_remote.streaming.h264 import (
        FLAG_CONFIG, FLAG_KEYFRAME, HEADER_SIZE, flags_for, pack_header, split_access_units,
    )
    import struct
    au1 = b"\x00\x00\x00\x01\x09\x10\x00\x00\x00\x01\x67x\x00\x00\x01\x68y\x00\x00\x01\x65z"
    au2 = b"\x00\x00\x00\x01\x09\x10\x00\x00\x01\x41q"
    units, tail = split_access_units(au1 + au2)
    check("H.264 separa access units por AUD", units == [au1] and tail == au2,
          f"units={len(units)} tail={len(tail)}")
    flags = flags_for(au1)
    check("H.264 detecta config + keyframe", flags == FLAG_CONFIG | FLAG_KEYFRAME, str(flags))
    header = pack_header(7, 123.456, len(au1), 1280, 754, flags)
    unpacked = struct.unpack(">4sBBHIQIII", header)
    check("framing btr-h264-v1 es estable", len(header) == HEADER_SIZE and
          unpacked == (b"BTRH", 1, flags, 32, 7, 123456000, len(au1), 1280, 754), str(unpacked))
    from blender_tablet_remote.streaming.encoder import H264Encoder
    encoded_frames = FrameBuffer()
    h264_encoder = H264Encoder(encoded_frames)
    started = h264_encoder.ensure(64, 64, 24, 70)
    for _ in range(2):
        h264_encoder.submit(bytes(64 * 64 * 4))
        time.sleep(0.03)
    deadline = time.time() + 2.0
    while encoded_frames.latest()[1] == 0 and time.time() < deadline:
        time.sleep(0.02)
    encoded, encoded_seq, _ = encoded_frames.latest()
    h264_encoder.stop()
    check("ffmpeg/libx264 produce Annex B en vivo", started and encoded_seq > 0 and
          flags_for(encoded) == FLAG_CONFIG | FLAG_KEYFRAME,
          f"started={started} seq={encoded_seq} bytes={len(encoded)} flags={flags_for(encoded)}")
    jpeg_live_frames = FrameBuffer()
    jpeg_live = JpegEncoder(jpeg_live_frames)
    jpeg_started = jpeg_live.ensure(64, 64, 24, 70)
    for _ in range(3):
        jpeg_live.submit(bytes(64 * 64 * 4))
        time.sleep(0.03)
    deadline = time.time() + 2.0
    while jpeg_live_frames.latest()[1] == 0 and time.time() < deadline:
        time.sleep(0.02)
    jpeg_data, jpeg_seq, _ = jpeg_live_frames.latest()
    jpeg_live.stop()
    check("ffmpeg/MJPEG fallback arranca en vivo", jpeg_started and jpeg_seq > 0 and
          jpeg_data.startswith(b"\xff\xd8"),
          f"started={jpeg_started} seq={jpeg_seq} bytes={len(jpeg_data)}")

    print("\n[1] Handshake, auth y capacidades")
    caps = ok_reply("server.capabilities", client.command("server.capabilities"))
    check("hay comandos registrados", len(caps.get("commands", [])) > 20, str(caps.get("commands")))
    check("modo background detectado", caps.get("background") is True)
    check("protocolo v2", caps.get("protocol_version") == "2.0", str(caps.get("protocol_version")))
    check("features estructuradas", isinstance(caps.get("features", {}).get("transform_modal"), dict))
    check("H.264 es preferido con MJPEG fallback",
          caps.get("features", {}).get("stream", {}).get("transports") == ["H264", "MJPEG"])
    check("enums canónicos", caps.get("enums", {}).get("constraint") == ["FREE", "X", "Y", "Z", "XY", "XZ", "YZ", "NORMAL", "VIEW"])
    check("unidades explícitas", caps.get("units", {}).get("rotation") == "DEGREE")
    edit_catalog = caps.get("features", {}).get("edit_catalog", {})
    conditional = {item.get("id"): item for item in edit_catalog.get("conditional_actions", [])}
    check("Circle declara dependencia condicional de LoopTools",
          conditional.get("LOOPTOOLS_CIRCLE", {}).get("operator") == "mesh.looptools_circle",
          str(conditional.get("LOOPTOOLS_CIRCLE")))
    circle_by_mode = [next((entry for entry in edit_catalog.get("groups", {}).get(mode, [])
                            if entry.get("id") == "LOOPTOOLS_CIRCLE"), None)
                      for mode in ("VERTEX", "EDGE")]
    try:
        bpy.ops.mesh.looptools_circle.get_rna_type()
        circle_available = True
    except (AttributeError, KeyError, RuntimeError):
        circle_available = False
    check("Circle solo aparece si el operador de LoopTools está registrado",
          all(entry is not None for entry in circle_by_mode) == circle_available
          and (circle_by_mode[0] is None) == (circle_by_mode[1] is None),
          f"available={circle_available} entries={circle_by_mode}")

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
    inset_result = ok_reply("mesh.inset", client.command("mesh.inset", {
        "thickness": 0.1, "boundary": False,
    }))
    check("Inset conserva la opción de costura fija", inset_result.get("boundary") is False,
          str(inset_result))
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

    print("  duplicar selección Edit por submodo")
    for selection_command, element_payload, expected_delta in (
        ("selection.vertex", {"verts": [0], "mode": "SET"}, {"verts": 1, "edges": 0, "faces": 0}),
        ("selection.edge", {"edges": [0], "mode": "SET"}, {"verts": 2, "edges": 1, "faces": 0}),
        ("selection.face", {"faces": [0], "mode": "SET"}, {"verts": 4, "edges": 4, "faces": 1}),
    ):
        ok_reply("escena limpia para duplicate", client.command("file.new"))
        fail_reply("mesh.duplicate exige Edit", client.command("mesh.duplicate"), "wrong_mode")
        ok_reply("entrar en Edit para duplicate", client.command("mode.edit"))
        ok_reply(selection_command, client.command(selection_command))
        ok_reply("vaciar selección", client.command("selection.all", {"value": False}))
        fail_reply("duplicate vacío", client.command("mesh.duplicate"), "empty_selection")
        ok_reply("selección parcial", client.command("selection.elements", element_payload))
        before = ok_reply("mesh.info antes de duplicate", client.command("mesh.info"))
        duplicated = ok_reply("mesh.duplicate", client.command("mesh.duplicate"))
        after = ok_reply("mesh.info tras duplicate", client.command("mesh.info"))
        for key, delta in expected_delta.items():
            check(f"duplicate añade {delta} {key}", after[key] - before[key] == delta,
                  f"{before[key]} -> {after[key]}")
        check("duplicate informa el subgrafo copiado", duplicated.get("duplicated") == expected_delta,
              str(duplicated))

    ok_reply("salir de Edit tras duplicate", client.command("mode.object"))
    # Los file.new de los casos aislados reemplazan el RNA; el resto del escenario
    # debe continuar con la instancia actual, no con la referencia del primer archivo.
    cube = bpy.data.objects["Cube"]

    result = ok_reply("object.add SPHERE", client.command("object.add", {"primitive": "SPHERE"}))
    check("esfera añadida", any(o.type == "MESH" and "Sphere" in o.name for o in bpy.data.objects))

    print("\n[9] Gestos con coalescing")
    from blender_tablet_remote.gestures import _Accumulator
    accumulated = _Accumulator()
    for _ in range(200):
        accumulated.add(0.001, -0.0005, 1.001)
    dx, dy, factor = accumulated.take()
    check("el coalescing conserva todo el desplazamiento", abs(dx - 0.2) < 1e-9 and abs(dy + 0.1) < 1e-9,
          f"dx={dx}, dy={dy}")
    check("el coalescing conserva todo el factor", abs(factor - 1.001 ** 200) < 1e-9, str(factor))
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

    fail_reply("GRID retirado de transformaciones", client.command("transform.begin", {
        "mode": "MOVE", "axes": ["X"], "snap": True, "snap_type": "GRID", "step": 1.0,
    }), "bad_payload")
    fail_reply("CURSOR retirado de transformaciones", client.command("transform.begin", {
        "mode": "MOVE", "snap": True, "snap_type": "CURSOR",
    }), "bad_payload")

    # Headless no dispone de raycast de viewport; se inyecta únicamente el resultado
    # del picker para probar la matemática y el contrato de valores REL.
    from blender_tablet_remote.commands.modal import session as modal_session
    ok_reply("begin para referencia REL", client.command("transform.begin", {"mode": "MOVE"}))
    modal_session.reference_position = modal_session.pivot.copy()
    modal_session.reference_position.x = 2.0
    modal_session.reference_candidate = {
        "hit": True, "snap_type": "VERTEX", "id": "test:VERTEX:0",
        "position": [2.0, 0.0, 0.0], "screen": [0.5, 0.5],
    }
    locked_reference = ok_reply("soltar REL congela el hover verde", client.command(
        "transform.reference_candidate", {"u": 0.01, "v": 0.01, "lock": True}))
    check("ACTION_UP no recalcula la referencia",
          locked_reference.get("reference_locked") is True
          and locked_reference.get("reference_position") == [2.0, 0.0, 0.0]
          and (locked_reference.get("reference_candidate") or {}).get("id") == "test:VERTEX:0",
          str(locked_reference))
    relative = ok_reply("XYZ cero desde REL", client.command("transform.value", {
        "values": [0.0, 0.0, 0.0],
    }))
    check("bloquear REL no altera el delta cero",
          abs(cube.location.x) < 1e-6, str(cube.location))
    check("estado publica origen y distancia REL",
          relative.get("reference_locked") is True
          and abs(relative.get("reference_distance", 0.0) - 2.0) < 1e-6,
          str(relative))
    moved = ok_reply("mover conserva REL unido", client.command("transform.value", {
        "values": [1.0, 0.0, 0.0],
    }))
    check("REL acompaña al objeto",
          abs(moved["reference_position"][0] - 3.0) < 1e-6,
          str(moved.get("reference_position")))
    cleared = ok_reply("limpiar REL conserva preview", client.command(
        "transform.reference_candidate", {"clear": True}))
    check("limpiar REL no mueve el objeto",
          abs(cube.location.x - 1.0) < 1e-6 and cleared.get("reference_locked") is False,
          f"{cube.location} | {cleared}")
    ok_reply("cancelar referencia REL", client.command("transform.cancel"))

    ok_reply("begin para confirmar", client.command("transform.begin", {"mode": "MOVE", "axes": ["Z"]}))
    ok_reply("valor exacto", client.command("transform.value", {"values": [0, 0, 3.0]}))
    ok_reply("transform.confirm", client.command("transform.confirm"))
    check("confirmar conserva el cambio", abs(cube.location.z - 3.0) < 1e-6, str(cube.location))

    ok_reply("rotar con snap", client.command("transform.begin", {"mode": "ROTATE", "axes": ["Z"], "snap": True}))
    result = ok_reply("ángulo 47°", client.command("transform.value", {"angle": 47.0}))
    check("cuadra a 5 grados", abs(result["angle"] - 45.0) < 1e-6, str(result["angle"]))
    ok_reply("cancelar rotación", client.command("transform.cancel"))

    # El snap cuantiza EN VIVO sobre el valor acumulado: varios arrastres pequeños
    # seguidos dentro de la misma sesión dan varios saltos, no uno por gesto.
    # ROTATE no necesita viewport para el nudge, así que esto corre en background.
    # `status()` devuelve el ángulo en grados; el step viaja en radianes.
    step_degrees = 5.0
    ok_reply("rotar acumulativa", client.command("transform.begin", {
        "mode": "ROTATE", "axes": ["Z"], "snap": True, "snap_type": "INCREMENT",
        "step": math.radians(step_degrees),
    }))
    seen_angles = []
    for _ in range(8):
        # Cada nudge suma dx*pi (≈18°): cruza varios pasos y debe cuantizarse sobre
        # el valor acumulado, no reiniciarse en cada nudge.
        nudged = ok_reply("nudge", client.command("transform.nudge", {"dx": 0.1, "dy": 0.0}))
        seen_angles.append(nudged["angle"])
    distinct = len({round(a, 6) for a in seen_angles})
    check("el snap acumula entre gestos: más de un salto", distinct >= 3,
          f"{distinct} ángulos distintos: {seen_angles}")
    final_angle = seen_angles[-1]
    check("el ángulo final sigue en múltiplos del paso",
          abs(final_angle / step_degrees - round(final_angle / step_degrees)) < 1e-6,
          str(final_angle))
    ok_reply("cancelar acumulativa", client.command("transform.cancel"))

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

    # Mirror Clipping no se ejecuta solo cuando escribimos BMesh directamente:
    # la sesión remota debe imponer el plano igual que G/R/S nativos de Blender.
    mirror = cube.modifiers.new("Mirror clipping test", "MIRROR")
    mirror.use_axis[0] = True
    mirror.use_clip = True
    mirror.merge_threshold = 0.001
    bm = bmesh.from_edit_mesh(cube.data)
    bm.verts.ensure_lookup_table()
    clipped = max(bm.verts, key=lambda vert: vert.co.x)
    clipped_index = clipped.index
    original_clipped = clipped.co.copy()
    ok_reply("vértice para clipping", client.command("selection.vertex"))
    ok_reply("seleccionar vértice clipping", client.command("selection.elements", {
        "verts": [clipped_index], "mode": "SET",
    }))
    ok_reply("begin Mirror Clipping", client.command("transform.begin", {"mode": "MOVE", "axes": ["X"]}))
    crossing_delta = -abs(original_clipped.x) - 1.0
    ok_reply("intentar cruzar plano Mirror", client.command("transform.value", {
        "values": [crossing_delta, 0.0, 0.0],
    }))
    bm = bmesh.from_edit_mesh(cube.data)
    check("Clipping detiene el vértice en el plano", abs(bm.verts[clipped_index].co.x) < 1e-6,
          str(bm.verts[clipped_index].co.x))
    ok_reply("cancelar clipping", client.command("transform.cancel"))
    bm = bmesh.from_edit_mesh(cube.data)
    check("cancelar clipping restaura el lado original",
          (bm.verts[clipped_index].co - original_clipped).length < 1e-6,
          str(bm.verts[clipped_index].co))

    # El umbral fusiona la geometría evaluada, pero no debe capturar como costura un
    # vértice original que todavía esté a un lado del plano.
    near_seam = original_clipped.copy()
    near_seam.x = mirror.merge_threshold * 0.5
    bm.verts[clipped_index].co = near_seam
    bmesh.update_edit_mesh(cube.data)
    ok_reply("begin vértice contiguo a Mirror", client.command("transform.begin", {
        "mode": "MOVE", "axes": ["X"],
    }))
    ok_reply("mover vértice contiguo sin capturarlo", client.command("transform.value", {
        "values": [0.25, 0.0, 0.0],
    }))
    bm = bmesh.from_edit_mesh(cube.data)
    check("Clipping no pega un vecino dentro del merge threshold",
          abs(bm.verts[clipped_index].co.x - (near_seam.x + 0.25)) < 1e-6,
          str(bm.verts[clipped_index].co.x))
    ok_reply("cancelar vértice contiguo", client.command("transform.cancel"))

    bm.verts[clipped_index].co.x = 0.0
    bmesh.update_edit_mesh(cube.data)
    ok_reply("begin costura pegada", client.command("transform.begin", {"mode": "MOVE", "axes": ["X"]}))
    ok_reply("intentar despegar costura", client.command("transform.value", {"values": [1.0, 0.0, 0.0]}))
    bm = bmesh.from_edit_mesh(cube.data)
    check("Clipping mantiene la costura pegada", abs(bm.verts[clipped_index].co.x) < 1e-6,
          str(bm.verts[clipped_index].co.x))
    ok_reply("cancelar costura", client.command("transform.cancel"))
    bm = bmesh.from_edit_mesh(cube.data)
    bm.verts[clipped_index].co = original_clipped
    cube.modifiers.remove(mirror)
    bmesh.update_edit_mesh(cube.data)
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

    for variant in ("ALONG_NORMALS", "INDIVIDUAL"):
        ok_reply(f"seleccionar cara para extrude {variant}", client.command(
            "selection.elements", {"faces": [0], "mode": "SET"}))
        begun = ok_reply(f"tool.begin extrude {variant}", client.command("tool.begin", {
            "tool": "EXTRUDE", "parameters": {"variant": variant, "offset": 0.2}}))
        check(f"{variant} queda en sesión", begun.get("parameters", {}).get("variant") == variant, str(begun))
        preview = ok_reply(f"preview extrude {variant}", client.command("mesh.info"))
        check(f"{variant} añade geometría", preview["verts"] > topology_before["verts"], str(preview))
        ok_reply(f"cancel extrude {variant}", client.command("tool.cancel"))
        restored = ok_reply(f"restaura extrude {variant}", client.command("mesh.info"))
        check(f"cancel {variant} restaura topología", restored["verts"] == topology_before["verts"], str(restored))

    ok_reply("modo vértice para incompatibilidad de variante", client.command("selection.vertex"))
    ok_reply("seleccionar vértice", client.command("selection.elements", {"verts": [0], "mode": "SET"}))
    fail_reply("extrude individual no acepta vértices", client.command(
        "mesh.extrude", {"variant": "INDIVIDUAL"}), "incompatible_selection")
    ok_reply("restaurar modo cara para confirmar", client.command("selection.face"))
    ok_reply("restaurar cara para confirmar", client.command("selection.elements", {"faces": [0], "mode": "SET"}))
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
    nested = os.path.join(folder, "Proyectos")
    os.mkdir(nested)
    with open(os.path.join(folder, "ignorado.txt"), "w", encoding="utf-8") as handle:
        handle.write("no se muestra")
    locations = ok_reply("file.locations", client.command("file.locations"))
    original_default = locations["default_folder"]
    check("lugares incluyen default/home/root",
          {"DEFAULT", "HOME", "ROOT"}.issubset({item["id"] for item in locations["locations"]}), str(locations))
    configured = ok_reply("configurar carpeta", client.command("file.default_folder", {"path": folder}))
    check("carpeta predeterminada canónica", configured.get("default_folder") == os.path.realpath(folder), str(configured))
    listing = ok_reply("explorar alias default", client.command("file.browse", {"path": "@default"}))
    check("browse solo muestra directorios y blend",
          [item["name"] for item in listing["entries"]] == ["Proyectos"], str(listing["entries"]))
    check("browse trae breadcrumbs del host",
          listing.get("breadcrumbs") and listing["breadcrumbs"][-1] == {"name": os.path.basename(folder), "path": os.path.realpath(folder)},
          str(listing.get("breadcrumbs")))
    fail_reply("browse de fichero", client.command("file.browse", {"path": "ignorado.txt"}), "not_directory")
    fail_reply("default inexistente", client.command("file.default_folder", {"path": "no-existe"}), "not_found")
    target = os.path.join(folder, "prueba")  # sin extensión: la debe añadir el servidor

    legacy = ok_reply("file.save_as path compatible", client.command("file.save_as", {"path": "legacy"}))
    check("path legado relativo sigue operativo", legacy.get("path") == os.path.join(folder, "legacy.blend"), str(legacy))
    fail_reply("save_as exige folder y name juntos", client.command("file.save_as", {"name": "prueba"}), "bad_payload")
    fail_reply("save_as no mezcla formatos", client.command("file.save_as", {
        "path": "otro", "folder": folder, "name": "prueba"}), "bad_payload")
    for unsafe_name in ("", ".", "..", "sub/prueba", "sub\\prueba", "nul\x00name"):
        fail_reply(f"nombre inseguro {unsafe_name!r}", client.command("file.save_as", {
            "folder": folder, "name": unsafe_name}), "bad_payload")
    fail_reply("folder debe ser directorio", client.command("file.save_as", {
        "folder": os.path.join(folder, "ignorado.txt"), "name": "prueba"}), "not_directory")

    info = ok_reply("file.save_as folder+name", client.command("file.save_as", {
        "folder": listing["path"], "name": "prueba"}))
    check("guardó con extensión .blend", info.get("path", "").endswith("prueba.blend"), str(info))
    check("el archivo existe en disco", os.path.isfile(target + ".blend"), info.get("path", ""))
    check("ya consta como guardado", info.get("saved") is True, str(info))

    ok_reply("file.save sobre la ruta ya conocida", client.command("file.save"))

    info = ok_reply("file.new", client.command("file.new"))
    check("el archivo nuevo no tiene ruta", info.get("saved") is False, str(info))

    info = ok_reply("file.open", client.command("file.open", {"path": target + ".blend"}))
    check("reabrió el archivo guardado", info.get("name") == "prueba.blend", str(info))
    fail_reply("open rechaza extensión ajena", client.command("file.open", {"path": os.path.join(folder, "ignorado.txt")}), "not_blend")

    # El servidor tiene que seguir en pie después de cargar otro .blend: el timer del
    # puente es persistent, pero es justo lo que se rompería sin darse cuenta.
    ok_reply("el servidor sigue vivo tras abrir", client.command("server.ping"))
    state_after = ok_reply("scene.get_state tras abrir", client.command("scene.get_state"))
    check("hay estado tras la carga", "mode" in state_after, str(state_after))

    ok_reply("restaurar carpeta predeterminada", client.command("file.default_folder", {"path": original_default}))
    shutil.rmtree(folder, ignore_errors=True)


def modeling_scenario(client: WSClient) -> None:
    print("\n[18] Modificadores, hide, apply y loop cut")
    ok_reply("escena limpia", client.command("file.new"))
    ok_reply("seleccionar Cube", client.command("object.select", {"names": ["Cube"]}))

    opts = ok_reply("modifier.add_options", client.command("modifier.add_options"))
    types = opts.get("types", {})
    for kind in ("SUBSURF", "ARRAY", "BEVEL", "SOLIDIFY", "BOOLEAN", "MIRROR"):
        check(f"catálogo incluye {kind}", kind in types, str(types))
    fail_reply("tipo inventado", client.command("modifier.add", {"type": "NO_EXISTE"}), "bad_payload")

    mirror = ok_reply("add MIRROR", client.command("modifier.add", {"type": "MIRROR"}))
    mirror_state = next(m for m in mirror["modifiers"] if m["type"] == "MIRROR")
    check("mirror por defecto en X", mirror_state["parameters"]["use_axis_x"] is True, str(mirror_state))
    mirror_name = mirror_state["name"]
    changed = ok_reply("mirror activa Y", client.command("modifier.set", {
        "name": mirror_name, "parameters": {"use_axis_y": True, "use_clip": True}}))
    mirror_state = next(m for m in changed["modifiers"] if m["name"] == mirror_name)
    check("set parcial conserva X", mirror_state["parameters"]["use_axis_x"] is True, str(mirror_state))
    check("mirror activa Y y clipping", mirror_state["parameters"]["use_axis_y"] is True
          and mirror_state["parameters"]["use_clip"] is True, str(mirror_state))
    fail_reply("mirror consigo mismo", client.command("modifier.set", {
        "name": mirror_name, "parameters": {"mirror_object": "Cube"}}), "bad_payload")
    ok_reply("quitar mirror", client.command("modifier.remove", {"name": mirror_name}))

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

    print("  shade flat / smooth")
    shaded = ok_reply("object.shade smooth", client.command(
        "object.shade", {"objects": ["Cube"], "mode": "SMOOTH"}))
    check("shade devuelve SMOOTH", shaded.get("shade") == "SMOOTH", str(shaded))
    # El estado tiene que seguir al comando: la tablet rotula su interruptor con esto.
    ok_reply("activar el cubo", client.command("object.set_active", {"name": "Cube"}))
    smooth_state = ok_reply("estado tras SMOOTH", client.command("scene.get_state"))
    check("el estado dice que está suave",
          smooth_state["active"]["mesh"]["shade_smooth"] is True,
          str(smooth_state["active"]["mesh"]))
    toggled = ok_reply("object.shade toggle", client.command(
        "object.shade", {"objects": ["Cube"], "mode": "TOGGLE"}))
    check("toggle vuelve a FLAT", toggled.get("shade") == "FLAT", str(toggled))
    flat_state = ok_reply("estado tras TOGGLE", client.command("scene.get_state"))
    check("el estado vuelve a plano",
          flat_state["active"]["mesh"]["shade_smooth"] is False,
          str(flat_state["active"]["mesh"]))
    fail_reply("shade inválido", client.command("object.shade", {"mode": "CURVED"}), "bad_payload")

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
    loop_selection = ok_reply("selección del preview cuts=2", client.command("selection.info"))
    check("Loop Cut selecciona solo los dos loops nuevos",
          len(loop_selection.get("edges", [])) == 8, str(loop_selection))
    confirmed = ok_reply("confirm loop cut", client.command("tool.confirm"))
    check("fase confirmada", confirmed.get("phase") == "CONFIRMED", str(confirmed))
    ok_reply("deseleccionar", client.command("selection.all", {"value": False}))
    print("  LOOP_CUT: armado por toque (sin selección previa, B1/B3)")
    armed = ok_reply("sin arista queda armada, no falla", client.command("tool.begin", {"tool": "LOOP_CUT"}))
    check("fase ARMED", armed.get("phase") == "ARMED" and armed.get("armed") is True and armed.get("active") is False,
          str(armed))
    status_armed = ok_reply("tool.status en ARMED", client.command("tool.status"))
    check("status refleja ARMED", status_armed.get("phase") == "ARMED" and status_armed.get("tool") == "LOOP_CUT",
          str(status_armed))
    ok_reply("encuadrar el cubo para el toque", client.command("view.frame_all"))
    no_hit = client.command("tool.loop_pick", {"u": 0.02, "v": 0.02})
    check("toque fuera de malla sigue armada", no_hit.get("ok") and (no_hit.get("result") or {}).get("phase") == "ARMED",
          str(no_hit))
    picked = ok_reply("primer toque activa la sesión", client.command("tool.loop_pick", {"u": 0.5, "v": 0.5}))
    check("toque en viewport activa LOOP_CUT", picked.get("phase") == "ACTIVE" and picked.get("active") is True,
          str(picked))
    ok_reply("cancel tras armar por toque", client.command("tool.cancel"))
    idle = ok_reply("tool.status vuelve a IDLE", client.command("tool.status"))
    check("cancel desde armado deja IDLE", idle.get("phase") == "IDLE", str(idle))
    fail_reply("loop_pick sin sesión ni armado", client.command("tool.loop_pick", {"u": 0.5, "v": 0.5}), "no_session")

    print("  LOOP_CUT: opciones del modal (falloff/even/flip/clamp)")
    fail_reply("falloff inválido", client.command("tool.begin", {
        "tool": "LOOP_CUT", "edge": 0, "parameters": {"falloff": "NOPE"}}), "bad_payload")
    fail_reply("factor 1.5 con clamp", client.command("tool.begin", {
        "tool": "LOOP_CUT", "edge": 0, "parameters": {"factor": 1.5}}), "bad_payload")
    ok_reply("factor 1.5 sin clamp", client.command("tool.begin", {
        "tool": "LOOP_CUT", "edge": 0, "parameters": {"factor": 1.5, "clamp": False}}))
    fail_reply("loop_pop sin corte anterior", client.command("tool.loop_pop"), "empty_history")
    ok_reply("cancel factor largo", client.command("tool.cancel"))

    def _preview_cut_verts():
        """Coordenadas de los vértices que añadió el preview, por tramo posicional."""
        data = bpy.context.view_layer.objects.active.data
        bm_now = bmesh.from_edit_mesh(data)
        return sorted(tuple(round(c, 5) for c in v.co) for v in bm_now.verts if v.select)

    ok_reply("semilla flip", client.command("selection.elements", {"edges": [0], "mode": "SET"}))
    ok_reply("flip con 0.6", client.command("tool.begin", {
        "tool": "LOOP_CUT", "parameters": {"factor": 0.6, "flip": True}}))
    flipped = _preview_cut_verts()
    ok_reply("cancel flip", client.command("tool.cancel"))
    ok_reply("semilla espejo", client.command("selection.elements", {"edges": [0], "mode": "SET"}))
    ok_reply("factor -0.6", client.command("tool.begin", {
        "tool": "LOOP_CUT", "parameters": {"factor": -0.6}}))
    mirrored = _preview_cut_verts()
    ok_reply("cancel espejo", client.command("tool.cancel"))
    check("flip espeja el factor", flipped == mirrored, f"{flipped[:2]} vs {mirrored[:2]}")

    # even: tira de dos quads con columnas de altura 1/2/1. Con factor 0.5 el
    # reparto proporcional sube cada arista a su 75%; con even, la columna doble
    # avanza la misma distancia absoluta que las simples (t=2/3 → z=1.3333).
    wedge_mesh = bpy.data.meshes.new("Wed")
    bmw = bmesh.new()
    wv = [bmw.verts.new(co) for co in
          ((0, 0, 0), (0, 0, 1), (1, 0, 0), (1, 0, 2), (2, 0, 0), (2, 0, 1))]
    bmw.faces.new((wv[0], wv[1], wv[3], wv[2]))
    bmw.faces.new((wv[2], wv[3], wv[5], wv[4]))
    bmw.to_mesh(wedge_mesh)
    bmw.free()
    wedge = bpy.data.objects.new("Wed", wedge_mesh)
    bpy.context.collection.objects.link(wedge)
    bpy.context.view_layer.objects.active = wedge
    wedge.select_set(True)
    # Los operadores no se pueden lanzar desde el hilo del cliente: el cambio de
    # modo va por el propio servidor, que sí corre en el hilo principal.
    ok_reply("entrar en Edit para el wedge", client.command("mode.edit"))
    # El índice de la arista no es estable tras to_mesh: la semilla se localiza
    # por geometría (la columna de altura 1 en x=0).
    bmw_edit = bmesh.from_edit_mesh(wedge.data)
    column = next(e for e in bmw_edit.edges
                  if sorted(tuple(round(c, 4) for c in v.co) for v in e.verts) == [(0.0, 0.0, 0.0), (0.0, 0.0, 1.0)])
    seed = column.index
    base_count = ok_reply("topo del wedge", client.command("mesh.info"))["verts"]

    def _wedge_cut_heights():
        bm_live = bmesh.from_edit_mesh(wedge.data)
        return sorted(round(v.co.z, 4) for v in bm_live.verts[base_count:base_count + 3])

    begun = ok_reply("begin even", client.command("tool.begin", {
        "tool": "LOOP_CUT", "edge": seed, "parameters": {"factor": 0.5, "even": True}}))
    check("even viaja en la sesión", begun.get("parameters", {}).get("even") is True, str(begun))
    zs = _wedge_cut_heights()
    check("even coloca por longitud real", len(zs) == 3 and abs(zs[2] - 1.3333) < 1e-3, str(zs))
    ok_reply("cancel even", client.command("tool.cancel"))
    ok_reply("begin proporcional", client.command("tool.begin", {
        "tool": "LOOP_CUT", "edge": seed, "parameters": {"factor": 0.5}}))
    zs = _wedge_cut_heights()
    check("proporcional cae en el 75% de cada arista", len(zs) == 3 and abs(zs[2] - 1.5) < 1e-3, str(zs))
    ok_reply("cancel proporcional", client.command("tool.cancel"))
    ok_reply("wedge a Object", client.command("mode.object"))
    bpy.data.objects.remove(wedge, do_unlink=True)
    bpy.context.view_layer.objects.active = bpy.data.objects.get("Cube")
    client.command("mode.object")

    print("  selection.more / selection.less")
    ok_reply("escena para more/less", client.command("file.new"))
    ok_reply("Cube more", client.command("object.select", {"names": ["Cube"]}))
    fail_reply("more en Object", client.command("selection.more"), "wrong_mode")
    fail_reply("less en Object", client.command("selection.less"), "wrong_mode")
    ok_reply("entrar en Edit", client.command("mode.edit"))
    ok_reply("modo cara", client.command("selection.face"))
    ok_reply("una sola cara", client.command("selection.elements", {"faces": [0], "mode": "SET"}))
    grown = ok_reply("more caras", client.command("selection.more"))
    check("more añadió adyacentes", len(grown["faces"]) > 1, str(grown))
    grown_count = len(grown["faces"])
    shrunk = ok_reply("less caras", client.command("selection.less"))
    check("less retiró fronterizas", len(shrunk["faces"]) < grown_count, str(shrunk))
    ok_reply("modo vertice", client.command("selection.vertex"))
    ok_reply("un solo vertice", client.command("selection.elements", {"verts": [0], "mode": "SET"}))
    grown_v = ok_reply("more verts", client.command("selection.more"))
    check("more verts creció", len(grown_v["verts"]) > 1, str(grown_v))
    shrunk_v = ok_reply("less verts", client.command("selection.less"))
    check("less verts menguó", len(shrunk_v["verts"]) < len(grown_v["verts"]), str(shrunk_v))
    ok_reply("modo arista", client.command("selection.edge"))
    ok_reply("una sola arista", client.command("selection.elements", {"edges": [0], "mode": "SET"}))
    grown_e = ok_reply("more edges", client.command("selection.more"))
    check("more edges creció", len(grown_e["edges"]) > 1, str(grown_e))
    shrunk_e = ok_reply("less edges", client.command("selection.less"))
    check("less edges menguó", len(shrunk_e["edges"]) < len(grown_e["edges"]), str(shrunk_e))
    client.command("mode.object")

    print("  view.local")
    ok_reply("esfera detras", client.command("object.add", {"primitive": "SPHERE"}))
    sphere_name = client.command("scene.get_state")["result"]["active_object"]
    ok_reply("limpiar seleccion", client.command("object.select_all", {"value": False}))
    ok_reply("solo el cubo", client.command("object.select", {"names": ["Cube"]}))
    ok_reply("pre-ocultar esfera", client.command("object.hide", {"objects": [sphere_name]}))
    # select=False a propósito: el reveal por defecto selecciona, y una esfera
    # seleccionada no cuenta como "resto" a la hora de aislar.
    ok_reply("revelar esfera sin seleccionar", client.command("object.reveal", {"objects": [sphere_name], "select": False}))
    local_on = ok_reply("aislar", client.command("view.local"))
    check("local activo", local_on.get("local") is True, str(local_on))
    check("la esfera quedo oculta", client.command("scene.get_object", {"name": sphere_name})["result"]["visible"] is False)
    check("el cubo sigue visible", client.command("scene.get_object", {"name": "Cube"})["result"]["visible"] is True)
    ok_reply("ocultar la esfera de verdad", client.command("object.hide", {"objects": [sphere_name]}))
    local_off = ok_reply("desaislar", client.command("view.local", {"enabled": False}))
    check("local inactivo", local_off.get("local") is False, str(local_off))
    check("la esfera NO se revela al desaislar (se oculto aparte)",
          client.command("scene.get_object", {"name": sphere_name})["result"]["visible"] is False)
    check("el cubo sigue visible tras desaislar",
          client.command("scene.get_object", {"name": "Cube"})["result"]["visible"] is True)
    ok_reply("revelar todo", client.command("object.reveal"))
    ok_reply("aislar otra vez", client.command("view.local"))
    ok_reply("nuevo archivo con aislando", client.command("file.new"))
    state_after = ok_reply("estado tras new", client.command("scene.get_state"))
    check("new resetea el aislamiento sin ocultar nada",
          not state_after.get("hidden_objects"), str(state_after.get("hidden_objects")))

    print("  view.shading en background")
    # En background puede haber layout definido en el .blend (y el comando funciona
    # igualmente) o no haberlo: ambos caminos son correctos, la traza no.
    shading_reply = client.command("view.shading", {"mode": "WIREFRAME"})
    if shading_reply.get("ok"):
        state_shading = ok_reply("estado shading", client.command("scene.get_state"))
        check("el shading aplicado viaja en el estado",
              state_shading.get("shading") == "WIREFRAME", str(state_shading.get("shading")))
    else:
        check("shading sin viewport responde no_viewport",
              shading_reply.get("code") == "no_viewport", str(shading_reply))
    fail_reply("modo de shading invalido", client.command("view.shading", {"mode": "NOPE"}), "bad_payload")


def edit_context_ops_scenario(client: WSClient) -> None:
    """Operaciones discretas que alimentan el catálogo contextual de Edit."""
    print("\n[19] Operaciones contextuales de Edit")
    ok_reply("escena para F/P/Y/normales", client.command("file.new"))
    ok_reply("Cube para operaciones contextuales", client.command("object.select", {"names": ["Cube"]}))
    ok_reply("entrar Edit contextual", client.command("mode.edit"))

    # F en vértices: buscamos una diagonal que no exista (el orden de vértices
    # del startup file no es una parte estable del contrato de Blender).
    ok_reply("modo vértice para F", client.command("selection.vertex"))
    bm = bmesh.from_edit_mesh(bpy.context.view_layer.objects.active.data)
    first, second = next((a, b) for pos, a in enumerate(bm.verts) for b in bm.verts[pos + 1:]
                         if bm.edges.get((a, b)) is None)
    ok_reply("dos vértices diagonales", client.command("selection.elements", {
        "verts": [first.index, second.index], "mode": "SET"}))
    made = ok_reply("make edge", client.command("mesh.make_edge_face"))
    check("F crea una arista", made.get("created") == "EDGE", str(made))
    fail_reply("F no duplica arista", client.command("mesh.make_edge_face"), "geometry_exists")

    # F con 3+ vértices vuelve a crear una cara desde un contorno conocido.
    ok_reply("modo cara para borrar", client.command("selection.face"))
    bm = bmesh.from_edit_mesh(bpy.context.view_layer.objects.active.data)
    face_vertices = [vert.index for vert in bm.faces[0].verts]
    ok_reply("cara 0 para borrar", client.command("selection.elements", {"faces": [0], "mode": "SET"}))
    ok_reply("borrar solo cara", client.command("mesh.delete", {"what": "ONLY_FACES"}))
    ok_reply("modo vértice para crear cara", client.command("selection.vertex"))
    ok_reply("contorno de vértices", client.command("selection.elements", {"verts": face_vertices, "mode": "SET"}))
    face = ok_reply("make face", client.command("mesh.make_edge_face"))
    check("F crea cara desde vértices", face.get("created") == "FACE", str(face))

    # Un segundo contorno de una cara eliminada se rellena desde submodo arista.
    ok_reply("modo cara para segundo borrar", client.command("selection.face"))
    ok_reply("cara 0 para segundo borrar", client.command("selection.elements", {"faces": [0], "mode": "SET"}))
    ok_reply("borrar segunda cara", client.command("mesh.delete", {"what": "ONLY_FACES"}))
    ok_reply("modo arista para fill", client.command("selection.edge"))
    bm = bmesh.from_edit_mesh(bpy.context.view_layer.objects.active.data)
    boundary = [edge.index for edge in bm.edges if len(edge.link_faces) == 1]
    ok_reply("contorno abierto", client.command("selection.elements", {"edges": boundary, "mode": "SET"}))
    filled = ok_reply("fill contorno", client.command("mesh.make_edge_face"))
    check("F rellena el borde", filled.get("created") == "FACE" and filled.get("count", 0) >= 1, str(filled))

    # Normales: una cara seleccionada responde en ambos sentidos y el flip.
    ok_reply("modo cara normales", client.command("selection.face"))
    ok_reply("cara para normales", client.command("selection.elements", {"faces": [0], "mode": "SET"}))
    outside = ok_reply("recalcular exterior", client.command("mesh.normals_recalculate"))
    inside = ok_reply("recalcular interior", client.command("mesh.normals_recalculate", {"inside": True}))
    flipped = ok_reply("voltear normales", client.command("mesh.normals_flip"))
    check("normales anuncian el sentido", outside.get("inside") is False and inside.get("inside") is True and flipped.get("faces") == 1,
          f"{outside} {inside} {flipped}")

    # Y mantiene un único objeto; P crea uno nuevo con la selección de cara.
    before_objects = set(bpy.data.objects.keys())
    ok_reply("split de cara", client.command("mesh.split"))
    check("Y no crea objeto", set(bpy.data.objects.keys()) == before_objects, str(set(bpy.data.objects.keys()) - before_objects))
    separated = ok_reply("separate selection", client.command("mesh.separate"))
    created = separated.get("created_objects", [])
    check("P crea objeto", len(created) == 1 and created[0] in bpy.data.objects, str(separated))
    ok_reply("volver a Object tras P", client.command("mode.object"))


def bridge_edge_loops_scenario(client: WSClient) -> None:
    print("\n[20] Bridge Edge Loops paramétrico")
    ok_reply("escena para bridge", client.command("file.new"))
    cube = bpy.data.objects.get("Cube")
    bpy.data.objects.remove(cube, do_unlink=True)
    data = bpy.data.meshes.new("BridgeRings")
    build = bmesh.new()
    lower = [build.verts.new(co) for co in ((-1, -1, 0), (1, -1, 0), (0, 1, 0))]
    upper = [build.verts.new(co) for co in ((-1, -1, 2), (1, -1, 2), (0, 1, 2))]
    for ring in (lower, upper):
        for index in range(3):
            build.edges.new((ring[index], ring[(index + 1) % 3]))
    build.to_mesh(data)
    build.free()
    rings = bpy.data.objects.new("BridgeRings", data)
    bpy.context.collection.objects.link(rings)
    bpy.context.view_layer.objects.active = rings
    rings.select_set(True)

    ok_reply("entrar Edit bridge", client.command("mode.edit"))
    ok_reply("modo edge bridge", client.command("selection.edge"))
    before = ok_reply("topo antes bridge", client.command("mesh.info"))
    ok_reply("dos loops para bridge", client.command("selection.elements", {
        "edges": list(range(before["edges"])), "mode": "SET"}))
    begun = ok_reply("begin bridge", client.command("tool.begin", {
        "tool": "BRIDGE_EDGE_LOOPS", "parameters": {"twist_offset": 0, "merge": False, "merge_factor": 0.0}}))
    check("sesión bridge activa", begun.get("active") and begun.get("tool") == "BRIDGE_EDGE_LOOPS", str(begun))
    preview = ok_reply("topo preview bridge", client.command("mesh.info"))
    check("bridge añade caras", preview["faces"] == before["faces"] + 3, f"{before} -> {preview}")
    ok_reply("twist bridge", client.command("tool.parameter", {"parameters": {"twist_offset": 1}}))
    ok_reply("cancel bridge", client.command("tool.cancel"))
    restored = ok_reply("topo cancel bridge", client.command("mesh.info"))
    check("cancel bridge restaura", restored["faces"] == before["faces"], f"{before} -> {restored}")

    ok_reply("un loop invalido", client.command("selection.elements", {"edges": [0, 1, 2], "mode": "SET"}))
    fail_reply("bridge exige dos loops", client.command("tool.begin", {"tool": "BRIDGE_EDGE_LOOPS"}), "empty_selection")
    ok_reply("volver Object bridge", client.command("mode.object"))


def knife_scenario(client: WSClient) -> None:
    print("\n[21] Knife: motor geométrico y sesión")
    from blender_tablet_remote.commands import knife as knife_commands
    from blender_tablet_remote.commands import tools as tool_commands

    # Geometría: rejilla 3x3 construida con subdivide_edges y cortada en línea recta.
    bm = bmesh.new()
    corners = [bm.verts.new((x, y, 0)) for x, y in ((-5, -5), (5, -5), (5, 5), (-5, 5))]
    bm.faces.new(corners)
    grid = list(bm.faces)
    bmesh.ops.subdivide_edges(bm, edges=list(grid[0].edges), cuts=2)
    before_faces = len(bm.faces)
    result = knife_commands.cut_polyline(bm, [[-5.0, 1.0, 0.0], [5.0, 1.0, 0.0]], False)
    check("knife corta la rejilla", len(bm.faces) > before_faces and result["segments"] == 1,
          f"{before_faces} -> {len(bm.faces)} {result}")
    closed = knife_commands.cut_polyline(
        bm, [[-4.0, -4.0, 0.0], [4.0, -4.0, 0.0], [4.0, 4.0, 0.0], [-4.0, 4.0, 0.0]], True)
    check("knife cierra la polilínea", closed["segments"] == 4, str(closed))
    auto_snap = tool_commands._knife_snap_thresholds("AUTO")
    forced_snap = tool_commands._knife_snap_thresholds("VERTEX")
    check("Knife AUTO deja accesible la arista",
          auto_snap[0] < forced_snap[0] and auto_snap[1] < forced_snap[1],
          f"auto={auto_snap} forced={forced_snap}")
    bm.free()

    # El corte de las capturas del usuario: esquina -> punto interior -> borde opuesto.
    # Una cara atravesada se parte en DOS, y el punto interior queda en la frontera del
    # corte. Si el motor triangula la cara en abanico (el viejo `_poke`), aquí salen
    # cuatro triángulos y diagonales que nadie dibujó.
    bm = bmesh.new()
    quad = [bm.verts.new(co) for co in ((-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0))]
    bm.faces.new(quad)
    knife_commands.cut_polyline(
        bm, [[-1.0, 1.0, 0.0], [0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], False)
    caras = sorted(len(f.verts) for f in bm.faces)
    check("un trazo por el interior parte la cara en dos", len(bm.faces) == 2, str(caras))
    check("el corte no triangula la cara en abanico",
          all(n >= 4 for n in caras), f"caras por número de vértices: {caras}")
    interior = [v for v in bm.verts
                if abs(v.co.x) < 1e-6 and abs(v.co.y) < 1e-6]
    check("el punto interior existe una sola vez", len(interior) == 1, str([tuple(v.co) for v in interior]))
    check("el punto interior solo une el trazo, no las esquinas",
          bool(interior) and len(interior[0].link_edges) == 2,
          str(len(interior[0].link_edges) if interior else "sin vértice"))
    bm.free()

    # Sesión: begin sin puntos, confirm falla, cancel restaura.
    ok_reply("escena knife", client.command("file.new"))
    ok_reply("Cube knife", client.command("object.select", {"names": ["Cube"]}))
    ok_reply("entrar Edit knife", client.command("mode.edit"))
    begun = ok_reply("begin KNIFE", client.command("tool.begin", {"tool": "KNIFE"}))
    check("sesión KNIFE activa", begun.get("active") and begun.get("tool") == "KNIFE", str(begun))
    obj = bpy.context.view_layer.objects.active
    bm = bmesh.from_edit_mesh(obj.data)
    topology_before = (len(bm.verts), len(bm.edges), len(bm.faces))
    from blender_tablet_remote.errors import CommandError as KnifeCommandError
    original_cut_polyline = knife_commands.cut_polyline

    def partial_then_fail(bm, _points, _closed):
        bm.verts.new((0.25, 0.25, 1.0))
        raise KnifeCommandError("Anchor not on mesh surface", code="disconnected_surface")

    knife_commands.cut_polyline = partial_then_fail
    tool_commands.tool_session.points = [[-0.5, 0.0, 1.0], [0.5, 0.0, 1.0]]
    try:
        atomic_reply = client.command("tool.confirm")
    finally:
        knife_commands.cut_polyline = original_cut_polyline
    bm = bmesh.from_edit_mesh(obj.data)
    topology_after = (len(bm.verts), len(bm.edges), len(bm.faces))
    check("confirm Knife inválido falla de forma controlada", atomic_reply.get("ok") is False, str(atomic_reply))
    check("confirm Knife inválido restaura BMesh completo", topology_after == topology_before,
          f"{topology_before} -> {topology_after}")
    tool_commands.tool_session.points = []
    fail_reply("confirm sin puntos", client.command("tool.confirm"), "empty_selection")
    pop = ok_reply("pop vacío no rompe", client.command("tool.knife_pop"))
    check("pop sin puntos ok", pop.get("active"), str(pop))
    ok_reply("cancel knife", client.command("tool.cancel"))
    client.command("mode.object")

    print("  Roll de cámara")
    from mathutils import Quaternion, Vector

    from blender_tablet_remote.camera import camera as tablet_camera

    tablet_camera.rotation = Quaternion((1.0, 0.0, 0.0, 0.0))
    tablet_camera.roll(math.pi / 2)
    forward = tablet_camera.rotation @ Vector((0.0, 0.0, -1.0))
    up = tablet_camera.rotation @ Vector((0.0, 1.0, 0.0))
    check("roll conserva el eje de visión", (forward - Vector((0, 0, -1))).length < 1e-5, str(forward))
    check("roll gira 90° sobre el eje", abs(up.y) < 1e-5 and abs(up.z) < 1e-5, str(up))


def extrude_axis_scenario(client: WSClient) -> None:
    print("\n[22] Extrude: restricción de eje")

    def _select_top_face():
        obj = bpy.context.view_layer.objects.active
        bm = bmesh.from_edit_mesh(obj.data)
        index = next(f.index for f in bm.faces if f.normal.z > 0.5)
        ok_reply("seleccionar cara superior", client.command("selection.elements", {"faces": [index], "mode": "SET"}))

    def _selected_verts():
        obj = bpy.context.view_layer.objects.active
        bm = bmesh.from_edit_mesh(obj.data)
        return [tuple(round(c, 4) for c in v.co) for v in bm.verts if v.select]

    ok_reply("escena extrude axis", client.command("file.new"))
    ok_reply("Cube extrude axis", client.command("object.select", {"names": ["Cube"]}))
    ok_reply("edit extrude axis", client.command("mode.edit"))
    ok_reply("cara extrude axis", client.command("selection.face"))
    _select_top_face()

    begun = ok_reply("begin extrude X global", client.command("tool.begin", {
        "tool": "EXTRUDE", "parameters": {"variant": "REGION", "constraint": "X", "orientation": "GLOBAL", "offset": 1.0}}))
    check("sesión extrude activa", begun.get("active") and begun.get("tool") == "EXTRUDE", str(begun))
    verts = _selected_verts()
    check("eje X global mueve +1 en X", abs(max(v[0] for v in verts) - 2.0) < 1e-3, str(verts))
    ok_reply("cambiar a Y", client.command("tool.parameter", {"parameters": {"constraint": "Y"}}))
    verts = _selected_verts()
    check("cambiar a Y recoloca sin acumular", abs(max(v[1] for v in verts) - 2.0) < 1e-3
          and abs(max(v[0] for v in verts) - 1.0) < 1e-3, str(verts))
    ok_reply("cancel extrude", client.command("tool.cancel"))

    # Objeto rotado 90° en Z: GLOBAL X debe resolver a LOCAL Y.
    ok_reply("rotar cubo 90", client.command("mode.object"))
    ok_reply("rotar Z", client.command("transform.rotate", {"z": 90.0, "absolute": True}))
    ok_reply("edit rotado", client.command("mode.edit"))
    ok_reply("cara rotada", client.command("selection.face"))
    _select_top_face()
    begun = ok_reply("begin extrude X global rotado", client.command("tool.begin", {
        "tool": "EXTRUDE", "parameters": {"variant": "REGION", "constraint": "X", "orientation": "GLOBAL", "offset": 1.0}}))
    verts = _selected_verts()
    # En un objeto rotado 90° en Z, el X mundial es el -Y local: la cara superior se
    # desplaza en X mundial, que en las coordenadas locales del cubo es -Y.
    check("X global respeta la rotación del objeto", abs(max(v[0] for v in verts) - 1.0) < 1e-3
          and any(abs(v[1] + 2.0) < 1e-3 for v in verts), str(verts))
    ok_reply("cancel extrude rotado", client.command("tool.cancel"))
    ok_reply("volver rotación", client.command("mode.object"))
    ok_reply("reset rot", client.command("transform.rotate", {"z": 0.0, "absolute": True}))

    # Rechazos y errores.
    ok_reply("edit rechazos", client.command("mode.edit"))
    ok_reply("cara rechazos", client.command("selection.face"))
    _select_top_face()
    fail_reply("eje en ALONG_NORMALS", client.command("tool.begin", {
        "tool": "EXTRUDE", "parameters": {"variant": "ALONG_NORMALS", "constraint": "X"}}), "incompatible_parameter")
    fail_reply("eje inválido", client.command("tool.begin", {
        "tool": "EXTRUDE", "parameters": {"constraint": "W"}}), "bad_payload")
    fail_reply("orientación inválida", client.command("tool.begin", {
        "tool": "EXTRUDE", "parameters": {"constraint": "X", "orientation": "NOPE"}}), "bad_payload")
    fail_reply("direction y constraint", client.command("mesh.extrude", {
        "direction": [0, 0, 1], "constraint": "X", "_no_undo": True}), "bad_payload")
    ok_reply("volver object extrude axis", client.command("mode.object"))


def inset_variant_scenario(client: WSClient) -> None:
    print("\n[23] Inset: variante REGION/INDIVIDUAL")
    ok_reply("escena inset variant", client.command("file.new"))
    ok_reply("Cube inset variant", client.command("object.select", {"names": ["Cube"]}))
    ok_reply("edit inset variant", client.command("mode.edit"))
    ok_reply("cara inset variant", client.command("selection.face"))
    ok_reply("dos caras", client.command("selection.elements", {"faces": [0, 1], "mode": "SET"}))

    region = ok_reply("begin inset REGION", client.command("tool.begin", {
        "tool": "INSET", "parameters": {"variant": "REGION", "thickness": 0.1}}))
    check("variant REGION viaja en la sesión", region.get("parameters", {}).get("variant") == "REGION", str(region))
    check("resultado anuncia REGION", region.get("preview", {}).get("variant") == "REGION", str(region))
    ok_reply("cancel inset REGION", client.command("tool.cancel"))

    individual = ok_reply("begin inset INDIVIDUAL", client.command("tool.begin", {
        "tool": "INSET", "parameters": {"variant": "INDIVIDUAL", "thickness": 0.1}}))
    check("variant INDIVIDUAL viaja en la sesión",
          individual.get("parameters", {}).get("variant") == "INDIVIDUAL", str(individual))
    check("resultado anuncia INDIVIDUAL", individual.get("preview", {}).get("variant") == "INDIVIDUAL", str(individual))
    ok_reply("cancel inset INDIVIDUAL", client.command("tool.cancel"))
    ok_reply("volver object inset variant", client.command("mode.object"))


def scalar_snap_scenario(client: WSClient) -> None:
    """Sesiones tool.* en vez de history.undo: en background no hay pila de undo,

    así que cancel (que restaura desde el backup de la sesión) es la única forma
    limpia de comparar "con snap" y "sin snap" sobre la misma selección.
    """
    print("\n[24] Snap real de incremento en Extrude y Loop Cut (B5)")
    ok_reply("escena snap escalar", client.command("file.new"))
    ok_reply("Cube snap escalar", client.command("object.select", {"names": ["Cube"]}))
    ok_reply("edit snap escalar", client.command("mode.edit"))
    ok_reply("cara snap escalar", client.command("selection.face"))
    ok_reply("una cara", client.command("selection.elements", {"faces": [0], "mode": "SET"}))

    plain = ok_reply("extrude sin snap", client.command("tool.begin", {
        "tool": "EXTRUDE", "parameters": {"offset": 0.37}}))
    check("offset sin snap se conserva exacto", abs(plain["preview"]["offset"] - 0.37) < 1e-9, str(plain))
    ok_reply("cancel extrude sin snap", client.command("tool.cancel"))

    ok_reply("misma cara para snap", client.command("selection.elements", {"faces": [0], "mode": "SET"}))
    snapped = ok_reply("extrude con snap INCREMENT", client.command("tool.begin", {
        "tool": "EXTRUDE", "parameters": {"offset": 0.37, "snap_type": "INCREMENT", "snap_step": 0.1}}))
    check("INCREMENT cuadra 0.37 a 0.4", abs(snapped["preview"]["offset"] - 0.4) < 1e-9, str(snapped))
    check("el snap sí cambia el resultado geométrico",
          abs(snapped["preview"]["offset"] - plain["preview"]["offset"]) > 1e-6,
          f"{plain['preview']['offset']} vs {snapped['preview']['offset']}")
    ok_reply("cancel extrude con snap", client.command("tool.cancel"))

    ok_reply("cara para snap inválido", client.command("selection.elements", {"faces": [0], "mode": "SET"}))
    geometric = ok_reply("snap geométrico arma Extrude sin candidato", client.command("tool.begin", {
        "tool": "EXTRUDE", "parameters": {"offset": 0.1, "snap_type": "VERTEX"}}))
    check("estado publica snap geométrico y candidato vacío",
          geometric.get("snap_type") == "VERTEX" and geometric.get("snap_candidate") is None,
          str(geometric))
    ok_reply("cancel extrude geométrico", client.command("tool.cancel"))

    ok_reply("semilla loop cut snap", client.command("selection.edge"))
    ok_reply("arista semilla snap", client.command("selection.elements", {"edges": [0], "mode": "SET"}))
    loop_plain = ok_reply("loop cut sin snap", client.command("tool.begin", {
        "tool": "LOOP_CUT", "parameters": {"factor": 0.23}}))
    ok_reply("cancel loop cut sin snap", client.command("tool.cancel"))
    ok_reply("arista semilla snap 2", client.command("selection.elements", {"edges": [0], "mode": "SET"}))
    loop_snapped = ok_reply("loop cut con snap GRID (=INCREMENT)", client.command("tool.begin", {
        "tool": "LOOP_CUT", "parameters": {"factor": 0.23, "snap_type": "GRID", "snap_step": 0.1}}))
    check("GRID cuadra el factor como INCREMENT", abs(loop_snapped["preview"]["factor"] - 0.2) < 1e-9,
          str(loop_snapped))
    check("el snap de Loop Cut también cambia el resultado",
          abs(loop_snapped["preview"]["factor"] - loop_plain["preview"]["factor"]) > 1e-6,
          f"{loop_plain['preview']['factor']} vs {loop_snapped['preview']['factor']}")
    ok_reply("cancel loop cut con snap", client.command("tool.cancel"))
    ok_reply("volver object snap escalar", client.command("mode.object"))


def bisect_scenario(client: WSClient) -> None:
    print("\n[25] Cut: Bisect (arrastre de línea, B4)")
    ok_reply("escena bisect", client.command("file.new"))
    ok_reply("Cube bisect", client.command("object.select", {"names": ["Cube"]}))
    fail_reply("bisect en Object", client.command("tool.begin", {"tool": "BISECT"}), "wrong_mode")

    ok_reply("edit bisect", client.command("mode.edit"))
    ok_reply("encuadrar cubo para bisect", client.command("view.frame_all"))
    before = ok_reply("topo antes de bisect", client.command("mesh.info"))

    armed = ok_reply("BISECT arma sin geometría", client.command("tool.begin", {"tool": "BISECT"}))
    check("fase ARMED para Bisect", armed.get("phase") == "ARMED" and armed.get("active") is False, str(armed))
    fail_reply("nudge no aplica a Bisect", client.command("tool.nudge", {"delta": 0.1}), "no_session")

    degenerate = client.command("tool.drag_line", {"start": [0.5, 0.5], "end": [0.5, 0.5]})
    check("línea de longitud cero es bad_payload", degenerate.get("code") == "bad_payload", str(degenerate))

    activated = ok_reply("arrastre completo activa Bisect", client.command("tool.drag_line", {
        "start": [0.1, 0.5], "end": [0.9, 0.5]}))
    check("Bisect queda ACTIVE tras el arrastre", activated.get("phase") == "ACTIVE" and activated.get("active"),
          str(activated))
    preview = ok_reply("topo preview bisect", client.command("mesh.info"))
    check("el corte añade aristas/vértices", preview["verts"] > before["verts"], f"{before} -> {preview}")

    ok_reply("activar fill", client.command("tool.parameter", {"parameters": {"fill": True}}))
    filled = ok_reply("topo con fill", client.command("mesh.info"))
    check("fill añade caras nuevas en el corte", filled["faces"] >= preview["faces"], f"{preview} -> {filled}")

    redrawn = ok_reply("redibujar línea no acumula", client.command("tool.drag_line", {
        "start": [0.5, 0.1], "end": [0.5, 0.9]}))
    check("redibujar sigue ACTIVE", redrawn.get("active") is True, str(redrawn))
    redrawn_info = ok_reply("topo tras redibujar", client.command("mesh.info"))
    check("redibujar reconstruye, no acumula", redrawn_info["verts"] < filled["verts"] * 2, str(redrawn_info))

    ok_reply("cancel bisect", client.command("tool.cancel"))
    cancelled = ok_reply("topo cancel bisect", client.command("mesh.info"))
    check("cancel restaura la topología exacta", cancelled["verts"] == before["verts"], str(cancelled))

    ok_reply("rearmar bisect", client.command("tool.begin", {"tool": "BISECT"}))
    ok_reply("línea de confirmación", client.command("tool.drag_line", {"start": [0.1, 0.5], "end": [0.9, 0.5]}))
    confirmed = ok_reply("confirm bisect", client.command("tool.confirm"))
    check("confirm crea un único paso de sesión", confirmed.get("phase") == "CONFIRMED", str(confirmed))
    after_confirm = ok_reply("topo tras confirm", client.command("mesh.info"))
    check("confirm deja el corte", after_confirm["verts"] > before["verts"], str(after_confirm))

    ok_reply("escena nueva para línea que falla", client.command("file.new"))
    ok_reply("Cube línea que falla", client.command("object.select", {"names": ["Cube"]}))
    ok_reply("edit línea que falla", client.command("mode.edit"))
    ok_reply("encuadrar para línea que falla", client.command("view.frame_all"))
    ok_reply("rearmar bisect para línea que falla", client.command("tool.begin", {"tool": "BISECT"}))
    missed = client.command("tool.drag_line", {"start": [0.001, 0.999], "end": [0.01, 0.999]})
    still_armed = ok_reply("tool.status tras línea fallida", client.command("tool.status"))
    check("una línea que no cruza geometría vuelve a ARMED, no a IDLE",
          still_armed.get("phase") in ("ARMED", "ACTIVE"), str((missed, still_armed)))
    ok_reply("cancelar lo que quedara armado/activo", client.command("tool.cancel"))
    ok_reply("volver object bisect", client.command("mode.object"))


def rotate_scale_sign_scenario(client: WSClient) -> None:
    """Fija el signo de B6 con pruebas: dedo a la derecha (dx > 0) es horario y

    agranda, tanto en la transformación modal como en la ruta legacy de gestos.
    Move, orbit, pan, zoom y roll no se tocan en este ciclo y no se prueban aquí.
    """
    print("\n[26] Signo de Rotate/Scale: arrastre horizontal (B6)")
    ok_reply("escena signo rotate/scale", client.command("file.new"))
    ok_reply("Cube signo rotate/scale", client.command("object.select", {"names": ["Cube"]}))

    print("  Modal: Rotate")
    begun = ok_reply("begin rotate modal", client.command("transform.begin", {"mode": "ROTATE"}))
    check("ángulo arranca en cero", begun.get("angle", 0.0) == 0.0, str(begun))
    nudged = ok_reply("nudge dx positivo (derecha)", client.command("transform.nudge", {"dx": 0.1, "dy": 0.0}))
    check("dedo a la derecha da ángulo negativo (horario en pantalla)",
          nudged.get("angle", 0.0) < 0.0, str(nudged))
    ok_reply("cancel rotate modal", client.command("transform.cancel"))

    print("  Modal: Scale")
    begun = ok_reply("begin scale modal", client.command("transform.begin", {"mode": "SCALE"}))
    check("valores arrancan en 1", all(abs(v - 1.0) < 1e-9 for v in begun.get("values", [])), str(begun))
    nudged = ok_reply("nudge dx positivo agranda", client.command("transform.nudge", {"dx": 0.1, "dy": 0.0}))
    check("dedo a la derecha agranda (factor > 1)", all(v > 1.0 for v in nudged.get("values", [])), str(nudged))
    ok_reply("reabrir scale modal", client.command("transform.cancel"))
    ok_reply("reabrir scale modal 2", client.command("transform.begin", {"mode": "SCALE"}))
    nudged = ok_reply("nudge dx negativo encoge", client.command("transform.nudge", {"dx": -0.1, "dy": 0.0}))
    check("dedo a la izquierda encoge (factor < 1)", all(v < 1.0 for v in nudged.get("values", [])), str(nudged))
    ok_reply("cancel scale modal", client.command("transform.cancel"))

    print("  Legacy: rotate (eje Z fijo, sin sesión modal)")
    ok_reply("rot Z a cero", client.command("transform.rotate", {"z": 0.0, "absolute": True}))
    client.gesture("rotate", "begin", axis="Z")
    for _ in range(10):
        client.gesture("rotate", "update", dx=0.02, axis="Z")
    client.gesture("rotate", "end", dx=0.0, axis="Z")
    time.sleep(0.3)
    info = ok_reply("estado tras rotate legacy", client.command("scene.get_object", {"name": "Cube"}))
    check("dedo a la derecha gira horario (Z negativo) en la ruta legacy",
          info["rotation_euler"][2] < 0.0, str(info["rotation_euler"]))
    ok_reply("reset rot legacy", client.command("transform.rotate", {"z": 0.0, "absolute": True}))


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
            edit_context_ops_scenario(extra)
            bridge_edge_loops_scenario(extra)
            knife_scenario(extra)
            extrude_axis_scenario(extra)
            inset_variant_scenario(extra)
            scalar_snap_scenario(extra)
            dissolve_scenario(extra)
            bisect_scenario(extra)
            rotate_scale_sign_scenario(extra)
            proportional_automerge_scenario(extra)
            session_exclusion_scenario(extra)
        finally:
            extra.close()

        auth_scenario()
        query_token_scenario()
    except Exception:  # noqa: BLE001
        _results.append(("excepción en el cliente", False, traceback.format_exc()))
        print(traceback.format_exc())
    finally:
        done.set()


def dissolve_scenario(client: WSClient) -> None:
    print("\n[27] Dissolve conserva superficie y es distinto de Delete")
    for mode, what, field in (("vertex", "VERTS", "verts"),
                              ("edge", "EDGES", "edges"),
                              ("face", "FACES", "faces")):
        ok_reply(f"escena dissolve {mode}", client.command("file.new"))
        ok_reply(f"edit dissolve {mode}", client.command("mode.edit"))
        ok_reply(f"submodo dissolve {mode}", client.command(f"selection.{mode}"))
        before = ok_reply(f"topología antes dissolve {mode}", client.command("mesh.info"))
        ok_reply(f"seleccionar elemento dissolve {mode}", client.command(
            "selection.elements", {field: [0], "mode": "SET"}))
        result = ok_reply(f"mesh.dissolve {what}", client.command("mesh.dissolve", {"what": what}))
        check(f"dissolve responde tipo {what}", result.get("dissolved") == what, str(result))
        after = ok_reply(f"topología tras dissolve {mode}", client.command("mesh.info"))
        check(f"dissolve {mode} no añade geometría",
              after[field] <= before[field], f"{before} -> {after}")
        ok_reply(f"object tras dissolve {mode}", client.command("mode.object"))


def proportional_automerge_scenario(client: WSClient) -> None:
    print("\n[28] Edición proporcional y Auto Merge")
    ok_reply("escena limpia proporcional", client.command("file.new"))
    ok_reply("entrar Edit proporcional", client.command("mode.edit"))
    ok_reply("submodo vértice proporcional", client.command("selection.vertex"))
    ok_reply("seleccionar un vértice proporcional", client.command(
        "selection.elements", {"verts": [0], "mode": "SET"}))
    settings = ok_reply("activar proporcional", client.command("edit.settings_set", {
        "proportional": True,
        "falloff": "LINEAR",
        "radius": 10.0,
        "auto_merge": False,
    }))
    check("estado publica proporcional", settings.get("edit_settings", {}).get("proportional") is True,
          str(settings.get("edit_settings")))

    obj = bpy.context.view_layer.objects.active
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    before = [vert.co.copy() for vert in bm.verts]
    ok_reply("begin proporcional", client.command("transform.begin", {"mode": "MOVE"}))
    ok_reply("mover proporcional", client.command("transform.value", {"values": [1.0, 0.0, 0.0]}))
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    moved = [(vert.co - before[vert.index]).length for vert in bm.verts]
    check("seleccionado recibe movimiento completo", abs(moved[0] - 1.0) < 1e-4, str(moved))
    check("proporcional mueve vecinos con peso", any(1e-4 < distance < 0.9999 for distance in moved[1:]),
          str(moved))
    ok_reply("cancel proporcional", client.command("transform.cancel"))
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    restored = [(vert.co - before[vert.index]).length for vert in bm.verts]
    check("cancel restaura todos los vértices", max(restored) < 1e-5, str(restored))

    ok_reply("configurar Auto Merge", client.command("edit.settings_set", {
        "proportional": False,
        "auto_merge": True,
        "merge_threshold": 0.001,
    }))
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    vertex_count = len(bm.verts)
    target_delta = bm.verts[1].co - bm.verts[0].co
    ok_reply("begin Auto Merge", client.command("transform.begin", {"mode": "MOVE"}))
    ok_reply("llevar vértice al vecino", client.command("transform.value", {
        "values": list(target_delta),
    }))
    ok_reply("confirmar Auto Merge", client.command("transform.confirm"))
    bm = bmesh.from_edit_mesh(obj.data)
    check("Auto Merge suelda al confirmar", len(bm.verts) == vertex_count - 1,
          f"{vertex_count} -> {len(bm.verts)}")
    ok_reply("desactivar ajustes de prueba", client.command("edit.settings_set", {
        "proportional": False,
        "auto_merge": False,
    }))
    ok_reply("volver Object tras proporcional", client.command("mode.object"))


def session_exclusion_scenario(client: WSClient) -> None:
    """Las dos familias globales no pueden conservar previews simultáneas."""
    print("\n[sesiones] exclusión transform/tool")
    ok_reply("escena limpia para exclusión", client.command("file.new"))
    ok_reply("entrar Edit para exclusión", client.command("mode.edit"))
    ok_reply("seleccionar todo para exclusión", client.command("selection.all", {"value": True}))
    ok_reply("transform antes de tool", client.command("transform.begin", {"mode": "MOVE"}))
    ok_reply("tool cancela transform", client.command("tool.begin", {
        "tool": "EXTRUDE", "parameters": {"offset": 0.0},
    }))
    transform_state = ok_reply("estado transform tras tool", client.command("transform.status"))
    check("tool.begin deja transform inactiva", transform_state.get("active") is False, str(transform_state))
    ok_reply("transform cancela tool", client.command("transform.begin", {"mode": "MOVE"}))
    tool_state = ok_reply("estado tool tras transform", client.command("tool.status"))
    check("transform.begin deja tool inactiva", tool_state.get("active") is False, str(tool_state))
    ok_reply("cancelar transform de exclusión", client.command("transform.cancel"))
    ok_reply("volver Object tras exclusión", client.command("mode.object"))


def main_thread_session_safety_tests() -> None:
    """Reproduce el RNA eliminado que antes escapaba desde transform.session."""
    from blender_tablet_remote.commands.modal import session

    bpy.ops.object.select_all(action="SELECT")
    session.begin("MOVE", [], False, None)
    doomed = bpy.context.view_layer.objects.active
    bpy.data.objects.remove(doomed, do_unlink=True)
    modal_state = session.status()
    check("status invalida Object RNA eliminado", modal_state.get("active") is False, str(modal_state))

    original_broadcast_events = bridge._broadcast_events
    original_last_poll = bridge._last_event_poll
    try:
        def broken_broadcast():
            raise ReferenceError("simulated stale RNA during broadcast")

        bridge._broadcast_events = broken_broadcast
        bridge._last_event_poll = 0.0
        interval = bridge._pump()
        check("pump sobrevive a excepción de broadcast", interval is not None, str(interval))
    finally:
        bridge._broadcast_events = original_broadcast_events
        bridge._last_event_poll = original_last_poll


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

    main_thread_session_safety_tests()

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
