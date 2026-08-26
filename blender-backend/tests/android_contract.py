"""Verifica el contrato que habla el cliente Android, sin necesidad de compilarlo.

Reproduce byte a byte los mensajes que emite `WebSocketRemoteBlenderClient.kt` y
comprueba que el backend los entiende. Sirve para detectar desajustes de protocolo
(nombres de campo, dónde viaja el estado, unidades de los gestos) sin Android Studio.

Arranca primero un servidor:

    blender --background --python tools/run_server.py -- --port 8801 --token devtoken

y luego:

    python3 tests/android_contract.py --port 8801 --token devtoken
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from wsclient import WSClient  # noqa: E402

results: list[tuple[str, bool, str]] = []

# Espejo de los enums de Kotlin: SnapAction.command y Primitive. Un nombre mal
# tecleado ahí solo se vería al pulsar la entrada del menú en la tablet.
MENU_COMMANDS = [
    "object.add",
    "object.select",
    "object.select_all",
    "object.duplicate",
    "object.delete",
    "object.rename",
    "object.hide",
    "object.reveal",
    "transform.apply",
    "modifier.add_options",
    "modifier.add",
    "modifier.remove",
    "modifier.move",
    "modifier.set",
    "modifier.toggle",
    "modifier.apply",
    "mesh.loop_cut",
    "mesh.loop_probe",
    "tool.loop_pick",
    "view.shading",
    "view.local",
    "selection.more",
    "selection.less",
    "snap.cursor_to_world",
    "snap.cursor_to_selected",
    "snap.cursor_to_active",
    "snap.cursor_to_grid",
    "snap.selected_to_cursor",
    "snap.selected_to_grid",
    "snap.origin_to_cursor",
    "snap.origin_to_geometry",
    "snap.origin_to_center_of_mass",
    "file.info",
    "file.new",
    "file.open",
    "file.save",
    "file.save_as",
    "file.recent",
    "file.locations",
    "file.browse",
    "file.default_folder",
    "transform.begin",
    "transform.axes",
    "transform.snap",
    "transform.value",
    "transform.confirm",
    "transform.cancel",
    "transform.status",
    "transform.snap_candidate",
    # Herramientas paramétricas de Edit Mode (bandeja A4).
    "tool.begin",
    "tool.parameter",
    "tool.nudge",
    "tool.confirm",
    "tool.cancel",
    "tool.status",
    # Selección contextual y borrado de malla (menú radial).
    "selection.all",
    "selection.invert",
    "selection.hide",
    "selection.reveal",
    "selection.box",
    "selection.circle",
    "selection.loop",
    "selection.ring",
    "snap.query",
    "mesh.delete",
    # Footer de vistas.
    "view.axis",
    "view.frame_all",
    "view.perspective",
]

# Espejo del enum AddObject de Kotlin. Cada nombre viaja tal cual como `primitive`,
# así que una clave que no exista en el backend sería un menú que falla al pulsarlo.
PRIMITIVES = [
    "PLANE", "CUBE", "CIRCLE", "SPHERE", "ICO_SPHERE",
    "CYLINDER", "CONE", "TORUS", "GRID", "MONKEY",
    "BEZIER_CURVE", "BEZIER_CIRCLE", "NURBS_CURVE", "NURBS_CIRCLE", "PATH",
    "SURFACE_CURVE", "SURFACE_CIRCLE", "SURFACE_PATCH",
    "SURFACE_CYLINDER", "SURFACE_SPHERE", "SURFACE_TORUS",
    "META_BALL", "META_CAPSULE", "META_PLANE", "META_ELLIPSOID", "META_CUBE",
    "TEXT",
    "EMPTY_PLAIN_AXES", "EMPTY_ARROWS", "EMPTY_SINGLE_ARROW",
    "EMPTY_CIRCLE", "EMPTY_CUBE", "EMPTY_SPHERE", "EMPTY_CONE",
    "LIGHT_POINT", "LIGHT_SUN", "LIGHT_SPOT", "LIGHT_AREA",
    "CAMERA",
]


def _contains(actual, expected) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(key in actual and _contains(actual[key], value) for key, value in expected.items())
    return actual == expected


def check(name: str, condition, detail: str = "") -> bool:
    ok = bool(condition)
    results.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else '  <- ' + detail}")
    return ok


class AndroidLikeClient:
    """Espeja lo que hace el cliente Kotlin: token en cada mensaje, id UUID, sin auth."""

    def __init__(self, ws: WSClient):
        self.ws = ws

    def command(self, name: str, payload: dict | None = None) -> dict:
        return self.ws.command(name, payload or {})

    def gesture(self, gesture: str, phase: str, dx=0.0, dy=0.0, factor=1.0) -> None:
        self.ws.send(
            {"type": "gesture", "gesture": gesture, "phase": phase, "dx": dx, "dy": dy, "factor": factor}
        )

    def drag(self, gesture: str, steps: int = 10, dx=0.0, dy=0.0, factor=1.0) -> None:
        """Un arrastre completo tal y como lo emite InputSurface a 30 Hz."""
        self.gesture(gesture, "begin")
        for _ in range(steps):
            self.gesture(gesture, "update", dx=dx, dy=dy, factor=factor)
        self.gesture(gesture, "end")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8801)
    parser.add_argument("--token", default="")
    args = parser.parse_args()

    ws = WSClient(args.host, args.port, args.token, timeout=8.0)
    hello = ws.connect()
    app = AndroidLikeClient(ws)

    fixtures = Path(__file__).resolve().parent.parent / "fixtures" / "v2"
    expected_caps = json.loads((fixtures / "capabilities.json").read_text())
    actual_caps = app.command("server.capabilities").get("result") or {}
    check("capabilities coincide con fixture", _contains(actual_caps, expected_caps), str(actual_caps.get("features")))
    expected_stream = json.loads((fixtures / "hello.stream.json").read_text())
    check("hello.stream coincide con fixture",
          _contains(hello.get("stream") or {}, expected_stream), str(hello.get("stream")))
    options_fixture = json.loads((fixtures / "modifier.add_options.json").read_text())
    check("modifier.add_options coincide con fixture",
          app.command("modifier.add_options").get("result") == options_fixture)

    print("\n[1] Conexión tal como la hace la app (token en cada mensaje, sin type=auth)")
    check("el servidor saluda con hello", hello.get("type") is None or "server" in hello, str(hello))

    print("\n[2] El estado llega donde la app lo lee ahora: en 'result'")
    reply = ws.command("scene.get_state")
    check("scene.get_state ok", reply.get("ok"), str(reply))
    result = reply.get("result") or {}
    for key in ("mode", "active_object", "selected_objects", "selection_mode"):
        check(f"result contiene '{key}'", key in result, str(list(result)))
    check("NO viene en 'payload' (el bug antiguo)", "payload" not in reply)

    print("\n[3] Comandos de los botones del dock")
    check("mode.edit", app.command("mode.edit").get("ok"))
    check("selection.face", app.command("selection.face").get("ok"))
    # Una sola cara: extruir un cubo cerrado entero da normal media cero y solo
    # desplazaría la cáscara, que no es lo que hace nadie desde la tablet.
    check("selection.elements", app.command("selection.elements", {"faces": [0]}).get("ok"))

    info_before = app.command("mesh.info")["result"]
    reply = app.command("mesh.extrude", {"offset": 0.1})
    check("mesh.extrude acepta 'offset'", reply.get("ok"), str(reply))
    check("y sí desplaza (offset != 0)", reply.get("result", {}).get("offset") == 0.1, str(reply.get("result")))
    info_after = app.command("mesh.info")["result"]
    check("la malla creció", info_after["verts"] > info_before["verts"], f"{info_before['verts']} -> {info_after['verts']}")

    reply = app.command("mesh.bevel", {"offset": 0.02})
    check("mesh.bevel acepta 'offset'", reply.get("ok"), str(reply))
    check("usa el offset enviado", reply.get("result", {}).get("offset") == 0.02, str(reply.get("result")))

    check("mode.object", app.command("mode.object").get("ok"))
    check("object.duplicate", app.command("object.duplicate").get("ok"))
    check("object.delete", app.command("object.delete").get("ok"))

    print("\n[4] Toque = selección por raycast")
    app.command("object.select", {"names": ["Cube"]})
    reply = app.command("selection.pick", {"u": 0.5, "v": 0.5})
    check("selection.pick responde", reply.get("ok"), str(reply))
    check("devuelve 'hit'", "hit" in (reply.get("result") or {}), str(reply.get("result")))

    print("\n[5] Gestos con las unidades nuevas (fracción de pantalla)")
    view_before = app.command("view.get")["result"]
    app.drag("orbit", steps=10, dx=0.02, dy=0.01)
    time.sleep(0.3)
    view_after = app.command("view.get")["result"]
    check("orbit giró la vista", view_before["rotation"] != view_after["rotation"])

    app.drag("pan", steps=10, dx=0.02, dy=0.01)
    time.sleep(0.3)
    check("pan movió el centro", app.command("view.get")["result"]["location"] != view_after["location"])

    dist_before = app.command("view.get")["result"]["distance"]
    app.drag("zoom", steps=10, factor=1.02)
    time.sleep(0.3)
    dist_after = app.command("view.get")["result"]["distance"]
    check("zoom acercó", dist_after < dist_before, f"{dist_before} -> {dist_after}")
    check("y no se disparó (10 pasos de 1.02 ~ 1.22x)", dist_after > dist_before / 2, f"{dist_before} -> {dist_after}")

    print("\n[6] Arrastre de herramienta: move / rotate / scale")
    app.command("object.select", {"names": ["Cube"]})
    loc_before = app.command("scene.get_object", {"name": "Cube"})["result"]["location"]
    app.drag("move", steps=10, dx=0.01, dy=0.01)
    time.sleep(0.3)
    loc_after = app.command("scene.get_object", {"name": "Cube"})["result"]["location"]
    check("el gesto move desplazó el cubo", loc_before != loc_after, f"{loc_before} -> {loc_after}")

    scale_before = app.command("scene.get_object", {"name": "Cube"})["result"]["scale"]
    app.drag("scale", steps=10, factor=1.02)
    time.sleep(0.3)
    scale_after = app.command("scene.get_object", {"name": "Cube"})["result"]["scale"]
    check("el gesto scale escaló", scale_before != scale_after, f"{scale_before} -> {scale_after}")

    rot_before = app.command("scene.get_object", {"name": "Cube"})["result"]["rotation_euler"]
    app.drag("rotate", steps=10, dx=0.02)
    time.sleep(0.3)
    rot_after = app.command("scene.get_object", {"name": "Cube"})["result"]["rotation_euler"]
    check("el gesto rotate giró", rot_before != rot_after, f"{rot_before} -> {rot_after}")

    print("\n[7] Menús: todo comando que la app puede emitir tiene que existir")
    available = set(ws.command("server.capabilities")["result"]["commands"])
    for name in MENU_COMMANDS:
        check(f"el servidor conoce {name}", name in available)

    print("\n[8] Menú Añadir: el catálogo del servidor y el enum de la app coinciden")
    catalog = ws.command("object.add_options")["result"]["categories"]
    known = {name for names in catalog.values() for name in names}
    check("el enum no inventa entradas", not (set(PRIMITIVES) - known), str(set(PRIMITIVES) - known))
    check("el enum no se deja ninguna", not (known - set(PRIMITIVES)), str(known - set(PRIMITIVES)))

    app.command("mode.object")
    failures = [p for p in PRIMITIVES if not app.command("object.add", {"primitive": p}).get("ok")]
    check(f"se añaden las {len(PRIMITIVES)} entradas del menú", not failures, str(failures))

    # Blender añade en el cursor 3D; añadir siempre en el origen dejaría sin sentido
    # todo el submenú de cursor.
    app.command("snap.cursor_set", {"x": 4, "y": 0, "z": 0})
    app.command("object.add", {"primitive": "BEZIER_CURVE"})
    active = app.command("scene.get_state")["result"]["active_object"]
    location = app.command("scene.get_object", {"name": active})["result"]["location"]
    check("se añade en el cursor 3D", round(location[0], 2) == 4.0, str(location))

    print("\n[9] Cursor y origen")
    app.command("mode.object")
    app.command("object.select", {"names": ["Cube"]})
    reply = app.command("snap.cursor_to_selected")
    check("snap devuelve el cursor", "cursor" in (reply.get("result") or {}), str(reply))
    check("snap.cursor_to_world", app.command("snap.cursor_to_world").get("ok"))
    check("snap.selected_to_cursor", app.command("snap.selected_to_cursor").get("ok"))
    check("snap.origin_to_geometry", app.command("snap.origin_to_geometry").get("ok"))

    print("\n[10] Archivo: los campos que lee la app")
    reply = app.command("file.info")
    info = reply.get("result") or {}
    for key in ("name", "path", "saved", "dirty"):
        check(f"file.info trae '{key}'", key in info, str(list(info)))

    reply = app.command("file.recent", {"limit": 12})
    files = (reply.get("result") or {}).get("files")
    check("file.recent devuelve 'files'", isinstance(files, list), str(reply))
    if files:
        for key in ("name", "path", "folder", "exists"):
            check(f"cada reciente trae '{key}'", key in files[0], str(files[0]))

    locations = (app.command("file.locations").get("result") or {})
    check("file.locations trae carpeta por defecto", isinstance(locations.get("default_folder"), str), str(locations))
    check("file.locations trae lugares navegables", isinstance(locations.get("locations"), list), str(locations))
    listing = (app.command("file.browse", {"path": "@default"}).get("result") or {})
    check("file.browse trae paths opacos y breadcrumbs", all(key in listing for key in
          ("path", "parent", "breadcrumbs", "default_folder", "entries")), str(listing))
    check("breadcrumbs tienen name/path", bool(listing.get("breadcrumbs")) and
          all(set(crumb) >= {"name", "path"} for crumb in listing["breadcrumbs"]), str(listing.get("breadcrumbs")))
    # Verifica los nombres wire folder/name sin escribir ningún fichero real.
    invalid_save = app.command("file.save_as", {"folder": listing.get("path", "@default"),
                                                 "name": "carpeta/escena"})
    check("file.save_as acepta contrato folder/name y valida basename",
          invalid_save.get("code") == "bad_payload", str(invalid_save))

    # La app decide entre Guardar y Guardar como con este código; si cambiara,
    # "Guardar" fallaría en silencio sobre un archivo sin ruta.
    if not info.get("saved"):
        reply = app.command("file.save")
        check("file.save sin ruta responde 'no_path'", reply.get("code") == "no_path", str(reply))

    print("\n[11] Transformación modal")
    app.command("mode.object")
    app.command("object.select", {"names": ["Cube"]})
    app.command("transform.move", {"x": 0, "y": 0, "z": 0, "absolute": True})

    reply = app.command("transform.begin", {"mode": "MOVE", "axes": ["X"], "snap": True, "step": 0.01})
    result = reply.get("result") or {}
    for key in ("active", "mode", "axes", "snap", "step", "values", "angle"):
        check(f"la sesión trae '{key}'", key in result, str(list(result)))

    result = app.command("transform.value", {"values": [1.234, 5.0, 9.0]})["result"]
    check("el eje restringe y el snap cuadra", round(result["values"][0], 4) == 1.23, str(result["values"]))
    check("los ejes no elegidos quedan a cero", result["values"][1] == 0 and result["values"][2] == 0, str(result))

    # Soltar el dedo NO debe cerrar la transformación: es lo que permite recolocar
    # la mano a mitad de un desplazamiento largo.
    app.gesture("move", "end")
    time.sleep(0.3)
    check("soltar el dedo no cierra la sesión", app.command("transform.status")["result"]["active"] is True)

    loc = app.command("scene.get_object", {"name": "Cube"})["result"]["location"]
    check("el objeto está movido antes de confirmar", round(loc[0], 3) == 1.23, str(loc))

    app.command("transform.cancel")
    loc = app.command("scene.get_object", {"name": "Cube"})["result"]["location"]
    check("cancelar deshace el movimiento", abs(loc[0]) < 1e-6, str(loc))

    print("\n[13] Opciones de la barra: snap, orientación y valor absoluto")
    # La barra manda snap_type y value_mode en cada begin, y los vuelve a leer de la
    # respuesta para pintarse. Si el servidor no los devolviera, la interfaz se
    # quedaría enseñando lo que el usuario eligió y no lo que de verdad está activo.
    app.command("object.select", {"name": "Cube", "mode": "SET", "active": True})
    session = app.command("transform.begin", {
        "mode": "MOVE", "axes": ["X"], "snap": True, "snap_type": "INCREMENT",
        "step": 0.25, "orientation": "GLOBAL", "value_mode": "RELATIVE",
    })["result"]
    check("la sesión devuelve snap_type", session.get("snap_type") == "INCREMENT", str(session))
    check("la sesión devuelve value_mode", session.get("value_mode") == "RELATIVE", str(session))
    check("la sesión devuelve orientation", session.get("orientation") == "GLOBAL", str(session))

    # Cambiar el tipo de snap en vivo: es el botón que cicla en la barra.
    changed = app.command("transform.snap", {"snap": False, "snap_type": "NONE", "step": 0.25})["result"]
    check("se puede quitar el snap sin cerrar la sesión", changed.get("snap_type") == "NONE", str(changed))
    app.command("transform.cancel")

    # Absoluto: el número tecleado es el destino, no el desplazamiento.
    app.command("transform.begin", {
        "mode": "MOVE", "axes": ["X"], "snap": False, "snap_type": "NONE",
        "step": 0.01, "orientation": "GLOBAL", "value_mode": "ABSOLUTE",
    })
    app.command("transform.value", {"values": [2.0, 0.0, 0.0]})
    app.command("transform.confirm")
    loc = app.command("scene.get_object", {"name": "Cube"})["result"]["location"]
    check("el valor absoluto lleva el objeto a la coordenada", round(loc[0], 3) == 2.0, str(loc))
    app.command("history.undo")

    print("\n[14] Herramientas paramétricas: preview, ajuste y cancelación")
    app.command("object.select", {"name": "Cube", "mode": "SET", "active": True})
    app.command("mode.edit")
    app.command("selection.set_mode", {"selection_mode": "FACE"})
    # Una sola cara, no la malla entera: extruir todas las caras de un sólido cerrado
    # solo desplaza la cáscara y deja el mismo número de vértices, así que no serviría
    # para comprobar que el preview hace algo.
    app.command("selection.elements", {"faces": [0]})
    verts_before = app.command("mesh.info")["result"]["verts"]

    begun = app.command("tool.begin", {"tool": "EXTRUDE", "parameters": {"offset": 0.0}})
    check("tool.begin abre la sesión", (begun.get("result") or {}).get("active") is True, str(begun))
    status = app.command("tool.parameter", {"parameters": {"offset": 0.5}})["result"]
    check("tool.parameter devuelve los parámetros", status.get("parameters", {}).get("offset") == 0.5, str(status))
    # El arrastre del dedo empuja el parámetro primario; el cliente acumula y manda
    # uno cada vez que el anterior contesta, no 30 por segundo.
    nudged = app.command("tool.nudge", {"delta": 0.25})["result"]
    check("tool.nudge mueve el parámetro primario",
          round(nudged.get("parameters", {}).get("offset", 0), 3) == 0.75, str(nudged))
    check("el preview ya cambió la malla",
          app.command("mesh.info")["result"]["verts"] > verts_before)

    app.command("tool.cancel")
    check("cancelar restaura la topología exacta",
          app.command("mesh.info")["result"]["verts"] == verts_before,
          str(app.command("mesh.info")["result"]["verts"]))

    app.command("selection.elements", {"faces": [0]})
    app.command("tool.begin", {"tool": "INSET", "parameters": {"thickness": 0.1, "depth": 0.0}})
    app.command("tool.confirm")
    check("confirmar deja la geometría nueva",
          app.command("mesh.info")["result"]["verts"] > verts_before)
    app.command("history.undo")

    print("\n[15] Menú radial en Edit: selección contextual")
    app.command("selection.set_mode", {"selection_mode": "EDGE"})
    app.command("selection.all", {"value": False})
    # Loop y Ring parten de una arista ya seleccionada: sin ella el cliente ni las
    # ofrece, y el servidor lo confirma con 'empty_selection'.
    reply = app.command("selection.loop")
    check("loop sin arista responde empty_selection", reply.get("code") == "empty_selection", str(reply))

    # Ojo: 'mode' aquí es la operación (SET/ADD/...), no el submodo de selección.
    app.command("selection.elements", {"edges": [0]})
    looped = app.command("selection.loop")
    check("selection.loop amplía la selección", looped.get("ok"), str(looped))
    ringed = app.command("selection.ring")
    check("selection.ring amplía la selección", ringed.get("ok"), str(ringed))
    check("selection.invert responde", app.command("selection.invert").get("ok"))
    check("selection.hide responde", app.command("selection.hide").get("ok"))
    check("selection.reveal responde", app.command("selection.reveal").get("ok"))
    app.command("mode.object")

    print("\n[16] Footer de vistas: la proyección que se enseña es la real")
    for axis in ("FRONT", "BACK", "LEFT", "RIGHT", "TOP", "BOTTOM"):
        if not check(f"view.axis {axis}", app.command("view.axis", {"axis": axis}).get("ok")):
            break
    ortho = app.command("view.perspective", {"mode": "ORTHO"})["result"]
    check("view.perspective pasa a ORTHO de verdad", ortho.get("perspective") == "ORTHO", str(ortho))
    # El footer lee la proyección del estado, no de lo que pulsó el usuario.
    view = app.command("scene.get_state")["result"].get("view", {})
    check("el estado refleja la proyección", view.get("perspective") == "ORTHO", str(view))
    app.command("view.perspective", {"mode": "PERSP"})

    print("\n[17] Modificadores, hide, apply y loop cut")
    app.command("mode.object")
    app.command("object.select", {"names": ["Cube"]})
    catalog = (app.command("modifier.add_options").get("result") or {}).get("types", {})
    for kind in ("SUBSURF", "ARRAY", "BEVEL", "SOLIDIFY", "BOOLEAN"):
        check(f"add_options incluye {kind}", kind in catalog, str(catalog))
    added = app.command("modifier.add", {"type": "SUBSURF"})
    check("modifier.add SUBSURF", added.get("ok"), str(added))
    mods = (added.get("result") or {}).get("modifiers") or []
    check("la pila vuelve en el result", any(m.get("type") == "SUBSURF" for m in mods), str(mods))
    if mods:
        app.command("modifier.remove", {"name": mods[0]["name"]})
    info = app.command("scene.get_object", {"name": "Cube"}).get("result") or {}
    check("object_info trae visible", "visible" in info, str(info))
    check("object_info trae modifiers", "modifiers" in info, str(info))
    check("object.hide", app.command("object.hide").get("ok"))
    check("oculto en el estado", app.command("scene.get_object", {"name": "Cube"})["result"]["visible"] is False)
    check("object.reveal", app.command("object.reveal").get("ok"))
    fail_reply = app.command("transform.apply", {})
    check("apply sin flags es bad_payload", fail_reply.get("code") == "bad_payload", str(fail_reply))
    app.command("transform.scale", {"factor": 2.0})
    check("transform.apply scale", app.command("transform.apply", {"scale": True}).get("ok"))
    app.command("mode.edit")
    app.command("selection.set_mode", {"selection_mode": "EDGE"})
    app.command("selection.elements", {"edges": [0]})
    tools = (app.command("scene.get_context").get("result") or {}).get("available_tools") or []
    check("LOOP_CUT está en available_tools", "LOOP_CUT" in tools, str(tools))
    begun = app.command("tool.begin", {"tool": "LOOP_CUT", "parameters": {"cuts": 1}})
    check("tool.begin LOOP_CUT", (begun.get("result") or {}).get("active") is True, str(begun))
    app.command("tool.cancel")
    # Opciones del modal Ctrl+R: la tablet las manda como parámetros tipados.
    begun = app.command("tool.begin", {"tool": "LOOP_CUT", "edge": 0, "parameters": {
        "cuts": 2, "factor": 0.3, "falloff": "SPHERE", "even": True, "flip": False, "clamp": False}})
    check("tool.begin LOOP_CUT con falloff/even/flip/clamp", (begun.get("result") or {}).get("active") is True, str(begun))
    echoed = (begun.get("result") or {}).get("parameters") or {}
    check("los parámetros viajan tal cual",
          echoed.get("falloff") == "SPHERE" and echoed.get("even") is True and echoed.get("clamp") is False,
          str(echoed))
    nudged = app.command("tool.nudge", {"delta": 0.2})
    factor = (nudged.get("result") or {}).get("parameters", {}).get("factor")
    check("sin clamp el factor puede pasar de 1", isinstance(factor, (int, float)) and factor > 0.3, str(nudged))
    app.command("tool.cancel")
    bad = app.command("tool.begin", {"tool": "LOOP_CUT", "edge": 0, "parameters": {"falloff": "NOPE"}})
    check("falloff inválido es bad_payload", bad.get("code") == "bad_payload", str(bad))
    bad = app.command("tool.begin", {"tool": "LOOP_CUT", "edge": 0, "parameters": {"factor": 1.5}})
    check("factor >1 con clamp es bad_payload", bad.get("code") == "bad_payload", str(bad))
    no_pick = app.command("tool.loop_pick", {"u": 0.5, "v": 0.5})
    check("tool.loop_pick sin sesión es no_session", no_pick.get("code") == "no_session", str(no_pick))
    probe = app.command("mesh.loop_probe", {"u": 0.5, "v": 0.5})
    check("mesh.loop_probe responde ok o no_viewport controlado",
          probe.get("ok") or probe.get("code") == "no_viewport", str(probe))
    app.command("mode.object")

    reply = app.command("modifier.add", {"type": "SUBSURF", "name": "Tablet Subsurf"})
    check("modifier.add devuelve identidad real", bool((reply.get("result") or {}).get("modifier")), str(reply))
    name = (reply.get("result") or {}).get("modifier")
    reply = app.command("modifier.set", {"name": name, "parameters": {"levels": 2}})
    check("modifier.set devuelve pila", any(
        item.get("name") == name and item.get("parameters", {}).get("levels") == 2
        for item in (reply.get("result") or {}).get("modifiers", [])
    ), str(reply))
    check("modifier.remove", app.command("modifier.remove", {"name": name}).get("ok"))
    reply = app.command("object.hide", {"objects": ["Cube"]})
    check("object.hide devuelve estado resultante", "hidden_objects" in (reply.get("result") or {}), str(reply))
    reply = app.command("object.reveal", {"objects": ["Cube"], "select": True})
    check("object.reveal devuelve estado resultante", "selected_objects" in (reply.get("result") or {}), str(reply))

    print("\n[12] Eventos que refrescan la UI")
    app.command("object.select_all", {"value": True})
    events = ws.drain_events(0.8)
    kinds = {e["event"] for e in events}
    check("llega selection.changed", "selection.changed" in kinds, str(kinds))
    payloads_ok = all("payload" in e for e in events)
    check("los eventos traen payload", payloads_ok, str(events[:1]))

    print("\n[18] Selección por forma en Object Mode y grow/shrink en Edit")
    # box/circle proyectan centros de objetos: en background no hay viewport, así
    # que aquí solo se comprueba que el error es el controlado. La selección real
    # la prueba la suite GUI.
    box_reply = app.command("selection.box", {"u0": 0.0, "v0": 0.0, "u1": 1.0, "v1": 1.0, "mode": "ADD"})
    check("selection.box responde ok o no_viewport controlado",
          box_reply.get("ok") or box_reply.get("code") in ("no_viewport", "wrong_mode"), str(box_reply))
    app.command("mode.edit")
    app.command("selection.set_mode", {"selection_mode": "FACE"})
    app.command("selection.all", {"value": False})
    app.command("selection.elements", {"faces": [0]})
    grown = app.command("selection.more")
    check("selection.more responde ok", grown.get("ok"), str(grown))
    faces_after_more = len((grown.get("result") or {}).get("faces", []))
    check("more añadió caras adyacentes", faces_after_more > 1, str(grown.get("result")))
    shrunk = app.command("selection.less")
    faces_after_less = len((shrunk.get("result") or {}).get("faces", []))
    check("less retiró caras fronterizas", faces_after_less < faces_after_more, str(shrunk.get("result")))
    app.command("mode.object")
    more_object = app.command("selection.more")
    check("more fuera de Edit es wrong_mode", more_object.get("code") == "wrong_mode", str(more_object))

    print("\n[19] Aislamiento (view.local) y shading anunciado")
    caps = app.command("server.capabilities")
    features = (caps.get("result") or {}).get("features", {})
    check("capabilities anuncia view.shading", "shading" in features.get("view", {}), str(features.get("view")))
    check("capabilities anuncia view.local_view", features.get("view", {}).get("local_view") is True)
    check("capabilities anuncia selection.grow", features.get("selection", {}).get("grow") is True)
    app.command("object.select", {"names": ["Cube"]})
    local_on = app.command("view.local", {"enabled": True})
    check("view.local activa", (local_on.get("result") or {}).get("local") is True, str(local_on))
    hidden = (local_on.get("result") or {}).get("hidden", [])
    check("ocultó algo distinto del cubo", all(name != "Cube" for name in hidden) and len(hidden) > 0, str(hidden))
    local_off = app.command("view.local", {"enabled": False})
    check("view.local restaura", (local_off.get("result") or {}).get("local") is False, str(local_off))
    state_reply = app.command("scene.get_state").get("result", {})
    check("el estado lleva shading", state_reply.get("shading") in ("WIREFRAME", "SOLID"), str(state_reply.get("shading")))

    ws.close()

    passed = sum(1 for _n, ok, _d in results if ok)
    failed = [(n, d) for n, ok, d in results if not ok]
    print("\n" + "=" * 60)
    print(f"CONTRATO ANDROID: {passed} PASS, {len(failed)} FAIL de {len(results)}")
    for name, detail in failed:
        print(f"  FAIL {name}: {detail}")
    print("=" * 60)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
