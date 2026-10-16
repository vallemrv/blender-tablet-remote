"""Selected sketch contours form one reversible cut, with persistent source IDs."""
import copy,math,sys,unittest
from pathlib import Path
from unittest.mock import patch
import bpy
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from test_cad import CadTests,OWNER,volume
from blender_tablet_remote.cad import document as model,occt
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.commands import cad
from blender_tablet_remote.errors import CommandError

class SelectedCutTests(CadTests):
    def plate(self):
        base=self.rect();target=self.extrude(base,.006)
        cad.sketch_create(dict(support_id=target,**OWNER));sketch=runtime.active_sketch_id
        holes=[self.draw('CIRCLE',(x,y),(x+.002,y)) for x,y in ((.01,.01),(.07,.01),(.01,.035),(.07,.035))]
        center=self.draw('CIRCLE',(.04,.0225),(.05,.0225))
        inner=self.draw('CIRCLE',(.04,.0225),(.046,.0225))
        return base,target,sketch,holes,center,inner
    def exact_volume(self):
        evaluator=occt.Evaluator();result=evaluator.evaluate(runtime.doc())
        return occt._volume(evaluator._shapes[next(iter(result['tips'].values()))][1])/1e9
    def cut(self,target,sketch,ids,**values):
        return cad.extrude_begin(dict(operation='CUT',sketch_id=sketch,entity_ids=ids,target_id=target,depth=.006,**values,**OWNER))
    def test_four_holes_exclude_central_circles_and_commit_one_undo(self):
        _,target,sketch,holes,_,_=self.plate();before=model.dumps(runtime.doc());baseline=volume(self.obj())
        state=self.cut(target,sketch,holes)
        self.assertTrue(state['session']['can_confirm'])
        self.assertEqual(model.dumps(runtime.doc()),before)
        self.assertIsNone(runtime.active_sketch_id)
        with patch.object(cad,'undo_push') as undo:cad.confirm(OWNER);undo.assert_called_once()
        self.assertAlmostEqual(baseline-volume(self.obj()),4*math.pi*.002**2*.006,delta=3e-10)
        self.assertAlmostEqual(self.exact_volume(),(.08*.045-4*math.pi*.002**2)*.006,delta=1e-12)
        feature=runtime.doc()['features'][-1]
        self.assertEqual(feature['entity_ids'],holes);self.assertEqual(feature['profile_id'],'profile_'+sketch)
        model.loads(model.dumps(runtime.doc()))
    def test_coincident_reference_centers_do_not_hide_drawn_holes(self):
        _,target,sketch,holes,_,_=self.plate()
        cad.select_all(dict(action='DESELECT',**OWNER))
        overlay=[]
        for i,identifier in enumerate(holes):
            center=[.2+i*.15,.5]
            for ref,construction in [('reference_'+identifier,True),(identifier,False)]:
                overlay.append(dict(id=ref,points=[],closed=False,construction=construction,
                                    handles=[dict(part='CENTER',point=center)]))
        with patch.object(runtime,'overlay',return_value=overlay):
            for i,identifier in enumerate(holes):
                cad.select(dict(u=.2+i*.15,v=.5,additive=True,**OWNER))
            self.assertEqual([r['id'] for r in cad._refs()],holes)
            # A nearer reference still wins; this is not a construction filter.
            overlay[0]['handles'][0]['point']=[.2,.51]
            self.assertEqual(cad._pick(dict(u=.2,v=.51))['id'],'reference_'+holes[0])
        self.cut(target,sketch,[r['id'] for r in cad._refs()]);cad.confirm(OWNER)
        self.assertEqual(runtime.doc()['features'][-1]['entity_ids'],holes)

    def test_shown_profiles_accumulate_toggle_and_cut_together_without_editing(self):
        _,target,sketch,holes,center,inner=self.plate();cad.sketch_finish(OWNER)
        cad.sketch_visibility(dict(sketch_id=sketch,visible=True,**OWNER))
        # Hit the shown profiles through the same coordinate command as Android.
        overlay=[dict(id=identifier,points=[[x-.02,.48],[x+.02,.48],[x+.02,.52],[x-.02,.52]],closed=True)
                 for identifier,x in zip(holes,[.2,.4,.6,.8])]
        with patch.object(runtime,'overlay',return_value=overlay):
            for x in [.2,.4,.6,.8]:cad.select(dict(u=x,v=.5,additive=True,**OWNER))
            self.assertIsNone(runtime.active_sketch_id)
            self.assertEqual([r['id'] for r in cad._refs()],['profile_'+i for i in holes])
            cad.select(dict(u=.4,v=.5,additive=True,**OWNER))
            self.assertEqual(len(cad._refs()),3)
            cad.select(dict(u=.4,v=.5,additive=True,**OWNER))
        before=model.dumps(runtime.doc());baseline=volume(self.obj())
        state=cad.extrude_begin(dict(operation='CUT',profile_ids=[r['id'] for r in cad._refs()],target_id=target,depth=.006,**OWNER))
        self.assertTrue(state['session']['can_confirm']);self.assertIsNone(runtime.active_sketch_id)
        self.assertEqual(model.dumps(runtime.doc()),before)
        with patch.object(cad,'undo_push') as undo:cad.confirm(OWNER);undo.assert_called_once()
        self.assertEqual(set(runtime.doc()['features'][-1]['entity_ids']),set(holes))
        self.assertAlmostEqual(baseline-volume(self.obj()),4*math.pi*.002**2*.006,delta=3e-10)
    def test_shown_profile_group_replaces_whole_sketch_or_other_sketch(self):
        _,_,sketch,holes,_,_=self.plate();cad.sketch_finish(OWNER)
        cad.select(dict(kind='SKETCH',id=sketch,**OWNER))
        cad.select(dict(kind='PROFILE',id='profile_'+holes[0],additive=True,**OWNER))
        self.assertEqual([r['id'] for r in cad._refs()],['profile_'+holes[0]])
        cad.sketch_create(dict(plane='XY',**OWNER));other=self.draw('CIRCLE',(.03,.03),(.031,.03));cad.sketch_finish(OWNER)
        cad.select(dict(kind='PROFILE',id='profile_'+holes[0],additive=True,**OWNER))
        cad.select(dict(kind='PROFILE',id='profile_'+other,additive=True,**OWNER))
        self.assertEqual([r['id'] for r in cad._refs()],['profile_'+other])
    def test_selected_profile_list_rejects_empty_duplicates_and_mixed_sketches(self):
        base,target,sketch,holes,_,_=self.plate();cad.sketch_finish(OWNER)
        before=model.dumps(runtime.doc())
        for ids in ([],['profile_'+holes[0]]*2,['profile_'+holes[0],'profile_'+base],['profile_'+sketch]):
            with self.subTest(ids=ids),self.assertRaises(CommandError):
                cad.extrude_begin(dict(operation='CUT',profile_ids=ids,target_id=target,depth=.006,**OWNER))
            self.assertIsNone(runtime.session);self.assertEqual(model.dumps(runtime.doc()),before)
    def test_shown_closed_chain_resolves_its_members(self):
        _,target,sketch,holes,_,_=self.plate()
        points=[(.025,.01),(.035,.01),(.035,.02),(.025,.02)]
        lines=[self.draw('LINE',a,b) for a,b in zip(points,points[1:]+points[:1])]
        source=model.find(runtime.doc(),'sketches',sketch)
        chain=next(e for e in model.closed_entities(source) if set(e.get('members',[]))==set(lines))
        cad.sketch_finish(OWNER)
        cad.extrude_begin(dict(operation='CUT',profile_ids=['profile_'+holes[0],'profile_'+chain['id']],target_id=target,depth=.006,**OWNER))
        cad.confirm(OWNER)
        self.assertEqual(set(runtime.doc()['features'][-1]['entity_ids']),set(lines+[holes[0]]))

    def test_subset_follows_dimensions_and_unused_geometry_is_not_a_cutter(self):
        _,target,sketch,holes,center,_=self.plate();self.cut(target,sketch,holes);cad.confirm(OWNER)
        before=volume(self.obj())
        cad.entity_set(dict(entity_id=center,values={'diameter':.025},**OWNER))
        self.assertAlmostEqual(volume(self.obj()),before,places=11)
        cad.entity_set(dict(entity_id=holes[0],values={'diameter':.006},**OWNER))
        self.assertAlmostEqual(before-volume(self.obj()),math.pi*(.003**2-.002**2)*.006,delta=1e-10)
        cad.entity_delete(dict(entity_id=center,**OWNER))
        before=bpy.context.scene[model.KEY]
        with self.assertRaises(CommandError):cad.entity_delete(dict(entity_id=holes[0],**OWNER))
        self.assertEqual(before,bpy.context.scene[model.KEY])
    def test_cancel_fast_preview_and_through_all_keep_only_the_subset(self):
        _,target,sketch,holes,_,_=self.plate();before=model.dumps(runtime.doc());self.cut(target,sketch,holes)
        session=runtime.session;selected,profile=model.profile(session['preview'],'profile_'+sketch,holes)
        vertices,_=session['extrusion_cache'].extrude(selected,profile,-.003)
        self.assertTrue(vertices)
        self.assertTrue(all(min(math.hypot(p[0]-x,p[1]-y) for x,y in ((.01,.01),(.07,.01),(.01,.035),(.07,.035)))<.00201 for p in vertices))
        cad.cancel(OWNER);self.assertEqual(model.dumps(runtime.doc()),before)
        self.cut(target,sketch,holes,extent='THROUGH_ALL');cad.confirm(OWNER)
        cad.feature_set(dict(feature_id=target,depth=.012,**OWNER))
        self.assertAlmostEqual(volume(self.obj()),(.08*.045-4*math.pi*.002**2)*.012,delta=6e-10)
        self.assertAlmostEqual(self.exact_volume(),(.08*.045-4*math.pi*.002**2)*.012,delta=1e-12)
    def test_one_circle_is_full_disk_even_with_unselected_inner_circle(self):
        _,target,sketch,_,center,_=self.plate();before=volume(self.obj())
        self.cut(target,sketch,[center]);cad.confirm(OWNER)
        self.assertAlmostEqual(before-volume(self.obj()),math.pi*.01**2*.006,delta=2e-9)
    def test_open_unselected_lines_are_ignored_but_empty_or_open_selection_rejected(self):
        _,target,sketch,holes,_,_=self.plate()
        line=self.draw('LINE',(.03,.01),(.05,.01))
        before=model.dumps(runtime.doc())
        for ids in ([],[holes[0],holes[0]],[line],['missing'],[holes[0],line]):
            with self.subTest(selection=ids),self.assertRaises(CommandError):self.cut(target,sketch,ids)
            self.assertIsNone(runtime.session);self.assertEqual(model.dumps(runtime.doc()),before)
        self.cut(target,sketch,holes);cad.cancel(OWNER)
        self.assertEqual(model.dumps(runtime.doc()),before)
    def test_to_face_and_closed_line_chain_use_only_selected_geometry(self):
        _,target,sketch,holes,_,_=self.plate()
        self.cut(target,sketch,holes)
        with patch.object(cad,'_face_target',return_value=dict(origin=[0,0,.003],normal=[0,0,1])):
            cad.extrude_update(dict(extent='TO_FACE',u=.5,v=.5,**OWNER))
        cad.confirm(OWNER)
        self.assertAlmostEqual(self.exact_volume(),.08*.045*.006-4*math.pi*.002**2*.003,delta=1e-12)
        cad.sketch_activate(dict(sketch_id=sketch,**OWNER))
        points=[(.025,.01),(.035,.01),(.035,.02),(.025,.02)]
        lines=[self.draw('LINE',a,b) for a,b in zip(points,points[1:]+points[:1])]
        target=runtime.doc()['features'][-1]['id'];before=self.exact_volume()
        self.cut(target,sketch,lines);cad.confirm(OWNER)
        self.assertAlmostEqual(before-self.exact_volume(),.01*.01*.006,delta=1e-12)

    def test_selection_cannot_erase_an_earlier_full_sketch_cache_dependency(self):
        _,target,sketch,holes,_,_=self.plate();self.cut(target,sketch,holes);cad.confirm(OWNER)
        doc=runtime.doc();feature=doc['features'][-1]
        # Reuse the source of an earlier operation as a subset cut, so both
        # complete and partial consumers occur under the same sketch ID.
        source=doc['sketches'][0];original=source['entities'][0]
        circle=dict(id='later_hole',type='CIRCLE',x=.01,y=.01,diameter=.004,construction=False)
        source['entities'].append(circle)
        feature.update(sketch_id=source['id'],profile_id='profile_'+source['id'],entity_ids=['later_hole'],extent='THROUGH_ALL')
        model.resolve_supports(doc);key=occt.geometry_key(doc,None,1.)
        original['width']+=.01
        self.assertNotEqual(key,occt.geometry_key(doc,None,1.))
    def test_mirror_and_pattern_keep_the_selected_operand(self):
        from blender_tablet_remote.commands import cad_operations
        _,target,sketch,holes,_,_=self.plate();self.cut(target,sketch,[holes[0]]);cad.confirm(OWNER)
        feature=runtime.doc()['features'][-1]['id'];baseline=volume(self.obj())
        cad.feature_mirror(dict(feature_id=feature,plane='YZ',offset=.04,**OWNER))
        self.assertAlmostEqual(baseline-volume(self.obj()),math.pi*.002**2*.006,delta=1e-10)
        self.assertEqual(runtime.doc()['features'][-1]['entity_ids'],[holes[0]])
        cad_operations.pattern_begin(dict(feature_id=feature,count=2,spacing=.02,**OWNER));cad.confirm(OWNER)
        self.assertAlmostEqual(baseline-volume(self.obj()),2*math.pi*.002**2*.006,delta=2e-10)

    @unittest.skipIf(bpy.app.background, 'GUI undo stack required')
    def test_four_holes_have_one_native_undo_and_redo(self):
        from blender_tablet_remote.commands import history
        _,target,sketch,holes,_,_=self.plate();before=model.dumps(runtime.doc());baseline=volume(self.obj())
        self.cut(target,sketch,holes);cad.confirm(OWNER);expected=volume(self.obj())
        history.undo({});self.assertEqual(model.dumps(runtime.doc()),before);self.assertAlmostEqual(volume(self.obj()),baseline,places=10)
        history.redo({});self.assertAlmostEqual(volume(self.obj()),expected,places=10)
        self.assertEqual(runtime.doc()['features'][-1]['entity_ids'],holes)


def run():
    suite=unittest.TestSuite(SelectedCutTests(n) for n in SelectedCutTests.__dict__ if n.startswith('test_'))
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
        import os
        os._exit(1)
    if not bpy.app.background:bpy.ops.wm.quit_blender()

if __name__=='__main__':
    if bpy.app.background:run()
    else:bpy.app.timers.register(run,first_interval=1.)
