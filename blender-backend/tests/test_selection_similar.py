"""Native similarity criteria: blender -b --factory-startup --python this_file."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import bpy
import bmesh

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import selection, sessions
from blender_tablet_remote.errors import CommandError
from blender_tablet_remote.protocol import EDIT_CATALOG, SELECTION_SIMILAR


class SimilarSelectionTests(unittest.TestCase):
    def setUp(self):
        sessions.cancel_all()
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        mesh = bpy.data.meshes.new('Similarity')
        coords = [(x+dx, y, 0) for x, width in ((0,1),(3,2),(7,1))
                  for dx,y in ((0,0),(width,0),(width,1),(0,1))]
        mesh.from_pydata(coords, [], [(i,i+1,i+2,i+3) for i in (0,4,8)])
        self.obj = bpy.data.objects.new('Similarity', mesh)
        bpy.context.collection.objects.link(self.obj)
        bpy.context.view_layer.objects.active = self.obj
        self.obj.select_set(True)
        for name in ('First', 'Second'):
            mesh.materials.append(bpy.data.materials.new(name))
        mesh.polygons[1].material_index = 1
        bpy.ops.object.mode_set(mode='EDIT')
        self.bm = bmesh.from_edit_mesh(mesh)
        for seq in (self.bm.verts,self.bm.edges,self.bm.faces): seq.ensure_lookup_table()
        self.undo_patch = patch('blender_tablet_remote.bpy_utils.undo_push')
        self.undo = self.undo_patch.start()

    def tearDown(self):
        self.undo_patch.stop()
        if self.obj.mode == 'EDIT': bpy.ops.object.mode_set(mode='OBJECT')

    def seed(self, mode, index=0):
        bpy.context.scene.tool_settings.mesh_select_mode = selection.MODE_FLAGS[mode]
        self.bm.select_mode = {dict(VERTEX='VERT',EDGE='EDGE',FACE='FACE')[mode]}
        for seq in (self.bm.verts,self.bm.edges,self.bm.faces):
            for elem in seq: elem.select = False
        if index is not None: selection._active_elements(self.bm)[index].select_set(True)
        self.bm.select_flush_mode()
        bmesh.update_edit_mesh(self.obj.data)

    def selected(self, mode):
        seq = dict(VERTEX=self.bm.verts,EDGE=self.bm.edges,FACE=self.bm.faces)[mode]
        return {elem.index for elem in seq if elem.select}

    def test_material_and_area_add_matching_faces_without_changing_mesh(self):
        original = [tuple(v.co) for v in self.bm.verts]
        for criterion in ('FACE_MATERIAL','FACE_AREA','FACE_PERIMETER'):
            self.seed('FACE')
            selection.similar(dict(type=criterion, threshold=.001))
            self.assertEqual(self.selected('FACE'), {0,2})
        self.assertEqual([tuple(v.co) for v in self.bm.verts], original)
        self.assertEqual(self.undo.call_count, 3)
        selection.similar(dict(type='FACE_AREA'))
        self.assertEqual(self.undo.call_count, 3)

    def test_edge_length_and_direction_use_current_submode(self):
        seed = next(e for e in self.bm.edges if abs(e.calc_length()-1)<1e-6)
        self.seed('EDGE', seed.index)
        selection.similar(dict(type='EDGE_LENGTH', threshold=.001))
        self.assertEqual(self.selected('EDGE'), {e.index for e in self.bm.edges if abs(e.calc_length()-1)<1e-6})
        self.seed('EDGE', seed.index)
        selection.similar(dict(type='EDGE_DIR', threshold=.001))
        direction = (seed.verts[1].co-seed.verts[0].co).normalized()
        self.assertTrue(all(abs((e.verts[1].co-e.verts[0].co).normalized().dot(direction))>.999 for e in self.bm.edges if e.select))

    def test_vertex_connectivity_and_hidden_elements(self):
        self.seed('VERTEX')
        self.bm.verts[8].hide_set(True)
        selection.similar(dict(type='VERT_EDGES'))
        self.assertFalse(self.bm.verts[8].select)
        self.assertTrue(self.bm.verts[4].select)

    def test_wrong_context_empty_seed_and_bad_threshold_do_not_modify_selection(self):
        self.seed('FACE')
        for payload in (dict(type='EDGE_LENGTH'),dict(type='FACE_AREA',threshold=-1)):
            with self.assertRaises(CommandError): selection.similar(payload)
            self.assertEqual(self.selected('FACE'), {0})
        self.seed('FACE', None)
        with self.assertRaises(CommandError): selection.similar(dict(type='FACE_AREA'))
        self.undo.assert_not_called()

    def test_every_advertised_variant_is_native_and_scoped(self):
        native = {item.identifier for item in bpy.ops.mesh.select_similar.get_rna_type().properties['type'].enum_items}
        for mode, variants in SELECTION_SIMILAR.items():
            action = next(a for a in EDIT_CATALOG['groups'][mode] if a['id']=='SELECT_SIMILAR')
            self.assertEqual({v['id'] for v in action['variants']}, {kind for kind,_ in variants})
            self.assertTrue({kind for kind,_ in variants} <= native)
            self.assertEqual(action['requirements']['selection_modes'], [mode])


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SimilarSelectionTests))
    if not result.wasSuccessful(): raise SystemExit(1)
