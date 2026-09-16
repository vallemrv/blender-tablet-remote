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
        def fail(mesh,matrix,face_labels=None,edge_labels=None):
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
    def test_real_picks_toggle_whole_face_and_edge_and_reject_curved_sketch_plane(self):
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
            self.assertEqual(len(item['triangles']),32)
            self.assertEqual(len(item['segments']),16)
            self.assertFalse(state['surface']['can_sketch'])
            self.assertFalse(item['planar'])
            state=pick('FACE',graph[4][max(region)])
            self.assertFalse(runtime.surface.items)  # Another small quad toggles the same CAD face.
            edge=max(graph[6],key=lambda e:sum(graph[1][i].z for i in e))
            selected=graph[8][edge]
            first,last=min(selected),max(selected)
            pick('EDGE',sum((graph[1][i] for i in first),Vector())*.5)
            self.assertEqual(len(runtime.surface.items),1)
            self.assertEqual(len(runtime.surface.items[0]['segments']),4)
            pick('EDGE',sum((graph[1][i] for i in last),Vector())*.5)
            self.assertFalse(runtime.surface.items)
            undo.assert_not_called()
        self.assertEqual(model.dumps(runtime.doc()),before)


def run():
    suite=unittest.TestSuite(ModifierSelectionTests(name) for name in ModifierSelectionTests.__dict__ if name.startswith('test_'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        import os;os._exit(1)
    if not bpy.app.background:bpy.ops.wm.quit_blender()

if __name__=='__main__':
    if bpy.app.background:run()
    else:bpy.app.timers.register(run,first_interval=1.)
