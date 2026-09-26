"""Cold CAD selection must group contours without repeatedly scanning the solid."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cad import CadTests, OWNER
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.commands import cad, snap


class SelectionEfficiencyTests(CadTests):
    def plate(self):
        outer = self.draw('RECTANGLE', (0, 0), (.27, .15))
        for x, y in ((.04, .03), (.04, .12), (.23, .03), (.23, .12)):
            self.draw('CIRCLE', (x, y), (x + .01, y))
        self.extrude(outer)
        return self.obj()

    def test_first_selection_of_four_holes_keeps_design_regions_with_bounded_work(self):
        obj = self.plate()
        with patch.object(snap, '_straight_boundary', wraps=snap._straight_boundary) as boundary:
            graph = snap._cad_mesh(obj)
        self.assertLessEqual(boundary.call_count, 2 * len(graph[6]))
        self.assertEqual(len(set(graph[7])), 10)  # Six plate faces plus four hole walls.
        self.assertEqual(len(set(graph[8].values())), 20)  # Twelve straight edges, eight rings.
        self.assertEqual(len(snap._cad_corners(graph[8])), 8)
        for edge, region in graph[8].items():
            self.assertTrue(all(graph[8][member] is region for member in region))
        with patch.object(snap, '_cad_topology', side_effect=AssertionError('Repeated topology')):
            for kind in ('FACE', 'EDGE', 'VERTEX'):
                cad.surface_mode(dict(mode=kind, **OWNER))
                self.assertIs(snap._cad_mesh(obj), graph)

    def test_tangent_lines_and_arcs_of_the_sketch_stay_separate_faces_edges_and_points(self):
        with patch.object(cad, '_endpoint', return_value=None):
            slot = self.draw_unsnapped('SLOT', (0, 0), (.04, 0))
        self.extrude(slot)
        graph = snap._cad_mesh(self.obj())
        # Top, bottom, two flat sides and two half cylinders.
        self.assertEqual(len(set(graph[7])), 6)
        # Each cap: two lines and two arcs; plus four tangent seams on the sides.
        self.assertEqual(len(set(graph[8].values())), 12)
        self.assertEqual(len(snap._cad_corners(graph[8])), 8)

    def test_more_circle_samples_do_not_multiply_global_contour_passes(self):
        for samples in (128, 512):
            with self.subTest(samples=samples):
                bpy.ops.mesh.primitive_cylinder_add(vertices=samples, radius=.01, depth=.02)
                obj = bpy.context.object
                obj['btr_cad_feature_id'] = 'test-cylinder'
                with patch.object(snap, '_straight_boundary', wraps=snap._straight_boundary) as boundary:
                    graph = snap._cad_mesh(obj)
                self.assertLessEqual(boundary.call_count, 4 * samples)
                self.assertEqual(len(set(graph[7])), 3)
                self.assertEqual({len(region) for region in graph[8].values()}, {samples})
                self.assertEqual(len(set(graph[8].values())), 2)
                self.assertEqual(snap._cad_corners(graph[8]), [])

    def test_straight_split_edges_keep_sharp_corners_and_separate_regions(self):
        points = [Vector(p) for p in ((0, 0, 0), (1, 0, 0), (2, 0, 0),
                                     (2, 1, 0), (1, 1, 0), (0, 1, 0))]
        regions = [frozenset(((0, 1), (1, 2))), frozenset(((2, 3),)),
                   frozenset(((3, 4), (4, 5))), frozenset(((0, 5),))]
        edges = {edge: region for region in regions for edge in region}
        incident = {}
        for edge in edges:
            for vertex in edge:
                incident.setdefault(vertex, []).append(edge)
        snap._merge_smooth_contours(points, incident, edges)
        self.assertEqual(set(edges.values()), set(regions))
        self.assertEqual(snap._cad_corners(edges), [0, 2, 3, 5])


def run():
    suite = unittest.TestSuite(SelectionEfficiencyTests(name)
                              for name in SelectionEfficiencyTests.__dict__ if name.startswith('test_'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == '__main__':
    run()
