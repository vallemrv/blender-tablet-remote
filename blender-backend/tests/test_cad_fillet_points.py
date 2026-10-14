"""Sharp-corner references survive sketch rounding, dimensions and symmetry."""
import math
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import bpy
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cad import CadTests, OWNER
from blender_tablet_remote.cad import document as model, sketch as geometry, annotations
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.camera import camera
from blender_tablet_remote.commands import cad


def ref(identifier, part='CORNER'):
    return dict(id=identifier, part=part)


class FilletPointTests(CadTests):
    def rounded(self):
        rectangle = self.square((-.02, -.02), (.02, .02))
        cad._set_selection([dict(kind='ENTITY', **ref(rectangle, 'BODY'))])
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            cad.fillet(dict(radius=.004, **OWNER))
            undo.assert_called_once()
        sketch = model.find(runtime.doc(),'sketches',runtime.active_sketch_id)
        return [e['id'] for e in sketch['entities'] if e['type']=='ARC']

    def test_four_outer_corners_and_centers_are_drawn_pickable_and_snap_targets(self):
        arcs = self.rounded()
        sketch = runtime.doc()['sketches'][0]
        expected = [(-.02,-.02),(.02,-.02),(.02,.02),(-.02,.02)]
        for identifier, position in zip(arcs, expected):
            np.testing.assert_allclose(geometry.point(sketch,ref(identifier)),position,atol=1e-9)
        with patch.object(camera,'project',side_effect=lambda p,_: (float(p.x)*10+.5,float(p.y)*10+.5)):
            doc=runtime.doc()
            # Move the radius label aside; a label overlapping a point owns that tap.
            for c in doc['sketches'][0]['constraints']:
                if c['type']=='RADIUS': c['label_position']=[.08,.08]
            overlay = runtime.overlay(doc)
            self.assertTrue(overlay)
            for identifier in arcs:
                item = next(o for o in overlay if o['id']==identifier)
                handles = {h['part']:h for h in item['handles']}
                self.assertEqual(set(handles),{'CENTER','START','END','CORNER'})
                p = handles['CORNER']['point']
                with patch.object(runtime,'overlay',return_value=overlay):
                    hit = cad._pick(dict(u=p[0],v=p[1]))
                    self.assertEqual((hit['id'],hit['part']),(identifier,'CORNER'))
                    snap = cad._endpoint(dict(u=p[0],v=p[1]),sketch)
                    self.assertEqual((snap['entity_id'],snap['part']),(identifier,'CORNER'))

    def test_dimensions_symmetry_radius_and_saved_document_keep_outer_square(self):
        arcs = self.rounded()
        cad.constraint_add(dict(type='SYMMETRIC',refs=[ref(arcs[0]),ref(arcs[2]),ref('ORIGIN','POINT')],**OWNER))
        cad.constraint_add(dict(type='DISTANCE_X',value=.06,refs=[ref(arcs[0]),ref(arcs[1])],**OWNER))
        for radius in (.007,.003):
            cad.entity_set(dict(entity_id=arcs[0],values={'radius':radius},**OWNER))
            sketch = model.loads(model.dumps(runtime.doc()))['sketches'][0]
            points = [geometry.point(sketch,ref(i)) for i in arcs]
            np.testing.assert_allclose(points,[(-.03,-.03),(.03,-.03),(.03,.03),(-.03,.03)],atol=1e-7)
            for e in sketch['entities']:
                if e['type']=='ARC': self.assertAlmostEqual(e['radius'],radius,places=7)
            rule = next(c for c in sketch['constraints'] if c['type']=='DISTANCE_X')
            np.testing.assert_allclose(annotations.anchors(sketch,rule),points[:2],atol=1e-9)
            self.assertEqual(len(model.profiles(sketch)),1)

    def test_existing_corner_fix_and_dimension_survive_rounding_and_removal(self):
        rectangle = self.rect()
        cad.constraint_add(dict(type='FIX',refs=[ref(rectangle,'P2')],**OWNER))
        cad.constraint_add(dict(type='DISTANCE_X',value=.08,refs=[ref('ORIGIN','POINT'),ref(rectangle,'P2')],**OWNER))
        before = {c['id'] for c in runtime.doc()['sketches'][0]['constraints'] if c['type']=='DISTANCE_X'}
        cad._set_selection([dict(kind='ENTITY',**ref(rectangle,'P2'))])
        cad.fillet(dict(radius=.005,**OWNER))
        sketch = runtime.doc()['sketches'][0]
        arc = next(e for e in sketch['entities'] if e['type']=='ARC')
        np.testing.assert_allclose(geometry.point(sketch,ref(arc['id'])),(.08,.045),atol=1e-8)
        self.assertEqual(next(c for c in sketch['constraints'] if c['type']=='FIX')['points'],{'CORNER':[.08,.045]})
        cad.entity_set(dict(entity_id=arc['id'],values={'radius':.009},**OWNER))
        cad.fillet_remove(dict(entity_id=arc['id'],**OWNER))
        sketch = model.loads(model.dumps(runtime.doc()))['sketches'][0]
        self.assertTrue(before <= {c['id'] for c in sketch['constraints']})
        for c in sketch['constraints']:
            self.assertFalse(any(r['id']==arc['id'] for r in c['refs']))
            np.testing.assert_allclose(geometry.residual(sketch,c,1.),0,atol=1e-8)

    def test_oblique_corners_follow_both_sweep_directions_and_drag(self):
        for angle in (35.,120.,-70.):
            with self.subTest(angle=angle):
                cad.sketch_create(dict(plane='XY',**OWNER))
                corner=(.03,.02)
                a=self.draw('LINE',corner,(.1,.02))
                theta=math.radians(angle)
                b=self.draw('LINE',corner,(corner[0]+.07*math.cos(theta),corner[1]+.07*math.sin(theta)))
                cad._set_selection([dict(kind='ENTITY',**ref(i,'BODY')) for i in (a,b)])
                cad.fillet(dict(radius=.003,**OWNER))
                sketch=runtime.doc()['sketches'][-1]
                arc=next(e for e in sketch['entities'] if e['type']=='ARC')
                np.testing.assert_allclose(geometry.point(sketch,ref(arc['id'])),corner,atol=1e-8)
                geometry.solve(sketch,geometry.move_goals(sketch,[ref(arc['id'])],.004,.002),drag=True)
                moved=model.find(sketch,'entities',arc['id'])
                sides=geometry.fillet_sides(sketch,moved)
                np.testing.assert_allclose(geometry.point(sketch,ref(arc['id'])),geometry._fillet_corner(sketch,sides),atol=1e-7)
                np.testing.assert_allclose(geometry.point(sketch,ref(arc['id'])),(.034,.022),atol=1e-6)

    def test_ordinary_arcs_have_no_corner_and_old_roundings_need_no_migration(self):
        arc=self.draw('ARC',(0,0),(.01,0))
        sketch,e=model.entity(runtime.doc(),arc)
        self.assertNotIn('CORNER',geometry.handles(e,sketch))
        cad.sketch_create(dict(plane='XY',**OWNER))
        arcs=self.rounded()
        doc=model.loads(model.dumps(runtime.doc()))
        sketch,e=model.entity(doc,arcs[0])
        self.assertNotIn('CORNER',e)
        self.assertNotIn('CORNER',geometry.handles(e))
        self.assertIn('CORNER',geometry.handles(e,sketch))


if __name__=='__main__':
    suite=unittest.TestSuite(FilletPointTests(n) for n in FilletPointTests.__dict__ if n.startswith('test_'))
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
        raise SystemExit(1)
