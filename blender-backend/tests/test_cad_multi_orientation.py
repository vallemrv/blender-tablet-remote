"""Horizontal/Vertical applies to a whole selection in one atomic transaction."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import bpy

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_cad import CadTests, OWNER
from blender_tablet_remote.cad import document as model, sketch as geometry
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.commands import cad
from blender_tablet_remote.errors import CommandError


class MultiOrientationTests(CadTests):
    def lines(self,count=6):
        return [self.draw('LINE',(i*.03,0),(i*.03+.01,.006)) for i in range(count)]

    def test_six_selected_lines_are_constrained_together_and_survive_drag_and_save(self):
        for typ,axis in (('HORIZONTAL',1),('VERTICAL',0)):
            with self.subTest(type=typ):
                cad.sketch_create(dict(plane='XY',**OWNER))
                ids=self.lines()
                refs=[dict(id=identifier,part='BODY') for identifier in ids]
                cad._set_selection([dict(kind='ENTITY',**ref) for ref in refs])
                with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
                    cad.constraint_add(dict(type=typ,**OWNER));undo.assert_called_once()
                doc=runtime.doc();sketch=doc['sketches'][-1]
                rules=[c for c in sketch['constraints'] if c['type']==typ]
                self.assertEqual(len(rules),6)
                self.assertEqual([c['refs'] for c in rules],[[ref] for ref in refs])
                geometry.solve(sketch,geometry.move_goals(sketch,[dict(id=ids[0],part='END')],.005,.007),drag=True)
                for ref in refs:
                    a,b=geometry.line(sketch,ref)
                    self.assertAlmostEqual(a[axis],b[axis],places=8)
                restored=model.loads(bpy.context.scene[model.KEY])
                self.assertEqual(restored['sketches'][-1]['constraints'],runtime.doc()['sketches'][-1]['constraints'])

    def test_rectangle_and_ngon_sides_can_share_one_request_without_duplicate_rules(self):
        rectangle=self.rect()
        polygon=self.draw('NGON',(.15,.1),(.17,.1))
        _,entity=model.entity(runtime.doc(),polygon)
        cad.constraint_add(dict(type='RADIUS',value=entity['flats']/2,
                                refs=[dict(id=polygon,part='BODY')],**OWNER))
        refs=[dict(id=rectangle,part='EDGE0'),dict(id=rectangle,part='EDGE2'),
              dict(id=polygon,part='EDGE0'),dict(id=polygon,part='EDGE3')]
        cad.constraint_add(dict(type='HORIZONTAL',refs=refs+[refs[0]],**OWNER))
        sketch=runtime.doc()['sketches'][0]
        rules=[c for c in sketch['constraints'] if c['type']=='HORIZONTAL']
        self.assertEqual(len(rules),4)
        for ref in refs:
            a,b=geometry.line(sketch,ref)
            self.assertAlmostEqual(a[1],b[1],places=8)
        cad.constraint_add(dict(type='HORIZONTAL',refs=refs,**OWNER))
        self.assertEqual([c['id'] for c in runtime.doc()['sketches'][0]['constraints'] if c['type']=='HORIZONTAL'],
                         [c['id'] for c in rules])

    def test_conflict_in_one_selected_line_rejects_the_entire_group(self):
        ids=self.lines()
        cad.constraint_add(dict(type='FIX',refs=[dict(id=ids[-1],part='BODY')],**OWNER))
        before=model.dumps(runtime.doc())
        for typ in ('HORIZONTAL','VERTICAL'):
            with self.subTest(type=typ), patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
                with self.assertRaises(CommandError):
                    cad.constraint_add(dict(type=typ,refs=[dict(id=i,part='BODY') for i in ids],**OWNER))
                undo.assert_not_called()
                self.assertEqual(model.dumps(runtime.doc()),before)

    def test_invalid_or_empty_selection_does_not_leave_partial_constraints(self):
        ids=self.lines(4)
        circle=self.draw('CIRCLE',(.2,.2),(.21,.2))
        refs=[dict(id=i,part='BODY') for i in ids]
        before=model.dumps(runtime.doc())
        for selection in ([],refs+[dict(id=circle,part='BODY')],refs+[dict(id=ids[0],part='END')]):
            with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
                with self.assertRaises(CommandError):
                    cad.constraint_add(dict(type='HORIZONTAL',refs=selection,**OWNER))
                undo.assert_not_called()
                self.assertEqual(model.dumps(runtime.doc()),before)


if __name__=='__main__':
    suite=unittest.TestSuite(MultiOrientationTests(n) for n in MultiOrientationTests.__dict__ if n.startswith('test_'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        import os
        os._exit(1)
