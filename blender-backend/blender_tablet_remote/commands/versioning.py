"""ValleTrack facade. Native file saves happen on the Blender pump."""
from . import command
from ..versioning.runtime import runtime
from ..errors import BadPayload

@command('versioning.status')
def status(payload):
    if payload.get('refresh') and not runtime.future:return runtime.start('status',payload)
    return runtime.status()

@command('versioning.action')
def action(payload):
    intent=payload.get('action')
    if intent not in ('commit','restore','explore','switch','connect','identity','forget','link','create_remote','push','pull','clone'):
        raise BadPayload('Acción ValleTrack no compatible')
    return runtime.start(intent,payload)
