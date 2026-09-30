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
    def test_confirmed_fields_lock_only_edited_measures_in_one_undo(self):
        entity=self.rect()
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            state=cad.entity_set(dict(entity_id=entity,values={'width':.09123},constrain=True,**OWNER))
            undo.assert_called_once()
        measures=state['document']['sketches'][0]['entities'][0]['dimensions']
        self.assertEqual(len(measures[0]['constraint_ids']),1)
        self.assertEqual(measures[1]['constraint_ids'],[])
        sketch,e=model.entity(runtime.doc(),entity)
        identifier=measures[0]['constraint_ids'][0]
        self.assertAlmostEqual(model.find(sketch,'constraints',identifier)['value'],.09123,places=10)
        geometry.solve(sketch,geometry.move_goals(sketch,[dict(id=entity,part='P2')],.02,.01),drag=True)
        e=model.find(sketch,'entities',entity)
        self.assertAlmostEqual(e['width'],.09123,places=7)
        self.assertGreater(e['height'],.045)
        cad.entity_set(dict(entity_id=entity,values={'width':.08,'height':.06},constrain=True,**OWNER))
        restored=model.loads(bpy.context.scene[model.KEY]); sketch,e=model.entity(restored,entity)
        self.assertEqual(dimensions.bindings(sketch,e)['width'],[identifier])
        self.assertEqual(len(sketch['constraints']),2)
        cad.constraint_delete(dict(constraint_id=identifier,**OWNER))
        sketch,e=model.entity(runtime.doc(),entity)
        self.assertEqual(dimensions.bindings(sketch,e)['width'],[])
        self.assertEqual(len(dimensions.bindings(sketch,e)['height']),1)

    def test_confirmed_radius_aliases_reuse_one_constraint(self):
        for kind,alias,amount in (('CIRCLE','diameter',.03),('SLOT','width',.03)):
            with self.subTest(kind=kind):
                cad.sketch_create(dict(plane='XY',**OWNER))
                entity=self.draw(kind,(0,0),(.025,0))
                cad.entity_set(dict(entity_id=entity,values={alias:amount},constrain=True,**OWNER))
                sketch,e=model.entity(runtime.doc(),entity)
                radius=next(c for c in sketch['constraints'] if c['type']=='RADIUS')
                self.assertAlmostEqual(radius['value'],.015,places=10)
                cad.entity_set(dict(entity_id=entity,values={'radius':.02},constrain=True,**OWNER))
                sketch,e=model.entity(runtime.doc(),entity)
                rules=[c for c in sketch['constraints'] if c['type']=='RADIUS']
                self.assertEqual([c['id'] for c in rules],[radius['id']])
                self.assertAlmostEqual(rules[0]['value'],.02,places=10)
                self.assertAlmostEqual(e[alias],.04,places=9)

    def test_confirmed_square_reuses_equality_and_conflict_is_atomic(self):
        entity=self.square((0,0),(.04,.04))
        cad.entity_set(dict(entity_id=entity,values={'width':.06},constrain=True,**OWNER))
        sketch,e=model.entity(runtime.doc(),entity)
        self.assertAlmostEqual(e['height'],.06)
        self.assertEqual(len([c for c in sketch['constraints'] if c['type']=='DISTANCE']),1)
        before=model.dumps(runtime.doc())
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            with self.assertRaises(CommandError):
                cad.entity_set(dict(entity_id=entity,values={'width':.08,'height':.09},constrain=True,**OWNER))
            undo.assert_not_called()
        self.assertEqual(model.dumps(runtime.doc()),before)

    def test_new_locks_reject_fixed_conflict_without_partial_changes(self):
        entity=self.rect(); self.refs((entity,'BODY')); cad.constraint_add(dict(type='FIX',**OWNER))
        before=model.dumps(runtime.doc())
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            with self.assertRaises(CommandError):
                cad.entity_set(dict(entity_id=entity,values={'width':.12,'height':.09},constrain=True,**OWNER))
            undo.assert_not_called()
        self.assertEqual(model.dumps(runtime.doc()),before)

    def test_confirmed_primitive_measures_use_the_schema_factors(self):
        for kind,field,value,expected in (('LINE','length',.055,.055),('NGON','flats',.032,.016),
                                          ('GEAR','module',.002,.02),('ARC','radius',.018,.018)):
            with self.subTest(kind=kind):
                cad.sketch_create(dict(plane='XY',**OWNER))
                entity=self.draw(kind,(0,0),(.02,0))
                cad.entity_set(dict(entity_id=entity,values={field:value},constrain=True,**OWNER))
                sketch,e=model.entity(runtime.doc(),entity)
                rule=sketch['constraints'][-1]
                self.assertAlmostEqual(rule['value'],expected,places=9)
                self.assertTrue(dimensions.describe(sketch,e)[0]['constraint_ids'])

    def test_confirmation_does_not_lock_discrete_fields_but_locks_arc_angle(self):
        gear=self.draw('GEAR',(0,0),(.02,0))
        cad.entity_set(dict(entity_id=gear,values={'teeth':24},constrain=True,**OWNER))
        sketch,e=model.entity(runtime.doc(),gear)
        self.assertEqual(dimensions.describe(sketch,e)[0]['constraint_ids'],[])
        arc=self.draw('ARC',(.1,.1),(.12,.1))
        cad.entity_set(dict(entity_id=arc,values={'sweep':120.},constrain=True,**OWNER))
        sketch,e=model.entity(runtime.doc(),arc)
        radius,angle=dimensions.describe(sketch,e)
        self.assertEqual(radius['constraint_ids'],[])
        self.assertEqual(angle['field'],'sweep'); self.assertEqual(angle['constraint_type'],'ANGLE')
        self.assertAlmostEqual(model.find(sketch,'constraints',angle['constraint_ids'][0])['value'],120.)

    def test_arc_angle_padlock_holds_the_sweep_while_dragging_its_end(self):
        arc=self.draw('ARC',(.1,.1),(.12,.1))
        sketch,e=model.entity(runtime.doc(),arc)
        cad.constraint_add(dict(type='ANGLE',value=-e['sweep'],refs=[dict(id=arc,part='BODY')],**OWNER))
        sketch,e=model.entity(runtime.doc(),arc); locked=e['sweep']
        self.assertNotIn('ANGLE',runtime.status()['dimension_options'])
        geometry.solve(sketch,geometry.arc_angle_goals(e,(.1,.13),locked),drag=True)
        self.assertAlmostEqual(model.find(sketch,'entities',arc)['sweep'],locked,places=6)
        rule=next(c for c in sketch['constraints'] if c['type']=='ANGLE')
        self.assertTrue(next(o['label'] for o in runtime.overlay(runtime.doc()) if o['id']==rule['id']).endswith('°'))
        cad.constraint_set(dict(constraint_id=rule['id'],value=45,**OWNER))
        self.assertAlmostEqual(abs(model.entity(runtime.doc(),arc)[1]['sweep']),45.,places=6)
        with self.assertRaises(CommandError): cad.constraint_set(dict(constraint_id=rule['id'],value=400,**OWNER))

    def test_roundings_have_no_angle_field_and_equalize_only_their_radius(self):
        ids=[self.draw('LINE',a,b) for a,b in [((0,0),(.08,0)),((.08,0),(.06,.04)),((.06,.04),(0,.04))]]
        self.refs((ids[0],'BODY'),(ids[1],'BODY')); cad.fillet(dict(radius=.004,**OWNER))
        self.refs((ids[1],'BODY'),(ids[2],'BODY')); cad.fillet(dict(radius=.006,**OWNER))
        sketch=runtime.doc()['sketches'][0]
        fillets=[e for e in sketch['entities'] if e['type']=='ARC']
        self.assertEqual(len(fillets),2)
        for e in fillets: self.assertEqual([m['field'] for m in dimensions.describe(sketch,e)],['radius'])
        second=next(c for c in sketch['constraints'] if c['type']=='RADIUS' and c['refs'][0]['id']==fillets[1]['id'])
        cad.constraint_delete(dict(constraint_id=second['id'],**OWNER))
        self.refs(*[(e['id'],'BODY') for e in fillets]); cad.constraint_add(dict(type='EQUAL',**OWNER))
        sketch=runtime.doc()['sketches'][0]
        self.assertFalse([c for c in sketch['constraints'] if c['type']=='EQUAL_ANGLE'])
        arcs=[e for e in sketch['entities'] if e['type']=='ARC']
        self.assertAlmostEqual(arcs[0]['radius'],arcs[1]['radius'],places=7)
        self.assertGreater(abs(abs(arcs[0]['sweep'])-abs(arcs[1]['sweep'])),30.)   # angles follow their own corners

    def test_equal_arcs_share_radius_and_angle_and_one_dimension_governs_all(self):
        arcs=[self.draw('ARC',(x,0),(x+r,0)) for x,r in ((0,.01),(.1,.02),(.2,.015))]
        cad.entity_set(dict(entity_id=arcs[1],values={'sweep':150.},**OWNER))
        self.refs(*[(a,'BODY') for a in arcs])
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            cad.constraint_add(dict(type='EQUAL',**OWNER)); undo.assert_called_once()
        sketch=runtime.doc()['sketches'][0]
        first=model.find(sketch,'entities',arcs[0])
        for a in arcs[1:]:
            e=model.find(sketch,'entities',a)
            self.assertAlmostEqual(e['radius'],first['radius'],places=7)
            self.assertAlmostEqual(abs(e['sweep']),abs(first['sweep']),places=5)
        count=len(sketch['constraints'])
        self.refs(*[(a,'BODY') for a in arcs]); cad.constraint_add(dict(type='EQUAL',**OWNER))
        self.assertEqual(len(runtime.doc()['sketches'][0]['constraints']),count)   # no duplicates
        cad.entity_set(dict(entity_id=arcs[2],values={'radius':.012,'sweep':60.},constrain=True,**OWNER))
        sketch=runtime.doc()['sketches'][0]
        for a in arcs:
            e=model.find(sketch,'entities',a)
            self.assertAlmostEqual(e['radius'],.012,places=7); self.assertAlmostEqual(abs(e['sweep']),60.,places=5)
            radius,angle=dimensions.describe(sketch,e)
            self.assertEqual(len(radius['constraint_ids']),1); self.assertEqual(len(angle['constraint_ids']),1)
        self.assertEqual(len([c for c in sketch['constraints'] if c['type'] in ('RADIUS','ANGLE')]),2)

    def test_tray_values_with_several_arcs_selected_equalize_them_in_one_undo(self):
        a=self.draw('ARC',(0,0),(.01,0)); b=self.draw('ARC',(.1,0),(.13,0))
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            cad.entity_set(dict(entity_id=a,values={'sweep':45.},constrain=True,equal_ids=[b],**OWNER))
            undo.assert_called_once()
        sketch=runtime.doc()['sketches'][0]
        ea,eb=model.find(sketch,'entities',a),model.find(sketch,'entities',b)
        self.assertAlmostEqual(abs(eb['sweep']),45.,places=5); self.assertAlmostEqual(eb['radius'],ea['radius'],places=7)
        self.assertEqual({c['type'] for c in sketch['constraints']},{'EQUAL','EQUAL_ANGLE','ANGLE'})
        before=model.dumps(runtime.doc()); line=self.draw('LINE',(0,.1),(.02,.1)); before=model.dumps(runtime.doc())
        with self.assertRaises(CommandError): cad.entity_set(dict(entity_id=a,values={'radius':.02},equal_ids=[line],**OWNER))
        self.assertEqual(model.dumps(runtime.doc()),before)

    def test_angle_between_lines_is_a_dimension_that_holds_while_dragging(self):
        base=self.draw('LINE',(0,0),(.1,0)); arm=self.draw('LINE',(0,0),(.05,.05))
        cad.constraint_add(dict(type='HORIZONTAL',refs=[dict(id=base,part='BODY')],**OWNER))
        cad._set_selection([dict(kind='ENTITY',id=base,part='BODY'),dict(kind='ENTITY',id=arm,part='BODY')])
        offer=runtime.status()['dimension_options']['ANGLE']
        self.assertAlmostEqual(offer['value'],45.,places=6)
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            cad.constraint_add(dict(type='ANGLE',value=30.,refs=[dict(id=base,part='BODY'),dict(id=arm,part='BODY')],**OWNER))
            undo.assert_called_once()
        sketch=runtime.doc()['sketches'][0]
        self.assertAlmostEqual(geometry.line_angle(sketch,[dict(id=base),dict(id=arm)])[3],30.,places=5)
        rule=next(c for c in sketch['constraints'] if c['type']=='ANGLE')
        geometry.solve(sketch,geometry.move_goals(sketch,[dict(id=arm,part='END')],.02,.03),drag=True)
        self.assertAlmostEqual(geometry.line_angle(sketch,[dict(id=base),dict(id=arm)])[3],30.,places=5)
        cad.constraint_set(dict(constraint_id=rule['id'],value=135,**OWNER))   # obtuse interior corner
        sketch=runtime.doc()['sketches'][0]
        self.assertAlmostEqual(geometry.line_angle(sketch,[dict(id=base),dict(id=arm)])[3],135.,places=5)
        label=next(o for o in runtime.overlay(runtime.doc()) if o['id']==rule['id'])
        self.assertEqual(label['label'],'135°'); self.assertEqual(len(label['arrows']),2)
        with self.assertRaises(CommandError): cad.constraint_set(dict(constraint_id=rule['id'],value=200,**OWNER))

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
        cad.entity_set(dict(entity_id=arc,values={'radius':.01},constrain=True,**OWNER))
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
        e=self.square((0,0),(.04,.04))
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
        e=self.square((0,0),(.04,.04)); self.refs((e,'EDGE0')); self.dimension('DISTANCE',.04)
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
        e=self.square((0,0),(.04,.04)); self.refs((e,'EDGE0')); self.dimension('DISTANCE',.04)
        equal=next(c for c in runtime.doc()['sketches'][0]['constraints'] if c['type']=='EQUAL')
        cad.constraint_delete(dict(constraint_id=equal['id'],**OWNER))
        entity=model.public(runtime.doc())['sketches'][0]['entities'][0]
        self.assertFalse(entity['is_square']); self.assertEqual(len(entity['dimensions']),2)
        cad.entity_set(dict(entity_id=e,values={'height':.06},**OWNER))
        _,entity=model.entity(runtime.doc(),e)
        self.assertAlmostEqual(entity['width'],.04); self.assertAlmostEqual(entity['height'],.06)


    def test_square_rounding_keeps_complete_sides_equal_and_editable(self):
        e=self.square((0,0),(.04,.04))
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
