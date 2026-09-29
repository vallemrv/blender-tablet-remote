"""Linked slot thickness and mirrored feature operands, including downstream rebuilds."""
import copy
import math
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_cad import CadTests,OWNER,volume
from blender_tablet_remote.cad import document as model,sketch as geometry
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.commands import cad
from blender_tablet_remote.errors import CommandError


class OffsetMirrorTests(CadTests):
    def test_slot_radius_is_exact_and_offset_keeps_centres_and_length(self):
        source=self.draw('SLOT',(0,0),(.035,0))
        cad.entity_set(dict(entity_id=source,values={'radius':.0075},**OWNER))
        source_before=copy.deepcopy(model.entity(runtime.doc(),source)[1])
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            state=cad.entity_offset(dict(entity_id=source,thickness=.0075,side='OUTWARD',**OWNER))
            undo.assert_called_once()
        child=state['selection']['id'];sketch,e=model.entity(runtime.doc(),child)
        self.assertAlmostEqual(e['width'],.03,places=9)
        self.assertEqual(geometry.slot_centers(e),geometry.slot_centers(source_before))
        self.assertEqual(model.entity(runtime.doc(),source)[1],source_before)
        self.assertEqual([m['field'] for m in model.public(runtime.doc())['sketches'][0]['entities'][-1]['dimensions']],['offset'])
        cad.entity_set(dict(entity_id=child,values={'offset':.005},**OWNER))
        self.assertEqual(model.entity(runtime.doc(),source)[1],source_before)
        self.assertAlmostEqual(model.entity(runtime.doc(),child)[1]['width'],.025,places=8)
        cad.entity_set(dict(entity_id=source,values={'width':.020,'length':.045,'angle':35.},**OWNER))
        sketch,e=model.entity(runtime.doc(),child);_,parent=model.entity(runtime.doc(),source)
        self.assertAlmostEqual(e['width'],.03,places=8)
        self.assertAlmostEqual(e['length'],.045,places=8)
        self.assertAlmostEqual(e['angle'],35.,places=6)
        for a,b in zip(geometry.slot_centers(e),geometry.slot_centers(parent)):
            self.assertLess(math.dist(a,b),1e-8)
        saved=model.loads(model.dumps(runtime.doc()))
        self.assertTrue(any(c['type']=='OFFSET' for c in saved['sketches'][0]['constraints']))
        raw=bpy.context.scene[model.KEY]
        with self.assertRaises(CommandError):cad.entity_set(dict(entity_id=child,values={'width':.04},**OWNER))
        self.assertEqual(bpy.context.scene[model.KEY],raw)

    def test_offset_circle_and_rectangle_and_invalid_thickness_are_atomic(self):
        for typ in ('CIRCLE','RECTANGLE'):
            cad.sketch_create(dict(plane='XY',**OWNER))
            source=self.draw(typ,(.01,.01),(.03,.03))
            state=cad.entity_offset(dict(entity_id=source,thickness=.002,side='INWARD',**OWNER))
            sketch,e=model.entity(runtime.doc(),state['selection']['id']);_,parent=model.entity(runtime.doc(),source)
            key='diameter' if typ=='CIRCLE' else 'width'
            self.assertAlmostEqual(e[key],parent[key]-.004,places=9)
            raw=bpy.context.scene[model.KEY]
            with self.assertRaises(CommandError):cad.entity_offset(dict(entity_id=source,thickness=1.,side='INWARD',**OWNER))
            self.assertEqual(bpy.context.scene[model.KEY],raw)
            with self.assertRaises(CommandError):cad.entity_delete(dict(entity_id=source,**OWNER))
            self.assertEqual(bpy.context.scene[model.KEY],raw)

    def test_offset_slot_makes_closed_ring_and_rebuilds_after_thickness_edit(self):
        source=self.draw('SLOT',(0,0),(.035,0))
        cad.entity_set(dict(entity_id=source,values={'width':.015},**OWNER))
        state=cad.entity_offset(dict(entity_id=source,thickness=.0075,side='OUTWARD',**OWNER))
        child=state['selection']['id']
        self.extrude(child,.01)
        expected=(.035*(.03-.015)+math.pi*((.03/2)**2-(.015/2)**2))*.01
        self.assertAlmostEqual(volume(self.obj()),expected,delta=expected*.002)
        cad.entity_set(dict(entity_id=child,values={'offset':.005},**OWNER))
        self.assertLess(volume(self.obj()),expected)

    def pillar(self):
        base=self.draw('RECTANGLE',(-.05,-.04),(.05,.04));support=self.extrude(base,.01)
        cad.sketch_create(dict(support_id=support,**OWNER))
        lug=self.draw('RECTANGLE',(-.04,.015),(-.02,.025));feature=self.extrude(lug,.02)
        cad.sketch_finish(OWNER)
        return support,lug,feature

    def test_mirror_extrusion_rebuilds_source_profile_and_depth_without_sketch_copy(self):
        _,lug,source=self.pillar();count=len(runtime.doc()['sketches'])
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            state=cad.feature_mirror(dict(feature_id=source,plane='XZ',offset=0.,**OWNER));undo.assert_called_once()
        mirrored=state['selection']['id']
        self.assertEqual(len(runtime.doc()['sketches']),count)
        self.assertAlmostEqual(volume(self.obj()),.1*.08*.01+2*.02*.01*.02,places=9)
        cad.feature_set(dict(feature_id=source,depth=.03,**OWNER))
        self.assertAlmostEqual(volume(self.obj()),.1*.08*.01+2*.02*.01*.03,places=9)
        self.assertEqual(model.find(runtime.doc(),'features',mirrored)['depth'],.03)
        cad.entity_set(dict(entity_id=lug,values={'width':.025},**OWNER))
        self.assertAlmostEqual(volume(self.obj()),.1*.08*.01+2*.025*.01*.03,places=9)
        raw=bpy.context.scene[model.KEY]
        with self.assertRaises(CommandError):cad.feature_delete(dict(feature_id=source,**OWNER))
        with self.assertRaises(CommandError):cad.feature_set(dict(feature_id=mirrored,depth=.04,**OWNER))
        with self.assertRaises(CommandError):cad.feature_set(dict(feature_id=mirrored,plane='BAD',**OWNER))
        self.assertEqual(bpy.context.scene[model.KEY],raw)
        self.assertEqual(model.loads(raw)['features'][-1]['mirror']['source_id'],source)

    def test_mirror_cut_subtracts_reflected_operand_only(self):
        _,_,source=self.pillar()
        target=cad.feature_mirror(dict(feature_id=source,plane='XZ',**OWNER))['selection']['id']
        cad.sketch_create(dict(support_id=source,**OWNER))
        hole=self.draw('CIRCLE',(-.03,.02),(-.027,.02))
        before=volume(self.obj())
        state=cad.extrude_begin(dict(profile_id='profile_'+hole,operation='CUT',target_id=target,depth=.04,**OWNER))
        cut=state['selection']['id'];cad.confirm(OWNER);cad.sketch_finish(OWNER)
        after_one=volume(self.obj())
        mirror=cad.feature_mirror(dict(feature_id=cut,plane='XZ',**OWNER))['selection']['id']
        self.assertAlmostEqual(before-volume(self.obj()),2*(before-after_one),delta=1e-9)
        cad.feature_set(dict(feature_id=mirror,enabled=False,**OWNER))
        self.assertAlmostEqual(volume(self.obj()),after_one,places=9)

    def test_mirror_at_rollback_advances_bar_and_invalid_input_preserves_it(self):
        _,_,source=self.pillar()
        cad.history_rollback(dict(node_id=source,**OWNER))
        raw=bpy.context.scene[model.KEY];bar=runtime.rollback_id
        with self.assertRaises(CommandError):cad.feature_mirror(dict(feature_id=source,plane='BAD',**OWNER))
        self.assertEqual(bpy.context.scene[model.KEY],raw);self.assertEqual(runtime.rollback_id,bar)
        state=cad.feature_mirror(dict(feature_id=source,plane='XZ',**OWNER))
        self.assertEqual(state['rollback_id'],state['selection']['id'])

    def test_mirror_plane_offset_suppression_and_design_surface_selection(self):
        from blender_tablet_remote.commands import snap
        from blender_tablet_remote.cad import mirror
        # A reflection changes handedness; face winding is reversed for every plane.
        for plane,axis in mirror.AXIS.items():
            point=(.01,.02,.03);spec=dict(plane=plane,offset=.05)
            reflected=mirror.point(point,spec)
            self.assertAlmostEqual(reflected[axis],.10-point[axis])
            for a,b in zip(mirror.point(reflected,spec),point):self.assertAlmostEqual(a,b,places=12)
        _,_,source=self.pillar()
        feature=cad.feature_mirror(dict(feature_id=source,plane='XZ',offset=-.005,**OWNER))['selection']['id']
        graph=snap._cad_mesh(self.obj())
        self.assertTrue(graph[7])
        # The reflected lug spans Y=-35..-25 mm, independent of base visibility.
        tops=[p for p in graph[1] if p.z>.029]
        self.assertAlmostEqual(min(p.y for p in tops),-.035,places=6)
        expected=volume(self.obj())
        cad.feature_set(dict(feature_id=source,enabled=False,**OWNER))
        self.assertAlmostEqual(volume(self.obj()),.1*.08*.01,places=9)
        cad.feature_set(dict(feature_id=source,enabled=True,**OWNER))
        self.assertAlmostEqual(volume(self.obj()),expected,places=9)
        self.assertTrue(model.find(runtime.doc(),'features',feature)['enabled'])


if __name__=='__main__':
    suite=unittest.TestSuite(OffsetMirrorTests(n) for n in OffsetMirrorTests.__dict__ if n.startswith('test_'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        import os;os._exit(1)
