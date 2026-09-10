"""Regressions for tablet feedback: constraints, planes, bodies and mesh export."""
import copy
import math
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import bpy
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_cad import CadTests, OWNER, volume
from blender_tablet_remote.cad import document as model, sketch as geometry
from blender_tablet_remote.cad.runtime import runtime, FEATURE_KEY
from blender_tablet_remote.cad.kernel import world
from blender_tablet_remote.commands import cad, mode, reconnect, view
from blender_tablet_remote.camera import camera
from blender_tablet_remote.bpy_utils import find_view3d
from blender_tablet_remote.errors import CommandError


class FeedbackTests(CadTests):
    def refs(self,*refs): cad._set_selection([dict(kind='ENTITY',id=i,part=p) for i,p in refs])
    def rule(self,typ,**values): return cad.constraint_add(dict(type=typ,**values,**OWNER))

    def test_fix_point_leaves_other_end_and_other_figures_free(self):
        a=self.draw('LINE',(0,0),(.04,.01)); b=self.draw('LINE',(.1,0),(.12,0))
        self.refs((a,'START')); self.rule('FIX')
        cad.entity_set(dict(entity_id=a,values={'x2':.06,'y2':.03},**OWNER))
        cad.entity_set(dict(entity_id=b,values={'x':.09},**OWNER))
        sketch,e=model.entity(runtime.doc(),a)
        self.assertEqual((e['x'],e['y']),(0.,0.))
        self.assertAlmostEqual(e['x2'],.06)
        self.assertEqual(sketch['constraints'][0]['points'],{'START':[0.,0.]})

    def test_fix_rectangle_corner_and_edge_only(self):
        e=self.rect(); self.refs((e,'P0')); self.rule('FIX')
        cad.entity_set(dict(entity_id=e,values={'width':.12},**OWNER))
        self.refs((e,'EDGE0')); self.rule('FIX')
        cad.entity_set(dict(entity_id=e,values={'height':.08},**OWNER))
        _,entity=model.entity(runtime.doc(),e)
        self.assertAlmostEqual(entity['width'],.12)
        self.assertAlmostEqual(entity['height'],.08)
        with self.assertRaises(CommandError): cad.entity_set(dict(entity_id=e,values={'width':.15},**OWNER))

    def test_fix_multiple_references_does_not_fix_whole_sketch(self):
        a=self.draw('LINE',(0,0),(.04,0)); b=self.draw('LINE',(.1,0),(.14,0))
        self.refs((a,'START'),(b,'END')); self.rule('FIX')
        self.assertEqual(len(runtime.doc()['sketches'][0]['constraints']),2)
        cad.entity_set(dict(entity_id=a,values={'x2':.06},**OWNER))
        cad.entity_set(dict(entity_id=b,values={'x':.09},**OWNER))

    def test_origin_midpoint_and_symmetry_survive_serialization(self):
        a=self.draw('LINE',(-.02,.01),(.04,.01))
        self.refs(('ORIGIN','POINT'),(a,'BODY')); self.rule('MIDPOINT')
        sketch=runtime.doc()['sketches'][0]
        self.assertLess(np.linalg.norm(geometry.residual(sketch,sketch['constraints'][0],1)),1e-8)
        self.refs((a,'START'),(a,'END'),('ORIGIN','POINT')); self.rule('SYMMETRIC')
        doc=model.loads(model.dumps(runtime.doc()))
        for c in doc['sketches'][0]['constraints']:
            self.assertLess(np.linalg.norm(geometry.residual(doc['sketches'][0],c,1)),1e-8)
        with self.assertRaises(CommandError):
            self.refs(('ORIGIN','POINT')); self.rule('FIX')

    def test_origin_coincidence_keeps_anchor_while_resizing(self):
        a=self.draw('LINE',(.01,.01),(.05,.02))
        self.refs((a,'START'),('ORIGIN','POINT')); self.rule('COINCIDENT')
        cad.entity_set(dict(entity_id=a,values={'x2':.08},**OWNER))
        _,e=model.entity(runtime.doc(),a)
        self.assertAlmostEqual(e['x'],0); self.assertAlmostEqual(e['y'],0)

    def test_construction_is_constrained_but_excluded_from_solid(self):
        outer=self.rect()
        cad.settings(dict(construction=True,**OWNER))
        inner=self.draw('CIRCLE',(.02,.02),(.025,.02))
        self.refs((inner,'BODY')); self.rule('RADIUS',value=.008)
        self.assertEqual(len(model.profiles(runtime.doc()['sketches'][0])),1)
        self.extrude(outer)
        self.assertAlmostEqual(volume(self.obj()),.08*.045*.02,places=10)
        cad.sketch_activate(dict(sketch_id=runtime.doc()['sketches'][0]['id'],**OWNER))
        self.refs((inner,'BODY'))
        cad.entity_construction(dict(construction=False,**OWNER))
        self.assertEqual(len(model.profiles(runtime.doc()['sketches'][0])),2)
        self.assertLess(volume(self.obj()),.08*.045*.02)

    def test_rectangle_fillet_preserves_profile_and_updates_existing_feature(self):
        e=self.rect(); f=self.extrude(e)
        cad.sketch_activate(dict(sketch_id=runtime.doc()['sketches'][0]['id'],**OWNER))
        self.refs((e,'P2')); cad.fillet(dict(radius=.005,**OWNER))
        doc=runtime.doc(); sketch=doc['sketches'][0]
        self.assertEqual(len(sketch['entities']),5)
        self.assertEqual(len(model.profiles(sketch)),1)
        self.assertEqual(doc['features'][0]['id'],f)
        self.assertAlmostEqual(volume(self.obj()),(.08*.045-.005**2*(1-math.pi/4))*.02,delta=2e-9)
        model.loads(model.dumps(doc))

    def test_custom_planes_are_persistent_and_drive_sketches_in_meters(self):
        cad.plane_create(dict(base='XZ',translation=[.01,.02,.03],rotation=[30,20,15],**OWNER))
        plane=runtime.doc()['planes'][0]
        cad.sketch_create(dict(plane_id=plane['id'],**OWNER))
        entity=self.rect(); self.extrude(entity)
        doc=runtime.doc(); sketch=doc['sketches'][-1]
        self.assertTrue(np.allclose(world(sketch,0,0),plane['frame']['origin']))
        obj=next(o for o in runtime.objects(doc) if o[FEATURE_KEY]==doc['features'][-1]['id'])
        self.assertAlmostEqual(volume(obj),.08*.045*.02,places=9)
        cad.plane_set(dict(plane_id=plane['id'],translation=[.03,.04,.05],**OWNER))
        new=runtime.doc()['sketches'][-1]
        self.assertFalse(np.allclose(world(new,0,0),world(sketch,0,0)))
        self.assertEqual(model.loads(model.dumps(runtime.doc()))['planes'],runtime.doc()['planes'])

    def test_plane_dependency_tracks_base_and_rejects_cycles_atomically(self):
        original=runtime.active_sketch_id
        cad.plane_create(dict(reference_sketch_id=original,translation=[0,0,.01],rotation=[0,30,0],**OWNER))
        plane=runtime.doc()['planes'][0]
        cad.sketch_create(dict(plane_id=plane['id'],**OWNER))
        doc=runtime.doc()
        doc['planes'][0]['reference_sketch_id']=doc['sketches'][-1]['id']
        with self.assertRaises(CommandError): model.resolve_supports(doc)
        with self.assertRaises(CommandError): cad.sketch_delete(dict(sketch_id=original,**OWNER))

    def test_bodies_and_sketch_visibility_preserve_other_piece_on_export(self):
        first_sketch=runtime.active_sketch_id
        a=self.extrude(self.rect()); raw=runtime.doc()
        cad.body_create(OWNER)
        body=runtime.active_body_id
        cad.sketch_create(dict(plane='YZ',**OWNER)); b=self.extrude(self.rect())
        doc=runtime.doc()
        self.assertNotEqual(doc['features'][0]['body_id'],doc['features'][1]['body_id'])
        self.assertEqual(doc['features'][1]['body_id'],body)
        cad.sketch_visibility(dict(sketch_id=first_sketch,visible=False,**OWNER))
        before=copy.deepcopy(runtime.doc())
        cad.convert(dict(feature_id=a,**OWNER))
        self.assertEqual(runtime.doc(),before)
        self.assertEqual(len(runtime.objects(runtime.doc())),2)
        self.assertNotIn(FEATURE_KEY,bpy.context.view_layer.objects.active)
        mode.mode_set(dict(mode='CAD',**OWNER))
        cad.sketch_activate(dict(sketch_id=first_sketch,**OWNER))
        self.assertEqual(runtime.active_sketch_id,first_sketch)

    def test_quad_extrusions_keep_manifold_boundaries_and_volume(self):
        self.extrude(self.rect())
        self.assertEqual(len(self.obj().data.polygons),6)
        self.assertTrue(all(len(p.vertices)==4 for p in self.obj().data.polygons))
        cad.sketch_create(dict(plane='XY',**OWNER))
        e=self.draw('CIRCLE',(.2,0),(.22,0)); f=self.extrude(e)
        obj=next(o for o in runtime.objects(runtime.doc()) if o[FEATURE_KEY]==f)
        self.assertTrue(all(len(p.vertices)==4 for p in obj.data.polygons))
        self.assertAlmostEqual(volume(obj),math.pi*.02**2*.02,delta=2e-8)

    def test_holes_and_repeated_pockets_remain_quads_without_exponential_growth(self):
        outer=self.rect(); hole=self.draw('CIRCLE',(.02,.02),(.025,.02))
        feature=self.extrude(outer)
        obj=self.obj()
        self.assertTrue(all(len(p.vertices)==4 for p in obj.data.polygons))
        previous_count=len(obj.data.polygons)
        counts=[previous_count]
        for i in range(3):
            cad.sketch_create(dict(support_id=feature,**OWNER))
            profile=self.draw('RECTANGLE',(.04+i*.009,.01),(.045+i*.009,.02))
            result=cad.extrude_begin(dict(profile_id='profile_'+profile,operation='CUT',target_id=feature,depth=.004,**OWNER))
            feature=result['selection']['id']; cad.confirm(OWNER)
            obj=next(o for o in runtime.objects(runtime.doc()) if o[FEATURE_KEY]==feature)
            self.assertTrue(all(len(p.vertices)==4 for p in obj.data.polygons))
            self.assertGreater(volume(obj),0)
            counts.append(len(obj.data.polygons))
        self.assertLess(len(obj.data.polygons),previous_count*5,counts)

    def test_planar_face_reference_uses_shared_visible_pick_and_rejects_nonplanar(self):
        from blender_tablet_remote.commands import snap
        bpy.ops.mesh.primitive_cube_add(location=(.1,.2,.3))
        obj=bpy.context.object
        hit=dict(object=obj.name,position=[.1,.2,.31],normal=[0,0,1],vertices=[[-.01,-.01,.01],[.01,-.01,.01],[.01,.01,.01],[-.01,.01,.01]])
        with patch.object(snap,'query_face_frame',return_value=hit) as pick:
            cad.plane_create(dict(u=.5,v=.5,**OWNER)); pick.assert_called_once()
        plane=runtime.doc()['planes'][0]
        self.assertTrue(np.allclose(plane['frame']['origin'],hit['position']))
        before=copy.deepcopy(runtime.doc())
        hit['vertices'][-1][-1]+=.01
        with patch.object(snap,'query_face_frame',return_value=hit),self.assertRaises(CommandError): cad.plane_create(dict(u=.5,v=.5,**OWNER))
        self.assertEqual(runtime.doc(),before)

    def test_resume_restores_workspace_sketch_and_camera_without_preview(self):
        reconnect.clear(); key='test-resume-session-key-1234567890'
        reconnect.resume(dict(session_key=key,**OWNER))
        identifier=self.rect(); active=runtime.active_sketch_id
        self.refs((identifier,'P0'))
        camera.distance=2.4
        reconnect.disconnected('test'); runtime.leave()
        state=reconnect.resume(dict(session_key=key,_client_id='replacement'))
        self.assertTrue(state['restored']); self.assertTrue(runtime.workspace)
        self.assertEqual(runtime.active_sketch_id,active)
        self.assertEqual(runtime.workspace_owner,'replacement')
        self.assertEqual(runtime.selection['id'],identifier)
        self.assertAlmostEqual(camera.distance,2.4)
        self.assertIsNone(runtime.session)
        reconnect.clear()

    @unittest.skipIf(bpy.app.background,'GPU viewport required')
    def test_sketch_navigation_locked_and_dimensions_projected(self):
        e=self.draw('LINE',(0,0),(.04,0)); self.refs((e,'BODY')); self.rule('DISTANCE',value=.04)
        runtime.focus(runtime.doc()['sketches'][0]); rotation=camera.rotation.copy()
        view.orbit_delta(.1,.2); view.roll_delta(.3); view.axis({'axis':'FRONT'}); view.perspective({'mode':'PERSP'})
        self.assertEqual(camera.rotation,rotation); self.assertEqual(camera.perspective,'ORTHO')
        overlay=runtime.overlay(runtime.doc())
        self.assertTrue(any(item['id']=='ORIGIN' for item in overlay))
        self.assertTrue(any(item.get('kind')=='DIMENSION' and item.get('label') for item in overlay))
        cad.plane_create(dict(base='XY',translation=[.1,.2,.3],rotation=[25,40,10],**OWNER))
        cad.sketch_create(dict(plane_id=runtime.doc()['planes'][0]['id'],**OWNER))
        sketch=runtime.doc()['sketches'][-1]
        p=(.02,.03); projected=camera.project(world(sketch,*p),find_view3d()[3])
        result=runtime.point(dict(u=projected[0],v=projected[1]),sketch)
        self.assertTrue(np.allclose(p,result,atol=1e-6),(p,result))


def run():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(FeedbackTests))
    if not result.wasSuccessful():
        import os
        os._exit(1)
    if not bpy.app.background: bpy.ops.wm.quit_blender()

if __name__=='__main__':
    if bpy.app.background: run()
    else: bpy.app.timers.register(run,first_interval=1.)
