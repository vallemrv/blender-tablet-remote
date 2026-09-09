"""Native GUI regression: blender -t 2 --factory-startup --python this_file.

Runs from the same timer context as bridge._pump. Background Blender is deliberately
unsupported by native brush execution and cannot validate these regressions.
"""
import sys
import unittest
from pathlib import Path
import bpy
from mathutils import Vector
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import sculpt, mode, sessions
from blender_tablet_remote.bpy_utils import view3d_override, find_view3d
from blender_tablet_remote.camera import camera
from blender_tablet_remote.errors import CommandError


class SculptTests(unittest.TestCase):
    def test_sculpt_grid_is_temporary_and_preserves_other_overlays(self):
        from blender_tablet_remote.streaming.capture import _sculpt_grid
        overlay = find_view3d()[1].spaces.active.overlay
        keys = ('show_floor', 'show_ortho_grid', 'show_axis_x', 'show_axis_y', 'show_axis_z')
        original = {key: getattr(overlay, key) for key in keys}
        original_overlays = overlay.show_overlays
        expected = dict(zip(keys, (True, True, True, False, False)))
        try:
            overlay.show_overlays = True
            for key, value in expected.items(): setattr(overlay, key, value)
            with self.assertRaisesRegex(RuntimeError, 'draw failed'):
                with _sculpt_grid(find_view3d()[1].spaces.active):
                    self.assertTrue(overlay.show_overlays)
                    self.assertFalse(any(getattr(overlay, key) for key in keys))
                    raise RuntimeError('draw failed')
            self.assertEqual({key: getattr(overlay, key) for key in keys}, expected)
            mode._set_mode('OBJECT')
            with _sculpt_grid(find_view3d()[1].spaces.active):
                self.assertEqual({key: getattr(overlay, key) for key in keys}, expected)
            # An already hidden grid must stay hidden after leaving Sculpt.
            for key in keys: setattr(overlay, key, False)
            mode._set_mode('SCULPT')
            with _sculpt_grid(find_view3d()[1].spaces.active): pass
            mode._set_mode('OBJECT')
            self.assertFalse(any(getattr(overlay, key) for key in keys))
        finally:
            for key, value in original.items(): setattr(overlay, key, value)
            overlay.show_overlays = original_overlays

    def test_multires_solid_surface_levels_strokes_and_history(self):
        import numpy as np
        from unittest.mock import patch
        from blender_tablet_remote import bridge
        from blender_tablet_remote.commands import history, modifiers
        from blender_tablet_remote.streaming.capture import ViewportCapture, _multires_surface
        from blender_tablet_remote.streaming.frames import FrameBuffer
        mode._set_mode('OBJECT')
        with view3d_override():
            bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
            bpy.ops.mesh.primitive_cube_add()
        modifiers.add({'type': 'MULTIRES'})
        for _ in range(2):
            modifiers.set_params({'name': 'Multires', 'parameters': {'subdivide': True}})
        cap = ViewportCapture(FrameBuffer()); cap.max_width = 640
        frames = []; cap.encoder.ensure = lambda *a: True; cap.encoder.submit = frames.append
        space = find_view3d()[1].spaces.active
        old_shading, old_overlays = space.shading.type, space.overlay.show_overlays
        sculpt.register_handlers()

        def capture():
            cap._grab_offscreen()
            return np.frombuffer(frames[-1], dtype=np.uint8).copy()

        def surface():
            usable, point = cap.sculpt_surface(.5, .5, bpy.context.object, self.rv)
            self.assertTrue(usable); self.assertIsNotNone(point)
            return point.z

        def assert_context():
            obj = bpy.context.view_layer.objects.active
            self.assertEqual(obj.mode, 'SCULPT')
            self.assertTrue(obj.select_get())
            self.assertEqual(obj.matrix_world, self.matrix)
            mod = obj.modifiers['Multires']
            self.assertFalse(mod.use_sculpt_base_mesh)
            self.assertEqual((mod.levels, mod.sculpt_levels, mod.render_levels), (0, 3, 1))
            self.assertEqual(self.rv.view_matrix, self.pc)

        try:
            space.shading.type = 'SOLID'; space.overlay.show_overlays = False
            expected = capture()
            mode._set_mode('SCULPT')
            modifiers.set_params({'name': 'Multires', 'parameters': {'levels': 0, 'render_levels': 1}})
            sculpt.settings(dict(brush='DRAW', radius=.12, strength=.7))
            baseline = capture(); baseline_z = surface()
            self.assertLess(np.count_nonzero(expected != baseline), 50)
            self.assertLess(baseline_z, .95)  # The rounded Multires cube, not its flat cage.
            assert_context()
            with patch.object(bridge, '_capture', cap):
                self.send('begin', [self.point()])
                changed = capture()
                self.assertGreater(np.count_nonzero(changed != baseline), 1000)
                self.assertGreater(surface(), baseline_z + .02)
                self.send('update', [self.point(.1)])
                capture(); assert_context()
                self.send('cancel')
                restored = capture()
                self.assertLess(np.count_nonzero(restored != baseline), 50)
                self.send('begin', [self.point()]); capture()
                self.send('update', [self.point(.1)])
                preview = capture()
                self.send('end')
                self.assertLess(np.count_nonzero(capture() != preview), 50)
                history.undo({})
                self.assertLess(np.count_nonzero(capture() != baseline), 50)
                history.redo({})
                self.assertLess(np.count_nonzero(capture() != preview), 50)
                assert_context()
            # A capture exception must not leave base-mesh sculpt enabled.
            with self.assertRaisesRegex(RuntimeError, 'draw failed'):
                with _multires_surface():
                    raise RuntimeError('draw failed')
            assert_context()
        finally:
            sculpt.unregister_handlers(); cap.shutdown()
            space.shading.type, space.overlay.show_overlays = old_shading, old_overlays

    def test_solid_surface_updates_during_stroke_and_after_cancel(self):
        import numpy as np
        from blender_tablet_remote.streaming.capture import ViewportCapture
        from blender_tablet_remote.streaming.frames import FrameBuffer
        cap=ViewportCapture(FrameBuffer());cap.max_width=640
        cap.encoder.ensure=lambda *a: True
        frames=[];cap.encoder.submit=frames.append
        space=find_view3d()[1].spaces.active
        previous=space.shading.type,space.overlay.show_overlays
        sculpt.register_handlers()
        try:
            for face in bpy.context.object.data.polygons: face.use_smooth=True
            bpy.context.object.data.update()
            space.shading.type='SOLID';space.overlay.show_overlays=False
            cap._grab_offscreen();cap._grab_offscreen()
            before=np.frombuffer(frames[-1],dtype=np.uint8).copy()
            p=self.point()
            _,surface=cap.sculpt_surface(p['u'],p['v'],bpy.context.object,self.rv)
            self.send('begin',[p])
            cap._grab_offscreen()
            _,after=cap.sculpt_surface(p['u'],p['v'],bpy.context.object,self.rv)
            self.assertGreater(after.z-surface.z,1e-4)
            self.assertGreater(np.count_nonzero(np.frombuffer(frames[-1],dtype=np.uint8)!=before),1000)
            self.assertEqual(bpy.context.object.mode,'SCULPT')
            self.assertEqual(space.shading.type,'SOLID')
            self.send('cancel');cap._grab_offscreen()
            _,restored=cap.sculpt_surface(p['u'],p['v'],bpy.context.object,self.rv)
            self.assertAlmostEqual(restored.z,surface.z,places=4)
            self.send('begin',[p]);self.send('end')
            from blender_tablet_remote.commands import history
            history.undo({});cap._grab_offscreen()
            _,undone=cap.sculpt_surface(p['u'],p['v'],bpy.context.object,self.rv)
            self.assertAlmostEqual(undone.z,surface.z,places=4)
        finally:
            sculpt.unregister_handlers()
            cap.shutdown()
            space.shading.type,space.overlay.show_overlays=previous

    def test_one_mm_brush_deforms_only_local_patch_and_cancels(self):
        mode._set_mode('OBJECT')
        obj=bpy.context.object
        for vert in obj.data.vertices: vert.co *= .0005
        obj.data.update()
        camera.distance=.0025; camera._invalidate()
        mode._set_mode('SCULPT')
        sculpt.settings(dict(brush='DRAW',radius=.04,strength=.5,
                             symmetry=dict(x=False,y=False,z=False)))
        baseline=[v.co.copy() for v in obj.data.vertices]
        original_projection=self.rv.view_perspective
        try:
            for projection in ('PERSP','ORTHO'):
                with self.subTest(pc_projection=projection):
                    self.rv.view_perspective=projection
                    self.rv.update()
                    camera._invalidate()
                    matrix=bpy.context.object.matrix_world.copy()
                    pc_matrix=self.rv.view_matrix.copy()
                    u,v=camera.project(Vector((0,0,.0005)), self.rv)
                    self.assertTrue(self.send('begin',[dict(u=u,v=v,pressure=1,time=0)])['hit'])
                    displacements=[(vert.co-co).length for vert,co in zip(bpy.context.object.data.vertices,baseline)]
                    self.assertGreater(max(displacements),1e-8)
                    outside=[d for d,co in zip(displacements,baseline) if Vector((co.x,co.y,0)).length>.0002]
                    self.assertLess(max(outside),1e-9)
                    self.assertEqual(bpy.context.object.matrix_world,matrix)
                    self.assertEqual(self.rv.view_matrix,pc_matrix)
                    self.send('cancel')
                    self.assertLess(max((vert.co-co).length for vert,co in zip(bpy.context.object.data.vertices,baseline)),1e-9)
        finally:
            self.rv.view_perspective=original_projection
            self.rv.update()

    def setUp(self):
        sculpt.cancel()
        with view3d_override():
            if bpy.context.view_layer.objects.active and bpy.context.view_layer.objects.active.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='SELECT')
            bpy.ops.object.delete(use_global=False)
            bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24)
        self.obj = bpy.context.view_layer.objects.active
        self.name = self.obj.name
        camera.reset()
        camera.sync_from_region(find_view3d()[3])
        camera.set_axis_view('TOP')
        camera.distance = 5
        camera.location = Vector((0, 0, 0))
        camera._invalidate()
        mode._set_mode('SCULPT')
        sculpt.settings(dict(brush='DRAW', radius=.08, strength=.5, pressure_strength=True,
                             pressure_size=False, symmetry=dict(x=False, y=False, z=False)))
        self.before = [v.co.copy() for v in self.obj.data.vertices]
        self.rv = find_view3d()[3]
        self.pc = self.rv.view_matrix.copy()
        self.matrix = self.obj.matrix_world.copy()

    def tearDown(self):
        sculpt.cancel()

    def point(self, x=0, pressure=1):
        u, v = camera.project(Vector((x, 0, (1-x*x)**.5)), self.rv)
        return dict(u=u, v=v, pressure=pressure, time=0)

    def send(self, phase, points=None, **kwargs):
        return sculpt.stroke(dict(phase=phase, stroke_id='test', _client_id='tablet',
                                  points=points or [], **kwargs))

    def changed(self):
        obj = bpy.context.view_layer.objects.active
        return max((v.co-co).length for v, co in zip(obj.data.vertices, self.before))

    def test_native_preview_pressure_cancel_and_camera(self):
        self.send('begin', [self.point(pressure=.15)])
        low = self.changed()
        self.assertGreater(low, 1e-5)
        self.send('cancel')
        self.assertLess(self.changed(), 1e-6)
        self.send('begin', [self.point(pressure=1)])
        self.assertGreater(self.changed(), low * 2)
        self.assertEqual(self.rv.view_matrix, self.pc)
        self.assertEqual(bpy.context.view_layer.objects.active.matrix_world, self.matrix)
        self.send('cancel')
        self.assertLess(self.changed(), 1e-6)
        self.assertFalse(sculpt.redo_allowed())

    def test_update_replays_one_native_undo_and_end_does_not_sample(self):
        self.send('begin', [self.point()])
        self.send('update', [self.point(.12)])
        self.send('update', [self.point(.24)])
        self.assertFalse(sculpt.status()['symmetry']['x'])
        result = self.send('end', [{'u': 'invalid'}])
        self.assertTrue(result['changed'])
        self.assertGreater(self.changed(), 1e-4)
        with view3d_override():
            bpy.ops.ed.undo()
        self.assertLess(self.changed(), 1e-6)
        with view3d_override():
            bpy.ops.ed.redo()
        self.assertGreater(self.changed(), 1e-4)

    def test_native_miss_keeps_mode_selection_and_previous_stroke(self):
        from unittest.mock import patch
        from blender_tablet_remote.commands import history
        from mathutils import Vector
        sculpt.register_handlers()
        try:
            self.send('begin', [self.point()]); self.send('end')
            committed = [v.co.copy() for v in bpy.context.object.data.vertices]
            # A remote hit can be rejected by native sculpt (e.g. an evaluated
            # Mirror face). Keep the real brush operator and force only its
            # screen coordinates to miss; Blender still returns FINISHED.
            for brush in ('SMOOTH', 'DRAW', 'CLAY', 'GRAB', 'MASK'):
                sculpt.settings(dict(brush=brush))
                with patch.object(sculpt, 'location_3d_to_region_2d', return_value=Vector((-10000, -10000))):
                    self.send('begin', [self.point()])
                    self.send('update', [self.point(.1)])
                    self.send('update', [self.point(.2)])
                    self.send('cancel')
                obj = bpy.context.view_layer.objects.active
                self.assertEqual(obj.name, self.name)
                self.assertTrue(obj.select_get())
                self.assertEqual(obj.mode, 'SCULPT')
                self.assertEqual(obj.matrix_world, self.matrix)
                self.assertLess(max((v.co-co).length for v, co in zip(obj.data.vertices, committed)), 1e-6)
            history.undo({})
            self.assertLess(self.changed(), 1e-6)
            history.redo({})
            self.assertGreater(self.changed(), 1e-4)
            sculpt.settings(dict(brush='DRAW'))
            self.send('begin', [self.point(.2)])
            self.send('update', [self.point(.3)]); self.send('end')
            history.undo({})
            self.assertLess(max((v.co-co).length for v, co in zip(bpy.context.object.data.vertices, committed)), 1e-6)
        finally:
            sculpt.unregister_handlers()

    def test_stale_owner_and_zero_pressure(self):
        self.send('begin', [self.point(pressure=0)])
        self.assertLess(self.changed(), 1e-6)
        result = sculpt.stroke(dict(phase='end', stroke_id='test', _client_id='other'))
        self.assertTrue(result['stale'])
        self.assertIsNotNone(sculpt._stroke)
        self.send('end')
        self.assertFalse(self.send('update', [self.point()])['active'])

    def test_grab_remote_plane_and_cancel(self):
        sculpt.settings(dict(brush='GRAB'))
        self.send('begin', [self.point()])
        self.send('update', [self.point(.2)])
        self.assertGreater(self.changed(), .01)
        obj = bpy.context.view_layer.objects.active
        deltas = [v.co-co for v, co in zip(obj.data.vertices, self.before)]
        self.assertGreater(max(d.x for d in deltas), .02)
        self.assertLess(max(abs(d.z) for d in deltas), .002)
        self.send('cancel')
        self.assertLess(self.changed(), 1e-6)

    def flush_evaluated(self):
        with view3d_override():
            bpy.ops.object.mode_set(mode='OBJECT')
        obj = bpy.context.view_layer.objects.active.evaluated_get(bpy.context.evaluated_depsgraph_get())
        positions = [v.co.copy() for v in obj.data.vertices]
        faces = len(obj.data.polygons)
        with view3d_override():
            bpy.ops.object.mode_set(mode='SCULPT')
        return positions, faces

    def test_multires_native_sculpt_undo(self):
        from blender_tablet_remote.commands import modifiers
        mode._set_mode('OBJECT')
        modifiers.add({'type':'MULTIRES'})
        mode._set_mode('SCULPT')
        result = {'sculpt':sculpt.status()}
        self.assertEqual(result['sculpt']['multires']['total_levels'], 1)
        base, _ = self.flush_evaluated()
        # Mode transitions above change the native grid cache; establish its
        # baseline just as mode.set does for a new sculpt workspace.
        with view3d_override(): bpy.ops.ed.undo_push(message='Multires test baseline')
        self.send('begin', [self.point()])
        self.send('update', [self.point(.1)])
        self.send('cancel')
        restored, _ = self.flush_evaluated()
        self.assertEqual(len(restored), len(base))
        self.assertLess(max((a-b).length for a,b in zip(restored,base)), 1e-6)
        with view3d_override(): bpy.ops.ed.undo_push(message='Multires test baseline')
        self.send('begin', [self.point()])
        self.send('update', [self.point(.1)])
        self.send('end')
        changed, _ = self.flush_evaluated()
        self.assertGreater(max((a-b).length for a,b in zip(changed,base)), 1e-4)
        with self.assertRaises(CommandError):
            sculpt.dyntopo(dict(enabled=True))

    def test_dyntopo_topology_preview_cancel(self):
        sculpt.dyntopo(dict(enabled=True, detail=4))
        base, faces = self.flush_evaluated()
        with view3d_override(): bpy.ops.ed.undo_push(message='Dyntopo test baseline')
        self.send('begin', [self.point()])
        self.send('update', [self.point(.1)])
        self.send('cancel')
        self.assertTrue(bpy.context.view_layer.objects.active.use_dynamic_topology_sculpting)
        restored, restored_faces = self.flush_evaluated()
        self.assertEqual((len(restored), restored_faces), (len(base), faces))
        with view3d_override(): bpy.ops.ed.undo_push(message='Dyntopo test baseline')
        self.send('begin', [self.point()])
        self.send('update', [self.point(.1)])
        self.send('end')
        changed, changed_faces = self.flush_evaluated()
        self.assertNotEqual((len(changed),changed_faces), (len(base),faces))
        with self.assertRaises(CommandError):
            sculpt.multires(dict(action='add'))

    def test_multires_two_commits_undo_redo_and_materials(self):
        from blender_tablet_remote.commands import history
        material = bpy.data.materials.new('Sculpt regression material')
        self.obj.data.materials.append(material)
        sculpt.multires(dict(action='add'))
        base, _ = self.flush_evaluated()
        with view3d_override(): bpy.ops.ed.undo_push(message='Multi committed baseline')
        for x in (0, .25):
            self.send('begin', [self.point(x)])
            self.send('update', [self.point(x+.05)])
            self.send('end')
        final, _ = self.flush_evaluated()
        self.assertGreater(max((a-b).length for a,b in zip(final,base)), 1e-4)
        history.undo({})
        history.undo({})
        restored, _ = self.flush_evaluated()
        self.assertLess(max((a-b).length for a,b in zip(restored,base)), 3e-6)
        history.redo({})
        history.redo({})
        replay, _ = self.flush_evaluated()
        self.assertLess(max((a-b).length for a,b in zip(replay,final)), 3e-6)
        self.assertEqual(bpy.context.view_layer.objects.active.data.materials[0].name, 'Sculpt regression material')
        self.assertFalse(any(m.name.startswith('Sculpt regression material.') for m in bpy.data.materials))
        sculpt.multires(dict(action='level', level=0))
        sculpt.multires(dict(action='level', level=1))
        after_level, _ = self.flush_evaluated()
        self.assertLess(max((a-b).length for a,b in zip(after_level,final)), 3e-6)

    def test_cancel_redo_barrier_preserves_earlier_history(self):
        from blender_tablet_remote.commands import history
        from blender_tablet_remote.bpy_utils import undo_push
        self.send('begin', [self.point()]); self.send('end')
        a = self.changed()
        self.send('begin', [self.point(.2)]); self.send('cancel')
        history.undo({})
        self.assertLess(self.changed(), 1e-6)
        history.redo({})
        self.assertAlmostEqual(self.changed(), a, places=5)
        with self.assertRaises(CommandError): history.redo({})
        with view3d_override():
            bpy.ops.object.mode_set(mode='OBJECT')
        obj = bpy.context.view_layer.objects.active
        obj.location.x = 1
        undo_push('Object change')
        history.undo({}); history.redo({})
        self.assertAlmostEqual(bpy.context.view_layer.objects.active.location.x, 1)

    def test_depth_surface_background_occlusion_and_stale_camera(self):
        from unittest.mock import patch
        from blender_tablet_remote import bridge
        from blender_tablet_remote.streaming.capture import ViewportCapture
        from blender_tablet_remote.streaming.frames import FrameBuffer
        cap = ViewportCapture(FrameBuffer())
        cap.encoder.ensure = lambda *args: True
        cap.encoder.submit = lambda data: None
        try:
            with patch.object(bridge, '_capture', cap):
                cap._grab_offscreen()
                self.assertIsNotNone(sculpt._location(self.obj, self.point(), self.rv))
                self.assertIsNone(sculpt._location(self.obj, dict(u=.99,v=.99), self.rv))
                with view3d_override():
                    bpy.ops.object.mode_set(mode='OBJECT')
                    bpy.ops.mesh.primitive_cube_add(size=.5, location=(0,0,2))
                    occluder = bpy.context.view_layer.objects.active
                    occluder.select_set(False)
                    self.obj.select_set(True)
                    bpy.context.view_layer.objects.active = self.obj
                    bpy.ops.object.mode_set(mode='SCULPT')
                cap._grab_offscreen()
                self.assertIsNone(sculpt._location(self.obj, self.point(), self.rv))
                camera.orbit(.1, 0, 1)
                self.assertFalse(cap.sculpt_surface(.5,.5,self.obj,self.rv)[0])
        finally:
            cap.shutdown()

    def test_z_multires_disconnect_save_cleanup_and_failed_snapshot(self):
        import os
        import tempfile
        from unittest.mock import patch
        sculpt.multires(dict(action='add'))
        self.send('begin', [self.point()])
        baseline = sculpt._stroke['multires_baseline']
        self.assertTrue(os.path.isfile(baseline))
        sculpt.owner_disconnected('tablet')
        self.assertFalse(os.path.exists(baseline))
        self.send('begin', [self.point()])
        baseline = sculpt._stroke['multires_baseline']
        with patch.object(sculpt, '_copy_multires_mesh', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): self.send('end')
        self.assertIsNone(sculpt._stroke)
        self.assertFalse(os.path.exists(baseline))
        sculpt.register_handlers()
        try:
            self.send('begin', [self.point()])
            baseline = sculpt._stroke['multires_baseline']
            with tempfile.TemporaryDirectory() as folder:
                bpy.ops.wm.save_as_mainfile(filepath=os.path.join(folder,'sculpt.blend'))
                sculpt.finish_saved_preview()
                self.assertIsNone(sculpt._stroke)
                self.assertFalse(os.path.exists(baseline))
                self.send('begin', [self.point()])
                baseline = sculpt._stroke['multires_baseline']
                bpy.ops.wm.open_mainfile(filepath=os.path.join(folder,'sculpt.blend'))
                self.assertIsNone(sculpt._stroke)
                self.assertFalse(os.path.exists(baseline))
        finally:
            sculpt.unregister_handlers()

    def test_symmetry_and_multires_shared_data_guard(self):
        sculpt.settings(dict(radius=.04, symmetry=dict(x=True,y=False,z=False)))
        self.send('begin', [self.point(.4)])
        obj = bpy.context.view_layer.objects.active
        deltas = [(v.co-co).length for v,co in zip(obj.data.vertices,self.before)]
        left = max(d for d,co in zip(deltas,self.before) if co.x < -.2)
        right = max(d for d,co in zip(deltas,self.before) if co.x > .2)
        self.assertGreater(left, 1e-4)
        self.assertAlmostEqual(left,right,places=4)
        self.send('cancel')
        sculpt.multires(dict(action='add'))
        other = bpy.context.view_layer.objects.active.copy()
        bpy.context.collection.objects.link(other)
        with self.assertRaises(CommandError): self.send('begin', [self.point()])
        self.assertIsNone(sculpt._stroke)

    def test_pressure_size_and_limit_keeps_last_visual(self):
        sculpt.settings(dict(pressure_size=True, pressure_strength=False, radius=.12))
        self.send('begin', [self.point(pressure=.2)])
        obj = bpy.context.view_layer.objects.active
        small = sum((v.co-co).length > 1e-5 for v,co in zip(obj.data.vertices,self.before))
        self.send('cancel')
        self.send('begin', [self.point(pressure=1)])
        obj = bpy.context.view_layer.objects.active
        large = sum((v.co-co).length > 1e-5 for v,co in zip(obj.data.vertices,self.before))
        self.assertGreater(large, small)
        stable = [v.co.copy() for v in obj.data.vertices]
        # Fill only the retained sample history: the limit must commit the last
        # rendered preview without evaluating an additional point or full replay.
        sculpt._stroke['points'] *= 4096
        result = self.send('update', [self.point(.1)])
        self.assertTrue(result['limit_reached'])
        self.assertFalse(result['active'])
        self.assertIsNone(sculpt._stroke)
        self.assertLess(max((v.co-co).length for v,co in zip(obj.data.vertices,stable)), 1e-6)

    def test_mask_and_all_native_assets(self):
        for brush in sculpt._BRUSHES:
            sculpt.settings(dict(brush=brush))
        sculpt.settings(dict(brush='MASK'))
        self.send('begin', [self.point()])
        self.send('end')
        attr = bpy.context.view_layer.objects.active.data.attributes.get('.sculpt_mask')
        self.assertIsNotNone(attr)
        self.assertGreater(max(v.value for v in attr.data), 0)
        sculpt.mask(dict(action='clear'))
        attr = bpy.context.view_layer.objects.active.data.attributes.get('.sculpt_mask')
        self.assertTrue(attr is None or max(v.value for v in attr.data) == 0)


def run():
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SculptTests))
    sys.stdout.flush();sys.stderr.flush()
    if not result.wasSuccessful():
        import os
        os._exit(1)
    bpy.ops.wm.quit_blender()
    return None

if __name__ == '__main__':
    if bpy.app.background:
        raise RuntimeError('Run sculpt tests with graphical Blender')
    bpy.app.timers.register(run, first_interval=2)
