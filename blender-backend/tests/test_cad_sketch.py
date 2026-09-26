"""Sketch editing and pocket integration, using real Blender meshes."""
import copy
import math
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.cad import document as model, sketch as geometry
from blender_tablet_remote.cad.runtime import runtime, FEATURE_KEY
from blender_tablet_remote.commands import cad
from blender_tablet_remote.errors import CommandError
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_cad import CadTests, OWNER, volume


class SketchTests(CadTests):
    def test_an_edge_below_the_sketch_projects_onto_that_plane(self):
        cad.sketch_create(dict(plane='XY', offset=.015, **OWNER))
        with patch.object(runtime.surface, 'validate'):
            runtime.surface.mode='EDGE'
            runtime.surface.items=[dict(id='e',kind='EDGE',object='Base',feature_id=None,planar=True,segments=[[[0,0,0],[.04,0,0]]],points=[[0,0,0],[.04,0,0]])]
            cad.project_reference(OWNER)
        line=runtime.doc()['sketches'][-1]['entities'][0]
        self.assertTrue(line['construction'] and line['reference'])
        self.assertAlmostEqual(line['x'],0,places=6)
        self.assertAlmostEqual(line['x2'],.04,places=6)
        self.assertAlmostEqual(line['y'],0,places=6)
        self.assertEqual(runtime.surface.mode,'PROFILE')
        angles=[i*math.tau/16 for i in range(16)]
        points=[[.02+.01*math.cos(a), .02+.01*math.sin(a), 0] for a in angles]
        cad.sketch_create(dict(plane='XY', offset=.015, **OWNER))
        with patch.object(runtime.surface, 'validate'):
            runtime.surface.mode='EDGE'
            runtime.surface.items=[dict(id='c',kind='EDGE',object='Base',feature_id=None,planar=True,points=points,segments=[[points[i], points[(i+1)%16]] for i in range(16)])]
            cad.project_reference(OWNER)
        circle=runtime.doc()['sketches'][-1]['entities'][0]
        self.assertEqual(circle['type'],'CIRCLE')
        self.assertAlmostEqual(circle['x'],.02,places=5)
        self.assertAlmostEqual(circle['y'],.02,places=5)
        self.assertAlmostEqual(circle['diameter'],.02,places=5)

    def test_symmetric_extrude_grows_equally_both_sides_of_the_sketch(self):
        rectangle=self.rect()
        cad.extrude_begin(dict(profile_id='profile_'+rectangle, depth=.02, extent='BOTH', **OWNER))
        self.assertEqual(runtime.session['extent'],'BOTH')
        cad.confirm(OWNER)
        obj=self.obj()
        zs=[(obj.matrix_world@v.co).z for v in obj.data.vertices]
        self.assertAlmostEqual(min(zs),-.02,places=5)
        self.assertAlmostEqual(max(zs),.02,places=5)
        self.assertAlmostEqual(volume(obj),.08*.045*.04,places=6)
        self.assertEqual(model.find(runtime.doc(),'features',obj[FEATURE_KEY])['extent'],'BOTH')

    def test_sketch_view_stands_upright_on_a_horizontal_plane(self):
        from mathutils import Vector
        from blender_tablet_remote.camera import camera
        self.rect()
        sketch=runtime.doc()['sketches'][0]
        runtime.focus(sketch)
        forward=camera.rotation@Vector((0,0,-1))
        up=camera.rotation@Vector((0,1,0))
        self.assertGreater(forward.dot(Vector((0,0,-1))),.99)
        self.assertGreater(up.dot(Vector((0,1,0))),.99)
        self.assertEqual(camera.perspective,'ORTHO')

    def test_rounding_all_rectangle_corners_at_once_and_one_by_one_share_a_radius(self):
        from blender_tablet_remote.cad import dimensions
        def arcs(): return [e for e in runtime.doc()['sketches'][0]['entities'] if e['type']=='ARC']
        rectangle=self.rect()
        self.select_refs((rectangle,'BODY')); cad.fillet(dict(radius=.005,**OWNER))
        self.assertEqual(len(arcs()),4)
        self.assertEqual(len(runtime.selection['items']),4)
        sketch=runtime.doc()['sketches'][0]
        self.assertEqual(len(model.profiles(sketch)),1)  # still one closed rounded profile
        cad.entity_set(dict(entity_id=arcs()[2]['id'],values={'radius':.008},**OWNER))  # one value edits all four
        self.assertTrue(all(abs(a['radius']-.008)<1e-9 for a in arcs()))
        cad.sketch_create(dict(plane='XY',**OWNER))
        second=self.rect()
        self.select_refs((second,'P1')); cad.fillet(dict(radius=.004,**OWNER))
        line=next(e for e in runtime.doc()['sketches'][1]['entities'] if e['type']=='LINE' and abs(e['x']-.08)<1e-9 and abs(e['y']-.045)<1e-9)
        self.select_refs((line['id'],'START')); cad.fillet(dict(radius=.004,**OWNER))  # a later corner, after the conversion
        self.assertEqual(len([e for e in runtime.doc()['sketches'][1]['entities'] if e['type']=='ARC']),2)

    def test_regular_polygon_draws_by_across_flats_and_extrudes_a_nut_profile(self):
        with patch.object(runtime,'point',return_value=(0,0)), patch.object(cad,'_endpoint',return_value=None):
            cad.entity_begin(dict(type='NGON',u=.1,v=.1,**OWNER))
        with patch.object(runtime,'point',return_value=(.0059,0)), patch.object(cad,'_endpoint',return_value=None):
            identifier=cad.entity_update(dict(u=.2,v=.1,**OWNER))['selection']['id']
        cad.confirm(OWNER)
        sketch,e=model.entity(runtime.doc(),identifier)
        self.assertEqual(e['sides'],6)
        self.assertAlmostEqual(e['flats'],.010,places=9)  # 2·5.9 mm·cos 30° = 10.2 → 10 mm with Increment
        self.assertEqual(len(geometry.handles(e)),7)  # center and six corners
        cad.entity_set(dict(entity_id=identifier,values={'flats':.013},**OWNER))  # M8 nut wrench size
        sketch,e=model.entity(runtime.doc(),identifier)
        corners=[geometry.point(sketch,dict(id=identifier,part='P'+str(i))) for i in range(6)]
        for a,b in zip(corners,corners[1:]+corners[:1]): self.assertAlmostEqual(math.dist(a,b),.013/math.sqrt(3),places=9)
        self.extrude(identifier,.0065)
        self.assertAlmostEqual(volume(self.obj()),math.sqrt(3)/2*.013**2*.0065,places=12)
        cad.entity_set(dict(entity_id=identifier,values={'sides':8},**OWNER))
        sketch,e=model.entity(runtime.doc(),identifier)
        self.assertEqual((e['sides'],len(model.outline(e))),(8,8))
        self.assertAlmostEqual(e['flats'],.013,places=9)
        described=model.public(runtime.doc())['sketches'][0]['entities'][0]['dimensions'][0]
        self.assertEqual((described['field'],described['constraint_type'],described['value_factor']),('flats','RADIUS',.5))

    def draw_extra(self, typ, start, end, **extra):
        with patch.object(runtime,'point',return_value=start), patch.object(cad,'_endpoint',return_value=None):
            cad.entity_begin(dict(type=typ,u=.1,v=.1,**extra,**OWNER))
        with patch.object(runtime,'point',return_value=end), patch.object(cad,'_endpoint',return_value=None):
            identifier=cad.entity_update(dict(u=.2,v=.1,**OWNER))['selection']['id']
        cad.confirm(OWNER)
        return identifier

    def test_slot_draws_between_cap_centers_and_keeps_its_length_dimension(self):
        identifier=self.draw_extra('SLOT',(0,0),(.0201,0))
        sketch,e=model.entity(runtime.doc(),identifier)
        self.assertAlmostEqual(e['length'],.020,places=9)
        self.assertAlmostEqual(e['width'],.008,places=9)
        self.assertAlmostEqual(geometry.point(sketch,dict(id=identifier,part='START'))[0],0,places=9)
        cad.constraint_add(dict(type='DISTANCE',value=.020,refs=[dict(id=identifier,part='AXIS')],**OWNER))
        cad.entity_set(dict(entity_id=identifier,values={'width':.006,'length':.030},**OWNER))
        sketch,e=model.entity(runtime.doc(),identifier)
        self.assertAlmostEqual(e['length'],.030,places=9)
        self.assertAlmostEqual(e['width'],.006,places=9)
        self.assertAlmostEqual(next(c for c in sketch['constraints'] if c['type']=='DISTANCE')['value'],.030,places=9)
        described=model.public(runtime.doc())['sketches'][0]['entities'][0]['dimensions']
        self.assertEqual([(d['field'],d['value_factor']) for d in described],[('width',.5),('length',1.)])
        self.extrude(identifier,.005)
        expected=(.030*.006+math.pi*.003**2)*.005
        self.assertAlmostEqual(volume(self.obj()),expected,delta=expected*.005)

    def test_gear_draws_a_standard_module_and_keeps_it_when_teeth_change(self):
        identifier=self.draw_extra('GEAR',(0,0),(.0105,0),teeth=20)
        sketch,e=model.entity(runtime.doc(),identifier)
        self.assertEqual((e['teeth'],e['pressure']),(20,20.))
        self.assertAlmostEqual(e['module'],.001,places=12)  # 1,05 mm → module 1 with Increment
        pitch,base,tip,root=model.gear_radii(e)
        ring=model.outline(e)
        radii=[math.hypot(*p) for p in ring]
        self.assertAlmostEqual(max(radii),tip,places=9)
        self.assertAlmostEqual(min(radii),root,places=9)
        cad.constraint_add(dict(type='RADIUS',value=pitch,refs=[dict(id=identifier,part='BODY')],**OWNER))
        cad.entity_set(dict(entity_id=identifier,values={'teeth':30},**OWNER))
        sketch,e=model.entity(runtime.doc(),identifier)
        self.assertAlmostEqual(e['module'],.001,places=12)
        self.assertAlmostEqual(next(c for c in sketch['constraints'] if c['type']=='RADIUS')['value'],.015,places=12)
        cad.entity_set(dict(entity_id=identifier,values={'module':.0015},**OWNER))
        sketch,e=model.entity(runtime.doc(),identifier)
        self.assertAlmostEqual(e['module'],.0015,places=12)
        described=model.public(runtime.doc())['sketches'][0]['entities'][0]['dimensions'][0]
        self.assertEqual((described['field'],described['constraint_type'],described['value_factor']),('module','RADIUS',15.))
        self.extrude(identifier,.005)
        pitch,base,tip,root=model.gear_radii(e)
        self.assertTrue(math.pi*root**2*.005 < volume(self.obj()) < math.pi*tip**2*.005)
        with self.assertRaises(CommandError):
            cad.entity_set(dict(entity_id=identifier,values={'teeth':3},**OWNER))

    def test_sketch_copy_sits_on_a_parallel_plane_whose_separation_stays_editable(self):
        rect=self.rect()
        source=runtime.doc()['sketches'][0]
        cad.constraint_add(dict(type='DISTANCE',value=.08,refs=[dict(id=rect,part='EDGE0')],**OWNER))
        status=cad.sketch_copy(dict(sketch_id=source['id'],offset=.03,**OWNER))
        doc=runtime.doc(); copy_=doc['sketches'][1]
        self.assertEqual(status['selection'],dict(kind='SKETCH',id=copy_['id']))
        self.assertAlmostEqual(model.frame(copy_)['origin'][2],.03,places=12)
        self.assertEqual(len(copy_['entities']),1)
        self.assertNotEqual(copy_['entities'][0]['id'],rect)
        self.assertEqual(copy_['constraints'][0]['refs'][0]['id'],copy_['entities'][0]['id'])
        self.assertEqual(model.outline(copy_['entities'][0]),model.outline(source['entities'][0]))
        cad.plane_set(dict(plane_id=copy_['plane_id'],translation=[0,0,-.02],**OWNER))
        self.assertAlmostEqual(model.frame(runtime.doc()['sketches'][1])['origin'][2],-.02,places=12)
        with self.assertRaises(CommandError): cad.sketch_delete(dict(sketch_id=source['id'],**OWNER))
        cad.sketch_delete(dict(sketch_id=copy_['id'],**OWNER))
        self.assertEqual(runtime.doc()['planes'],[])

    def test_loft_joins_two_parallel_sketches_into_one_solid_and_one_undo(self):
        rect=self.rect()
        source=runtime.doc()['sketches'][0]
        cad.sketch_copy(dict(sketch_id=source['id'],offset=.03,**OWNER))
        copy_=runtime.doc()['sketches'][1]
        cad.loft_create(dict(from_sketch_id=source['id'],to_sketch_id=copy_['id'],**OWNER))
        self.assertAlmostEqual(volume(self.obj()),.08*.045*.03,places=10)
        feature=runtime.doc()['features'][0]
        self.assertEqual((feature['type'],feature['to_sketch_id']),('LOFT',copy_['id']))
        # Halving the top turns the prism into a frustum: h/3·(A1+A2+√(A1·A2)).
        top=copy_['entities'][0]['id']
        cad.entity_set(dict(entity_id=top,values={'width':.04,'height':.0225},**OWNER))
        a1,a2=.08*.045,.04*.0225
        self.assertAlmostEqual(volume(self.obj()),.03/3*(a1+a2+math.sqrt(a1*a2)),places=10)
        with self.assertRaises(CommandError): cad.sketch_delete(dict(sketch_id=copy_['id'],**OWNER))
        self.assertFalse(model.sketch_visible(runtime.doc(),runtime.doc()['sketches'][1]))

    def test_loft_from_a_circle_to_a_square_and_rejects_coplanar_sketches(self):
        circle=self.draw('CIRCLE',(0,0),(.02,0))
        source=runtime.doc()['sketches'][0]
        cad.sketch_copy(dict(sketch_id=source['id'],offset=.05,**OWNER))
        copy_=runtime.doc()['sketches'][1]
        with self.assertRaises(CommandError):
            cad.loft_create(dict(from_sketch_id=source['id'],to_sketch_id=source['id'],**OWNER))
        cad.sketch_activate(dict(sketch_id=copy_['id'],**OWNER))
        cad.entity_delete(dict(entity_id=copy_['entities'][0]['id'],**OWNER))
        self.draw('RECTANGLE',(-.015,-.015),(.015,.015))
        cad.sketch_finish(OWNER)
        cad.loft_create(dict(from_sketch_id=source['id'],to_sketch_id=copy_['id'],**OWNER))
        v=volume(self.obj())
        self.assertTrue(.03**2*.05 < v < math.pi*.02**2*.05)
        with self.assertRaises(CommandError):  # coplanar: rejected, the document keeps its separation
            cad.plane_set(dict(plane_id=copy_['plane_id'],translation=[0,0,0],**OWNER))
        self.assertEqual(model.find(runtime.doc(),'planes',copy_['plane_id'])['translation'],[0.,0.,.05])

    def test_drawing_uses_increment_grid_point_snap_and_drops_collapsed_figures(self):
        def entity(identifier):
            return next(e for s in runtime.doc()['sketches'] for e in s['entities'] if e['id']==identifier)
        rect=entity(self.draw('RECTANGLE',(.01234,.00488),(.05071,.03012)))
        self.assertEqual([round(rect[k],9) for k in ('x','y','width','height')],[.012,.005,.039,.025])
        circle=entity(self.draw('CIRCLE',(.1,.1),(.1173,.1)))
        self.assertAlmostEqual(circle['diameter'],.034,places=9)  # Increment rounds the radius (17 mm).
        with patch.object(runtime,'point',return_value=(0,0)), patch.object(cad,'_endpoint',return_value=None):
            cad.entity_begin(dict(type='RECTANGLE',u=.1,v=.1,**OWNER))
        with patch.object(runtime,'point',return_value=(.0004,.0001)), patch.object(cad,'_endpoint',return_value=None):
            status=cad.entity_update(dict(u=.1,v=.1,**OWNER))
        self.assertFalse(status['session']['can_confirm'])  # An accidental tap never leaves a sub-step rectangle.
        cad.cancel(OWNER)
        origin=dict(entity_id='ORIGIN',part='POINT',id='ORIGIN:POINT',distance=0.)
        with patch.object(runtime,'point',return_value=(.0003,-.0002)), patch.object(cad,'_endpoint',return_value=origin):
            cad.entity_begin(dict(type='CIRCLE',u=.1,v=.1,**OWNER))
        with patch.object(runtime,'point',return_value=(.02,0)), patch.object(cad,'_endpoint',return_value=None):
            identifier=cad.entity_update(dict(u=.2,v=.1,**OWNER))['selection']['id']
        cad.confirm(OWNER)
        self.assertEqual((entity(identifier)['x'],entity(identifier)['y']),(0,0))
        sketch=runtime.doc()['sketches'][0]
        self.assertTrue(any(c['type']=='COINCIDENT' and dict(id=identifier,part='CENTER') in c['refs'] for c in sketch['constraints']))

    def test_reopen_selected_profile_or_feature_edits_source_without_duplicate_or_navigation_undo(self):
        entity = self.rect()
        sketch_id = runtime.active_sketch_id
        feature = self.extrude(entity)
        baseline = copy.deepcopy(runtime.doc())
        for kind, identifier in [('PROFILE', 'profile_' + entity), ('FEATURE', feature)]:
            cad.select(dict(kind=kind, id=identifier, **OWNER))
            with patch.object(runtime, 'focus') as focus, patch.object(cad, 'undo_push') as command_undo, \
                    patch('blender_tablet_remote.cad.runtime.undo_push') as runtime_undo:
                status = cad.sketch_activate(dict(sketch_id=sketch_id, **OWNER))
                self.assertEqual(status['active_sketch_id'], sketch_id)
                self.assertIsNone(status['selection'])
                focus.assert_called_once()
                self.assertEqual(focus.call_args.args[0]['id'], sketch_id)
                cad.sketch_finish(OWNER)
                command_undo.assert_not_called()
                runtime_undo.assert_not_called()
            self.assertEqual(runtime.doc(), baseline)
        cad.sketch_activate(dict(sketch_id=sketch_id, **OWNER))
        cad.select(dict(kind='ENTITY', id=entity, **OWNER))
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            cad.entity_set(dict(entity_id=entity, values={'width': .1}, **OWNER))
            undo.assert_called_once()
        cad.sketch_finish(OWNER)
        self.assertEqual(len(runtime.doc()['sketches']), 1)
        self.assertEqual(len(runtime.doc()['features']), 1)
        self.assertEqual(self.obj()[FEATURE_KEY], feature)
        self.assertAlmostEqual(volume(self.obj()), .1 * .045 * .02, places=10)

    def select_refs(self,*refs):
        cad._set_selection([dict(kind='ENTITY',id=identifier,part=part) for identifier,part in refs])

    def rule(self,typ,**payload):
        return cad.constraint_add(dict(type=typ,**payload,**OWNER))

    def test_square_is_persistent_equal_sides_constraint(self):
        e=self.square((0,0),(.04,.02))
        cad.entity_set(dict(entity_id=e,values={'width':.06},**OWNER))
        sketch,entity=model.entity(runtime.doc(),e)
        self.assertAlmostEqual(entity['height'],.06,places=8)
        self.assertEqual(sketch['constraints'][0]['type'],'EQUAL')

    def test_constraints_propagate_and_conflicts_are_atomic(self):
        a=self.draw('LINE',(0,0),(.04,.01))
        self.select_refs((a,'BODY')); self.rule('HORIZONTAL')
        sketch,e=model.entity(runtime.doc(),a)
        self.assertAlmostEqual(e['y'],e['y2'],places=9)
        self.rule('DISTANCE',value=.05)
        self.rule('FIX')
        raw=bpy.context.scene[model.KEY]
        with self.assertRaises(CommandError): cad.entity_set(dict(entity_id=a,values={'x2':.2},**OWNER))
        self.assertEqual(raw,bpy.context.scene[model.KEY])
        restored=model.loads(raw)
        self.assertEqual(len(restored['sketches'][0]['constraints']),3)

    def test_coincident_point_drag_preserves_join_and_horizontal(self):
        a=self.draw('LINE',(0,0),(.04,0))
        b=self.draw('LINE',(.04,.01),(.04,.04))
        self.select_refs((a,'END'),(b,'START')); self.rule('COINCIDENT')
        self.select_refs((a,'BODY')); self.rule('HORIZONTAL')
        sketch=model.entity(runtime.doc(),a)[0]
        goals=geometry.move_goals(sketch,[dict(id=b,part='START')],.01,.005)
        geometry.solve(sketch,goals)
        pa=geometry.handles(model.find(sketch,'entities',a)); pb=geometry.handles(model.find(sketch,'entities',b))
        self.assertLess(math.dist(pa['END'],pb['START']),1e-8)
        self.assertAlmostEqual(pa['START'][1],pa['END'][1],places=8)

    def test_parallel_perpendicular_equal_and_radius(self):
        a=self.draw('LINE',(0,0),(.04,0))
        b=self.draw('LINE',(.01,.02),(.03,.05))
        self.select_refs((a,'BODY'),(b,'BODY')); self.rule('PARALLEL'); self.rule('EQUAL')
        sketch=runtime.doc()['sketches'][0]
        for c in sketch['constraints']: self.assertLess(max(abs(v) for v in geometry.residual(sketch,c,1)),1e-7)
        c=self.draw('CIRCLE',(.1,.1),(.11,.1))
        self.select_refs((c,'BODY')); self.rule('RADIUS',value=.015)
        self.assertAlmostEqual(model.entity(runtime.doc(),c)[1]['diameter'],.03,places=8)
        self.select_refs((a,'BODY'),(b,'BODY'))
        raw=bpy.context.scene[model.KEY]
        with self.assertRaises(CommandError): self.rule('PERPENDICULAR')
        self.assertEqual(raw,bpy.context.scene[model.KEY])

    def test_fillet_trims_corner_and_chain_extrudes(self):
        ids=[self.draw('LINE',a,b) for a,b in [((0,0),(.08,0)),((.08,0),(.08,.04)),((.08,.04),(0,.04)),((0,.04),(0,0))]]
        self.select_refs((ids[0],'BODY'),(ids[1],'BODY'))
        cad.fillet(dict(radius=.005,**OWNER))
        sketch=runtime.doc()['sketches'][0]
        self.assertEqual(len(sketch['entities']),5)
        self.assertEqual(len(sketch['constraints']),5)
        profiles=model.profiles(sketch)
        self.assertEqual(len(profiles),1)
        cad.extrude_begin(dict(profile_id=profiles[0]['id'],depth=.02,**OWNER)); cad.confirm(OWNER)
        expected=(.08*.04-.005**2*(1-math.pi/4))*.02
        self.assertAlmostEqual(volume(self.obj()),expected,delta=2e-9)
        raw=bpy.context.scene[model.KEY]
        self.assertEqual(model.profiles(model.loads(raw)['sketches'][0]),profiles)

    def test_invalid_fillet_preserves_original(self):
        a=self.draw('LINE',(0,0),(.04,0)); b=self.draw('LINE',(.04,0),(.04,.03))
        self.select_refs((a,'BODY'),(b,'BODY')); raw=bpy.context.scene[model.KEY]
        with self.assertRaises(CommandError): cad.fillet(dict(radius=.1,**OWNER))
        self.assertEqual(raw,bpy.context.scene[model.KEY])

    def test_arc_dimensions_keep_angles_in_degrees(self):
        a=self.draw('ARC',(0,0),(.04,0))
        cad.entity_set(dict(entity_id=a,values={'sweep':180.,'radius':.02},**OWNER))
        arc=model.entity(runtime.doc(),a)[1]
        self.assertAlmostEqual(arc['sweep'],180.)
        self.assertLess(math.dist(model.outline(arc)[-1],(-.02,0)),1e-8)
        self.assertFalse(model.profiles(runtime.doc()['sketches'][0]))

    def test_drag_has_one_undo_and_cancel_restores(self):
        a=self.draw('LINE',(0,0),(.04,0)); raw=bpy.context.scene[model.KEY]
        hit=dict(kind='ENTITY',id=a,part='END')
        with patch.object(cad,'_pick',return_value=hit), patch.object(runtime,'point',return_value=(.04,0)):
            cad.drag_begin(dict(u=.2,v=.2,**OWNER))
        with patch.object(cad,'undo_push') as undo:
            with patch.object(runtime,'point',return_value=(.0414,.0014)):
                cad.drag_update(dict(u=.3,v=.3,**OWNER))
            preview=model.entity(runtime.session['preview'],a)[1]
            self.assertAlmostEqual(preview['x2'],.041,places=8)
            self.assertEqual(raw,bpy.context.scene[model.KEY])
            cad.drag_end(OWNER)
            self.assertEqual(undo.call_count,1)
        with patch.object(cad,'_pick',return_value=hit), patch.object(runtime,'point',return_value=(.041,.001)):
            cad.drag_begin(dict(u=.2,v=.2,**OWNER))
        with patch.object(cad,'undo_push') as undo: cad.drag_end(OWNER); undo.assert_not_called()
        with patch.object(cad,'_pick',return_value=hit), patch.object(runtime,'point',return_value=(.041,.001)):
            cad.drag_begin(dict(u=.2,v=.2,**OWNER))
        baseline=bpy.context.scene[model.KEY]
        with patch.object(runtime,'point',return_value=(.05,.01)): cad.drag_update(dict(u=.4,v=.4,**OWNER))
        cad.cancel(OWNER)
        self.assertEqual(baseline,bpy.context.scene[model.KEY])

    def test_drag_keeps_multiselection_and_owner(self):
        a=self.draw('LINE',(0,0),(.04,0)); b=self.draw('LINE',(0,.02),(.04,.02))
        self.select_refs((a,'BODY'),(b,'BODY'))
        with patch.object(cad,'_pick',return_value=dict(kind='ENTITY',id=a,part='BODY')), patch.object(runtime,'point',return_value=(.02,0)):
            cad.drag_begin(dict(u=.2,v=.2,**OWNER))
        with self.assertRaises(CommandError): cad.drag_end({'_client_id':'other'})
        with patch.object(runtime,'point',return_value=(.023,.005)): cad.drag_update(dict(u=.3,v=.3,**OWNER))
        cad.drag_end(OWNER)
        for identifier in (a,b): self.assertAlmostEqual(model.entity(runtime.doc(),identifier)[1]['x'],.003,places=8)

    def pocket(self):
        base=self.extrude(self.rect())
        cad.sketch_create(dict(support_id=base,**OWNER))
        hole=self.draw('RECTANGLE',(.01,.01),(.03,.025))
        state=cad.extrude_begin(dict(operation='CUT',target_id=base,profile_id='profile_'+hole,depth=.005,**OWNER))
        return base,hole,state['selection']['id']

    def test_cut_extent_grows_one_side_or_both(self):
        base=self.extrude(self.rect())
        cad.sketch_create(dict(plane='XY',offset=.01,**OWNER))
        hole=self.draw('RECTANGLE',(.01,.01),(.03,.025))
        area=.02*.015
        original=.08*.045*.02
        state=cad.extrude_begin(dict(operation='CUT',target_id=base,profile_id='profile_'+hole,depth=.004,extent='ONE',**OWNER))
        cut=state['selection']['id']
        def cut_object(): return next(o for o in runtime.objects(runtime.doc()) if o[FEATURE_KEY]==cut)
        self.assertEqual(state['session']['extent'],'ONE')
        self.assertAlmostEqual(volume(cut_object()),original-area*.004,places=10)
        state=cad.extrude_update(dict(extent='BOTH',**OWNER))
        self.assertEqual(state['session']['extent'],'BOTH')
        self.assertAlmostEqual(volume(cut_object()),original-area*.008,places=10)
        cad.extrude_update(dict(extent='ONE',depth=.004,**OWNER))
        self.assertAlmostEqual(volume(cut_object()),original-area*.004,places=10)
        with self.assertRaises(CommandError): cad.extrude_update(dict(extent='SIDEWAYS',**OWNER))
        cad.confirm(OWNER)
        self.assertEqual(model.find(runtime.doc(),'features',cut)['extent'],'ONE')
        cad.feature_set(dict(feature_id=cut,extent='BOTH',**OWNER))
        self.assertEqual(model.find(runtime.doc(),'features',cut)['extent'],'BOTH')
        self.assertAlmostEqual(volume(cut_object()),original-area*.008,places=10)

    def test_cut_depth_is_subtractive_and_cancel_restores(self):
        base,hole,cut=self.pocket()
        original=.08*.045*.02
        def cut_object(): return next(o for o in runtime.objects(runtime.doc()) if o[FEATURE_KEY]==cut)
        self.assertAlmostEqual(volume(cut_object()),original-.02*.015*.005,places=10)
        for delta,expected in ((.08,.007),(-.04,.004),(.02,.005)):
            cad.extrude_update(dict(gesture=delta,baseline_depth=.005,**OWNER))
            self.assertAlmostEqual(runtime.session['depth'],expected,places=8)
            self.assertAlmostEqual(volume(cut_object()),original-.02*.015*expected,places=10)
        self.assertTrue(runtime.status()['session']['transparent'])
        cad.cancel(OWNER)
        self.assertEqual(len(runtime.objects(runtime.doc())),1)
        self.assertAlmostEqual(volume(self.obj()),original,places=10)
        self.assertFalse(self.obj().hide_viewport)
        self.assertFalse(any(o.name.startswith('CAD cutter') for o in bpy.data.objects))

    def test_cut_rebuild_persist_dependency_and_scene_units(self):
        bpy.context.scene.unit_settings.scale_length=.001
        base,hole,cut=self.pocket(); cad.confirm(OWNER)
        raw=bpy.context.scene[model.KEY]; doc=model.loads(raw)
        self.assertEqual(doc['features'][-1]['target_id'],base)
        cutobj=next(o for o in runtime.objects(doc) if o[FEATURE_KEY]==cut)
        self.assertAlmostEqual(volume(cutobj),80*45*20-20*15*5,delta=.03)
        with self.assertRaises(CommandError): cad.feature_delete(dict(feature_id=base,**OWNER))
        self.assertEqual(raw,bpy.context.scene[model.KEY])
        cad.entity_set(dict(entity_id=hole,values={'width':.025},**OWNER))
        self.assertAlmostEqual(volume(cutobj),80*45*20-25*15*5,delta=.03)

    def test_supported_plane_tracks_base_height_and_cut_persists(self):
        base,hole,cut=self.pocket(); cad.confirm(OWNER)
        cad.feature_set(dict(feature_id=base,depth=.03,**OWNER))
        doc=runtime.doc(); sketch,_=model.entity(doc,hole)
        self.assertAlmostEqual(sketch['offset'],.03)
        cutobj=next(o for o in runtime.objects(doc) if o[FEATURE_KEY]==cut)
        self.assertAlmostEqual(volume(cutobj),.08*.045*.03-.02*.015*.005,places=10)

    def test_square_drag_projects_to_constraint_and_keeps_center(self):
        identifier=self.square((0,0),(.04,.04))
        sketch=runtime.doc()['sketches'][0]
        goals=geometry.move_goals(sketch,[dict(id=identifier,part='P2')],.01,.02)
        geometry.solve(sketch,goals,drag=True)
        e=model.find(sketch,'entities',identifier)
        self.assertAlmostEqual(e['x']+e['width']/2,.02,places=8)
        self.assertAlmostEqual(e['y']+e['height']/2,.02,places=8)
        self.assertAlmostEqual(e['width'],e['height'],places=8)
        self.assertGreater(e['width'],.04)

    def test_multi_corner_drag_translates_rectangle_without_anchoring_selected_points(self):
        identifier=self.rect(); sketch=runtime.doc()['sketches'][0]
        refs=[dict(id=identifier,part=part) for part in ('P0','P2')]
        geometry.solve(sketch,geometry.move_goals(sketch,refs,.01,.005),drag=True)
        e=model.find(sketch,'entities',identifier)
        self.assertAlmostEqual(e['x'],.01,places=8); self.assertAlmostEqual(e['y'],.005,places=8)
        self.assertAlmostEqual(e['width'],.08,places=8); self.assertAlmostEqual(e['height'],.045,places=8)

    def test_locked_drag_is_noop_without_empty_undo(self):
        identifier=self.draw('LINE',(0,0),(.04,0))
        self.select_refs((identifier,'BODY')); self.rule('FIX')
        with patch.object(cad,'_pick',return_value=dict(kind='ENTITY',id=identifier,part='END')), patch.object(runtime,'point',return_value=(.04,0)):
            cad.drag_begin(dict(u=.2,v=.2,**OWNER))
        with patch.object(runtime,'point',return_value=(.05,.01)): cad.drag_update(dict(u=.4,v=.4,**OWNER))
        with patch.object(cad,'undo_push') as undo: cad.drag_end(OWNER); undo.assert_not_called()

    def test_auto_coincidence_uses_last_stable_endpoint(self):
        a=self.draw('LINE',(0,0),(.04,0))
        anchor=dict(entity_id=a,part='END',id=a+':END')
        with patch.object(cad,'_endpoint',return_value=anchor),patch.object(runtime,'point',return_value=(.041,.001)):
            cad.entity_begin(dict(type='LINE',u=.2,v=.2,**OWNER))
        with patch.object(cad,'_endpoint',return_value=None),patch.object(runtime,'point',return_value=(.04,.04)):
            cad.entity_update(dict(u=.4,v=.4,**OWNER))
        with patch.object(runtime,'point',side_effect=AssertionError('release raycast')): cad.confirm(OWNER)
        sketch=runtime.doc()['sketches'][0]
        self.assertEqual(sketch['constraints'][0]['type'],'COINCIDENT')
        self.assertEqual(geometry.handles(sketch['entities'][0])['END'],geometry.handles(sketch['entities'][1])['START'])

    def test_transparency_is_scoped_even_when_render_fails(self):
        self.pocket()
        shading=SimpleNamespace(type='MATERIAL',show_xray=False,xray_alpha=.5)
        with self.assertRaises(RuntimeError):
            with runtime.preview_shading(SimpleNamespace(shading=shading)):
                self.assertTrue(shading.show_xray); self.assertEqual(shading.xray_alpha,.35)
                raise RuntimeError('render failed')
        self.assertEqual((shading.type,shading.show_xray,shading.xray_alpha),('MATERIAL',False,.5))


def run():
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(SketchTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        import os
        os._exit(1)
    if not bpy.app.background: bpy.ops.wm.quit_blender()


if __name__=='__main__':
    if bpy.app.background: run()
    else: bpy.app.timers.register(run,first_interval=1.)
