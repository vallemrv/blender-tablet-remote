"""Native mesh groups, live Edit weights and modifier influence."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
import bpy,bmesh
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import vertex_groups as groups,modifiers,history,sessions
from blender_tablet_remote.errors import CommandError
from blender_tablet_remote import state

class VertexGroupTests(unittest.TestCase):
    def setUp(self):
        sessions.cancel_all()
        if bpy.context.object and bpy.context.object.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add();self.obj=bpy.context.object
        bpy.ops.object.mode_set(mode='EDIT')
        self.select([0,1])
    def select(self,ids):
        bm=bmesh.from_edit_mesh(self.obj.data);bm.verts.ensure_lookup_table();bm.verts.index_update()
        for face in bm.faces:face.select_set(False)
        for edge in bm.edges:edge.select_set(False)
        for v in bm.verts:v.select_set(v.index in ids)
        bm.select_mode={'VERT'};bm.select_flush_mode();bmesh.update_edit_mesh(self.obj.data)
    def weights(self,name):
        index=self.obj.vertex_groups[name].index;bm=bmesh.from_edit_mesh(self.obj.data);bm.verts.index_update()
        layer=bm.verts.layers.deform.active
        return {v.index:v[layer][index] for v in bm.verts if layer and index in v[layer]}
    def test_save_selection_is_one_step_and_shared_with_painting(self):
        from blender_tablet_remote.commands import mode,material
        from blender_tablet_remote.materials.runtime import runtime as painting
        with patch.object(groups,'undo_push') as undo:
            groups.create(dict(name='Zona común',assign_selection=True));undo.assert_called_once()
        self.assertEqual(self.weights('Zona común'),{0:1.,1:1.})
        bpy.ops.object.mode_set(mode='OBJECT')
        mode.mode_set(dict(mode='MATERIAL',_client_id='test'))
        try:
            self.assertIn('GROUP:Zona común',[r['id'] for r in painting.status()['regions']])
            with patch.object(material,'undo_push') as undo:
                material.group(dict(name='Desde pintura',_client_id='test'));undo.assert_called_once()
            self.assertEqual(painting.scope,'GROUP:Desde pintura')
        finally:painting.leave()
        name=modifiers.add(dict(type='SIMPLE_DEFORM',parameters=dict(vertex_group='Desde pintura')))['modifier']
        self.assertEqual(self.obj.modifiers[name].vertex_group,'Desde pintura')
        bpy.ops.object.mode_set(mode='EDIT')
        self.assertEqual(self.weights('Desde pintura'),{0:1.,1:1.})
    def test_save_selection_validates_every_target_before_creating_any_group(self):
        bpy.ops.object.mode_set(mode='OBJECT')
        other=self.obj.copy();other.data=self.obj.data.copy();bpy.context.collection.objects.link(other)
        for v in other.data.vertices:v.select=False
        with self.assertRaises(CommandError):groups.save_selection([self.obj,other],'Zona')
        self.assertFalse(self.obj.vertex_groups);self.assertFalse(other.vertex_groups)

    def test_assign_remove_zero_weight_and_select_without_leaving_edit(self):
        groups.create(dict(name='Zona'))
        with patch.object(groups,'undo_push') as undo:
            result=groups.edit(dict(name='Zona',action='ASSIGN',weight=.25));undo.assert_called_once()
        self.assertEqual(self.weights('Zona'),{0:.25,1:.25});self.assertEqual(self.obj.mode,'EDIT')
        self.assertEqual(result['active']['vertex_groups'],[dict(name='Zona',locked=False)])
        self.select([2]);groups.edit(dict(name='Zona',action='ASSIGN',weight=0))
        groups.edit(dict(name='Zona',action='SELECT'))
        bm=bmesh.from_edit_mesh(self.obj.data)
        self.assertEqual({v.index for v in bm.verts if v.select},{0,1,2})
        self.select([1]);groups.edit(dict(name='Zona',action='REMOVE'))
        self.assertEqual(self.weights('Zona'),{0:.25,2:0.})
        groups.edit(dict(name='Zona',action='SELECT'));groups.edit(dict(name='Zona',action='DESELECT'))
        self.assertFalse(any(v.select for v in bm.verts))
    def test_rename_delete_preserve_other_group_weights_in_edit(self):
        groups.create(dict(name='Uno'));groups.edit(dict(name='Uno',action='ASSIGN',weight=.5))
        self.select([2,3]);groups.create(dict(name='Dos'));groups.edit(dict(name='Dos',action='ASSIGN',weight=.75))
        groups.rename(dict(name='Dos',new_name='Zona'))
        self.assertEqual(self.weights('Zona'),{2:.75,3:.75})
        groups.delete(dict(name='Uno'));self.assertEqual(self.weights('Zona'),{2:.75,3:.75})
    def test_invalid_or_locked_assignment_and_stale_object_are_atomic(self):
        groups.create(dict(name='Zona'));before=self.weights('Zona')
        for weight in [-1,2,float('nan')]:
            with self.assertRaises(CommandError):groups.edit(dict(name='Zona',action='ASSIGN',weight=weight))
            self.assertEqual(self.weights('Zona'),before)
        self.obj.vertex_groups['Zona'].lock_weight=True
        with self.assertRaises(CommandError):groups.edit(dict(name='Zona',action='ASSIGN',weight=.2))
        with self.assertRaises(CommandError):groups.create(dict(name='Otra',object='Otro objeto'))
        with self.assertRaises(CommandError):groups.create(dict(name='Zona'))
        self.assertEqual(len(self.obj.vertex_groups),1)
    def test_simple_deform_only_moves_assigned_vertices_and_invert_switches_influence(self):
        groups.create(dict(name='Zona'));groups.edit(dict(name='Zona',action='ASSIGN',weight=1))
        bpy.ops.object.mode_set(mode='OBJECT')
        original=[v.co.copy() for v in self.obj.data.vertices]
        name=modifiers.add(dict(type='SIMPLE_DEFORM',parameters=dict(angle=90,vertex_group='Zona')))['modifier']
        for inverted in [False,True]:
            modifiers.set_params(dict(name=name,parameters=dict(invert_vertex_group=inverted)))
            bpy.context.view_layer.update();mesh=self.obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
            for i,v in enumerate(mesh.vertices):
                influenced=(i in [0,1]) != inverted
                self.assertEqual((v.co-original[i]).length>1e-5,influenced)
        groups.rename(dict(name='Zona',new_name='Local'))
        self.assertEqual(self.obj.modifiers[name].vertex_group,'Local')
        groups.delete(dict(name='Local'))
        self.assertEqual(self.obj.modifiers[name].vertex_group,'')
    @unittest.skipIf(bpy.app.background,'Native GUI undo required')
    def test_weight_assignment_has_native_undo_and_redo(self):
        groups.create(dict(name='Zona'))
        groups.edit(dict(name='Zona',action='ASSIGN',weight=.25))
        history.undo({});self.obj=bpy.context.object;self.assertEqual(self.weights('Zona'),{})
        history.redo({});self.obj=bpy.context.object;self.assertEqual(self.weights('Zona'),{0:.25,1:.25})

def run():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(VertexGroupTests))
    if not result.wasSuccessful():
        import os
        os._exit(1)
    if not bpy.app.background:bpy.ops.wm.quit_blender()
if __name__=='__main__':
    if bpy.app.background:run()
    else:bpy.app.timers.register(run,first_interval=1.)
