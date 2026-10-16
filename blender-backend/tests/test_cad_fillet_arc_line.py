"""Analytic arc/line sketch fillets, persistent tangency and reversible trimming."""
import copy,math,sys,unittest
from pathlib import Path
from unittest.mock import patch
import bpy,numpy as np
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from test_cad import CadTests,OWNER,volume
from blender_tablet_remote.cad import document as model,sketch as geometry
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.commands import cad
from blender_tablet_remote.errors import CommandError

class ArcLineFilletTests(CadTests):
    def sketch(self,inside=False,reverse_line=False,reverse_arc=False):
        line=dict(id='line',type='LINE',x=0.,y=0.,x2=.03,y2=0.,construction=False)
        arc=dict(id='arc',type='ARC',x=.02 if inside else -.02,y=0.,radius=.02,start=180. if inside else 0.,sweep=-90. if inside else 90.,construction=False)
        if reverse_line:line.update(x=.03,x2=0.)
        if reverse_arc:arc.update(start=arc['start']+arc['sweep'],sweep=-arc['sweep'])
        return dict(id='s',plane='XY',offset=0,entities=[line,arc],constraints=[])
    def create(self,sketch,r=.003,endpoint=False):
        refs=[dict(id='line',part=('START' if sketch['entities'][0]['x']==0 else 'END') if endpoint else 'BODY')]
        if not endpoint:refs.append(dict(id='arc',part='BODY'))
        return geometry.fillet(sketch,refs,r)[0]
    def assert_tangent(self,sketch,fillet,corner=(0.,0.)):
        sides=geometry.fillet_sides(sketch,fillet);self.assertIsNotNone(sides)
        for ref,role in zip(sides,('START','END')):
            np.testing.assert_allclose(geometry.point(sketch,ref),geometry.point(sketch,dict(id=fillet['id'],part=role)),atol=1e-8)
        for c in sketch['constraints']:
            np.testing.assert_allclose(geometry.residual(sketch,c,1.),0.,atol=1e-8)
        np.testing.assert_allclose(geometry.point(sketch,dict(id=fillet['id'],part='CORNER')),corner,atol=1e-8)
    def test_internal_external_and_both_endpoint_directions(self):
        for inside in (False,True):
            for reverse_line in (False,True):
                for reverse_arc in (False,True):
                    with self.subTest(inside=inside,line=reverse_line,arc=reverse_arc):
                        sketch=self.sketch(inside,reverse_line,reverse_arc);original=copy.deepcopy(sketch['entities'][1])
                        arc=self.create(sketch);self.assert_tangent(sketch,arc)
                        source=geometry.get_entity(sketch,dict(id='arc'))
                        for key in ('x','y','radius'):self.assertAlmostEqual(source[key],original[key],places=10)
                        self.assertLess(abs(source['sweep']),abs(original['sweep']))
                        tangent=next(c for c in sketch['constraints'] if c['type']=='TANGENT' and any(r['id']=='arc' for r in c['refs']))
                        self.assertEqual(tangent.get('mode'),'INTERNAL' if inside else 'EXTERNAL')
    def test_oblique_and_translated_join(self):
        for angle in (35.,90.,-70.,180.):
            sketch=self.sketch();a=math.radians(angle);matrix=np.array([[math.cos(a),-math.sin(a)],[math.sin(a),math.cos(a)]])
            offset=np.array([.042,-.016])
            for e in sketch['entities']:
                e['x'],e['y']=map(float,matrix@np.array([e['x'],e['y']])+offset)
                if e['type']=='LINE':e['x2'],e['y2']=map(float,matrix@np.array([e['x2'],e['y2']])+offset)
                else:e['start']+=angle
            fillet=self.create(sketch);self.assert_tangent(sketch,fillet,offset)

    def test_radius_edit_and_remove_restore_the_corner(self):
        from blender_tablet_remote.cad import dimensions
        for inside in (False,True):
            sketch=self.sketch(inside);original=copy.deepcopy(sketch['entities'])
            arc=self.create(sketch,endpoint=True)
            for r in (.004,.0015):
                goals=dimensions.set_values(sketch,arc,dict(radius=r));geometry.solve(sketch,goals)
                arc=model.find(sketch,'entities',arc['id']);self.assertAlmostEqual(arc['radius'],r,places=9)
                self.assert_tangent(sketch,arc)
            geometry.remove_fillet(sketch,arc)
            for before,after in zip(original,sketch['entities']):
                for key in model.FIELDS[before['type']]:self.assertAlmostEqual(before[key],after[key],places=8)
    def test_compatible_radius_length_and_fixed_points_survive(self):
        sketch=self.sketch();sketch['constraints']=[
            dict(id='r',type='RADIUS',refs=[dict(id='arc',part='BODY')],value=.02),
            dict(id='l',type='DISTANCE',refs=[dict(id='line',part='BODY')],value=.03),
            dict(id='corner',type='FIX',refs=[dict(id='line',part='START')],points={'START':[0.,0.]}),
            dict(id='end',type='FIX',refs=[dict(id='arc',part='END')],points={'END':[-.02,.02]}),
            dict(id='joined',type='COINCIDENT',refs=[dict(id='line',part='START'),dict(id='arc',part='START')])]
        arc=self.create(sketch);self.assert_tangent(sketch,arc)
        self.assertEqual(next(c for c in sketch['constraints'] if c['id']=='corner')['points'],{'CORNER':[0.,0.]})
        geometry.remove_fillet(sketch,arc)
        for c in sketch['constraints']:np.testing.assert_allclose(geometry.residual(sketch,c,1.),0,atol=1e-8)
    def test_two_junctions_of_a_semicircle_can_be_rounded_together(self):
        sketch=dict(entities=[dict(id='line',type='LINE',x=-.02,y=0.,x2=.02,y2=0.),
                              dict(id='arc',type='ARC',x=0.,y=0.,radius=.02,start=0.,sweep=180.)],constraints=[])
        arcs=geometry.fillet(sketch,[dict(id='line'),dict(id='arc')],.002)
        self.assertEqual(len(arcs),2);self.assertEqual(len(model.profiles(sketch)),1)
        for c in sketch['constraints']:np.testing.assert_allclose(geometry.residual(sketch,c,1.),0,atol=1e-8)
    def test_used_closed_profile_rebuilds_only_at_finish_and_keeps_one_undo(self):
        sketch=self.sketch(reverse_arc=True)
        sketch['entities'].extend([dict(id='up',type='LINE',x=.03,y=0.,x2=.03,y2=.02),dict(id='top',type='LINE',x=.03,y=.02,x2=-.02,y2=.02)])
        doc=runtime.doc();current=doc['sketches'][0];current.update(entities=sketch['entities'],constraints=[]);runtime.persist(doc)
        profile=model.profiles(current)[0]['id'];cad.extrude_begin(dict(profile_id=profile,depth=.01,**OWNER));cad.confirm(OWNER)
        baseline=volume(self.obj());cad.sketch_activate(dict(sketch_id=current['id'],**OWNER))
        cad._set_selection([dict(kind='ENTITY',id=i,part='BODY') for i in ('line','arc')])
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            cad.fillet(dict(radius=.003,**OWNER));undo.assert_called_once()
        self.assertAlmostEqual(volume(self.obj()),baseline);self.assertTrue(runtime.status()['sketch_pending'])
        arc=next(e for e in runtime.doc()['sketches'][0]['entities'] if e.get('fillet_kind'))
        self.assertTrue(model.public(runtime.doc())['sketches'][0]['entities'][-1]['is_fillet'])
        model.loads(model.dumps(runtime.doc()));cad.sketch_finish(OWNER)
        self.assertNotAlmostEqual(volume(self.obj()),baseline,places=10)
        cad.sketch_activate(dict(sketch_id=current['id'],**OWNER));cad.fillet_remove(dict(entity_id=arc['id'],**OWNER));cad.sketch_finish(OWNER)
        self.assertAlmostEqual(volume(self.obj()),baseline,places=9)
    def test_copy_remaps_tangent_sources_and_keeps_radius_editable(self):
        sketch=self.sketch();doc=runtime.doc();doc['sketches'][0].update(entities=sketch['entities'],constraints=[]);runtime.persist(doc)
        source=runtime.active_sketch_id
        cad._set_selection([dict(kind='ENTITY',id=i,part='BODY') for i in ('line','arc')]);cad.fillet(dict(radius=.003,**OWNER))
        cad.sketch_copy(dict(sketch_id=source,offset=.01,**OWNER))
        copied=runtime.doc()['sketches'][-1];arc=next(e for e in copied['entities'] if e.get('fillet_kind'))
        ids={e['id'] for e in copied['entities']}
        self.assertTrue(all(r['id'] in ids for r in geometry.fillet_sides(copied,arc)))
        cad.entity_set(dict(entity_id=arc['id'],values={'radius':.002},**OWNER))
        model.loads(model.dumps(runtime.doc()))

    def test_too_large_radius_rejects_without_changing_document(self):
        sketch=self.sketch(inside=True);doc=runtime.doc();doc['sketches'][0].update(entities=sketch['entities'],constraints=[]);runtime.persist(doc)
        cad._set_selection([dict(kind='ENTITY',id=i,part='BODY') for i in ('line','arc')]);before=bpy.context.scene[model.KEY]
        with self.assertRaises(CommandError):cad.fillet(dict(radius=.1,**OWNER))
        self.assertEqual(before,bpy.context.scene[model.KEY])

if __name__=='__main__':
    suite=unittest.TestSuite(ArcLineFilletTests(n) for n in ArcLineFilletTests.__dict__ if n.startswith('test_'))
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():raise SystemExit(1)
