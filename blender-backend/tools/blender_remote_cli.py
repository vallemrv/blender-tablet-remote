#!/usr/bin/env python3
"""CLI de prueba del backend. Permite validar Blender SIN la app Android.

    python3 blender_remote_cli.py --host 10.0.0.8 --token XXXX

Comandos interactivos:

    state                estado actual
    objects              lista de objetos
    select Cube          seleccionar objeto
    move 1 0 0           mover (delta)
    rotate 0 0 45        rotar (grados, delta)
    scale 2 2 2          escalar (factor)
    edit / object        cambiar de modo
    vertex / edge / face modo de selección
    all / none           seleccionar todo / nada (en Edit Mode)
    extrude 0.5          extruir a lo largo de la normal
    inset 0.2            inset de las caras seleccionadas
    bevel 0.1 2          bevel (offset, segmentos)
    undo / redo
    orbit 0.1 0          orbitar (fracción de pantalla)
    pan 0.1 0
    zoom 1.2
    frame                frame selected
    add cube             añadir primitiva
    hide [unselected]    ocultar selección u objetos no seleccionados
    reveal               revelar todos los objetos ocultos
    apply scale rotation hornear componentes del transform
    loopcut 2 0.25       abrir preview Loop Cut (cortes, factor)
    mod options          mostrar descriptores de modifiers
    mod add ARRAY        añadir modifier
    mod set Array count 3 / mod apply Array
    drag orbit 0.4 0.1   gesto completo begin/update/end (prueba de coalescing)
    raw {"type":...}     enviar JSON tal cual
    watch 5              escuchar eventos 5 segundos
    quit
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from wsclient import WSClient, WSError  # noqa: E402


def _floats(args, count, default=0.0):
    values = [float(a) for a in args[:count]]
    while len(values) < count:
        values.append(default)
    return values


def dispatch(client: WSClient, line: str) -> bool:
    """Devuelve False para salir."""
    parts = line.split()
    if not parts:
        return True
    cmd, args = parts[0].lower(), parts[1:]

    if cmd in {"quit", "exit", "q"}:
        return False

    if cmd == "raw":
        client.send(json.loads(line[3:].strip()))
        _show(client.recv())
        return True

    if cmd == "watch":
        seconds = float(args[0]) if args else 5.0
        print(f"escuchando {seconds}s...")
        for event in client.drain_events(seconds):
            print("  EVENT", event["event"], json.dumps(event.get("payload", {})))
        return True

    if cmd == "drag":
        gesture = args[0] if args else "orbit"
        dx, dy = _floats(args[1:], 2)
        client.gesture(gesture, "begin")
        steps = 20
        for _ in range(steps):
            client.gesture(gesture, "update", dx=dx / steps, dy=dy / steps, factor=1.0)
        client.gesture(gesture, "end", dx=0, dy=0, factor=1.0)
        print(f"  gesto {gesture} enviado en {steps + 2} mensajes (el servidor los agrupa)")
        return True

    mapping = {
        "state": ("scene.get_state", {}),
        "objects": ("scene.list_objects", {}),
        "edit": ("mode.edit", {}),
        "object": ("mode.object", {}),
        "sculpt": ("mode.sculpt", {}),
        "vertex": ("selection.vertex", {}),
        "edge": ("selection.edge", {}),
        "face": ("selection.face", {}),
        "undo": ("history.undo", {}),
        "redo": ("history.redo", {}),
        "frame": ("view.frame_selected", {}),
        "info": ("mesh.info", {}),
        "caps": ("server.capabilities", {}),
    }
    if cmd in mapping:
        name, payload = mapping[cmd]
        _show(client.command(name, payload))
        return True

    if cmd == "select":
        _show(client.command("object.select", {"names": args}))
    elif cmd == "all":
        _show(client.command("selection.all", {"value": True}))
    elif cmd == "none":
        _show(client.command("selection.all", {"value": False}))
    elif cmd == "move":
        x, y, z = _floats(args, 3)
        _show(client.command("transform.move", {"x": x, "y": y, "z": z}))
    elif cmd == "rotate":
        x, y, z = _floats(args, 3)
        _show(client.command("transform.rotate", {"x": x, "y": y, "z": z}))
    elif cmd == "scale":
        x, y, z = _floats(args, 3, default=1.0)
        _show(client.command("transform.scale", {"x": x, "y": y, "z": z}))
    elif cmd == "extrude":
        offset = float(args[0]) if args else 1.0
        _show(client.command("mesh.extrude", {"offset": offset}))
    elif cmd == "inset":
        thickness = float(args[0]) if args else 0.1
        _show(client.command("mesh.inset", {"thickness": thickness}))
    elif cmd == "bevel":
        offset = float(args[0]) if args else 0.1
        segments = int(args[1]) if len(args) > 1 else 1
        _show(client.command("mesh.bevel", {"offset": offset, "segments": segments}))
    elif cmd == "subdivide":
        _show(client.command("mesh.subdivide", {"cuts": int(args[0]) if args else 1}))
    elif cmd == "delete":
        _show(client.command("object.delete", {}))
    elif cmd == "duplicate":
        _show(client.command("object.duplicate", {}))
    elif cmd == "add":
        _show(client.command("object.add", {"primitive": (args[0] if args else "cube").upper()}))
    elif cmd == "orbit":
        dx, dy = _floats(args, 2)
        _show(client.command("view.orbit", {"dx": dx, "dy": dy}))
    elif cmd == "pan":
        dx, dy = _floats(args, 2)
        _show(client.command("view.pan", {"dx": dx, "dy": dy}))
    elif cmd == "zoom":
        _show(client.command("view.zoom", {"factor": float(args[0]) if args else 1.2}))
    elif cmd == "pick":
        u, v = _floats(args, 2, default=0.5)
        _show(client.command("selection.pick", {"u": u, "v": v}))
    elif cmd == "hide":
        payload = {"unselected": True} if args and args[0] in {"unselected", "other"} else {}
        _show(client.command("object.hide", payload))
    elif cmd == "reveal":
        _show(client.command("object.reveal", {}))
    elif cmd == "apply":
        payload = {}
        for token in args or ["scale"]:
            payload[token.lower()] = True
        _show(client.command("transform.apply", payload))
    elif cmd == "loopcut":
        payload = {"cuts": int(args[0]) if args else 1}
        if len(args) > 1:
            payload["factor"] = float(args[1])
        _show(client.command("tool.begin", {"tool": "LOOP_CUT", "parameters": payload}))
    elif cmd == "mod":
        sub = args[0] if args else "list"
        rest = args[1:]
        if sub == "list" or sub == "options":
            _show(client.command("modifier.add_options" if sub == "options" else "scene.get_object", {}))
        elif sub == "add":
            payload = {"type": (rest[0] if rest else "SUBSURF").upper()}
            if len(rest) > 1:
                payload["object"] = rest[1]
            _show(client.command("modifier.add", payload))
        elif sub == "set":
            name = rest[0] if rest else ""
            key = rest[1] if len(rest) > 1 else "levels"
            value = rest[2] if len(rest) > 2 else "2"
            try:
                parsed = float(value) if "." in value else int(value)
            except ValueError:
                parsed = value
            _show(client.command("modifier.set", {"name": name, "parameters": {key: parsed}}))
        elif sub in {"remove", "apply", "toggle"}:
            command = "modifier.toggle" if sub == "toggle" else f"modifier.{sub}"
            _show(client.command(command, {"name": rest[0] if rest else ""}))
        else:
            print("mod add|set|remove|apply|toggle|list|options")
    else:
        print(f"comando desconocido: {cmd} (usa 'help')")
    return True


def _show(reply: dict) -> None:
    if reply.get("ok"):
        result = reply.get("result")
        print("  ok", json.dumps(result, indent=2, ensure_ascii=False) if result else "")
    else:
        print(f"  ERROR [{reply.get('code', '?')}] {reply.get('error')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Cliente de prueba de Blender Tablet Remote")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--token", default="")
    parser.add_argument("-c", "--command", action="append", help="ejecuta y sale (repetible)")
    args = parser.parse_args()

    client = WSClient(args.host, args.port, args.token)
    try:
        hello = client.connect()
    except (OSError, WSError) as exc:
        print(f"No se pudo conectar a ws://{args.host}:{args.port} — {exc}")
        return 1
    print(f"Conectado a {hello.get('server')} sobre Blender {hello.get('blender')}")

    try:
        if args.command:
            for line in args.command:
                print(f"> {line}")
                dispatch(client, line)
            return 0

        print("Escribe 'help' para ver los comandos, 'quit' para salir.")
        while True:
            try:
                line = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if line in {"help", "?"}:
                print(__doc__)
                continue
            try:
                if not dispatch(client, line):
                    break
            except WSError as exc:
                print(f"  fallo de conexión: {exc}")
                break
            except Exception as exc:  # noqa: BLE001
                print(f"  error local: {exc}")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
