"""Drawable reference points, shared midpoints and recursive sketch subdivision."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import bpy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cad import CadTests, OWNER, volume
from blender_tablet_remote.cad import document as model, sketch as geometry
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.commands import cad
from blender_tablet_remote.errors import CommandError


def ref(identifier, part='POINT'):
    return dict(id=identifier, part=part)


class ReferencePointTests(CadTests):
    def point(self, position):
        with patch.object(cad, '_endpoint', return_value=None), patch.object(runtime, 'point', return_value=position):
            state = cad.entity_begin(dict(type='POINT', u=.5, v=.5, **OWNER))
        identifier = state['selection']['id']
        self.assertEqual(state['selection']['part'], 'POINT')
        with patch.object(runtime, 'point', side_effect=AssertionError('UP must not sample again')):
            cad.confirm(OWNER)
        return identifier

    def subdivide(self, *refs):
        cad._set_selection([dict(kind='ENTITY', **r) for r in refs])
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            state = cad.points_midpoint(OWNER)
            undo.assert_called_once()
        return state['selection']['id']

    def test_point_tap_drag_and_cancel_use_the_last_preview(self):
        baseline = bpy.context.scene.get(model.KEY)
        with patch.object(cad, '_endpoint', return_value=None), patch.object(runtime, 'point', return_value=(.0034, .0044)):
            state = cad.entity_begin(dict(type='POINT', u=.2, v=.2, **OWNER))
        self.assertTrue(state['session']['can_confirm'])
        with patch.object(cad, '_endpoint', return_value=None), patch.object(runtime, 'point', return_value=(.0134, .0144)):
            cad.entity_update(dict(u=.4, v=.4, **OWNER))
            cad.entity_update(dict(u=.4, v=.4, **OWNER))
        with patch.object(cad, 'undo_push') as undo, patch.object(runtime, 'point', side_effect=AssertionError('END resampled')):
            cad.confirm(OWNER)
            undo.assert_called_once()
        sketch = runtime.doc()['sketches'][0]
        self.assertEqual(len(sketch['entities']), 1)
        point = sketch['entities'][0]
        self.assertAlmostEqual(point['x'], .013, places=12)
        self.assertAlmostEqual(point['y'], .014, places=12)
        before = bpy.context.scene[model.KEY]
        with patch.object(cad, '_endpoint', return_value=None), patch.object(runtime, 'point', return_value=(.02, .02)):
            cad.entity_begin(dict(type='POINT', u=.2, v=.2, **OWNER))
        cad.cancel(OWNER)
        self.assertEqual(bpy.context.scene[model.KEY], before)
        self.assertNotEqual(before, baseline)

    def test_one_point_can_be_the_midpoint_of_two_edges_and_a_symmetry_center(self):
        a = self.draw('LINE', (0, 0), (.04, 0))
        cad.constraint_add(dict(type='FIX', refs=[ref(a, 'BODY')], **OWNER))
        b = self.draw('LINE', (0, .03), (.04, .03))
        p = self.point((.02, .015))
        cad.constraint_add(dict(type='MIDPOINT', refs=[ref(a, 'BODY'), ref(p)], **OWNER))
        cad.constraint_add(dict(type='MIDPOINT', refs=[ref(p), ref(b, 'BODY')], **OWNER))
        sketch = runtime.doc()['sketches'][0]
        for identifier in (a, b):
            start, end = geometry.line(sketch, ref(identifier, 'BODY'))
            self.assertLess(max(abs(geometry.point(sketch, ref(p))-(start+end)*.5)), 1e-8)
        c = self.point((.01, -.02)); d = self.point((.03, .02))
        cad.constraint_add(dict(type='SYMMETRIC', refs=[ref(c), ref(d), ref(p)], **OWNER))
        sketch = runtime.doc()['sketches'][0]
        self.assertLess(max(abs((geometry.point(sketch, ref(c))+geometry.point(sketch, ref(d)))*.5-geometry.point(sketch, ref(p)))), 1e-8)
        restored = model.loads(model.dumps(runtime.doc()))
        self.assertEqual(len([c for c in restored['sketches'][0]['constraints'] if c['type']=='MIDPOINT']), 2)

    def test_point_snap_keeps_a_coincidence_and_conflicting_midpoints_are_atomic(self):
        a = self.draw('LINE', (0, 0), (.04, 0))
        anchor = dict(entity_id=a, part='START', id=a+':START', distance=0.)
        with patch.object(cad, '_endpoint', return_value=anchor), patch.object(runtime, 'point', side_effect=AssertionError('Snap must win')):
            state = cad.entity_begin(dict(type='POINT', u=.5, v=.5, **OWNER))
        p = state['selection']['id']; cad.confirm(OWNER)
        sketch = runtime.doc()['sketches'][0]
        coincidence = next(c for c in sketch['constraints'] if c['type']=='COINCIDENT')
        self.assertEqual(coincidence['refs'], [ref(p), ref(a,'START')])
        cad.constraint_delete(dict(constraint_id=coincidence['id'], **OWNER))
        b = self.draw('LINE', (0, .03), (.04, .03))
        for line in (a,b): cad.constraint_add(dict(type='FIX', refs=[ref(line,'BODY')], **OWNER))
        cad.constraint_add(dict(type='MIDPOINT', refs=[ref(p), ref(a,'BODY')], **OWNER))
        before = bpy.context.scene[model.KEY]
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            with self.assertRaises(CommandError):
                cad.constraint_add(dict(type='MIDPOINT', refs=[ref(p), ref(b,'BODY')], **OWNER))
            undo.assert_not_called()
        self.assertEqual(bpy.context.scene[model.KEY], before)

    def test_recursive_midpoints_follow_the_line_and_do_not_split_its_profile(self):
        rectangle = self.rect()
        midpoint = self.subdivide(ref(rectangle, 'EDGE0'))
        quarter = self.subdivide(ref(midpoint), ref(rectangle, 'P0'))
        eighth = self.subdivide(ref(quarter), ref(rectangle, 'P0'))
        cad.entity_set(dict(entity_id=rectangle, values={'width':.16}, **OWNER))
        sketch = runtime.doc()['sketches'][0]
        for identifier, fraction in ((midpoint,.5),(quarter,.25),(eighth,.125)):
            a = geometry.point(sketch, ref(rectangle,'P0')); b = geometry.point(sketch, ref(rectangle,'P1'))
            self.assertLess(max(abs(geometry.point(sketch,ref(identifier))-(a+(b-a)*fraction))), 1e-8)
        self.assertEqual([p['id'] for p in model.closed_entities(sketch)], [rectangle])
        cad.sketch_finish(OWNER)
        cad.extrude_begin(dict(sketch_id=sketch['id'], depth=.02, **OWNER)); cad.confirm(OWNER)
        self.assertAlmostEqual(volume(self.obj()), .16*.045*.02, places=9)
        runtime.rebuild(model.loads(model.dumps(runtime.doc())))
        self.assertAlmostEqual(volume(self.obj()), .16*.045*.02, places=9)

    def test_reference_point_does_not_block_whole_profile_after_construction_toggle(self):
        rectangle = self.rect(); point = self.point((.02,.02))
        cad._set_selection([dict(kind='ENTITY', **ref(point))])
        cad.entity_construction(dict(construction=False, **OWNER))
        sketch, source = model.profile(runtime.doc(), 'profile_'+runtime.active_sketch_id)
        self.assertEqual(source['type'], 'SKETCH')
        self.assertEqual(len(model.closed_entities(sketch)), 1)

    def test_invalid_subdivision_is_atomic_and_has_no_undo(self):
        line = self.draw('LINE', (0, 0), (.04, 0))
        before = bpy.context.scene[model.KEY]
        for refs in ([], [ref(line,'START')], [ref(line,'BODY'),ref(line,'START')], [ref('ORIGIN'),ref('ORIGIN')]):
            cad._set_selection([dict(kind='ENTITY', **r) for r in refs])
            with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
                with self.assertRaises(CommandError): cad.points_midpoint(OWNER)
                undo.assert_not_called()
            self.assertEqual(bpy.context.scene[model.KEY], before)


if __name__ == '__main__':
    suite=unittest.TestSuite(ReferencePointTests(n) for n in ReferencePointTests.__dict__ if n.startswith('test_'))
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
        raise SystemExit(1)
