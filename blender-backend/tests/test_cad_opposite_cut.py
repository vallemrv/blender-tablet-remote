"""Opposite and mirrored bores after unions and sloping cuts on a supported tube."""
import copy
import math
import sys
import unittest
from pathlib import Path

import bpy
import bmesh

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.cad.kernel import kernel, ExtrusionPreviewCache
from blender_tablet_remote.cad import mirror
from blender_tablet_remote.errors import CommandError


def solid(typ,params,*,origin=(0,0,0),normal=(0,0,1),x=(1,0,0),y=(0,1,0),depth=.01,symmetric=False):
    entity=dict(id='profile',type=typ,**params)
    sketch=dict(id='sketch',plane='XY',plane_id='plane',
                frame=dict(origin=origin,x=x,y=y,normal=normal),entities=[entity])
    return ExtrusionPreviewCache().extrude(sketch,entity,depth,symmetric=symmetric)


def closed_volume(data):
    bm=bmesh.new()
    try:
        vertices=[bm.verts.new(v) for v in data[0]]
        for face in data[1]: bm.faces.new([vertices[i] for i in face])
        bm.normal_update()
        assert bm.faces and all(e.is_manifold for e in bm.edges)
        return bm.calc_volume()
    finally: bm.free()


class OppositeCutTests(unittest.TestCase):
    def setUp(self):
        self.objects=set(bpy.data.objects.keys()); self.meshes=set(bpy.data.meshes.keys())
        # Two supports of different thickness, joined by a transverse cylinder.
        base=solid('RECTANGLE',dict(x=-.0775,y=.01,width=.07,height=.01),origin=(0,0,.012),depth=.05)
        base=kernel.union(base,solid('RECTANGLE',dict(x=-.076952286,y=-.0185,width=.068904573,height=.0085),
                                     origin=(0,0,.012),depth=.05))
        base=kernel.union(base,solid('CIRCLE',dict(x=-.0425,y=.062,diameter=.05),
                                     normal=(0,-1,0),y=(0,0,1),depth=.03,symmetric=True))
        for points in ([(-.0775,.012),(-.0775,.062),(-.0675,.062)],
                       [(-.0075,.012),(-.0175,.062),(-.0075,.062)]):
            if sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1]))<0:
                points=list(reversed(points))
            base=kernel.cut(base,solid('POLYGON',dict(points=points),origin=(0,-.0185,0),
                                       normal=(0,-1,0),y=(0,0,1),depth=-.05))
        self.cutter=solid('CIRCLE',dict(x=-.0425,y=.062,diameter=.035),origin=(0,-.03,0),
                          normal=(0,-1,0),y=(0,0,1),depth=-.01)
        self.base=kernel.cut(base,self.cutter)

    def tearDown(self):
        self.assertEqual(set(bpy.data.objects.keys()),self.objects)
        self.assertEqual(set(bpy.data.meshes.keys()),self.meshes)

    def assert_removed_bore(self,cutter,radius,depth):
        baseline=copy.deepcopy(self.base); operand=copy.deepcopy(cutter)
        result=kernel.cut(self.base,cutter)
        removed=closed_volume(self.base)-closed_volume(result)
        # Area of the 128-sided evaluated circle; depth is along its plane normal.
        expected=64*radius**2*math.sin(math.tau/128)*depth
        self.assertAlmostEqual(removed,expected,delta=expected*2e-5)
        self.assertEqual(self.base,baseline); self.assertEqual(cutter,operand)

    def test_opposite_face_bore_removes_material_towards_negative_y(self):
        for depth in (.001,.01):
            with self.subTest(depth=depth):
                # A face picked from Blender carries float precision in its origin.
                cutter=solid('CIRCLE',dict(x=.0425,y=.062,diameter=.034),origin=(0,.030000005,0),
                             normal=(0,1,0),x=(-1,0,0),y=(0,0,1),depth=-depth)
                self.assert_removed_bore(cutter,.017,depth)

    def test_mirrored_bore_subtracts_only_the_opposite_operand(self):
        self.assert_removed_bore(mirror.solid(self.cutter,dict(plane='XZ',offset=0.)),.0175,.01)

    def test_miss_and_empty_result_still_reject_without_scene_residue(self):
        outside=solid('RECTANGLE',dict(x=1.,y=1.,width=.1,height=.1),depth=.1)
        covering=solid('RECTANGLE',dict(x=-1.,y=-1.,width=2.,height=2.),origin=(0,0,-1),depth=2.)
        for cutter,code in ((outside,'cad_cut_miss'),(covering,'cad_cut_invalid')):
            with self.subTest(code=code), self.assertRaises(CommandError) as error:
                kernel.cut(self.base,cutter)
            self.assertEqual(error.exception.code,code)


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(OppositeCutTests))
    if not result.wasSuccessful():
        import os
        os._exit(1)
