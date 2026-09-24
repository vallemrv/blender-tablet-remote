"""CAD edge finishes: fillet/chamfer several solid edges as one body operation."""
import math
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_cad import CadTests, OWNER, volume
from blender_tablet_remote.cad import document as model
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.commands import cad
from blender_tablet_remote.errors import BadPayload, CommandError


class FinishTests(CadTests):
    def box(self):
        """80 × 45 × 20 mm block."""
        return self.extrude(self.rect(),.02)

    def select_edges(self,*segments):
        obj=self.obj()
        runtime.surface.clear()
        for index,(a,b) in enumerate(segments):
            runtime.surface.items.append(dict(id=obj.name+':EDGE:'+str(index),kind='EDGE',object=obj.name,feature_id=None,
                                              planar=False,segments=[[list(a),list(b)]],points=[list(a),list(b)]))
        runtime.surface._stamps[obj.name]=__import__('blender_tablet_remote.cad.surface',fromlist=['stamp']).stamp(obj)

    def test_chamfer_two_edges_removes_exact_prisms_in_one_undo(self):
        self.box(); base=volume(self.obj())
        self.select_edges(((0,0,.02),(.08,0,.02)),((0,.045,.02),(.08,.045,.02)))
        status=cad.finish_begin(dict(operation='CHAMFER',width=.003,**OWNER))
        self.assertEqual(status['session']['operation'],'CHAMFER')
        with patch('blender_tablet_remote.commands.cad.undo_push') as undo:
            cad.confirm(OWNER)
        undo.assert_called_once()
        self.assertAlmostEqual(base-volume(self.obj()),2*.5*.003**2*.08,places=10)
        feature=runtime.doc()['features'][-1]
        self.assertEqual((feature['type'],feature['segments'],len(feature['edges'])),('CHAMFER',1,2))
        from blender_tablet_remote.cad.runtime import mesh_copy
        self.assertTrue(all(len(p.vertices)==4 for p in mesh_copy(self.obj()).data.polygons))

    def test_fillet_follows_a_deeper_extrusion_and_width_edits(self):
        feature=self.box()
        self.select_edges(((0,0,0),(0,0,.02)))
        cad.finish_begin(dict(operation='FILLET',width=.004,segments=8,**OWNER))
        cad.finish_update(dict(width=.005,**OWNER))
        cad.confirm(OWNER)
        loss=lambda depth:(1-math.pi/4)*.005**2*depth
        self.assertAlmostEqual(.08*.045*.02-volume(self.obj()),loss(.02),delta=loss(.02)*.03)
        cad.feature_set(dict(feature_id=feature,depth=.03,**OWNER))  # the vertical edge grows and keeps its fillet
        self.assertAlmostEqual(.08*.045*.03-volume(self.obj()),loss(.03),delta=loss(.03)*.03)

    def test_cancel_restores_the_solid_and_validation_rejects_bad_input(self):
        self.box(); base=volume(self.obj())
        self.select_edges(((0,0,.02),(.08,0,.02)))
        cad.finish_begin(dict(operation='FILLET',width=.004,**OWNER))
        self.assertLess(volume(self.obj()),base)
        cad.cancel(OWNER)
        self.assertAlmostEqual(volume(self.obj()),base,places=12)
        self.assertFalse(any(f['type'] in model.FINISHES for f in runtime.doc()['features']))
        runtime.surface.clear()
        with self.assertRaises(BadPayload): cad.finish_begin(dict(operation='FILLET',**OWNER))
        self.select_edges(((0,0,.02),(.08,0,.02)))
        with self.assertRaises(BadPayload): cad.finish_begin(dict(operation='FILLET',segments=0,**OWNER))

    @unittest.skipIf(bpy.app.background,'Real viewport projection required')
    def test_tapping_edges_accumulates_them_and_fillets_every_one(self):
        from mathutils import Quaternion, Vector
        from blender_tablet_remote.bpy_utils import find_view3d
        from blender_tablet_remote.camera import camera
        self.box(); base=volume(self.obj())
        camera.apply(location=(.04,.0225,.01),rotation=Quaternion((1,0,0),math.radians(55)),distance=.3,perspective='ORTHO')
        cad.surface_mode(dict(mode='EDGE',**OWNER))
        for point in ((.04,0,.02),(.04,0,0),(0,.0225,.02)):
            screen=camera.project(Vector(point),find_view3d()[3])
            cad.surface_select(dict(u=screen[0],v=screen[1],**OWNER))
        self.assertEqual(len(runtime.surface.items),3)
        cad.finish_begin(dict(operation='FILLET',width=.002,segments=4,**OWNER)); cad.confirm(OWNER)
        self.assertLess(volume(self.obj()),base)
        self.assertEqual(len(runtime.doc()['features'][-1]['edges']),3)

    def test_operations_continue_after_a_fillet(self):
        feature=self.box()
        self.select_edges(((0,0,.02),(.08,0,.02)))
        cad.finish_begin(dict(operation='FILLET',width=.003,**OWNER)); cad.confirm(OWNER)
        before=volume(self.obj())
        cad.sketch_create(dict(support_id=feature,**OWNER))
        hole=self.draw('CIRCLE',(.04,.0225),(.05,.0225))
        cad.extrude_begin(dict(profile_id='profile_'+hole,operation='CUT',target_id=runtime.doc()['features'][-1]['id'],depth=.03,**OWNER))
        cad.confirm(OWNER)
        self.assertAlmostEqual(before-volume(self.obj()),math.pi*.01**2*.02,delta=2e-8)

    def test_a_vanished_edge_is_an_explicit_error(self):
        self.box()
        self.select_edges(((.2,.2,.2),(.3,.2,.2)))
        with self.assertRaises(CommandError): cad.finish_begin(dict(operation='FILLET',width=.002,**OWNER))
        self.assertIsNone(runtime.session)


def run():
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(FinishTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        import os
        os._exit(1)
    if not bpy.app.background: bpy.ops.wm.quit_blender()


if __name__=='__main__':
    if bpy.app.background: run()
    else: bpy.app.timers.register(run,first_interval=1.)
