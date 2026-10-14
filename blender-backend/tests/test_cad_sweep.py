"""Sweep: a closed contour, holes included, follows the line/arc chain of another sketch."""
import math
import sys
import unittest
from pathlib import Path

import bpy
import bmesh
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cad import CadTests, OWNER, volume
from blender_tablet_remote.cad import document as model
from blender_tablet_remote.cad.kernel import sweep_path
from blender_tablet_remote.cad import occt
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.commands import cad
from blender_tablet_remote.errors import CommandError


def tube(outer=.044, inner=.028):
    entities = [dict(id='outer', type='CIRCLE', x=0, y=0, diameter=outer)]
    if inner: entities.append(dict(id='inner', type='CIRCLE', x=0, y=0, diameter=inner))
    return dict(id='profile', plane='XY', offset=0, entities=entities), entities[0]


def elbow(radius=.05):
    # Straight 40 mm up, then a quarter turn of R50 towards +X (Frontal plane).
    return dict(id='path', plane='XZ', offset=0, entities=[
        dict(id='arc', type='ARC', x=radius, y=.04, radius=radius, start=180, sweep=-90),
        dict(id='line', type='LINE', x=0, y=.04, x2=0, y2=0)])


def closed_volume(data):
    bm = bmesh.new()
    try:
        vertices = [bm.verts.new(v) for v in data[0]]
        for face in data[1]: bm.faces.new([vertices[i] for i in face])
        assert all(e.is_manifold for e in bm.edges)
        return bm.calc_volume(signed=True)
    finally: bm.free()


class SweepKernelTests(unittest.TestCase):
    def test_elbow_tube_keeps_its_section_and_ends_at_the_arc(self):
        sketch, source = tube()
        path = sweep_path(elbow())
        self.assertAlmostEqual(path[0][0].z, 0, places=7)   # the chain is ordered end to end
        data = occt.tessellate(occt.sweep(sketch, source, elbow()))
        length = .04 + math.pi/2*.05
        expected = math.pi*(.022**2-.014**2)*length
        self.assertAlmostEqual(closed_volume(data)/expected, 1, delta=.01)
        # The end cap lies on x = 50 mm around (50, 0, 90); the outer wall tops at 40 + 50 + 22.
        self.assertAlmostEqual(max(v[0] for v in data[0]), .05, places=6)
        self.assertAlmostEqual(max(v[2] for v in data[0]), .112, delta=1e-4)

    def test_straight_path_matches_an_extrusion(self):
        sketch, source = tube(.02, None)
        path = dict(id='p', plane='XZ', offset=0, entities=[dict(id='l', type='LINE', x=0, y=0, x2=0, y2=.03)])
        self.assertAlmostEqual(closed_volume(occt.tessellate(occt.sweep(sketch, source, path))), math.pi*.01**2*.03, delta=1e-8)

    def test_invalid_paths_and_profiles_are_rejected(self):
        sketch, source = tube()
        with self.assertRaises(CommandError):   # profile wider than the bend radius
            occt.sweep(sketch, source, elbow(.015))
        branched = elbow(); branched['entities'].append(dict(id='x', type='LINE', x=0, y=.02, x2=.03, y2=.02))
        with self.assertRaises(CommandError):
            sweep_path(branched)
        with self.assertRaises(CommandError):   # profile plane contains the start tangent
            occt.sweep(sketch, source, dict(id='p', plane='XY', offset=0,
                  entities=[dict(id='l', type='LINE', x=0, y=0, x2=.03, y2=0)]))


