"""Tangency between two arcs/circles keeps the side they were drawn on."""
import math
import random
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cad import CadTests, OWNER
from blender_tablet_remote.cad import document as model
from blender_tablet_remote.cad import sketch as geometry
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.commands import cad
from blender_tablet_remote.errors import CommandError


class TangentArcTests(CadTests):
    def test_closed_mouth_arcs_keep_coincident_ends_radii_and_tangency_after_drag(self):
        # R27 centre, R15 ears 50 mm apart, four concave R10 connections.
        boss_r, ear_r, blend_r, offset = .027, .015, .010, .025
        x = ((boss_r+blend_r)**2-(ear_r+blend_r)**2+offset**2)/(2*offset)
        y = math.sqrt((boss_r+blend_r)**2-x*x)
        centers = [(sx*x, sy*y) for sx in (1,-1) for sy in (1,-1)]
        entities, constraints, pairs = [], [], []
        def angle(c,p): return math.degrees(math.atan2(p[1]-c[1],p[0]-c[0]))
        def contact(c,r,b):
            d=math.dist(c,b)
            return (c[0]+(b[0]-c[0])*r/d,c[1]+(b[1]-c[1])*r/d)
        def arc(identifier,c,r,a,b):
            entities.append(dict(id=identifier,type='ARC',x=c[0],y=c[1],radius=r,start=a,sweep=(b-a)%360))
        points=[(contact((0,0),boss_r,b),contact((offset if b[0]>0 else -offset,0),ear_r,b)) for b in centers]
        arc('top',(0,0),boss_r,angle((0,0),points[0][0]),angle((0,0),points[2][0]))
        arc('bottom',(0,0),boss_r,angle((0,0),points[3][0]),angle((0,0),points[1][0]))
        arc('right',(offset,0),ear_r,angle((offset,0),points[1][1]),angle((offset,0),points[0][1]))
        arc('left',(-offset,0),ear_r,angle((-offset,0),points[2][1]),angle((-offset,0),points[3][1]))
        for i,c in enumerate(centers):
            a,b=(angle(c,p) for p in points[i])
            if (b-a)%360>180: a,b=b,a
            arc('blend'+str(i),c,blend_r,a,b)
            pairs.extend([('blend'+str(i),'top' if c[1]>0 else 'bottom'),('blend'+str(i),'right' if c[0]>0 else 'left')])
        def rule(typ,refs,**kw):
            constraints.append(dict(id='rule'+str(len(constraints)),type=typ,refs=refs,**kw))
        ends=[(e['id'],role,p) for e in entities for role,p in geometry.handles(e).items() if role in ('START','END')]
        for i,(a,role,p) in enumerate(ends):
            for b,other,q in ends[i+1:]:
                if a!=b and math.dist(p,q)<1e-9:
                    rule('COINCIDENT',[dict(id=a,part=role),dict(id=b,part=other)])
        for e in entities:
            rule('RADIUS',[dict(id=e['id'],part='BODY')],value=e['radius'])
            if not e['id'].startswith('blend'):
                rule('FIX',[dict(id=e['id'],part='CENTER')],points={'CENTER':[e['x'],e['y']]})
        rng=random.Random(7)
        for e in entities:
            e['start']+=rng.uniform(-.5,.5)
            if e['id'].startswith('blend'):
                e['x']+=rng.uniform(-.0002,.0002);e['y']+=rng.uniform(-.0002,.0002)
        doc=runtime.doc();sketch=doc['sketches'][0]
        sketch.update(entities=entities,constraints=constraints)
        geometry.solve(sketch)
        runtime.persist(doc)
        for a,b in pairs:
            with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
                cad.constraint_add(dict(type='TANGENT',refs=[dict(id=a),dict(id=b)],**OWNER))
                undo.assert_called_once()
        sketch=runtime.doc()['sketches'][0]
        self.assertEqual(len(model.closed_entities(sketch)),1)
        geometry.solve(sketch,geometry.move_goals(sketch,[dict(id='blend0',part='CENTER')],.002,.003),drag=True)
        for c in sketch['constraints']:
            self.assertLess(max(abs(v) for v in geometry.residual(sketch,c,1.)),1e-7)
        for a,b in pairs:
            ea,eb=(model.find(sketch,'entities',i) for i in (a,b))
            self.assertAlmostEqual(math.hypot(ea['x']-eb['x'],ea['y']-eb['y']),ea['radius']+eb['radius'],places=7)
        self.assertEqual(len(model.closed_entities(sketch)),1)
        # A contradictory hard radius must leave the whole document unchanged.
        before=model.dumps(runtime.doc())
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            with self.assertRaises(CommandError):
                cad.entity_set(dict(entity_id='top',values={'radius':.05},**OWNER))
            undo.assert_not_called()
        self.assertEqual(model.dumps(runtime.doc()),before)

    def entity(self, identifier):
        sketch = model.find(runtime.doc(), 'sketches', runtime.active_sketch_id)
        return model.find(sketch, 'entities', identifier)

    def test_internal_arc_tangency_survives_radius_edit_and_roundtrip(self):
        outer=self.draw('ARC',(0,0),(.03,0))
        inner=self.draw('ARC',(.02,0),(.03,0))
        for identifier,r in ((outer,.03),(inner,.01)):
            cad.constraint_add(dict(type='RADIUS',refs=[dict(id=identifier)],value=r,**OWNER))
        cad.constraint_add(dict(type='COINCIDENT',refs=[dict(id=outer,part='START'),dict(id=inner,part='START')],**OWNER))
        cad.constraint_add(dict(type='TANGENT',refs=[dict(id=outer),dict(id=inner)],**OWNER))
        cad.entity_set(dict(entity_id=inner,values={'radius':.012},**OWNER))
        restored=model.loads(model.dumps(runtime.doc()))['sketches'][0]
        a,b=(model.find(restored,'entities',i) for i in (outer,inner))
        rule=next(c for c in restored['constraints'] if c['type']=='TANGENT')
        self.assertEqual(rule['mode'],'INTERNAL')
        self.assertAlmostEqual(math.hypot(a['x']-b['x'],a['y']-b['y']),.018,places=7)
        self.assertLess(math.dist(geometry.handles(a)['START'],geometry.handles(b)['START']),1e-7)

    def test_same_arc_twice_is_rejected_without_undo_or_document_change(self):
        arc=self.draw('ARC',(0,0),(.02,0))
        before=model.dumps(runtime.doc())
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            with self.assertRaises(CommandError):
                cad.constraint_add(dict(type='TANGENT',refs=[dict(id=arc,part='START'),dict(id=arc,part='END')],**OWNER))
            undo.assert_not_called()
        self.assertEqual(model.dumps(runtime.doc()),before)

    def test_outside_and_inside_tangency_between_circles(self):
        big = self.draw('CIRCLE', (0, 0), (.027, 0))
        outer = self.draw('CIRCLE', (.05, 0), (.06, 0))
        inner = self.draw('CIRCLE', (.008, 0), (.013, 0))
        cad.constraint_add(dict(type='RADIUS', refs=[dict(id=big)], value=.027, **OWNER))
        cad.constraint_add(dict(type='TANGENT', refs=[dict(id=big), dict(id=outer)], **OWNER))
        cad.constraint_add(dict(type='TANGENT', refs=[dict(id=big), dict(id=inner)], **OWNER))
        sketch = model.find(runtime.doc(), 'sketches', runtime.active_sketch_id)
        self.assertEqual([c['mode'] for c in sketch['constraints'] if c['type'] == 'TANGENT'], ['EXTERNAL', 'INTERNAL'])
        b, o, i = (self.entity(e) for e in (big, outer, inner))
        rb, ro, ri = b['diameter']/2, o['diameter']/2, i['diameter']/2
        self.assertAlmostEqual(math.hypot(o['x']-b['x'], o['y']-b['y']), rb+ro, places=7)
        self.assertAlmostEqual(math.hypot(i['x']-b['x'], i['y']-b['y']), rb-ri, places=7)
        model.loads(model.dumps(runtime.doc()))

    def test_blend_arc_tangent_to_two_arcs_keeps_its_radius(self):
        # The flange mouth: R27 boss, R15 ear, and a concave R10 blend touching both from outside.
        boss = self.draw('CIRCLE', (0, 0), (.027, 0))
        ear = self.draw('CIRCLE', (0, .025), (.015, .025))
        blend = self.draw('CIRCLE', (.03, .03), (.04, .03))
        for ref, value in ((boss, .027), (ear, .015), (blend, .01)):
            cad.constraint_add(dict(type='RADIUS', refs=[dict(id=ref)], value=value, **OWNER))
        for other in (boss, ear):
            cad.constraint_add(dict(type='TANGENT', refs=[dict(id=blend), dict(id=other)], **OWNER))
        b, e, k = (self.entity(i) for i in (boss, ear, blend))
        self.assertAlmostEqual(math.hypot(k['x']-b['x'], k['y']-b['y']), .037, places=7)
        self.assertAlmostEqual(math.hypot(k['x']-e['x'], k['y']-e['y']), .025, places=7)

    def test_two_lines_are_not_a_tangency(self):
        a = self.draw('LINE', (0, 0), (.02, 0)); b = self.draw('LINE', (0, .01), (.02, .01))
        with self.assertRaises(CommandError):
            cad.constraint_add(dict(type='TANGENT', refs=[dict(id=a), dict(id=b)], **OWNER))


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TangentArcTests)
    suite = unittest.TestSuite(t for t in suite if t._testMethodName in TangentArcTests.__dict__)
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
        raise SystemExit(1)
