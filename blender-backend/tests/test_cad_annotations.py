"""Selectable dimensions use sketch-space placement and leave geometry untouched."""
import copy
import json
import math
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import bpy

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_cad import CadTests, OWNER
from blender_tablet_remote.cad import document as model, annotations
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.commands import cad, snap
from blender_tablet_remote.errors import CommandError


class AnnotationTests(CadTests):
    def dimension(self):
        entity=self.rect()
        cad.constraint_add(dict(type='DISTANCE',refs=[dict(id=entity,part='EDGE0')],value=.08,**OWNER))
        return entity,runtime.doc()['sketches'][0]['constraints'][0]['id']

    def test_distance_arrows_keep_witness_endpoints_while_label_moves(self):
        entity,identifier=self.dimension();sketch=runtime.doc()['sketches'][0];rule=model.find(sketch,'constraints',identifier)
        rule['label_position']=[.06,-.02]
        drawing=annotations.layout(sketch,rule)
        self.assertEqual(drawing['segments'][0],((0.,0.),(0.,-.02)))
        self.assertEqual(drawing['segments'][1],((.08,0.),(.08,-.02)))
        self.assertEqual(drawing['arrows'],[((0.,-.02),(.08,-.02)),((.08,-.02),(0.,-.02))])
        self.assertEqual(drawing['label'],(.06,-.02))
        self.assertEqual(rule['value'],.08)

    def test_axis_dimensions_and_zero_distance_are_finite(self):
        a=self.draw('CIRCLE',(.02,.03),(.025,.03));b=self.draw('CIRCLE',(.06,.07),(.065,.07))
        sketch=runtime.doc()['sketches'][0]
        refs=[dict(id=i,part='CENTER') for i in (a,b)]
        for typ in ('DISTANCE_X','DISTANCE_Y'):
            rule=dict(id='measure',type=typ,refs=refs,value=.04,label_position=[.1,.12])
            drawing=annotations.layout(sketch,rule)
            p,q=drawing['segments'][-1]
            axis=1 if typ=='DISTANCE_X' else 0
            self.assertEqual(p[axis],q[axis])
            self.assertAlmostEqual(math.dist(p,q),.04,places=8)
        rule=dict(id='zero',type='DISTANCE_X',refs=[dict(id='ORIGIN',part='POINT'),dict(id='ORIGIN',part='POINT')],value=0.)
        drawing=annotations.layout(sketch,rule)
        self.assertTrue(all(math.isfinite(x) for line in drawing['segments'] for p in line for x in p))

    def test_radius_arrow_ends_on_arc_even_when_label_is_outside_its_sector(self):
        arc=self.draw('ARC',(.02,.03),(.04,.03));cad.entity_set(dict(entity_id=arc,values={'start':0.,'sweep':90.},**OWNER))
        sketch=runtime.doc()['sketches'][0]
        rule=dict(id='radius',type='RADIUS',refs=[dict(id=arc,part='BODY')],value=.02,label_position=[-.05,-.05])
        drawing=annotations.layout(sketch,rule);center,rim=drawing['segments'][0]
        self.assertAlmostEqual(center[0],.02);self.assertAlmostEqual(center[1],.03)
        self.assertAlmostEqual(math.dist(center,rim),.02,places=8)
        self.assertGreaterEqual(rim[0],center[0]-1e-9);self.assertGreaterEqual(rim[1],center[1]-1e-9)
        self.assertEqual(drawing['arrows'],[(rim,center)])

    def test_slot_radius_uses_an_endcap_center_and_angular_arrows_follow_sweep(self):
        slot=self.draw('SLOT',(0,0),(.04,0));sketch=runtime.doc()['sketches'][0]
        e=model.find(sketch,'entities',slot)
        rule=dict(id='radius',type='RADIUS',refs=[dict(id=slot,part='BODY')],value=e['width']/2,label_position=[.07,.03])
        center,rim=annotations.layout(sketch,rule)['segments'][0]
        self.assertAlmostEqual(center[0],.04,places=8)
        self.assertAlmostEqual(math.dist(center,rim),e['width']/2,places=8)
        arc=self.draw('ARC',(.1,.1),(.12,.1));cad.entity_set(dict(entity_id=arc,values={'sweep':90.},**OWNER))
        sketch=runtime.doc()['sketches'][0];e=model.find(sketch,'entities',arc)
        rule=dict(id='angle',type='ANGLE',refs=[dict(id=arc,part='BODY')],value=90.)
        drawing=annotations.layout(sketch,rule)
        first,last=[sub[0] for sub in drawing['arrows']]
        self.assertAlmostEqual(first[1],e['y'],places=8)
        self.assertAlmostEqual(last[0],e['x'],places=8)
        self.assertAlmostEqual(math.dist(first,(e['x'],e['y'])),math.dist(last,(e['x'],e['y'])),places=8)

    def test_only_dimensions_are_selectable_one_at_a_time(self):
        first,identifier=self.dimension();second=self.draw('LINE',(.1,0),(.13,0))
        cad.constraint_add(dict(type='HORIZONTAL',refs=[dict(id=second,part='BODY')],**OWNER))
        rule=runtime.doc()['sketches'][0]['constraints'][-1]['id']
        cad.constraint_add(dict(type='DISTANCE',refs=[dict(id=second,part='BODY')],value=.03,**OWNER))
        other=runtime.doc()['sketches'][0]['constraints'][-1]['id']
        cad.select(dict(kind='ENTITY',id=first,additive=True,**OWNER));cad.select(dict(kind='ENTITY',id=second,additive=True,**OWNER))
        cad.select(dict(kind='CONSTRAINT',id=identifier,additive=True,**OWNER))
        self.assertEqual([(r['kind'],r['id']) for r in cad._refs()],[('CONSTRAINT',identifier)])
        cad.select(dict(kind='CONSTRAINT',id=other,additive=True,**OWNER))
        cad.select(dict(kind='CONSTRAINT',id=other,additive=True,**OWNER))
        self.assertEqual([r['id'] for r in cad._refs()],[other])
        with self.assertRaises(CommandError): cad.select(dict(kind='CONSTRAINT',id=rule,**OWNER))
        cad.select(dict(kind='ENTITY',id=first,additive=True,**OWNER));cad.select(dict(kind='ENTITY',id=second,additive=True,**OWNER))
        self.assertEqual([r['id'] for r in cad._refs()],[first,second])

    def test_rule_marks_appear_only_beside_selected_geometry_and_are_not_pickable(self):
        line=self.draw('LINE',(0,0),(.03,0))
        cad.constraint_add(dict(type='HORIZONTAL',refs=[dict(id=line,part='BODY')],**OWNER))
        sketch=runtime.doc()['sketches'][0];project=lambda p:[.2+p[0]*3,.6-p[1]*3]
        self.assertFalse(annotations.overlay(sketch,project,None,'MILLIMETERS',1.))
        selection=dict(kind='ENTITY',id=line,part='BODY',items=[dict(kind='ENTITY',id=line,part='BODY')])
        marks=annotations.overlay(sketch,project,selection,'MILLIMETERS',1.)
        self.assertEqual([(m['kind'],m['label']) for m in marks],[('CONSTRAINT','H')])
        self.assertNotIn('label_box',marks[0])
        u,v=marks[0]['label_point']
        self.assertIsNone(snap.query_sketch_annotation(marks,u,v,1.,labels_only=False))

    def test_projected_labels_and_lines_are_pickable_and_reproject(self):
        entity,identifier=self.dimension();sketch=runtime.doc()['sketches'][0]
        project=lambda p:[.2+p[0]*3,.6-p[1]*3]
        overlay=annotations.overlay(sketch,project,None,'MILLIMETERS',2.)
        item=overlay[0];self.assertEqual(item['label'],'80 mm');self.assertEqual(len(item['arrows']),2)
        u,v=item['label_point']
        self.assertEqual(snap.query_sketch_annotation(overlay,u,v,2.)['id'],identifier)
        with patch.object(runtime,'overlay',return_value=overlay):
            self.assertEqual(cad._pick(dict(u=u,v=v))['kind'],'CONSTRAINT')
        moved=annotations.overlay(sketch,lambda p:[project(p)[0]+.1,project(p)[1]],None,'MILLIMETERS',2.)
        self.assertAlmostEqual(moved[0]['label_point'][0]-u,.1)
        self.assertEqual(runtime.doc()['sketches'][0]['constraints'],sketch['constraints'])

    def test_drag_changes_only_annotation_without_solver_or_rebuild_and_one_undo(self):
        entity,identifier=self.dimension();before=copy.deepcopy(runtime.doc())
        hit=dict(kind='CONSTRAINT',id=identifier,part='LABEL')
        with patch.object(cad,'_pick',return_value=hit),patch.object(runtime,'point',return_value=(.01,.01)):
            cad.drag_begin(dict(u=.5,v=.5,**OWNER))
        original=runtime.session['annotation_start'];runtime.increment=True;runtime.step=.01
        with patch.object(runtime,'rebuild_steps',side_effect=AssertionError('annotation rebuilt geometry')):
            for p in ((.02,.03),(.0137,.0242)):
                with patch.object(runtime,'point',return_value=p):cad.drag_update(dict(u=.6,v=.6,**OWNER))
            with patch.object(runtime,'point',side_effect=AssertionError('END raycast')),patch.object(cad,'undo_push') as undo:
                cad.drag_end(OWNER);undo.assert_called_once()
        doc=runtime.doc();sketch=doc['sketches'][0];rule=model.find(sketch,'constraints',identifier)
        self.assertAlmostEqual(rule['label_position'][0],original[0]+.0037)
        self.assertAlmostEqual(rule['label_position'][1],original[1]+.0142)
        self.assertEqual(sketch['entities'],before['sketches'][0]['entities'])
        self.assertEqual(rule['value'],.08)
        self.assertEqual(model.loads(bpy.context.scene[model.KEY])['sketches'][0]['constraints'],sketch['constraints'])
        cad.constraint_set(dict(constraint_id=identifier,value=.09,**OWNER))
        self.assertEqual(model.find(runtime.doc()['sketches'][0],'constraints',identifier)['label_position'],rule['label_position'])

    def test_tap_has_no_undo_and_cancel_restores_placement_and_selection(self):
        entity,identifier=self.dimension();before=model.dumps(runtime.doc())
        hit=dict(kind='CONSTRAINT',id=identifier,part='LABEL')
        with patch.object(cad,'_pick',return_value=hit),patch.object(runtime,'point',return_value=(0,0)):
            cad.drag_begin(dict(u=.5,v=.5,**OWNER))
        with patch.object(cad,'undo_push') as undo:cad.drag_end(OWNER);undo.assert_not_called()
        self.assertEqual(runtime.selection['id'],identifier);self.assertEqual(model.dumps(runtime.doc()),before)
        previous=copy.deepcopy(runtime.selection)
        with patch.object(cad,'_pick',return_value=hit),patch.object(runtime,'point',return_value=(0,0)):
            cad.drag_begin(dict(u=.5,v=.5,**OWNER))
        with patch.object(runtime,'point',return_value=(.01,.02)):cad.drag_update(dict(u=.6,v=.6,**OWNER))
        with patch.object(runtime,'rebuild',side_effect=AssertionError('cancel rebuilt geometry')):cad.cancel(OWNER)
        self.assertEqual(model.dumps(runtime.doc()),before);self.assertEqual(runtime.selection,previous)
        cad.constraint_delete(dict(constraint_id=identifier,**OWNER))
        self.assertIsNone(runtime.selection)

    def test_invalid_stored_label_coordinates_are_rejected(self):
        _,identifier=self.dimension()
        for value in ([0.],['bad',1.],[float('nan'),0.]):
            doc=runtime.doc();doc['sketches'][0]['constraints'][0]['label_position']=value
            with self.assertRaises(CommandError):model.loads(json.dumps(doc))

    def test_overlapping_labels_keep_the_explicitly_selected_rule_on_top(self):
        _,identifier=self.dimension();sketch=runtime.doc()['sketches'][0]
        first=sketch['constraints'][0];first['label_position']=[.05,.06]
        other=dict(id='other',type='DISTANCE_Y',refs=copy.deepcopy(first['refs']),value=0.,label_position=[.05,.06])
        sketch['constraints'].append(other)
        overlay=annotations.overlay(sketch,lambda p:list(p),dict(kind='CONSTRAINT',id=identifier),'METERS',1.)
        self.assertEqual(overlay[-1]['id'],identifier)
        self.assertEqual(snap.query_sketch_annotation(overlay,.05,.06,1.)['id'],identifier)


if __name__=='__main__':
    suite=unittest.TestSuite(AnnotationTests(n) for n in AnnotationTests.__dict__ if n.startswith('test_'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        import os
        os._exit(1)
