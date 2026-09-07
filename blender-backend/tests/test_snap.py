"""Regresiones: blender --background --factory-startup --python-exit-code 1 --python este_archivo.
GPU real: blender --factory-startup --python este_archivo -- --gpu (cierra su propia ventana).
"""
import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import snap, modal
from blender_tablet_remote.camera import camera
from blender_tablet_remote.streaming.markers import transform_markers, draw_transform_markers


class SnapTests(unittest.TestCase):
    def setUp(self):
        modal.session.reset()
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        camera.reset()
        camera._synced = True
        camera.location = Vector((0, 0, 0))
        camera.rotation = Quaternion((1, 0, 0, 0))
        camera.distance = 10
        camera.perspective = 'PERSP'
        self.rv3d = SimpleNamespace(window_matrix=Matrix(((1,0,0,0),(0,2,0,0),(0,0,-1,-.02),(0,0,-1,0))))
        self.region = SimpleNamespace(width=1000, height=500)
        self.patches = [patch.object(snap, 'find_view3d', return_value=(None,None,self.region,self.rv3d)),
                        patch.object(modal, 'require_rv3d', return_value=self.rv3d)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        modal.session.restore_safely()
        modal.session.reset()
        for p in self.patches:
            p.stop()

    def mesh(self, name, verts, edges=(), faces=()):
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(verts, edges, faces)
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.collection.objects.link(obj)
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.context.view_layer.update()
        return obj

    def test_release_cannot_acquire_a_distant_new_point(self):
        old = dict(id='old', distance=.12)
        new = dict(id='new', distance=.10)
        self.assertEqual(snap.choose_sticky_candidate([old,new],old,.08)['id'], 'old')
        self.assertIsNone(snap.choose_sticky_candidate([new],old,.08))

    def test_jitter_retains_identity_and_clear_approach_switches(self):
        old = dict(id='old', distance=.04)
        near = dict(id='near', distance=.035)
        self.assertEqual(snap.choose_sticky_candidate([old,near],old,.055)['id'],'old')
        near['distance'] = .01
        self.assertEqual(snap.choose_sticky_candidate([old,near],old,.055)['id'],'near')

    def test_face_center_can_replace_a_retained_vertex(self):
        self.mesh('face', [(-1,-1,0),(1,-1,0),(1,1,0),(-1,1,0)], faces=[(0,1,2,3)])
        previous = snap.query_reference_candidate({'u':.55,'v':.4})
        self.assertEqual(previous['snap_type'], 'VERTEX')
        result = snap.query_reference_candidate({'u':.5,'v':.5},previous)
        self.assertEqual(result['snap_type'], 'FACE_CENTER')

    def test_silhouette_and_wire_are_acquired_without_surface_hit(self):
        self.mesh('wire', [(0,0,0),(1,0,0)], edges=[(0,1)])
        result = snap.query_candidate({'u':.555,'v':.5,'snap_type':'VERTEX','threshold':.01})
        self.assertTrue(result['hit'])
        self.assertEqual(result['element'],1)

    def test_horizontal_and_vertical_pixel_radii_are_equal(self):
        self.mesh('point', [(0,0,0)])
        h = snap.query_candidate({'u':.54,'v':.5,'threshold':.045})
        v = snap.query_candidate({'u':.5,'v':.58,'threshold':.045})
        self.assertTrue(h['hit'] and v['hit'])
        self.assertAlmostEqual(h['distance'],v['distance'],places=6)

    def test_occluder_blocks_and_explicit_exclusion_allows_target(self):
        self.mesh('point', [(0,0,0)])
        self.mesh('wall', [(-2,-2,1),(2,-2,1),(2,2,1),(-2,2,1)],faces=[(0,1,2,3)])
        payload = dict(u=.5,v=.5,include_objects=['point'])
        self.assertFalse(snap.query_candidate(payload)['hit'])
        self.assertTrue(snap.query_candidate(dict(payload,exclude_objects=['wall']))['hit'])

    def test_backside_of_open_face_remains_available(self):
        self.mesh('backside', [(-1,-1,0),(1,-1,0),(1,1,0),(-1,1,0)],faces=[(3,2,1,0)])
        self.assertTrue(snap.query_candidate(dict(u=.5,v=.5,snap_type='FACE_CENTER'))['hit'])

    def test_edge_point_projects_to_touch_in_perspective(self):
        obj = self.mesh('edge', [(-1,0,6),(2,0,-2)], edges=[(0,1)])
        a,b = [camera.project(v.co,self.rv3d) for v in obj.data.vertices]
        u = (a[0]+b[0])/2
        result = snap.query_candidate(dict(u=u,v=.5,snap_type='EDGE'))
        self.assertTrue(result['hit'])
        projected = camera.project(result['position'],self.rv3d)
        self.assertAlmostEqual(projected[0],u,places=6)

    def test_edit_exclusions_and_hidden_vertices(self):
        obj = self.mesh('edit',[(0,0,0),(1,0,0)])
        bpy.ops.object.mode_set(mode='EDIT')
        result = snap.query_candidate(dict(u=.5,v=.5,exclude_elements={'edit':{'vertices':[0,1]}}))
        self.assertFalse(result['hit'])
        import bmesh
        bm = bmesh.from_edit_mesh(obj.data)
        for v in bm.verts:
            v.hide = True
        self.assertFalse(snap.query_candidate(dict(u=.5,v=.5))['hit'])
        bpy.ops.object.mode_set(mode='OBJECT')

    def test_center_source_and_target_survive_camera_changes(self):
        self.mesh('object',[(0,0,0),(1,0,0)])
        session = modal.session
        session.begin('ROTATE',['Z'],False,None)
        session.center_position = Vector((0,0,0))
        session.source_position = Vector((1,0,0))
        session.reference_locked = True
        session.reference_role = 'SOURCE'
        session.values = Vector((0,0,math.pi/2))
        session.snap = True
        session.snap_candidate = dict(position=[0,2,0],screen=[.5,.3],snap_type='VERTEX')
        status = session.status()
        markers = dict(transform_markers(status))
        self.assertEqual(set(markers),{'CENTER','SOURCE','TARGET'})
        self.assertLess((Vector(markers['SOURCE'])-Vector((0,1,0))).length,1e-5)
        before = camera.project(markers['SOURCE'],self.rv3d)
        camera.rotation = Quaternion((0,1,0),.4)
        camera._invalidate()
        after = camera.project(markers['SOURCE'],self.rv3d)
        self.assertNotEqual(before,after)
        self.assertEqual(dict(transform_markers(session.status())),markers)

    def test_behind_camera_has_no_stale_screen_position(self):
        self.mesh('object',[(0,0,0)])
        modal.session.begin('ROTATE',['Z'],False,None)
        modal.session.snap_candidate = dict(position=[0,0,20],screen=[.5,.5])
        self.assertEqual(modal.session.status()['snap_candidate']['screen'],[])

    def test_release_locks_the_preview_without_querying_again(self):
        self.mesh('object',[(0,0,0),(1,0,0)])
        session = modal.session
        session.begin('ROTATE',['Z'],False,None)
        candidate = dict(position=[1,0,0],screen=[.55,.5],snap_type='VERTEX',id='object:VERTEX:1')
        session.reference_candidate = candidate
        session.reference_candidate_role = 'SOURCE'
        with patch.object(snap,'query_reference_candidate',side_effect=AssertionError('release queried')):
            modal.set_reference_candidate(dict(u=.9,v=.9,lock=True,role='SOURCE'))
        self.assertEqual(list(session.source_position),[1,0,0])

    def test_pivot_preset_preserves_the_source_marker(self):
        self.mesh('object',[(0,0,0),(1,0,0)])
        session = modal.session
        session.begin('SCALE',[],False,None)
        session.source_position = Vector((1,0,0))
        session.reference_locked = True
        session.reference_role = 'SOURCE'
        for preset in ('OBJECT_ORIGIN','CURSOR','SELECTION'):
            status = modal.set_reference_candidate(dict(role='CENTER',preset=preset))
            self.assertEqual(list(session.source_position),[1,0,0])
            self.assertEqual(set(dict(transform_markers(status))),{'CENTER','SOURCE'})

    @unittest.skipUnless('--gpu' in sys.argv, 'requires a GPU window')
    def test_gpu_markers_are_rendered_and_reprojected_in_frame(self):
        import gpu
        self.mesh('object',[(0,0,0),(1,0,0)])
        modal.session.begin('ROTATE',['Z'],False,None)
        modal.session.center_position = Vector((0,0,0))
        modal.session.source_position = Vector((1,0,0))
        offscreen = gpu.types.GPUOffScreen(1000,500)
        try:
            with offscreen.bind():
                fb = gpu.state.active_framebuffer_get()
                for location in [(0,0,0),(.5,.25,0)]:
                    camera.location = Vector(location)
                    camera._invalidate()
                    fb.clear(color=(0,0,0,1))
                    draw_transform_markers(self.rv3d,1000,500)
                    pixels = bytes(fb.read_color(0,0,1000,500,4,0,'UBYTE'))
                    u,v = camera.project(Vector((0,0,0)),self.rv3d)
                    x,y = round(u*1000),round((1-v)*500)
                    red = sum(pixels[(py*1000+px)*4] > 100
                              for py in range(y-8,y+9) for px in range(x-8,x+9))
                    self.assertGreater(red,10)
        finally:
            offscreen.free()

    @unittest.skipUnless('--gpu' in sys.argv, 'requires a GPU window')
    def test_complete_capture_contains_all_three_markers(self):
        from blender_tablet_remote.streaming.capture import ViewportCapture
        from blender_tablet_remote.streaming.frames import FrameBuffer
        from blender_tablet_remote.bpy_utils import find_view3d
        bpy.ops.mesh.primitive_cube_add()
        modal.session.begin('ROTATE',['Z'],False,None)
        modal.session.center_position = Vector((0,0,1))
        modal.session.source_position = Vector((1,0,1))
        modal.session.snap = True
        modal.session.snap_candidate = dict(position=[-1,0,1],screen=[],snap_type='VERTEX')
        capture = ViewportCapture(FrameBuffer())
        capture.encoder = SimpleNamespace(ensure=lambda *a: True, submit=lambda frame: frames.append(frame), stop=lambda: None)
        frames = []
        try:
            self.assertTrue(capture._grab_offscreen())
            width,height = capture._offscreen_size
            self.assertEqual(len(frames[0]),width*height*4)
            rv3d = find_view3d()[3]
            for kind,position in transform_markers(modal.session.status()):
                u,v = camera.project(position,rv3d)
                x,y = round(u*width),round((1-v)*height)
                colors = [frames[0][(py*width+px)*4:(py*width+px)*4+3]
                          for py in range(max(0,y-18),min(height,y+19))
                          for px in range(max(0,x-18),min(width,x+19))]
                if kind == 'CENTER':
                    count = sum(r>180 and r>g*1.5 and r>b*1.5 for r,g,b in colors)
                elif kind == 'SOURCE':
                    count = sum(r>180 and g>120 and b<120 for r,g,b in colors)
                else:
                    count = sum(b>180 and g>120 and r<160 for r,g,b in colors)
                self.assertGreater(count,5,kind)
        finally:
            capture.shutdown()


def run():
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SnapTests))
    if not result.wasSuccessful():
        raise RuntimeError('Snap regression tests failed')
    if '--gpu' in sys.argv:
        bpy.ops.wm.quit_blender()


if '--gpu' in sys.argv:
    bpy.app.timers.register(run, first_interval=1.0)
else:
    run()
