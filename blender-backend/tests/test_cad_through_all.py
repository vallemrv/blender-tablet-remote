"""Through-all pockets follow the body, with reversible previews and no blind cap."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_cad import CadTests, OWNER, volume
from blender_tablet_remote.cad import document as model, design_surfaces
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.commands import cad
from blender_tablet_remote.errors import CommandError


class ThroughAllTests(CadTests):
    def prepare(self, offset=.02, plane='XY'):
        if plane!='XY': cad.sketch_create(dict(plane=plane,**OWNER))
        base=self.extrude(self.rect(),depth=.02)
        cad.sketch_create(dict(plane=plane,offset=offset,**OWNER))
        profile=self.draw('RECTANGLE',(.01,.01),(.02,.025))
        return base,profile

    def begin(self, target, profile, extent='THROUGH_ALL'):
        return cad.extrude_begin(dict(operation='CUT',target_id=target,profile_id='profile_'+profile,
                                      depth=.002,extent=extent,**OWNER))

    def test_preview_ghost_cancel_and_confirm_keep_one_undo(self):
        base,profile=self.prepare()
        before=bpy.context.scene[model.KEY]
        state=self.begin(base,profile,extent='ONE')
        self.assertAlmostEqual(volume(self.obj()),.08*.045*.02-.01*.015*.002,places=9)
        state=cad.extrude_update(dict(extent='THROUGH_ALL',**OWNER))
        self.assertEqual(state['session']['extent'],'THROUGH_ALL')
        self.assertTrue(state['session']['can_confirm'])
        self.assertAlmostEqual(volume(self.obj()),(.08*.045-.01*.015)*.02,places=9)
        ghost=runtime.cut_ghost()
        self.assertLess(min(v[2] for v in ghost['triangles']),0)
        self.assertGreater(max(v[2] for v in ghost['triangles']),.02)
        self.assertIs(runtime.cut_ghost(),ghost)
        with patch.object(runtime,'fast_depth',side_effect=AssertionError('Automatic cut must not drag')):
            cad.extrude_update(dict(gesture_u=.1,gesture_v=.2,baseline_depth=.002,**OWNER))
            cad.extrude_update(dict(settle=True,**OWNER))
        self.assertEqual(runtime.session['extent'],'THROUGH_ALL')
        self.assertEqual(runtime.session['depth'],.002)
        cad.cancel(OWNER)
        self.assertEqual(bpy.context.scene[model.KEY],before)
        self.assertAlmostEqual(volume(self.obj()),.08*.045*.02,places=9)
        self.begin(base,profile)
        with patch.object(cad,'undo_push') as undo:
            cad.confirm(OWNER)
            undo.assert_called_once()
        self.assertIsNone(runtime.cut_ghost())
        self.assertEqual(runtime.doc()['features'][-1]['extent'],'THROUGH_ALL')

    def test_through_cut_recomputes_after_body_depth_change_and_reload(self):
        base,profile=self.prepare(offset=.01)
        self.begin(base,profile); cad.confirm(OWNER)
        cut=runtime.doc()['features'][-1]['id']
        for thickness in (.07,.004,.03):
            cad.feature_set(dict(feature_id=base,depth=thickness,**OWNER))
            self.assertAlmostEqual(volume(self.obj()),(.08*.045-.01*.015)*thickness,places=9)
            doc=model.loads(model.dumps(runtime.doc()))
            runtime.rebuild(doc)
            self.assertEqual(model.find(doc,'features',cut)['extent'],'THROUGH_ALL')
            self.assertAlmostEqual(volume(self.obj()),(.08*.045-.01*.015)*thickness,places=9)
        cad.feature_set(dict(feature_id=cut,enabled=False,**OWNER))
        self.assertAlmostEqual(volume(self.obj()),.08*.045*.03,places=9)
        cad.feature_set(dict(feature_id=cut,enabled=True,**OWNER))
        self.assertAlmostEqual(volume(self.obj()),(.08*.045-.01*.015)*.03,places=9)

    def test_cut_is_independent_of_sketch_side_and_plane(self):
        for plane,offset in (('XY',-.03),('XZ',.01),('YZ',.1)):
            with self.subTest(plane=plane,offset=offset):
                self.setUp()
                base,profile=self.prepare(offset,plane)
                self.begin(base,profile); cad.confirm(OWNER)
                self.assertAlmostEqual(volume(self.obj()),(.08*.045-.01*.015)*.02,places=9)

    def test_existing_cut_can_switch_modes_and_explicit_depth_restores_blind_cut(self):
        base,profile=self.prepare()
        self.begin(base,profile,extent='ONE'); cad.confirm(OWNER)
        cut=runtime.doc()['features'][-1]['id']
        cad.feature_set(dict(feature_id=cut,extent='THROUGH_ALL',**OWNER))
        self.assertAlmostEqual(volume(self.obj()),(.08*.045-.01*.015)*.02,places=9)
        cad.feature_set(dict(feature_id=cut,depth=.005,**OWNER))
        self.assertEqual(runtime.doc()['features'][-1]['extent'],'ONE')
        self.assertAlmostEqual(volume(self.obj()),.08*.045*.02-.01*.015*.005,places=9)
        self.begin(cut,profile)
        cad.extrude_update(dict(depth=.01,**OWNER))
        self.assertEqual(runtime.session['extent'],'ONE')
        self.assertAlmostEqual(volume(self.obj()),.08*.045*.02-.01*.015*.01,places=9)
        cad.cancel(OWNER)

    def test_whole_sketch_regions_and_holes_are_respected(self):
        base,profile=self.prepare()
        self.draw('RECTANGLE',(.04,.01),(.05,.025))
        self.draw('RECTANGLE',(.012,.012),(.018,.02))
        sketch=runtime.active_sketch_id
        cad.extrude_begin(dict(operation='CUT',target_id=base,sketch_id=sketch,depth=.002,extent='THROUGH_ALL',**OWNER))
        cad.confirm(OWNER)
        expected=(.08*.045-2*.01*.015+.006*.008)*.02
        self.assertAlmostEqual(volume(self.obj()),expected,places=9)

    def test_through_cut_uses_the_accumulated_body_and_mirror_inherits_it(self):
        base=self.extrude(self.rect(),depth=.02)
        cad.sketch_create(dict(plane='XY',offset=.02,**OWNER))
        top=self.draw('RECTANGLE',(0,0),(.08,.045))
        self.extrude(top,depth=.04)
        cad.sketch_create(dict(plane='XY',offset=.02,**OWNER))
        profile=self.draw('RECTANGLE',(.01,.01),(.02,.025))
        # An older target ID still refers to the current accumulated body.
        self.begin(base,profile); cad.confirm(OWNER)
        cut=runtime.doc()['features'][-1]['id']
        self.assertAlmostEqual(volume(self.obj()),(.08*.045-.01*.015)*.06,places=9)
        cad.feature_mirror(dict(feature_id=cut,plane='YZ',offset=.04,**OWNER))
        self.assertEqual(runtime.doc()['features'][-1]['extent'],'THROUGH_ALL')
        self.assertAlmostEqual(volume(self.obj()),(.08*.045-2*.01*.015)*.06,places=9)

    @unittest.skipIf(bpy.app.background,'GUI undo stack required')
    def test_one_native_undo_and_redo_restore_the_through_operation(self):
        from blender_tablet_remote.commands import history
        base,profile=self.prepare()
        self.begin(base,profile); cad.confirm(OWNER)
        history.undo({})
        self.assertEqual([f['id'] for f in runtime.doc()['features']],[base])
        self.assertAlmostEqual(volume(self.obj()),.08*.045*.02,places=9)
        history.redo({})
        self.assertEqual(runtime.doc()['features'][-1]['extent'],'THROUGH_ALL')
        self.assertAlmostEqual(volume(self.obj()),(.08*.045-.01*.015)*.02,places=9)

    def test_rejects_extrusion_atomically_and_adds_no_spurious_cap_surface(self):
        base,profile=self.prepare()
        before=model.dumps(runtime.doc())
        with self.assertRaises(CommandError):
            cad.extrude_begin(dict(profile_id='profile_'+profile,extent='THROUGH_ALL',**OWNER))
        self.assertIsNone(runtime.session)
        with self.assertRaises(CommandError): cad.feature_set(dict(feature_id=base,extent='THROUGH_ALL',**OWNER))
        self.assertEqual(model.dumps(runtime.doc()),before)
        self.begin(base,profile); cad.confirm(OWNER)
        doc=runtime.doc(); cut=doc['features'][-1]
        # Isolate cut descriptors: its walls exist but neither blind cap is invented.
        isolated=copy.deepcopy(doc)
        for f in isolated['features'][:-1]: f['enabled']=False
        surfaces=design_surfaces.surfaces(isolated,cut['body_id'],1.)
        self.assertTrue(surfaces)
        self.assertTrue(all(s[0]!='PLANE' or abs(s[1].z)<1e-7 for s in surfaces))
        invalid=copy.deepcopy(doc); invalid['features'][0]['extent']='THROUGH_ALL'
        with self.assertRaises(CommandError): model.loads(model.dumps(invalid))


def run():
    suite=unittest.TestSuite(ThroughAllTests(n) for n in ThroughAllTests.__dict__ if n.startswith('test_'))
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
        import os
        os._exit(1)
    if not bpy.app.background: bpy.ops.wm.quit_blender()


if __name__=='__main__':
    if bpy.app.background: run()
    else: bpy.app.timers.register(run,first_interval=1.)
