"""Modifiers retain visual detail while CAD picks complete source references."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import bpy
from mathutils import Vector, Quaternion
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_cad import CadTests, OWNER
from blender_tablet_remote.cad import document as model
from blender_tablet_remote.cad.runtime import runtime
from blender_tablet_remote.cad.surface import stamp
from blender_tablet_remote.commands import cad, snap
from blender_tablet_remote.camera import camera
from blender_tablet_remote.bpy_utils import find_view3d


class ModifierSelectionTests(CadTests):
    def subdivided(self, kind='CATMULL_CLARK', level=2):
        self.extrude(self.rect())
        obj=self.obj()
        mod=obj.modifiers.new('Subdivision','SUBSURF')
        mod.subdivision_type=kind; mod.levels=level
        bpy.context.view_layer.update()
        return obj,mod

    def test_subdivision_keeps_six_faces_and_twelve_complete_edges(self):
        obj,mod=self.subdivided()
        for kind in ('CATMULL_CLARK','SIMPLE'):
            mod.subdivision_type=kind; bpy.context.view_layer.update()
            before=stamp(obj); doc=model.dumps(runtime.doc())
            attributes=list(obj.data.attributes.keys())
            graph=snap._cad_mesh(obj)
            self.assertEqual(len(graph[2]),96)
            self.assertEqual(len(set(graph[7])),6)
            self.assertEqual({len(region) for region in graph[7]},{16})
            self.assertEqual(len(set(graph[8].values())),12)
            self.assertEqual({len(region) for region in graph[8].values()},{4})
            self.assertEqual(len(graph[6]),48)  # The 144 new internal edges stay unselectable.
            self.assertEqual(stamp(obj),before)
            self.assertEqual(list(obj.data.attributes.keys()),attributes)
            self.assertEqual(model.dumps(runtime.doc()),doc)
            with patch.object(snap,'_cad_topology',side_effect=AssertionError('same geometry')):
                self.assertIs(snap._cad_mesh(obj),graph)

    def test_modifier_change_invalidates_selection_and_cached_regions(self):
        obj,mod=self.subdivided()
        graph=snap._cad_mesh(obj)
        runtime.surface.items=[dict(object=obj.name)]
        runtime.surface._stamps[obj.name]=stamp(obj)
        mod.levels=3; bpy.context.view_layer.update()
        runtime.surface.validate(); self.assertFalse(runtime.surface.items)
        updated=snap._cad_mesh(obj)
        self.assertIsNot(updated,graph)
        self.assertEqual(len(set(updated[7])),6)
        self.assertEqual({len(region) for region in updated[7]},{64})
        mod.show_viewport=False; bpy.context.view_layer.update()
        graph=snap._cad_mesh(obj)
        self.assertEqual(len(graph[2]),6)
        self.assertEqual(len(graph[6]),12)

    def test_temporary_lineage_is_removed_even_when_evaluation_fails(self):
        obj,mod=self.subdivided()
        before=list(obj.data.attributes.keys()); topology=snap._cad_topology
        def fail(mesh,matrix,face_labels=None,edge_labels=None,**_):
            if face_labels is not None: raise RuntimeError('evaluation failed')
            return topology(mesh,matrix)
        with patch.object(snap,'_cad_topology',side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,'evaluation failed'): snap._cad_mesh(obj)
        self.assertEqual(list(obj.data.attributes.keys()),before)
        self.assertNotIn(obj.as_pointer(),runtime.surface.graphs)
        self.assertEqual(mod.levels,2)

    def test_bevel_and_subdivision_keep_source_lineage_and_geometry(self):
        obj,mod=self.subdivided()
        bevel=obj.modifiers.new('Bevel','BEVEL');bevel.width=.002;bevel.segments=3
        obj.modifiers.move(1,0);bpy.context.view_layer.update()
        before=stamp(obj)
        graph=snap._cad_mesh(obj)
        self.assertEqual(len(set(graph[7])),6)
        self.assertTrue(all(len(region)>1 for region in graph[7]))
        self.assertLess(len(graph[6]),len(graph[5]))
        self.assertEqual(stamp(obj),before)

    @unittest.skipIf(bpy.app.background,'Real viewport projection required')
    def test_real_picks_use_design_planes_and_keep_evaluated_highlights(self):
        obj,mod=self.subdivided()
        camera.apply(location=(.04,.0225,.01),rotation=Quaternion(),distance=.09,perspective='ORTHO')
        graph=snap._cad_mesh(obj)
        face=max(range(len(graph[2])),key=lambda i:graph[4][i].z)
        region=graph[7][face]
        def pick(kind,position):
            screen=camera.project(position,find_view3d()[3]);self.assertIsNotNone(screen)
            cad.surface_mode(dict(mode=kind,**OWNER))
            return cad.surface_select(dict(u=screen[0],v=screen[1],**OWNER))
        before=model.dumps(runtime.doc())
        with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            state=pick('FACE',graph[4][min(region)])
            self.assertEqual(len(runtime.surface.items),1)
            item=runtime.surface.items[0]
            self.assertEqual(len(item['display']['triangles']),32)
            self.assertEqual(len(item['triangles']),2)
            self.assertEqual(len(item['display']['segments']),16)
            self.assertTrue(state['surface']['can_sketch'])
            self.assertTrue(item['planar'])
            self.assertFalse(item['display']['planar'])
            state=pick('FACE',graph[4][max(region)])
            self.assertFalse(runtime.surface.items)  # Another small quad toggles the same CAD face.
            edge=max(graph[6],key=lambda e:sum(graph[1][i].z for i in e))
            selected=graph[8][edge]
            first,last=min(selected),max(selected)
            pick('EDGE',sum((graph[1][i] for i in first),Vector())*.5)
            self.assertEqual(len(runtime.surface.items),1)
            self.assertEqual(len(runtime.surface.items[0]['display']['segments']),4)
            self.assertEqual(len(runtime.surface.items[0]['segments']),1)
            pick('EDGE',sum((graph[1][i] for i in last),Vector())*.5)
            self.assertFalse(runtime.surface.items)
            undo.assert_not_called()
        self.assertEqual(model.dumps(runtime.doc()),before)

    def pocket(self):
        bpy.context.scene.unit_settings.scale_length=.001
        runtime.step=.0005  # Drawing snaps to Increment; these are half-millimetre design values.
        base=self.draw('RECTANGLE',(-.0915,-.051),(.0915,.051))
        first=self.extrude(base,.03)
        cad.sketch_create(dict(support_id=first,**OWNER))
        hole=self.draw('RECTANGLE',(-.0865,-.0455),(.0865,.0455))
        cad.extrude_begin(dict(profile_id='profile_'+hole,operation='CUT',target_id=first,depth=.026,**OWNER))
        cad.confirm(OWNER)
        obj=self.obj()
        bevel=obj.modifiers.new('Bevel','BEVEL');bevel.width=1.;bevel.segments=3
        sub=obj.modifiers.new('Subdivision','SUBSURF');sub.levels=2
        bpy.context.view_layer.update()
        return obj,sub

    @unittest.skipIf(bpy.app.background,'Real viewport projection required')
    def test_pocket_bevel_points_edges_and_face_to_sketch_in_millimeter_scene(self):
        obj,sub=self.pocket()
        camera.apply(location=(0,0,15),rotation=Quaternion(),distance=250,perspective='ORTHO')
        def pick(kind,position):
            runtime.surface.clear()
            screen=camera.project(Vector(position),find_view3d()[3])
            cad.surface_mode(dict(mode=kind,**OWNER))
            return cad.surface_select(dict(u=screen[0],v=screen[1],**OWNER))
        before=model.dumps(runtime.doc()); pointer=obj.data.as_pointer()
        for enabled in (False,True):
            sub.show_viewport=enabled;bpy.context.view_layer.update()
            with patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
                self.assertEqual(len(pick('VERTEX',(-91.5,-51,30))['surface']['selection']),1)
                self.assertEqual(runtime.surface.items[0]['kind'],'VERTEX')
                self.assertLess((Vector(runtime.surface.items[0]['points'][0])-Vector((-91.5,-51,30))).length,1e-4)
                state=pick('EDGE',(0,-51,30))
                self.assertEqual(len(state['surface']['selection']),1)
                length=next(m['value'] for m in state['surface']['measurements'] if m['label']=='Longitud')
                self.assertAlmostEqual(length,.183,places=6)
                state=pick('FACE',(0,-49,30))
                self.assertTrue(state['surface']['can_sketch'])
                self.assertAlmostEqual(runtime.surface.face_frame()['origin'][2],.03,places=6)
                self.assertEqual(obj.data.as_pointer(),pointer)
                self.assertEqual(model.dumps(runtime.doc()),before)
                undo.assert_not_called()
        with patch.object(snap,'query_cad_surface',side_effect=AssertionError('second raycast')),patch('blender_tablet_remote.cad.runtime.undo_push') as undo:
            cad.sketch_on_face(OWNER);undo.assert_called_once()
        self.assertAlmostEqual(model.frame(runtime.doc()['sketches'][-1])['origin'][2],.03,places=6)
        self.assertEqual([m.type for m in obj.modifiers],['BEVEL','SUBSURF'])

    @unittest.skipIf(bpy.app.background,'Real viewport projection required')
    def test_design_corner_does_not_select_through_another_object(self):
        obj,sub=self.pocket()
        camera.apply(location=(0,0,15),rotation=Quaternion(),distance=250,perspective='ORTHO')
        bpy.ops.mesh.primitive_cube_add(size=20,location=(-91.5,-51,60))
        blocker=bpy.context.object
        bpy.context.view_layer.update()
        screen=camera.project(Vector((-91.5,-51,30)),find_view3d()[3])
        selected=snap.query_cad_surface(dict(u=screen[0],v=screen[1]),'VERTEX')
        self.assertTrue(selected is None or selected['object']==blocker.name)


def run():
    suite=unittest.TestSuite(ModifierSelectionTests(name) for name in ModifierSelectionTests.__dict__ if name.startswith('test_'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        import os;os._exit(1)
    if not bpy.app.background:bpy.ops.wm.quit_blender()

if __name__=='__main__':
    if bpy.app.background:run()
    else:bpy.app.timers.register(run,first_interval=1.)
