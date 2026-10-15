"""Analytic trim, surviving constraints and transactional touch lifecycle."""
import copy,math,sys,unittest
from pathlib import Path
from unittest.mock import patch
import bpy
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from test_cad import CadTests,OWNER,volume
from blender_tablet_remote.cad import document as model,sketch as geom
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.commands import cad
from blender_tablet_remote.errors import CommandError

class TrimTests(CadTests):
    def entities(self,*entities,constraints=()):
        doc=runtime.doc();sketch=model.find(doc,'sketches',runtime.active_sketch_id)
        sketch['entities']=list(entities);sketch['constraints']=list(constraints);runtime.persist(doc)
        return sketch
    def line(self,id,a,b):return dict(id=id,type='LINE',x=a[0],y=a[1],x2=b[0],y2=b[1],construction=False)
    def circle(self,id,x):return dict(id=id,type='CIRCLE',x=x,y=0.,diameter=.02,construction=False)
    def tap(self,id,p,phase='TAP'):
        with patch.object(cad,'_pick',return_value=dict(kind='ENTITY',id=id,part='BODY')):
            with patch.object(runtime,'point',side_effect=[p,(p[0],p[1]+.001)]):
                return cad.entity_trim(dict(phase=phase,u=.5,v=.5,**OWNER))
    def test_overlapping_circles_leave_closed_extrudable_outline(self):
        self.entities(self.circle('a',0),self.circle('b',.012))
        self.tap('a',(.01,0));self.tap('b',(.002,0))
        sketch=runtime.doc()['sketches'][0];self.assertEqual([e['type'] for e in sketch['entities']],['ARC','ARC'])
        profiles=model.profiles(sketch);self.assertEqual(len(profiles),1)
        self.extrude(profiles[0]['id'].removeprefix('profile_'),.005)
        r=.01;d=.012;overlap=2*r*r*math.acos(d/(2*r))-.5*d*math.sqrt(4*r*r-d*d)
        expected=(2*math.pi*r*r-overlap)*.005
        self.assertAlmostEqual(volume(self.obj()),expected,delta=expected*.002)
        model.loads(model.dumps(runtime.doc()))
    def test_line_crossing_rectangle_retains_both_ends_and_dimensions(self):
        rectangle=dict(id='r',type='RECTANGLE',x=.01,y=-.01,width=.02,height=.02,construction=False)
        constraints=[dict(id='fixed',type='FIX',refs=[dict(id='l',part='START')],points={'START':[0.,0.]}),
                     dict(id='distance',type='DISTANCE_X',refs=[dict(id='ORIGIN',part='POINT'),dict(id='l',part='END')],value=.04),
                     dict(id='length',type='DISTANCE',refs=[dict(id='l',part='BODY')],value=.04)]
        self.entities(self.line('l',(0,0),(.04,0)),rectangle,constraints=constraints)
        self.tap('l',(.02,0));sketch=runtime.doc()['sketches'][0]
        lines=[e for e in sketch['entities'] if e['type']=='LINE'];self.assertEqual(len(lines),2)
        self.assertEqual([(round(e['x'],6),round(e['x2'],6)) for e in lines],[(0.,.01),(.03,.04)])
        self.assertTrue(any(c['id']=='distance' for c in sketch['constraints']));self.assertFalse(any(c['id']=='length' for c in sketch['constraints']))
        self.assertEqual(sum(c['type']=='POINT_ON_LINE' for c in sketch['constraints']),2)
        geom.validate_constraints(sketch);model.loads(model.dumps(runtime.doc()))
    def test_rectangle_converts_and_trimmed_arcs_keep_sign(self):
        rectangle=dict(id='r',type='RECTANGLE',x=0.,y=0.,width=.04,height=.04,construction=False)
        self.entities(rectangle,self.line('l',(.02,-.01),(.02,.05)))
        self.tap('r',(.01,0));sketch=runtime.doc()['sketches'][0]
        self.assertFalse(any(e['type']=='RECTANGLE' for e in sketch['entities']));self.assertEqual(len(sketch['entities']),5)
        arc=dict(id='a',type='ARC',x=0.,y=0.,radius=.02,start=180.,sweep=-180.,construction=False)
        sketch=dict(entities=[arc,self.line('l',(0,0),(0,.04))],constraints=[])
        geom.trim(sketch,(.014,.014));remaining=next(e for e in sketch['entities'] if e['type']=='ARC')
        self.assertAlmostEqual(remaining['start'],180.);self.assertAlmostEqual(remaining['sweep'],-90.)
    def test_used_profile_is_rejected_atomically(self):
        e=self.rect();self.extrude(e);sketch=runtime.doc()['sketches'][0]
        cad.sketch_activate(dict(sketch_id=sketch['id'],**OWNER));before=bpy.context.scene[model.KEY]
        with self.assertRaises(CommandError):self.tap(e,(.04,0))
        self.assertEqual(before,bpy.context.scene[model.KEY]);self.assertIsNone(runtime.session)
    def test_end_uses_last_candidate_one_undo_and_cancel_or_miss_no_undo(self):
        self.entities(self.line('l',(0,0),(.04,0)),self.line('c',(.02,-.01),(.02,.01)))
        before=bpy.context.scene[model.KEY]
        self.tap('l',(.01,0),'BEGIN')
        self.assertEqual(before,bpy.context.scene[model.KEY]);self.assertIsNotNone(runtime.session['candidate'])
        with patch.object(cad,'_pick',side_effect=AssertionError('END must not raycast')):
            with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
                cad.entity_trim(dict(phase='END',u=.99,v=.99,**OWNER));undo.assert_called_once()
        line=model.find(runtime.doc()['sketches'][0],'entities','l');self.assertAlmostEqual(line['x'],.02)
        before=bpy.context.scene[model.KEY];self.tap('l',(.03,0),'BEGIN');cad.cancel(OWNER);self.assertEqual(before,bpy.context.scene[model.KEY])
        with patch.object(cad,'_pick',return_value=None),patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            cad.entity_trim(dict(u=.9,v=.9,**OWNER));undo.assert_not_called()
    def test_highlight_is_not_a_pickable_entity(self):
        self.entities(self.line('l',(0,0),(.04,0)))
        overlay=[dict(id='TRIM_CANDIDATE',kind='TRIM',points=[(.2,.5),(.8,.5)],closed=False),
                 dict(id='l',points=[(.2,.5),(.8,.5)],closed=False)]
        with patch.object(runtime,'overlay',return_value=overlay):
            self.assertEqual(cad._pick(dict(u=.4,v=.5))['id'],'l')

    @unittest.skipIf(bpy.app.background,'GUI undo stack required')
    def test_native_undo_redo_restores_trim(self):
        self.draw('LINE',(0,0),(.04,0))
        identifier=runtime.doc()['sketches'][0]['entities'][0]['id']
        self.draw('LINE',(.02,-.01),(.02,.01))
        before=model.dumps(runtime.doc())
        self.tap(identifier,(.01,0),'BEGIN')
        overlay=runtime.status()['overlay']
        self.assertTrue(any(i.get('kind')=='TRIM' for i in overlay))
        cad.entity_trim(dict(phase='END',**OWNER))
        from blender_tablet_remote.commands import history
        history.undo({});self.assertEqual(model.dumps(runtime.doc()),before)
        history.redo({});self.assertAlmostEqual(model.find(runtime.doc()['sketches'][0],'entities',identifier)['x'],.02)

    def test_construction_does_not_cut_and_unsupported_shapes_report_error(self):
        sketch=dict(entities=[self.line('l',(0,0),(.04,0)),dict(self.line('c',(.02,-.01),(.02,.01)),construction=True)],constraints=[])
        geom.trim(sketch,(.01,0));self.assertEqual([e['id'] for e in sketch['entities']],['c'])
        sketch=dict(entities=[dict(id='n',type='NGON',x=0.,y=0.,flats=.02,angle=0.,sides=6)],constraints=[])
        with self.assertRaises(CommandError):geom.trim(sketch,(.01,0))

if __name__=='__main__':
    suite=unittest.TestSuite(TrimTests(n) for n in TrimTests.__dict__ if n.startswith('test_'))
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():raise SystemExit(1)
