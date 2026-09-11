"""GPU regression: a material-preview glass sphere must reveal its inner object.

blender --factory-startup --python-exit-code 1 --python tests/test_materials_glass.py
"""
import os
import sys
import tempfile
import traceback
from pathlib import Path
import bpy
import numpy as np
from mathutils import Quaternion, Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.materials.runtime import runtime
from blender_tablet_remote.materials import recipes
from blender_tablet_remote.streaming.capture import ViewportCapture
from blender_tablet_remote.streaming.frames import FrameBuffer
from blender_tablet_remote.camera import camera

out=Path(tempfile.mkdtemp(prefix='tablet-glass-test-'))
capture=ViewportCapture(FrameBuffer());capture.max_width=800
stage=0


def pixels(path):
    image=bpy.data.images.load(str(path),check_existing=False)
    data=np.array(image.pixels[:]).reshape(image.size[1],image.size[0],4)
    bpy.data.images.remove(image)
    return data


def step():
    global stage
    try:
        if stage==0:
            bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
            bpy.ops.mesh.primitive_uv_sphere_add(segments=48,ring_count=24,radius=1)
            shell=bpy.context.object;shell.name='GlassShell'
            for p in shell.data.polygons:p.use_smooth=True
            bpy.ops.mesh.primitive_cube_add(size=.65,location=(0,0,0))
            inner=bpy.context.object;inner.name='Interior'
            inner.data.materials.append(recipes.compile_material(recipes.BUILTINS[0],'#FF1500'))
            inner.select_set(False);shell.select_set(True);bpy.context.view_layer.objects.active=shell
            runtime.enter('test');runtime.preset='glass';runtime.tint='#FFF4DA';runtime.apply()
            space=next(a.spaces.active for a in bpy.context.screen.areas if a.type=='VIEW_3D')
            camera.sync_from_region(space.region_3d)
            camera.rotation=Quaternion((1,0,0,0));camera.location=Vector((0,0,0));camera.distance=5
            bpy.context.scene.eevee.use_raytracing=False
        elif stage in (1,2,3):
            result=capture._grab_offscreen(clean=True)
            assert result
            (out/'glass-interior.png').write_bytes(result[0])
            assert not bpy.data.objects['Interior'].hide_get()
            assert not bpy.context.scene.eevee.use_raytracing,'Ray tracing leaked into scene settings'
        elif stage==4:
            bpy.data.objects['Interior'].hide_set(True)
        elif stage in (5,6,7):
            (out/'glass-empty.png').write_bytes(capture._grab_offscreen(clean=True)[0])
        elif stage==8:
            visible=pixels(out/'glass-interior.png');empty=pixels(out/'glass-empty.png')
            h,w=visible.shape[:2]
            delta=np.abs(visible[h//3:2*h//3,w//3:2*w//3,:3]-empty[h//3:2*h//3,w//3:2*w//3,:3])
            assert np.count_nonzero(delta.max(axis=2)>.04)>150, ('Interior not visible',float(delta.max()))
            print('MATERIAL GLASS PASS '+str(out),flush=True)
            capture.shutdown();runtime.leave();bpy.ops.wm.quit_blender();return None
        stage+=1
        return .6
    except Exception:
        traceback.print_exc();print('MATERIAL GLASS FAIL '+str(out),flush=True);os._exit(1)

bpy.app.timers.register(step,first_interval=2.)
