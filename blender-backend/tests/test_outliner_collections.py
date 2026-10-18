"""blender --background --factory-startup --python-exit-code 1 --python este_archivo"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import outliner, sessions
from blender_tablet_remote.errors import BadPayload, CommandError


class CollectionTests(unittest.TestCase):
    def setUp(self):
        sessions.cancel_all()
        if bpy.context.object and bpy.context.object.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
        for obj in list(bpy.data.objects): bpy.data.objects.remove(obj, do_unlink=True)
        bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection
        bpy.ops.mesh.primitive_cube_add(location=(1, 2, 3))
        self.first = bpy.context.object
        bpy.ops.mesh.primitive_cube_add(location=(4, 5, 6))
        self.second = bpy.context.object
        self.patch = patch.object(outliner, 'undo_push')
        self.undo = self.patch.start()

    def tearDown(self): self.patch.stop()
    def identity(self, obj): return outliner._identity(obj)
    def create(self, name='Piezas', parent=None, objects=()):
        result = outliner.collection_action(dict(action='CREATE', name=name, parent_id=parent,
                                                object_ids=[self.identity(o) for o in objects]))
        created = result['created_collection']
        return bpy.data.collections[created['name']], created['id']

    def test_create_empty_and_nested_collections_are_listed(self):
        parent, parent_id = self.create()
        child, child_id = self.create('Referencias', parent_id)
        self.assertIn(child.name, parent.children)
        rows = {c['id']: c for c in outliner.listing({})['collections']}
        self.assertEqual(rows[child_id]['count'], 0)
        self.assertEqual(rows[child_id]['parents'], [parent_id])
        self.assertIn('Piezas / Referencias', rows[child_id]['path'])
        self.assertEqual(self.undo.call_count, 2)

    def test_create_with_selection_moves_both_in_one_undo_without_geometry_changes(self):
        self.first.parent = self.second
        bpy.context.view_layer.update()
        matrices = [obj.matrix_world.copy() for obj in (self.first, self.second)]
        meshes = [obj.data for obj in (self.first, self.second)]
        destination, _ = self.create(objects=(self.first, self.second))
        for index, obj in enumerate((self.first, self.second)):
            self.assertEqual(list(obj.users_collection), [destination])
            self.assertEqual(obj.matrix_world, matrices[index])
            self.assertEqual(obj.data, meshes[index])
        self.assertEqual(self.first.parent, self.second)
        self.undo.assert_called_once()

    def test_move_between_collections_keeps_memberships_outside_current_scene(self):
        foreign = bpy.data.scenes.new('Otra escena')
        foreign.collection.objects.link(self.first)
        destination, dest_id = self.create()
        self.undo.reset_mock()
        outliner.collection_action(dict(action='MOVE_OBJECTS', collection_id=dest_id,
                                        object_ids=[self.identity(self.first)]))
        self.assertIn(self.first.name, foreign.collection.objects)
        self.assertIn(self.first.name, destination.objects)
        self.assertNotIn(self.first.name, bpy.context.scene.collection.objects)
        self.undo.assert_called_once()
        outliner.collection_action(dict(action='MOVE_OBJECTS', collection_id=dest_id,
                                        object_ids=[self.identity(self.first)]))
        self.undo.assert_called_once()

    def test_invalid_name_stale_object_and_stale_parent_leave_no_collection(self):
        before = len(bpy.data.collections)
        for payload in [dict(action='CREATE', name=' '),
                        dict(action='CREATE', name='Error', object_ids=['missing']),
                        dict(action='CREATE', name='Error', parent_id='missing')]:
            with self.assertRaises((BadPayload, CommandError)): outliner.collection_action(payload)
            self.assertEqual(len(bpy.data.collections), before)
        self.undo.assert_not_called()

    def test_multiple_parents_share_identity_and_report_both_paths(self):
        parent_a, aid = self.create('Grupo A')
        parent_b, bid = self.create('Grupo B')
        child, cid = self.create('Compartida', aid)
        parent_b.children.link(child)
        rows = [c for c in outliner.describe_collections() if c['id'] == cid]
        self.assertEqual(len(rows), 1)
        self.assertEqual(set(rows[0]['parents']), {aid, bid})

    def test_native_collection_membership_persists_in_blend(self):
        collection, _ = self.create('Guardada', objects=(self.first,))
        object_name, collection_name = self.first.name, collection.name
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'collections.blend')
            bpy.ops.wm.save_as_mainfile(filepath=path)
            bpy.ops.wm.open_mainfile(filepath=path)
            self.assertIn(object_name, bpy.data.collections[collection_name].objects)


if __name__ == '__main__':
    r = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CollectionTests))
    if not r.wasSuccessful(): raise SystemExit(1)
