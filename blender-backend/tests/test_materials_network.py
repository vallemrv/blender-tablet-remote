"""Window + actual WebSocket integration, no external running Blender is used.

blender --factory-startup --python blender-backend/tests/test_materials_network.py
"""
import os
import sys
import threading
import traceback
import tempfile
import base64
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from blender_tablet_remote import bridge
from wsclient import WSClient

out=Path(tempfile.mkdtemp(prefix='tablet-material-network-'))
done=threading.Event()
failed=[]


def requests():
    try:
        with WSClient(port=19865,timeout=45) as client:
            def cmd(name,payload=None):
                reply=client.command(name,payload)
                assert reply.get('ok'),(name,reply)
                return reply.get('result',{})
            caps=cmd('server.capabilities')
            assert caps['features']['materials']['recipe_version']==1
            assert caps['features']['workspace_resume']
            cmd('server.resume',{'session_key':'network-resume-key-1234567890'})
            assert cmd('mode.set',{'mode':'MATERIAL'})['material']['active']
            state=cmd('scene.get_state')
            assert state['mode']=='MATERIAL' and state['material']['targets']==['Cube']
            cmd('material.settings',{'preset':'wood'})
            cmd('material.apply')
            denied=client.request({'type':'gesture','gesture':'move','phase':'begin'})
            assert not denied['ok'] and denied['code']=='wrong_mode'
            before=cmd('scene.capture');assert before['mime']=='image/png'
            (out/'material-before.png').write_bytes(base64.b64decode(before['png_base64']))
            cmd('material.settings',{'preset':'plastic','color':'#FF3010','radius':.08})
            cmd('material.stroke',{'phase':'begin','stroke_id':'network','points':[{'u':.5,'v':.5,'pressure':1}]})
            cmd('material.stroke',{'phase':'update','stroke_id':'network','points':[{'u':.56,'v':.5,'pressure':1}]})
            cmd('material.stroke',{'phase':'end','stroke_id':'network'})
            after=cmd('scene.capture')
            assert before['png_base64']!=after['png_base64']
            (out/'material-painted.png').write_bytes(base64.b64decode(after['png_base64']))
            with WSClient(port=19865,timeout=45) as other:
                denied=other.command('material.apply')
                assert not denied['ok'] and denied['code']=='session_owned'
                denied=other.command('mode.set',{'mode':'OBJECT'})
                assert not denied['ok'] and denied['code']=='session_owned'
            cmd('history.undo');cmd('history.redo')
            for mode in ('OBJECT','EDIT','OBJECT','SCULPT','OBJECT','CAD','OBJECT'):
                cmd('mode.set',{'mode':mode})
                png=cmd('scene.capture')
                assert base64.b64decode(png['png_base64']).startswith(b'\x89PNG\r\n\x1a\n')
                assert png['width']>0 and png['height']>0
                (out/(mode.lower()+'.png')).write_bytes(base64.b64decode(png['png_base64']))
            cmd('object.select',{'name':'Cube'})
            cmd('mode.set',{'mode':'MATERIAL'})
        # Owner disconnect is enqueued ahead of the next client's commands.
        with WSClient(port=19865,timeout=45) as observer:
            reply=observer.command('scene.get_state')
            assert reply['ok'] and not reply['result']['material']['active']
        with WSClient(port=19865,timeout=45) as replacement:
            reply=replacement.command('server.resume',{'session_key':'network-resume-key-1234567890'})
            assert reply['ok'] and reply['result']['restored'] and reply['result']['mode']=='MATERIAL',reply
            assert replacement.command('material.settings',{'preset':'iron','color':'#DD1122'})['ok']
            reply=replacement.command('mode.set',{'mode':'CAD'})
            assert reply['ok'],reply
            sketch=replacement.command('cad.sketch.create',{'plane':'XZ'})['result']['active_sketch_id']
            assert replacement.command('view.orbit',{'dx':.2,'dy':.1})['ok']
            before=replacement.command('view.get')['result']
        with WSClient(port=19865,timeout=45) as restored:
            reply=restored.command('server.resume',{'session_key':'network-resume-key-1234567890'})
            assert reply['ok'] and reply['result']['restored'],reply
            assert reply['result']['cad']['active_sketch_id']==sketch,reply
            after=restored.command('view.get')['result']
            assert after['perspective']==before['perspective']
            for field in ('location','rotation'):
                assert all(abs(a-b)<1e-6 for a,b in zip(after[field],before[field])),(before,after)
            assert abs(after['distance']-before['distance'])<1e-6,(before,after)
            assert restored.command('cad.sketch.finish')['ok']
        print('MATERIAL NETWORK PASS '+str(out),flush=True)
    except Exception:
        failed.append(traceback.format_exc());print(failed[-1],flush=True)
    finally: done.set()


def monitor():
    if not done.is_set():return .2
    bridge.stop()
    if failed:os._exit(1)
    bpy.ops.wm.quit_blender()
    return None


def start():
    bridge.start('127.0.0.1',19865,stream={'enabled':False,'max_width':800})
    threading.Thread(target=requests,daemon=True).start()
    bpy.app.timers.register(monitor,first_interval=.2)
    return None

bpy.app.timers.register(start,first_interval=2.)
