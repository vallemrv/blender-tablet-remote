"""GUI: blender --factory-startup --python this_file -- --looptools-dir /path/to/parent.
The optional directory contains the real LoopTools package, never a fake operator.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import bpy
import bmesh
from mathutils import Vector
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import tools, mesh, history
from blender_tablet_remote.bpy_utils import undo_push
from blender_tablet_remote.errors import CommandError


class LoopCutTests(unittest.TestCase):
    def setUp(self):
        tools.tool_session.restore_safely()
        tools.tool_session.close()
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add()
        bpy.context.scene.unit_settings.scale_length = .01
        bpy.context.object.scale = (2, 3, 4)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.context.tool_settings.mesh_select_mode = (False, True, False)
        bm = bmesh.from_edit_mesh(bpy.context.object.data)
        bm.edges.ensure_lookup_table()
        seed = bm.edges[0]
        self.edge = seed.index
        self.direction = (seed.verts[1].co-seed.verts[0].co).normalized()
        self.axis = max(range(3), key=lambda i:abs(self.direction[i]))
        self.meters_per_local = (bpy.context.object.matrix_world.to_3x3() @ self.direction).length * .01
        for e in bm.edges:e.select_set(False)
        for v in bm.verts:v.select = False
        bmesh.update_edit_mesh(bpy.context.object.data)
        undo_push('Loop test baseline')

    def tearDown(self):
        tools.tool_session.restore_safely()
        tools.tool_session.close()

    def coords(self):
        bm = bmesh.from_edit_mesh(bpy.context.object.data)
        return tuple(sorted(tuple(round(c, 6) for c in v.co) for v in bm.verts))

    def levels(self):
        bm = bmesh.from_edit_mesh(bpy.context.object.data)
        return sorted(set(round(v.co.dot(self.direction), 6) for v in bm.verts if v.select))

    def begin(self, cuts=1):
        return tools.begin({'tool':'LOOP_CUT', 'parameters':{'edge':self.edge,'cuts':cuts}})

    def test_first_touch_and_added_cut_ignore_touch_factor(self):
        tools.begin({'tool':'LOOP_CUT', 'parameters':{'cuts':1}})
        self.assertFalse(tools.tool_session.active)
        with patch.object(mesh, 'loop_probe', return_value={'hit':True,'edge':self.edge,'factor':.8}):
            tools.loop_pick({'u':.5,'v':.5})
        self.assertEqual(self.levels(), [0.0])
        self.assertEqual(tools.tool_session.params['factor'], 0.0)
        with patch.object(mesh, 'loop_probe', return_value={'hit':True,'edge':self.edge,'factor':-.7}):
            tools.loop_pick({'u':.5,'v':.5,'add':True})
        self.assertEqual(tools.tool_session.params['factor'], 0.0)

    def test_metric_offset_scale_and_no_accumulation(self):
        self.begin()
        for distance in (.005, .01, -.005, 0.0):
            state = tools.parameter({'parameters':{'slide_distance':distance}})
            self.assertAlmostEqual(self.levels()[0] * self.meters_per_local, distance, places=6)
            self.assertAlmostEqual(state['slide_distance'], distance)
        self.assertEqual(self.levels(), [0.0])

    def test_multiple_cuts_translate_without_compressing_spacing(self):
        self.begin(cuts=3)
        centered = self.levels()
        tools.parameter({'parameters':{'slide_distance':.002}})
        moved = self.levels()
        self.assertEqual(len(moved), 3)
        for before,after in zip(centered,moved):
            self.assertAlmostEqual((after-before)*self.meters_per_local, .002, places=6)

    def test_percent_and_metric_agree_and_center_clears_distance(self):
        self.begin()
        state = tools.parameter({'parameters':{'factor':.5,'even':True}})
        percent = self.coords()
        tools.parameter({'parameters':{'slide_distance':state['slide_distance']}})
        self.assertEqual(self.coords(), percent)
        tools.parameter({'parameters':{'factor':0.0}})
        self.assertNotIn('slide_distance', tools.tool_session.params)
        self.assertEqual(self.levels(), [0.0])

    def test_invalid_distance_restores_valid_preview(self):
        self.begin()
        before = self.coords()
        for value in (1e6, float('nan')):
            with self.assertRaises(CommandError):
                tools.parameter({'parameters':{'slide_distance':value}})
            self.assertEqual(self.coords(), before)

    def test_metric_nudge_and_cancel(self):
        before = self.coords()
        self.begin()
        state = tools.parameter({'parameters':{'slide_distance':.002}})
        result = tools.nudge({'delta':.1})
        self.assertAlmostEqual(result['slide_distance'], .002 + .1*state['slide_range'])
        tools.cancel({})
        self.assertEqual(self.coords(), before)

    def test_circle_undo_retains_cuts_then_next_undo_removes_them(self):
        try:bpy.ops.mesh.looptools_circle.get_rna_type()
        except (AttributeError, RuntimeError, KeyError):self.skipTest('Real LoopTools required')
        bm = bmesh.from_edit_mesh(bpy.context.object.data)
        other = (self.axis+1)%3
        for v in bm.verts:v.co[other]*=2
        bmesh.update_edit_mesh(bpy.context.object.data)
        undo_push('Rectangle baseline')
        baseline = self.coords()
        self.begin(cuts=3)
        tools.confirm({})
        cut = self.coords()
        mesh.looptools_circle({})
        circle = self.coords()
        self.assertNotEqual(cut, circle)
        history.undo({})
        self.assertEqual(self.coords(), cut)
        history.undo({})
        self.assertEqual(self.coords(), baseline)
        history.redo({})
        self.assertEqual(self.coords(), cut)
        history.redo({})
        self.assertEqual(self.coords(), circle)


def run():
    args = sys.argv
    if '--looptools-dir' in args:
        sys.path.insert(0, args[args.index('--looptools-dir')+1])
        import looptools
        looptools.register()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(LoopCutTests))
    if not result.wasSuccessful():
        import os
        os._exit(1)
    bpy.ops.wm.quit_blender()

bpy.app.timers.register(run, first_interval=.5)
