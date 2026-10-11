"""Explicit projected-profile closure, including truncated arcs from a real CAD body."""
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
from test_cad import CadTests,OWNER,volume
from blender_tablet_remote.cad import document as model
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.commands import cad
from blender_tablet_remote.errors import CommandError

FRAME=json.loads((Path(__file__).parent/'fixtures'/'cad_projected_frame.json').read_text())


class ProjectedProfileTests(CadTests):
    def projected_frame(self):
        doc=runtime.doc();sketch=doc['sketches'][0]
        sketch['entities']=copy.deepcopy(FRAME['entities']);sketch['constraints']=copy.deepcopy(FRAME['constraints'])
        runtime.persist(doc)
        return sketch['id']

    def test_real_projected_frame_closes_in_one_undo_and_extrudes(self):
        sketch_id=self.projected_frame();before=copy.deepcopy(runtime.doc())
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            state=cad.close_reference(OWNER);undo.assert_called_once()
        sketch=runtime.doc()['sketches'][0]
        self.assertEqual(len(model.profiles(sketch)),1)
        self.assertTrue(all(not e['construction'] and e['reference'] for e in sketch['entities']))
        self.assertEqual([e['id'] for e in sketch['entities']],[e['id'] for e in before['sketches'][0]['entities']])
        for old,new in zip(before['sketches'][0]['entities'],sketch['entities']):
            if new['type']=='ARC':
                self.assertEqual((new['x'],new['y'],new['radius']),(old['x'],old['y'],old['radius']))
                self.assertAlmostEqual(abs(new['sweep']),90.,places=6)
        self.assertEqual(len([c for c in sketch['constraints'] if c['type']=='COINCIDENT']),8)
        cad.sketch_finish(OWNER)
        cad.extrude_begin(dict(sketch_id=sketch_id,depth=.003,**OWNER));cad.confirm(OWNER)
        expected=(.1*.06-(4-math.pi)*.005**2)*.003
        self.assertAlmostEqual(volume(self.obj()),expected,delta=2e-8)
        runtime.rebuild(model.loads(model.dumps(runtime.doc())))
        self.assertAlmostEqual(volume(self.obj()),expected,delta=2e-8)

    def test_gap_beyond_step_rejects_all_changes_and_undo(self):
        self.projected_frame();cad.settings(dict(step=.0001,**OWNER));before=bpy.context.scene[model.KEY]
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            with self.assertRaisesRegex(CommandError,'Paso'):cad.close_reference(OWNER)
            undo.assert_not_called()
        self.assertEqual(bpy.context.scene[model.KEY],before)

    def test_selected_closed_rectangle_converts_without_unfixing_other_references(self):
        self.projected_frame()
        doc=runtime.doc();sketch=doc['sketches'][0]
        rectangle=dict(id='rectangle',type='RECTANGLE',x=.08,y=0.,width=.02,height=.02,construction=True,reference=True)
        sketch['entities'].append(rectangle)
        sketch['constraints'].append(dict(id='fix_rect',type='FIX',refs=[dict(id='rectangle',part='BODY')],values={k:rectangle[k] for k in model.FIELDS['RECTANGLE']}))
        runtime.persist(doc)
        cad._set_selection([dict(kind='ENTITY',id='rectangle',part='BODY')]);cad.close_reference(OWNER)
        sketch=runtime.doc()['sketches'][0]
        self.assertEqual(sketch['entities'][:-1],FRAME['entities'])
        self.assertFalse(sketch['entities'][-1]['construction'])
        self.assertEqual(model.profiles(sketch)[0]['id'],'profile_rectangle')

    def test_ambiguous_branch_rejects_without_persisting_a_partial_closure(self):
        self.projected_frame();doc=runtime.doc();sketch=doc['sketches'][0]
        duplicate=copy.deepcopy(sketch['entities'][0]);duplicate['id']='duplicate'
        sketch['entities'].append(duplicate);runtime.persist(doc);before=bpy.context.scene[model.KEY]
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            with self.assertRaisesRegex(CommandError,'varios extremos'):cad.close_reference(OWNER)
            undo.assert_not_called()
        self.assertEqual(bpy.context.scene[model.KEY],before)


if __name__=='__main__':
    suite=unittest.TestSuite(ProjectedProfileTests(n) for n in ProjectedProfileTests.__dict__ if n.startswith('test_'))
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():raise SystemExit(1)
