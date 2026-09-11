"""Window/GPU integration: blender --factory-startup --python this_file.

Runs in an isolated Blender window. Writes evidence under a temporary directory,
prints its path, exits with nonzero status on assertion failure.
"""
import os
import sys
import tempfile
import traceback
import time
from pathlib import Path
import bpy
from mathutils import Euler, Vector
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.materials.runtime import runtime, register_handlers
from blender_tablet_remote.materials import recipes
from blender_tablet_remote.streaming.capture import ViewportCapture
from blender_tablet_remote.streaming.frames import FrameBuffer
from blender_tablet_remote.camera import camera
from blender_tablet_remote.bpy_utils import undo_push, view3d_override
from blender_tablet_remote.commands import material, history

out=Path(tempfile.mkdtemp(prefix='tablet-material-test-'))
capture=ViewportCapture(FrameBuffer())
capture.max_width=800
stage=0


def step():
    global stage
    try:
        if stage==0:
            bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
            bpy.ops.mesh.primitive_cube_add(); obj=bpy.context.object; obj.name='PaintTest'
            bpy.ops.mesh.primitive_uv_sphere_add(location=(3,0,0)); other=bpy.context.object; other.name='Other'
            other.select_set(False);obj.select_set(True);bpy.context.view_layer.objects.active=obj
            undo_push('Material test baseline')
            runtime.enter('test');runtime.preset='wood';runtime.tint='#B87D43';runtime.erase=False;runtime.finish='natural';runtime.apply()
            camera.sync_from_region(next(a.spaces.active.region_3d for a in bpy.context.screen.areas if a.type=='VIEW_3D'))
            camera.rotation=Euler((.35,.45,.12)).to_quaternion();camera.location=Vector((0,0,0));camera.distance=6
            register_handlers()
            space=next(a.spaces.active for a in bpy.context.screen.areas if a.type=='VIEW_3D')
            original=(space.shading.type,space.overlay.show_overlays,space.show_gizmo)
            try:
                with runtime.presentation(space,True):
                    assert not other.hide_get(), 'Materiales debe mostrar las otras piezas'
                    raise ValueError('intentional test failure')
            except ValueError: pass
            assert (space.shading.type,space.overlay.show_overlays,space.show_gizmo)==original
            assert not other.hide_get()
        elif stage in (1,2,3):
            started=time.perf_counter()
            result=capture._grab_offscreen(clean=True)
            print(f'MATERIAL CAPTURE stage={stage} ms={(time.perf_counter()-started)*1000:.1f}',flush=True)
            assert result
            (out/'before.png').write_bytes(result[0])
            assert 0 < float(runtime.frame[0].min()) < 1
            if stage==3:
                matrix=camera.perspective_matrix(next(a.spaces.active.region_3d for a in bpy.context.screen.areas if a.type=='VIEW_3D'))
                assert not runtime.needs_depth(matrix,*runtime.frame[2:]), 'Static view should reuse depth'
                old=bpy.data.objects['PaintTest'].data.vertices[0].co.copy()
                bpy.data.objects['PaintTest'].data.vertices[0].co.x+=.1
                bpy.data.objects['PaintTest'].data.update(); bpy.context.view_layer.update()
                assert runtime.needs_depth(matrix,*runtime.frame[2:]), 'Geometry edit must invalidate depth'
                bpy.data.objects['PaintTest'].data.vertices[0].co=old
                bpy.data.objects['PaintTest'].data.update(); bpy.context.view_layer.update()
        elif stage==4:
            material.settings({'_client_id':'test','preset':'plastic','color':'#2080FF','radius':.14})
            material.stroke({'_client_id':'test','phase':'begin','stroke_id':'one','points':[{'u':.5,'v':.5,'pressure':1}]})
            assert runtime.stroke['changed'], 'No visible texels painted'
            count=np.count_nonzero(runtime.stroke['objects'][0]['pixels'][::4])
            assert count>100, count
            material.stroke({'_client_id':'test','phase':'end','stroke_id':'one'})
        elif stage==5:
            (out/'painted.png').write_bytes(capture._grab_offscreen(clean=True)[0])
            obj=bpy.data.objects['PaintTest']
            assert obj.data.materials[0]['tablet_layers']==1
            assert not bpy.data.objects['Other'].hide_get(), 'Isolation leaked to the PC'
            history.undo({})
        elif stage==6:
            assert bpy.data.objects['PaintTest'].data.materials[0].get('tablet_layers',0)==0, 'Undo did not restore base'
            history.redo({})
        elif stage==7:
            assert bpy.data.objects['PaintTest'].data.materials[0]['tablet_layers']==1
            material.stroke({'_client_id':'test','phase':'begin','stroke_id':'cancel','points':[{'u':.6,'v':.5,'pressure':1}]})
            bpy.ops.wm.save_as_mainfile(filepath=str(out/'paint.blend'))
            assert runtime.stroke is None, 'Save did not discard preview'
            assert bpy.data.objects['PaintTest'].data.materials[0]['tablet_layers']==1
            runtime.leave()
            bpy.ops.wm.open_mainfile(filepath=str(out/'paint.blend'))
        elif stage==8:
            obj=bpy.data.objects['PaintTest']
            mat=obj.data.materials[0]
            assert mat['tablet_layers']==1
            image=bpy.data.images[mat['tablet_top_mask']]
            assert image.packed_file and max(image.pixels[:])>0, 'Saved paint missing'
            assert not bpy.data.objects['Other'].hide_get()
            print('MATERIAL VIEWPORT PASS '+str(out),flush=True)
            capture.shutdown()
            bpy.ops.wm.quit_blender()
            return None
        stage+=1
        return 1.
    except Exception:
        traceback.print_exc()
        print('MATERIAL VIEWPORT FAIL '+str(out),flush=True)
        os._exit(1)

bpy.app.timers.register(step,first_interval=2.,persistent=True)
