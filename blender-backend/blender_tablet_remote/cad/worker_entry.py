"""Auxiliary Blender entry point. All native calls run on its main thread."""
import json
import os
from pathlib import Path
import sys
import time
import shutil

import bpy

# Load the installed package under a private name, without starting its server.
import importlib.util
package = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('_btr_cad_worker', package / '__init__.py',
                                             submodule_search_locations=[str(package)])
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
from _btr_cad_worker.cad.evaluation import calculate
from _btr_cad_worker.errors import CommandError

directory, parent = sys.argv[sys.argv.index('--') + 1:]
directory = Path(directory)
parent = int(parent)
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

last_request = time.monotonic()
while directory.exists() and time.monotonic() - last_request < 300:
    # kill(pid, 0) is a liveness probe only on POSIX. Idle expiry also releases
    # workers whose host vanished on platforms without that probe.
    if os.name == 'posix':
        try:
            os.kill(parent, 0)
        except OSError:
            break
    path = directory / 'request.json'
    if not path.exists():
        time.sleep(.01)
        continue
    message = json.loads(path.read_text(encoding='utf8'))
    path.unlink()
    last_request = time.monotonic()
    try:
        result = dict(id=message['id'], result=calculate(message['request']))
    except CommandError as exc:
        result = dict(id=message['id'], error=exc.message, code=exc.code)
    except Exception as exc:
        result = dict(id=message['id'], error=f'Error de cálculo CAD: {exc}', code='cad_worker_failed')
    temporary = directory / 'result.tmp'
    temporary.write_text(json.dumps(result), encoding='utf8')
    temporary.replace(directory / 'result.json')

shutil.rmtree(directory, ignore_errors=True)
