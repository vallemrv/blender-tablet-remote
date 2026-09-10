"""Restore committed tablet workspaces after transport loss, never live previews."""
import copy
import re
import bpy
from . import command
from ..errors import BadPayload
from ..camera import camera

_clients = {}
_saved = {}


def clear():
    _clients.clear()
    _saved.clear()


def disconnected(owner):
    key = _clients.pop(owner, None)
    if key is None: return
    from ..cad.runtime import runtime as cad
    from ..materials.runtime import runtime as material
    saved = dict(scene=bpy.context.scene.as_pointer(), view=camera.as_dict())
    if cad.workspace and cad.workspace_owner == owner:
        saved.update(mode='CAD', document=cad.doc()['id'], active=cad.active_sketch_id,
                     body=cad.active_body_id, step=cad.step, increment=cad.increment,
                     construction=cad.construction, show_scene=cad.show_scene,
                     selection=copy.deepcopy(cad.selection) if not cad.session else None)
    elif material.active and material.owner == owner:
        saved.update(mode='MATERIAL', settings={k:copy.deepcopy(getattr(material,k)) for k in
            ('targets','preset','tint','finish','erase','radius','strength','environment')})
    else:
        # Native Object/Edit/Sculpt modes already survive socket loss.
        saved['mode'] = 'NATIVE'
    _saved[key] = saved
    while len(_saved) > 16: _saved.pop(next(iter(_saved)))


@command('server.resume')
def resume(payload):
    key = payload.get('session_key')
    if not isinstance(key,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{24,80}',key):
        raise BadPayload('session_key requiere un identificador privado de 24–80 caracteres')
    owner=payload.get('_client_id')
    from ..cad.runtime import runtime as cad
    from ..materials.runtime import runtime as material
    # A replacement socket can finish its handshake before the dead socket closes.
    for old,old_key in list(_clients.items()):
        if old_key == key and old != owner:
            disconnected(old)
            if cad.workspace_owner == old: cad.leave()
            if material.owner == old: material.leave()
    _clients[owner]=key
    saved=_saved.pop(key,None)
    restored=False
    if saved and saved['scene']==bpy.context.scene.as_pointer() and not cad.workspace and not material.active:
        if saved['mode']=='CAD' and cad.doc()['id']==saved['document'] and bpy.context.mode=='OBJECT':
            cad.workspace=True; cad.workspace_owner=owner
            cad.active_sketch_id=saved['active']; cad.active_body_id=saved['body']
            cad.selection=saved['selection']; cad.step=saved['step']; cad.increment=saved['increment']
            cad.construction=saved['construction']; cad.show_scene=saved['show_scene']
            cad.isolate(); restored=True
        elif saved['mode']=='MATERIAL' and all(n in bpy.data.objects and bpy.data.objects[n].type=='MESH' and bpy.data.objects[n].mode=='OBJECT' for n in saved['settings']['targets']):
            for k,v in saved['settings'].items(): setattr(material,k,v)
            material.active=True; material.owner=owner; material.frame=None; restored=True
        if restored:
            view=saved['view']
            camera.apply(location=view.get('location'),rotation=view.get('rotation'),distance=view.get('distance'),perspective=view.get('perspective'))
    from .. import state
    return dict(state.snapshot(),restored=restored)
