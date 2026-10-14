"""Cooperative CAD commands. Only plain snapshots cross the process boundary."""
from ..errors import CommandError


def calculate(request):
    """Only the evaluator process loads OCP; all commands share this dispatcher."""
    operation = request['operation']
    if operation == 'evaluate':
        from . import occt
        occt.load(request.get('occt_path'))
        return occt.evaluator.evaluate(request['doc'], limit=request.get('limit'), scale=request['scale'])
    if operation == 'solve':
        from .sketch import solve
        sketch = request['sketch']
        solve(sketch, request['goals'], drag=True)
        return sketch
    raise ValueError('Unknown CAD calculation')


class Calculation:
    def __init__(self, **request):
        self.request = request

    def run(self):
        # Direct Python callers use exactly the same evaluator, synchronously.
        return calculate(self.request)


def blocking(steps):
    value = None
    error = None
    while True:
        try:
            job = steps.throw(error) if error else steps.send(value)
        except StopIteration as done:
            return done.value
        try:
            value = job.run()
            error = None
        except Exception as exc:
            error = exc


class PendingCommand:
    def __init__(self, steps):
        self.steps = steps
        self.ticket = None
        self.result = None
        self.done = False
        self.checkpoint = None

    def _context(self):
        import bpy
        from .runtime import runtime
        from .document import KEY
        return (runtime._epoch, bpy.context.scene.as_pointer(), bpy.context.scene.get(KEY),
                bpy.context.scene.unit_settings.scale_length)

    def poll(self):
        from .worker import worker
        if self.checkpoint is not None and self.checkpoint != self._context():
            self.cancel()
            raise CommandError('Cálculo CAD cancelado', code='cad_cancelled')
        value = None
        error = None
        if self.ticket is not None:
            try:
                ready, value = worker.poll(self.ticket)
                if not ready:
                    return False
            except Exception as exc:
                error = exc
            self.ticket = None
        try:
            job = self.steps.throw(error) if error else self.steps.send(value)
        except StopIteration as done:
            self.result, self.done = done.value, True
            return True
        try:
            self.checkpoint = self._context()
            self.ticket = worker.submit(job.request)
        except Exception as exc:
            # Resume the generator's rollback/error handling even on launch failure.
            try:
                self.steps.throw(exc)
            finally:
                self.steps.close()
            raise
        return False

    def cancel(self):
        from .worker import worker
        if self.ticket is not None:
            worker.cancel(self.ticket)
        self.steps.close()
        self.done = True
