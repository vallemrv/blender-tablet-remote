"""One persistent, isolated Blender process; no bpy on a Python worker thread.

Private atomic files carry bounded, serialized requests/results. The pump only
polls completed results and never waits for the subprocess. No scene is opened.
"""
import atexit
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import uuid

from ..errors import CommandError


class Worker:
    def __init__(self):
        self.process = None
        self.directory = None
        self.pending = None
        self.retired = []

    def reap(self):
        alive = []
        for process, directory in self.retired:
            if process.poll() is None:
                alive.append((process, directory))
            else:
                shutil.rmtree(directory, ignore_errors=True)
        self.retired = alive

    def start(self):
        self.reap()
        if self.process is not None and self.process.poll() is None:
            return
        self.stop()
        import bpy
        self.directory = Path(tempfile.mkdtemp(prefix='btr-cad-'))
        try:
            # Leave CPU capacity for video/input; native booleans may use these cores.
            threads = max(1, (os.cpu_count() or 2) - 2)
            with (self.directory / 'worker.log').open('wb') as log:
                self.process = subprocess.Popen([
                    bpy.app.binary_path, '--background', '--factory-startup',
                    '--disable-autoexec', '--threads', str(threads),
                    '--python', str(Path(__file__).with_name('worker_entry.py')),
                    '--', str(self.directory), str(os.getpid()),
                ], stdin=subprocess.DEVNULL, stdout=log, stderr=log)
        except Exception:
            shutil.rmtree(self.directory, ignore_errors=True)
            self.directory = None
            raise CommandError('No se pudo iniciar el cálculo CAD', code='cad_worker_failed')

    def submit(self, request):
        if self.pending is not None:
            raise CommandError('Hay un cálculo CAD pendiente', code='cad_busy')
        self.start()
        identifier = uuid.uuid4().hex
        temporary = self.directory / 'request.tmp'
        temporary.write_text(json.dumps(dict(id=identifier, request=request)), encoding='utf8')
        temporary.replace(self.directory / 'request.json')
        self.pending = (identifier, time.monotonic())
        return identifier

    def poll(self, identifier):
        if self.pending is None or self.pending[0] != identifier:
            raise CommandError('Cálculo CAD cancelado', code='cad_cancelled')
        path = self.directory / 'result.json'
        if path.exists():
            result = json.loads(path.read_text(encoding='utf8'))
            path.unlink()
            self.pending = None
            if result['id'] != identifier:
                raise CommandError('Resultado CAD fuera de sesión', code='cad_cancelled')
            if 'error' in result:
                raise CommandError(result['error'], code=result['code'])
            return True, result['result']
        if self.process.poll() is not None or time.monotonic() - self.pending[1] > 120:
            self.stop()
            raise CommandError('El cálculo CAD no terminó; vuelve a intentarlo', code='cad_worker_failed')
        return False, None

    def cancel(self, identifier):
        if self.pending and self.pending[0] == identifier:
            self.stop()

    def stop(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.kill()
            self.retired.append((self.process, self.directory))
        elif self.directory is not None:
            shutil.rmtree(self.directory, ignore_errors=True)
        self.process = self.directory = self.pending = None
        self.reap()

    def shutdown(self):
        self.stop()
        for process, directory in self.retired:
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                continue
            shutil.rmtree(directory, ignore_errors=True)
        self.retired = []


worker = Worker()
atexit.register(worker.shutdown)
