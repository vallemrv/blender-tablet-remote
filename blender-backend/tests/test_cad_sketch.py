"""Sketch editing and pocket integration, using real Blender meshes."""
import copy
import math
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.cad import document as model, sketch as geometry
from blender_tablet_remote.cad.runtime import runtime, FEATURE_KEY
from blender_tablet_remote.commands import cad
from blender_tablet_remote.errors import CommandError
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_cad import CadTests, OWNER, volume


class SketchTests(CadTests):
    def test_reopen_selected_profile_or_feature_edits_source_without_duplicate_or_navigation_undo(self):
        entity = self.rect()
        sketch_id = runtime.active_sketch_id
        feature = self.extrude(entity)
        baseline = copy.deepcopy(runtime.doc())
        for kind, identifier in [('PROFILE', 'profile_' + entity), ('FEATURE', feature)]:
            cad.select(dict(kind=kind, id=identifier, **OWNER))
            with patch.object(runtime, 'focus') as focus, patch.object(cad, 'undo_push') as command_undo, \
                    patch('blender_tablet_remote.cad.runtime.undo_push') as runtime_undo:
                status = cad.sketch_activate(dict(sketch_id=sketch_id, **OWNER))
                self.assertEqual(status['active_sketch_id'], sketch_id)
                self.assertIsNone(status['selection'])
                focus.assert_called_once()
                self.assertEqual(focus.call_args.args[0]['id'], sketch_id)
                cad.sketch_finish(OWNER)
                command_undo.assert_not_called()
                runtime_undo.assert_not_called()
            self.assertEqual(runtime.doc(), baseline)
        cad.sketch_activate(dict(sketch_id=sketch_id, **OWNER))
        cad.select(dict(kind='ENTITY', id=entity, **OWNER))
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            cad.entity_set(dict(entity_id=entity, values={'width': .1}, **OWNER))
            undo.assert_called_once()
        cad.sketch_finish(OWNER)
        self.assertEqual(len(runtime.doc()['sketches']), 1)
        self.assertEqual(len(runtime.doc()['features']), 1)
        self.assertEqual(self.obj()[FEATURE_KEY], feature)
        self.assertAlmostEqual(volume(self.obj()), .1 * .045 * .02, places=10)

    def select_refs(self,*refs):
        cad._set_selection([dict(kind='ENTITY',id=identifier,part=part) for identifier,part in refs])

    def rule(self,typ,**payload):
        return cad.constraint_add(dict(type=typ,**payload,**OWNER))

    def test_square_is_persistent_equal_sides_constraint(self):
        e=self.draw('SQUARE',(0,0),(.04,.02))
        cad.entity_set(dict(entity_id=e,values={'width':.06},**OWNER))
        sketch,entity=model.entity(runtime.doc(),e)
        self.assertAlmostEqual(entity['height'],.06,places=8)
        self.assertEqual(sketch['constraints'][0]['type'],'EQUAL')

    def test_constraints_propagate_and_conflicts_are_atomic(self):
        a=self.draw('LINE',(0,0),(.04,.01))
        self.select_refs((a,'BODY')); self.rule('HORIZONTAL')
        sketch,e=model.entity(runtime.doc(),a)
        self.assertAlmostEqual(e['y'],e['y2'],places=9)
        self.rule('DISTANCE',value=.05)
        self.rule('FIX')
        raw=bpy.context.scene[model.KEY]
        with self.assertRaises(CommandError): cad.entity_set(dict(entity_id=a,values={'x2':.2},**OWNER))
        self.assertEqual(raw,bpy.context.scene[model.KEY])
        restored=model.loads(raw)
        self.assertEqual(len(restored['sketches'][0]['constraints']),3)

    def test_coincident_point_drag_preserves_join_and_horizontal(self):
        a=self.draw('LINE',(0,0),(.04,0))
        b=self.draw('LINE',(.04,.01),(.04,.04))
        self.select_refs((a,'END'),(b,'START')); self.rule('COINCIDENT')
        self.select_refs((a,'BODY')); self.rule('HORIZONTAL')
        sketch=model.entity(runtime.doc(),a)[0]
        goals=geometry.move_goals(sketch,[dict(id=b,part='START')],.01,.005)
        geometry.solve(sketch,goals)
        pa=geometry.handles(model.find(sketch,'entities',a)); pb=geometry.handles(model.find(sketch,'entities',b))
        self.assertLess(math.dist(pa['END'],pb['START']),1e-8)
        self.assertAlmostEqual(pa['START'][1],pa['END'][1],places=8)

    def test_parallel_perpendicular_equal_and_radius(self):
        a=self.draw('LINE',(0,0),(.04,0))
        b=self.draw('LINE',(.01,.02),(.03,.05))
        self.select_refs((a,'BODY'),(b,'BODY')); self.rule('PARALLEL'); self.rule('EQUAL')
        sketch=runtime.doc()['sketches'][0]
        for c in sketch['constraints']: self.assertLess(max(abs(v) for v in geometry.residual(sketch,c,1)),1e-7)
        c=self.draw('CIRCLE',(.1,.1),(.11,.1))
        self.select_refs((c,'BODY')); self.rule('RADIUS',value=.015)
        self.assertAlmostEqual(model.entity(runtime.doc(),c)[1]['diameter'],.03,places=8)
        self.select_refs((a,'BODY'),(b,'BODY'))
        raw=bpy.context.scene[model.KEY]
        with self.assertRaises(CommandError): self.rule('PERPENDICULAR')
        self.assertEqual(raw,bpy.context.scene[model.KEY])

    def test_fillet_trims_corner_and_chain_extrudes(self):
        ids=[self.draw('LINE',a,b) for a,b in [((0,0),(.08,0)),((.08,0),(.08,.04)),((.08,.04),(0,.04)),((0,.04),(0,0))]]
        self.select_refs((ids[0],'BODY'),(ids[1],'BODY'))
        cad.fillet(dict(radius=.005,**OWNER))
        sketch=runtime.doc()['sketches'][0]
        self.assertEqual(len(sketch['entities']),5)
        self.assertEqual(len(sketch['constraints']),5)
        profiles=model.profiles(sketch)
        self.assertEqual(len(profiles),1)
        cad.extrude_begin(dict(profile_id=profiles[0]['id'],depth=.02,**OWNER)); cad.confirm(OWNER)
        expected=(.08*.04-.005**2*(1-math.pi/4))*.02
        self.assertAlmostEqual(volume(self.obj()),expected,delta=2e-9)
        raw=bpy.context.scene[model.KEY]
        self.assertEqual(model.profiles(model.loads(raw)['sketches'][0]),profiles)

    def test_invalid_fillet_preserves_original(self):
        a=self.draw('LINE',(0,0),(.04,0)); b=self.draw('LINE',(.04,0),(.04,.03))
        self.select_refs((a,'BODY'),(b,'BODY')); raw=bpy.context.scene[model.KEY]
        with self.assertRaises(CommandError): cad.fillet(dict(radius=.1,**OWNER))
        self.assertEqual(raw,bpy.context.scene[model.KEY])

    def test_arc_dimensions_keep_angles_in_degrees(self):
        a=self.draw('ARC',(0,0),(.04,0))
        cad.entity_set(dict(entity_id=a,values={'sweep':180.,'radius':.02},**OWNER))
        arc=model.entity(runtime.doc(),a)[1]
        self.assertAlmostEqual(arc['sweep'],180.)
        self.assertLess(math.dist(model.outline(arc)[-1],(-.02,0)),1e-8)
        self.assertFalse(model.profiles(runtime.doc()['sketches'][0]))

    def test_drag_has_one_undo_and_cancel_restores(self):
        a=self.draw('LINE',(0,0),(.04,0)); raw=bpy.context.scene[model.KEY]
        hit=dict(kind='ENTITY',id=a,part='END')
        with patch.object(cad,'_pick',return_value=hit), patch.object(runtime,'point',return_value=(.04,0)):
            cad.drag_begin(dict(u=.2,v=.2,**OWNER))
        with patch.object(cad,'undo_push') as undo:
            with patch.object(runtime,'point',return_value=(.0414,.0014)):
                cad.drag_update(dict(u=.3,v=.3,**OWNER))
            preview=model.entity(runtime.session['preview'],a)[1]
            self.assertAlmostEqual(preview['x2'],.041,places=8)
            self.assertEqual(raw,bpy.context.scene[model.KEY])
            cad.drag_end(OWNER)
            self.assertEqual(undo.call_count,1)
        with patch.object(cad,'_pick',return_value=hit), patch.object(runtime,'point',return_value=(.041,.001)):
            cad.drag_begin(dict(u=.2,v=.2,**OWNER))
        with patch.object(cad,'undo_push') as undo: cad.drag_end(OWNER); undo.assert_not_called()
        with patch.object(cad,'_pick',return_value=hit), patch.object(runtime,'point',return_value=(.041,.001)):
            cad.drag_begin(dict(u=.2,v=.2,**OWNER))
        baseline=bpy.context.scene[model.KEY]
        with patch.object(runtime,'point',return_value=(.05,.01)): cad.drag_update(dict(u=.4,v=.4,**OWNER))
        cad.cancel(OWNER)
        self.assertEqual(baseline,bpy.context.scene[model.KEY])

    def test_drag_keeps_multiselection_and_owner(self):
        a=self.draw('LINE',(0,0),(.04,0)); b=self.draw('LINE',(0,.02),(.04,.02))
        self.select_refs((a,'BODY'),(b,'BODY'))
        with patch.object(cad,'_pick',return_value=dict(kind='ENTITY',id=a,part='BODY')), patch.object(runtime,'point',return_value=(.02,0)):
            cad.drag_begin(dict(u=.2,v=.2,**OWNER))
        with self.assertRaises(CommandError): cad.drag_end({'_client_id':'other'})
        with patch.object(runtime,'point',return_value=(.023,.005)): cad.drag_update(dict(u=.3,v=.3,**OWNER))
        cad.drag_end(OWNER)
        for identifier in (a,b): self.assertAlmostEqual(model.entity(runtime.doc(),identifier)[1]['x'],.003,places=8)

    def pocket(self):
        base=self.extrude(self.rect())
        cad.sketch_create(dict(support_id=base,**OWNER))
        hole=self.draw('RECTANGLE',(.01,.01),(.03,.025))
        state=cad.extrude_begin(dict(operation='CUT',target_id=base,profile_id='profile_'+hole,depth=.005,**OWNER))
        return base,hole,state['selection']['id']

    def test_cut_depth_is_subtractive_and_cancel_restores(self):
        base,hole,cut=self.pocket()
        original=.08*.045*.02
        def cut_object(): return next(o for o in runtime.objects(runtime.doc()) if o[FEATURE_KEY]==cut)
        self.assertAlmostEqual(volume(cut_object()),original-.02*.015*.005,places=10)
        for delta,expected in ((.08,.007),(-.04,.004),(.02,.005)):
            cad.extrude_update(dict(gesture=delta,baseline_depth=.005,**OWNER))
            self.assertAlmostEqual(runtime.session['depth'],expected,places=8)
            self.assertAlmostEqual(volume(cut_object()),original-.02*.015*expected,places=10)
        self.assertTrue(runtime.status()['session']['transparent'])
        cad.cancel(OWNER)
        self.assertEqual(len(runtime.objects(runtime.doc())),1)
        self.assertAlmostEqual(volume(self.obj()),original,places=10)
        self.assertFalse(self.obj().hide_viewport)
        self.assertFalse(any(o.name.startswith('CAD cutter') for o in bpy.data.objects))

    def test_cut_rebuild_persist_dependency_and_scene_units(self):
        bpy.context.scene.unit_settings.scale_length=.001
        base,hole,cut=self.pocket(); cad.confirm(OWNER)
        raw=bpy.context.scene[model.KEY]; doc=model.loads(raw)
        self.assertEqual(doc['features'][-1]['target_id'],base)
        cutobj=next(o for o in runtime.objects(doc) if o[FEATURE_KEY]==cut)
        self.assertAlmostEqual(volume(cutobj),80*45*20-20*15*5,delta=.03)
        with self.assertRaises(CommandError): cad.feature_delete(dict(feature_id=base,**OWNER))
        self.assertEqual(raw,bpy.context.scene[model.KEY])
        cad.entity_set(dict(entity_id=hole,values={'width':.025},**OWNER))
        self.assertAlmostEqual(volume(cutobj),80*45*20-25*15*5,delta=.03)

    def test_supported_plane_tracks_base_height_and_cut_persists(self):
        base,hole,cut=self.pocket(); cad.confirm(OWNER)
        cad.feature_set(dict(feature_id=base,depth=.03,**OWNER))
        doc=runtime.doc(); sketch,_=model.entity(doc,hole)
        self.assertAlmostEqual(sketch['offset'],.03)
        cutobj=next(o for o in runtime.objects(doc) if o[FEATURE_KEY]==cut)
        self.assertAlmostEqual(volume(cutobj),.08*.045*.03-.02*.015*.005,places=10)

    def test_square_drag_projects_to_constraint_and_keeps_opposite_corner(self):
        identifier=self.draw('SQUARE',(0,0),(.04,.04))
        sketch=runtime.doc()['sketches'][0]
        goals=geometry.move_goals(sketch,[dict(id=identifier,part='P2')],.01,.02)
        geometry.solve(sketch,goals,drag=True)
        e=model.find(sketch,'entities',identifier)
        self.assertAlmostEqual(e['x'],0,places=8); self.assertAlmostEqual(e['y'],0,places=8)
        self.assertAlmostEqual(e['width'],e['height'],places=8)
        self.assertGreater(e['width'],.04)

    def test_multi_corner_drag_translates_rectangle_without_anchoring_selected_points(self):
        identifier=self.rect(); sketch=runtime.doc()['sketches'][0]
        refs=[dict(id=identifier,part=part) for part in ('P0','P2')]
        geometry.solve(sketch,geometry.move_goals(sketch,refs,.01,.005),drag=True)
        e=model.find(sketch,'entities',identifier)
        self.assertAlmostEqual(e['x'],.01,places=8); self.assertAlmostEqual(e['y'],.005,places=8)
        self.assertAlmostEqual(e['width'],.08,places=8); self.assertAlmostEqual(e['height'],.045,places=8)

    def test_locked_drag_is_noop_without_empty_undo(self):
        identifier=self.draw('LINE',(0,0),(.04,0))
        self.select_refs((identifier,'BODY')); self.rule('FIX')
        with patch.object(cad,'_pick',return_value=dict(kind='ENTITY',id=identifier,part='END')), patch.object(runtime,'point',return_value=(.04,0)):
            cad.drag_begin(dict(u=.2,v=.2,**OWNER))
        with patch.object(runtime,'point',return_value=(.05,.01)): cad.drag_update(dict(u=.4,v=.4,**OWNER))
        with patch.object(cad,'undo_push') as undo: cad.drag_end(OWNER); undo.assert_not_called()

    def test_auto_coincidence_uses_last_stable_endpoint(self):
        a=self.draw('LINE',(0,0),(.04,0))
        anchor=dict(entity_id=a,part='END',id=a+':END')
        with patch.object(cad,'_endpoint',return_value=anchor),patch.object(runtime,'point',return_value=(.041,.001)):
            cad.entity_begin(dict(type='LINE',u=.2,v=.2,**OWNER))
        with patch.object(cad,'_endpoint',return_value=None),patch.object(runtime,'point',return_value=(.04,.04)):
            cad.entity_update(dict(u=.4,v=.4,**OWNER))
        with patch.object(runtime,'point',side_effect=AssertionError('release raycast')): cad.confirm(OWNER)
        sketch=runtime.doc()['sketches'][0]
        self.assertEqual(sketch['constraints'][0]['type'],'COINCIDENT')
        self.assertEqual(geometry.handles(sketch['entities'][0])['END'],geometry.handles(sketch['entities'][1])['START'])

    def test_transparency_is_scoped_even_when_render_fails(self):
        self.pocket()
        shading=SimpleNamespace(type='MATERIAL',show_xray=False,xray_alpha=.5)
        with self.assertRaises(RuntimeError):
            with runtime.preview_shading(SimpleNamespace(shading=shading)):
                self.assertTrue(shading.show_xray); self.assertEqual(shading.xray_alpha,.35)
                raise RuntimeError('render failed')
        self.assertEqual((shading.type,shading.show_xray,shading.xray_alpha),('MATERIAL',False,.5))


def run():
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(SketchTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        import os
        os._exit(1)
    if not bpy.app.background: bpy.ops.wm.quit_blender()


if __name__=='__main__':
    if bpy.app.background: run()
    else: bpy.app.timers.register(run,first_interval=1.)
