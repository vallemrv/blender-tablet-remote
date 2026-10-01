"""Plane on a solid edge, purge of unused planes and the sketch section view."""
import math
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import bpy
from mathutils import Quaternion, Vector

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_cad import CadTests, OWNER
from blender_tablet_remote.cad import document as model
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.camera import camera
from blender_tablet_remote.commands import cad, snap
from blender_tablet_remote.errors import CommandError


class PlaneToolTests(CadTests):
    def tearDown(self):
        runtime.section=False; camera.set_section(None)
        super().tearDown()

    def select_edge(self, start, end):
        """Select the straight solid edge between two design corners."""
        obj=self.obj(); graph=snap._cad_mesh(obj)
        points=graph[1]
        def near(p,q): return (Vector(p)-Vector(q)).length<1e-6
        source=next(e for e in graph[6] if {0,1}=={i for i,c in enumerate((start,end)) for v in e if near(points[v],c)})
        item=snap._cad_reference_geometry(graph,'EDGE',source)
        item=dict(item,id=obj.name+':'+item['id'],object=obj.name,feature_id=obj.get('btr_cad_feature_id'))
        cad.surface_mode(dict(mode='EDGE',**OWNER))
        with patch.object(snap,'query_cad_surface',return_value=item):
            return cad.surface_select(dict(u=.5,v=.5,**OWNER))

    def test_edge_plane_starts_flush_turns_around_the_edge_and_confirms_once(self):
        self.extrude(self.rect())
        state=self.select_edge((0,0,.02),(.08,0,.02))
        self.assertTrue(state['surface']['can_edge_plane'])
        cad.plane_begin(dict(base='EDGE',**OWNER))
        frame=runtime.session['plane_frame']
        x,n=Vector(frame['x']),Vector(frame['normal'])
        self.assertAlmostEqual(abs(x.dot(Vector((1,0,0)))),1.,places=6)
        self.assertAlmostEqual(Vector(frame['origin']).y,0.,places=7)
        self.assertAlmostEqual(Vector(frame['origin']).z,.02,places=7)
        # Flush with one of the two faces that meet there: the top (Z) or the front (−Y).
        self.assertTrue(any(abs(n.dot(v))>1-1e-6 for v in (Vector((0,0,1)),Vector((0,1,0)))))
        cad.plane_update(dict(tilt=[37.,0.],**OWNER))
        turned=runtime.session['plane_frame']
        # Turning keeps the edge on the plane and changes the normal by that angle.
        self.assertAlmostEqual((Vector(turned['origin'])-Vector(frame['origin'])).length,0.,places=7)
        self.assertAlmostEqual(abs(Vector(turned['x']).dot(x)),1.,places=6)
        self.assertAlmostEqual(math.degrees(Vector(turned['normal']).angle(n)),37.,places=5)
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            cad.confirm(OWNER); undo.assert_called_once()
        doc=runtime.doc(); plane=doc['planes'][-1]
        self.assertTrue(plane['implicit'])
        self.assertEqual(doc['sketches'][-1]['plane_id'],plane['id'])

    def test_edge_base_requires_one_straight_edge(self):
        self.extrude(self.rect())
        with self.assertRaises(CommandError): cad.plane_begin(dict(base='EDGE',**OWNER))
        cad.plane_begin(dict(base='XY',**OWNER))
        with self.assertRaises(CommandError): cad.plane_update(dict(base='EDGE',**OWNER))
        self.assertEqual(runtime.session['plane']['base'],'XY')

    def test_purge_removes_only_planes_without_sketches_in_one_undo(self):
        for base in ('XZ','YZ'):
            cad.plane_begin(dict(base=base,**OWNER)); cad.confirm(OWNER); cad.sketch_finish(OWNER)
        doc=runtime.doc(); used=doc['planes'][0]['id']
        doc['sketches']=[s for s in doc['sketches'] if s.get('plane_id')==used]
        runtime.persist(doc)
        cad.plane_create(dict(base='XY',**OWNER))
        self.assertEqual(len(runtime.doc()['planes']),3)
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            cad.plane_purge(OWNER); undo.assert_called_once()
        self.assertEqual([p['id'] for p in runtime.doc()['planes']],[used])
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            with self.assertRaises(CommandError): cad.plane_purge(OWNER)
            undo.assert_not_called()

    def test_section_clips_in_front_of_the_open_sketch_only_when_facing_it(self):
        cad.plane_begin(dict(base='XZ',**OWNER)); cad.confirm(OWNER)
        state=cad.settings(dict(section=True,**OWNER))
        self.assertTrue(state['section'])
        point,normal=camera.section
        self.assertAlmostEqual(abs(normal.dot(Vector((0,1,0)))),1.,places=6)
        # Looking at the plane from −Y: the half towards the camera is retired.
        camera.location=Vector((0,0,0)); camera.distance=1.; camera.perspective='ORTHO'
        camera.rotation=Quaternion((math.sqrt(.5),math.sqrt(.5),0,0)); camera._invalidate()
        self.assertTrue(camera.section_hides((0,-.1,0)))
        self.assertFalse(camera.section_hides((0,.1,0)))
        self.assertFalse(camera.section_hides((0,0,0)))
        # A tilted peek ignores the section.
        camera.rotation=Quaternion((1,0,0,0)); camera._invalidate()
        self.assertFalse(camera.section_hides((0,-.1,0)))
        cad.sketch_finish(OWNER)
        self.assertIsNone(camera.section)
        cad.settings(dict(section=False,**OWNER))
        self.assertIsNone(camera.section)


if __name__=='__main__':
    suite=unittest.TestSuite(PlaneToolTests(n) for n in PlaneToolTests.__dict__ if n.startswith('test_'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        import os
        os._exit(1)
