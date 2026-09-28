"""CAD irregular polygon tool: stroke chain, auto-close, cancel and single undo."""
import sys
import unittest
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_cad import CadTests, OWNER, volume
from unittest.mock import patch
from blender_tablet_remote.cad import document as model, sketch as geometry
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.commands import cad, history
from blender_tablet_remote.errors import BadPayload, CommandError


class PolygonTests(CadTests):
    def stroke(self,a,b):
        """One pointer stroke: begin, preview, release at b. Snapping patched out."""
        with patch.object(runtime,'point',return_value=a),patch.object(cad,'_endpoint',return_value=None):
            cad.polygon_begin(dict(u=.1,v=.1,**OWNER))
        with patch.object(runtime,'point',return_value=b),patch.object(cad,'_preview_endpoint',return_value=None):
            cad.polygon_update(dict(u=.5,v=.5,**OWNER))
        return cad.polygon_segment(dict(u=.5,v=.5,**OWNER))

    def test_two_sides_enable_close_immediately_without_a_third_stroke(self):
        first=self.stroke((0,0),(.08,0))
        self.assertFalse(first['session']['can_close'])
        second=self.stroke((.08,0),(.04,.04))
        self.assertTrue(second['session']['can_close'])
        visible=second['document']['sketches'][0]['entities']
        self.assertEqual(len(visible),2)
        self.assertEqual(visible[-1]['id'],second['selection']['id'])
        with patch.object(runtime,'point',side_effect=AssertionError('Close must not probe another point')):
            closed=cad.polygon_close(OWNER)
        self.assertFalse(closed['session']['active'])
        sides=closed['document']['sketches'][0]['entities']
        self.assertEqual(len(sides),3)
        self.assertEqual((sides[-1]['x'],sides[-1]['y']),(.04,.04))
        self.assertEqual((sides[-1]['x2'],sides[-1]['y2']),(0,0))

    def test_close_builds_joined_profile_and_single_undo(self):
        self.stroke((0,0),(.08,0))
        self.stroke((.08,0),(.08,.045))
        status=cad.polygon_close(OWNER)
        sketch=runtime.doc()['sketches'][0]
        self.assertEqual(len(sketch['entities']),3)
        self.assertEqual(len(sketch['constraints']),3)  # two joins and the closing corner
        self.assertEqual(status['selection']['kind'],'PROFILE')
        self.assertTrue(runtime.active_sketch_id)  # the sketch view is kept
        self.assertEqual(len(runtime.objects(runtime.doc())),0)  # nothing extruded yet
        f=self.extrude(status['selection']['id'].removeprefix('profile_'),.02)
        self.assertAlmostEqual(volume(self.obj()),.5*.08*.045*.02,places=9)

    def test_closed_corner_moves_as_one_point_and_keeps_the_profile(self):
        from blender_tablet_remote.cad import sketch as geometry
        self.stroke((0,0),(.08,0))
        self.stroke((.08,0),(.08,.045))
        cad.polygon_close(OWNER)
        sketch=runtime.doc()['sketches'][0]
        first=sketch['entities'][0]['id']
        geometry.solve(sketch,geometry.move_goals(sketch,[dict(kind='ENTITY',id=first,part='START')],.01,.01),drag=True)
        last=sketch['entities'][-1]
        self.assertAlmostEqual(last['x2'],.01); self.assertAlmostEqual(last['y2'],.01)
        self.assertEqual(len(model.profiles(sketch)),1)

    def test_tapping_a_closed_polygon_side_selects_only_that_side_for_constraints(self):
        self.stroke((0,0),(.08,.01))
        self.stroke((.08,.01),(.07,.06))
        closed=cad.polygon_close(OWNER)
        self.assertEqual(closed['selection']['kind'],'PROFILE')
        sides=runtime.doc()['sketches'][0]['entities']
        for index,typ,axis in ((0,'HORIZONTAL','y'),(1,'VERTICAL','x')):
            if index: cad.select_all(dict(action='DESELECT',**OWNER))
            hit=dict(kind='ENTITY',id=sides[index]['id'],part='BODY')
            baseline=model.dumps(runtime.doc())
            with patch.object(cad,'_pick',return_value=hit),patch.object(runtime,'point',return_value=(.04,.02)):
                cad.drag_begin(dict(u=.5,v=.5,**OWNER))
            with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
                status=cad.drag_end(OWNER)
                undo.assert_not_called()
            self.assertEqual(status['selection']['items'],[hit])
            self.assertEqual(model.dumps(runtime.doc()),baseline)
            with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
                cad.constraint_add(dict(type=typ,**OWNER))
                undo.assert_called_once()
            sketch=runtime.doc()['sketches'][0]
            side=model.find(sketch,'entities',hit['id'])
            self.assertAlmostEqual(side[axis],side[axis+'2'],places=8)
            self.assertEqual(len(model.profiles(sketch)),1)

    def test_regular_polygon_side_accepts_horizontal_and_vertical(self):
        for typ,axis in (('HORIZONTAL',1),('VERTICAL',0)):
            cad.sketch_create(dict(plane='XY',**OWNER))
            identifier=self.draw('NGON',(0,0),(.04,.01))
            hit=dict(kind='ENTITY',id=identifier,part='EDGE4')
            cad._set_selection([hit])
            cad.constraint_add(dict(type=typ,**OWNER))
            sketch,polygon=model.entity(runtime.doc(),identifier)
            a,b=geometry.line(sketch,hit)
            self.assertAlmostEqual(a[axis],b[axis],places=8)
            self.assertEqual(polygon['sides'],6)
            self.assertEqual(len(model.profiles(sketch)),1)

    def test_tapping_the_first_vertex_closes_automatically(self):
        self.stroke((0,0),(.08,0))
        self.stroke((.08,0),(.04,.04))
        status=self.stroke((.04,.04),(0,0))
        self.assertEqual(status['selection']['kind'],'PROFILE')
        self.assertEqual(len(runtime.doc()['sketches'][0]['entities']),3)
        self.assertFalse(runtime.session)

    def test_cancel_discards_the_whole_chain(self):
        self.stroke((0,0),(.08,0))
        self.stroke((.08,0),(.04,.04))
        cad.cancel(dict(**OWNER))
        self.assertFalse(runtime.doc()['sketches'][0]['entities'])
        self.assertFalse(runtime.session)

    def test_two_vertices_cannot_close_but_three_points_close_button_works(self):
        self.stroke((0,0),(.08,0))
        status=self.stroke((.08,0),(0,0))  # tapping the start with 2 points: ignored
        self.assertEqual(len(runtime.session['segments']),1)
        self.assertTrue(runtime.session)
        with self.assertRaises(BadPayload): cad.polygon_close(OWNER)
        self.stroke((.08,0),(.08,.045))
        cad.polygon_close(OWNER)
        self.assertEqual(len(runtime.doc()['sketches'][0]['entities']),3)

    def test_tap_on_last_vertex_commits_nothing(self):
        self.stroke((0,0),(.08,0))
        status=self.stroke((.08,0),(.08,0))
        self.assertEqual(len(runtime.session['segments']),1)
        self.assertEqual(len(runtime.doc()['sketches'][0]['entities']),0)  # still only in session
        self.assertTrue(runtime.session)

    def test_construction_chain_makes_no_profile_and_selects_last_segment(self):
        cad.settings(dict(construction=True,**OWNER))
        self.stroke((0,0),(.08,0))
        self.stroke((.08,0),(.08,.045))
        cad.polygon_close(OWNER)
        sketch=runtime.doc()['sketches'][0]
        self.assertEqual(len(sketch['entities']),3)
        self.assertEqual(model.profiles(sketch),[])
        self.assertEqual(runtime.selection['kind'],'ENTITY')

    @unittest.skipIf(bpy.app.background,'GUI undo stack required')
    def test_polygon_close_is_a_single_undo_step(self):
        self.stroke((0,0),(.08,0))
        self.stroke((.08,0),(.08,.045))
        cad.polygon_close(OWNER)
        self.assertEqual(len(runtime.doc()['sketches'][0]['entities']),3)
        history.undo({})
        self.assertEqual(len(runtime.doc()['sketches'][0]['entities']),0)


def run():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PolygonTests))
    if not result.wasSuccessful():
        import os
        os._exit(1)
    if not bpy.app.background: bpy.ops.wm.quit_blender()

if __name__=='__main__':
    if bpy.app.background: run()
    else: bpy.app.timers.register(run,first_interval=1.)
