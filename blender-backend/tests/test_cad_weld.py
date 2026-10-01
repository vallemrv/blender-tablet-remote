"""Joining points on a real sketch with projected references, and its solver cost."""
import copy
import json
import math
import sys
import time
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

FIXTURE=json.loads((Path(__file__).parent/'fixtures/sketch_near_redundant.json').read_text())
# Left arc start and the upper arc end: both on the same R25 circle.
LEFT=dict(id='entity_e9bd94a8477b4bac875fbb95ee01f9b1',part='START')
TOP=dict(id='entity_7d6ba1b53ca844e9aaf552b0016855d0',part='END')


def sketch():
    return dict(id='sketch_weld',name='Boceto',plane='XY',offset=0,**copy.deepcopy(FIXTURE))


class WeldTests(CadTests):
    def test_weld_accepts_float32_noise_of_projected_references(self):
        s=sketch(); anchor=geometry.point(s,TOP)
        self.assertTrue(geometry.weld_points(s,[LEFT,TOP]))
        self.assertLess(math.dist(geometry.point(s,LEFT),anchor),1e-7)
        self.assertLess(math.dist(geometry.point(s,TOP),anchor),1e-7)

    def test_real_conflict_is_still_rejected(self):
        s=sketch()
        # The bottom line endpoint is fixed: it cannot reach the top arc.
        with self.assertRaises(CommandError):
            geometry.weld_points(s,[TOP,dict(id='entity_bb39251b025246878e84d6211fb3fc20',part='START')])

    def test_drag_solve_reevaluates_only_items_reading_each_parameter(self):
        s=sketch()
        ref=[dict(id=next(e['id'] for e in s['entities'] if e['id'].endswith('2df9b1')),part='BODY')]
        started=time.perf_counter()
        geometry.solve(s,geometry.move_goals(s,ref,.001,0.),drag=True)
        self.assertLess(time.perf_counter()-started,.15)

    def test_zero_distance_between_two_points_joins_them(self):
        a=self.draw('LINE',(0,0),(.02,0)); b=self.draw('LINE',(.03,.01),(.05,.01))
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            cad.constraint_add(dict(type='DISTANCE',value=0.,refs=[dict(id=a,part='END'),dict(id=b,part='START')],**OWNER))
            undo.assert_called_once()
        s=runtime.doc()['sketches'][-1]
        self.assertTrue(any(c['type']=='COINCIDENT' for c in s['constraints']))
        self.assertLess(math.dist(geometry.point(s,dict(id=a,part='END')),(.03,.01)),1e-7)


if __name__=='__main__':
    suite=unittest.TestSuite(WeldTests(n) for n in WeldTests.__dict__ if n.startswith('test_'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        import os
        os._exit(1)