class SweepCommandTests(CadTests):
    def test_sweep_joins_the_body_follows_its_path_and_protects_the_path_sketch(self):
        circle = self.draw('CIRCLE', (0, 0), (.011, 0))
        profile_sketch = runtime.active_sketch_id
        cad.sketch_finish(OWNER)
        cad.sketch_create(dict(plane='XZ', **OWNER))
        line = self.draw('LINE', (0, 0), (0, .04))
        path_sketch = runtime.active_sketch_id
        cad.sketch_finish(OWNER)
        cad.sweep_create(dict(profile_id='profile_'+circle, path_sketch_id=path_sketch, **OWNER))
        feature = runtime.doc()['features'][-1]
        self.assertEqual((feature['type'], feature['path_sketch_id']), ('SWEEP', path_sketch))
        self.assertAlmostEqual(volume(self.obj()), math.pi*.011**2*.04, delta=2e-8)
        model.loads(model.dumps(runtime.doc()))
        self.assertFalse(model.sketch_visible(runtime.doc(), model.find(runtime.doc(), 'sketches', path_sketch)))
        with self.assertRaises(CommandError):
            cad.sketch_delete(dict(sketch_id=path_sketch, **OWNER))
        with self.assertRaises(CommandError):
            cad.sweep_create(dict(profile_id='profile_'+circle, path_sketch_id=profile_sketch, **OWNER))

    def test_whole_ring_sketch_sweeps_its_outer_contour_with_the_hole(self):
        self.draw('CIRCLE', (0, 0), (.022, 0)); self.draw('CIRCLE', (0, 0), (.014, 0))
        ring = runtime.active_sketch_id
        cad.sketch_finish(OWNER)
        cad.sketch_create(dict(plane='XZ', **OWNER))
        self.draw('LINE', (0, 0), (0, .04))
        path = runtime.active_sketch_id
        cad.sketch_finish(OWNER)
        cad.sweep_create(dict(sketch_id=ring, path_sketch_id=path, **OWNER))
        self.assertAlmostEqual(volume(self.obj()), math.pi*(.022**2-.014**2)*.04, delta=5e-8)

    def test_tube_meets_a_flange_in_one_circular_edge_that_takes_a_fillet(self):
        from blender_tablet_remote.commands.snap import _cad_mesh
        flange = self.draw('CIRCLE', (0, 0), (.04, 0))
        self.extrude(flange, .007)
        cad.sketch_create(dict(plane='XY', **OWNER))
        self.draw('CIRCLE', (0, 0), (.022, 0)); self.draw('CIRCLE', (0, 0), (.014, 0))
        ring = runtime.active_sketch_id
        cad.sketch_finish(OWNER)
        cad.sketch_create(dict(plane='XZ', **OWNER))
        self.draw('LINE', (0, 0), (0, .04))
        path = runtime.active_sketch_id
        cad.sketch_finish(OWNER)
        cad.sweep_create(dict(sketch_id=ring, path_sketch_id=path, **OWNER))
        obj = self.obj(); scale = bpy.context.scene.unit_settings.scale_length
        points, edge_regions = _cad_mesh(obj)[1], _cad_mesh(obj)[8]
        on_ring = lambda e: all(abs(points[i].z*scale-.007) < 1e-6 and abs(math.hypot(points[i].x, points[i].y)*scale-.022) < 1e-5 for i in e)
        regions = {id(edge_regions[e]): edge_regions[e] for e in edge_regions if on_ring(e)}
        self.assertEqual(len(regions), 1)   # one design edge, not its tessellation
        edge = [[list(points[a]*scale), list(points[b]*scale)] for a, b in next(iter(regions.values()))]
        solid = runtime.doc()['features'][-1]['id']
        from blender_tablet_remote.cad import occt
        occt.evaluator.evaluate(runtime.doc(), scale=1.)
        shape = occt.evaluator._shapes[solid][1]
        added = (occt._volume(occt.finish_edges(shape, [edge], .004, 4))-occt._volume(shape))/occt.MM**3
        self.assertAlmostEqual(added/((1-math.pi/4)*.004**2*2*math.pi*.0233), 1, delta=.12)
        with self.assertRaises(CommandError): occt.finish_edges(shape, [edge], .03, 4)



if __name__ == '__main__':
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(case)
                               for case in (SweepKernelTests, SweepCommandTests))
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
        raise SystemExit(1)
