"""Dimensions and fillets have one editable source and can be removed independently."""
import copy
import math
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_cad import CadTests, OWNER, volume
from blender_tablet_remote.cad import document as model, sketch as geometry, dimensions
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.commands import cad
from blender_tablet_remote.errors import CommandError


class DimensionTests(CadTests):
    def refs(self,*refs): cad._set_selection([dict(kind='ENTITY',id=i,part=p) for i,p in refs])
    def dimension(self,typ,value): cad.constraint_add(dict(type=typ,value=value,**OWNER))

    def rounded(self,extrude=False):
        rectangle=self.rect()
        if extrude:
            self.extrude(rectangle); cad.sketch_activate(dict(sketch_id=runtime.doc()['sketches'][0]['id'],**OWNER))
        self.refs((rectangle,'P2')); cad.fillet(dict(radius=.005,**OWNER))
        return next(e['id'] for e in runtime.doc()['sketches'][0]['entities'] if e['type']=='ARC')

    def test_radius_field_edits_fillet_dimension_and_keeps_outer_bounds(self):
        arc=self.rounded(extrude=True)
        before=runtime.doc(); old_feature=before['features'][0]['id']
        cad.entity_set(dict(entity_id=arc,values={'radius':.01},**OWNER))
        doc=runtime.doc(); sketch,e=model.entity(doc,arc)
        self.assertAlmostEqual(e['radius'],.01)
        self.assertEqual(doc['features'][0]['id'],old_feature)
        points=[p for item in sketch['entities'] for p in model.outline(item)]
        self.assertAlmostEqual(min(p[0] for p in points),0); self.assertAlmostEqual(max(p[0] for p in points),.08)
        self.assertAlmostEqual(min(p[1] for p in points),0); self.assertAlmostEqual(max(p[1] for p in points),.045)
        radius=[c for c in sketch['constraints'] if c['type']=='RADIUS']
        self.assertEqual(len(radius),1); self.assertAlmostEqual(radius[0]['value'],.01)
        self.assertGreater(volume(self.obj()),0)

    def test_constraint_list_edits_same_fillet_and_rejects_oversize_atomically(self):
        arc=self.rounded()
        sketch=runtime.doc()['sketches'][0]; c=next(c for c in sketch['constraints'] if c['type']=='RADIUS')
        cad.constraint_set(dict(constraint_id=c['id'],value=.008,**OWNER))
        self.assertAlmostEqual(model.entity(runtime.doc(),arc)[1]['radius'],.008)
        baseline=model.dumps(runtime.doc())
        with self.assertRaises(CommandError): cad.constraint_set(dict(constraint_id=c['id'],value=.1,**OWNER))
        self.assertEqual(model.dumps(runtime.doc()),baseline)

    def test_remove_fillet_restores_sharp_corner_and_preserves_feature(self):
        arc=self.rounded(extrude=True); feature=runtime.doc()['features'][0]['id']
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            cad.fillet_remove(dict(entity_id=arc,**OWNER)); undo.assert_called_once()
        doc=runtime.doc(); sketch=doc['sketches'][0]
        self.assertEqual(len(sketch['entities']),4)
        self.assertTrue(all(e['type']=='LINE' for e in sketch['entities']))
        self.assertEqual(len(model.profiles(sketch)),1)
        self.assertEqual(doc['features'][0]['id'],feature)
        self.assertAlmostEqual(volume(self.obj()),.08*.045*.02,places=10)
        model.loads(model.dumps(doc))

    def test_removing_radius_releases_measurement_without_removing_fillet(self):
        arc=self.rounded(); sketch=runtime.doc()['sketches'][0]
        c=next(c for c in sketch['constraints'] if c['type']=='RADIUS')
        cad.constraint_delete(dict(constraint_id=c['id'],**OWNER))
        self.assertIsNotNone(geometry.fillet_sides(runtime.doc()['sketches'][0],model.entity(runtime.doc(),arc)[1]))
        cad.entity_set(dict(entity_id=arc,values={'radius':.009},**OWNER))
        sketch,e=model.entity(runtime.doc(),arc)
        self.assertAlmostEqual(e['radius'],.009)
        self.assertFalse(any(c['type']=='RADIUS' for c in sketch['constraints']))

    def test_square_size_is_free_until_dimensioned_then_field_updates_same_dimension(self):
        e=self.draw('SQUARE',(0,0),(.04,.04))
        public=model.public(runtime.doc())['sketches'][0]['entities'][0]
        self.assertTrue(public['is_square']); self.assertEqual(len(public['dimensions']),1)
        self.assertEqual(public['dimensions'][0]['label'],'Lado'); self.assertEqual(public['dimensions'][0]['constraint_ids'],[])
        self.refs((e,'EDGE0')); self.dimension('DISTANCE',.05)
        first=next(c for c in runtime.doc()['sketches'][0]['constraints'] if c['type']=='DISTANCE')['id']
        cad.entity_set(dict(entity_id=e,values={'width':.08},**OWNER))
        sketch,entity=model.entity(runtime.doc(),e)
        self.assertAlmostEqual(entity['width'],.08); self.assertAlmostEqual(entity['height'],.08)
        self.assertEqual(dimensions.bindings(sketch,entity),{'width':[first],'height':[first]})
        self.refs((e,'EDGE1')); self.dimension('DISTANCE',.09)
        c=[c for c in runtime.doc()['sketches'][0]['constraints'] if c['type']=='DISTANCE']
        self.assertEqual(len(c),1); self.assertEqual(c[0]['id'],first); self.assertAlmostEqual(c[0]['value'],.09)
        cad.constraint_delete(dict(constraint_id=first,**OWNER))
        self.assertEqual([c['type'] for c in runtime.doc()['sketches'][0]['constraints']],['EQUAL'])
        cad.entity_set(dict(entity_id=e,values={'height':.06},**OWNER))
        self.assertAlmostEqual(model.entity(runtime.doc(),e)[1]['width'],.06)

    def test_opposite_sides_and_endpoint_distance_reuse_one_width_dimension(self):
        e=self.rect()
        self.refs((e,'EDGE0')); self.dimension('DISTANCE',.1)
        self.refs((e,'EDGE2')); self.dimension('DISTANCE',.12)
        self.refs((e,'P0'),(e,'P1')); self.dimension('DISTANCE',.14)
        sketch,entity=model.entity(runtime.doc(),e)
        self.assertEqual(len(sketch['constraints']),1); self.assertAlmostEqual(entity['width'],.14)
        cad.entity_set(dict(entity_id=e,values={'width':.16,'height':.06},**OWNER))
        self.assertAlmostEqual(runtime.doc()['sketches'][0]['constraints'][0]['value'],.16)

    def test_circle_diameter_and_line_length_share_existing_dimensions(self):
        circle=self.draw('CIRCLE',(.1,.1),(.12,.1)); self.refs((circle,'BODY')); self.dimension('RADIUS',.02)
        cad.entity_set(dict(entity_id=circle,values={'diameter':.06},**OWNER))
        self.assertAlmostEqual(runtime.doc()['sketches'][0]['constraints'][0]['value'],.03)
        line=self.draw('LINE',(0,0),(.04,0)); self.refs((line,'BODY')); self.dimension('DISTANCE',.04)
        cad.entity_set(dict(entity_id=line,values={'length':.07},**OWNER))
        e=model.entity(runtime.doc(),line)[1]
        self.assertAlmostEqual(e['x2']-e['x'],.07)
        self.assertAlmostEqual(model.public(runtime.doc())['sketches'][0]['entities'][-1]['length'],.07)

    def test_conflicting_square_fields_do_not_silently_choose_one(self):
        e=self.draw('SQUARE',(0,0),(.04,.04)); self.refs((e,'EDGE0')); self.dimension('DISTANCE',.04)
        baseline=model.dumps(runtime.doc())
        with self.assertRaises(CommandError): cad.entity_set(dict(entity_id=e,values={'width':.08,'height':.09},**OWNER))
        self.assertEqual(model.dumps(runtime.doc()),baseline)

    def test_old_duplicate_measurements_are_merged_or_removed_together(self):
        e=self.rect(); self.refs((e,'EDGE0')); self.dimension('DISTANCE',.08)
        doc=runtime.doc(); sketch=doc['sketches'][0]; original=sketch['constraints'][0]
        duplicate=dict(copy.deepcopy(original),id=model.uid('constraint')); duplicate['refs'][0]['part']='EDGE2'
        sketch['constraints'].append(duplicate); runtime.persist(doc)
        self.assertEqual(len(model.public(runtime.doc())['sketches'][0]['constraints']),1)
        cad.constraint_set(dict(constraint_id=original['id'],value=.09,**OWNER))
        self.assertEqual(len(runtime.doc()['sketches'][0]['constraints']),1)
        self.assertAlmostEqual(model.entity(runtime.doc(),e)[1]['width'],.09)
        cad.constraint_delete(dict(constraint_id=original['id'],**OWNER))
        self.assertFalse(runtime.doc()['sketches'][0]['constraints'])


    def test_measurement_offer_uses_actual_size_and_existing_dimension(self):
        e=self.rect(); self.refs((e,'EDGE0'))
        option=runtime.status()['dimension_options']['DISTANCE']
        self.assertAlmostEqual(option['value'],.08); self.assertIsNone(option['constraint_id'])
        self.dimension('DISTANCE',.1)
        self.refs((e,'EDGE2'))
        option=runtime.status()['dimension_options']['DISTANCE']
        self.assertAlmostEqual(option['value'],.1)
        self.assertEqual(option['constraint_id'],runtime.doc()['sketches'][0]['constraints'][0]['id'])

    def test_measurement_spec_targets_correct_field_without_reselecting(self):
        e=self.rect(); other=self.draw('CIRCLE',(.2,.2),(.22,.2)); self.refs((other,'CENTER'))
        cad.constraint_add(dict(type='DISTANCE',value=.12,refs=[dict(id=e,part='EDGE0')],**OWNER))
        self.assertAlmostEqual(model.entity(runtime.doc(),e)[1]['width'],.12)
        self.assertEqual(cad._refs()[0]['id'],other)
        raw=model.dumps(runtime.doc())
        with self.assertRaises(CommandError): cad.constraint_add(dict(type='DISTANCE',value=.1,refs=[],**OWNER))
        self.assertEqual(model.dumps(runtime.doc()),raw)

    def test_removing_square_equality_releases_height_and_keeps_width_dimension(self):
        e=self.draw('SQUARE',(0,0),(.04,.04)); self.refs((e,'EDGE0')); self.dimension('DISTANCE',.04)
        equal=next(c for c in runtime.doc()['sketches'][0]['constraints'] if c['type']=='EQUAL')
        cad.constraint_delete(dict(constraint_id=equal['id'],**OWNER))
        entity=model.public(runtime.doc())['sketches'][0]['entities'][0]
        self.assertFalse(entity['is_square']); self.assertEqual(len(entity['dimensions']),2)
        cad.entity_set(dict(entity_id=e,values={'height':.06},**OWNER))
        _,entity=model.entity(runtime.doc(),e)
        self.assertAlmostEqual(entity['width'],.04); self.assertAlmostEqual(entity['height'],.06)


    def test_square_rounding_keeps_complete_sides_equal_and_editable(self):
        e=self.draw('SQUARE',(0,0),(.04,.04))
        self.refs((e,'EDGE0')); self.dimension('DISTANCE',.04)
        self.refs((e,'P2')); cad.fillet(dict(radius=.005,**OWNER))
        arc=next(e['id'] for e in runtime.doc()['sketches'][0]['entities'] if e['type']=='ARC')
        for radius in (.008,.012,.003):
            cad.entity_set(dict(entity_id=arc,values={'radius':radius},**OWNER))
            sketch=runtime.doc()['sketches'][0]
            points=[p for item in sketch['entities'] for p in model.outline(item)]
            self.assertAlmostEqual(max(p[0] for p in points)-min(p[0] for p in points),.04,places=7)
            self.assertAlmostEqual(max(p[1] for p in points)-min(p[1] for p in points),.04,places=7)
        cad.fillet_remove(dict(entity_id=arc,**OWNER))
        sketch=runtime.doc()['sketches'][0]
        for line in sketch['entities']:
            self.assertAlmostEqual(math.dist(*geometry.line(sketch,dict(id=line['id'],part='BODY'))),.04,places=7)


    def test_semicircle_between_parallel_sides_remains_an_arc_not_a_corner(self):
        arc=self.draw('ARC',(0,0),(.01,0))
        cad.entity_set(dict(entity_id=arc,values={'sweep':180.},**OWNER))
        a=self.draw('LINE',(.01,0),(.01,-.03)); b=self.draw('LINE',(-.01,0),(-.01,-.03))
        for line,role in ((a,'START'),(b,'END')):
            self.refs((line,'START'),(arc,role)); cad.constraint_add(dict(type='COINCIDENT',**OWNER))
            self.refs((line,'BODY'),(arc,'BODY')); cad.constraint_add(dict(type='TANGENT',**OWNER))
        state=runtime.status()
        self.assertIsNone(state['error'])
        entity=next(e for e in state['document']['sketches'][0]['entities'] if e['id']==arc)
        self.assertFalse(entity['is_fillet'])
        self.assertAlmostEqual(next(e for e in state['document']['sketches'][0]['entities'] if e['id']==a)['length'],.03)


def run():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DimensionTests))
    if not result.wasSuccessful():
        import os
        os._exit(1)
    if not bpy.app.background: bpy.ops.wm.quit_blender()

if __name__=='__main__':
    if bpy.app.background: run()
    else: bpy.app.timers.register(run,first_interval=1.)
