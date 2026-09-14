"""blender -b --factory-startup --python-exit-code 1 --python tests/test_cad_usability.py"""
import copy
import math
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import bpy
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_cad import CadTests, OWNER, volume
from blender_tablet_remote.cad import document as model, sketch as geometry
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.commands import cad
from blender_tablet_remote.errors import CommandError


class UsabilityTests(CadTests):
    def refs(self,*items):
        cad._set_selection([dict(kind='ENTITY',id=i,part=p) for i,p in items])

    def test_circle_preview_and_committed_radius_share_one_dimension(self):
        with patch.object(runtime,'point',return_value=(0,0)):
            cad.entity_begin(dict(type='CIRCLE',u=.1,v=.1,**OWNER))
        with patch.object(runtime,'point',return_value=(.03,.04)):
            status=cad.entity_update(dict(u=.5,v=.5,**OWNER))
        circle=status['document']['sketches'][0]['entities'][0]
        self.assertAlmostEqual(circle['radius'],.05)
        self.assertEqual(circle['dimensions'][0]['field'],'radius')
        self.assertEqual(circle['dimensions'][0]['label'],'Radio')
        self.assertTrue(status['session']['active'])
        cad.confirm(OWNER)
        cad.constraint_add(dict(type='RADIUS',value=.05,**OWNER))
        constraint=runtime.doc()['sketches'][0]['constraints'][0]['id']
        cad.entity_set(dict(entity_id=circle['id'],values={'radius':.025},**OWNER))
        doc=runtime.doc(); published=model.public(doc)['sketches'][0]['entities'][0]
        self.assertAlmostEqual(published['radius'],.025)
        self.assertAlmostEqual(published['diameter'],.05)
        self.assertEqual(published['dimensions'][0]['constraint_ids'],[constraint])
        self.assertAlmostEqual(doc['sketches'][0]['constraints'][0]['value'],.025)
        self.assertNotIn('radius',doc['sketches'][0]['entities'][0])

    def test_weld_closes_profile_at_last_point_and_is_one_undo(self):
        a=self.draw('LINE',(0,0),(.04,0))
        self.draw('LINE',(.04,0),(.04,.04))
        self.draw('LINE',(.04,.04),(0,.04))
        b=self.draw('LINE',(0,.04),(0,.005))
        self.assertFalse(model.profiles(runtime.doc()['sketches'][0]))
        self.refs((b,'END'),(a,'START'))
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            cad.points_weld(OWNER); undo.assert_called_once()
        sketch=runtime.doc()['sketches'][0]
        self.assertEqual(len(model.profiles(sketch)),1)
        self.assertLess(math.dist(geometry.point(sketch,dict(id=b,part='END')),(0,0)),1e-9)
        self.assertLess(math.dist(geometry.handles(model.find(sketch,'entities',a))['START'],(0,0)),1e-12)
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            cad.points_weld(OWNER); undo.assert_not_called()
        self.assertEqual(len(runtime.doc()['sketches'][0]['constraints']),1)
        cad.extrude_begin(dict(profile_id=model.profiles(sketch)[0]['id'],depth=.01,**OWNER));cad.confirm(OWNER)
        self.assertAlmostEqual(volume(self.obj()),.04*.04*.01,places=10)

    def test_weld_conflict_keeps_document_and_selection(self):
        a=self.draw('LINE',(0,0),(.04,0)); b=self.draw('LINE',(.05,0),(.05,.04))
        self.refs((a,'END'),(b,'START'))
        cad.constraint_add(dict(type='FIX',**OWNER))
        before=model.dumps(runtime.doc()); selection=copy.deepcopy(runtime.selection)
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            with self.assertRaises(CommandError): cad.points_weld(OWNER)
            undo.assert_not_called()
        self.assertEqual(model.dumps(runtime.doc()),before)
        self.assertEqual(runtime.selection,selection)

    def test_weld_multiple_points_and_origin_remain_associative(self):
        a=self.draw('LINE',(.001,.001),(.04,0)); b=self.draw('LINE',(.002,.001),(0,.04))
        self.refs(('ORIGIN','POINT'),(a,'START'),(b,'START'))
        cad.points_weld(OWNER)
        sketch=runtime.doc()['sketches'][0]
        for i in (a,b): self.assertLess(math.dist(geometry.point(sketch,dict(id=i,part='START')),(0,0)),1e-9)
        self.assertEqual(len(sketch['constraints']),2)
        self.refs((a,'BODY'),(b,'BODY'))
        before=model.dumps(runtime.doc())
        with self.assertRaises(CommandError):cad.points_weld(OWNER)
        self.assertEqual(model.dumps(runtime.doc()),before)

    def arc_begin(self,arc):
        hit=dict(kind='ENTITY',id=arc,part='END',intent='ANGLE')
        end=geometry.handles(model.entity(runtime.doc(),arc)[1])['END']
        with patch.object(cad,'_pick',return_value=hit),patch.object(runtime,'point',return_value=end):
            cad.drag_begin(dict(u=.5,v=.5,**OWNER))

    def arc_update(self,point):
        with patch.object(runtime,'point',return_value=point): return cad.drag_update(dict(u=.5,v=.5,**OWNER))

    def test_angle_handle_preserves_center_radius_start_and_group(self):
        arc=self.draw('ARC',(0,0),(.02,0)); line=self.draw('LINE',(.05,0),(.05,.04))
        self.refs((arc,'BODY'),(line,'BODY'))
        baseline=model.dumps(runtime.doc())
        self.arc_begin(arc)
        self.arc_update((-.02,0)); state=self.arc_update((0,-.04))
        value=next(e for e in state['document']['sketches'][0]['entities'] if e['id']==arc)
        self.assertAlmostEqual(value['sweep'],270.,places=5)
        for field,number in [('x',0.),('y',0.),('radius',.02),('start',0.)]:
            self.assertAlmostEqual(value[field],number,places=8)
        self.assertEqual(model.dumps(runtime.doc()),baseline)
        with patch.object(runtime,'point',side_effect=AssertionError('release raycast')),patch.object(cad,'undo_push') as undo:
            cad.drag_end(OWNER);undo.assert_called_once()
        self.assertAlmostEqual(model.entity(runtime.doc(),line)[1]['x'],.05)
        committed=model.dumps(runtime.doc())
        self.arc_begin(arc);self.arc_update((-.02,0));cad.cancel(OWNER)
        self.assertEqual(model.dumps(runtime.doc()),committed)

    def test_fixed_arc_cannot_be_changed_by_angle_handle(self):
        arc=self.draw('ARC',(0,0),(.02,0));self.refs((arc,'BODY'))
        cad.constraint_add(dict(type='FIX',**OWNER))
        self.arc_begin(arc);self.arc_update((-.02,0))
        with patch.object(cad,'undo_push') as undo:
            cad.drag_end(OWNER);undo.assert_not_called()
        self.assertAlmostEqual(model.entity(runtime.doc(),arc)[1]['sweep'],90.,places=6)

    @unittest.skipIf(bpy.app.background,'GUI viewport required')
    def test_visible_angle_handle_is_picked_and_native_undo_restores_arc(self):
        from blender_tablet_remote.bpy_utils import find_view3d
        from blender_tablet_remote.camera import camera
        from blender_tablet_remote.commands import history
        arc=self.draw('ARC',(0,0),(.02,0))
        runtime.focus(runtime.doc()['sketches'][0])
        overlay=next(item for item in runtime.overlay(runtime.doc()) if item['id']==arc)
        handle=next(h for h in overlay['handles'] if h['intent']=='ANGLE')
        self.assertEqual(handle['part'],'END')
        u,v=handle['point']
        before=find_view3d()[3].view_matrix.copy()
        cad.drag_begin(dict(u=u,v=v,**OWNER))
        self.assertEqual(runtime.session['hit']['intent'],'ANGLE')
        target=camera.project(Vector((-.02,0,0)),find_view3d()[3])
        cad.drag_update(dict(u=target[0],v=target[1],**OWNER));cad.drag_end(OWNER)
        self.assertAlmostEqual(model.entity(runtime.doc(),arc)[1]['sweep'],180.,places=5)
        self.assertEqual(find_view3d()[3].view_matrix,before)
        history.undo({})
        self.assertAlmostEqual(model.entity(runtime.doc(),arc)[1]['sweep'],90.,places=5)


def run():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(UsabilityTests))
    if not result.wasSuccessful():os._exit(1)
    if not bpy.app.background:bpy.ops.wm.quit_blender()


if __name__=='__main__':
    if bpy.app.background:run()
    else:bpy.app.timers.register(run,first_interval=1.)
