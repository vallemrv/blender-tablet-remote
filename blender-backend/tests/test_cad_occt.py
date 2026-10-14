"""Required OpenCascade kernel and clear installation failures, with no fallback."""
import copy
import json
import math
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import bmesh
from mathutils.bvhtree import BVHTree
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.cad import document as model, occt
from blender_tablet_remote.errors import CommandError

occt.load()
ELBOW = json.loads((Path(__file__).parent/'fixtures'/'cad_elbow.json').read_text())
INDIVIDUAL = model.loads((Path(__file__).parent/'fixtures'/'cad_individual_extrusions.json').read_text())


def mesh_report(vertices, faces):
    bm = bmesh.new()
    try:
        vs = [bm.verts.new(v) for v in vertices]
        for f in faces: bm.faces.new([vs[i] for i in f])
        bm.normal_update(); bm.faces.ensure_lookup_table()
        tree = BVHTree.FromBMesh(bm)
        crossings = sum(1 for a, b in tree.overlap(tree)
                        if a < b and not set(bm.faces[a].verts) & set(bm.faces[b].verts))
        return all(e.is_manifold for e in bm.edges), crossings, bm.calc_volume()
    finally:
        bm.free()


def ring(vertices, x, cy, cz, r):
    """Stored design edge as the host saves it: displayed vertices on the circle, in metres."""
    pts = [v for v in vertices if abs(v[0]-x) < 1e-5 and abs(math.hypot(v[1]-cy, v[2]-cz)-r) < 1e-5]
    pts.sort(key=lambda v: math.atan2(v[2]-cz, v[1]-cy))
    return [[list(a), list(b)] for a, b in zip(pts, pts[1:]+pts[:1])]


class OcctKernelTests(unittest.TestCase):
    def evaluate(self, doc):
        evaluator = occt.Evaluator()
        result = evaluator.evaluate(copy.deepcopy(doc), scale=1.)
        return evaluator, result

    def test_elbow_document_is_one_clean_solid(self):
        evaluator, result = self.evaluate(ELBOW)
        (body, tip), = result['tips'].items()
        manifold, crossings, volume = mesh_report(*result['display'][body][1])
        self.assertTrue(manifold)
        self.assertEqual(crossings, 0)
        self.assertAlmostEqual(volume/1.47102e-4, 1, delta=5e-3)
        self.assertAlmostEqual(occt._volume(evaluator._shapes[tip][1])/1.47102e5, 1, delta=1e-4)   # mm³

    def square(self, depth, *finishes):
        doc = copy.deepcopy(ELBOW)
        base = next(f for f in doc['features'] if f['type'] == 'EXTRUDE')
        base['depth'] = depth
        sketch = model.find(doc, 'sketches', base['sketch_id'])
        sketch['entities'] = [dict(id='square', type='RECTANGLE', x=0., y=0., width=.02, height=.02, construction=False)]
        base['profile_id'] = 'profile_square'
        doc['features'] = [base]+[dict(id=f'finish{i}', type='FILLET', order=99+i, name='Redondeo', sketch_id=None,
                                       body_id=base['body_id'], enabled=True, width=.002, segments=4, edges=edges)
                                  for i, edges in enumerate(finishes)]
        return doc, base['body_id']

    def test_planar_faces_are_single_polygons(self):
        doc, body = self.square(.007)
        _, result = self.evaluate(doc)
        vertices, faces = result['display'][body][1]
        self.assertEqual((len(vertices), sorted(len(f) for f in faces)), (8, [4]*6))

    def test_individual_rectangles_join_a_body_on_a_captured_face(self):
        # Real failing geometry: a pocketed case, dividers and three rectangles
        # on a captured plane. Its nanometre offsets must survive face cleanup.
        sketch = INDIVIDUAL['sketches'][-1]
        body = sketch['body_id']
        for extent in ('ONE', 'TO_FACE'):
            doc = copy.deepcopy(INDIVIDUAL)
            evaluator, baseline = self.evaluate(doc)
            previous_volume = mesh_report(*baseline['display'][body][1])[2]
            for i, entity in enumerate(model.closed_entities(sketch)[:2]):
                with self.subTest(extent=extent, rectangle=i):
                    feature = dict(id=f'individual{i}', name='Extrusión individual', type='EXTRUDE',
                                   order=10+i, sketch_id=sketch['id'], profile_id='profile_'+entity['id'],
                                   depth=.02, enabled=True, body_id=body, extent=extent)
                    if extent == 'TO_FACE':
                        feature['to_face'] = copy.deepcopy(INDIVIDUAL['features'][-1]['to_face'])
                    doc['features'].append(feature)
                    result = evaluator.evaluate(copy.deepcopy(doc))
                    manifold, crossings, volume = mesh_report(*result['display'][body][1])
                    self.assertTrue(manifold)
                    self.assertEqual(crossings, 0)
                    travel = .02 if extent == 'ONE' else model.frame(sketch)['normal'][2] * (
                        feature['to_face']['origin'][2] - model.frame(sketch)['origin'][2])
                    expected_added = entity['width']*entity['height']*travel
                    self.assertAlmostEqual(volume-previous_volume, expected_added, delta=1e-10)
                    previous_volume = volume

    def test_all_three_rectangles_reach_a_face_in_one_extrusion(self):
        doc = copy.deepcopy(INDIVIDUAL)
        target = doc['features'].pop()['to_face']
        sketch = doc['sketches'][-1]
        body = sketch['body_id']
        evaluator, baseline = self.evaluate(doc)
        before = mesh_report(*baseline['display'][body][1])[2]
        feature = dict(id='whole', name='Extrusión del boceto', type='EXTRUDE',
                       order=10, sketch_id=sketch['id'], profile_id='profile_'+sketch['id'],
                       depth=.018, enabled=True, body_id=body, extent='TO_FACE', to_face=target)
        doc['features'].append(feature)
        result = evaluator.evaluate(copy.deepcopy(doc))
        manifold, crossings, volume = mesh_report(*result['display'][body][1])
        self.assertTrue(manifold)
        self.assertEqual(crossings, 0)
        height = target['origin'][2] - model.frame(sketch)['origin'][2]
        area = sum(e['width']*e['height'] for e in model.closed_entities(sketch))
        self.assertAlmostEqual(volume-before, area*height, delta=1e-10)

    def test_lateral_junction_takes_an_exact_fillet(self):
        evaluator, result = self.evaluate(ELBOW)
        shape = evaluator._shapes[next(iter(result['tips'].values()))][1]
        vertices = next(iter(result['display'].values()))[1][0]
        edge = ring(vertices, .049999, 0., .090001, .022)
        self.assertGreater(len(edge), 32)
        filleted = occt.finish_edges(shape, [edge], .003, 4)
        # A concave fillet adds material around the tube.
        self.assertGreater(occt._volume(filleted), occt._volume(shape))
        with self.assertRaises(CommandError):
            occt.finish_edges(shape, [edge], .01, 4)

    def test_finish_keeps_its_straight_edge_when_the_extrusion_grows(self):
        doc, body = self.square(.007, [[[[0., 0., 0.], [0., 0., .007]]]])
        self.evaluate(doc)
        doc['features'][0]['depth'] = .015
        evaluator, grown = self.evaluate(doc)
        self.assertEqual(grown['tips'][body], 'finish0')
        self.assertTrue(mesh_report(*grown['display'][body][1])[0])
        # The rounded vertical edge now spans the whole 15 mm.
        self.assertAlmostEqual(occt._volume(evaluator._shapes['finish0'][1]), (400-(4-math.pi))*15, delta=.5)

    def test_missing_design_edge_is_an_explicit_error(self):
        evaluator, result = self.evaluate(ELBOW)
        shape = evaluator._shapes[next(iter(result['tips'].values()))][1]
        with self.assertRaises(CommandError) as raised:
            occt.finish_edges(shape, [[[[.5, 0., .068], [.5, .001, .068]]]], .003, 4)
        self.assertEqual(raised.exception.code, 'cad_reference_missing')


