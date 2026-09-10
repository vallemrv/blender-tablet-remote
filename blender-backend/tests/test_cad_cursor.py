"""Smart CAD cursor and selection deletion using real sketches and solid evaluation."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_cad import CadTests, OWNER, volume
from blender_tablet_remote.cad import document as model, sketch as geometry
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.commands import cad
from blender_tablet_remote.errors import CommandError


def ref(identifier,part='BODY'):
    return dict(kind='ENTITY',id=identifier,part=part)


class CursorTests(CadTests):
    def begin(self,hit,point=(.02,.02)):
        with patch.object(cad,'_pick',return_value=hit),patch.object(runtime,'point',return_value=point):
            return cad.drag_begin(dict(u=.3,v=.3,**OWNER))

    def update(self,point):
        with patch.object(runtime,'point',return_value=point): return cad.drag_update(dict(u=.4,v=.4,**OWNER))

    def tap(self,hit):
        before=copy.deepcopy(runtime.selection)
        self.begin(hit)
        self.assertEqual(runtime.selection,before,'DOWN must not change selection')
        with patch.object(cad,'_pick',side_effect=AssertionError('release pick')),patch.object(runtime,'point',side_effect=AssertionError('release raycast')):
            cad.drag_end(OWNER)

    def test_taps_toggle_multiple_elements_without_geometry_or_undo(self):
        a=self.draw('LINE',(0,0),(.04,0)); b=self.draw('LINE',(0,.02),(.04,.02))
        cad._set_selection([]); baseline=model.dumps(runtime.doc())
        with patch.object(cad,'undo_push') as undo:
            self.tap(ref(a,'END')); self.tap(ref(b,'START'))
            self.assertEqual(cad._refs(),[ref(a,'END'),ref(b,'START')])
            self.tap(ref(a,'END'))
            self.assertEqual(cad._refs(),[ref(b,'START')])
            self.tap(ref(b,'START')); self.assertIsNone(runtime.selection)
            undo.assert_not_called()
        self.assertEqual(model.dumps(runtime.doc()),baseline)

    def test_drag_selected_drawing_from_corner_preserves_group_and_size(self):
        a=self.rect(); b=self.draw('LINE',(.1,0),(.14,0))
        cad._set_selection([ref(a),ref(b)])
        self.begin(ref(a,'P0'),(0,0)); self.update((.01,.02))
        with patch.object(cad,'undo_push') as undo: cad.drag_end(OWNER); undo.assert_called_once()
        self.assertEqual(cad._refs(),[ref(a),ref(b)])
        _,rectangle=model.entity(runtime.doc(),a); _,line=model.entity(runtime.doc(),b)
        self.assertAlmostEqual(rectangle['x'],.01); self.assertAlmostEqual(rectangle['y'],.02)
        self.assertAlmostEqual(rectangle['width'],.08); self.assertAlmostEqual(rectangle['height'],.045)
        self.assertAlmostEqual(line['x'],.11); self.assertAlmostEqual(line['y'],.02)

    def test_drag_unselected_replaces_selection_but_tap_adds(self):
        a=self.rect(); b=self.draw('LINE',(.1,0),(.14,0))
        cad._set_selection([ref(a)])
        self.begin(ref(b),(.1,0)); self.update((.11,.01)); cad.drag_end(OWNER)
        self.assertEqual(cad._refs(),[ref(b)])
        _,rectangle=model.entity(runtime.doc(),a)
        self.assertAlmostEqual(rectangle['x'],0); self.assertAlmostEqual(rectangle['y'],0)
        self.tap(ref(a,'P0')); self.assertEqual(cad._refs(),[ref(b),ref(a,'P0')])

    def test_cancel_restores_original_selection_and_geometry(self):
        a=self.rect(); b=self.draw('LINE',(.1,0),(.14,0))
        cad._set_selection([ref(a)]); baseline=model.dumps(runtime.doc())
        self.begin(ref(b),(.1,0)); self.update((.11,.01)); cad.cancel(OWNER)
        self.assertEqual(cad._refs(),[ref(a)]); self.assertEqual(model.dumps(runtime.doc()),baseline)
        self.begin(ref(b)); cad.cancel(OWNER)
        self.assertEqual(cad._refs(),[ref(a)])

    def test_empty_tap_clears_but_empty_drag_or_cancel_preserves(self):
        a=self.rect(); cad._set_selection([ref(a)])
        self.begin(None); self.update((.1,.1)); cad.drag_end(OWNER)
        self.assertEqual(cad._refs(),[ref(a)])
        self.begin(None); cad.cancel(OWNER); self.assertEqual(cad._refs(),[ref(a)])
        self.tap(None); self.assertIsNone(runtime.selection)

    def test_constrained_drag_is_not_misinterpreted_as_toggle(self):
        a=self.rect(); cad._set_selection([ref(a)])
        cad.constraint_add(dict(type='FIX',**OWNER))
        self.begin(ref(a,'P0'),(0,0)); self.update((.01,.02))
        with patch.object(cad,'undo_push') as undo: cad.drag_end(OWNER); undo.assert_not_called()
        self.assertEqual(cad._refs(),[ref(a)])

    def test_tapping_member_of_whole_drawing_deselects_it(self):
        a=self.rect(); cad._set_selection([ref(a)])
        self.tap(ref(a,'P0')); self.assertIsNone(runtime.selection)
        cad.select(dict(kind='ENTITY',id=a,part='P0',additive=True,**OWNER))
        cad.select(dict(kind='ENTITY',id=a,part='BODY',additive=True,**OWNER))
        self.assertEqual(cad._refs(),[ref(a)])

    def test_select_all_includes_construction_and_excludes_origin_without_undo(self):
        a=self.rect(); cad.settings(dict(construction=True,**OWNER))
        b=self.draw('LINE',(.1,0),(.14,0)); baseline=model.dumps(runtime.doc())
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            cad.select_all(dict(action='SELECT',**OWNER))
            self.assertEqual(cad._refs(),[ref(a),ref(b)])
            cad.select_all(dict(action='DESELECT',**OWNER)); self.assertIsNone(runtime.selection)
            undo.assert_not_called()
        self.assertEqual(model.dumps(runtime.doc()),baseline)

    def test_delete_selected_drawings_is_one_undo_and_keeps_unrelated_rules(self):
        a=self.rect(); b=self.draw('CIRCLE',(.1,.1),(.12,.1)); c=self.draw('LINE',(.2,0),(.24,0))
        cad._set_selection([ref(c)]); cad.constraint_add(dict(type='HORIZONTAL',**OWNER))
        cad._set_selection([ref(a),ref(b)])
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo: cad.entity_delete(OWNER); undo.assert_called_once()
        sketch=runtime.doc()['sketches'][0]
        self.assertEqual([e['id'] for e in sketch['entities']],[c]); self.assertEqual(len(sketch['constraints']),1)
        self.assertIsNone(runtime.selection)

    def test_delete_rectangle_edge_keeps_three_sides_and_point_fix(self):
        a=self.rect(); cad._set_selection([ref(a,'P0')]); cad.constraint_add(dict(type='FIX',**OWNER))
        cad._set_selection([ref(a,'EDGE0')]); cad.entity_delete(OWNER)
        sketch=runtime.doc()['sketches'][0]
        self.assertEqual(len(sketch['entities']),3); self.assertFalse(model.profiles(sketch))
        fixed=next(c for c in sketch['constraints'] if c['type']=='FIX')
        self.assertEqual(fixed['points'],{'END':[0.,0.]})
        for c in sketch['constraints']: self.assertLess(max(abs(v) for v in geometry.residual(sketch,c,1)),1e-8)
        model.loads(model.dumps(runtime.doc()))

    def test_delete_rectangle_corner_keeps_opposite_sides(self):
        a=self.rect(); cad._set_selection([ref(a,'P0')]); cad.entity_delete(OWNER)
        lines=runtime.doc()['sketches'][0]['entities']
        self.assertEqual(len(lines),2)
        self.assertEqual([(e['x'],e['y'],e['x2'],e['y2']) for e in lines],[(.08,0.,.08,.045),(.08,.045,0.,.045)])

    def test_delete_endpoint_removes_its_primitive_and_associated_rules(self):
        a=self.draw('LINE',(0,0),(.04,0)); b=self.draw('LINE',(.04,0),(.04,.04))
        cad._set_selection([ref(a,'END'),ref(b,'START')]); cad.constraint_add(dict(type='COINCIDENT',**OWNER))
        cad._set_selection([ref(a,'END')]); cad.entity_delete(OWNER)
        sketch=runtime.doc()['sketches'][0]
        self.assertEqual([e['id'] for e in sketch['entities']],[b]); self.assertFalse(sketch['constraints'])

    def test_delete_origin_is_rejected_and_closed_feature_is_protected(self):
        a=self.rect(); self.extrude(a); baseline=model.dumps(runtime.doc()); previous_volume=volume(self.obj())
        cad.sketch_activate(dict(sketch_id=runtime.doc()['sketches'][0]['id'],**OWNER))
        for selected in (ref('ORIGIN','POINT'),ref(a,'EDGE0')):
            cad._set_selection([selected])
            with self.assertRaises(CommandError): cad.entity_delete(OWNER)
            self.assertEqual(model.dumps(runtime.doc()),baseline)
            self.assertAlmostEqual(volume(self.obj()),previous_volume)
            self.assertEqual(cad._refs(),[selected])

    def test_unused_geometry_can_be_deleted_without_removing_extrusion(self):
        a=self.rect(); self.extrude(a)
        cad.sketch_activate(dict(sketch_id=runtime.doc()['sketches'][0]['id'],**OWNER))
        cad.settings(dict(construction=True,**OWNER)); b=self.draw('LINE',(.1,0),(.14,0))
        cad.entity_delete(dict(entity_id=b,**OWNER))
        self.assertEqual(len(runtime.doc()['features']),1)
        self.assertEqual([e['id'] for e in runtime.doc()['sketches'][0]['entities']],[a])


def run():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CursorTests))
    if not result.wasSuccessful():
        import os
        os._exit(1)
    if not bpy.app.background: bpy.ops.wm.quit_blender()

if __name__=='__main__':
    if bpy.app.background: run()
    else: bpy.app.timers.register(run,first_interval=1.)
