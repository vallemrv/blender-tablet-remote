"""Whole-sketch selection and extrusion, with holes and disconnected regions."""
import math
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cad import CadTests, OWNER, volume
from blender_tablet_remote.cad import document as model
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.commands import cad
from blender_tablet_remote.errors import CommandError


class WholeSketchTests(CadTests):
    def begin_whole(self, **values):
        return cad.extrude_begin(dict(sketch_id=runtime.doc()['sketches'][-1]['id'], depth=.02, **values, **OWNER))

    def test_finish_selects_whole_plate_instead_of_last_hole(self):
        self.rect()
        for x,y in ((.02,.01),(.06,.01),(.02,.035),(.06,.035)):
            self.draw('CIRCLE',(x,y),(x+.003,y))
        sketch=runtime.active_sketch_id
        before=model.dumps(runtime.doc())
        state=cad.sketch_finish(OWNER)
        self.assertEqual(state['selection'], dict(kind='SKETCH',id=sketch))
        self.assertEqual(model.dumps(runtime.doc()),before)
        self.begin_whole()
        with patch('blender_tablet_remote.commands.cad.undo_push') as undo:
            cad.confirm(OWNER);undo.assert_called_once()
        self.assertEqual(len(runtime.doc()['features']),1)
        self.assertAlmostEqual(volume(self.obj()),(.08*.045-4*math.pi*.003**2)*.02,delta=1e-9)

    def test_disconnected_regions_extrude_together_and_rebuild_from_sketch(self):
        self.rect()
        second=self.draw('RECTANGLE',(.1,0),(.13,.03))
        hole=self.draw('CIRCLE',(.115,.015),(.118,.015))
        cad.sketch_finish(OWNER)
        self.begin_whole()
        cad.extrude_update(dict(depth=.04,**OWNER))
        cad.confirm(OWNER)
        self.assertEqual(len(runtime.objects(runtime.doc())),1)
        expected=(.08*.045+.03*.03-math.pi*.003**2)*.04
        self.assertAlmostEqual(volume(self.obj()),expected,delta=1e-9)
        cad.entity_set(dict(entity_id=second,values={'width':.04},**OWNER))
        rebuilt=model.loads(model.dumps(runtime.doc()))
        runtime.rebuild(rebuilt)
        expected=(.08*.045+.04*.03-math.pi*.003**2)*.04
        self.assertAlmostEqual(volume(self.obj()),expected,delta=1e-9)
        self.assertEqual(rebuilt['features'][0]['profile_id'],'profile_'+rebuilt['sketches'][0]['id'])

    def test_whole_sketch_requires_closed_geometry_but_ignores_construction(self):
        self.rect(); line=self.draw('LINE',(.1,0),(.12,.02))
        cad.sketch_finish(OWNER)
        before=model.dumps(runtime.doc())
        with self.assertRaisesRegex(CommandError,'abierta'): self.begin_whole()
        self.assertEqual(model.dumps(runtime.doc()),before)
        self.assertIsNone(runtime.session)
        doc=runtime.doc(); model.entity(doc,line)[1]['construction']=True
        runtime.persist(doc)
        self.begin_whole(); cad.confirm(OWNER)
        self.assertAlmostEqual(volume(self.obj()),.08*.045*.02,places=10)

    def test_select_all_edits_entities_in_sketch_and_selects_whole_in_3d(self):
        self.rect();self.draw('CIRCLE',(.02,.02),(.025,.02))
        sketch=runtime.active_sketch_id
        state=cad.select_all(dict(action='SELECT',**OWNER))
        self.assertEqual(len(state['selection']['items']),2)
        self.assertEqual(state['selection']['kind'],'ENTITY')
        cad.sketch_finish(OWNER)
        state=cad.select_all(dict(action='DESELECT',**OWNER))
        self.assertIsNone(state['selection'])
        state=cad.select_all(dict(action='SELECT',sketch_id=sketch,**OWNER))
        self.assertEqual(state['selection']['kind'],'SKETCH')
        self.assertEqual(state['selection']['id'],sketch)

    def test_separate_cut_profiles_remove_material_in_one_feature(self):
        target=self.extrude(self.rect())
        cad.sketch_create(dict(support_id=target,**OWNER))
        for x in (.02,.06): self.draw('CIRCLE',(x,.02),(x+.003,.02))
        cad.sketch_finish(OWNER)
        self.begin_whole(operation='CUT',target_id=target)
        cad.confirm(OWNER)
        visible=[o for o in runtime.objects(runtime.doc()) if o.visible_get()]
        self.assertEqual(len(visible),1)
        self.assertEqual(len(runtime.doc()['features']),2)
        self.assertAlmostEqual(volume(visible[0]),(.08*.045-2*math.pi*.003**2)*.02,delta=1e-9)

    def test_overlapping_regions_are_rejected_atomically(self):
        self.rect(); self.draw('RECTANGLE',(.04,.02),(.12,.06))
        cad.sketch_finish(OWNER)
        before=model.dumps(runtime.doc())
        with self.assertRaises(CommandError): self.begin_whole()
        self.assertEqual(model.dumps(runtime.doc()),before)
        self.assertFalse(runtime.objects(runtime.doc()))
        self.assertIsNone(runtime.session)

    @unittest.skipIf(bpy.app.background, 'GUI undo and overlay required')
    def test_whole_sketch_overlay_and_single_native_undo(self):
        from blender_tablet_remote.commands import history
        self.rect(); self.draw('CIRCLE',(.02,.02),(.023,.02))
        state=cad.sketch_finish(OWNER)
        self.assertEqual(len(state['overlay']),2)
        self.assertTrue(all(item['selected'] for item in state['overlay']))
        self.begin_whole();cad.extrude_update(dict(depth=.03,**OWNER));cad.confirm(OWNER)
        expected=volume(self.obj())
        history.undo({})
        self.assertFalse(runtime.doc()['features'])
        self.assertFalse(runtime.objects(runtime.doc()))
        history.redo({})
        self.assertEqual(len(runtime.doc()['features']),1)
        self.assertAlmostEqual(volume(self.obj()),expected,places=10)


def run():
    suite=unittest.TestSuite(WholeSketchTests(name) for name in WholeSketchTests.__dict__ if name.startswith('test_'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        import os
        os._exit(1)
    if not bpy.app.background: bpy.ops.wm.quit_blender()

if __name__ == '__main__':
    if bpy.app.background: run()
    else: bpy.app.timers.register(run,first_interval=1.)