class RequiredKernelTests(unittest.TestCase):
    def test_missing_ocp_reports_installer_and_never_evaluates(self):
        from blender_tablet_remote.cad.jobs import calculate
        with patch.object(occt, 'DEFAULT_PATH', '/nonexistent'), patch.object(occt.evaluator, 'evaluate') as evaluate:
            for call in (occt.require_available, occt.load, lambda: calculate(dict(operation='evaluate',doc=ELBOW,scale=1.))):
                with self.assertRaises(CommandError) as raised: call()
                self.assertEqual(raised.exception.code, 'cad_kernel_missing')
                self.assertIn('tools/install_occt.sh', raised.exception.message)
            evaluate.assert_not_called()

    def test_broken_ocp_reports_installer_instead_of_a_raw_import_error(self):
        import builtins
        original=builtins.__import__
        def importing(name,*args,**kwargs):
            if name=='OCP.BRepAlgoAPI': raise ImportError('incompatible native library')
            return original(name,*args,**kwargs)
        with patch('builtins.__import__',side_effect=importing), self.assertRaises(CommandError) as raised:
            occt.load()
        self.assertEqual(raised.exception.code,'cad_kernel_missing')
        self.assertIn('tools/install_occt.sh',raised.exception.message)

    def test_missing_ocp_blocks_entering_cad_without_modifying_the_scene(self):
        import bpy
        from blender_tablet_remote.commands import mode
        from blender_tablet_remote.cad.runtime import runtime
        mode.mode_set(dict(mode='OBJECT',_client_id='test'))
        before=bpy.context.scene.get(model.KEY)
        with patch.object(occt,'DEFAULT_PATH','/nonexistent'), self.assertRaises(CommandError) as raised:
            mode.mode_set(dict(mode='CAD',_client_id='test'))
        self.assertEqual(raised.exception.code,'cad_kernel_missing')
        self.assertIn('tools/install_occt.sh',raised.exception.message)
        self.assertFalse(runtime.workspace)
        self.assertEqual(bpy.context.scene.get(model.KEY),before)

    def test_default_capability_and_path_have_no_engine_selector(self):
        from blender_tablet_remote.protocol import FEATURES
        from blender_tablet_remote import BTRPreferences
        self.assertEqual(FEATURES['cad']['kernel'],'OCCT')
        self.assertTrue(FEATURES['cad']['kernel_required'])
        self.assertNotIn('cad_kernel',BTRPreferences.__annotations__)
        self.assertTrue(Path(occt.configured_path(),'OCP').is_dir())


if __name__ == '__main__':
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(case)
                               for case in (OcctKernelTests, RequiredKernelTests))
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
        sys.exit(1)
