"""CAD solid selection, face sketch, references and 2D/3D transitions."""
import copy
import math
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import bpy
from mathutils import Vector, Euler
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_cad import CadTests, OWNER, volume
from blender_tablet_remote.cad import document as model, sketch as geometry
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.cad.surface import measurements, segment_distance
from blender_tablet_remote.commands import cad, snap, view
from blender_tablet_remote.camera import camera
from blender_tablet_remote.bpy_utils import find_view3d
from blender_tablet_remote.errors import CommandError


class SurfaceTests(CadTests):
    def pick(self, kind, position):
        cad.surface_mode(dict(mode=kind,**OWNER))
        screen=camera.project(Vector(position),find_view3d()[3])
        self.assertIsNotNone(screen)
        return cad.surface_select(dict(u=screen[0],v=screen[1],**OWNER))

    def test_history_keeps_chronological_sources_and_newest_unused_sketch(self):
        first=runtime.active_sketch_id; f=self.extrude(self.rect())
        cad.sketch_create(dict(plane='XZ',**OWNER)); second=runtime.active_sketch_id
        self.assertEqual([n['id'] for n in model.public(runtime.doc())['history']],[first,f,second])
        before=copy.deepcopy(runtime.doc()); cad.sketch_activate(dict(sketch_id=first,**OWNER)); cad.sketch_finish(OWNER)
        self.assertEqual(runtime.doc(),before)
        cad.sketch_create(dict(plane='YZ',**OWNER))
        self.assertEqual(model.public(runtime.doc())['history'][-1]['id'],runtime.active_sketch_id)

    def test_used_sketch_hides_automatically_but_explicit_visibility_persists(self):
        self.extrude(self.rect()); identifier=runtime.doc()['sketches'][0]['id']
        self.assertFalse(model.public(runtime.doc())['sketches'][0]['visible'])
        cad.sketch_visibility(dict(sketch_id=identifier,visible=True,**OWNER))
        doc=model.loads(model.dumps(runtime.doc()))
        self.assertTrue(model.public(doc)['sketches'][0]['visible'])

    def test_new_sketch_finish_selects_its_profile_even_when_a_parent_solid_exists(self):
        f=self.extrude(self.rect()); cad.sketch_create(dict(support_id=f,**OWNER))
        circle=self.draw('CIRCLE',(.02,.02),(.025,.02))
        state=cad.sketch_finish(OWNER)
        self.assertEqual(state['selection']['kind'],'PROFILE')
        self.assertEqual(state['selection']['id'],'profile_'+circle)
        self.assertIsNone(runtime.active_sketch_id)

    def test_measurements_use_scene_units_and_measure_only_announced_quantities(self):
        def edge(a,b): return dict(kind='EDGE',segments=[[a,b]],points=[a,b],triangles=[],planar=False)
        a=edge((0,0,0),(10,0,0)); b=edge((0,3,0),(10,3,0))
        result={m['label']:m['value'] for m in measurements([a,b],.001)}
        self.assertAlmostEqual(result['Longitud 1'],.01)
        self.assertAlmostEqual(result['Distancia entre aristas'],.003)
        self.assertAlmostEqual(result['Ángulo entre aristas'],0)
        self.assertAlmostEqual(segment_distance(Vector((0,0,0)),Vector((1,0,0)),Vector((.5,-1,1)),Vector((.5,1,1))),1.)

    @unittest.skipIf(bpy.app.background,'GPU viewport required')
    def test_finish_restores_3d_orbit_and_never_writes_pc_view(self):
        found=find_view3d(); rv3d=found[3]
        pc=(tuple(rv3d.view_rotation),tuple(rv3d.view_location),rv3d.view_distance,rv3d.view_perspective)
        self.extrude(self.rect()); identifier=runtime.doc()['sketches'][0]['id']
        camera.apply(rotation=Euler((.8,.3,.4)).to_quaternion(),perspective='PERSP')
        expected=camera.rotation.copy()
        cad.sketch_activate(dict(sketch_id=identifier,**OWNER))
        self.assertEqual(camera.perspective,'ORTHO')
        cad.sketch_finish(OWNER)
        self.assertLess(camera.rotation.rotation_difference(expected).angle,1e-5)
        self.assertEqual(camera.perspective,'PERSP')
        before=camera.rotation.copy(); view.orbit_delta(.1,.1)
        self.assertGreater(camera.rotation.rotation_difference(before).angle,.1)
        self.assertEqual(pc,(tuple(rv3d.view_rotation),tuple(rv3d.view_location),rv3d.view_distance,rv3d.view_perspective))

    @unittest.skipIf(bpy.app.background,'GPU viewport required')
    def test_face_preview_is_visible_complete_and_creates_associative_top_sketch_once(self):
        f=self.extrude(self.rect()); before=model.dumps(runtime.doc())
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            state=self.pick('FACE',(.04,.0225,.02)); undo.assert_not_called()
        self.assertEqual(model.dumps(runtime.doc()),before)
        surface=state['surface']; self.assertTrue(surface['can_sketch'])
        self.assertEqual(surface['selection'][0]['feature_id'],f)
        area=next(m['value'] for m in surface['measurements'] if m['label']=='Área')
        self.assertAlmostEqual(area,.08*.045,places=8)
        self.assertEqual(len(runtime.surface.items[0]['segments']),4)
        with patch.object(snap,'query_cad_surface',side_effect=AssertionError('confirm raycast')),patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            cad.sketch_on_face(OWNER); undo.assert_called_once()
        doc=runtime.doc(); plane=doc['planes'][0]
        self.assertEqual(plane['support_id'],f)
        self.assertAlmostEqual(model.frame(doc['sketches'][-1])['origin'][2],.02)
        cad.feature_set(dict(feature_id=f,depth=.03,**OWNER))
        self.assertAlmostEqual(model.frame(runtime.doc()['sketches'][-1])['origin'][2],.03)

    @unittest.skipIf(bpy.app.background,'GPU viewport required')
    def test_edge_selection_and_projection_create_fixed_reference_for_dimensions(self):
        self.extrude(self.rect())
        state=self.pick('EDGE',(.04,0,.02))
        self.assertEqual(state['surface']['selection'][0]['kind'],'EDGE')
        self.assertAlmostEqual(state['surface']['measurements'][0]['value'],.08,places=7)
        cad.surface_clear(OWNER); self.pick('FACE',(.04,.0225,.02)); cad.sketch_on_face(OWNER)
        self.pick('EDGE',(.04,0,.02))
        cad.project_reference(OWNER)
        sketch=runtime.doc()['sketches'][-1]; reference=sketch['entities'][0]
        self.assertTrue(reference['construction']); self.assertTrue(reference['reference'])
        self.assertEqual(sketch['constraints'][0]['type'],'FIX')
        self.assertFalse(model.profiles(sketch))
        self.assertAlmostEqual(math.dist(*geometry.line(sketch,dict(id=reference['id'],part='BODY'))),.08,places=7)
        original=copy.deepcopy(reference)
        geometry.solve(sketch,geometry.move_goals(sketch,[dict(id=reference['id'],part='START')],.01,.01),drag=True)
        for field in model.FIELDS['LINE']: self.assertAlmostEqual(sketch['entities'][0][field],original[field],places=7)

    @unittest.skipIf(bpy.app.background,'GPU viewport required')
    def test_selection_is_invalidated_by_geometry_edit_before_face_confirmation(self):
        f=self.extrude(self.rect()); self.pick('FACE',(.04,.0225,.02))
        cad.feature_set(dict(feature_id=f,depth=.03,**OWNER))
        baseline=model.dumps(runtime.doc())
        with self.assertRaises(CommandError): cad.sketch_on_face(OWNER)
        self.assertEqual(model.dumps(runtime.doc()),baseline)

    @unittest.skipIf(bpy.app.background,'GPU viewport required')
    def test_coplanar_quad_grid_is_one_selected_face_and_hole_is_preserved(self):
        outer=self.rect(); self.draw('CIRCLE',(.02,.02),(.025,.02)); self.extrude(outer)
        state=self.pick('FACE',(.06,.03,.02))
        area=next(m['value'] for m in state['surface']['measurements'] if m['label']=='Área')
        self.assertAlmostEqual(area,.08*.045-math.pi*.005**2,delta=4e-8)
        item=runtime.surface.items[0]
        self.assertGreater(len(item['triangles']),10)
        # The internal cap grid must not appear as selectable coplanar edges.
        graph=snap._cad_mesh(self.obj())
        for a,b in graph[6]:
            pa,pb=graph[1][a],graph[1][b]
            if abs(pa.z-.02)<1e-6 and abs(pb.z-.02)<1e-6:
                center=(pa+pb)*.5
                outer_edge=min(abs(center.x),abs(center.x-.08),abs(center.y),abs(center.y-.045))<1e-6
                inner_edge=abs(math.hypot(center.x-.02,center.y-.02)-.005)<1e-5
                self.assertTrue(outer_edge or inner_edge,tuple(center))


    @unittest.skipIf(bpy.app.background,'GPU viewport required')
    def test_selected_face_is_painted_in_gpu_video_and_clean_capture_excludes_it(self):
        import tempfile
        import numpy as np
        from blender_tablet_remote.streaming.capture import ViewportCapture
        from blender_tablet_remote.streaming.frames import FrameBuffer
        from blender_tablet_remote.streaming.png import encode_png
        import gpu
        self.extrude(self.rect())
        capture=ViewportCapture(FrameBuffer()); capture.max_width=800
        frames=[]
        try:
            with patch.object(capture.encoder,'ensure',return_value=True),patch.object(capture.encoder,'submit',side_effect=frames.append):
                capture._grab_offscreen(); capture._grab_offscreen()
                before=frames[-1]
                self.pick('FACE',(.04,.0225,.02))
                saved=(gpu.state.blend_get(),gpu.state.depth_test_get(),gpu.state.depth_mask_get())
                capture._grab_offscreen()
                self.assertEqual((gpu.state.blend_get(),gpu.state.depth_test_get(),gpu.state.depth_mask_get()),saved)
                after=frames[-1]
                changed=np.any(np.frombuffer(before,dtype=np.uint8).reshape(-1,4)[:,:3]!=np.frombuffer(after,dtype=np.uint8).reshape(-1,4)[:,:3],axis=1)
                self.assertGreater(np.count_nonzero(changed),100)
                with patch('blender_tablet_remote.streaming.capture.draw_cad_selection',side_effect=AssertionError('marker in clean capture')):
                    self.assertTrue(capture._grab_offscreen(clean=True)[0].startswith(b'\x89PNG'))
                out=Path(tempfile.mkdtemp(prefix='cad-face-preview-'))
                width,height=capture._offscreen_size
                (out/'selected.png').write_bytes(encode_png(after,width,height))
                print('CAD FACE PREVIEW '+str(out/'selected.png'),flush=True)
        finally: capture.shutdown()


def run():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SurfaceTests))
    if not result.wasSuccessful():
        import os
        os._exit(1)
    if not bpy.app.background: bpy.ops.wm.quit_blender()

if __name__=='__main__':
    if bpy.app.background: run()
    else: bpy.app.timers.register(run,first_interval=1.)
